from __future__ import annotations

import httpx


class HyperliquidClient:
    def __init__(self, info_url: str) -> None:
        self.info_url = info_url

    async def all_mids(self) -> dict[str, str]:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(self.info_url, json={"type": "allMids"})
            response.raise_for_status()
            return response.json()

    async def meta_and_asset_ctxs(self) -> tuple[list[dict], list[dict]]:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(self.info_url, json={"type": "metaAndAssetCtxs"})
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, list) and len(payload) == 2:
                universe = payload[0].get("universe", [])
                return universe, payload[1]
            return [], []
