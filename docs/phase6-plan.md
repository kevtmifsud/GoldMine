# GoldMine Phase 6 — Stock History Data, Portfolio Trades & Price History Chart

## Context

Phase 5 delivered the email scheduling system with background delivery. Phase 6 adds historical price data for charting and a simulated portfolio trades dataset for future portfolio analytics. This involves: (1) scripts to pull daily closing prices and EPS data from Yahoo Finance for all 76 tickers back to 2015, (2) a script to generate simulated portfolio trades using real prices, and (3) a full-width interactive price history line chart on each stock entity page with EPS estimate/actual overlay on a secondary axis.

**User decisions:**
- Price data: Yahoo Finance via `yfinance` library. Single `yf.download()` call with `threads=True` for all tickers.
- EPS data: Yahoo Finance `get_earnings_dates()` per ticker, parallelized with `ThreadPoolExecutor`. Checkpoint/resume for interrupted runs.
- Stopgap: `generate_eps_data.py` derives realistic EPS from prices when Yahoo rate limits are active.
- Chart interactions: Click-and-drag to zoom into a date range, double-click to reset zoom.
- Chart lines: Linear interpolation (no smoothing). EPS lines rendered at 45% opacity.

**Key patterns followed (established in Phases 0-5):**
- Backend: factory+provider singletons, Pydantic models, `from __future__ import annotations`
- Frontend: functional components with hooks, BEM CSS, Recharts for charts
- Data: CSV flat files in `data/structured/`

---

## New Files (5)

| File | Purpose |
|------|---------|
| `scripts/pull_stock_history.py` | Download daily closing prices from Yahoo Finance for all 76 tickers using `yf.download(threads=True)` |
| `scripts/add_eps_to_history.py` | Fetch real EPS estimate/actual per ticker via `ThreadPoolExecutor`, merge into `stock_history.csv`. Checkpoint/resume support. |
| `scripts/generate_eps_data.py` | Generate derived EPS data from stock prices (no API calls — stopgap for rate limits) |
| `scripts/generate_portfolio_trades.py` | Simulate portfolio trades using real prices for 18 diversified tickers |
| `data/structured/stock_history.csv` | ~212K rows: `date,ticker,close,eps_estimate,eps_actual` (76 tickers, 2015–present) |
| `data/structured/portfolio_trades.csv` | ~152 trades: `date,ticker,action,shares,price` (18 tickers, seeded for reproducibility) |

## Modified Files (6)

| File | Change |
|------|--------|
| `backend/requirements.txt` | Add `yfinance==0.2.54` |
| `backend/app/api/entity_models.py` | Add `SecondaryLine` model; extend `ChartConfig` with `secondary_y_label` and `secondary_lines` |
| `backend/app/api/entities.py` | Add `GET /api/entities/stock/{ticker}/price-history` endpoint; add `price_history` widget as first widget in `_build_stock_detail()` |
| `frontend/src/types/entities.ts` | Add `SecondaryLine` interface; extend `ChartConfig` with `secondary_y_label` and `secondary_lines` |
| `frontend/src/components/ChartWidget.tsx` | Line chart rendering with zoom, secondary Y-axis, and multi-line support |
| `frontend/src/pages/EntityPage.tsx` | Full-width layout for `price_history` chart, 2-column grid for remaining charts |
| `frontend/src/styles/entity.css` | Add `.entity-page__chart-full` class |
| `frontend/src/styles/chart.css` | Add zoom cursor styles, header layout for reset button |

---

## Stage 1: Data Scripts

### `scripts/pull_stock_history.py`

- Reads tickers from `data/structured/stocks.csv`
- Converts `BRK.B` → `BRK-B` for Yahoo Finance compatibility, maps back for storage
- Single `yf.download()` call with `threads=True` for all 76 tickers — most efficient approach
- Extracts Close prices only (auto-adjusted for splits/dividends)
- Output: `data/structured/stock_history.csv` in long format with columns: `date,ticker,close,eps_estimate,eps_actual` (EPS columns left empty — populated by separate scripts)
- ~76 tickers × ~2600 trading days ≈ 198K–212K rows
- Idempotent — overwrites on re-run

