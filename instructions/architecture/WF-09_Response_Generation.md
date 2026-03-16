# WF-09: Response Generation

## Purpose

Response generation assembles all retrieved context into a prompt and calls Claude to produce the final user-facing answer. It enforces sourcing requirements, manages the token budget, selects the appropriate response format for the query type, and streams the response back to Goldmine.

---

## Goals

- Assemble context within a defined token budget
- Enforce that every factual claim is attributed to a specific source
- Select the appropriate response format per query type
- Stream the response to Goldmine as tokens are generated
- Emit full metadata (sources, models, costs) after streaming completes

---

## Model

Uses the model assigned to `response_generator` in `model_config`. Default: `claude-sonnet-4-6`.

This is the one component where model quality directly affects user experience. Do not substitute Haiku here. Sonnet is appropriate for the complexity of financial synthesis across multiple sources.

---

## Token Budget

The context passed to Claude must stay within a defined budget to keep costs predictable. Target budget per call:

| Context component | Token allocation |
|---|---|
| System prompt + instructions | ~500 |
| Session history (summary + last 4 turns) | ~1,100 |
| Retrieved chunks | ~2,400 |
| Q&A library hits (up to 2) | ~600 |
| Structured data results | ~400 |
| User question | ~100 |
| **Total input budget** | **~5,100** |

If retrieved chunks exceed the allocation, trim from lowest similarity score first — never trim the highest-ranked chunks.

---

## System Prompt Structure

The system prompt is assembled dynamically for each call. It contains:

**1. Role and platform context**
```
You are a financial research assistant for a professional investment team.
You are analyzing financial documents and data for portfolio managers and analysts.
Always maintain the precision and rigor expected of institutional financial analysis.
```

**2. Sourcing requirement (non-negotiable)**
```
Every factual claim, figure, or quote in your response MUST be attributed to its source.
Cite sources inline using this format: [TICKER | DOCUMENT_TYPE | PERIOD | SECTION]
Example: [AAPL | Earnings Transcript | Q4 2024 | CFO Remarks]
If you cannot attribute a claim to a provided source, do not make the claim.
Do not use prior knowledge about companies — rely only on the provided context.
```

**3. Response format instruction (varies by query type)**
See response format section below.

**4. Q&A library instruction (when hits exist)**
```
Prior validated answers to similar questions are provided below.
Reference these where relevant but do not simply repeat them.
If the prior answer conflicts with the current source documents, note the discrepancy.
```

**5. Retrieved context**
Structured data results first (if any), then chunks in order of relevance, then Q&A library hits.

---

## Response Format by Query Type

| Query type | Format instruction |
|---|---|
| `single_ticker_qualitative` | Narrative prose with inline citations. Concise — answer the question directly, do not pad. |
| `single_ticker_quantitative` | Lead with the exact figure and period. Follow with one sentence of context if relevant. Citation required on the figure. |
| `cross_ticker` | Structured comparison. Use a consistent format per ticker (e.g., one paragraph each, or a summary table followed by detail). Order tickers by relevance to the question. |
| `screening` | Ranked list of tickers that match the criteria. For each: ticker, brief evidence quote with citation, why it matches. Tickers that do not match should not appear. |
| `trend_analysis` | Chronological narrative. Describe the evolution across periods. Use citations anchored to specific periods. Conclude with a summary of direction and magnitude of change. |

---

## Streaming Implementation

The FastAPI endpoint uses `StreamingResponse` with `text/event-stream` content type. Claude's API supports streaming natively.

**Stream sequence:**
1. Token events fire as Claude generates text — Goldmine renders these progressively
2. After Claude completes, a single `metadata` event fires containing:
   - Full source chunk references (for citation rendering)
   - Message ID (for feedback controls)
   - Models used (classifier + generator)
   - Token counts and cost estimate
3. A `done` event signals stream completion

The metadata event is assembled from information already available at generation time — no additional API calls are needed after Claude finishes.

---

## Handling Cache Hits

When WF-08 returns `cache_hit: true` (screening queries only), skip Claude entirely. Format the cached result for streaming and emit it as a single token event followed immediately by the metadata event. This is near-instantaneous and costs nothing.

---

## Saving the Message

After streaming completes, persist to Supabase asynchronously (non-blocking):

```
INSERT INTO messages:
  - session_id, user_id
  - role: 'assistant'
  - content: full response text
  - query_type: from classifier
  - tickers_referenced: from resolved universe
  - source_chunks: JSONB array of chunk metadata used
  - qa_library_hits: JSONB array of library entries surfaced
  - classifier_model: from model_config at call time
  - generator_model: from model_config at call time
  - input_tokens, output_tokens: from Claude API response
  - cost_usd: calculated from api_pricing
```

Also update the parent session record: increment `turn_count`, add to `total_cost_usd`.

---

## Automatic Q&A Library Candidacy

Every assistant message is automatically a candidate for the Q&A library — it does not need to wait for feedback to be stored as a candidate. The message is stored in `messages` immediately. When feedback arrives (WF-11), it triggers promotion to `qa_library` with the appropriate validation type and weight.

---

## Cost Tracking

Emits one cost event to `api_cost_events` per response generated:

- `component`: `response_generator`
- `mode`: `mode_2`
- `model`: from `model_config` at call time
- `input_tokens`, `output_tokens`: from Claude API response
- `session_id`, `message_id`, `user_id`, `query_type`, `ticker_count` all attached

See DS-04 for full cost logging specification.
