# WF-08: Retrieval — Tool Handlers

## Purpose

WF-08 provides the data retrieval functions that the agentic response generator (WF-09) calls via tool use. There is no standalone orchestrator — Claude decides which tools to call and in what order during the agentic loop in `generator.py`.

The `_query_*` functions in `retrieval.py` are the tool handlers. They are called by `execute_tool()` in `tools.py`, which routes each tool call to the correct function.

---

## Architecture

```
generator.py (WF-09 agentic loop)
    ↓
Claude returns tool_use blocks (e.g. search_documents, get_financial_metrics)
    ↓
execute_tool() in tools.py — dispatches to the correct _query_* function
    ↓
_query_* functions in retrieval.py — run SQL or pgvector queries against Supabase
    ↓
Results returned to Claude as tool_result blocks
    ↓
Claude calls more tools or produces final text response
```

---

## Functions in retrieval.py

### Always run at the start (by generator.py, not by tool calls)

- `_embed_query()` — Embeds the user query using OpenAI text-embedding-3-large (1536 dims). Called once at the start of the agentic loop. The embedding is passed to `execute_tool()` for `search_documents` calls.
- `_lookup_qa_library()` — Searches `qa_library` via pgvector cosine similarity (threshold 0.88, top 2). Results are appended to the system prompt.

### Vector search

- `_vector_search()` — pgvector cosine similarity on `chunks` table. Supports filters: `tickers`, `doc_types`, `section_type`, `fiscal_periods`, `limit_per_ticker`. Called by the `search_documents` tool.

### SQL query functions (one per data source)

| Function | Tool | Table(s) |
|---|---|---|
| `_structured_query()` | `get_financial_metrics` | `financial_metrics` |
| `_query_estimates()` | `get_all_estimates` | All 4 estimate tables in parallel |
| `_query_daily_pnl()` | `get_daily_pnl` | `daily_pnl` |
| `_query_portfolio_concentration()` | `get_portfolio_concentration` | `portfolio_concentration` |
| `_query_portfolio_risk()` | `get_portfolio_risk` | `portfolio_risk` |
| `_query_trade_requests()` | `get_trade_requests` | `trade_requests` |
| `_query_stock_history()` | `get_stock_history` | `stock_history` |
| `_query_guidance()` | `get_guidance` | `guidance` |
| `_query_alt_data()` | `get_alt_data` | `alt_data` |
| `_query_model_outputs()` | `get_model_outputs` | `model_outputs` |
| `_query_workflow_registry()` | `get_workflow_registry` | `workflow_registry` |

### Screening support

- `_screening_prefilter()` — Uses Haiku to pre-filter large chunk sets (>20) down to the top 20 most relevant. Still available for screening queries.
- `_check_screening_cache()` / `_write_screening_cache()` — MD5-based cache with 24h TTL for screening results.

### Utility

- `_estimate_tokens()` — Rough token estimate from chunks and structured data. Retained for cost estimation.

---

## Cost Tracking

Emits cost events for:
- `query_embedder` — one embedding call per user message (all query types)
- `screening_prefilter` — one Haiku call for screening queries only

The pgvector searches themselves are free Supabase operations and do not emit cost events.

See DS-04 for full cost logging specification.
