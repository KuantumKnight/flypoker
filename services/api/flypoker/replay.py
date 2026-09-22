"""Pure event-log reducer used by replay verification and future clients."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def reconstruct(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Rebuild the visible hand state without invoking PokerKit or FlyBrain."""
    state: dict[str, Any] = {"players": {}, "board": [], "pot": 0, "street": "intermission", "winnerId": None, "winnerIds": [], "payouts": {}}
    for event in events:
        event_type = event.get("type")
        payload = event.get("payload", {})
        if event_type == "cards.dealt":
            for item in payload.get("players", []):
                state["players"][str(item["id"])] = {
                    "id": str(item["id"]),
                    "cards": list(item.get("cards", [])),
                    "equity": float(item.get("equity", 0.0)),
                    "chips": int(item.get("chips", 0)),
                    "alive": bool(item.get("alive", False)),
                    "status": item.get("status", "watching"),
                }
            state["street"] = "preflop"
        elif event_type == "street.revealed":
            state["street"] = payload.get("street", state["street"])
            state["board"] = list(payload.get("board", state["board"]))
        elif event_type == "action.committed":
            state["street"] = payload.get("street", state["street"])
            state["board"] = list(payload.get("board", state["board"]))
            state["pot"] = int(payload.get("pot", state["pot"]))
            for item in payload.get("players", []):
                state["players"][str(item["id"])] = {
                    **state["players"].get(str(item["id"]), {}),
                    **deepcopy(item),
                }
        elif event_type == "showdown.resolved":
            state["street"] = "showdown"
            state["board"] = list(payload.get("board", state["board"]))
            state["pot"] = int(payload.get("pot", state["pot"]))
            state["winnerId"] = payload.get("winnerId")
            state["winnerIds"] = list(payload.get("winnerIds", [payload.get("winnerId")] if payload.get("winnerId") else []))
            state["payouts"] = deepcopy(payload.get("payouts", {}))
            for item in payload.get("players", []):
                state["players"][str(item["id"])] = {
                    **state["players"].get(str(item["id"]), {}),
                    **deepcopy(item),
                }
    return state
