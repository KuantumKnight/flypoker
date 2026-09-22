from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .engine import LiveEngine
from .brain_adapter import FlyBrainBatchAdapter
from .brain_worker import BrainWorkerConfig, BrainWorkerProcess
from .models import EventEnvelope, EventMessage, SnapshotMessage, StatusMessage, StatusResponse


requested_mode = os.environ.get("FLYPOKER_MODE", "flybrain")
dev_simulator = os.environ.get("FLYPOKER_DEV_SIMULATOR", "0").lower() in {"1", "true", "yes"}
readout_dir = os.environ.get("FLYPOKER_READOUT_DIR", "artifacts/readout-male-cns-gpu")
data_dir = os.environ.get("FLY_DATA", "fly-data")
brain_variant = os.environ.get("FLY_VARIANT", "profiles")
brain_seed = int(os.environ.get("FLY_BRAIN_SEED", "20260921"))
brain_probe = FlyBrainBatchAdapter(readout_dir, data_dir=data_dir, device=os.environ.get("FLY_DEVICE", "cuda"), variant=brain_variant, seed=brain_seed).probe() if requested_mode == "flybrain" else (False, "simulator disabled in production")
brain_worker = BrainWorkerProcess(BrainWorkerConfig(artifact_dir=readout_dir, data_dir=data_dir, device=os.environ.get("FLY_DEVICE", "cuda"), variant=brain_variant, seed=brain_seed)) if brain_probe[0] else None
engine = LiveEngine(brain_worker=brain_worker, restore_checkpoint=True, brain_seed=brain_seed)
live_available = False
allowed_origins = {
    origin.strip()
    for origin in os.environ.get("FLYPOKER_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
}
require_origin = os.environ.get("FLYPOKER_REQUIRE_ORIGIN", "true" if requested_mode == "flybrain" else "false").lower() == "true"
max_spectators = max(1, int(os.environ.get("FLYPOKER_MAX_SPECTATORS", "200")))
# Permit the full 200-spectator capacity to arrive during a launch burst while
# still bounding repeated reconnect storms from one client address.
connection_rate_limit = max(1, int(os.environ.get("FLYPOKER_CONNECTIONS_PER_MINUTE", "240")))
connection_attempts: dict[str, deque[float]] = defaultdict(deque)


def _connection_allowed(client_id: str) -> bool:
    now = time.monotonic()
    if len(connection_attempts) > 4096:
        for key, history in list(connection_attempts.items()):
            if not history or now - history[-1] >= 60.0:
                connection_attempts.pop(key, None)
        # Keep the address ledger bounded even if many unique addresses arrive
        # inside one minute (for example through a reconnect storm).
        if len(connection_attempts) > 4096:
            oldest = sorted(connection_attempts, key=lambda key: connection_attempts[key][-1] if connection_attempts[key] else 0.0)
            for key in oldest[: len(connection_attempts) - 4096]:
                connection_attempts.pop(key, None)
    attempts = connection_attempts[client_id]
    while attempts and now - attempts[0] >= 60.0:
        attempts.popleft()
    if len(attempts) >= connection_rate_limit:
        return False
    attempts.append(now)
    return True


@asynccontextmanager
async def lifespan(_: FastAPI):
    global live_available
    worker_watchdog: asyncio.Task[None] | None = None
    if brain_worker:
        brain_worker.start()
        ready = await asyncio.to_thread(brain_worker.wait_ready, 45.0)
        if ready:
            engine.snapshot.mode = "flybrain"
            live_available = True
        else:
            brain_worker.stop()
            engine.brain_worker = None
        if ready:
            async def supervise_brain_worker() -> None:
                global live_available
                while True:
                    await asyncio.sleep(2.0)
                    if brain_worker.alive:
                        continue
                    engine.brain_worker = None
                    live_available = False
                    await engine.stop()
                    try:
                        engine.brain_worker_restarts += 1
                        brain_worker.start()
                        if await asyncio.to_thread(brain_worker.wait_ready, 20.0):
                            engine.brain_worker = brain_worker
                            engine.snapshot.mode = "flybrain"
                            live_available = True
                            engine.request_brain_reset("GPU worker restarted; restored last completed hand")
                            await engine.start()
                        else:
                            brain_worker.stop()
                    except Exception:
                        brain_worker.stop()
            worker_watchdog = asyncio.create_task(supervise_brain_worker(), name="fly-poker-brain-watchdog")
    elif dev_simulator:
        engine.snapshot.mode = "simulated"
        live_available = True
        await engine.start()
    if live_available and not (engine._task and not engine._task.done()):
        await engine.start()
    yield
    live_available = False
    if worker_watchdog:
        worker_watchdog.cancel()
        await asyncio.gather(worker_watchdog, return_exceptions=True)
    await engine.stop()
    if brain_worker:
        brain_worker.stop()


app = FastAPI(title="Fly Poker Live API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(allowed_origins),
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health/live")
async def health_live() -> dict[str, str]:
    return {"status": "live"}


@app.get("/health/ready")
async def health_ready() -> dict[str, str]:
    active = bool(engine.brain_worker and engine.brain_worker.alive)
    runtime = "available" if active else ("simulated" if dev_simulator else "unavailable")
    if not active and not dev_simulator:
        raise HTTPException(status_code=503, detail={"status": "offline", "mode": "flybrain", "brainRuntime": runtime, "runtimeNote": brain_probe[1]})
    return {"status": "ready", "mode": "flybrain" if active else "simulated", "brainRuntime": runtime, "runtimeNote": brain_probe[1]}


@app.get("/v1/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    active = bool(engine.brain_worker and engine.brain_worker.alive)
    runtime = "available" if active else ("simulated" if dev_simulator else "unavailable")
    return StatusResponse(status="live" if active or dev_simulator else "offline", mode="flybrain" if active else ("simulated" if dev_simulator else "offline"), gpu="RTX 5070 / FlyBrain batch=6" if active else "offline", connected_spectators=engine.connected_spectators, step_latency_ms=round(engine.step_latency_ms or 0.0, 2), current_hand=engine.hand_number if active else 0, brain_runtime=runtime, runtime_note=brain_probe[1])


@app.get("/v1/metrics")
async def metrics() -> dict[str, object]:
    result = engine.metrics_snapshot()
    nvidia = shutil.which("nvidia-smi")
    if nvidia:
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                [nvidia, "--query-gpu=name,temperature.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=1.5,
                check=False,
            )
            line = completed.stdout.strip().splitlines()[0] if completed.stdout.strip() else ""
            fields = [field.strip() for field in line.split(",")]
            if len(fields) == 4:
                result["gpu"] = {"name": fields[0], "temperatureC": float(fields[1]), "memoryUsedMiB": float(fields[2]), "memoryTotalMiB": float(fields[3])}
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
            result["gpu"] = {"status": "unavailable"}
    else:
        result["gpu"] = {"status": "unavailable"}
    return result


@app.get("/v1/live/snapshot")
async def live_snapshot():
    if not live_available:
        raise HTTPException(status_code=503, detail={"status": "offline", "runtimeNote": brain_probe[1]})
    return engine.snapshot.model_dump(mode="json")


@app.get("/v1/replays/{slug}")
async def replay(slug: str):
    if slug == "latest":
        latest = engine.store.latest_completed_events()
        if latest is None:
            raise HTTPException(status_code=404, detail="Replay unavailable")
        latest_slug, events = latest
        return {"slug": latest_slug, "mode": "flybrain", "events": events, "snapshot": engine.snapshot.model_dump(mode="json")}
    events = [event.model_dump(mode="json", by_alias=True) for event in engine.recent_events if slug.endswith(event.hand_id)]
    if not events:
        # Stable replay URLs are `<tournament-id>-hand-####`. Resolve the
        # exact persisted tournament instead of accidentally looking up the
        # current tournament after a champion rollover.
        if "-hand-" in slug:
            tournament_id, hand_suffix = slug.rsplit("-hand-", 1)
            requested_tournament = tournament_id
            requested_hand = f"hand-{hand_suffix}"
        else:
            requested_tournament = engine.tournament_id
            requested_hand = slug if slug.startswith("hand-") else f"hand-{slug.split('-')[-1]}"
        events = engine.store.hand_events(requested_tournament, requested_hand)
    if not events:
        raise HTTPException(status_code=404, detail="Replay unavailable")
    return {"slug": slug, "mode": "flybrain", "events": events, "snapshot": engine.snapshot.model_dump(mode="json")}


@app.websocket("/v1/live/ws")
async def live_websocket(websocket: WebSocket):
    origin = websocket.headers.get("origin")
    if (require_origin and not origin) or (origin and origin not in allowed_origins):
        await websocket.close(code=1008, reason="origin not allowed")
        return
    # Cloudflare Tunnel preserves the viewer address in this header.  Fall
    # back to the socket peer for local development without trusting an
    # arbitrary forwarded-for chain.
    client_id = websocket.headers.get("cf-connecting-ip") or (websocket.client.host if websocket.client else "unknown")
    if not _connection_allowed(client_id):
        await websocket.close(code=1013, reason="connection rate limit")
        return
    if engine.connected_spectators >= max_spectators:
        await websocket.close(code=1013, reason="spectator capacity reached")
        return
    await websocket.accept()
    if not live_available:
        offline_status = await status()
        await websocket.send_json(StatusMessage(status=offline_status).model_dump(mode="json"))
        await websocket.close(code=1001, reason="live table asleep")
        return
    engine.connected_spectators += 1
    queue: asyncio.Queue[EventEnvelope] = asyncio.Queue(maxsize=64)

    async def listener(event: EventEnvelope) -> None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            engine.dropped_telemetry += 1
            await websocket.close(code=1013, reason="spectator queue overflow")

    engine.add_listener(listener)
    try:
        snapshot_message = SnapshotMessage(snapshot=engine.snapshot, sequence=engine.snapshot.sequence)
        await websocket.send_json(snapshot_message.model_dump(mode="json"))
        while True:
            event = await queue.get()
            await websocket.send_json(EventMessage(event=event).model_dump(mode="json", by_alias=True))
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        engine.remove_listener(listener)
        engine.connected_spectators = max(0, engine.connected_spectators - 1)
