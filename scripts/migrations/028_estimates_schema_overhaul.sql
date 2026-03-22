-- 028_estimates_schema_overhaul.sql
-- Adds sector_coverage to people, renames estimate date columns,
-- and creates daily_estimates table.

-- Step 1: Add sector_coverage to people
ALTER TABLE people
  ADD COLUMN IF NOT EXISTS sector_coverage TEXT[] DEFAULT '{}';

-- Step 2: Rename estimate date columns for consistency
ALTER TABLE consensus_estimates
  RENAME COLUMN as_of_date TO estimate_date;

ALTER TABLE buyside_estimates
  RENAME COLUMN as_of_date TO estimate_date;

ALTER TABLE sellside_estimates
  RENAME COLUMN published_date TO estimate_date;

ALTER TABLE internal_estimates
  ADD COLUMN IF NOT EXISTS estimate_date DATE;

UPDATE internal_estimates
SET estimate_date = created_at::date
WHERE estimate_date IS NULL;

-- Step 3: Create daily_estimates table
CREATE TABLE IF NOT EXISTS daily_estimates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker TEXT NOT NULL,
  metric TEXT NOT NULL,
  period TEXT NOT NULL,
  period_start_date DATE NOT NULL,
  period_end_date DATE NOT NULL,
  source TEXT NOT NULL
    CHECK (source IN ('consensus','buyside','internal','sellside')),
  firm TEXT,
  analyst_name TEXT,
  analyst_person_id VARCHAR REFERENCES people(person_id),
  user_id UUID,
  value NUMERIC NOT NULL,
  unit TEXT,
  estimate_date DATE NOT NULL,
  as_of_date DATE NOT NULL,
  staleness_days INTEGER GENERATED ALWAYS AS (as_of_date - estimate_date) STORED,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (ticker, metric, period, source, firm, as_of_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_estimates_ticker_period
  ON daily_estimates(ticker, period);

CREATE INDEX IF NOT EXISTS idx_daily_estimates_as_of_date
  ON daily_estimates(as_of_date DESC);

CREATE INDEX IF NOT EXISTS idx_daily_estimates_source
  ON daily_estimates(source);

CREATE INDEX IF NOT EXISTS idx_daily_estimates_lookup
  ON daily_estimates(ticker, metric, period, source, as_of_date DESC);

CREATE INDEX IF NOT EXISTS idx_daily_estimates_firm
  ON daily_estimates(firm) WHERE firm IS NOT NULL;
