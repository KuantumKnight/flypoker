from __future__ import annotations

import asyncio
import json
import os
from urllib.request import Request, urlopen


class ReplayUploader:
    """Optional authenticated bridge to the Cloudflare R2 ingest Worker.

    It is disabled unless both environment variables are present. Upload
    failures are returned to the caller and never interrupt live poker.
    """

    def __init__(self, endpoint: str | None = None, token: str | None = None) -> None:
        self.endpoint = endpoint or os.environ.get("FLYPOKER_REPLAY_UPLOAD_URL", "")
        self.token = token or os.environ.get("FLYPOKER_REPLAY_UPLOAD_TOKEN", "")

    @property
    def enabled(self) -> bool:
        return bool(self.endpoint and self.token)

    async def upload(self, slug: str, replay: dict, poster_svg: str | None = None) -> bool:
        if not self.enabled:
            return False
        body = json.dumps({"slug": slug, "replay": replay, "posterSvg": poster_svg}, separators=(",", ":")).encode("utf-8")

        def send() -> bool:
            request = Request(self.endpoint, data=body, method="POST", headers={"content-type": "application/json", "authorization": f"Bearer {self.token}"})
            try:
                with urlopen(request, timeout=8) as response:
                    return 200 <= response.status < 300
            except OSError:
                return False

        return await asyncio.to_thread(send)
