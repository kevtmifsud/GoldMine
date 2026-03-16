# DS-04: Cost Management & Model Versioning

## Purpose

This document defines the cost tracking architecture and model versioning system that spans both Mode 1 and Mode 2. The goal is to know exactly what every API call costs, which model ran it, who or what triggered it, and to be able to swap models across the platform without code changes.

---

## Design Principles

**Non-blocking:** Cost logging never adds latency to user-facing responses. All cost events are written asynchronously after the API call completes.

**Complete:** Every LLM and embedding API call anywhere in the system emits a cost event. No call goes unlogged.

**Model-aware:** Every cost event records the exact model used. Historical records are never updated when models change — they permanently reflect what ran at the time.

**Config-driven:** Model selection is driven by the `model_config` table in Supabase. No model names are hardcoded in application code. Swapping a model requires updating one database row.

---

## The Two Tables (Defined in DS-02)

**`api_cost_events`** — append-only log of every API call. Never updated, never deleted.

**`model_config`** — current model assignment per component. One row per component, updated in place when switching models.

**`api_pricing`** — current and historical pricing per model. Used to calculate cost at log time.

---

## Components That Log Cost Events

Every component below emits one cost event per API call.

| Component | Mode | Model tier | What triggers it |
|---|---|---|---|
| `document_classifier` | Mode 1 | Haiku | LLM fallback classification in WF-02 |
| `document_embedder` | Mode 1 | Embedding | Every chunk embedded in WF-04 |
| `query_classifier` | Mode 2 | Haiku | Every user message in WF-06 |
| `query_embedder` | Mode 2 | Embedding | Every user message vector search |
| `qa_library_embedder` | Mode 2 | Embedding | Every Q&A library entry created |
| `screening_prefilter` | Mode 2 | Haiku | Screening queries only in WF-08 |
| `response_generator` | Mode 2 | Sonnet | Every assistant response in WF-09 |
| `session_compressor` | Mode 2 | Haiku | Session compression in WF-10 |

---

## How Model Selection Works at Runtime

Every component that calls an LLM or embedding API follows this pattern at runtime:

```
1. Query model_config WHERE component = '{component_name}'
2. Use the returned model value in the API call
3. After API call completes, log cost event with:
   - The exact model used (from model_config at call time)
   - Token counts from the API response
   - Cost calculated from api_pricing WHERE model = '{model}' AND is_current = TRUE
```

This means if a model is switched mid-day, calls before the switch log the old model and calls after log the new model. The historical record is always accurate.

---

## Cost Calculation

Cost is calculated at log time using current pricing from the `api_pricing` table:

```
cost_usd = (input_tokens  / 1,000,000 × input_per_1m)
         + (output_tokens / 1,000,000 × output_per_1m)
```

For embedding models, `output_per_1m` is NULL — only input tokens are billed.

---

## Switching Models

When a new model is released and you want to adopt it for a component:

**Step 1 — Add new model to api_pricing:**
```sql
-- Retire old model pricing
UPDATE api_pricing
SET is_current = FALSE, effective_to = CURRENT_DATE
WHERE model = 'claude-sonnet-4-6' AND is_current = TRUE;

-- Add new model pricing
INSERT INTO api_pricing (model, provider, input_per_1m, output_per_1m, effective_from, is_current)
VALUES ('claude-new-model-id', 'anthropic', X.XX, X.XX, CURRENT_DATE, TRUE);
```

**Step 2 — Update model_config:**
```sql
UPDATE model_config
SET
    previous_model  = model,
    switched_at     = NOW(),
    model           = 'claude-new-model-id',
    updated_at      = NOW()
WHERE component = 'response_generator';
```

That is the entire switch. No code changes. No redeployment. The platform picks up the new model on the next API call to that component.

**Step 3 — Verify in cost events:**
After a few queries, confirm the new model is being logged correctly:
```sql
SELECT model, COUNT(*), SUM(cost_usd)
FROM api_cost_events
WHERE component = 'response_generator'
AND created_at > NOW() - INTERVAL '1 hour'
GROUP BY model;
```

