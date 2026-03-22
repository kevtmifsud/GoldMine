-- 025: Add visibility and title columns to sessions table,
-- drop unused chat_sessions table.
--
-- sessions is the canonical session store. chat_sessions was
-- created in error during domain table migrations and has zero rows.

ALTER TABLE sessions
  ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'private';

ALTER TABLE sessions
  ADD COLUMN IF NOT EXISTS title TEXT;

CREATE INDEX IF NOT EXISTS idx_sessions_visibility ON sessions(visibility);

-- Drop unused chat_sessions table (zero rows, duplicates sessions)
DROP TABLE IF EXISTS chat_sessions;
