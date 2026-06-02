from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
from typing import Any
from uuid import UUID

from app.db.repository import Repository
from app.services.control_api import ControlApi
from app.services.embedding import EmbeddingProvider, make_embedder
from app.services.notifier import Notifier
from app.settings import Settings

logger = logging.getLogger(__name__)


async def run_agent(settings: Settings) -> None:
    repo = await Repository.connect(settings.database_url)
    control = ControlApi(settings.control_api_url, settings.api_auth_token)
    notifier = Notifier(settings)
    embedder = make_embedder(settings)
    try:
        while True:
            signals = await repo.new_signals(limit=10)
            for signal in signals:
                try:
                    await handle_signal(repo, control, notifier, embedder, settings, signal)
                except Exception:
                    logger.exception("agent failed signal=%s", signal["id"])
                    await safe_mark(repo, signal["id"], "AGENT_FAILED")
            await asyncio.sleep(30)
    except asyncio.CancelledError:
        logger.info("agent worker cancelled, closing repo")
        raise
    finally:
        await repo.close()


async def handle_signal(
    repo: Repository,
    control: ControlApi,
    notifier: Notifier,
    embedder: EmbeddingProvider,
    settings: Settings,
    signal: Any,
) -> None:
    await repo.mark_signal(signal["id"], "PROCESSING")

    query_text = build_query_text(signal)
    query_embedding = await embedder.embed(query_text)

    await backfill_wiki_embeddings(repo, embedder)

    experiences = await repo.recall_experiences(
        query_embedding, signal["symbol"], limit=settings.recall_experience_limit
    )
    wikis = await repo.recall_wikis(
        query_embedding, signal["symbol"], signal["market"], limit=settings.recall_wiki_limit
    )
    if wikis:
        await repo.bump_wiki_use([row["id"] for row in wikis])

    market_snapshot_id = await repo.latest_market_snapshot_id(signal["symbol"], signal["market"])
    agent_json = build_agent_json(signal, experiences, wikis)
    prompt_hash = hashlib.sha256(
        json.dumps(
            {
                "signal": dict(signal),
                "experiences": [_record_summary(item) for item in experiences],
                "wikis": [_wiki_summary(item) for item in wikis],
                "query_text": query_text,
            },
            default=str,
            sort_keys=True,
        ).encode()
    ).hexdigest()

    payload: dict[str, Any] = {
        "signalId": str(signal["id"]),
        "market": signal["market"],
        "symbol": signal["symbol"],
        "mode": "PAPER_ONLY",
        "promptHash": prompt_hash,
        "modelName": f"{settings.llm_model}:deterministic-mvp+wiki",
        "agentJson": agent_json,
        "relatedMemoryIds": [str(item["id"]) for item in experiences],
    }
    if market_snapshot_id is not None:
        payload["marketSnapshotId"] = str(market_snapshot_id)

    response = await control.create_decision(payload)
    decision_id = str(response["decisionId"])
    risk = response["risk"]
    if risk["status"] == "PASS":
        try:
            approval = await control.request_approval(
                decision_id, "telegram", settings.telegram_chat_id or "operator"
            )
        except Exception:
            logger.exception("approval request failed decision=%s", decision_id)
            await repo.mark_signal(signal["id"], "APPROVAL_REQUEST_FAILED")
            return
        await repo.mark_signal(signal["id"], "AWAITING_APPROVAL")
        await safe_notify(
            notifier,
            format_approval_message(signal, agent_json, approval, wikis),
            {"decision_id": decision_id, "wiki_count": len(wikis)},
        )
    else:
        await repo.mark_signal(signal["id"], "RISK_REJECTED")
        await safe_notify(
            notifier,
            f"[AI-Quant] 风控拒单\nID: {decision_id}\n品种: {signal['symbol']}\n"
            f"原因: {', '.join(risk['reasons'])}",
            {"decision_id": decision_id, "risk": risk},
        )


def build_query_text(signal: Any) -> str:
    features = _json_value(signal["features"], default={})
    if isinstance(features, dict):
        feature_summary = ", ".join(f"{k}={v}" for k, v in sorted(features.items()))
    else:
        feature_summary = str(features)
    return (
        f"market={signal['market']} symbol={signal['symbol']} "
        f"direction={signal['direction']} strategy={signal['strategy']} "
        f"confidence={signal['confidence']} rr={signal['risk_reward_ratio']} "
        f"features=({feature_summary})"
    )


