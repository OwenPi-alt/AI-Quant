from __future__ import annotations

import asyncio
import logging

import httpx

from app.services.notifier import Notifier
from app.settings import Settings

logger = logging.getLogger(__name__)


async def run_notifier(settings: Settings) -> None:
    notifier = Notifier(settings)
    try:
        await notifier.send("[AI-Quant] LA notifier online")
    except Exception:
        logger.exception("initial heartbeat failed")
    try:
        while True:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    response = await client.get(f"{settings.control_api_url.rstrip('/')}/health")
                    response.raise_for_status()
                    logger.info("control api health=%s", response.json())
            except Exception:
                logger.exception("control api health check failed")
                try:
                    await notifier.send("[AI-Quant] control-api health check failed")
                except Exception:
                    logger.exception("failed to alert health check failure")
            await asyncio.sleep(300)
    except asyncio.CancelledError:
        logger.info("notifier cancelled")
        raise
