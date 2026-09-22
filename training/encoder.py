"""Documented poker-to-MaleCNS feature encoder.

This module is deliberately independent from FlyBrain.  It defines the small,
auditable interface between poker state and the four feature-detector groups
described in the project methodology.  A live runner turns each pulse into
the corresponding FlyBrain injection after resolving the dataset's neuron
indices; no opponent private cards are accepted by this API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np


@dataclass(frozen=True)
class PublicPokerState:
    """Information available to one fly at a decision point."""

    own_equity: float
    pot_odds: float
    position: float
    effective_stack_ratio: float
    pot_pressure: float
    aggression: float
    legal_actions: tuple[str, ...]
    street: Literal["preflop", "flop", "turn", "river"]
    own_hole_cards: tuple[str, ...] = ()
    public_board: tuple[str, ...] = ()
    public_action_history: tuple[str, ...] = ()


FEATURE_GROUPS = ("LC10a", "LPLC1", "LPLC2", "LC4")
ENCODER_SCHEMA = "poker-feature-detectors-v2"


def _clip(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


def _card_texture(cards: tuple[str, ...]) -> float:
    """Compress the fly's private cards into a bounded card-strength cue.

    The encoder never accepts opponent cards. Rank texture is intentionally
    coarse because the teacher supplies equity as the primary signal; this
    keeps the readout dimensionality stable while making the private-card
    boundary explicit in the protocol.
    """
    ranks = {str(rank): index for index, rank in enumerate("23456789TJQKA", start=2)}
    values = [ranks.get(card[:1].upper(), 2) for card in cards[:2] if card]
    if not values:
        return 0.0
    average = sum(values) / (len(values) * 14.0)
    pair_bonus = 0.12 if len(values) == 2 and values[0] == values[1] else 0.0
    suited_bonus = 0.05 if len(cards) == 2 and cards[0][-1:] == cards[1][-1:] else 0.0
    return _clip(average * 0.82 + pair_bonus + suited_bonus)


def encode_state(state: PublicPokerState, steps: int = 50) -> list[dict[str, float]]:
    """Create a one-second (20 ms x ``steps``) temporal pulse sequence.

    Left/right amplitude encodes sign.  Magnitudes are bounded so pathological
    API input cannot produce non-finite neural stimulation.  The return value
    is JSON-friendly and can be adapted to the feature-detector indices for a
    specific MaleCNS artifact.
    """

    if steps < 1:
        raise ValueError("steps must be positive")
    equity = _clip(state.own_equity)
    odds = _clip(state.pot_odds)
    pressure = _clip(state.pot_pressure)
    aggression = _clip(state.aggression)
    card_signal = _card_texture(state.own_hole_cards)
    board_signal = _card_texture(tuple(state.public_board[:2]))
    perceived_value = _clip(equity * 0.79 + card_signal * 0.16 + board_signal * 0.05)
    opportunity = perceived_value - odds
    recent_aggression = sum("raise" in action or "all-in" in action for action in state.public_action_history[-8:]) / max(1, len(state.public_action_history[-8:]))
    approach = max(0.0, odds - perceived_value) + pressure * 0.35 + recent_aggression * 0.08
    threat = _clip(pressure * 0.65 + aggression * 0.27 + recent_aggression * 0.08)
    shove = _clip(aggression * 0.7 + max(0.0, 0.35 - state.effective_stack_ratio))
    base = {
        "LC10a": opportunity,
        "LPLC1": approach,
        "LPLC2": threat,
        "LC4": shove,
    }
    # A short eased pulse avoids a single-frame discontinuity while preserving
    # deterministic input for readout training and replay inspection.
    sequence: list[dict[str, float]] = []
    for index in range(steps):
        phase = min(1.0, (index + 1) / 8.0, (steps - index) / 8.0)
        sequence.append({name: round(value * max(0.0, phase), 6) for name, value in base.items()})
    return sequence


def vectorize_state(state: PublicPokerState) -> np.ndarray:
    """Return the compact feature vector used by the offline readout harness."""

    return np.asarray(
        [
            _clip(state.own_equity),
            _clip(state.pot_odds),
            _clip(state.position),
            _clip(state.effective_stack_ratio),
            _clip(state.pot_pressure),
            _clip(state.aggression),
            float(state.street == "flop"),
            float(state.street == "turn"),
            float(state.street == "river"),
            float("raise" in state.legal_actions),
            float("call" in state.legal_actions),
            float("check" in state.legal_actions),
        ],
        dtype=np.float32,
    )
