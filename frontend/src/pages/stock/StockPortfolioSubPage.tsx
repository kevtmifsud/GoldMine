import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ColDef, GridApi } from "ag-grid-community";
import {
  LineChart,
  Line,
  ComposedChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import api from "../../config/api";
import { AppGrid } from "../../components/ag-grid/AppGrid";
import { createEntityLinkRenderer } from "../../components/ag-grid/EntityLinkRenderer";
import { useGridColumnManager } from "../../hooks/useGridColumnManager";
import { ResearchSearchBar } from "../../components/ResearchSearchBar";
import { StockViewToolbar } from "../../components/StockViewToolbar";
import { useStockEntity } from "./StockEntityPage";
import { StockSummaryBar } from "../../components/StockSummaryBar";
import type {
  TickerPortfolioData,
  TradeRecord,
  OpenPosition,
} from "../../types/portfolio";
import {
  ToggleableLegend,
  useToggleableLegend,
} from "../../components/ToggleableLegend";
import "../../styles/portfolio.css";

function formatCurrency(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}B`;
  if (abs >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
}

function formatDollar(value: number): string {
  return value.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function formatPct(value: number | undefined): string {
  const v = value ?? 0;
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function pnlClass(value: number): string {
  if (value > 0) return "portfolio-summary-card__value--positive";
  if (value < 0) return "portfolio-summary-card__value--negative";
  return "";
}

function pnlColor(value: number): string {
  if (value > 0) return "pnl--positive";
  if (value < 0) return "pnl--negative";
  return "";
}

const PortfolioLinkRenderer = createEntityLinkRenderer({ entityType: "portfolio" });

export function StockPortfolioSubPage() {
  const { detail } = useStockEntity();
  const [data, setData] = useState<TickerPortfolioData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPortfolio, setSelectedPortfolio] = useState<string | null>(null);
  const [pnlMode, setPnlMode] = useState<"$" | "%">("$");
  const [weightMode, setWeightMode] = useState<"%" | "$">("%");
  const gridApiRef = useRef<GridApi<TradeRecord> | null>(null);
  const { hiddenKeys: weightHidden, handleToggle: weightToggle, handleSolo: weightSolo } = useToggleableLegend();
  const { hiddenKeys: pnlChartHidden, handleToggle: pnlChartToggle, handleSolo: pnlChartSolo } = useToggleableLegend();

  useEffect(() => {
    setLoading(true);
    setError(null);
    const params: Record<string, string> = {};
    if (selectedPortfolio) params.portfolio = selectedPortfolio;
    api
      .get<TickerPortfolioData>(`/api/portfolio/${detail.entity_id}`, { params })
      .then((resp) => {
        setData(resp.data);
        // Auto-select the first portfolio if we haven't selected one yet
        if (
          !selectedPortfolio &&
          resp.data.portfolios.length > 0
        ) {
          setSelectedPortfolio(resp.data.portfolios[0]);
        }
      })
      .catch(() => setError("Failed to load portfolio data"))
      .finally(() => setLoading(false));
  }, [detail.entity_id, selectedPortfolio]);

  const allTradeColumns = useMemo<ColDef<TradeRecord>[]>(
    () => [
      { field: "date", headerName: "Date", sort: "desc" },
      {
        field: "action",
        headerName: "Action",
        valueFormatter: (p) => p.value ? p.value.charAt(0).toUpperCase() + p.value.slice(1).toLowerCase() : "",
        cellStyle: (params) => ({
          color: params.value === "buy" ? "var(--color-success)" : "var(--color-error)",
          fontWeight: 600,
        }),
      },
      {
        field: "side",
        headerName: "Side",
        width: 100,
        valueFormatter: (p) => p.value ? p.value.charAt(0).toUpperCase() + p.value.slice(1).toLowerCase() : "",
      },
      {
        field: "shares",
        headerName: "Shares",
        type: "numericColumn",
        valueFormatter: (p) => p.value?.toLocaleString() ?? "",
      },
      {
        field: "price",
        headerName: "Price",
        type: "numericColumn",
        valueFormatter: (p) => (p.value != null ? `$${p.value.toFixed(2)}` : ""),
      },
      {
        field: "notional",
        headerName: "Notional",
        type: "numericColumn",
        valueFormatter: (p) => (p.value != null ? formatDollar(p.value) : ""),
      },
      { field: "portfolio", headerName: "Portfolio", cellRenderer: PortfolioLinkRenderer },
    ],
    []
  );

  const defaultTradeFields = useMemo(
    () => ["date", "action", "side", "shares", "price", "notional", "portfolio"],
    []
  );

  const { columnDefs: tradeColumns, contextMenuConfig: tradeContextMenu } = useGridColumnManager<TradeRecord>({
    gridId: "stock-trade-history",
    allColumns: allTradeColumns,
    defaultVisibleFields: defaultTradeFields,
  });

  const handleGridReady = useCallback(
    (e: { api: GridApi<TradeRecord> }) => {
      gridApiRef.current = e.api;
    },
    []
  );

  const tooltipFormatter = useCallback(
    (value: number | undefined) => formatDollar(value ?? 0),
    []
  );

  const handlePortfolioChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const val = e.target.value;
      setSelectedPortfolio(val || null);
    },
    []
  );

  // Determine the side for the selected portfolio to color the area chart
  // (must be before early returns to keep hook order consistent)
  const positionSide = useMemo(() => {
    if (!data || !selectedPortfolio) return "long";
    const pos = data.open_positions.find((p) => p.portfolio === selectedPortfolio);
    if (pos) return pos.side;
    const portfolioTrades = data.trades.filter((t) => t.portfolio === selectedPortfolio);
    if (portfolioTrades.length > 0) return portfolioTrades[portfolioTrades.length - 1].side;
    return "long";
  }, [data, selectedPortfolio]);
  const areaColor = positionSide === "short" ? "#e53e3e" : "#38a169";

  if (loading && !data) {
    return (
      <>
        <ResearchSearchBar entityType={detail.entity_type} entityId={detail.entity_id} />
        <StockViewToolbar pageWidgets={[]} />
        <StockSummaryBar displayName={detail.display_name} headerFields={detail.header_fields} />
        <div className="portfolio-loading">
          <div className="spinner" />
        </div>
      </>
    );
  }

  if (error) {
    return (
      <>
        <ResearchSearchBar entityType={detail.entity_type} entityId={detail.entity_id} />
        <StockViewToolbar pageWidgets={[]} />
        <StockSummaryBar displayName={detail.display_name} headerFields={detail.header_fields} />
        <div className="portfolio-empty">
          <div className="portfolio-empty__title">Error</div>
          <div className="portfolio-empty__message">{error}</div>
        </div>
      </>
    );
  }

  if (!data) {
    return (
      <>
        <ResearchSearchBar entityType={detail.entity_type} entityId={detail.entity_id} />
        <StockViewToolbar pageWidgets={[]} />
        <StockSummaryBar displayName={detail.display_name} headerFields={detail.header_fields} />
        <div className="portfolio-empty">
          <div className="portfolio-empty__title">No Portfolio Data</div>
          <div className="portfolio-empty__message">
            Unable to load portfolio data for {detail.entity_id}.
          </div>
        </div>
      </>
    );
  }

  const { summary, open_positions, pnl_series, trades, portfolios, price_weight_series } = data;

  return (
    <>
      <ResearchSearchBar entityType={detail.entity_type} entityId={detail.entity_id} />
      <StockViewToolbar pageWidgets={[]} />
      <StockSummaryBar displayName={detail.display_name} headerFields={detail.header_fields} />

      {/* Portfolio Filter */}
      {portfolios.length > 0 && (
        <div className="portfolio-filter-bar">
          <span className="portfolio-filter-bar__label">Portfolio</span>
          <select
            className="portfolio-filter-bar__select"
            value={selectedPortfolio ?? ""}
            onChange={handlePortfolioChange}
          >
            <option value="">All Portfolios</option>
            {portfolios.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Summary Cards */}
      <div className="portfolio-summary-cards">
        <div className="portfolio-summary-card">
          <span className="portfolio-summary-card__label">Lifetime PnL</span>
          <span className={`portfolio-summary-card__value ${pnlClass(summary.lifetime_pnl)}`}>
            {formatCurrency(summary.lifetime_pnl)}
            <span className="portfolio-summary-card__pct">{formatPct(summary.lifetime_pnl_pct)}</span>
          </span>
          <span className="portfolio-summary-card__detail">
            <span className={pnlColor(summary.lifetime_realized_pnl)}>
              {formatCurrency(summary.lifetime_realized_pnl)} realized ({formatPct(summary.lifetime_realized_pnl_pct)})
            </span>
            {" | "}
            <span className={pnlColor(summary.lifetime_unrealized_pnl)}>
              {formatCurrency(summary.lifetime_unrealized_pnl)} unrealized ({formatPct(summary.lifetime_unrealized_pnl_pct)})
            </span>
          </span>
        </div>

        <div className="portfolio-summary-card">
          <span className="portfolio-summary-card__label">YTD PnL</span>
          <span className={`portfolio-summary-card__value ${pnlClass(summary.ytd_pnl)}`}>
            {formatCurrency(summary.ytd_pnl)}
            <span className="portfolio-summary-card__pct">{formatPct(summary.ytd_pnl_pct)}</span>
          </span>
          <span className="portfolio-summary-card__detail">
            <span className={pnlColor(summary.ytd_realized_pnl)}>
              {formatCurrency(summary.ytd_realized_pnl)} realized ({formatPct(summary.ytd_realized_pnl_pct)})
            </span>
            {" | "}
            <span className={pnlColor(summary.ytd_unrealized_pnl)}>
              {formatCurrency(summary.ytd_unrealized_pnl)} unrealized ({formatPct(summary.ytd_unrealized_pnl_pct)})
            </span>
          </span>
        </div>

        <div className="portfolio-summary-card">
          <span className="portfolio-summary-card__label">Active Positions</span>
          <span className="portfolio-summary-card__value">
            {summary.active_position_count}
          </span>
          <span className="portfolio-summary-card__detail">
            {selectedPortfolio ? `in ${selectedPortfolio}` : "across portfolios"}
          </span>
        </div>

        <div className="portfolio-summary-card">
          <span className="portfolio-summary-card__label">Total Trades</span>
          <span className="portfolio-summary-card__value">
            {summary.total_trade_count}
          </span>
          <span className="portfolio-summary-card__detail">
            {summary.first_trade_date && summary.last_trade_date
              ? `${summary.first_trade_date} — ${summary.last_trade_date}`
              : "No trades"}
          </span>
        </div>
      </div>

      {/* Charts Row */}
      <div className="portfolio-charts-row">
        {/* Price & Portfolio Weight Chart */}
        {price_weight_series.length > 1 && (
          <div className="portfolio-chart">
            <div className="portfolio-chart__header">
              <div className="portfolio-chart__title">
                Price &amp; Portfolio Weight
              </div>
              <div className="portfolio-chart__toggle">
                <button
                  className={`portfolio-chart__toggle-btn${weightMode === "%" ? " portfolio-chart__toggle-btn--active" : ""}`}
                  onClick={() => setWeightMode("%")}
                >
                  %
                </button>
                <button
                  className={`portfolio-chart__toggle-btn${weightMode === "$" ? " portfolio-chart__toggle-btn--active" : ""}`}
                  onClick={() => setWeightMode("$")}
                >
                  $
                </button>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={price_weight_series}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v: string) => v.slice(0, 7)}
                  interval={Math.max(0, Math.floor(price_weight_series.length / 8) - 1)}
                />
                <YAxis
                  yAxisId="price"
                  tickFormatter={(v: number) => `$${v}`}
                  tick={{ fontSize: 11 }}
                />
                <YAxis
                  yAxisId="weight"
                  orientation="right"
                  tickFormatter={weightMode === "%" ? (v: number) => `${v}%` : (v: number) => formatCurrency(v)}
                  tick={{ fontSize: 11 }}
                />
                <Tooltip
                  labelFormatter={(label) => String(label)}
                  formatter={(value: number | undefined, name: string | undefined) => {
                    if (value == null) return "—";
                    if (name === "Portfolio %") return `${value.toFixed(2)}%`;
                    if (name === "Portfolio $") return formatCurrency(value);
                    return `$${value.toFixed(2)}`;
                  }}
                />
                <Legend
                  content={(props) => (
                    <ToggleableLegend
                      payload={props.payload as never}
                      hiddenKeys={weightHidden}
                      onToggle={weightToggle}
                      onSolo={(key) => weightSolo(key, [
                        weightMode === "%" ? "portfolio_pct" : "portfolio_dollars",
                        "stock_price",
                      ])}
                    />
                  )}
                />
                <Area
                  yAxisId="weight"
                  type="stepAfter"
                  dataKey={weightMode === "%" ? "portfolio_pct" : "portfolio_dollars"}
                  name={weightMode === "%" ? "Portfolio %" : "Portfolio $"}
                  fill={areaColor}
                  stroke={areaColor}
                  fillOpacity={0.15}
                  strokeWidth={1}
                  strokeOpacity={0.4}
                  hide={weightHidden.has(weightMode === "%" ? "portfolio_pct" : "portfolio_dollars")}
                />
                <Line
                  yAxisId="price"
                  type="monotone"
                  dataKey="stock_price"
                  name="Stock Price"
                  stroke="#1a202c"
                  dot={false}
                  strokeWidth={2}
                  hide={weightHidden.has("stock_price")}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Cumulative PnL Chart */}
        {pnl_series.length > 1 && (
          <div className="portfolio-chart">
            <div className="portfolio-chart__header">
              <div className="portfolio-chart__title">Cumulative PnL</div>
              <div className="portfolio-chart__toggle">
                <button
                  className={`portfolio-chart__toggle-btn${pnlMode === "$" ? " portfolio-chart__toggle-btn--active" : ""}`}
                  onClick={() => setPnlMode("$")}
                >
                  $
                </button>
                <button
                  className={`portfolio-chart__toggle-btn${pnlMode === "%" ? " portfolio-chart__toggle-btn--active" : ""}`}
                  onClick={() => setPnlMode("%")}
                >
                  %
                </button>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={pnl_series}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis
                  tickFormatter={pnlMode === "$" ? (v: number) => formatCurrency(v) : (v: number) => `${v.toFixed(1)}%`}
                  tick={{ fontSize: 11 }}
                />
                <Tooltip
                  formatter={pnlMode === "$"
                    ? tooltipFormatter
                    : (value: number | undefined) => `${(value ?? 0).toFixed(2)}%`
                  }
                />
                <Legend
                  content={(props) => (
                    <ToggleableLegend
                      payload={props.payload as never}
                      hiddenKeys={pnlChartHidden}
                      onToggle={pnlChartToggle}
                      onSolo={(key) => pnlChartSolo(key, [
                        pnlMode === "$" ? "cumulative_pnl" : "cumulative_pnl_pct",
                        pnlMode === "$" ? "realized_pnl" : "realized_pnl_pct",
                      ])}
                    />
                  )}
                />
                <Line
                  type="monotone"
                  dataKey={pnlMode === "$" ? "cumulative_pnl" : "cumulative_pnl_pct"}
                  name="Cumulative PnL"
                  stroke="#3182ce"
                  dot={false}
                  strokeWidth={2}
                  hide={pnlChartHidden.has(pnlMode === "$" ? "cumulative_pnl" : "cumulative_pnl_pct")}
                />
                <Line
                  type="monotone"
                  dataKey={pnlMode === "$" ? "realized_pnl" : "realized_pnl_pct"}
                  name="Realized PnL"
                  stroke="#38a169"
                  dot={false}
                  strokeWidth={2}
                  hide={pnlChartHidden.has(pnlMode === "$" ? "realized_pnl" : "realized_pnl_pct")}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Open Positions */}
      {open_positions.length > 0 && (
        <div className="portfolio-positions">
          <div className="portfolio-positions__title">Open Positions</div>
          <div className="portfolio-positions__grid">
            {open_positions.map((pos: OpenPosition) => (
              <div
                key={`${pos.portfolio}-${pos.side}`}
                className="portfolio-position-card"
              >
                <div className="portfolio-position-card__header">
                  <span className="portfolio-position-card__portfolio">
                    {pos.portfolio}
                  </span>
                  <span
                    className={`portfolio-position-card__badge portfolio-position-card__badge--${pos.side}`}
                  >
                    {pos.side}
                  </span>
                </div>
                <div className="portfolio-position-card__rows">
                  <div className="portfolio-position-card__row">
                    <span className="portfolio-position-card__row-label">Shares</span>
                    <span className="portfolio-position-card__row-value">
                      {pos.shares.toLocaleString()}
                    </span>
                  </div>
                  <div className="portfolio-position-card__row">
                    <span className="portfolio-position-card__row-label">Avg Cost</span>
                    <span className="portfolio-position-card__row-value">
                      ${pos.avg_cost.toFixed(2)}
                    </span>
                  </div>
                  <div className="portfolio-position-card__row">
                    <span className="portfolio-position-card__row-label">Current Price</span>
                    <span className="portfolio-position-card__row-value">
                      ${pos.current_price.toFixed(2)}
                    </span>
                  </div>
                  <div className="portfolio-position-card__row">
                    <span className="portfolio-position-card__row-label">Portfolio Weight</span>
                    <span className="portfolio-position-card__row-value">
                      {pos.portfolio_pct.toFixed(1)}%
                    </span>
                  </div>
                  <div className="portfolio-position-card__row">
                    <span className="portfolio-position-card__row-label">Unrealized PnL</span>
                    <span className={`portfolio-position-card__row-value ${pnlColor(pos.unrealized_pnl)}`}>
                      {formatDollar(pos.unrealized_pnl)} ({pos.unrealized_pnl_pct.toFixed(1)}%)
                    </span>
                  </div>
                  <div className="portfolio-position-card__row">
                    <span className="portfolio-position-card__row-label">Realized PnL</span>
                    <span className={`portfolio-position-card__row-value ${pnlColor(pos.realized_pnl)}`}>
                      {formatDollar(pos.realized_pnl)}
                    </span>
                  </div>
                  <div className="portfolio-position-card__row">
                    <span className="portfolio-position-card__row-label">Last Trade</span>
                    <span className="portfolio-position-card__row-value">
                      {pos.last_trade_date}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Trade History */}
      <div className="portfolio-trades">
        <div className="portfolio-trades__header">
          <div className="portfolio-trades__title">Trade History</div>
          {trades.length > 0 && (
            <button
              className="portfolio-trades__download-btn"
              onClick={() => gridApiRef.current?.exportDataAsCsv()}
            >
              Download CSV
            </button>
          )}
        </div>
        <div className="portfolio-trades__grid">
          <AppGrid<TradeRecord>
            rowData={trades}
            columnDefs={tradeColumns}
            onGridReady={handleGridReady}
            contextMenu={tradeContextMenu}
            viewKey="stock-trade-history"
          />
        </div>
      </div>
    </>
  );
}
