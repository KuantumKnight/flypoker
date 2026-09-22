"""Small spectator WebSocket load probe for the 200-client target."""

from __future__ import annotations

import argparse
import asyncio
import json
import time

try:
    import websockets
except ImportError as exc:  # pragma: no cover - exercised on the host venv
    raise SystemExit("Install uvicorn[standard] before running load-test.py") from exc


async def spectator(url: str, seconds: float) -> dict[str, int]:
    received = 0
    received_bytes = 0
    try:
        async with websockets.connect(url, origin="http://localhost:3000", max_size=2**20, open_timeout=5) as socket:
            first = await asyncio.wait_for(socket.recv(), timeout=5)
            received_bytes += len(first.encode("utf-8") if isinstance(first, str) else first)
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                try:
                    message = await asyncio.wait_for(socket.recv(), timeout=max(0.05, deadline - time.monotonic()))
                    received_bytes += len(message.encode("utf-8") if isinstance(message, str) else message)
                    received += 1
                except asyncio.TimeoutError:
                    break
        return {"connected": 1, "events": received, "bytes": received_bytes, "failed": 0}
    except Exception:
        return {"connected": 0, "events": received, "bytes": received_bytes, "failed": 1}


async def run(url: str, clients: int, seconds: float) -> dict[str, int | float]:
    results = await asyncio.gather(*(spectator(url, seconds) for _ in range(clients)))
    totals = {key: sum(result[key] for result in results) for key in ("connected", "events", "bytes", "failed")}
    totals["bytesPerClientSecond"] = round(totals["bytes"] / max(1, clients) / max(0.1, seconds), 2)
    return totals


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://127.0.0.1:8000/v1/live/ws")
    parser.add_argument("--clients", type=int, default=20)
    parser.add_argument("--seconds", type=float, default=30)
    args = parser.parse_args()
    if not 1 <= args.clients <= 200:
        parser.error("--clients must be between 1 and 200")
    result = asyncio.run(run(args.url, args.clients, args.seconds))
    print(json.dumps(result, indent=2))
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
