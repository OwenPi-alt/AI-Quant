import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import asyncpg


@dataclass
class Repository:
    pool: asyncpg.Pool

    @classmethod
    async def connect(cls, database_url: str) -> "Repository":
        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
        return cls(pool=pool)

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()

    # ---------------- market data ----------------

    async def insert_market_snapshot(
        self,
        *,
        source: str,
        market: str,
        symbol: str,
        price: float | None,
        bid: float | None = None,
        ask: float | None = None,
        volume_24h: float | None = None,
        funding_rate: float | None = None,
        open_interest: float | None = None,
        payload: dict[str, Any] | None = None,
    ) -> UUID:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                """
                INSERT INTO market_snapshot
                  (source, market, symbol, price, bid, ask, volume_24h, funding_rate, open_interest, payload)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
                RETURNING id
                """,
                source,
                market,
                symbol,
                price,
                bid,
                ask,
                volume_24h,
                funding_rate,
                open_interest,
                json.dumps(payload or {}, ensure_ascii=True),
            )

    async def recent_snapshots(self, symbol: str, limit: int = 120) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT * FROM market_snapshot
                WHERE symbol = $1 AND price IS NOT NULL
                ORDER BY created_at DESC
                LIMIT $2
                """,
                symbol,
                limit,
            )

    async def latest_market_snapshot_id(self, symbol: str, market: str) -> UUID | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                """
                SELECT id FROM market_snapshot
                WHERE symbol = $1 AND market = $2 AND price IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 1
                """,
                symbol,
                market,
            )

    async def latest_price(self, symbol: str, market: str) -> float | None:
        async with self.pool.acquire() as conn:
            value = await conn.fetchval(
                """
                SELECT price FROM market_snapshot
                WHERE symbol = $1 AND market = $2 AND price IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 1
                """,
                symbol,
                market,
            )
            return float(value) if value is not None else None

    # ---------------- trade signals ----------------

    async def insert_trade_signal(
        self,
        *,
        strategy: str,
        market: str,
        symbol: str,
        direction: str,
        confidence: float,
        entry_min: float,
        entry_max: float,
        stop_loss: float,
        take_profit: list[float],
        risk_reward_ratio: float,
        features: dict[str, Any],
    ) -> UUID:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                """
                INSERT INTO trade_signal
                  (strategy, market, symbol, direction, confidence, entry_min, entry_max,
                   stop_loss, take_profit, risk_reward_ratio, features)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11::jsonb)
                RETURNING id
                """,
                strategy,
                market,
                symbol,
                direction,
                confidence,
                entry_min,
                entry_max,
                stop_loss,
                json.dumps(take_profit, ensure_ascii=True),
                risk_reward_ratio,
                json.dumps(features, ensure_ascii=True),
            )

    async def new_signals(self, limit: int = 10) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT * FROM trade_signal
                WHERE status = 'NEW'
                ORDER BY created_at
                LIMIT $1
                """,
                limit,
            )

    async def mark_signal(self, signal_id: UUID, status: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE trade_signal SET status = $2 WHERE id = $1", signal_id, status)

    # ---------------- experience memory ----------------

    async def latest_memories(self, symbol: str, limit: int = 5) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT id, summary, error_tags, outcome
                FROM experience_memory
                WHERE symbol = $1 OR symbol IS NULL
                ORDER BY created_at DESC
                LIMIT $2
                """,
                symbol,
                limit,
            )

    async def recall_experiences(
        self,
        embedding: list[float],
        symbol: str | None,
        limit: int = 5,
    ) -> list[asyncpg.Record]:
        """pgvector cosine similarity over experience_memory."""
        vector_literal = _vector_literal(embedding)
        if vector_literal is None:
            return []
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT id, symbol, market, summary, error_tags, outcome,
                       1 - (embedding <=> $1::vector) AS similarity
                FROM experience_memory
                WHERE embedding IS NOT NULL
                  AND ($2::text IS NULL OR symbol = $2 OR symbol IS NULL)
                ORDER BY embedding <=> $1::vector
                LIMIT $3
                """,
                vector_literal,
                symbol,
                limit,
            )

    # ---------------- wiki ----------------

    async def recall_wikis(
        self,
        embedding: list[float],
        symbol: str | None,
        market: str | None,
        limit: int = 5,
    ) -> list[asyncpg.Record]:
        """pgvector cosine similarity over wiki_entry.

        Rows with NULL embedding rank highest so seeded entries get
        recalled before their first embed; caller is expected to fill
        their embedding via `update_wiki_embedding`.
        """
        vector_literal = _vector_literal(embedding)
        if vector_literal is None:
            return []
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT id, category, symbol, market, title, body, tags,
                       confidence, weight,
                       embedding IS NULL AS needs_embedding,
                       CASE WHEN embedding IS NULL THEN 0.0
                            ELSE 1 - (embedding <=> $1::vector)
                       END AS similarity
                FROM wiki_entry
                WHERE active
                  AND ($2::text IS NULL OR symbol IS NULL OR symbol = $2)
                  AND ($3::text IS NULL OR market IS NULL OR market = $3)
                ORDER BY needs_embedding DESC,
                         embedding <=> $1::vector NULLS LAST
                LIMIT $4
                """,
                vector_literal,
                symbol,
                market,
                limit,
            )

    async def wiki_without_embedding(self, limit: int = 50) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT id, title, body, category, tags
                FROM wiki_entry
                WHERE active AND embedding IS NULL
                ORDER BY created_at
                LIMIT $1
                """,
                limit,
            )

    async def update_wiki_embedding(self, wiki_id: UUID, embedding: list[float]) -> None:
        vector_literal = _vector_literal(embedding)
        if vector_literal is None:
            return
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE wiki_entry SET embedding = $2::vector, updated_at = now() WHERE id = $1",
                wiki_id,
                vector_literal,
            )

    async def bump_wiki_use(self, wiki_ids: list[UUID]) -> None:
        if not wiki_ids:
            return
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE wiki_entry
                SET use_count = use_count + 1, last_used_at = now()
                WHERE id = ANY($1::uuid[])
                """,
                wiki_ids,
            )

    async def upsert_wiki(
        self,
        *,
        category: str,
        title: str,
        body: str,
        symbol: str | None = None,
        market: str | None = None,
        tags: list[str] | None = None,
        source: str = "manual",
        confidence: float = 0.7,
        weight: float = 1.0,
        embedding: list[float] | None = None,
    ) -> UUID:
        vector_literal = _vector_literal(embedding)
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                """
                INSERT INTO wiki_entry
                  (category, symbol, market, title, body, tags, source,
                   confidence, weight, embedding)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::vector)
                RETURNING id
                """,
                category,
                symbol,
                market,
                title,
                body,
                tags or [],
                source,
                confidence,
                weight,
                vector_literal,
            )

    # ---------------- broker queue ----------------

    async def approved_decisions_without_order(self, limit: int = 10) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT d.id
                FROM decision_log d
                JOIN approval_request a ON a.decision_id = d.id AND a.status = 'APPROVED'
                WHERE d.risk_status = 'PASS'
                  AND NOT EXISTS (SELECT 1 FROM trade_order o WHERE o.decision_id = d.id)
                ORDER BY a.approved_at
                LIMIT $1
                """,
                limit,
            )

    # ---------------- review tasks ----------------

    async def due_review_tasks(self, limit: int = 20) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT rt.*, d.symbol, d.market, d.agent_json, d.created_at AS decision_created_at
                FROM review_task rt
                JOIN decision_log d ON d.id = rt.decision_id
                WHERE rt.status = 'PENDING' AND rt.due_at <= now()
                ORDER BY rt.due_at
                LIMIT $1
                """,
                limit,
            )

    async def mark_review_task(self, task_id: UUID, status: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE review_task SET status = $2, attempts = attempts + 1 WHERE id = $1",
                task_id,
                status,
            )

    async def insert_review_bundle(
        self,
        *,
        task: asyncpg.Record,
        max_favorable: float,
        max_adverse: float,
        hit_tp: bool,
        hit_sl: bool,
        agent_correct: bool,
        error_tags: list[str],
        experience_summary: str,
        rule_candidate: str,
        payload: dict[str, Any],
        embedding: list[float] | None = None,
    ) -> UUID:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                review_id = await conn.fetchval(
                    """
                    INSERT INTO review_result
                      (task_id, decision_id, window_name, max_favorable_excursion,
                       max_adverse_excursion, hit_take_profit, hit_stop_loss, agent_correct,
                       error_tags, experience_summary, rule_candidate, payload)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb)
                    RETURNING id
                    """,
                    task["id"],
                    task["decision_id"],
                    task["window_name"],
                    max_favorable,
                    max_adverse,
                    hit_tp,
                    hit_sl,
                    agent_correct,
                    error_tags,
                    experience_summary,
                    rule_candidate,
                    json.dumps(payload, ensure_ascii=True),
                )
                embedding_literal = _vector_literal(embedding)
                await conn.execute(
                    """
                    INSERT INTO experience_memory
                      (symbol, market, memory_type, summary, error_tags, outcome,
                       embedding, source_decision_id, source_review_id)
                    VALUES ($1, $2, 'TRADE_REVIEW', $3, $4, $5::jsonb, $6::vector, $7, $8)
                    """,
                    task["symbol"],
                    task["market"],
                    experience_summary,
                    error_tags,
                    json.dumps(payload, ensure_ascii=True),
                    embedding_literal,
                    task["decision_id"],
                    review_id,
                )
                if rule_candidate:
                    await conn.execute(
                        """
                        INSERT INTO rule_candidate
                          (scope, condition, action, confidence, sample_count, source_review_id, payload)
                        VALUES ($1, $2, $3, $4, 1, $5, $6::jsonb)
                        """,
                        f"{task['market']}:{task['symbol']}",
                        rule_candidate,
                        "tighten_or_skip",
                        0.50,
                        review_id,
                        json.dumps(payload, ensure_ascii=True),
                    )
                await conn.execute("UPDATE review_task SET status = 'DONE' WHERE id = $1", task["id"])
                return review_id

    async def market_window(self, symbol: str, since: datetime) -> list[asyncpg.Record]:
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT created_at, price
                FROM market_snapshot
                WHERE symbol = $1 AND created_at >= $2 AND price IS NOT NULL
                ORDER BY created_at
                LIMIT 5000
                """,
                symbol,
                since,
            )

    # ---------------- position keeper ----------------

    async def open_positions(self) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT id, decision_id, market, symbol, direction, entry_price,
                       stop_loss, take_profit, qty, notional_usd
                FROM trade_position
                WHERE status = 'OPEN'
                ORDER BY created_at
                """
            )

    async def close_position(
        self,
        *,
        position_id: UUID,
        close_price: float,
        realized_pnl_usd: float,
        close_reason: str,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE trade_position
                SET status = 'CLOSED',
                    closed_at = now(),
                    close_reason = $2,
                    close_price = $3,
                    realized_pnl_usd = $4,
                    unrealized_pnl_usd = 0,
                    updated_at = now()
                WHERE id = $1 AND status = 'OPEN'
                """,
                position_id,
                close_reason,
                close_price,
                realized_pnl_usd,
            )

    async def update_position_unrealized(self, position_id: UUID, unrealized_pnl_usd: float) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE trade_position
                SET unrealized_pnl_usd = $2, updated_at = now()
                WHERE id = $1 AND status = 'OPEN'
                """,
                position_id,
                unrealized_pnl_usd,
            )

    # ---------------- account snapshot ----------------

    async def latest_account_snapshot(self) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT * FROM account_snapshot ORDER BY created_at DESC LIMIT 1"
            )

    async def insert_account_snapshot(
        self,
        *,
        mode: str,
        equity_usd: float,
        available_usd: float,
        daily_pnl_usd: float,
        weekly_pnl_usd: float,
        consecutive_losses: int,
        daily_window_date: str,
        weekly_window_start: str,
        raw: dict[str, Any] | None = None,
    ) -> UUID:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                """
                INSERT INTO account_snapshot
                  (mode, equity_usd, available_usd, daily_pnl_usd, weekly_pnl_usd,
                   consecutive_losses, daily_window_date, weekly_window_start, raw)
                VALUES ($1, $2, $3, $4, $5, $6, $7::date, $8::date, $9::jsonb)
                RETURNING id
                """,
                mode,
                equity_usd,
                available_usd,
                daily_pnl_usd,
                weekly_pnl_usd,
                consecutive_losses,
                daily_window_date,
                weekly_window_start,
                json.dumps(raw or {}, ensure_ascii=True),
            )

    # ---------------- risk events ----------------

    async def insert_risk_event(
        self,
        *,
        event_type: str,
        severity: str,
        reasons: list[str],
        payload: dict[str, Any] | None = None,
        decision_id: UUID | None = None,
        order_id: UUID | None = None,
    ) -> UUID:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                """
                INSERT INTO risk_event
                  (event_type, severity, decision_id, order_id, reasons, payload)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                RETURNING id
                """,
                event_type,
                severity,
                decision_id,
                order_id,
                reasons,
                json.dumps(payload or {}, ensure_ascii=True),
            )


def _vector_literal(values: list[float] | None) -> str | None:
    if values is None:
        return None
    formatted = ",".join(f"{float(v):.6f}" for v in values)
    return "[" + formatted + "]"
