# WF-12: Sharing & Permissions

## Purpose

All user-generated content — conversations, sessions, insights — is private by default. This workflow defines how content is shared, how permissions are enforced, and how the history and search pages in Goldmine surface both personal and shared content.

---

## Goals

- Private by default — no content is visible to other users without an explicit share action
- Simple sharing model — share with a specific person or the whole team
- Shared content is read-only for recipients
- History and search pages surface both personal and shared content clearly distinguished

---

## Privacy Model

| Content type | Default visibility | Can be shared with |
|---|---|---|
| Conversations | Private to creator | Specific user or whole team |
| Sessions | Inherit from conversation | Inherit from conversation |
| Messages | Inherit from conversation | Inherit from conversation |
| Insights | Private to creator | Specific user or whole team |
| Q&A library entries | Team-visible once validated | N/A — library is always team-wide |

The Q&A library is intentionally team-wide. Validated answers are institutional knowledge and should benefit all analysts regardless of who generated them. This is the one exception to the private-by-default rule.

---

## Sharing a Conversation

When an analyst shares a conversation:

1. A record is inserted into `conversation_shares` with `shared_by`, `shared_with` (or `share_with_team = TRUE`)
2. Recipients can view the full conversation thread including all sessions and messages
3. Recipients cannot add messages, edit content, or re-share
4. The original owner can revoke sharing by deleting the share record

**Share with team:** When `share_with_team = TRUE`, the conversation is visible to all users with an active account. This is appropriate for particularly valuable research threads that the whole team should be able to reference.

---

## Sharing an Insight

Insights are discrete saved moments — a single answer or passage. Sharing an insight shares only that excerpt, not the full conversation it came from.

Same mechanics as conversation sharing — specific user or whole team, read-only for recipients.

---

## Row-Level Security in Supabase

Supabase supports row-level security (RLS) policies that enforce privacy at the database level. This means even if the API has a bug, users cannot accidentally access other users' private data.

**Enable RLS on all Mode 2 tables:**
```sql
ALTER TABLE conversations     ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions          ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages          ENABLE ROW LEVEL SECURITY;
ALTER TABLE insights          ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_ticker_lists ENABLE ROW LEVEL SECURITY;
```

**Example RLS policy — conversations:**
```sql
-- Users can see their own conversations
CREATE POLICY "own_conversations" ON conversations
FOR SELECT USING (user_id = auth.uid());

-- Users can see conversations shared with them
CREATE POLICY "shared_conversations" ON conversations
FOR SELECT USING (
    id IN (
        SELECT conversation_id FROM conversation_shares
        WHERE shared_with = auth.uid()
        OR share_with_team = TRUE
    )
);
```

Similar policies apply to sessions, messages (via conversation), and insights.

---

## History Page — What Goldmine Displays

The history page in Goldmine queries two pools of content and displays them in a unified view:

**Personal history:**
```sql
SELECT * FROM conversations
WHERE user_id = auth.uid()
AND is_archived = FALSE
ORDER BY updated_at DESC;
```

**Shared with me:**
```sql
SELECT c.*, cs.shared_by, u.display_name AS shared_by_name
FROM conversations c
JOIN conversation_shares cs ON c.id = cs.conversation_id
JOIN user_profiles u ON cs.shared_by = u.user_id
WHERE cs.shared_with = auth.uid()
OR cs.share_with_team = TRUE
ORDER BY c.updated_at DESC;
```

The UI should visually distinguish personal vs. shared conversations — e.g., a small avatar or "Shared by [name]" label on shared items.

---

## Conversation Search

The search endpoint (defined in DS-03) searches across:
- The user's own message history
- Messages in conversations shared with the user or team-shared

It does not search private conversations belonging to other users under any circumstances. RLS policies enforce this at the database level.

---

## Admin Visibility

Admins (`user_profiles.is_admin = TRUE`) do not automatically see all private conversations. Admin access to content is intentionally not implemented — the platform is a research tool, not a surveillance tool. Admins have access to cost and usage analytics (DS-04) but not to the content of analyst conversations.

---

## Cost Tracking

No API calls are made in this workflow. Sharing and permission enforcement are pure database operations. No cost events are emitted.
