"""Surf AI API client — enrichment and reasoning layer.

TODO: implement against the Surf API once sponsor credits are provisioned.
"""

import httpx

from alphatide.core.config import settings


class SurfClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.surf_api_key
        self._client = httpx.AsyncClient(timeout=30)

    async def enrich_signal(self, signal: dict) -> dict:
        """Ask Surf to add context, narrative, and risk framing to a raw signal."""
        raise NotImplementedError
