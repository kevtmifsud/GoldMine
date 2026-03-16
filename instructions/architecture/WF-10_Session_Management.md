# WF-10: Session & Conversation Management

## Purpose

Session management maintains conversational coherence across multiple turns without allowing context to grow unboundedly. It controls what history Claude sees on each turn, compresses old history into rolling summaries, and manages the full conversation lifecycle in Supabase.

---

## Goals

- Provide Claude with enough history to answer follow-up questions coherently
- Prevent token costs from growing with every turn
- Store complete session history permanently in Supabase for history and search
- Never block a user-facing response with compression work

---

## Session Lifecycle

```
User opens Goldmine page → new session created in Supabase
User sends messages → turns accumulate in messages table
User navigates away → session remains in Supabase, UI clears
User returns to history page → session retrieved and displayed
```

A session belongs to a conversation. A conversation is the top-level research thread (e.g., "AAPL Q4 Analysis"). Multiple sessions can exist within one conversation — each page load or fresh chat interaction creates a new session.

---

## Context Assembly Per Turn

On every new user message, the following history is assembled for Claude:

**If session has fewer than 10 turns:**
Send all prior turns verbatim. No compression needed yet.

**If session has 10 or more turns:**
Send rolling summary + last 4 turns verbatim.

```
[Rolling summary covers turns 1 through N-4]
[Turn N-3: user question + assistant response verbatim]
[Turn N-2: user question + assistant response verbatim]
[Turn N-1: user question + assistant response verbatim]
[Turn N: current user question]
```

This keeps the history context to approximately 1,100 tokens regardless of how long the session runs.

---

## Rolling Summary Compression

Compression is triggered when `turn_count` crosses a multiple of 10 (turn 10, 20, 30, etc.). It runs **asynchronously after the response has streamed to the user** — it never adds latency to the active turn.

**Compression process:**
1. Retrieve all turns not yet covered by the rolling summary (turns from `summary_covers_through + 1` to `turn_count - 4`)
2. Call Claude Haiku with a prompt asking for a concise summary of key facts established:
   - Tickers discussed and key figures mentioned
   - Questions asked and conclusions reached
   - Any follow-up threads the user indicated interest in
3. Update `sessions.rolling_summary` with the new summary
4. Update `sessions.summary_covers_through` to `turn_count - 4`

**Compression prompt instruction:**
The summary should preserve specific numbers, ticker names, and conclusions — not just themes. "AAPL gross margin was 46.2% in Q4 2024, below analyst expectations" is useful. "The user asked about margins" is not.

---

## Token Budget Enforcement

Beyond the turn-based rule, enforce a hard token budget on the history portion of the context. If the last 4 turns verbatim exceed 1,100 tokens, trim the oldest of the 4 turns until within budget. Never trim the most recent turn.

This handles cases where individual turns are unusually long (e.g., a complex cross-ticker comparison response).

---

## Conversation Management

**Creating a conversation:**
When a user starts a new research thread, a conversation record is created with an optional title and ticker context. The first session is created simultaneously.

**Auto-titling:**
If the user does not provide a title, generate one automatically after the first assistant response. Use Haiku to produce a 4-6 word title summarizing the first exchange. Store it on the conversation record. This makes the history page scannable without requiring user effort.

**Archiving:**
Users can archive conversations they no longer need active. Archived conversations are hidden from the default history view but remain searchable and fully retrievable.

---

## History Search

The history search endpoint (defined in DS-03) enables semantic search across a user's prior conversations and team-shared conversations.

**Implementation:**
- On each assistant message, generate and store an embedding of the question using the `query_embedder` model
- Store this embedding on the messages table (add `content_embedding vector(1536)` column)
- History search performs a pgvector search on `messages.content_embedding` filtered to the user's accessible conversations
- Return matching messages with their conversation context

This gives analysts a powerful way to surface prior research — "find all the times I asked about supply chain risk" — without requiring exact keyword matches.

---

## Cost Tracking

Emits cost events for:

- `session_compressor` — one Haiku call per compression event (every 10 turns)
- `query_embedder` — one embedding call per assistant message stored (for history search)

Auto-titling uses `session_compressor` model and emits a cost event.

See DS-04 for full cost logging specification.
