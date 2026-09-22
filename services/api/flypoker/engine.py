from __future__ import annotations

import asyncio
import math
import random
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .models import EventEnvelope, FlyProfile, TableSnapshot, now_iso
from .announcer import announce_action, announce_thinking
from .pokerkit_adapter import PokerKitTable
from .poster import render_poster
from .storage import EventStore
from .uploader import ReplayUploader


EventSink = Callable[[EventEnvelope], Awaitable[None]]


PROFILE_DATA = [
    ("vesper", "Vesper", "tight-aggressive", "#e9c46a", "A single antenna sweep before a sharp raise."),
    ("sugar", "Sugar", "loose-aggressive", "#f4a261", "Her wings buzz when the pot smells sweet."),
    ("knuckles", "Knuckles", "short-stack pressure", "#e76f51", "A restless foreleg taps the felt."),
    ("velvet", "Velvet", "trap-heavy", "#b56576", "She grooms slowly when the table thinks she is weak."),
    ("static", "Static", "high-variance", "#72efdd", "A bright tremor travels through both wings."),
    ("hex", "Hex", "balanced / pot-odds", "#9b8afb", "Both antennae settle into a precise, quiet line."),
]
PROFILE_STATS = {
    "vesper": (0.566, 0.293, 0.519),
    "sugar": (0.852, 0.636, 0.746),
    "knuckles": (0.869, 0.632, 0.728),
    "velvet": (0.601, 0.069, 0.115),
    "static": (0.897, 0.752, 0.838),
    "hex": (0.647, 0.227, 0.351),
}
DECISION_DELAY_SECONDS = {
    "vesper": 1.65,
    "sugar": 3.4,
    "knuckles": 2.1,
    "velvet": 4.0,
    "static": 2.75,
    "hex": 2.3,
}


@dataclass
class EngineConfig:
    tick_seconds: float = 1.15
    decision_seconds: float = 2.2
    intermission_seconds: float = 45.0
    replay_limit: int = 200


