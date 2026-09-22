"""Verify a persisted hand can be reconstructed from its append-only events."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from flypoker.storage import EventStore  # noqa: E402
from flypoker.replay import reconstruct  # noqa: E402


LEGAL_ACTIONS = {"fold", "check", "call", "raise", "all-in"}


def verify(events: list[dict]) -> dict[str, object]:
    if not events:
        raise ValueError("replay contains no events")
    sequences = [int(event["sequence"]) for event in events]
    if sequences != sorted(set(sequences)):
        raise ValueError("event sequence is not strictly monotonic")
    types = [str(event["type"]) for event in events]
    if "hand.started" not in types or "cards.dealt" not in types or "hand.completed" not in types:
        raise ValueError("replay is missing hand lifecycle events")
    action_count = 0
    for index, event in enumerate(events):
        if event["type"] != "action.committed":
            # Board and deal events are also visible-state checkpoints.
            if event["type"] == "cards.dealt":
                state = reconstruct(events[: index + 1])
                if len(state["players"]) != len(event.get("payload", {}).get("players", [])):
                    raise ValueError("deal event does not reconstruct all visible players")
            elif event["type"] == "street.revealed":
                state = reconstruct(events[: index + 1])
                if state["board"] != list(event.get("payload", {}).get("board", [])):
                    raise ValueError("reconstructed board diverges from street reveal")
            continue
        action = str(event.get("payload", {}).get("action", ""))
        if action not in LEGAL_ACTIONS:
            raise ValueError(f"illegal action in replay: {action}")
        stacks = event.get("payload", {}).get("stacks", [])
        if len(stacks) != 6 or any(int(stack) < 0 for stack in stacks):
            raise ValueError("action event does not contain six non-negative public stacks")
        state = reconstruct(events[: index + 1])
        if state["pot"] != int(event.get("payload", {}).get("pot", state["pot"])):
            raise ValueError("reconstructed pot diverges from action event")
        visible_players = event.get("payload", {}).get("players", [])
        for item in visible_players:
            reconstructed = state["players"].get(str(item.get("id")))
            if reconstructed is None or int(reconstructed.get("chips", -1)) != int(item.get("chips", -2)):
                raise ValueError("reconstructed stack diverges from action event")
        action_count += 1
    state = reconstruct(events)
    if len(state["players"]) != 6:
        raise ValueError("reconstructed state does not contain six players")
    return {"events": len(events), "actions": action_count, "firstSequence": sequences[0], "lastSequence": sequences[-1], "reconstructedStreet": state["street"], "reconstructible": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=Path("data/flypoker.db"))
    parser.add_argument("--tournament")
    parser.add_argument("--hand")
    args = parser.parse_args()
    store = EventStore(args.database)
    if args.tournament and args.hand:
        slug, events = f"{args.tournament}-{args.hand}", store.hand_events(args.tournament, args.hand)
    else:
        latest = store.latest_completed_events()
        if latest is None:
            raise SystemExit("no completed replay found")
        slug, events = latest
    report = {"slug": slug, **verify(events)}
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
