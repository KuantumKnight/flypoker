from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from typing_extensions import TypedDict

from pydantic import BaseModel, ConfigDict, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventPayload(TypedDict, total=False):
    """Known live-event payload fields.

    The protocol stays forward-compatible: producers may add event-specific
    keys, but the fields below document and type every payload currently
    emitted by the engine and GPU worker.
    """

    status: str
    mode: Literal["simulated", "flybrain", "offline"]
    reason: str
    message: str
    tournamentId: str
    handNumber: int
    blinds: str
    deckSeed: int
    players: list[Any]
    playerId: str
    street: str
    board: list[str]
    action: str
    amount: int
    sizing: str
    pot: int
    stacks: list[int]
    logits: dict[str, float]
    features: dict[str, float]
    legalActions: list[str]
    winnerId: str
    winnerIds: list[str]
    payouts: dict[str, int]
    payoffs: list[int]
    replaySlug: str
    slug: str
    seeds: list[int]
    activity: float
    regions: dict[str, float]
    sampledSpikes: list[int]
    sampledNeuronCount: int
    stimulatedPopulations: list[str]


# Pydantic supports TypedDict configuration while preserving a plain dict at
# runtime, which keeps the SQLite/event listener boundary JSON-native.
EventPayload.__pydantic_config__ = ConfigDict(extra="allow")


class FlyProfile(BaseModel):
    id: str
    name: str
    style: str
    accent: str
    chips: int
    seat: int
    alive: bool = True
    hole_cards: list[str] = Field(default_factory=list)
    equity: float = 0.0
    activity: float = 0.0
    vpip: float = 0.0
    pfr: float = 0.0
    aggression: float = 0.0
    tell: str
    status: str = "watching"


class TableSnapshot(BaseModel):
    mode: Literal["simulated", "flybrain"] = "simulated"
    tournament_id: str
    hand_id: str
    deck_seed: int = 0
    hand_number: int
    street: str
    board: list[str] = Field(default_factory=list)
    pot: int = 0
    current_actor: str | None = None
    blind_level: int = 0
    blinds: str = "10 / 20"
    players: list[FlyProfile]
    last_event: str = "The table is warming up."
    sequence: int = 0
    updated_at: str = Field(default_factory=now_iso)


class EventEnvelope(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: int = Field(default=1, alias="schemaVersion")
    tournament_id: str = Field(alias="tournamentId")
    hand_id: str = Field(alias="handId")
    sequence: int
    server_time: str = Field(default_factory=now_iso, alias="serverTime")
    type: str
    payload: EventPayload = Field(default_factory=dict)


class SnapshotMessage(BaseModel):
    """First WebSocket frame: a complete visible state and its sequence."""

    kind: Literal["snapshot"] = "snapshot"
    snapshot: TableSnapshot
    sequence: int


class EventMessage(BaseModel):
    """Ordered WebSocket event frame following the initial snapshot."""

    kind: Literal["event"] = "event"
    event: EventEnvelope


class StatusResponse(BaseModel):
    status: Literal["live", "starting", "offline"]
    mode: Literal["simulated", "flybrain", "offline"]
    gpu: str
    connected_spectators: int
    step_latency_ms: float
    current_hand: int
    brain_runtime: Literal["simulated", "available", "unavailable"] = "simulated"
    runtime_note: str = "development adapter"
    updated_at: str = Field(default_factory=now_iso)


class StatusMessage(BaseModel):
    """WebSocket frame sent when no verified live table is available."""

    kind: Literal["status"] = "status"
    status: StatusResponse
