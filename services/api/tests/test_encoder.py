from training.encoder import PublicPokerState, encode_state, vectorize_state
from training.train_readouts import sample_states


def test_encoder_accepts_only_own_public_state_and_has_four_named_groups():
    state = PublicPokerState(
        own_equity=0.62,
        pot_odds=0.31,
        position=0.5,
        effective_stack_ratio=0.8,
        pot_pressure=0.4,
        aggression=0.2,
        legal_actions=("fold", "call", "raise"),
        street="flop",
    )
    assert "opponent_hole_cards" not in state.__dataclass_fields__
    pulses = encode_state(state, steps=50)
    assert len(pulses) == 50
    assert set(pulses[-1]) == {"LC10a", "LPLC1", "LPLC2", "LC4"}
    assert vectorize_state(state).shape == (12,)


def test_encoder_bounds_malformed_values():
    state = PublicPokerState(
        own_equity=99,
        pot_odds=-4,
        position=2,
        effective_stack_ratio=-1,
        pot_pressure=8,
        aggression=-3,
        legal_actions=("check",),
        street="river",
    )
    assert all(0 <= value <= 1 for value in encode_state(state)[-1].values())


def test_private_card_signal_is_own_cards_only():
    strong = PublicPokerState(
        own_equity=0.5,
        pot_odds=0.3,
        position=0.2,
        effective_stack_ratio=0.8,
        pot_pressure=0.2,
        aggression=0.2,
        legal_actions=("call", "raise"),
        street="preflop",
        own_hole_cards=("A♠", "A♥"),
    )
    weak = strong.__class__(**{**strong.__dict__, "own_hole_cards": ("2♠", "7♦")})
    assert encode_state(strong)[-1]["LC10a"] > encode_state(weak)[-1]["LC10a"]
    assert "opponent_hole_cards" not in strong.__dataclass_fields__


def test_teacher_corpus_carries_the_same_public_information_boundary():
    states, _, _ = sample_states(32, 20260921)
    assert all(len(state.own_hole_cards) == 2 for state in states)
    assert all(state.street == "preflop" or len(state.public_board) >= 3 for state in states)
    assert any(state.public_action_history for state in states)
