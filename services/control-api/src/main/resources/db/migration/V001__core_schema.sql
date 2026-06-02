CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS account_snapshot (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  mode TEXT NOT NULL,
  equity_usd NUMERIC(20, 8) NOT NULL,
  available_usd NUMERIC(20, 8) NOT NULL,
  daily_pnl_usd NUMERIC(20, 8) NOT NULL DEFAULT 0,
  weekly_pnl_usd NUMERIC(20, 8) NOT NULL DEFAULT 0,
  consecutive_losses INT NOT NULL DEFAULT 0,
  raw JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS market_snapshot (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  source TEXT NOT NULL,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  price NUMERIC(30, 12),
  bid NUMERIC(30, 12),
  ask NUMERIC(30, 12),
  volume_24h NUMERIC(30, 12),
  funding_rate NUMERIC(20, 10),
  open_interest NUMERIC(30, 12),
  payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS news_event (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  source TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT,
  symbol TEXT,
  published_at TIMESTAMPTZ,
  reliability_score NUMERIC(5, 4) NOT NULL DEFAULT 0.5,
  summary TEXT,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS sentiment_snapshot (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  source TEXT NOT NULL,
  symbol TEXT,
  score NUMERIC(6, 4) NOT NULL,
  weight NUMERIC(6, 4) NOT NULL DEFAULT 0.2,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS trade_signal (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  strategy TEXT NOT NULL,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  direction TEXT NOT NULL,
  confidence NUMERIC(5, 4) NOT NULL,
  entry_min NUMERIC(30, 12),
  entry_max NUMERIC(30, 12),
  stop_loss NUMERIC(30, 12),
  take_profit JSONB NOT NULL DEFAULT '[]'::jsonb,
  risk_reward_ratio NUMERIC(10, 4),
  features JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'NEW'
);

CREATE TABLE IF NOT EXISTS decision_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  mode TEXT NOT NULL DEFAULT 'PAPER_ONLY',
  signal_id UUID REFERENCES trade_signal(id),
  prompt_hash TEXT NOT NULL,
  model_name TEXT NOT NULL,
  agent_json JSONB NOT NULL,
  json_valid BOOLEAN NOT NULL,
  confidence NUMERIC(5, 4),
  risk_status TEXT NOT NULL,
  risk_reasons TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  related_memory_ids TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  market_snapshot_id UUID REFERENCES market_snapshot(id),
  news_event_ids UUID[] NOT NULL DEFAULT ARRAY[]::UUID[],
  approval_id UUID
);

CREATE TABLE IF NOT EXISTS approval_request (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  decision_id UUID NOT NULL REFERENCES decision_log(id),
  code_hash TEXT NOT NULL,
  channel TEXT NOT NULL,
  recipient TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL DEFAULT 'PENDING',
  approved_at TIMESTAMPTZ,
  approved_by TEXT
);

ALTER TABLE decision_log
  ADD CONSTRAINT fk_decision_approval
  FOREIGN KEY (approval_id) REFERENCES approval_request(id);

CREATE TABLE IF NOT EXISTS trade_order (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  decision_id UUID REFERENCES decision_log(id),
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  side TEXT NOT NULL,
  order_type TEXT NOT NULL,
  mode TEXT NOT NULL,
  status TEXT NOT NULL,
  entry_price NUMERIC(30, 12),
  stop_loss NUMERIC(30, 12) NOT NULL,
  take_profit JSONB NOT NULL DEFAULT '[]'::jsonb,
  qty NUMERIC(30, 12),
  notional_usd NUMERIC(20, 8),
  exchange_order_id TEXT,
  client_order_id TEXT UNIQUE NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS trade_position (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  decision_id UUID REFERENCES decision_log(id),
  order_id UUID REFERENCES trade_order(id),
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  direction TEXT NOT NULL,
  status TEXT NOT NULL,
  entry_price NUMERIC(30, 12) NOT NULL,
  stop_loss NUMERIC(30, 12) NOT NULL,
  take_profit JSONB NOT NULL DEFAULT '[]'::jsonb,
  qty NUMERIC(30, 12) NOT NULL,
  notional_usd NUMERIC(20, 8) NOT NULL,
  realized_pnl_usd NUMERIC(20, 8) NOT NULL DEFAULT 0,
  unrealized_pnl_usd NUMERIC(20, 8) NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS review_task (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  decision_id UUID NOT NULL REFERENCES decision_log(id),
  window_name TEXT NOT NULL,
  due_at TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL DEFAULT 'PENDING',
  attempts INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS review_result (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  task_id UUID NOT NULL REFERENCES review_task(id),
  decision_id UUID NOT NULL REFERENCES decision_log(id),
  window_name TEXT NOT NULL,
  max_favorable_excursion NUMERIC(12, 6),
  max_adverse_excursion NUMERIC(12, 6),
  hit_take_profit BOOLEAN,
  hit_stop_loss BOOLEAN,
  agent_correct BOOLEAN,
  error_tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  experience_summary TEXT,
  rule_candidate TEXT,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS experience_memory (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  symbol TEXT,
  market TEXT,
  memory_type TEXT NOT NULL,
  summary TEXT NOT NULL,
  error_tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  outcome JSONB NOT NULL DEFAULT '{}'::jsonb,
  embedding vector(1536),
  source_decision_id UUID REFERENCES decision_log(id),
  source_review_id UUID REFERENCES review_result(id)
);

CREATE TABLE IF NOT EXISTS rule_candidate (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  scope TEXT NOT NULL,
  condition TEXT NOT NULL,
  action TEXT NOT NULL,
  confidence NUMERIC(5, 4) NOT NULL DEFAULT 0,
  sample_count INT NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'CANDIDATE',
  expires_at TIMESTAMPTZ,
  source_review_id UUID REFERENCES review_result(id),
  payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS verified_rule (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  rule_candidate_id UUID REFERENCES rule_candidate(id),
  version INT NOT NULL DEFAULT 1,
  scope TEXT NOT NULL,
  condition TEXT NOT NULL,
  action TEXT NOT NULL,
  confidence NUMERIC(5, 4) NOT NULL,
  sample_count INT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  expires_at TIMESTAMPTZ,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS risk_event (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  event_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  decision_id UUID REFERENCES decision_log(id),
  order_id UUID REFERENCES trade_order(id),
  reasons TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_market_snapshot_symbol_created ON market_snapshot(symbol, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_decision_symbol_created ON decision_log(symbol, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trade_order_status ON trade_order(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_review_task_due ON review_task(status, due_at);
CREATE INDEX IF NOT EXISTS idx_experience_memory_embedding ON experience_memory USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
