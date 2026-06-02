-- V004: wiki_entry — curated trading knowledge that the agent recalls
-- alongside specific past trade reviews (experience_memory). Wiki entries
-- are CURATED RULES OF THUMB, written either by the operator or distilled
-- from verified_rule. They are vectorised so they appear in the same
-- pgvector recall path as experience_memory.

CREATE TABLE IF NOT EXISTS wiki_entry (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  category TEXT NOT NULL,
  symbol TEXT,
  market TEXT,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  source TEXT NOT NULL DEFAULT 'manual',
  confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.7,
  weight NUMERIC(4, 3) NOT NULL DEFAULT 1.0,
  embedding vector(1536),
  active BOOLEAN NOT NULL DEFAULT true,
  last_used_at TIMESTAMPTZ,
  use_count INT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_wiki_active_category ON wiki_entry (category) WHERE active;
CREATE INDEX IF NOT EXISTS idx_wiki_symbol ON wiki_entry (symbol) WHERE active AND symbol IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_wiki_market ON wiki_entry (market) WHERE active AND market IS NOT NULL;
-- lists=10 is appropriate while we have ~15 rows; rebuild larger when
-- experience_memory + wiki_entry combined exceed a few thousand.
CREATE INDEX IF NOT EXISTS idx_wiki_embedding ON wiki_entry USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);
-- Unique title lets all seed INSERTs below be idempotent (ON CONFLICT
-- DO NOTHING), so a partially-failed V004 can be re-run without
-- checksum/dup-key crashes.
CREATE UNIQUE INDEX IF NOT EXISTS uq_wiki_title ON wiki_entry (title);

-- Seed entries. embedding left NULL on purpose — the agent-worker's
-- embedding provider will lazy-fill it on first recall. This keeps V004
-- independent of any LLM provider being configured at deploy time.
-- ON CONFLICT (title) DO NOTHING makes every INSERT idempotent.

INSERT INTO wiki_entry (category, symbol, market, title, body, tags, source, confidence) VALUES
('funding', NULL, NULL,
 'Funding spike over +1bp/8h often precedes mean reversion',
 'When perpetual funding rate stays above 0.0001 (1 bps) per 8h funding interval for 2+ periods, long crowding is high. Subsequent 24h often shows 1-3% mean reversion against the trend. Reduce long size or skip late entries.',
 ARRAY['funding','mean_reversion','crowding'], 'manual', 0.72),

('funding', NULL, NULL,
 'Funding flip from positive to negative + OI drop = early reversal',
 'When 8h funding flips from > +0.005% to negative while open interest drops > 3% in 24h, it commonly marks the early stage of a trend reversal. Treat existing long signals with skepticism; tighten stops.',
 ARRAY['funding','reversal','oi'], 'manual', 0.68),

('pattern', NULL, NULL,
 'EMA20 crossing EMA60 from below with rising volume',
 'Bullish trend ignition: when 1h EMA20 crosses EMA60 from below and the latest bar volume is >= 1.3x the 20-bar avg, the median follow-through over 24h is favourable. Confidence drops sharply if RSI(14) > 75 at the crossover.',
 ARRAY['trend','ema','volume'], 'manual', 0.7),

('risk', NULL, NULL,
 'Stop distance under 0.5% is mostly noise',
 'On BTCUSDT / ETHUSDT 1h, stop-loss distance below 0.5% of entry is hit by intraday noise roughly 60% of the time. Prefer ATR-based stops at 1.0-1.5x ATR(14).',
 ARRAY['stop_loss','atr','noise'], 'manual', 0.78),

('risk', NULL, NULL,
 'Halve size after 3 consecutive losses',
 'Empirical: traders who keep position size constant after 3 consecutive losses make worse decisions on trade 4-6. System already pauses at 3 losses; if you manually unpause, halve position size for the next 5 trades.',
 ARRAY['psychology','sizing','consecutive_loss'], 'manual', 0.8),

