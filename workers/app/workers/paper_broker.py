from __future__ import annotations

import asyncio
import logging

from app.db.repository import Repository
from app.services.control_api import ControlApi
from app.services.notifier import Notifier
from app.settings import Settings

logger = logging.getLogger(__name__)


async def run_paper_broker(settings: Settings) -> None:
    repo = await Repository.connect(settings.database_url)
    control = ControlApi(settings.control_api_url, settings.api_auth_token)
    notifier = Notifier(settings)
    try:
        while True:
            try:
                decisions = await repo.approved_decisions_without_order(limit=10)
            except Exception:
                logger.exception("paper-broker failed to query approved decisions")
                await asyncio.sleep(20)
                continue
            for decision in decisions:
                try:
                    result = await control.place_paper_order(str(decision["id"]))
                    status = result.get("status", "PAPER_FILLED")
                    if status == "ALREADY_FILLED":
                        logger.info("paper order already exists decision=%s", decision["id"])
                        continue
                    try:
                        await notifier.send(
                            "[AI-Quant] 模拟盘已入场\n"
                            f"Decision: {decision['id']}\n"
                            f"Order: {result.get('orderId')}\n"
                            f"Position: {result.get('positionId')}\n"
                            f"Status: {status}",
                            {"decision_id": str(decision["id"]), "order": result},
                        )
                    except Exception:
                        logger.exception("notify after fill failed decision=%s", decision["id"])
                except Exception:
                    logger.exception("failed to place paper order decision=%s", decision["id"])
            await asyncio.sleep(20)
    except asyncio.CancelledError:
        logger.info("paper-broker cancelled")
        raise
    finally:
        await repo.close()
