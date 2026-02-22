# GoldMine Phase 6 — Stock History Data, Portfolio Trades & Price History Chart

## Context

Phase 5 delivered the email scheduling system with background delivery. Phase 6 adds historical price data for charting and a simulated portfolio trades dataset for future portfolio analytics. This involves: (1) a script to pull daily closing prices and EPS data from defeatbeta-api (DuckDB queries against Parquet files on Hugging Face — no API keys, no rate limits) for all 506 tickers back to 2015, (2) a script to generate simulated portfolio trades using real prices, and (3) a full-width interactive price history line chart on each stock entity page with EPS estimate/actual overlay on a secondary axis.

**User decisions:**
- Price data: defeatbeta-api `Ticker(symbol).price()` per ticker, parallelized with `ThreadPoolExecutor`.
- EPS data: defeatbeta-api `Ticker(symbol).ttm_eps()` per ticker, parallelized with `ThreadPoolExecutor`. Checkpoint/resume for interrupted runs.
- EPS estimates: Derived synthetically from price / sector P/E / 4 (defeatbeta-api provides actuals only, not consensus estimates).
- Stocks.csv financials (price, 52W high/low, EPS, P/E) are computed from stock_history.csv data after each update.
- Chart interactions: Click-and-drag to zoom into a date range, double-click to reset zoom.
- Chart lines: Linear interpolation (no smoothing). EPS lines rendered at 45% opacity.

**Key patterns followed (established in Phases 0-5):**
- Backend: factory+provider singletons, Pydantic models, `from __future__ import annotations`
- Frontend: functional components with hooks, BEM CSS, Recharts for charts
- Data: CSV flat files in `data/structured/`

---

## Data Scripts

### `scripts/update_fundamentals_data.py`

Single unified script that handles all data fetching and computation:

**Phase 1 — Prices:**
- Reads tickers from `data/structured/stocks.csv`
- Converts `BRK.B` → `BRK-B` for defeatbeta-api compatibility, maps back for storage
- Per-ticker `Ticker(symbol).price()` calls via `ThreadPoolExecutor` (10 threads)
- Extracts `report_date` and `close` columns, filters by `--start-date`
- ~506 tickers × ~2600 trading days ≈ 1.3M rows

**Phase 2 — EPS:**
- Per-ticker `Ticker(symbol).ttm_eps()` calls via `ThreadPoolExecutor` (10 threads)
- Uses `eps` column as quarterly `eps_actual`
- Generates synthetic `eps_estimate` from close price / sector P/E / 4
- Maps fiscal quarter-end dates to nearest trading dates
- Checkpoint/resume support via `.eps_checkpoint.json`
- Tickers that fail fall back to fully synthetic EPS

**Phase 3 — Write output:**
- Writes `data/structured/stock_history.csv` — columns: `date,ticker,close,eps_estimate,eps_actual`

**Phase 4 — Update stocks.csv:**
- Computes from stock history: latest price, 52W high/low, TTM EPS, P/E ratio
- Updates `data/structured/stocks.csv` financial columns in-place
- Preserves static fields: ticker, company_name, sector, industry, country, exchange

**CLI flags:**
- `--fresh` — Re-fetch all EPS (ignore checkpoint)
- `--synthetic-only` — Skip real EPS fetches, use synthetic EPS only
- `--prices-only` — Skip EPS entirely (empty EPS columns)
- `--start-date DATE` — Price history start date (default: 2015-01-01)

### `scripts/generate_portfolio_trades.py`

- Reads real prices from `stock_history.csv`
- Picks 18 diversified tickers: AAPL, MSFT, GOOGL, AMZN, JPM, JNJ, XOM, PG, V, UNH, HD, BA, NEE, DIS, KO, BLK, PLD, FCX
- Simulates: initial buys in Jan 2015, then 5-10 random trades per ticker over time
- Uses `random.seed(42)` for reproducibility
- Output: `data/structured/portfolio_trades.csv` — columns: `date,ticker,action,shares,price`

---

