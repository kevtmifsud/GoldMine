-- 020: Add shares_held, market_value, cost_basis to daily_pnl
-- These three columns make daily_pnl self-contained for position queries,
-- comparison charts, and report rendering without replaying trades or
-- joining stock_history at query time.

ALTER TABLE daily_pnl ADD COLUMN IF NOT EXISTS shares_held NUMERIC;
ALTER TABLE daily_pnl ADD COLUMN IF NOT EXISTS market_value NUMERIC;
ALTER TABLE daily_pnl ADD COLUMN IF NOT EXISTS cost_basis NUMERIC;

CREATE INDEX IF NOT EXISTS idx_daily_pnl_ticker_date
    ON daily_pnl (ticker, date DESC);
CREATE INDEX IF NOT EXISTS idx_daily_pnl_portfolio_date
    ON daily_pnl (portfolio, date DESC);
