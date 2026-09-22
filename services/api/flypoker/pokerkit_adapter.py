from __future__ import annotations

"""Authoritative Hold'em table boundary.

The development engine uses a visual simulator so the scene can be built
without waiting on the full training corpus. This adapter is the seam used by
the production engine to delegate all betting legality and payout mechanics to
PokerKit.
"""

import random
from dataclasses import dataclass

from pokerkit import Automation, NoLimitTexasHoldem, State


AUTOMATIONS = (
    Automation.ANTE_POSTING,
    Automation.BET_COLLECTION,
    Automation.BLIND_OR_STRADDLE_POSTING,
    Automation.CARD_BURNING,
    Automation.HOLE_DEALING,
    Automation.BOARD_DEALING,
    Automation.HOLE_CARDS_SHOWING_OR_MUCKING,
    Automation.HAND_KILLING,
    Automation.CHIPS_PUSHING,
    Automation.CHIPS_PULLING,
)


@dataclass
class PokerKitTable:
    starting_stack: int | list[int] = 2000
    small_blind: int = 10
    big_blind: int = 20
    deck_seed: int | None = None
    blind_layout: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        # PokerKit shuffles from Python's module-level RNG.  Isolate and seed
        # that shuffle so the persisted hand seed is sufficient to recreate
        # the exact deal without perturbing the engine's other RNG streams.
        rng_state = random.getstate()
        try:
            if self.deck_seed is not None:
                random.seed(self.deck_seed)
            raw_blinds = self.blind_layout or (self.small_blind, self.big_blind)
            self.state = NoLimitTexasHoldem.create_state(
                AUTOMATIONS,
                False,
                0,
                raw_blinds,
                self.big_blind,
                self.starting_stack,
                6,
            )
        finally:
            random.setstate(rng_state)

    @property
    def actor_index(self) -> int | None:
        return self.state.actor_index

    @property
    def board(self) -> list[str]:
        cards = []
        for board in self.state.board_cards:
            cards.extend(board if isinstance(board, (list, tuple)) else [board])
        return [card_label(card) for card in cards]

    @property
    def hole_cards(self) -> list[list[str]]:
        return [[card_label(card) for card in cards] for cards in self.state.hole_cards]

    @property
    def stacks(self) -> list[int]:
        return list(self.state.stacks)

    def legal_actions(self) -> list[str]:
        actions: list[str] = []
        if self.state.can_fold():
            actions.append("fold")
        if self.state.can_check_or_call():
            actions.append("check" if self.state.checking_or_calling_amount == 0 else "call")
        if self.state.can_complete_bet_or_raise_to():
            actions.append("raise")
        return actions

    def apply(self, action: str, amount: int | None = None) -> None:
        if action == "fold":
            self.state.fold()
        elif action in {"check", "call"}:
            self.state.check_or_call()
        elif action in {"raise", "all-in"}:
            target = amount or self.state.pot_completion_betting_or_raising_to_amount
            self.state.complete_bet_or_raise_to(target)
        else:
            raise ValueError(f"unsupported action: {action}")


def card_label(card) -> str:
    """Convert PokerKit cards into the compact labels used by the web client."""
    suits = {"s": "♠", "h": "♥", "d": "♦", "c": "♣"}
    return f"{card.rank.value}{suits.get(str(card.suit.value).lower(), str(card.suit.value))}"
