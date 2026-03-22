-- 023: Add market_value and portfolio_market_value columns to portfolio_concentration
--
-- market_value: this position's dollar value (shares * close price)
-- portfolio_market_value: total dollar value of all positions in the portfolio on this date
-- These support verifiable market neutrality compliance calculations.

ALTER TABLE portfolio_concentration
  ADD COLUMN IF NOT EXISTS market_value NUMERIC;

ALTER TABLE portfolio_concentration
  ADD COLUMN IF NOT EXISTS portfolio_market_value NUMERIC;
