-- 029_add_analyst_columns_to_buyside_estimates.sql
-- Add analyst attribution columns to buyside_estimates log table.
-- Also update daily_estimates unique constraint to include analyst_name.

ALTER TABLE buyside_estimates
  ADD COLUMN IF NOT EXISTS analyst_name TEXT;

ALTER TABLE buyside_estimates
  ADD COLUMN IF NOT EXISTS analyst_person_id VARCHAR
    REFERENCES people(person_id);

-- Update daily_estimates unique constraint to support per-analyst rows.
-- The old constraint was (ticker, metric, period, source, firm, as_of_date).
-- We need to include analyst_name to allow multiple analysts per firm.
-- First make analyst_name default to empty string for constraint purposes.
ALTER TABLE daily_estimates
  ALTER COLUMN analyst_name SET DEFAULT '';

-- Drop old constraint and create new one including analyst_name
ALTER TABLE daily_estimates
  DROP CONSTRAINT IF EXISTS daily_estimates_ticker_metric_period_source_firm_as_of_date_key;

-- Backfill existing NULLs to empty string for constraint
UPDATE daily_estimates SET analyst_name = '' WHERE analyst_name IS NULL;
UPDATE daily_estimates SET firm = '' WHERE firm IS NULL;

-- Make columns NOT NULL with defaults for constraint
ALTER TABLE daily_estimates
  ALTER COLUMN analyst_name SET NOT NULL;

ALTER TABLE daily_estimates
  ALTER COLUMN firm SET NOT NULL;

ALTER TABLE daily_estimates
  ADD CONSTRAINT daily_estimates_unique_key
  UNIQUE (ticker, metric, period, source, firm, analyst_name, as_of_date);
