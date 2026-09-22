"""Deterministic, non-LLM broadcast copy for the spectator layer."""

from __future__ import annotations

import hashlib


TEMPLATES: dict[tuple[str, str], tuple[str, ...]] = {
    ("all-in", "strong"): ("{name} detonates an all-in with the table cornered.", "{name} turns a strong read into a full-flight shove."),
    ("raise", "strong"): ("{name} lifts the pot; the felt suddenly feels smaller.", "{name} finds pressure in the wiring and raises."),
    ("raise", "quiet"): ("{name} applies a measured squeeze from the shadows.", "{name} nudges the table toward a difficult decision."),
    ("call", "strong"): ("{name} keeps the signal quiet and comes along.", "{name} declines the spectacle and calls."),
    ("call", "quiet"): ("{name} pays for another look at the board.", "{name} follows the odds without giving away the tell."),
    ("fold", "strong"): ("{name} releases the hand before the trap closes.", "{name} folds a playable signal and preserves the stack."),
    ("fold", "quiet"): ("{name} vanishes from the pot without a sound.", "{name} lets the weak signal go."),
}

PERSONALITY_LINES: dict[str, tuple[str, ...]] = {
    "trap-heavy": ("{name} keeps the signal deliberately unreadable.", "{name} lets patience do the talking."),
    "loose-aggressive": ("{name} smells momentum and turns it into pressure.", "{name} makes the table pay attention."),
    "short-stack pressure": ("{name} measures every remaining chip as leverage.",),
    "high-variance": ("{name} lets the variance breathe.",),
}


def announce_action(name: str, style: str, action: str, street: str, equity: float, pot: int) -> str:
    """Select a stable caption from event rarity, strength, and personality."""
    normalized = "all-in" if action == "all-in" else action
    strength = "strong" if equity >= 0.68 else "quiet"
    rarity = "rare" if normalized == "all-in" or pot >= 1500 else "routine"
    personality = PERSONALITY_LINES.get(style, ()) if normalized in {"raise", "all-in", "call"} else ()
    options = personality or TEMPLATES.get((normalized, strength), (f"{{name}} chooses {normalized.replace('-', ' ')}.",))
    # Stable hash avoids random overrides while still varying repeated actions;
    # rarity and personality are explicit inputs to the caption key.
    key = f"{name}|{style}|{normalized}|{street}|{round(equity, 2)}|{pot}|{rarity}"
    index = int.from_bytes(hashlib.blake2s(key.encode("utf-8"), digest_size=2).digest(), "big") % len(options)
    return options[index].format(name=name)


def announce_thinking(name: str, style: str, street: str, equity: float) -> str:
    """Caption the decision pause without implying biological understanding."""
    if equity >= 0.68:
        return f"{name} holds a strong signal on the {street}."
    if style == "trap-heavy":
        return f"{name} stays very still on the {street}."
    return f"{name} reads the {street} before moving a wing."
