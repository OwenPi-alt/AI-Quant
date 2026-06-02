from __future__ import annotations

import httpx


class BinanceClient:
    def __init__(self, spot_base_url: str, futures_base_url: str) -> None:
        self.spot_base_url = spot_base_url.rstrip("/")
        self.futures_base_url = futures_base_url.rstrip("/")

    async def ticker_24h(self, symbol: str) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{self.spot_base_url}/api/v3/ticker/24hr", params={"symbol": symbol})
            response.raise_for_status()
            return response.json()

    async def premium_index(self, symbol: str) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{self.futures_base_url}/fapi/v1/premiumIndex", params={"symbol": symbol})
            response.raise_for_status()
            return response.json()

    async def open_interest(self, symbol: str) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{self.futures_base_url}/fapi/v1/openInterest", params={"symbol": symbol})
            response.raise_for_status()
            return response.json()