### `scripts/add_eps_to_history.py`

- Reads existing `stock_history.csv` (does not re-download prices)
- Fetches `get_earnings_dates(limit=50)` per ticker for EPS Estimate and Reported EPS
- **Parallelized**: `ThreadPoolExecutor` with 5 workers for concurrent fetches
- **Checkpoint/resume**: saves progress to `.eps_checkpoint.json` — interrupted runs pick up where they left off
- **Exponential backoff**: 60s → 120s → 240s on rate limit, 3 retries per ticker
- Thread-safe checkpoint writes via `threading.Lock`
- `--fresh` flag to ignore checkpoint and re-fetch everything
- Rewrites CSV with real EPS data; only cleans up checkpoint when all tickers succeed

### `scripts/generate_eps_data.py`

- Stopgap for when Yahoo Finance rate limits are active
- Derives realistic quarterly EPS from actual stock prices using sector P/E ratios
- Uses `random.seed(42)` for reproducibility
- Picks one date per quarter (end of earnings window months: Jan, Apr, Jul, Oct)
- EPS estimate derived from price / sector P/E / 4; actual adds random surprise (-5% to +10%)
- No API calls — runs instantly

### `scripts/generate_portfolio_trades.py`

- Reads real prices from `stock_history.csv`
- Picks 18 diversified tickers: AAPL, MSFT, GOOGL, AMZN, JPM, JNJ, XOM, PG, V, UNH, HD, BA, NEE, DIS, KO, BLK, PLD, FCX
- Simulates: initial buys in Jan 2015, then 5–10 random trades per ticker over time
- Uses `random.seed(42)` for reproducibility
- Output: `data/structured/portfolio_trades.csv` — columns: `date,ticker,action,shares,price`

---

## Stage 2: Backend Endpoint & Widget

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

Widget definition in `_build_stock_detail()` — `price_history` added as **first** widget:
```python
WidgetConfig(
    widget_id="price_history",
    title="Price History",
    endpoint=f"/api/entities/stock/{ticker}/price-history",
    widget_type="chart",
    chart_config=ChartConfig(
        chart_type="line",
        x_key="date",
        y_key="close",
        x_label="Date",
        y_label="Close Price ($)",
        secondary_y_label="EPS ($)",
        secondary_lines=[
            SecondaryLine(y_key="eps_estimate", label="EPS Estimate", color="#805ad5"),
            SecondaryLine(y_key="eps_actual", label="EPS Actual", color="#38a169"),
        ],
    ),
    columns=[],
    default_page_size=5000,
)
```

---

## Stage 3: Frontend Chart Enhancements

### `frontend/src/types/entities.ts`

New interface:
```typescript
interface SecondaryLine {
  y_key: string;
  label: string;
  color: string;
}
```

Extended `ChartConfig`:
```typescript
interface ChartConfig {
  // ... existing fields ...
  secondary_y_label: string | null;
  secondary_lines: SecondaryLine[];
}
```

### `frontend/src/components/ChartWidget.tsx`

Major enhancements to the line chart rendering:

