from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.clients.binance import BinanceClient
from app.clients.hyperliquid import HyperliquidClient
from app.clients.polymarket import PolymarketClient
from app.db.repository import Repository
from app.settings import Settings

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 60


async def run_collector(settings: Settings) -> None:
    repo = await Repository.connect(settings.database_url)
    binance = BinanceClient(settings.binance_spot_base_url, settings.binance_futures_base_url)
    hyperliquid = HyperliquidClient(settings.hyperliquid_info_url)
    polymarket = PolymarketClient(
        settings.polymarket_gamma_url,
        settings.polymarket_clob_url,
        settings.polymarket_geoblock_url,
    )
    try:
        while True:
            await asyncio.gather(
                collect_binance(repo, binance, settings),
                collect_hyperliquid(repo, hyperliquid, settings),
                collect_polymarket(repo, polymarket, settings),
                return_exceptions=True,
            )
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        logger.info("collector cancelled")
        raise
    finally:
        await repo.close()


async def collect_binance(repo: Repository, client: BinanceClient, settings: Settings) -> None:
    for symbol in settings.symbols:
        try:
            ticker = await client.ticker_24h(symbol)
            premium = await client.premium_index(symbol)
            oi = await client.open_interest(symbol)
            await repo.insert_market_snapshot(
                source="BINANCE",
                market="BINANCE_FUTURES_PAPER",
                symbol=symbol,
                price=_float(ticker.get("lastPrice")),
                bid=_float(ticker.get("bidPrice")),
                ask=_float(ticker.get("askPrice")),
                volume_24h=_float(ticker.get("volume")),
                funding_rate=_float(premium.get("lastFundingRate")),
                open_interest=_float(oi.get("openInterest")),
                payload={"ticker": ticker, "premium": premium, "open_interest": oi},
            )
            logger.info("collected binance %s", symbol)
        except Exception:
            logger.exception("failed to collect binance %s", symbol)


async def collect_hyperliquid(repo: Repository, client: HyperliquidClient, settings: Settings) -> None:
    try:
        mids = await client.all_mids()
        universe, contexts = await client.meta_and_asset_ctxs()
        ctx_by_coin: dict[str, dict[str, Any]] = {}
        for index, item in enumerate(universe):
            coin = str(item.get("name", "")).upper()
            if coin and index < len(contexts):
                ctx_by_coin[coin] = contexts[index]
        for coin in settings.hyperliquid_coin_list:
            ctx = ctx_by_coin.get(coin, {})
            price = _float(mids.get(coin) or ctx.get("markPx") or ctx.get("midPx"))
            await repo.insert_market_snapshot(
                source="HYPERLIQUID",
                market="HYPERLIQUID_PERP_PAPER",
                symbol=coin,
                price=price,
                funding_rate=_float(ctx.get("funding")),
                open_interest=_float(ctx.get("openInterest")),
                payload={"mid": mids.get(coin), "asset_ctx": ctx},
            )
            logger.info("collected hyperliquid %s", coin)
    except Exception:
        logger.exception("failed to collect hyperliquid")


async def collect_polymarket(repo: Repository, client: PolymarketClient, settings: Settings) -> None:
    mode = settings.polymarket_mode.upper()
    if mode not in {"OBSERVE_ONLY", "PAPER_ONLY"}:
        logger.warning("polymarket mode=%s not allowed by safety guard; skipping", mode)
        return
    try:
        geoblock = await client.geoblock()
    except Exception:
        logger.exception("polymarket geoblock probe failed; skipping cycle for safety")
        return
    if _is_blocked(geoblock):
        logger.warning(
            "polymarket geoblock=%s; skipping data ingestion (must observe legal restrictions)",
            geoblock,
        )
        await repo.insert_risk_event(
            event_type="GEOBLOCK",
            severity="HIGH",
            reasons=["POLYMARKET_GEOBLOCKED"],
            payload={"geoblock": geoblock},
        )
        return
    try:
        markets = await client.markets(limit=20)
        for market in markets[:10]:
            token_ids = PolymarketClient.token_ids(market)
            if not token_ids:
                continue
            book = await client.order_book(token_ids[0])
            bid = _best_price(book.get("bids"), reverse=True)
            ask = _best_price(book.get("asks"), reverse=False)
            mid = (bid + ask) / 2 if bid is not None and ask is not None else None
            slug = str(market.get("slug") or market.get("id") or token_ids[0])[:120]
            await repo.insert_market_snapshot(
                source="POLYMARKET",
                market="POLYMARKET_PAPER",
                symbol=slug,
                price=mid,
                bid=bid,
                ask=ask,
                volume_24h=_float(market.get("volume24hr") or market.get("volume")),
                open_interest=_float(market.get("openInterest")),
                payload={"market": market, "book": book, "geoblock": geoblock},
            )
        logger.info("collected polymarket markets=%s", len(markets))
    except Exception:
        logger.exception("failed to collect polymarket")


def _is_blocked(geoblock: Any) -> bool:
    if not isinstance(geoblock, dict):
        return False
    for key in ("blocked", "isBlocked", "geoBlocked", "geo_blocked"):
        value = geoblock.get(key)
        if isinstance(value, bool) and value:
            return True
        if isinstance(value, str) and value.strip().lower() in {"true", "yes", "1"}:
            return True
    return False


def _float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _best_price(levels: object, reverse: bool) -> float | None:
    if not isinstance(levels, list) or not levels:
        return None
    prices = []
    for level in levels:
        if isinstance(level, dict) and "price" in level:
            price = _float(level["price"])
            if price is not None:
                prices.append(price)
    if not prices:
        return None
    return max(prices) if reverse else min(prices)