class LiveEngine:
    """Deterministic spectator engine.

    This simulator deliberately exposes the same event surface as the real
    batched FlyBrain runner. Replace `_brain_step` with the CUDA adapter when
    MaleCNS data and readout artifacts are available.
    """

    def __init__(self, config: EngineConfig | None = None, store: EventStore | None = None, brain_worker: Any | None = None, restore_checkpoint: bool = False, brain_seed: int = 20260921) -> None:
        self.config = config or EngineConfig()
        self.store = store or EventStore()
        self.replay_uploader = ReplayUploader()
        self.brain_worker = brain_worker
        self.brain_seeds = [brain_seed + index for index in range(6)]
        self.tournament_id = f"tourney-{secrets.token_hex(4)}"
        self.hand_number = 0
        self.hand_id = "boot"
        self.deck_seed = 0
        self.sequence = 0
        self.listeners: set[EventSink] = set()
        self.recent_events: list[EventEnvelope] = []
        self.snapshot = self._initial_snapshot()
        self._restored_checkpoint = False
        if restore_checkpoint:
            checkpoint = self.store.latest_checkpoint()
            if checkpoint is not None:
                self.snapshot = checkpoint
                self.tournament_id = checkpoint.tournament_id
                self.hand_id = checkpoint.hand_id
                self.deck_seed = checkpoint.deck_seed
                self.hand_number = checkpoint.hand_number
                self.sequence = checkpoint.sequence
                self._restored_checkpoint = True
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._brain_reset_requested = False
        self._brain_reset_reason = "GPU worker restarted"
        self._rng = random.Random(1017)
        self.connected_spectators = 0
        self.readout_logits: dict[str, dict[str, float]] = {}
        self.readout_sizing: dict[str, str] = {}
        self.neural_telemetry: dict[str, dict[str, Any]] = {}
        self.step_latency_ms = 0.0
        self.hands_completed = 0
        self.decision_count = 0
        self.brain_fallbacks = 0
        self.replay_upload_failures = 0
        self.brain_worker_restarts = 0
        self.dropped_telemetry = 0
        self._last_telemetry_at = 0.0

    def _initial_snapshot(self) -> TableSnapshot:
        players = [
            FlyProfile(
                id=pid,
                name=name,
                style=style,
                accent=accent,
                chips=2000,
                seat=index,
                hole_cards=[],
                equity=0.0,
                activity=0.0,
                vpip=PROFILE_STATS[pid][0],
                pfr=PROFILE_STATS[pid][1],
                aggression=PROFILE_STATS[pid][2],
                tell=tell,
            )
            for index, (pid, name, style, accent, tell) in enumerate(PROFILE_DATA)
        ]
        return TableSnapshot(
            tournament_id=self.tournament_id,
            hand_id=self.hand_id,
            hand_number=0,
            street="intermission",
            players=players,
            last_event="The table is warming up.",
        )

    def add_listener(self, listener: EventSink) -> None:
        self.listeners.add(listener)

    def remove_listener(self, listener: EventSink) -> None:
        self.listeners.discard(listener)

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._running = True
        self._task = asyncio.create_task(self._run(), name="fly-poker-engine")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _run(self) -> None:
        if self._restored_checkpoint:
            self._restored_checkpoint = False
            await self._emit("brain.reset", {"reason": "restored last completed hand", "handId": self.hand_id, "seeds": self.brain_seeds})
        await self._emit("system.status", {"status": "live", "mode": "flybrain" if self.brain_worker else "simulated"})
        await self._emit("tournament.started", {"tournamentId": self.tournament_id, "players": [player.id for player in self.snapshot.players], "commentaryKey": "tournament.started"})
        while self._running:
            if self._brain_reset_requested:
                self._restore_completed_checkpoint()
                reason = self._brain_reset_reason
                self._brain_reset_requested = False
                await self._emit("brain.reset", {"reason": reason, "handId": self.hand_id, "seeds": self.brain_seeds})
                continue
            await self._play_hand()
            if self._brain_reset_requested:
                continue
            await asyncio.sleep(2.4)

    def request_brain_reset(self, reason: str = "GPU worker restarted") -> None:
        """Abort the in-flight hand at its next safe boundary."""
        self._brain_reset_reason = reason
        self._brain_reset_requested = True

    def _restore_completed_checkpoint(self) -> None:
        checkpoint = self.store.latest_checkpoint()
        if checkpoint is None:
            return
        sequence = self.sequence
        mode = self.snapshot.mode
        self.snapshot = checkpoint.model_copy(deep=True)
        self.snapshot.mode = mode
        self.tournament_id = checkpoint.tournament_id
        self.hand_id = checkpoint.hand_id
        self.hand_number = checkpoint.hand_number
        self.deck_seed = checkpoint.deck_seed
        # Sequence numbers never move backwards across a crash/reset.
        self.sequence = max(sequence, checkpoint.sequence)

    def _deck(self) -> list[str]:
        suits = ["♠", "♥", "♦", "♣"]
        ranks = list("23456789") + ["T", "J", "Q", "K", "A"]
        cards = [f"{rank}{suit}" for suit in suits for rank in ranks]
        self._rng.shuffle(cards)
        return cards

    async def _play_hand(self) -> None:
        if sum(1 for player in self.snapshot.players if player.chips > 0) < 2:
            champion = next((player for player in self.snapshot.players if player.chips > 0), None)
            if champion:
                self.snapshot.last_event = f"{champion.name} claims the table."
                await self._emit("champion", {"winnerId": champion.id, "message": f"{champion.name} claims the table.", "commentaryKey": "champion.ceremony"})
            await self._emit("tournament.completed", {"reason": "champion reached"})
            await asyncio.sleep(self.config.intermission_seconds)
            self.tournament_id = f"tourney-{secrets.token_hex(4)}"
            self.hand_number = 0
            for player in self.snapshot.players:
                player.chips = 2000
                player.alive = True
                player.status = "watching"
            await self._emit("intermission", {"message": "A new table is being dealt.", "commentaryKey": "intermission.new-tournament"})
            await self._emit("tournament.started", {"tournamentId": self.tournament_id, "players": [player.id for player in self.snapshot.players], "commentaryKey": "tournament.started"})

        self.hand_number += 1
        self.hand_id = f"hand-{self.hand_number:04d}"
        # Keep the persisted seed within JavaScript's exact integer range so
        # replay consumers can round-trip it without changing the deal.
        self.deck_seed = self._rng.getrandbits(32)
        players = self.snapshot.players
        small_blind, big_blind = self._blind_values()
        active_mask = [player.chips > 0 for player in players]
        blind_layout = self._blind_layout(active_mask, small_blind, big_blind)
        # PokerKit requires a positive stack for every configured seat. Dead
        # seats receive a one-chip sentinel and are folded automatically;
        # their public tournament stack remains zero throughout the hand.
        table = PokerKitTable(starting_stack=[max(1, player.chips) for player in players], small_blind=small_blind, big_blind=big_blind, deck_seed=self.deck_seed, blind_layout=blind_layout)
        for index, player in enumerate(players):
            player.alive = player.chips > 0
            player.hole_cards = table.hole_cards[index] if player.alive else []
            player.equity = self._estimate_equity(player.hole_cards, table.board) if player.alive else 0
            player.status = "watching" if player.alive else "eliminated"
            player.activity = 0.08

        self.snapshot = self.snapshot.model_copy(
            update={
                "tournament_id": self.tournament_id,
                "hand_id": self.hand_id,
                "deck_seed": self.deck_seed,
                "hand_number": self.hand_number,
                "street": "preflop",
                "board": [],
                "pot": sum(table.state.bets),
                "blind_level": min((self.hand_number - 1) // 6, 7),
                "blinds": self._blinds(),
                "current_actor": None,
                "last_event": "Fresh cards. Old grudges.",
            }
        )
        await self._emit("hand.started", {"handNumber": self.hand_number, "blinds": self.snapshot.blinds, "deckSeed": self.deck_seed, "commentaryKey": "hand.started"})
        await self._emit("cards.dealt", {"players": [{"id": p.id, "cards": p.hole_cards if p.alive else [], "equity": p.equity, "chips": p.chips, "alive": p.alive, "status": p.status} for p in players]})
        previous_board: list[str] = []
        public_action_history: list[str] = []
        action_count = 0
        eliminated_announced: set[str] = set()
        while table.state.status and action_count < 120:
            if self._brain_reset_requested:
                return
            actor_index = table.actor_index
            if actor_index is None:
                break
            player = players[actor_index]
            if not active_mask[actor_index]:
                table.apply("fold")
                player.status = "eliminated"
                action_count += 1
                continue
            street = self._street_for_board(table.board)
            self.snapshot.street = street
            self.snapshot.board = table.board
            self.snapshot.pot = table.state.total_pot_amount
            if table.board != previous_board:
                previous_board = table.board
                if table.board:
                    self.snapshot.last_event = f"The {street} arrives."
                await self._emit("street.revealed", {"street": street, "board": table.board, "commentaryKey": f"street.{street}"})
            self.snapshot.current_actor = player.id
            player.status = "thinking"
            player.activity = round(0.38 + self._rng.random() * 0.55, 2)
            self.snapshot.last_event = self._thinking_line(player, street)
            await self._emit("actor.thinking", {"playerId": player.id, "street": street, "commentaryKey": f"thinking.{player.id}.{street}", "features": self._features(player), "legalActions": table.legal_actions()})
            await asyncio.sleep(self._decision_delay(player))
            if self._brain_reset_requested:
                return
            preferred = await self._brain_action(players, table, street, action_count, public_action_history) if self.brain_worker else self._action_for(player, street)
            action = self._legal_action(preferred, table.legal_actions())
            amount = 0
            sizing_bucket = self.readout_sizing.pop(player.id, None)
            if action == "raise":
                amount = self._sizing_target(table, sizing_bucket)
                table.apply(action, amount)
            else:
                table.apply(action)
            action_count += 1
            self.decision_count += 1
            public_action_history.append(f"{player.id}:{action}:{amount}")
            display_action = "all-in" if action == "raise" and sizing_bucket == "all-in" else action
            player.status = display_action
            telemetry_activity = self.neural_telemetry.get(player.id, {}).get("activity")
            player.activity = float(telemetry_activity) if telemetry_activity is not None else round(0.35 + self._rng.random() * 0.6, 2)
            for index, stack in enumerate(table.stacks):
                players[index].chips = stack if active_mask[index] else 0
                players[index].alive = bool(active_mask[index] and table.state.statuses[index])
            self.snapshot.pot = table.state.total_pot_amount
            self.snapshot.last_event = self._action_line(player, display_action)
            await self._emit("action.committed", {
                "playerId": player.id,
                "action": display_action,
                "commentaryKey": f"action.{player.id}.{display_action}",
                "amount": amount,
                "sizing": sizing_bucket or "legal-clamp",
                "street": street,
                "board": table.board,
                "pot": table.state.total_pot_amount,
                "stacks": [int(players[index].chips) for index in range(len(players))],
                "players": [{"id": item.id, "chips": item.chips, "alive": item.alive, "status": item.status} for item in players],
                "logits": self.readout_logits.pop(player.id, self._logits(display_action)),
            })
            telemetry = self.neural_telemetry.pop(player.id, None)
            if telemetry is None:
                telemetry = {
                    "mode": "simulated",
                    "activity": player.activity,
                    "regions": self._regions(player.activity),
                    "sampledSpikes": self._sample_spikes(player.activity),
                    "sampledNeuronCount": 12000,
                }
            now = time.monotonic()
            if now - self._last_telemetry_at >= 0.1:
                self._last_telemetry_at = now
                await self._emit("brain.telemetry", {"playerId": player.id, **telemetry, "features": telemetry.get("features", self._features(player)), "stimulatedPopulations": telemetry.get("stimulatedPopulations", ["LC10a", "LPLC1", "LPLC2", "LC4"])})
            else:
                self.dropped_telemetry += 1

        payoffs = [int(value) for value in table.state.payoffs]
        active_indices = [index for index, active in enumerate(active_mask) if active]
        winner_indices = [index for index in active_indices if payoffs[index] > 0]
        if not winner_indices:
            winner_indices = [max(active_indices, key=lambda index: payoffs[index])]
        winner_index = winner_indices[0]
        winner = players[winner_index]
        for index, player in enumerate(players):
            player.chips = int(table.stacks[index]) if active_mask[index] else 0
            player.alive = bool(player.chips > 0)
            player.status = "winner" if index in winner_indices else ("eliminated" if player.chips <= 0 else "watching")
        winner_ids = [players[index].id for index in winner_indices]
        payouts = {players[index].id: max(payoffs[index], 0) for index in winner_indices}
        for player in players:
            if active_mask[player.seat] and player.chips <= 0 and player.id not in eliminated_announced:
                eliminated_announced.add(player.id)
                self.snapshot.last_event = f"{player.name} leaves the felt."
                await self._emit("elimination", {"playerId": player.id, "stack": 0, "commentaryKey": "elimination.player"})
        self.snapshot.current_actor = None
        self.snapshot.street = "showdown"
        self.snapshot.board = table.board
        self.snapshot.pot = table.state.total_pot_amount
        self.snapshot.last_event = f"{winner.name} takes the pot. The table goes quiet."
        await self._emit("showdown.resolved", {"winnerId": winner.id, "winnerIds": winner_ids, "payouts": payouts, "payoffs": payoffs, "commentaryKey": "showdown.split" if len(winner_ids) > 1 else "showdown.winner", "pot": self.snapshot.pot, "board": self.snapshot.board, "players": [{"id": item.id, "chips": item.chips, "alive": item.alive, "status": item.status} for item in players]})
        for winner_id, amount in payouts.items():
            await self._emit("payout", {"winnerId": winner_id, "amount": amount, "split": len(winner_ids) > 1})
        replay_slug = self._replay_slug()
        await self._emit("hand.completed", {"replaySlug": replay_slug})
        self.hands_completed += 1
        if self.replay_uploader.enabled:
            uploaded = await self.replay_uploader.upload(replay_slug, {"slug": replay_slug, "events": self.store.hand_events(self.tournament_id, self.hand_id), "snapshot": self.snapshot.model_dump(mode="json")}, render_poster(replay_slug, self.snapshot, winner.name))
            if not uploaded:
                self.replay_upload_failures += 1
                await self._emit("system.status", {"status": "replay-upload-failed", "slug": replay_slug})

    async def _brain_action(self, players: list[FlyProfile], table: PokerKitTable, street: str, action_count: int, public_action_history: list[str] | None = None) -> str:
        """Ask the six-lane worker for one actor's readout decision.

        Every lane receives a state built from that fly's own cards/equity and
        public table facts. Opponent private cards are never part of the pulse
        payload. A bounded timeout falls back to the deterministic development
        policy so a slow GPU cannot block spectators.
        """
        try:
            started = time.perf_counter()
            from training.encoder import PublicPokerState, encode_state

            to_call = float(getattr(table.state, "checking_or_calling_amount", 0))
            pot = float(max(1, table.state.total_pot_amount))
            pot_odds = min(1.0, max(0.0, to_call / (pot + to_call)))
            max_stack = max(1, max(table.stacks))
            state_street = street if street in {"preflop", "flop", "turn", "river"} else "river"
            sequences = [
                encode_state(
                    PublicPokerState(
                        own_equity=player.equity,
                        pot_odds=pot_odds,
                        position=player.seat / 5.0,
                        effective_stack_ratio=table.stacks[player.seat] / max_stack,
                        pot_pressure=min(1.0, pot / max(1.0, sum(table.stacks) + pot)),
                        aggression=min(1.0, player.equity),
                        legal_actions=tuple(table.legal_actions()),
                        street=state_street,
                        own_hole_cards=tuple(player.hole_cards),
                        public_board=tuple(table.board),
                        public_action_history=tuple(public_action_history or ()),
                    ),
                    steps=50,
                )
                for player in players
            ]
            request_id = f"{self.hand_id}-{action_count}"
            if not self.brain_worker.submit_features(request_id, sequences):
                self.brain_fallbacks += 1
                return self._action_for(players[table.actor_index or 0], street)
            for _ in range(400):
                response = self.brain_worker.poll()
                if response and response.get("requestId") == request_id:
                    if "result" not in response:
                        break
                    actor = table.actor_index or 0
                    result = response["result"]
                    activity = result.get("activity") or []
                    sampled_spikes = result.get("sampledSpikes") or []
                    regions = result.get("regions") or []
                    if actor < len(activity):
                        actor_activity = float(max(0.0, min(1.0, activity[actor])))
                        players[actor].activity = actor_activity
                        self.neural_telemetry[players[actor].id] = {
                            "mode": "flybrain",
                            "activity": round(actor_activity, 4),
                            "regions": regions[actor] if actor < len(regions) and isinstance(regions[actor], dict) else self._regions(actor_activity),
                            "sampledSpikes": sampled_spikes[actor] if actor < len(sampled_spikes) else [],
                            "sampledNeuronCount": int(result.get("sampledNeuronCount", 12000)),
                            # Keep the final 20 ms frame visible to inspectors;
                            # this is the exact engineered pulse presented to
                            # the actor's batched lane, not a synthetic HUD cue.
                            "features": sequences[actor][-1] if actor < len(sequences) else self._features(players[actor]),
                            "stimulatedPopulations": ["LC10a", "LPLC1", "LPLC2", "LC4"],
                        }
                    logits = result.get("actionLogits")
                    if logits is not None and actor < len(logits):
                        classes = ["check-call", "fold", "raise"]
                        try:
                            values = [float(value) for value in logits[actor]]
                        except (TypeError, ValueError):
                            values = []
                        if values and all(math.isfinite(value) for value in values):
                            self.readout_logits[players[actor].id] = {name: value for name, value in zip(classes, values, strict=False)}
                    sizes = result.get("sizing")
                    if sizes is not None and actor < len(sizes):
                        candidate = str(sizes[actor])
                        if candidate in {"half-pot", "three-quarter-pot", "pot", "all-in"}:
                            self.readout_sizing[players[actor].id] = candidate
                    self.step_latency_ms = (time.perf_counter() - started) * 1000
                    return str(result["action"][actor]).replace("check-call", "call")
                await asyncio.sleep(0.005)
        except Exception:
            # Readout, queue, or optional training imports are all fail-closed.
            self.brain_fallbacks += 1
            pass
        self.step_latency_ms = (time.perf_counter() - started) * 1000 if "started" in locals() else 0.0
        return self._action_for(players[table.actor_index or 0], street)

    @staticmethod
    def _sizing_target(table: PokerKitTable, bucket: str | None) -> int:
        minimum = int(table.state.min_completion_betting_or_raising_to_amount)
        maximum = int(table.state.max_completion_betting_or_raising_to_amount)
        if bucket == "all-in":
            return maximum
        multiplier = {"half-pot": 0.5, "three-quarter-pot": 0.75, "pot": 1.0}.get(bucket or "", 0.5)
        desired = int(table.state.checking_or_calling_amount + table.state.total_pot_amount * multiplier)
        return max(minimum, min(maximum, desired))

    def _blinds(self) -> str:
        small, big = self._blind_values()
        return f"{small} / {big}"

    def _blind_layout(self, active_mask: list[bool], small_blind: int, big_blind: int) -> tuple[int, ...]:
        """Rotate blinds over surviving seats, with heads-up button rules."""
        active = [index for index, is_active in enumerate(active_mask) if is_active]
        if len(active) < 2:
            return tuple([small_blind, big_blind, 0, 0, 0, 0])
        button_position = (self.hand_number - 1) % len(active)
        small_index = active[(button_position + 1) % len(active)] if len(active) > 2 else active[button_position]
        big_index = active[(button_position + 2) % len(active)] if len(active) > 2 else active[(button_position + 1) % len(active)]
        layout = [0] * len(active_mask)
        layout[small_index] = small_blind
        layout[big_index] = big_blind
        return tuple(layout)

    def _decision_delay(self, player: FlyProfile) -> float:
        if self.config.decision_seconds <= 0:
            return 0.0
        target = DECISION_DELAY_SECONDS.get(player.id, self.config.decision_seconds)
        # Keep the test/slow-mode knob useful while preserving the cinematic
        # 1.5–4 second personality envelope at the production default.
        return max(0.0, target * (self.config.decision_seconds / 2.2))

    def _blind_values(self) -> tuple[int, int]:
        levels = [(10, 20), (15, 30), (25, 50), (40, 80), (60, 120), (100, 200), (150, 300), (250, 500)]
        return levels[min((self.hand_number - 1) // 6, len(levels) - 1)]

    @staticmethod
    def _street_for_board(board: list[str]) -> str:
        return {0: "preflop", 3: "flop", 4: "turn", 5: "river"}.get(len(board), "showdown")

    @staticmethod
    def _estimate_equity(hole_cards: list[str], board: list[str]) -> float:
        """Fast spectator estimate used by the encoder and HUD.

        PokerKit remains authoritative for outcomes; this deliberately modest
        estimate is deterministic and card-derived rather than pretending to
        be a full Monte Carlo evaluator.
        """
        rank_values = {rank: value for value, rank in enumerate("23456789TJQKA", start=2)}
        ranks = [rank_values.get(card[:1].upper(), 2) for card in hole_cards[:2]]
        if not ranks:
            return 0.0
        score = 0.08 + (sum(ranks) / (2 * 14.0)) * 0.52
        if len(ranks) == 2 and ranks[0] == ranks[1]:
            score += 0.18
        if len(hole_cards) == 2 and hole_cards[0][-1:] == hole_cards[1][-1:]:
            score += 0.045
        board_ranks = {rank_values.get(card[:1].upper(), 2) for card in board}
        score += 0.04 * len(set(ranks) & board_ranks)
        return round(max(0.05, min(0.92, score)), 2)

    @staticmethod
    def _legal_action(preferred: str, legal: list[str]) -> str:
        if not isinstance(preferred, str):
            preferred = ""
        if preferred == "all-in":
            preferred = "raise"
        if preferred in legal:
            return preferred
        if preferred == "call" and "check" in legal:
            return "check"
        for fallback in ("check", "call", "fold"):
            if fallback in legal:
                return fallback
        return legal[0]

    def _features(self, player: FlyProfile) -> dict[str, float]:
        return {
            "LC10a": round(max(0.0, min(1.0, player.equity)), 2),
            "LPLC1": round(max(0.0, min(1.0, 1 - player.equity * 0.7)), 2),
            "LPLC2": round(max(0.0, min(1.0, player.activity)), 2),
            "LC4": round(max(0.0, min(1.0, player.activity * 0.8)), 2),
        }

    def _regions(self, activity: float) -> dict[str, float]:
        return {"sensory": round(activity * 0.75, 2), "central": round(activity * 0.94, 2), "drives": round(activity * 0.62, 2), "motor": round(activity, 2)}

    def _sample_spikes(self, activity: float) -> list[int]:
        return [self._rng.randrange(0, 166700) for _ in range(max(2, int(activity * 13)))]

    def _action_for(self, player: FlyProfile, street: str) -> str:
        # Development fallback is deterministic and threshold-based; it never
        # overrides a trained readout with a random personality coin flip.
        equity = player.equity
        if player.style == "tight-aggressive":
            return "raise" if equity > 0.52 else ("call" if equity > 0.31 else "fold")
        if player.style == "loose-aggressive":
            return "raise" if equity > 0.30 else ("call" if equity > 0.13 else "fold")
        if player.style == "short-stack pressure":
            return "all-in" if player.chips < 420 else ("raise" if equity > 0.34 else "call")
        if player.style == "trap-heavy":
            return "raise" if equity > 0.62 else ("call" if equity > 0.42 else "fold")
        if player.style == "high-variance":
            return "raise" if equity > 0.28 else ("call" if equity > 0.12 else "fold")
        return "raise" if equity > 0.58 else ("call" if equity > 0.27 else "fold")

    def _logits(self, action: str) -> dict[str, float]:
        base = {"fold": -0.1, "call": 0.18, "raise": 0.0, "all-in": 0.0}
        base[action] = 0.91
        return base

    def _thinking_line(self, player: FlyProfile, street: str) -> str:
        return announce_thinking(player.name, player.style, street, player.equity)

    def _action_line(self, player: FlyProfile, action: str) -> str:
        return announce_action(player.name, player.style, action, self.snapshot.street, player.equity, self.snapshot.pot)

    def _replay_slug(self) -> str:
        return f"{self.tournament_id}-{self.hand_id}"

    async def _emit(self, event_type: str, payload: dict) -> None:
        self.sequence += 1
        self.snapshot.sequence = self.sequence
        self.snapshot.updated_at = now_iso()
        event = EventEnvelope(tournament_id=self.tournament_id, hand_id=self.hand_id, sequence=self.sequence, type=event_type, payload=payload)
        self.recent_events.append(event)
        self.recent_events = self.recent_events[-self.config.replay_limit :]
        self.store.append(event)
        if event.type in {"hand.completed", "tournament.completed", "brain.reset"}:
            self.store.checkpoint(self.snapshot)
        for listener in tuple(self.listeners):
            try:
                await listener(event)
            except Exception:
                self.listeners.discard(listener)

    def metrics_snapshot(self) -> dict[str, object]:
        return {
            "tournamentId": self.tournament_id,
            "currentHand": self.hand_number,
            "handsCompleted": self.hands_completed,
            "decisions": self.decision_count,
            "brainFallbacks": self.brain_fallbacks,
            "replayUploadFailures": self.replay_upload_failures,
            "brainWorkerRestarts": self.brain_worker_restarts,
            "droppedTelemetry": self.dropped_telemetry,
            "websocketClients": self.connected_spectators,
            "eventSequence": self.sequence,
            "stepLatencyMs": round(self.step_latency_ms, 2),
            "brainSeeds": self.brain_seeds,
        }
