from __future__ import annotations

import json
from typing import Any

import httpx


class PolymarketClient:
    def __init__(self, gamma_url: str, clob_url: str, geoblock_url: str) -> None:
        self.gamma_url = gamma_url.rstrip("/")
        self.clob_url = clob_url.rstrip("/")
        self.geoblock_url = geoblock_url

    async def geoblock(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(self.geoblock_url)
            response.raise_for_status()
            return response.json()

    async def markets(self, limit: int = 25) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{self.gamma_url}/markets",
                params={"active": "true", "closed": "false", "limit": limit, "order": "volume24hr"},
            )
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, list):
                return payload
            if isinstance(payload, dict):
                return payload.get("data", [])
            return []

    async def order_book(self, token_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{self.clob_url}/book", params={"token_id": token_id})
            response.raise_for_status()
            return response.json()

    @staticmethod
    def token_ids(market: dict[str, Any]) -> list[str]:
        raw = market.get("clobTokenIds") or market.get("clob_token_ids") or market.get("tokenIds")
        if isinstance(raw, list):
            return [str(item) for item in raw]
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
            except json.JSONDecodeError:
                return []
        return []