## Backend Endpoint & Widget

### `backend/app/api/entity_models.py`

New model:
```python
class SecondaryLine(BaseModel):
    y_key: str
    label: str
    color: str = "#e86319"
```

Extended `ChartConfig`:
```python
class ChartConfig(BaseModel):
    # ... existing fields ...
    secondary_y_label: str | None = None
    secondary_lines: list[SecondaryLine] = Field(default_factory=list)
```

### `backend/app/api/entities.py`

New endpoint: `GET /api/entities/stock/{ticker}/price-history`
- Reads `data/structured/stock_history.csv` directly via `csv.DictReader`
- Filters rows by ticker, returns chronologically sorted `PaginatedResponse`
- Includes `eps_estimate` and `eps_actual` fields only when present (non-empty)
- Default `page_size=5000` to return all ~2600 data points in one page
- Gracefully returns empty response if `stock_history.csv` doesn't exist

Stock detail header fields (price, 52W high/low, EPS, P/E) are read from `stocks.csv`, which is updated with computed values by `update_fundamentals_data.py`.

---

## Frontend Chart Enhancements

### `frontend/src/components/ChartWidget.tsx`

1. **Proper line rendering**: `dot={false}`, `strokeWidth={1.5}`, `isAnimationActive={false}`, `type="linear"` (no smoothing)
2. **Click-and-drag zoom**: `onMouseDown`/`onMouseMove`/`onMouseUp` handlers track selection range. `ReferenceArea` highlights the selected region. On release, data is sliced to the selected range.
3. **Double-click to reset zoom**: `onDoubleClick` handler resets zoom state. "Reset Zoom" button also available.
4. **Cursor feedback**: Crosshair cursor when unzoomed, zoom-out cursor when zoomed.
5. **Secondary Y-axis**: Right-side `YAxis` for EPS lines when `secondary_lines` is configured.
6. **Multi-line support**: Primary line on left axis, secondary lines on right axis at 45% opacity.
7. **X-axis tick thinning**: Limits to ~10 evenly spaced ticks to prevent date label overlap.

---

## Execution Order

1. `pip install defeatbeta-api` in the project venv
2. Run `scripts/update_fundamentals_data.py` → `stock_history.csv` + updated `stocks.csv` ready
3. Run `scripts/generate_portfolio_trades.py` → `portfolio_trades.csv` ready
4. Start backend — stock detail pages show computed financials + price history chart

---

## Key Design Decisions

1. **defeatbeta-api over yfinance** — DuckDB queries against Parquet files on Hugging Face. No API keys, no rate limits. Sub-second per-ticker queries. Replaces yfinance which suffered from aggressive Yahoo Finance rate limiting.
2. **Per-ticker `ThreadPoolExecutor`** — defeatbeta-api queries are I/O-bound HTTP fetches to Hugging Face. 10 parallel threads provide good throughput without overwhelming the data source.
3. **Checkpoint/resume for EPS** — 506 per-ticker API calls can be interrupted. JSON checkpoint saves progress after each ticker so runs resume from where they left off.
4. **Synthetic EPS estimates** — defeatbeta-api provides actual quarterly EPS but not consensus estimates. Estimates are derived from price / sector P/E / 4. Real actuals come from defeatbeta-api.
5. **Computed stocks.csv financials** — Price, 52W high/low, TTM EPS, and P/E ratio are computed from stock_history.csv data rather than being static snapshots. Updated automatically when the data script runs.
6. **Linear interpolation, no smoothing** — `type="linear"` on all `<Line>` components. Shows actual price movements without artificial curves.
7. **Secondary Y-axis for EPS** — EPS values are orders of magnitude smaller than stock prices. A right-side Y-axis with independent scale allows both to be visible.
8. **Click-and-drag zoom with double-click reset** — Standard charting UX pattern. Implemented with Recharts `ReferenceArea` + data slicing.
9. **Full-width price chart, 2-column peer charts** — Price history benefits from maximum width. Peer comparison bar charts work well side-by-side.
