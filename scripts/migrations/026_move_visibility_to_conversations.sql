-- 026: Move visibility from sessions to conversations.
-- Conversations are the shareable unit — visibility belongs there.

-- Add visibility to conversations
ALTER TABLE conversations
  ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'private';

-- Add indexes
CREATE INDEX IF NOT EXISTS idx_conversations_visibility ON conversations(visibility);
CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);

-- Migrate existing values: take most permissive per conversation
UPDATE conversations c
SET visibility = COALESCE(s.most_permissive, 'private')
FROM (
  SELECT conversation_id, MAX(visibility) as most_permissive
  FROM sessions
  WHERE visibility IS NOT NULL
  GROUP BY conversation_id
) s
WHERE s.conversation_id = c.id;

-- Remove visibility from sessions (it belongs on conversations)
ALTER TABLE sessions DROP COLUMN IF EXISTS visibility;
