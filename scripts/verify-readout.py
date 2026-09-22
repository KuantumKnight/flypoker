"""Validate a trained readout manifest against the launch acceptance gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("artifacts/readout-male-cns-gpu/manifest.json"))
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    metrics = manifest.get("metrics", {})
    variants = manifest.get("variants", {})
    if metrics.get("action_macro_f1", 0.0) < 0.65 or metrics.get("legal_action_rate", 0.0) < 1.0:
        raise SystemExit("readout acceptance gate failed")
    if any(float(item.get("action_macro_f1", 0.0)) < 0.65 for item in variants.values()):
        raise SystemExit("profile action macro-F1 gate failed")
    for key in ("vpip", "pfr", "aggression"):
        values = [float(item[key]) for item in variants.values()]
        if not values or max(values) - min(values) < 0.10:
            raise SystemExit(f"profile separation gate failed: {key}")
    print(json.dumps({"manifest": str(args.manifest), "encoderSchema": manifest.get("encoder_schema"), "metrics": metrics, "profiles": sorted(variants)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
