-- 024: Add daily_realized_pnl, ytd_pnl, itd_pnl columns to daily_pnl
--
-- daily_realized_pnl: P&L from positions closed on THIS date only (not cumulative)
-- ytd_pnl: year-to-date total P&L from Jan 1 (unrealized change + realized)
-- itd_pnl: inception-to-date total P&L since first trade ever

ALTER TABLE daily_pnl
  ADD COLUMN IF NOT EXISTS daily_realized_pnl NUMERIC;

ALTER TABLE daily_pnl
  ADD COLUMN IF NOT EXISTS ytd_pnl NUMERIC;

ALTER TABLE daily_pnl
  ADD COLUMN IF NOT EXISTS itd_pnl NUMERIC;
