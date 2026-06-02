from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.db.repository import Repository
from app.services.embedding import (
    DEFAULT_EMBEDDING_DIM,
    DeterministicEmbedder,
    EmbeddingProvider,
    make_embedder,
)
from app.services.notifier import Notifier
from app.settings import Settings

logger = logging.getLogger(__name__)

# Re-exported so existing tests can `from app.workers.review import EMBEDDING_DIM`.
EMBEDDING_DIM = DEFAULT_EMBEDDING_DIM


async def run_review(settings: Settings) -> None:
    repo = await Repository.connect(settings.database_url)
    notifier = Notifier(settings)
    embedder = make_embedder(settings)
    try:
        while True:
            try:
                tasks = await repo.due_review_tasks(limit=20)
            except Exception:
                logger.exception("review failed to query due tasks")
                await asyncio.sleep(300)
                continue
            for task in tasks:
                try:
                    await review_task(repo, notifier, embedder, task)
                except Exception:
                    logger.exception("review failed task=%s", task["id"])
                    await repo.mark_review_task(task["id"], "FAILED")
            await asyncio.sleep(300)
    except asyncio.CancelledError:
        logger.info("review cancelled")
        raise
    finally:
        await repo.close()


async def review_task(repo: Repository, notifier: Notifier, embedder: EmbeddingProvider, task: Any) -> None:
    agent_json = _json_value(task["agent_json"], {})
    direction = str(agent_json.get("direction", "LONG")).upper()
    entry = _entry_price(agent_json)
    stop = _float(agent_json.get("stop_loss"))
    tps = [_float(item) for item in _json_value(agent_json.get("take_profit"), [])]
    prices = [float(row["price"]) for row in await repo.market_window(task["symbol"], task["decision_created_at"])]
    if not prices or entry is None or entry <= 0:
        await repo.mark_review_task(task["id"], "SKIPPED")
        return
    if direction in {"LONG", "BUY"}:
        max_favorable = (max(prices) - entry) / entry
        max_adverse = (min(prices) - entry) / entry
        hit_tp = any(tp is not None and max(prices) >= tp for tp in tps)
        hit_sl = stop is not None and min(prices) <= stop
    else:
        max_favorable = (entry - min(prices)) / entry
        max_adverse = (entry - max(prices)) / entry
        hit_tp = any(tp is not None and min(prices) <= tp for tp in tps)
        hit_sl = stop is not None and max(prices) >= stop
    agent_correct = bool(hit_tp or (max_favorable > abs(max_adverse) and max_favorable > 0.005))
    error_tags = [] if agent_correct else ["review_unfavorable", "needs_manual_analysis"]
    summary = (
        f"{task['window_name']} review for {task['symbol']}: "
        f"MFE={max_favorable:.4f}, MAE={max_adverse:.4f}, hit_tp={hit_tp}, hit_sl={hit_sl}."
    )
    rule = "" if agent_correct else "if similar setup has weak follow-through, reduce size or skip"
    payload = {
        "prices_checked": len(prices),
        "entry": entry,
        "stop_loss": stop,
        "take_profit": tps,
        "direction": direction,
    }
    embedding_text = (
        f"{task['market']}|{task['symbol']}|{direction}|"
        f"{round(entry, 4)}|{round(stop or 0, 4)}|"
        f"{','.join(f'{tp:.4f}' for tp in tps if tp is not None)}|"
        f"{summary}"
    )
    embedding = await embedder.embed(embedding_text)
    await repo.insert_review_bundle(
        task=task,
        max_favorable=max_favorable,
        max_adverse=max_adverse,
        hit_tp=hit_tp,
        hit_sl=hit_sl,
        agent_correct=agent_correct,
        error_tags=error_tags,
        experience_summary=summary,
        rule_candidate=rule,
        payload=payload,
        embedding=embedding,
    )
    try:
        await notifier.send(
            "[AI-Quant] 自动复盘完成\n"
            f"Decision: {task['decision_id']}\n"
            f"窗口: {task['window_name']}\n"
            f"MFE: {max_favorable:.4f}, MAE: {max_adverse:.4f}\n"
            f"TP: {hit_tp}, SL: {hit_sl}\n"
            f"结论: {summary}",
            payload,
        )
    except Exception:
        logger.exception("review notify failed decision=%s", task["decision_id"])


def _entry_price(agent_json: dict[str, Any]) -> float | None:
    entry = _json_value(agent_json.get("entry"), {})
    return _float(entry.get("max") or entry.get("price") or entry.get("min"))


def _json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _deterministic_embedding(text: str) -> list[float]:
    """Backwards-compatible helper for tests that called the legacy sync API.

    Delegates to DeterministicEmbedder so the output is byte-identical.
    """
    embedder = DeterministicEmbedder(dim=EMBEDDING_DIM)
    return asyncio.run(embedder.embed(text))
