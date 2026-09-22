import asyncio

import pytest

from flypoker.engine import EngineConfig, LiveEngine
from flypoker.pokerkit_adapter import PokerKitTable, card_label
from flypoker.storage import EventStore
from flypoker.replay import reconstruct
from flypoker.announcer import announce_action


class FakeBrainWorker:
    def __init__(self):
        self.request_id = None

    def submit_features(self, request_id, _features):
        self.request_id = request_id
        return True

    def poll(self):
        if self.request_id is None:
            return None
        request_id, self.request_id = self.request_id, None
        return {
            "requestId": request_id,
            "result": {
                "action": ["check-call"] * 6,
                "sizing": ["half-pot"] * 6,
                "actionLogits": [[0.4, -0.2, 0.9]] * 6,
                "activity": [0.77] * 6,
                "regions": [{"sensory": 0.11, "central": 0.22, "drives": 0.33, "motor": 0.44}] * 6,
                "sampledSpikes": [[42, 84]] * 6,
                "sampledNeuronCount": 12000,
            },
        }


def test_six_profiles_have_distinct_ids_and_seats():
    engine = LiveEngine()
    players = engine.snapshot.players
    assert len(players) == 6
    assert [player.seat for player in players] == list(range(6))
    assert len({player.id for player in players}) == 6
    assert len({player.style for player in players}) == 6
    assert max(player.vpip for player in players) - min(player.vpip for player in players) > 0.1
    assert max(player.pfr for player in players) - min(player.pfr for player in players) > 0.1


def test_action_policy_is_legal_vocabulary():
    engine = LiveEngine()
    legal = {"fold", "call", "raise", "all-in"}
    for player in engine.snapshot.players:
        for _ in range(20):
            assert engine._action_for(player, "flop") in legal


def test_illegal_or_non_string_readout_falls_back_to_legal_action():
    assert LiveEngine._legal_action("raise", ["check"]) == "check"
    assert LiveEngine._legal_action("call", ["check"]) == "check"
    assert LiveEngine._legal_action(object(), ["fold"]) == "fold"


@pytest.mark.asyncio
async def test_emit_increments_sequence_and_notifies_listener():
    engine = LiveEngine()
    received = []

    async def listener(event):
        received.append(event)

    engine.add_listener(listener)
    await engine._emit("test.event", {"ok": True})
    assert engine.sequence == 1
    assert received[0].type == "test.event"
    assert received[0].payload == {"ok": True}


@pytest.mark.asyncio
async def test_brain_result_drives_real_telemetry_payload():
    worker = FakeBrainWorker()
    engine = LiveEngine(EngineConfig(decision_seconds=0), brain_worker=worker)
    table = PokerKitTable([2000] * 6, deck_seed=123)
    actor_id = engine.snapshot.players[table.actor_index or 0].id
    action = await engine._brain_action(engine.snapshot.players, table, "preflop", 0, [])
    assert action == "call"
    telemetry = engine.neural_telemetry[actor_id]
    assert telemetry["mode"] == "flybrain"
    assert telemetry["activity"] == 0.77
    assert telemetry["regions"] == {"sensory": 0.11, "central": 0.22, "drives": 0.33, "motor": 0.44}
    assert telemetry["sampledSpikes"] == [42, 84]
    assert telemetry["sampledNeuronCount"] == 12000
    assert set(telemetry["features"]) == {"LC10a", "LPLC1", "LPLC2", "LC4"}
    assert telemetry["stimulatedPopulations"] == ["LC10a", "LPLC1", "LPLC2", "LC4"]


@pytest.mark.asyncio
async def test_pokerkit_driven_hand_emits_completion():
    engine = LiveEngine(EngineConfig(decision_seconds=0))
    await engine._play_hand()
    assert engine.hand_number == 1
    assert 0 <= engine.deck_seed <= 2**32 - 1
    assert engine.snapshot.street == "showdown"
    assert any(event.type == "hand.completed" for event in engine.recent_events)


@pytest.mark.asyncio
async def test_pokerkit_tournament_survives_eliminations(tmp_path):
    engine = LiveEngine(EngineConfig(decision_seconds=0, intermission_seconds=0), store=EventStore(tmp_path / "tournament.db"))
    for _ in range(12):
        await engine._play_hand()
    assert engine.hand_number >= 1
    assert engine.store.latest_checkpoint() is not None


def test_feature_values_are_bounded():
    engine = LiveEngine()
    for player in engine.snapshot.players:
        features = engine._features(player)
        assert all(0 <= value <= 1 for value in features.values())


def test_pokerkit_table_exposes_legal_actions():
    table = PokerKitTable()
    assert table.actor_index is not None
    assert "fold" in table.legal_actions()
    table.apply("fold")