async def backfill_wiki_embeddings(repo: Repository, embedder: EmbeddingProvider) -> None:
    """Compute embeddings for newly-seeded wiki entries that have no vector."""
    pending = await repo.wiki_without_embedding(limit=20)
    for row in pending:
        text = f"{row['category']} :: {row['title']} :: {row['body']}"
        try:
            vector = await embedder.embed(text)
            await repo.update_wiki_embedding(row["id"], vector)
        except Exception:
            logger.exception("failed to backfill wiki embedding id=%s", row["id"])


def build_agent_json(signal: Any, experiences: list[Any], wikis: list[Any]) -> dict[str, Any]:
    take_profit = _json_value(signal["take_profit"], default=[])
    features = _json_value(signal["features"], default={})
    confidence = float(signal["confidence"])
    rr = float(signal["risk_reward_ratio"])
    entry_min = float(signal["entry_min"])
    entry_max = float(signal["entry_max"])

    wiki_hints = [
        {
            "id": str(w["id"]),
            "category": w["category"],
            "title": w["title"],
            "body": w["body"],
            "tags": list(w["tags"] or []),
            "confidence": float(w["confidence"]),
            "similarity": float(w["similarity"]),
        }
        for w in wikis
    ]
    experience_hints = [
        {
            "id": str(e["id"]),
            "summary": e["summary"],
            "outcome": e["outcome"],
            "similarity": float(e["similarity"]),
            "error_tags": list(e["error_tags"] or []),
        }
        for e in experiences
    ]
    wiki_titles = [w["title"][:40] for w in wikis[:3]]
    reasoning = f"{signal['strategy']} | features={features}"
    if wiki_titles:
        reasoning += " | wiki: " + " ; ".join(wiki_titles)

    return {
        "symbol": signal["symbol"],
        "market": signal["market"],
        "direction": signal["direction"],
        "entry": {"type": "LIMIT", "min": entry_min, "max": entry_max},
        "stop_loss": float(signal["stop_loss"]),
        "take_profit": [float(tp) for tp in take_profit if tp is not None],
        "risk_reward_ratio": rr,
        "confidence": confidence,
        "max_position_size": {"notional_usd": 100.0, "risk_usd": 5.0},
        "leverage": 1,
        "invalidation_condition": "price closes beyond stop_loss or major news risk triggers pause",
        "reasoning_summary": reasoning,
        "related_memories": [str(e["id"]) for e in experiences],
        "news_sources": [],
        "sentiment_score": 0.0,
        "risk_flags": ["PAPER_ONLY", "MANUAL_APPROVAL_REQUIRED"],
        "wiki_hints": wiki_hints,
        "experience_hints": experience_hints,
    }


def format_approval_message(
    signal: Any, agent_json: dict[str, Any], approval: dict[str, Any], wikis: list[Any]
) -> str:
    wiki_lines = (
        "\n".join(f"  - [{w['category']}] {w['title']}" for w in wikis[:3])
        if wikis
        else "  (none)"
    )
    return (
        "[AI-Quant] 待确认交易\n"
        f"ID: {approval['decisionId']}\n"
        f"市场: {signal['market']}\n"
        f"品种: {signal['symbol']}\n"
        f"方向: {signal['direction']}\n"
        f"入场: {agent_json['entry']['min']:.6g}-{agent_json['entry']['max']:.6g}\n"
        f"止损: {agent_json['stop_loss']:.6g}\n"
        f"止盈: {agent_json['take_profit']}\n"
        f"RR: {agent_json['risk_reward_ratio']:.2f}, Confidence: {agent_json['confidence']:.2f}\n"
        f"依据: {agent_json['reasoning_summary']}\n"
        f"Wiki 命中 ({len(wikis)}):\n{wiki_lines}\n"
        f"确认: {approval['command']}\n"
        f"过期: {approval['expiresAt']}"
    )


def _record_summary(row: Any) -> dict[str, Any]:
    sim = row["similarity"] if "similarity" in row.keys() else 0.0
    return {"id": str(row["id"]), "similarity": float(sim)}


def _wiki_summary(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "category": row["category"],
        "title": row["title"],
        "similarity": float(row["similarity"]),
    }


async def safe_mark(repo: Repository, signal_id: UUID, status: str) -> None:
    with contextlib.suppress(Exception):
        await repo.mark_signal(signal_id, status)


async def safe_notify(notifier: Notifier, text: str, extra: dict[str, Any]) -> None:
    try:
        await notifier.send(text, extra)
    except Exception:
        logger.exception("notify failed text=%s", text[:80])


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
