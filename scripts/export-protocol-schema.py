"""Export the Pydantic protocol models consumed by the frontend and Workers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import TypeAdapter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from flypoker.models import EventEnvelope, EventMessage, EventPayload, FlyProfile, SnapshotMessage, StatusResponse, TableSnapshot  # noqa: E402


def main() -> int:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Fly Poker live protocol",
        "schemaVersion": 1,
        "$defs": {
            "FlyProfile": FlyProfile.model_json_schema(),
            "TableSnapshot": TableSnapshot.model_json_schema(),
            "EventEnvelope": EventEnvelope.model_json_schema(),
            "EventPayload": TypeAdapter(EventPayload).json_schema(),
            "SnapshotMessage": SnapshotMessage.model_json_schema(),
            "EventMessage": EventMessage.model_json_schema(),
            "StatusResponse": StatusResponse.model_json_schema(),
        },
    }
    output = ROOT / "schemas" / "live-protocol.schema.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
