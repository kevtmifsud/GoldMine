# WF-07: Ticker Resolution

## Purpose

The ticker resolver takes the classifier output from WF-06 and expands any list references or group descriptors into a concrete set of ticker symbols. It is a pure database operation — no LLM involvement. The output is a definitive list of tickers that WF-08 uses to scope retrieval.

---

## Goals

- Expand user-defined list references into ticker arrays
- Resolve sector, industry, and market cap group descriptors into ticker arrays
- Return a clean, deduplicated ticker list to WF-08
- Complete with one or two SQL queries — no API calls, no latency

---

## Resolution Sources

There are three sources for ticker resolution, checked in order:

**Source 1 — Explicit tickers**
Tickers named directly in the user's message are passed through as-is after validation against the `tickers` master table. Invalid tickers are dropped and logged.

**Source 2 — User-defined lists**
Named list references (e.g., "my semiconductor names", "Farm System") are resolved by querying `user_ticker_lists` filtered by `user_id` and `list_name`.

**Source 3 — System-defined groups**
Sector, industry, and market cap references (e.g., "large cap tech", "energy names", "Russell 2000 exposure") are resolved by querying the `tickers` master table with the appropriate filter. These groups are derived from the `sector`, `industry`, and `market_cap_tier` columns defined in DS-01.

---

## Resolution Logic

```
For each item in classifier output:

  If item is in tickers[]:
      Validate against tickers master table
      Add to resolved set if valid

  If item is in list_references[]:
      Query user_ticker_lists WHERE user_id = current AND list_name = item
      Add all returned tickers to resolved set

  If item looks like a sector/industry/group descriptor:
      Query tickers WHERE sector ILIKE item OR industry ILIKE item
      Add all returned tickers to resolved set

Deduplicate resolved set
Return final ticker array
```

---

## Handling Screening Queries

For screening queries where the user does not specify a universe, the resolver defaults to all active tickers in the platform:

```sql
SELECT ticker FROM tickers WHERE is_active = TRUE ORDER BY ticker;
```

This can return thousands of tickers. WF-08 handles the scale of retrieval for screening queries — the resolver's job is just to return the complete universe.

---

## Universe Size Caps

To prevent runaway retrieval costs on very large universes:

| Query type | Max tickers | Behavior if exceeded |
|---|---|---|
| `cross_ticker` | 50 | Truncate to 50, warn user in response |
| `screening` | All active | No cap — WF-08 manages cost via chunk limits |
| `trend_analysis` | 1 | Ignore additional tickers, use first only |
| `single_ticker_*` | 1 | Ignore additional tickers, use first only |

---

## Output

A resolved ticker list passed to WF-08:

```python
class ResolvedUniverse(BaseModel):
    tickers: list[str]
    resolution_sources: dict[str, str]  # ticker → how it was resolved
    was_truncated: bool
    original_list_references: list[str]
```

The `resolution_sources` field is stored on the message record in Supabase for audit and debugging.

---

## Cost Tracking

No API calls are made in this workflow. No cost events are emitted. All operations are SQL queries against Supabase at no cost.
