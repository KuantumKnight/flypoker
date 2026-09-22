"""Start the FastAPI lifespan once and assert the real GPU mode is exposed."""

from __future__ import annotations

import sys
from pathlib import Path
import asyncio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from flypoker.main import app  # noqa: E402
from flypoker.main import health_ready, status  # noqa: E402


async def run() -> int:
    async with app.router.lifespan_context(app):
        ready = await health_ready()
        live_status = await status()
        status_payload = live_status.model_dump(mode="json")
        print({"ready": ready, "status": status_payload})
        return 0 if ready.get("brainRuntime") == "available" and status_payload.get("mode") == "flybrain" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
