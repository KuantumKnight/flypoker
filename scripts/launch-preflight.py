"""Fail-closed launch preflight for the live Fly Poker host.

The preflight is intentionally read-only.  It never starts services, uploads
data, or prints tokens.  Use the default mode while developing and
``--production`` immediately before installing the supervised Windows
services.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def connectome_hash(data_dir: Path) -> str:
    digest = hashlib.sha256()
    for filename in ("brain.npz", "weights.npz"):
        with (data_dir / filename).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    return digest.hexdigest()


def command_available(command: str) -> bool:
    return shutil.which(command) is not None


def production_checks(data_dir: Path, readout_dir: Path) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    checks.append(check("python312", shutil.which("py") is not None, "Python launcher is available"))
    checks.append(check("nvidia-smi", command_available("nvidia-smi"), "NVIDIA driver telemetry command"))
    checks.append(check("cloudflared", command_available("cloudflared"), "Outbound tunnel binary"))
    checks.append(check("nssm", command_available("nssm"), "Windows service supervisor"))

    allowed_origins = os.environ.get("FLYPOKER_ALLOWED_ORIGINS", "")
    checks.append(check(
        "allowed-origins",
        bool(allowed_origins) and "example.com" not in allowed_origins and "localhost" not in allowed_origins,
        "FLYPOKER_ALLOWED_ORIGINS contains the production origin",
    ))
    tunnel_config = Path(os.environ.get("CLOUDFLARED_CONFIG", ROOT / "infra" / "cloudflared" / "config.yml"))
    tunnel_text = tunnel_config.read_text(encoding="utf-8") if tunnel_config.exists() else ""
    checks.append(check(
        "cloudflare-tunnel-config",
        bool(tunnel_text) and "YOUR_USER" not in tunnel_text and "live.example.com" not in tunnel_text,
        f"Configured tunnel file: {tunnel_config}",
    ))

    replay_worker = ROOT / "infra" / "cloudflare" / "wrangler.toml"
    replay_text = replay_worker.read_text(encoding="utf-8") if replay_worker.exists() else ""
    checks.append(check(
        "replay-worker-origin",
        bool(replay_text) and "live.example.com" not in replay_text,
        "Replay Worker PUBLIC_ORIGIN is not the placeholder",
    ))
    checks.append(check("connectome-hash", (data_dir / "brain.npz").exists() and (data_dir / "weights.npz").exists(), f"MaleCNS data directory: {data_dir}"))
    manifest = readout_dir / "manifest.json"
    manifest_ok = False
    manifest_detail = f"Readout manifest: {manifest}"
    if manifest.exists():
        try:
            raw = json.loads(manifest.read_text(encoding="utf-8"))
            metrics = raw.get("metrics", {})
            expected = raw.get("connectome_sha256", "")
            actual = connectome_hash(data_dir)
            manifest_ok = (
                raw.get("encoder_schema") == "poker-feature-detectors-v2"
                and float(metrics.get("action_macro_f1", 0.0)) >= 0.65
                and float(metrics.get("legal_action_rate", 0.0)) >= 1.0
                and expected == actual
                and all(float(value.get("action_macro_f1", 0.0)) >= 0.65 for value in raw.get("variants", {}).values())
            )
            manifest_detail = f"{manifest} / connectome {actual[:12]}…"
        except (OSError, ValueError, KeyError):
            manifest_detail = f"Unreadable readout manifest: {manifest}"
    checks.append(check("readout-gates", manifest_ok, manifest_detail))
    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production", action="store_true", help="require production host, tunnel, and service prerequisites")
    parser.add_argument("--data", type=Path, default=Path(os.environ.get("FLY_DATA", ROOT / "fly-data")))
    parser.add_argument("--readout", type=Path, default=Path(os.environ.get("FLYPOKER_READOUT_DIR", ROOT / "artifacts" / "readout-male-cns-gpu")))
    args = parser.parse_args()

    data_dir = args.data if args.data.is_absolute() else ROOT / args.data
    readout_dir = args.readout if args.readout.is_absolute() else ROOT / args.readout
    checks = [
        check("data-directory", (data_dir / "brain.npz").exists() and (data_dir / "weights.npz").exists(), f"MaleCNS data directory: {data_dir}"),
        check("readout-directory", (readout_dir / "manifest.json").exists(), f"Readout directory: {readout_dir}"),
        check(
            "webgl-assets",
            all((ROOT / "public" / "models" / filename).exists() for filename in ("spyfly.glb", "table.obj", "table.mtl", "card.obj", "card.mtl", "chip_25.obj", "chip_25.mtl")),
            "Bundled fly, table, card, and chip runtime models",
        ),
    ]
    if args.production:
        checks.extend(production_checks(data_dir, readout_dir))
    result = {"mode": "production" if args.production else "development", "checks": checks, "ready": all(item["ok"] for item in checks)}
    print(json.dumps(result, indent=2))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