def test_pokerkit_all_in_path_builds_side_pots_and_conserves_chips():
    table = PokerKitTable([100, 50, 200, 200, 200, 200], deck_seed=1)
    starting_total = sum(table.stacks) + sum(table.state.bets)
    for _ in range(6):
        actor = table.actor_index
        assert actor is not None
        if actor == 2:
            table.apply("raise", 200)
        elif actor == 5:
            table.apply("fold")
        else:
            table.apply("call")
    assert sum(table.stacks) == starting_total
    # Short stacks and deeper callers force PokerKit to resolve a main pot and
    # a side-pot-eligible payoff path; the exact winner is deck-seed dependent.
    assert max(int(payoff) for payoff in table.state.payoffs) >= 250
    assert any(int(payoff) < 0 for payoff in table.state.payoffs)


def test_pokerkit_card_labels_are_browser_safe():
    table = PokerKitTable()
    assert all(any(suit in card for suit in "♠♥♦♣") for cards in table.hole_cards for card in cards)


def test_pokerkit_deal_is_reproducible_from_hand_seed():
    first = PokerKitTable([2000] * 6, deck_seed=918273)
    second = PokerKitTable([2000] * 6, deck_seed=918273)
    other = PokerKitTable([2000] * 6, deck_seed=918274)
    assert first.hole_cards == second.hole_cards
    assert first.hole_cards != other.hole_cards


def test_blind_layout_rotates_and_handles_heads_up():
    engine = LiveEngine()
    engine.hand_number = 1
    assert engine._blind_layout([True] * 6, 10, 20) == (0, 10, 20, 0, 0, 0)
    engine.hand_number = 2
    assert engine._blind_layout([True] * 6, 10, 20) == (0, 0, 10, 20, 0, 0)
    engine.hand_number = 1
    assert engine._blind_layout([True, False, True, False, False, False], 10, 20) == (10, 0, 20, 0, 0, 0)
    table = PokerKitTable([100, 1, 100, 1, 1, 1], blind_layout=(10, 0, 20, 0, 0, 0))
    assert tuple(table.state.blinds_or_straddles) == (10, 0, 20, 0, 0, 0)


def test_replay_reducer_preserves_split_pot_winners():
    state = reconstruct([
        {"type": "showdown.resolved", "payload": {"winnerId": "vesper", "winnerIds": ["vesper", "hex"], "payouts": {"vesper": 75, "hex": 75}, "board": [], "pot": 150, "players": []}},
    ])
    assert state["winnerIds"] == ["vesper", "hex"]
    assert state["payouts"] == {"vesper": 75, "hex": 75}


def test_announcer_is_deterministic_and_keyed_by_action_context():
    first = announce_action("Vesper", "tight-aggressive", "raise", "flop", 0.72, 460)
    assert first == announce_action("Vesper", "tight-aggressive", "raise", "flop", 0.72, 460)
    assert first != announce_action("Vesper", "tight-aggressive", "fold", "flop", 0.22, 460)


def test_metrics_snapshot_is_bounded_and_serializable():
    engine = LiveEngine()
    metrics = engine.metrics_snapshot()
    assert metrics["websocketClients"] == 0
    assert metrics["eventSequence"] == 0
    assert isinstance(metrics["tournamentId"], str)


@pytest.mark.asyncio
async def test_checkpoint_restore_preserves_sequence_and_hand(tmp_path):
    store = EventStore(tmp_path / "checkpoint.db")
    first = LiveEngine(store=store)
    first.hand_number = 7
    first.hand_id = "hand-0007"
    first.snapshot.hand_number = 7
    first.snapshot.hand_id = "hand-0007"
    await first._emit("hand.completed", {"replaySlug": "tourney-hand-0007"})
    restored = LiveEngine(store=store, restore_checkpoint=True)
    assert restored.hand_id == "hand-0007"
    assert restored.hand_number == 7
    assert restored.sequence == first.sequence


@pytest.mark.asyncio
async def test_brain_reset_aborts_partial_hand_and_keeps_checkpoint_sequence(tmp_path):
    store = EventStore(tmp_path / "reset.db")
    checkpointed = LiveEngine(store=store)
    checkpointed.hand_number = 3
    checkpointed.hand_id = "hand-0003"
    checkpointed.snapshot.hand_number = 3
    checkpointed.snapshot.hand_id = "hand-0003"
    await checkpointed._emit("hand.completed", {"replaySlug": "tourney-hand-0003"})
    engine = LiveEngine(EngineConfig(decision_seconds=0), store=store)
    engine.sequence = 20
    engine.request_brain_reset("test worker restart")
    await engine._play_hand()
    assert not any(event.type == "hand.completed" for event in engine.recent_events)
    engine._restore_completed_checkpoint()
    assert engine.hand_id == "hand-0003"
    assert engine.sequence >= 20
