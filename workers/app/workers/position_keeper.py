from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timezone

from app.db.repository import Repository
from app.services.notifier import Notifier
from app.settings import Settings

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 60


async def run_position_keeper(settings: Settings) -> None:
    repo = await Repository.connect(settings.database_url)
    notifier = Notifier(settings)
    try:
        while True:
            try:
                await tick(repo, notifier, settings)
            except Exception:
                logger.exception("position keeper tick failed")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        logger.info("position keeper cancelled")
        raise
    finally:
        await repo.close()


async def tick(repo: Repository, notifier: Notifier, settings: Settings) -> None:
    positions = await repo.open_positions()
    closed_pnl: list[tuple[str, float]] = []
    for position in positions:
        symbol = position["symbol"]
        market = position["market"]
        mid = await repo.latest_price(symbol, market)
        if mid is None:
            continue
        direction = (position["direction"] or "").upper()
        entry = float(position["entry_price"])
        qty = float(position["qty"])
        stop = float(position["stop_loss"])
        take_profit = _parse_tp(position["take_profit"])
        outcome = _evaluate(direction, mid, entry, stop, take_profit)
        unreal = (mid - entry) * qty if direction in {"LONG", "BUY"} else (entry - mid) * qty
        if outcome is None:
            await repo.update_position_unrealized(position["id"], unreal)
            continue
        close_price, reason = outcome
        pnl = (close_price - entry) * qty if direction in {"LONG", "BUY"} else (entry - close_price) * qty
        await repo.close_position(
            position_id=position["id"],
            close_price=close_price,
            realized_pnl_usd=pnl,
            close_reason=reason,
        )
        closed_pnl.append((symbol, pnl))
        try:
            await notifier.send(
                "[AI-Quant] 模拟盘平仓\n"
                f"品种: {symbol}\n方向: {direction}\n"
                f"原因: {reason}\n开仓: {entry:.6g}  平仓: {close_price:.6g}\n"
                f"盈亏: {pnl:+.4f} USDT",
                {"position_id": str(position["id"]), "reason": reason},
            )
        except Exception:
            logger.exception("close notify failed position=%s", position["id"])

    await refresh_account_snapshot(repo, settings, closed_pnl)


async def refresh_account_snapshot(
    repo: Repository, settings: Settings, closed_pnl: list[tuple[str, float]]
) -> None:
    snapshot = await repo.latest_account_snapshot()
    now_utc = datetime.now(timezone.utc)
    today = now_utc.date().isoformat()
    monday = _monday_of(now_utc.date()).isoformat()

    if snapshot is None:
        equity = settings.account_equity_usd
        available = settings.account_equity_usd
        daily = 0.0
        weekly = 0.0
        consec = 0
        snap_day = today
        snap_week = monday
    else:
        equity = float(snapshot["equity_usd"])
        available = float(snapshot["available_usd"])
        daily = float(snapshot["daily_pnl_usd"])
        weekly = float(snapshot["weekly_pnl_usd"])
        consec = int(snapshot["consecutive_losses"])
        snap_day = (
            snapshot["daily_window_date"].isoformat()
            if snapshot["daily_window_date"] is not None
            else today
        )
        snap_week = (
            snapshot["weekly_window_start"].isoformat()
            if snapshot["weekly_window_start"] is not None
            else monday
        )

    if snap_day != today:
        daily = 0.0
        snap_day = today
    if snap_week != monday:
        weekly = 0.0
        snap_week = monday

    for _, pnl in closed_pnl:
        equity += pnl
        available += pnl
        daily += pnl
        weekly += pnl
        if pnl < 0:
            consec += 1
        elif pnl > 0:
            consec = 0

    if not closed_pnl and snapshot is not None:
        prev_day = snapshot["daily_window_date"].isoformat() if snapshot["daily_window_date"] else today
        prev_week = snapshot["weekly_window_start"].isoformat() if snapshot["weekly_window_start"] else monday
        if snap_day == prev_day and snap_week == prev_week and float(snapshot["equity_usd"]) == equity:
            return

    await repo.insert_account_snapshot(
        mode="PAPER_ONLY",
        equity_usd=equity,
        available_usd=available,
        daily_pnl_usd=daily,
        weekly_pnl_usd=weekly,
        consecutive_losses=consec,
        daily_window_date=snap_day,
        weekly_window_start=snap_week,
        raw={"closed": [{"symbol": s, "pnl": p} for s, p in closed_pnl]},
    )


def _evaluate(
    direction: str, mid: float, entry: float, stop: float, take_profit: list[float]
) -> tuple[float, str] | None:
    if direction in {"LONG", "BUY"}:
        if mid <= stop:
            return stop, "STOP_LOSS"
        if take_profit:
            target = min(take_profit)
            if mid >= target:
                return target, "TAKE_PROFIT"
        return None
    if direction in {"SHORT", "SELL"}:
        if mid >= stop:
            return stop, "STOP_LOSS"
        if take_profit:
            target = max(take_profit)
            if mid <= target:
                return target, "TAKE_PROFIT"
        return None
    return None


def _parse_tp(raw: object) -> list[float]:
    if raw is None:
        return []
    if isinstance(raw, list):
        candidates = raw
    elif isinstance(raw, str):
        try:
            candidates = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(candidates, list):
            return []
    else:
        return []
    out: list[float] = []
    for item in candidates:
        if isinstance(item, dict):
            value = item.get("px") or item.get("price") or item.get("value")
        else:
            value = item
        try:
            if value is not None:
                out.append(float(value))
        except (TypeError, ValueError):
            continue
    return out


def _monday_of(value: date) -> date:
    return value.fromordinal(value.toordinal() - value.weekday())
