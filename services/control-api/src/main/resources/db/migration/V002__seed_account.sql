INSERT INTO account_snapshot (mode, equity_usd, available_usd, raw)
SELECT 'PAPER_ONLY', 1000, 1000, '{"seed": true}'::jsonb
WHERE NOT EXISTS (SELECT 1 FROM account_snapshot);