1. **Proper line rendering**: `dot={false}`, `strokeWidth={1.5}`, `isAnimationActive={false}`, `type="linear"` (no smoothing)
2. **Click-and-drag zoom**: `onMouseDown`/`onMouseMove`/`onMouseUp` handlers track selection range. `ReferenceArea` highlights the selected region with a blue overlay while dragging. On release, data is sliced to the selected range. Y-axis rescales with `domain={["auto", "auto"]}`.
3. **Double-click to reset zoom**: `onDoubleClick` handler on the chart container resets zoom state. "Reset Zoom" button also available in the chart header.
4. **Cursor feedback**: Crosshair cursor when unzoomed (signals drag-to-zoom), zoom-out cursor when zoomed (signals double-click to reset).
5. **Secondary Y-axis**: Right-side `YAxis` with `yAxisId="right"` for EPS lines when `secondary_lines` is configured.
6. **Multi-line support**: Primary line on left axis, secondary lines on right axis. Secondary lines rendered with `strokeOpacity={0.45}` and `connectNulls` for visual hierarchy.
7. **Legend**: Custom legend showing all line series when secondary lines are present.
8. **X-axis tick thinning**: Limits to ~10 evenly spaced ticks to prevent date label overlap.
9. **Numeric coercion**: Secondary line values coerced to `Number` or `undefined` (so Recharts skips empty EPS gaps).

### `frontend/src/pages/EntityPage.tsx`

Split chart rendering into two sections:
- `price_history` widgets get a full-width container (`.entity-page__chart-full`)
- All other chart widgets stay in the existing 2-column grid (`.entity-page__charts`)

### `frontend/src/styles/entity.css`

New class:
```css
.entity-page__chart-full {
  width: 100%;
}
```

### `frontend/src/styles/chart.css`

- `.chart-widget__header` — flex layout for title + reset zoom button
- `.chart-widget__zoom-reset` — styled button for zoom reset
- `.chart-widget__container--zoomable` — crosshair cursor
- `.chart-widget__container--zoomed` — zoom-out cursor
- `user-select: none` on container to prevent text selection during drag

---

## Execution Order

1. `pip install yfinance` → run `scripts/pull_stock_history.py` → `stock_history.csv` ready with prices
2. Run `scripts/generate_eps_data.py` → EPS columns populated (derived data)
3. Run `scripts/generate_portfolio_trades.py` → `portfolio_trades.csv` ready
4. (Later, when rate limits clear) Run `scripts/add_eps_to_history.py` → replace derived EPS with real Yahoo Finance data
5. Backend: add endpoint + widget definition
6. Frontend: update chart component + layout
7. `npx tsc -b` builds clean

---

## Key Design Decisions

1. **Single `yf.download(threads=True)` call** — Most efficient approach for batch price data. yfinance handles internal threading and batching. Avoids manual batch splitting and delays.
2. **Separate EPS fetching script** — Yahoo Finance has no batch API for earnings data. `get_earnings_dates()` requires one call per ticker. Parallelized with `ThreadPoolExecutor(max_workers=5)` to minimize wall-clock time while staying under rate limits.
3. **Checkpoint/resume for EPS** — 76 sequential API calls are fragile. JSON checkpoint saves progress after each ticker so interrupted runs (rate limits, network issues) resume from where they left off.
4. **Derived EPS as stopgap** — When Yahoo rate limits are active, `generate_eps_data.py` generates realistic EPS from actual prices using sector P/E ratios. All chart plumbing works immediately; swap in real data later.
5. **Linear interpolation, no smoothing** — `type="linear"` on all `<Line>` components. Data points connected with straight segments, no cubic spline interpolation. Shows actual price movements without artificial curves.
6. **Secondary Y-axis for EPS** — EPS values are orders of magnitude smaller than stock prices. A right-side Y-axis with independent scale allows both to be visible and readable on the same chart.
7. **EPS lines at 45% opacity** — Lower opacity creates clear visual hierarchy: price line is primary, EPS lines are secondary context. Both visible without competing.
8. **Click-and-drag zoom with double-click reset** — Standard charting UX pattern. Cursor changes (crosshair → zoom-out) provide visual affordance. No external zoom library needed — implemented with Recharts `ReferenceArea` + data slicing.
9. **Full-width price chart, 2-column peer charts** — Price history is the primary visual on stock pages and benefits from maximum width. Peer comparison bar charts are secondary and work well side-by-side.
10. **Portfolio trades for future use** — `portfolio_trades.csv` is generated but not yet surfaced in the UI. Provides the data foundation for future portfolio analytics features (P&L, holdings over time, trade blotter).
