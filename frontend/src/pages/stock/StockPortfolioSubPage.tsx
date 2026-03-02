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
  ReferenceLine,
  ReferenceArea,
  ResponsiveContainer,
} from "recharts";
import api from "../../config/api";
import { EarningsDetailDialog } from "../../components/EarningsDetailDialog";
import { AppGrid } from "../../components/ag-grid/AppGrid";
import { createEntityLinkRenderer } from "../../components/ag-grid/EntityLinkRenderer";
import { useGridColumnManager } from "../../hooks/useGridColumnManager";
import { useChartZoom } from "../../hooks/useChartZoom";
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

interface EarningsEntry {
  report_date: string;
  time: string;
  fiscal_quarter_ending: string;
  fiscal_year?: number;
  fiscal_quarter?: number;
  has_transcript?: boolean;
  filing_url?: string | null;
}

interface AllEarningsEntry {
  report_date: string;
  fiscal_year: number | null;
  fiscal_quarter: number | null;
}

interface EarningsData {
  ticker: string;
  last_earnings: EarningsEntry | null;
  next_earnings: EarningsEntry | null;
  all_earnings: AllEarningsEntry[];
}

function formatEarningsDate(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function formatEarningsTime(time: string): string {
  switch (time) {
    case "after-market-close": return "After Market";
    case "before-market-open": return "Before Open";
    case "time-after-hours": return "After Hours";
    case "time-pre-market": return "Pre-Market";
    default: return "";
  }
}

function daysUntil(dateStr: string): number {
  const target = new Date(dateStr + "T00:00:00");
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  return Math.ceil((target.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
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
  const [earningsData, setEarningsData] = useState<EarningsData | null>(null);
  const [showEarningsDialog, setShowEarningsDialog] = useState(false);
  const gridApiRef = useRef<GridApi<TradeRecord> | null>(null);
  const { hiddenKeys: weightHidden, handleToggle: weightToggle, handleSolo: weightSolo } = useToggleableLegend();
  const { hiddenKeys: pnlChartHidden, handleToggle: pnlChartToggle, handleSolo: pnlChartSolo } = useToggleableLegend();
  const priceZoom = useChartZoom();
  const pnlZoom = useChartZoom();

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

  useEffect(() => {
    api
      .get<EarningsData>(`/api/earnings/${detail.entity_id}`)
      .then((resp) => setEarningsData(resp.data))
      .catch(() => {/* ignore — cards will show dashes */});
  }, [detail.entity_id]);

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

  // Earnings date lookup map for tooltip enrichment
  const earningsDateToLabel = useMemo(() => {
    const m = new Map<string, string>();
    earningsData?.all_earnings?.forEach((e) => {
      if (e.fiscal_year && e.fiscal_quarter) {
        m.set(e.report_date, `FY${String(e.fiscal_year).slice(-2)} Q${e.fiscal_quarter}`);
      }
    });
    return m;
  }, [earningsData]);

  // Trade date lookup for chart dot markers and tooltip
  const tradeDateMap = useMemo(() => {
    const m = new Map<string, TradeRecord[]>();
    if (!data) return m;
    for (const t of data.trades) {
      const arr = m.get(t.date);
      if (arr) arr.push(t);
      else m.set(t.date, [t]);
    }
    return m;
  }, [data]);

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

        {/* Last Earnings */}
        <div
          className={`portfolio-summary-card${earningsData?.last_earnings?.has_transcript ? " portfolio-summary-card--clickable" : ""}`}
          onClick={() => {
            if (earningsData?.last_earnings?.has_transcript) setShowEarningsDialog(true);
          }}
        >
          <span className="portfolio-summary-card__label">Last Earnings</span>
          <span className="portfolio-summary-card__value">
            {earningsData?.last_earnings
              ? formatEarningsDate(earningsData.last_earnings.report_date)
              : "\u2014"}
          </span>
          <span className="portfolio-summary-card__detail">
            {earningsData?.last_earnings
              ? [
                  earningsData.last_earnings.fiscal_year && earningsData.last_earnings.fiscal_quarter
                    ? `FY${String(earningsData.last_earnings.fiscal_year).slice(-2)} Q${earningsData.last_earnings.fiscal_quarter}`
                    : "",
                  formatEarningsTime(earningsData.last_earnings.time),
                ].filter(Boolean).join(" \u00B7 ") || "\u00A0"
              : "\u00A0"}
          </span>
        </div>

        {/* Next Earnings */}
        <div className="portfolio-summary-card">
          <span className="portfolio-summary-card__label">Next Earnings</span>
          <span className="portfolio-summary-card__value">
            {earningsData?.next_earnings
              ? formatEarningsDate(earningsData.next_earnings.report_date)
              : "\u2014"}
          </span>
          <span className="portfolio-summary-card__detail">
            {earningsData?.next_earnings
              ? [
                  formatEarningsTime(earningsData.next_earnings.time),
                  `in ${daysUntil(earningsData.next_earnings.report_date)} days`,
                ].filter(Boolean).join(" \u00B7 ")
              : "\u00A0"}
          </span>
        </div>
      </div>

      {/* Earnings Detail Dialog */}
      {showEarningsDialog && earningsData?.last_earnings?.fiscal_year && earningsData?.last_earnings?.fiscal_quarter && (
        <EarningsDetailDialog
          symbol={detail.entity_id}
          year={earningsData.last_earnings.fiscal_year}
          quarter={earningsData.last_earnings.fiscal_quarter}
          filingUrl={earningsData.last_earnings.filing_url ?? null}
          onClose={() => setShowEarningsDialog(false)}
        />
      )}

      {/* Charts Row */}
      <div className="portfolio-charts-row">
        {/* Price & Portfolio Weight Chart */}
        {price_weight_series.length > 1 && (() => {
          const priceData = priceZoom.zoomData(price_weight_series, "date");
          const priceDates = new Set(priceData.map((d) => d.date));
          return (
          <div className="portfolio-chart">
            <div className="portfolio-chart__header">
              <div className="portfolio-chart__title">
                Price &amp; Portfolio Weight
              </div>
              <div className="portfolio-chart__header-controls">
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
                {priceZoom.isZoomed && (
                  <button className="portfolio-chart__zoom-reset" onClick={priceZoom.handleResetZoom}>
                    Reset Zoom
                  </button>
                )}
              </div>
            </div>
            <div
              className={`portfolio-chart__container${priceZoom.isZoomed ? " portfolio-chart__container--zoomed" : " portfolio-chart__container--zoomable"}`}
              onDoubleClick={priceZoom.isZoomed ? priceZoom.handleResetZoom : undefined}
            >
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart
                data={priceData}
                onMouseDown={priceZoom.handleMouseDown as (e: unknown) => void}
                onMouseMove={priceZoom.handleMouseMove as (e: unknown) => void}
                onMouseUp={priceZoom.handleMouseUp}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v: string) => v.slice(0, 7)}
                  interval={Math.max(0, Math.floor(priceData.length / 8) - 1)}
                />
                <YAxis
                  yAxisId="price"
                  tickFormatter={(v: number) => `$${v}`}
                  tick={{ fontSize: 11 }}
                  domain={["auto", "auto"]}
                />
                <YAxis
                  yAxisId="weight"
                  orientation="right"
                  tickFormatter={weightMode === "%" ? (v: number) => `${v}%` : (v: number) => formatCurrency(v)}
                  tick={{ fontSize: 11 }}
                />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null;
                    const dateStr = String(label);
                    const earningsLabel = earningsDateToLabel.get(dateStr);
                    const dateTrades = tradeDateMap.get(dateStr);
                    return (
                      <div className="recharts-default-tooltip" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", padding: "8px 12px", fontSize: "0.8rem" }}>
                        <p style={{ margin: 0, fontWeight: 600 }}>
                          {dateStr}
                          {earningsLabel && <span style={{ color: "#718096", fontWeight: 400 }}> — {earningsLabel}</span>}
                        </p>
                        {payload.map((entry, i) => (
                          <p key={i} style={{ margin: "2px 0 0", color: entry.color }}>
                            {entry.name}: {entry.name === (weightMode === "%" ? "Portfolio %" : "Portfolio $")
                              ? (weightMode === "%" ? `${Number(entry.value).toFixed(2)}%` : formatCurrency(Number(entry.value)))
                              : `$${Number(entry.value).toFixed(2)}`}
                          </p>
                        ))}
                        {dateTrades && dateTrades.length > 0 && (
                          <div style={{ borderTop: "1px solid var(--color-border)", marginTop: 4, paddingTop: 4 }}>
                            {dateTrades.map((t, i) => (
                              <p key={i} style={{ margin: i > 0 ? "3px 0 0" : 0, color: t.action === "buy" ? "#38a169" : "#e53e3e" }}>
                                {t.action.charAt(0).toUpperCase() + t.action.slice(1)} {t.shares.toLocaleString()} @ ${t.price.toFixed(2)}
                                <span style={{ color: "var(--color-text-secondary)" }}> ({formatCurrency(t.notional)})</span>
                              </p>
                            ))}
                          </div>
                        )}
                      </div>
                    );
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
                  dot={(props: Record<string, unknown>) => {
                    const { cx, cy, payload, key } = props as { cx: number; cy: number; payload: { date: string }; key: string };
                    const dateTrades = tradeDateMap.get(payload.date);
                    if (!dateTrades?.length) return <g key={key} />;
                    const hasBuy = dateTrades.some((t) => t.action === "buy");
                    const hasSell = dateTrades.some((t) => t.action === "sell");
                    if (hasBuy && hasSell) {
                      return (
                        <g key={key}>
                          <circle cx={cx} cy={cy - 4} r={4} fill="#38a169" stroke="#fff" strokeWidth={1.5} />
                          <circle cx={cx} cy={cy + 4} r={4} fill="#e53e3e" stroke="#fff" strokeWidth={1.5} />
                        </g>
                      );
                    }
                    return (
                      <circle key={key} cx={cx} cy={cy} r={4}
                        fill={hasBuy ? "#38a169" : "#e53e3e"}
                        stroke="#fff" strokeWidth={1.5}
                      />
                    );
                  }}
                  activeDot={((props: Record<string, unknown>) => {
                    const { cx, cy, payload, key } = props as { cx: number; cy: number; payload: { date: string }; key: string };
                    const dateTrades = tradeDateMap.get(payload?.date);
                    if (!dateTrades?.length) {
                      return <circle key={key} cx={cx} cy={cy} r={4} fill="#1a202c" stroke="#fff" strokeWidth={2} />;
                    }
                    const hasBuy = dateTrades.some((t) => t.action === "buy");
                    const hasSell = dateTrades.some((t) => t.action === "sell");
                    if (hasBuy && hasSell) {
                      return (
                        <g key={key}>
                          <circle cx={cx} cy={cy - 4} r={5} fill="#38a169" stroke="#fff" strokeWidth={2} />
                          <circle cx={cx} cy={cy + 4} r={5} fill="#e53e3e" stroke="#fff" strokeWidth={2} />
                        </g>
                      );
                    }
                    return (
                      <circle key={key} cx={cx} cy={cy} r={5}
                        fill={hasBuy ? "#38a169" : "#e53e3e"}
                        stroke="#fff" strokeWidth={2}
                      />
                    );
                  }) as never}
                  strokeWidth={2}
                  hide={weightHidden.has("stock_price")}
                />
                {earningsData?.all_earnings
                  ?.filter((e) => priceDates.has(e.report_date))
                  .map((e) => (
                    <ReferenceLine
                      key={`pw-earn-${e.report_date}`}
                      x={e.report_date}
                      yAxisId="price"
                      stroke="#a0aec0"
                      strokeDasharray="4 3"
                      strokeWidth={1}
                    />
                  ))}
                {priceZoom.selectingLeft && priceZoom.selectingRight && (
                  <ReferenceArea
                    yAxisId="price"
                    x1={priceZoom.selectingLeft}
                    x2={priceZoom.selectingRight}
                    strokeOpacity={0.3}
                    fill="#3182ce"
                    fillOpacity={0.15}
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>
            </div>
          </div>
          );
        })()}

        {/* Cumulative PnL Chart */}
        {pnl_series.length > 1 && (() => {
          const pnlData = pnlZoom.zoomData(pnl_series, "date");
          const pnlDates = new Set(pnlData.map((d) => d.date));
          return (
          <div className="portfolio-chart">
            <div className="portfolio-chart__header">
              <div className="portfolio-chart__title">Cumulative PnL</div>
              <div className="portfolio-chart__header-controls">
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
                {pnlZoom.isZoomed && (
                  <button className="portfolio-chart__zoom-reset" onClick={pnlZoom.handleResetZoom}>
                    Reset Zoom
                  </button>
                )}
              </div>
            </div>
            <div
              className={`portfolio-chart__container${pnlZoom.isZoomed ? " portfolio-chart__container--zoomed" : " portfolio-chart__container--zoomable"}`}
              onDoubleClick={pnlZoom.isZoomed ? pnlZoom.handleResetZoom : undefined}
            >
            <ResponsiveContainer width="100%" height={300}>
              <LineChart
                data={pnlData}
                onMouseDown={pnlZoom.handleMouseDown as (e: unknown) => void}
                onMouseMove={pnlZoom.handleMouseMove as (e: unknown) => void}
                onMouseUp={pnlZoom.handleMouseUp}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis
                  tickFormatter={pnlMode === "$" ? (v: number) => formatCurrency(v) : (v: number) => `${v.toFixed(1)}%`}
                  tick={{ fontSize: 11 }}
                  domain={["auto", "auto"]}
                />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null;
                    const dateStr = String(label);
                    const earningsLabel = earningsDateToLabel.get(dateStr);
                    return (
                      <div className="recharts-default-tooltip" style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", padding: "8px 12px", fontSize: "0.8rem" }}>
                        <p style={{ margin: 0, fontWeight: 600 }}>
                          {dateStr}
                          {earningsLabel && <span style={{ color: "#718096", fontWeight: 400 }}> — {earningsLabel}</span>}
                        </p>
                        {payload.map((entry, i) => (
                          <p key={i} style={{ margin: "2px 0 0", color: entry.color }}>
                            {entry.name}: {pnlMode === "$" ? formatDollar(Number(entry.value)) : `${Number(entry.value).toFixed(2)}%`}
                          </p>
                        ))}
                      </div>
                    );
                  }}
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
                {earningsData?.all_earnings
                  ?.filter((e) => pnlDates.has(e.report_date))
                  .map((e) => (
                    <ReferenceLine
                      key={`pnl-earn-${e.report_date}`}
                      x={e.report_date}
                      stroke="#a0aec0"
                      strokeDasharray="4 3"
                      strokeWidth={1}
                    />
                  ))}
                {pnlZoom.selectingLeft && pnlZoom.selectingRight && (
                  <ReferenceArea
                    x1={pnlZoom.selectingLeft}
                    x2={pnlZoom.selectingRight}
                    strokeOpacity={0.3}
                    fill="#3182ce"
                    fillOpacity={0.15}
                  />
                )}
              </LineChart>
            </ResponsiveContainer>
            </div>
          </div>
          );
        })()}
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
