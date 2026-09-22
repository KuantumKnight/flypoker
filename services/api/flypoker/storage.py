from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .models import EventEnvelope, TableSnapshot


class EventStore:
    """Small WAL-backed journal for live events and replay reconstruction."""

    def __init__(self, path: str | Path = "data/flypoker.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              tournament_id TEXT NOT NULL,
              hand_id TEXT NOT NULL,
              sequence INTEGER NOT NULL,
              event_type TEXT NOT NULL,
              server_time TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              UNIQUE(tournament_id, sequence)
            );
            CREATE INDEX IF NOT EXISTS idx_events_hand ON events(tournament_id, hand_id, sequence);
            CREATE TABLE IF NOT EXISTS checkpoints (
              tournament_id TEXT PRIMARY KEY,
              hand_id TEXT NOT NULL,
              hand_number INTEGER NOT NULL,
              sequence INTEGER NOT NULL,
              snapshot_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def append(self, event: EventEnvelope) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO events (tournament_id, hand_id, sequence, event_type, server_time, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
            (event.tournament_id, event.hand_id, event.sequence, event.type, event.server_time, json.dumps(event.payload, separators=(",", ":"))),
        )
        self.connection.commit()

    def checkpoint(self, snapshot: TableSnapshot) -> None:
        self.connection.execute(
            "INSERT INTO checkpoints (tournament_id, hand_id, hand_number, sequence, snapshot_json, updated_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(tournament_id) DO UPDATE SET hand_id=excluded.hand_id, hand_number=excluded.hand_number, sequence=excluded.sequence, snapshot_json=excluded.snapshot_json, updated_at=excluded.updated_at",
            (snapshot.tournament_id, snapshot.hand_id, snapshot.hand_number, snapshot.sequence, snapshot.model_dump_json(), snapshot.updated_at),
        )
        self.connection.commit()

    def hand_events(self, tournament_id: str, hand_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT tournament_id, hand_id, sequence, event_type, server_time, payload_json FROM events WHERE tournament_id = ? AND hand_id = ? ORDER BY sequence",
            (tournament_id, hand_id),
        ).fetchall()
        return [
            {
                "schemaVersion": 1,
                "tournamentId": row[0],
                "handId": row[1],
                "sequence": row[2],
                "serverTime": row[4],
                "type": row[3],
                "payload": json.loads(row[5]),
            }
            for row in rows
        ]

    def latest_completed_events(self) -> tuple[str, list[dict[str, Any]]] | None:
        row = self.connection.execute(
            "SELECT tournament_id, hand_id FROM events WHERE event_type = 'hand.completed' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return f"{row[0]}-{row[1]}", self.hand_events(row[0], row[1])

    def latest_checkpoint(self) -> TableSnapshot | None:
        row = self.connection.execute(
            "SELECT snapshot_json FROM checkpoints ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return TableSnapshot.model_validate_json(row[0])
