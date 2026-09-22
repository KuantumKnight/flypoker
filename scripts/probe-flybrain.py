from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


def connectome_hash(directory: Path) -> str:
    digest = hashlib.sha256()
    for name in ("brain.npz", "weights.npz"):
        with (directory / name).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe the optional FlyBrain runtime without starting the web service.")
    parser.add_argument("--artifact-dir", default=os.environ.get("FLY_DATA", "fly-data"))
    parser.add_argument("--device", default=os.environ.get("FLY_DEVICE", "cpu"), choices=["cpu", "cuda", "auto"])
    parser.add_argument("--steps", type=int, default=0, help="run this many 20 ms steps after loading")
    args = parser.parse_args()

    result: dict[str, object] = {"artifact_dir": str(Path(args.artifact_dir).resolve()), "device": args.device}
    try:
        import flybrain

        result["flybrain"] = flybrain.__version__
        result["data_present"] = bool(flybrain.has_data(args.artifact_dir))
        result["cuda_available"] = bool(flybrain.cuda_available())
        if result["data_present"]:
            before_hash = connectome_hash(Path(args.artifact_dir))
            brain = flybrain.FlyBrain(data=args.artifact_dir, device=args.device, batch=6, dt=0.020)
            result["neurons"] = brain.n
            result["batch"] = brain.batch
            result["descending_neurons"] = len(brain.cells(["descending_neuron"]))
            if result["neurons"] != 166700 or result["batch"] != 6 or result["descending_neurons"] != 1314:
                raise RuntimeError("MaleCNS batch/neuron trace contract failed")
            result["status"] = "ready"
            if args.steps:
                import time
                import numpy as np

                started = time.perf_counter()
                for _ in range(args.steps):
                    brain.step()
                elapsed_ms = (time.perf_counter() - started) * 1000
                left = brain.v[:, 0].get() if brain.device == "cuda" else brain.v[:, 0]
                right = brain.v[:, 1].get() if brain.device == "cuda" else brain.v[:, 1]
                result.update({"steps": args.steps, "elapsed_ms": round(elapsed_ms, 2), "mean_step_ms": round(elapsed_ms / args.steps, 3), "independent_states": bool(np.max(np.abs(left - right)) > 0)})
            result["connectome_hash_unchanged"] = before_hash == connectome_hash(Path(args.artifact_dir))
        else:
            result["status"] = "missing-data"
            result["message"] = "Run `flybrain download` or provide a built MaleCNS data directory."
    except Exception as exc:
        result["status"] = "unavailable"
        result["error"] = f"{type(exc).__name__}: {exc}"

    print(json.dumps(result, indent=2))
    return 0 if result["status"] in {"ready", "missing-data"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
