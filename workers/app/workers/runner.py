from __future__ import annotations

import logging

from app.settings import Settings
from app.workers.agent import run_agent
from app.workers.collector import run_collector
from app.workers.notifier import run_notifier
from app.workers.paper_broker import run_paper_broker
from app.workers.position_keeper import run_position_keeper
from app.workers.review import run_review
from app.workers.strategy import run_strategy

logger = logging.getLogger(__name__)


async def run_role(role: str, settings: Settings) -> None:
    normalized = role.lower().strip()
    logger.info("starting worker role=%s", normalized)
    if normalized == "collector":
        return await run_collector(settings)
    if normalized == "strategy":
        return await run_strategy(settings)
    if normalized == "agent":
        return await run_agent(settings)
    if normalized == "paper-broker":
        return await run_paper_broker(settings)
    if normalized == "review":
        return await run_review(settings)
    if normalized == "notifier":
        return await run_notifier(settings)
    if normalized == "position-keeper":
        return await run_position_keeper(settings)
    raise ValueError(f"unknown WORKER_ROLE={role}")
