# WF-09: Agentic Response Generation

## Purpose

Response generation uses an agentic tool-calling loop where Claude receives the user question and tool definitions, calls tools as needed to gather data, and then streams the final answer. It enforces sourcing requirements via the system prompt, and streams the response back to GoldMine.

---

## Goals

- Give Claude access to all data sources via GOLDMINE_TOOLS
- Let Claude decide which tools to call based on the question
- Enforce that every factual claim is attributed to a specific source
- Stream the final response to GoldMine as tokens are generated
- Emit full metadata (tools used, models, costs) after streaming completes

---

## Model

Uses the model assigned to `response_generator` in `model_config`. Default: `claude-sonnet-4-6`.

This is the one component where model quality directly affects user experience. Do not substitute Haiku here. Sonnet is appropriate for the complexity of financial synthesis across multiple sources.

---

## System Prompt

The system prompt is loaded from `instructions/domain/WF-09_system_prompt.md` at import time — not assembled dynamically in code. This allows updating behavioral rules without a code change.

The system prompt contains:
- Role and platform context
- Sourcing requirement (non-negotiable) with citation format
- Citation exemptions (portfolio data, stock history)
- No fabrication rule, no hierarchy rule, synthesis boundary
- Read-only constraint
- Source isolation rules (estimates always all four, portfolio tools only for P&L, note type isolation, alt data requires type filter)
- Response format guidance per query type
- Uncertainty handling

When Q&A library hits are found, they are appended to the system prompt as "Prior Validated Answers".

---

## Agentic Tool-Calling Loop

The `generate_response()` function in `generator.py` implements:

```
1. Embed user query once (_embed_query from retrieval.py)
2. Look up Q&A library (_lookup_qa_library)
3. Build messages: system prompt + rolling summary + history + user message
4. Call Claude with GOLDMINE_TOOLS
5. If Claude returns tool_use blocks:
   a. Execute each tool via execute_tool() in tools.py
   b. Feed tool results back to Claude
   c. Repeat from step 4
6. When Claude returns final text response:
   a. Stream token-by-token via SSE
   b. Emit metadata event (tools used, tokens, cost)
   c. Emit done event
7. Persist message to Supabase asynchronously
```

Safety limit: maximum 10 tool-calling iterations per message.

### Cost Warning

If `classified.estimated_ticker_count >= 10` and the first tool call includes `search_documents`, a `cost_warning` event is emitted before tool execution.

---

## SSE Stream Events

| Event type | Content |
|---|---|
| `step` | Pipeline transparency (embedding, Q&A lookup, tool calls) |
| `cost_warning` | Large query warning with ticker count |
| `token` | Streamed response text |
| `metadata` | Tools used, models, token counts, cost, tickers referenced |
| `done` | Stream completion signal |

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
  - source_chunks: JSON list of tools used
  - classifier_model, generator_model: from model_config
  - input_tokens, output_tokens: cumulative across all tool loop iterations
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
- `input_tokens`, `output_tokens`: cumulative across all tool loop iterations
- `session_id`, `message_id`, `user_id`, `query_type`, `ticker_count` all attached

See DS-04 for full cost logging specification.
