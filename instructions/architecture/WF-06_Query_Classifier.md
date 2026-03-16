# WF-06: Query Classifier

## Purpose

The query classifier is the first step in every Mode 2 user message. It takes the raw user input and produces a structured representation of what the user is asking — query type, tickers involved, time periods, topic, and what data sources are needed. Everything downstream depends on the classifier output being accurate.

---

## Goals

- Classify every user message into one of five query types
- Extract or resolve tickers, time periods, and topic from the message
- Determine whether structured data, vector search, or both are needed
- Complete in under one second — this is a fast, cheap call that must not add perceptible latency

---

## Model

Uses the model assigned to `query_classifier` in `model_config`. Default: `claude-haiku-4-5-20251001`.

Haiku is appropriate here — the classification task is well-defined structured extraction, not open-ended reasoning. Sonnet is not needed and would add unnecessary cost on every single user message.

---

## Input

The classifier receives:

- The user's current message
- The last 2 turns of session history (for context on follow-up questions)
- The list of valid ticker symbols and user's named lists (for ticker resolution)

---

## Output — ClassifiedQuery Pydantic Model

```python
class ClassifiedQuery(BaseModel):
    query_type: Literal[
        "single_ticker_qualitative",
        "single_ticker_quantitative",
        "cross_ticker",
        "screening",
        "trend_analysis"
    ]
    tickers: list[str]
    list_references: list[str]
    fiscal_periods: list[str]
    topic: str
    needs_structured_data: bool
    needs_vector_search: bool
    section_type_hint: str | None
    time_range_quarters: int | None
```

---

## Query Type Definitions

| Query type | Definition | Example |
|---|---|---|
| `single_ticker_qualitative` | One ticker, qualitative question answered from transcript chunks | "What did AAPL say about margins last quarter?" |
| `single_ticker_quantitative` | One ticker, numerical question answered from structured tables | "What was AAPL's gross margin in Q3 2024?" |
| `cross_ticker` | Multiple tickers, comparison or aggregation | "Compare guidance tone across my semiconductor names" |
| `screening` | Broad universe, filter by criteria | "Which tickers flagged new supply chain risks this quarter?" |
| `trend_analysis` | One ticker, multiple time periods | "How has AAPL's China commentary changed over 8 quarters?" |

---

## Classifier Prompt Design

The classifier is called with a structured system prompt that:

1. Defines each query type with examples
2. Specifies the exact JSON output format matching the Pydantic model
3. Instructs the model to infer fiscal periods from natural language ("last quarter" → current period - 1)
4. Lists the user's named ticker lists so references can be identified
5. Instructs the model to set `section_type_hint` when the topic maps clearly to a known section type (e.g., "risk factors" → `risk_factors`, "guidance" → `cfo_remarks`)

The prompt must instruct Claude to return **only valid JSON** with no preamble or explanation. The response is parsed directly into the Pydantic model.

---

## Handling Follow-Up Questions

Follow-up questions often omit context that was established earlier in the session. The classifier must handle this:

- "How does that compare to last quarter?" — no ticker mentioned, must infer from prior turn
- "What about MSFT?" — query type and topic carried forward from prior turn

Passing the last 2 turns of session history to the classifier gives it enough context to resolve these references correctly without sending the full session history (which would add tokens and latency).

---

## Ticker Resolution

The classifier identifies ticker references but does not expand named lists. List expansion happens in WF-07 as a separate step. The classifier's output for list references:

```json
{
  "tickers": [],
  "list_references": ["Semiconductor Names"]
}
```

WF-07 then resolves "Semiconductor Names" to `["NVDA", "AMD", "INTC", "TSM"]` via Supabase lookup.

---

## Fiscal Period Inference

The classifier infers fiscal periods from natural language using knowledge of the current date:

| User says | Classifier infers |
|---|---|
| "last quarter" | Current quarter - 1 |
| "this year" | Current fiscal year |
| "the last 8 quarters" | Last 8 quarterly periods (sets `time_range_quarters: 8`) |
| "Q4 2024" | `["Q4_2024"]` |
| "recent" | Last 1-2 periods |
| No time reference | Empty list — retrieval will not filter by period |

The current date is injected into the classifier prompt so period inference is always accurate.

---

## Fallback Handling

If the classifier returns malformed JSON or the Pydantic model fails to parse:

1. Log the failure with the raw response
2. Fall back to a safe default: `query_type = "single_ticker_qualitative"`, extract any ticker mentioned, no period filter
3. Proceed with the safe default — never block the user with a classifier error

Classifier failures should be monitored in the cost events log and reviewed periodically to improve the prompt if a pattern emerges.

---

## Cost Tracking

Emits one cost event to `api_cost_events` per user message:

- `component`: `query_classifier`
- `mode`: `mode_2`
- `model`: from `model_config`
- `session_id`, `message_id`, `user_id` attached
- `query_type` populated after successful classification

See DS-04 for full cost logging specification.
