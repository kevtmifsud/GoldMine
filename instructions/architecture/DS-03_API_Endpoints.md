# DS-03: FastAPI Endpoint Specifications

## Purpose

This document defines all FastAPI endpoints that the Goldmine frontend calls to interact with the Mode 2 backend. This is the complete contract between the two systems. All endpoints are authenticated via Supabase JWT tokens passed in the Authorization header.

---

## Base Configuration

```
Base URL (local dev):   http://localhost:8000
Base URL (production):  TBD when hosted
API prefix:             /api/v1
Authentication:         Bearer {supabase_jwt_token}
Content-Type:           application/json
Streaming:              text/event-stream (SSE) for /chat/message
```

All endpoints except streaming return JSON. All endpoints require authentication. All requests include the user's Supabase JWT which the backend validates and uses to identify the user.

---

## Chat Endpoints

### POST /api/v1/chat/message
Main endpoint. Receives a user message, runs the full Mode 2 pipeline, and streams the response back via Server-Sent Events.

**Slash command interception:** Before entering the pipeline, the endpoint checks if `content` begins with `/request`. If so, the message is intercepted — it is written directly to `feature_requests` and a fixed acknowledgment is returned without any LLM call. No classification, no retrieval, no streaming. See the Feature Requests section below for details.

**Request body:**
```json
{
  "session_id": "uuid",
  "conversation_id": "uuid",
  "content": "What did AAPL say about gross margins last quarter?",
  "context_tickers": ["AAPL"]
}
```

**Response:** SSE stream with the following event types:

```
event: token
data: {"token": "Apple"}

event: token
data: {"token": " reported"}

event: metadata
data: {
  "message_id": "uuid",
  "query_type": "single_ticker_qualitative",
  "tickers_referenced": ["AAPL"],
  "source_chunks": [
    {
      "chunk_id": "uuid",
      "ticker": "AAPL",
      "document_type": "earnings_transcript",
      "fiscal_period": "Q4_2024",
      "section_name": "CFO Prepared Remarks",
      "excerpt": "first 150 chars of chunk..."
    }
  ],
  "classifier_model": "claude-haiku-4-5-20251001",
  "generator_model": "claude-sonnet-4-6",
  "cost_usd": 0.018
}

event: done
data: {}
```

The `metadata` event fires after streaming completes. Goldmine uses it to render citation cards and feedback controls below the response.

---

### POST /api/v1/chat/session
Creates a new session within an existing conversation.

**Request body:**
```json
{
  "conversation_id": "uuid"
}
```

**Response:**
```json
{
  "session_id": "uuid",
  "conversation_id": "uuid",
  "created_at": "2025-01-30T10:00:00Z"
}
```

---

### GET /api/v1/chat/session/{session_id}
Returns full message history for a session. Used when Goldmine needs to restore a session view.

**Response:**
```json
{
  "session_id": "uuid",
  "conversation_id": "uuid",
  "messages": [
    {
      "id": "uuid",
      "role": "user",
      "content": "What did AAPL say about margins?",
      "created_at": "2025-01-30T10:00:00Z"
    },
    {
      "id": "uuid",
      "role": "assistant",
      "content": "In the Q4 2024 earnings call...",
      "source_chunks": [...],
      "query_type": "single_ticker_qualitative",
      "created_at": "2025-01-30T10:00:05Z",
      "feedback": null
    }
  ]
}
```

---

## Feedback Endpoints

### POST /api/v1/messages/{message_id}/feedback
Submits analyst feedback on an assistant message. Triggers Q&A library entry creation for positive feedback.

**Request body:**
```json
{
  "feedback_type": "thumbs_up",
  "edited_content": null
}
```

For `feedback_type: "edited"`, `edited_content` must be provided with the corrected answer text.

**Response:**
```json
{
  "feedback_id": "uuid",
  "qa_library_entry_created": true
}
```

---

## Conversation Endpoints

### GET /api/v1/conversations
Returns the current user's conversation list for the history page.

**Query params:** `?limit=20&offset=0&ticker={ticker}&search={text}`

**Response:**
```json
{
  "conversations": [
    {
      "id": "uuid",
      "title": "AAPL Margin Analysis",
      "ticker_context": "AAPL",
      "session_count": 3,
      "last_active": "2025-01-30T10:00:00Z",
      "is_shared": false
    }
  ],
  "total": 47
}
```

---

### POST /api/v1/conversations
Creates a new conversation.

**Request body:**
```json
{
  "title": "AAPL Q4 Deep Dive",
  "ticker_context": "AAPL"
}
```

---

### POST /api/v1/conversations/{conversation_id}/share
Shares a conversation with a team member or the whole team.

**Request body:**
```json
{
  "share_with_user_id": "uuid",
  "share_with_team": false
}
```

---

### GET /api/v1/conversations/search
Semantic search across the user's conversation history and team-shared conversations.

**Query params:** `?q=AAPL+margin+guidance&limit=10`

**Response:**
```json
{
  "results": [
    {
      "message_id": "uuid",
      "conversation_id": "uuid",
      "conversation_title": "AAPL Q4 Deep Dive",
      "excerpt": "Apple's CFO guided for gross margins of...",
      "similarity_score": 0.91,
      "created_at": "2025-01-30T10:00:00Z",
      "shared_by": null
    }
  ]
}
```

---

## Insights Endpoints

### GET /api/v1/insights
Returns the user's saved insights plus insights shared with them.

**Query params:** `?ticker={ticker}&tag={tag}&limit=20&offset=0`

---

### POST /api/v1/insights
Saves an insight from a session.

