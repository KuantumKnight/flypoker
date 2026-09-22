"""Smoke-test the Windows spawn boundary with the real MaleCNS artifacts."""

from __future__ import annotations

import asyncio
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))
sys.path.insert(0, str(ROOT))

from flypoker.brain_worker import BrainWorkerConfig, BrainWorkerProcess  # noqa: E402
from training.encoder import PublicPokerState, encode_state  # noqa: E402


async def main() -> int:
    worker = BrainWorkerProcess(BrainWorkerConfig(artifact_dir="artifacts/readout-male-cns-gpu", data_dir="fly-data", device="cuda", variant="profiles"))
    worker.start()
    try:
        if not await asyncio.to_thread(worker.wait_ready, 45.0):
            print({"status": "unavailable"})
            return 1
        state = PublicPokerState(0.55, 0.25, 0.5, 0.8, 0.4, 0.4, ("fold", "call", "raise"), "flop")
        features = [encode_state(state, steps=50) for _ in range(6)]
        assert worker.submit_features("smoke-1", features)
        for _ in range(1000):
            response = worker.poll()
            if response and response.get("requestId") == "smoke-1":
                result = response.get("result", {})
                actions = [str(action).replace("check-call", "call") for action in result.get("action", [])]
                logits = result.get("actionLogits") or []
                sampled_spikes = result.get("sampledSpikes") or []
                lane_seeds = result.get("laneSeeds") or []
                legal = {"fold", "call", "raise"}
                finite = all(math.isfinite(float(value)) for row in logits for value in row)
                telemetry_ok = len(sampled_spikes) == 6 and int(result.get("sampledNeuronCount", 0)) == 12000
                independent_lanes = len(lane_seeds) == 6 and len(set(lane_seeds)) == 6
                independent_noise = len({tuple(spikes) for spikes in sampled_spikes}) > 1
                print({"status": "ready", "actions": actions, "finiteLogits": finite, "telemetrySample": telemetry_ok, "independentLaneSeeds": independent_lanes, "independentNoiseSample": independent_noise, "error": response.get("error")})
                return 0 if len(actions) == 6 and all(action in legal for action in actions) and finite and telemetry_ok and independent_lanes and independent_noise else 1
            await asyncio.sleep(0.005)
        print({"status": "timeout"})
        return 1
    finally:
        worker.stop()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
