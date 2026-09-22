"""Deterministic engine soak harness.

Use a short run in CI and a 12-hour run on the plugged-in GPU host. The
authoritative GPU worker is exercised separately by ``verify-brain-worker``;
this harness focuses on poker-state determinism, event growth, and replay
checkpoint stability without opening a public port.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import tracemalloc
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from flypoker.engine import EngineConfig, LiveEngine  # noqa: E402
from flypoker.storage import EventStore  # noqa: E402
from flypoker.brain_worker import BrainWorkerConfig, BrainWorkerProcess  # noqa: E402


async def run(hours: float, max_hands: int, database: Path, brain_worker: BrainWorkerProcess | None = None) -> dict[str, object]:
    duration = max(0.1, hours * 3600.0)
    store = EventStore(database)
    engine = LiveEngine(config=EngineConfig(decision_seconds=0, intermission_seconds=0, replay_limit=200), store=store, brain_worker=brain_worker)
    started = time.monotonic()
    tracemalloc.start()
    first_current, _ = tracemalloc.get_traced_memory()
    hands = 0
    while hands < max_hands and time.monotonic() - started < duration:
        await engine._play_hand()
        hands += 1
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "hands": hands,
        "elapsedSeconds": round(time.monotonic() - started, 3),
        "events": engine.sequence,
        "checkpoint": store.latest_checkpoint() is not None,
        "tracemallocStartBytes": first_current,
        "tracemallocCurrentBytes": current,
        "tracemallocPeakBytes": peak,
        "memoryGrowthBytes": current - first_current,
        "mode": "flybrain" if brain_worker else "simulated",
        "stepLatencyMs": round(engine.step_latency_ms, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=0.01, help="maximum runtime; use 12 on the launch host")
    parser.add_argument("--hands", type=int, default=100, help="maximum completed hands")
    parser.add_argument("--database", type=Path, default=Path("data/soak-test.db"))
    parser.add_argument("--gpu", action="store_true", help="exercise the real six-lane FlyBrain worker")
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--data", type=Path, default=Path("fly-data"))
    parser.add_argument("--readout", type=Path, default=Path("artifacts/readout-male-cns-gpu"))
    args = parser.parse_args()
    args.database.parent.mkdir(parents=True, exist_ok=True)
    worker = None
    if args.gpu:
        worker = BrainWorkerProcess(BrainWorkerConfig(artifact_dir=str(args.readout), data_dir=str(args.data), device=args.device, variant="profiles"))
        worker.start()
        if not worker.wait_ready(45.0):
            worker.stop()
            parser.error("real FlyBrain worker did not become ready")
    try:
        print(json.dumps(asyncio.run(run(args.hours, args.hands, args.database, worker)), indent=2))
    finally:
        if worker:
            worker.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