('macro', NULL, NULL,
 'Pause auto-entry 4h around FOMC / CPI / NFP releases',
 'Major US macro releases (FOMC rate decision, CPI MoM, Non-Farm Payrolls) cause crypto vol spikes and stop runs. Block new positions from 4h before to 1h after the scheduled release time (UTC).',
 ARRAY['macro','fomc','cpi','nfp','blackout'], 'manual', 0.85),

('liquidity', NULL, NULL,
 'Weekend BTC liquidity drops ~40%',
 'From Saturday 00:00 UTC to Sunday 22:00 UTC, BTC top-of-book depth shrinks ~40% vs weekday median. Stops are more likely to slip; cap notional at 50% of weekday limit and prefer limit orders.',
 ARRAY['weekend','liquidity','slippage'], 'manual', 0.7),

('liquidity', 'BTC', 'HYPERLIQUID_PERP_PAPER',
 'Hyperliquid markPx diverging from spot > 0.3% — pre-liquidation cascade',
 'When Hyperliquid markPx for BTC diverges from a major CEX spot mid by > 0.3% for > 5 minutes, an inventory imbalance is likely. Subsequent funding rate cycles often trigger liquidations. Avoid late entries until divergence closes.',
 ARRAY['hyperliquid','mark_px','liquidation'], 'manual', 0.65),

('venue', NULL, 'POLYMARKET_PAPER',
 'Polymarket markets with 24h volume < $20k are not tradable',
 'Slippage on YES/NO trades larger than $200 in markets with under $20k 24h volume can exceed 5%. Skip these markets even if the implied probability looks attractive.',
 ARRAY['polymarket','liquidity','slippage'], 'manual', 0.9),

('venue', NULL, 'POLYMARKET_PAPER',
 'Polymarket resolution within 6h — do not enter new positions',
 'Within 6 hours of scheduled resolution, midpoint moves are dominated by gamma squeezes and last-minute information. Risk / reward is unfavourable for new entries; only manage existing positions.',
 ARRAY['polymarket','resolution','gamma'], 'manual', 0.75),

('mistake', NULL, NULL,
 'Late entry after 1.5x ATR move',
 'Entering long after the bar has already moved > 1.5x ATR(14) from breakout level historically yields max-adverse-excursion 2x worse than fresh entries. Skip or wait for pullback to 38-50% of the move.',
 ARRAY['late_entry','atr','breakout'], 'manual', 0.7),

('mistake', NULL, NULL,
 'Holding through invalidation_condition',
 'When invalidation_condition stated in agent_json is met (e.g. price closes beyond stop_loss, funding flips), do NOT override the exit. Holding through invalidation has historically converted small losses into 3-5x larger ones.',
 ARRAY['invalidation','discipline','exit'], 'manual', 0.88),

('pattern', NULL, NULL,
 'RSI > 80 with 24h return > 15% = high chase risk',
 'On BTC / ETH 1h, when RSI(14) > 80 AND trailing 24h return > 15%, the next 4-12h has a positive expectancy only ~38% of the time (vs ~52% base rate). Skip late longs; consider mean-reversion shorts with strict stops.',
 ARRAY['rsi','overbought','chasing'], 'manual', 0.65),

('risk', NULL, NULL,
 'Approval expired = market context drifted',
 'If a decision has been waiting for confirmation past the 10-minute TTL, the market has likely drifted enough that the original entry / RR is no longer valid. Always recompute from current snapshot; do not extend TTL.',
 ARRAY['approval','ttl','drift'], 'manual', 0.85),

('pattern', NULL, NULL,
 'OI rising + price flat = squeeze setup',
 'When open interest rises > 5% in 6h while price stays within a 1% band, an imbalance is being built. Breakout direction is often opposite to majority funding sign. Trade the break with confirmation, not the lead-up.',
 ARRAY['oi','squeeze','breakout'], 'manual', 0.6)
ON CONFLICT (title) DO NOTHING;
