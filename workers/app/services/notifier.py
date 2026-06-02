from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

from app.settings import Settings

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send(self, text: str, extra: dict[str, Any] | None = None) -> None:
        await self._telegram(text)
        await self._hermes(text, extra or {})

    async def _telegram(self, text: str) -> None:
        if not self.settings.telegram_bot_token or not self.settings.telegram_chat_id:
            logger.info("telegram not configured; message=%s", text)
            return
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                url,
                json={"chat_id": self.settings.telegram_chat_id, "text": text, "disable_web_page_preview": True},
            )
            response.raise_for_status()

    async def _hermes(self, text: str, extra: dict[str, Any]) -> None:
        if not self.settings.hermes_webhook_url:
            return
        payload = {"text": text, "extra": extra}
        headers = {"Content-Type": "application/json"}
        if self.settings.hermes_webhook_secret:
            body = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode()
            signature = hmac.new(
                self.settings.hermes_webhook_secret.encode(), body, hashlib.sha256
            ).hexdigest()
            headers["X-Hermes-Signature"] = signature
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(self.settings.hermes_webhook_url, json=payload, headers=headers)
            response.raise_for_status()