---

## Cost Monitoring Queries

These queries can be run directly in the Supabase SQL Editor or surfaced in a Goldmine admin dashboard.

**Daily cost by mode:**
```sql
SELECT
    DATE(created_at) AS date,
    mode,
    SUM(cost_usd) AS total_cost,
    COUNT(*) AS api_calls
FROM api_cost_events
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY DATE(created_at), mode
ORDER BY date DESC;
```

**Cost by user this month:**
```sql
SELECT
    u.display_name,
    COUNT(*) AS queries,
    SUM(e.cost_usd) AS total_cost,
    AVG(e.cost_usd) AS avg_cost_per_query
FROM api_cost_events e
JOIN user_profiles u ON e.user_id = u.user_id
WHERE e.mode = 'mode_2'
AND e.component = 'response_generator'
AND e.created_at >= DATE_TRUNC('month', NOW())
GROUP BY u.display_name
ORDER BY total_cost DESC;
```

**Cost by query type:**
```sql
SELECT
    query_type,
    COUNT(*) AS count,
    SUM(cost_usd) AS total_cost,
    AVG(cost_usd) AS avg_cost,
    MAX(cost_usd) AS max_cost
FROM api_cost_events
WHERE mode = 'mode_2'
AND component = 'response_generator'
AND created_at >= DATE_TRUNC('month', NOW())
GROUP BY query_type
ORDER BY total_cost DESC;
```

**Cost by model (tracks impact of model switches):**
```sql
SELECT
    model,
    component,
    COUNT(*) AS calls,
    SUM(input_tokens) AS total_input_tokens,
    SUM(output_tokens) AS total_output_tokens,
    SUM(cost_usd) AS total_cost
FROM api_cost_events
WHERE created_at >= DATE_TRUNC('month', NOW())
GROUP BY model, component
ORDER BY total_cost DESC;
```

**Is caching/deduplication saving money? (Week over week):**
```sql
SELECT
    DATE_TRUNC('week', created_at) AS week,
    SUM(cost_usd) AS total_cost,
    COUNT(*) AS total_queries,
    SUM(cost_usd) / COUNT(*) AS avg_cost_per_query
FROM api_cost_events
WHERE mode = 'mode_2'
AND component = 'response_generator'
GROUP BY DATE_TRUNC('week', created_at)
ORDER BY week DESC;
```

**Mode 1 cost per ticker (corpus maintenance cost):**
```sql
SELECT
    r.ticker,
    COUNT(e.id) AS embedding_calls,
    SUM(e.cost_usd) AS total_cost
FROM api_cost_events e
JOIN processing_registry r ON e.document_id = r.document_id
WHERE e.mode = 'mode_1'
GROUP BY r.ticker
ORDER BY total_cost DESC;
```

---

## Soft Budget Alerts

Hard limits that block users are too disruptive for an analyst workflow. The platform uses soft alerts instead — notifications when cost thresholds are crossed. These are checked by a lightweight daily job that queries `api_cost_events` and sends an alert if any threshold is exceeded.

**Recommended thresholds to configure:**

| Alert | Threshold | Action |
|---|---|---|
| Single user daily cost | > $5 | Notify admin |
| Platform daily cost (Mode 2) | > $30 | Notify admin |
| Platform monthly cost | > $300 | Notify admin |
| Single query cost | > $0.50 | Log as anomaly, notify admin |
| Mode 1 daily run cost | > $10 | Notify admin (unexpected re-processing) |

Thresholds should be stored in a config table or environment variable so they can be adjusted as the team scales without code changes.

---

## What Each Workflow Document References

Every WF document includes a short Cost Tracking section. Here is the standard pattern each uses:

> **Cost Tracking**
> This workflow emits cost events to `api_cost_events` for the following calls:
> - `{component_name}` — model from `model_config`, logged after each API call
> Metadata attached: `mode`, `document_id` or `session_id`, `query_type` where applicable.
> See DS-04 for the full cost logging specification.
