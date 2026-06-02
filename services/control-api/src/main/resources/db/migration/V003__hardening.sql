-- V003: hardening — atomic state machines, idempotency, window resets, lifecycle

-- trade_order references the approval that authorised it (BLOCKER C7)
ALTER TABLE trade_order
  ADD COLUMN IF NOT EXISTS approval_id UUID REFERENCES approval_request(id);

-- trade_position lifecycle: track when we closed it and how
ALTER TABLE trade_position
  ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS close_reason TEXT,
  ADD COLUMN IF NOT EXISTS close_price NUMERIC(30, 12);

-- account_snapshot window markers (so position-keeper knows when to reset daily/weekly pnl)
ALTER TABLE account_snapshot
  ADD COLUMN IF NOT EXISTS daily_window_date DATE,
  ADD COLUMN IF NOT EXISTS weekly_window_start DATE;

UPDATE account_snapshot
  SET daily_window_date = COALESCE(daily_window_date, (created_at AT TIME ZONE 'UTC')::date),
      weekly_window_start = COALESCE(weekly_window_start, date_trunc('week', created_at AT TIME ZONE 'UTC')::date)
  WHERE daily_window_date IS NULL OR weekly_window_start IS NULL;

-- approval_request: only one PENDING per decision (BLOCKER C4)
CREATE UNIQUE INDEX IF NOT EXISTS uq_approval_decision_pending
  ON approval_request (decision_id)
  WHERE status = 'PENDING';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'chk_approval_status'
  ) THEN
    ALTER TABLE approval_request
      ADD CONSTRAINT chk_approval_status
      CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED', 'CANCELLED'));
  END IF;
END$$;

-- decision_log: only one decision per signal (H12)
CREATE UNIQUE INDEX IF NOT EXISTS uq_decision_signal
  ON decision_log (signal_id)
  WHERE signal_id IS NOT NULL;

-- trade_position open-position lookups
CREATE INDEX IF NOT EXISTS idx_trade_position_open_symbol
  ON trade_position (symbol)
  WHERE status = 'OPEN';

-- risk_event type / severity dashboards
CREATE INDEX IF NOT EXISTS idx_risk_event_type_created
  ON risk_event (event_type, created_at DESC);

-- account_snapshot ordering used by RiskService
CREATE INDEX IF NOT EXISTS idx_account_snapshot_created
  ON account_snapshot (created_at DESC);

-- review_task secondary index for due polling
CREATE INDEX IF NOT EXISTS idx_review_task_status_due
  ON review_task (status, due_at);

-- trade_signal: index for new-signal polling
CREATE INDEX IF NOT EXISTS idx_trade_signal_status_created
  ON trade_signal (status, created_at);