**Request body:**
```json
{
  "message_id": "uuid",
  "session_id": "uuid",
  "title": "AAPL margin headwinds Q4",
  "content": "Management flagged FX headwinds as primary driver...",
  "ticker_context": "AAPL",
  "tags": ["margins", "FX", "Q4_2024"]
}
```

---

### POST /api/v1/insights/{insight_id}/share
Shares an insight.

**Request body:**
```json
{
  "share_with_user_id": "uuid",
  "share_with_team": false
}
```

---

## Ticker List Endpoints

### GET /api/v1/lists
Returns all of the user's ticker lists.

**Response:**
```json
{
  "lists": [
    {
      "list_name": "Semiconductor Names",
      "tickers": ["NVDA", "AMD", "INTC", "TSM"],
      "ticker_count": 4
    },
    {
      "list_name": "Farm System",
      "tickers": ["PLTR", "SNOW", "MDB"],
      "ticker_count": 3
    }
  ]
}
```

---

### POST /api/v1/lists
Creates or updates a ticker list. Replaces all tickers for the given list_name if it already exists.

**Request body:**
```json
{
  "list_name": "Semiconductor Names",
  "tickers": ["NVDA", "AMD", "INTC", "TSM", "QCOM"]
}
```

---

### DELETE /api/v1/lists/{list_name}
Deletes a list and all its ticker entries.

---

## Feature Requests

### Slash Command Interception (within POST /api/v1/chat/message)

When `content` starts with `/request`, the message is intercepted before the pipeline runs:

1. Strip the `/request` prefix and trim whitespace from the remaining text
2. Write a record to `feature_requests` with `user_id`, `session_id`, and `request_text`
3. Return a non-streaming JSON acknowledgment immediately — no LLM call is made

**Acknowledgment response:**
```json
{
  "type": "feature_request_received",
  "message": "Your feature request has been logged and will be reviewed. Thank you.",
  "request_id": "uuid"
}
```

Goldmine renders this acknowledgment inline in the chat thread like a normal assistant message, visually distinguishable (e.g., a small tag reading "Feature Request Logged").

---

### GET /api/v1/admin/feature-requests
Returns all submitted feature requests. Admin only.

**Query params:** `?status=submitted|reviewing|planned|declined|completed&limit=50&offset=0`

**Response:**
```json
{
  "requests": [
    {
      "id": "uuid",
      "user": {"user_id": "uuid", "display_name": "Jane Smith"},
      "request_text": "can we add sellside research as a datasource",
      "status": "submitted",
      "priority": null,
      "admin_notes": null,
      "created_at": "2025-01-30T10:00:00Z"
    }
  ],
  "total": 14
}
```

---

### PATCH /api/v1/admin/feature-requests/{request_id}
Updates status, priority, and admin notes on a feature request. Admin only.

**Request body:**
```json
{
  "status": "planned",
  "priority": "high",
  "admin_notes": "Sellside research datasource — scheduled for Q2 build."
}
```

---

## Issues & Bug Reports

### GET /api/v1/admin/issues
Returns all flagged messages with issue details for triage. Admin only.

**Query params:** `?status=open|triaging|resolved&priority=low|medium|high&limit=50&offset=0`

**Response:**
```json
{
  "issues": [
    {
      "feedback_id": "uuid",
      "reported_by": {"user_id": "uuid", "display_name": "Jane Smith"},
      "reported_at": "2025-01-30T10:05:00Z",
      "priority": "high",
      "issue_status": "open",
      "issue_notes": "The margin figure cited was incorrect — it quoted Q3 not Q4",
      "message": {
        "message_id": "uuid",
        "content": "Apple's gross margin in Q4 2024 was 45.9%...",
        "query_type": "single_ticker_qualitative",
        "tickers_referenced": ["AAPL"],
        "source_chunks": [...],
        "generator_model": "claude-sonnet-4-6",
        "created_at": "2025-01-30T10:00:00Z"
      }
    }
  ],
  "total": 3
}
```

The full `source_chunks` array is included so the technical lead can immediately see which document chunks were retrieved and diagnose what went wrong.

---

### PATCH /api/v1/admin/issues/{feedback_id}
Updates issue status and adds resolution notes. Admin only.

**Request body:**
```json
{
  "issue_status": "resolved",
  "resolution_notes": "Confirmed chunking error — Q3 and Q4 CFO remarks were merged into one chunk. Re-chunked AAPL Q4 2024 transcript."
}
```

Sets `resolved_by` to the admin's user_id and `resolved_at` to NOW() automatically.

---

## Cost & Admin Endpoints

### GET /api/v1/admin/costs/summary
Returns cost summary. Admin only.

**Query params:** `?from=2025-01-01&to=2025-01-31&group_by=user|query_type|model|component`

**Response:**
```json
{
  "total_cost_usd": 142.83,
  "period": {"from": "2025-01-01", "to": "2025-01-31"},
  "breakdown": [
    {"dimension": "user_id", "value": "uuid", "cost_usd": 28.40, "query_count": 312},
    {"dimension": "user_id", "value": "uuid", "cost_usd": 22.15, "query_count": 241}
  ]
}
```

---

### GET /api/v1/admin/models
Returns current model configuration for all components.

---

### PUT /api/v1/admin/models/{component}
Updates the model assignment for a component. Admin only.

**Request body:**
```json
{
  "model": "claude-new-model-identifier",
  "provider": "anthropic"
}
```

This triggers the SQL update pattern defined in DS-02.

---

## Error Response Format

All errors return a consistent structure:

```json
{
  "error": {
    "code": "RETRIEVAL_FAILED",
    "message": "Vector search returned no results for the given filters",
    "details": {}
  }
}
```

Standard HTTP status codes apply: 400 bad request, 401 unauthorized, 403 forbidden, 404 not found, 500 internal server error.
