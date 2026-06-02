from __future__ import annotations

from typing import Any

import httpx


class ControlApi:
    def __init__(self, base_url: str, token: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _headers(self) -> dict[str, str]:
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    async def create_decision(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20, headers=self._headers()) as client:
            response = await client.post(f"{self.base_url}/api/v1/decisions", json=payload)
            response.raise_for_status()
            return response.json()["data"]

    async def request_approval(self, decision_id: str, channel: str, recipient: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20, headers=self._headers()) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/approvals/request",
                json={"decisionId": decision_id, "channel": channel, "recipient": recipient},
            )
            response.raise_for_status()
            return response.json()["data"]

    async def place_paper_order(self, decision_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20, headers=self._headers()) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/orders/paper",
                json={"decisionId": decision_id},
            )
            response.raise_for_status()
            return response.json()["data"]

    async def health(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()["data"]
