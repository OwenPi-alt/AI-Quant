from __future__ import annotations

import asyncio
import logging
import statistics

from app.db.repository import Repository
from app.settings import Settings

logger = logging.getLogger(__name__)


async def run_strategy(settings: Settings) -> None:
    repo = await Repository.connect(settings.database_url)
    try:
        while True:
            for symbol in settings.symbols:
                try:
                    await generate_crypto_signals(repo, symbol)
                except Exception:
                    logger.exception("strategy failed for %s", symbol)
            await asyncio.sleep(300)
    except asyncio.CancelledError:
        logger.info("strategy cancelled")
        raise
    finally:
        await repo.close()


async def generate_crypto_signals(repo: Repository, symbol: str) -> None:
    snapshots = await repo.recent_snapshots(symbol, limit=80)
    if len(snapshots) < 20:
        return
    ordered = list(reversed(snapshots))
    prices = [float(row["price"]) for row in ordered if row["price"] is not None]
    if len(prices) < 20:
        return
    latest = prices[-1]
    ma20 = statistics.fmean(prices[-20:])
    ma60 = statistics.fmean(prices[-60:]) if len(prices) >= 60 else statistics.fmean(prices)
    funding = _last_non_null([row["funding_rate"] for row in ordered])
    oi = _last_non_null([row["open_interest"] for row in ordered])

    if latest > ma20 * 1.003 and ma20 > ma60:
        stop = latest * 0.985
        risk = latest - stop
        if risk <= 0:
            return
        take_profit = [latest + risk * 1.8, latest + risk * 2.6]
        rr = _weighted_rr(latest, stop, take_profit)
        if rr < 1.5:
            return
        await repo.insert_trade_signal(
            strategy="trend_following_v1",
            market="BINANCE_FUTURES_PAPER",
            symbol=symbol,
            direction="LONG",
            confidence=0.67,
            entry_min=latest * 0.997,
            entry_max=latest * 1.002,
            stop_loss=stop,
            take_profit=take_profit,
            risk_reward_ratio=rr,
            features={"latest": latest, "ma20": ma20, "ma60": ma60, "funding": _num(funding), "open_interest": _num(oi)},
        )
        logger.info("trend signal generated %s rr=%.2f", symbol, rr)
    elif latest < ma20 * 0.985:
        stop = latest * 0.975
        risk = latest - stop
        if risk <= 0:
            return
        take_profit = [latest + risk * 1.6]
        rr = _weighted_rr(latest, stop, take_profit)
        if rr < 1.5:
            return
        await repo.insert_trade_signal(
            strategy="mean_reversion_v1",
            market="BINANCE_FUTURES_PAPER",
            symbol=symbol,
            direction="LONG",
            confidence=0.66,
            entry_min=latest * 0.995,
            entry_max=latest * 1.001,
            stop_loss=stop,
            take_profit=take_profit,
            risk_reward_ratio=rr,
            features={"latest": latest, "ma20": ma20, "funding": _num(funding), "open_interest": _num(oi)},
        )
        logger.info("mean reversion signal generated %s rr=%.2f", symbol, rr)


def _weighted_rr(entry: float, stop: float, take_profit: list[float]) -> float:
    risk = abs(entry - stop)
    if risk <= 0 or not take_profit:
        return 0.0
    reward = statistics.fmean(abs(tp - entry) for tp in take_profit)
    return reward / risk


def _last_non_null(values: list[object]) -> object | None:
    for value in reversed(values):
        if value is not None:
            return value
    return None


def _num(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
