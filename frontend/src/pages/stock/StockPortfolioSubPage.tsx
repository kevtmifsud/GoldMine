import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ColDef, GridApi } from "ag-grid-community";
import Plot from "react-plotly.js";
import api from "../../config/api";
import { EarningsDetailDialog } from "../../components/EarningsDetailDialog";
import { AppGrid } from "../../components/ag-grid/AppGrid";
import { createEntityLinkRenderer } from "../../components/ag-grid/EntityLinkRenderer";
import { useGridColumnManager } from "../../hooks/useGridColumnManager";
import { StockViewToolbar } from "../../components/StockViewToolbar";
import { useStockEntity } from "./StockEntityPage";
import { StockSummaryBar } from "../../components/StockSummaryBar";
import type {
  TickerPortfolioData,
  TradeRecord,
  OpenPosition,
} from "../../types/portfolio";
import {
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

const PLOTLY_LAYOUT_DEFAULTS: Partial<Plotly.Layout> = {
  paper_bgcolor: "transparent",
  plot_bgcolor: "transparent",
  font: { family: "Inter, sans-serif", size: 11 },
  hovermode: "x unified" as Plotly.Layout["hovermode"],
  margin: { l: 55, r: 55, t: 8, b: 55 },
};

const PLOTLY_CONFIG: Partial<Plotly.Config> = {
  displayModeBar: false,
  responsive: true,
};

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
  const { hiddenKeys: weightHidden, handleToggle: weightToggle } = useToggleableLegend();
  const { hiddenKeys: pnlChartHidden, handleToggle: pnlChartToggle } = useToggleableLegend();

  useEffect(() => {
    setLoading(true);
    setError(null);
    const params: Record<string, string> = {};
    if (selectedPortfolio) params.portfolio = selectedPortfolio;
    api
      .get<TickerPortfolioData>(`/api/portfolio/${detail.entity_id}`, { params })
      .then((resp) => {
        setData(resp.data);
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
        {price_weight_series.length > 1 && (
          <PriceWeightChart
            priceWeightSeries={price_weight_series}
            weightMode={weightMode}
            setWeightMode={setWeightMode}
            areaColor={areaColor}
            weightHidden={weightHidden}
            weightToggle={weightToggle}
            tradeDateMap={tradeDateMap}
            earningsData={earningsData}
            earningsDateToLabel={earningsDateToLabel}
          />
        )}

        {/* Cumulative PnL Chart */}
        {pnl_series.length > 1 && (
          <PnlChart
            pnlSeries={pnl_series}
            pnlMode={pnlMode}
            setPnlMode={setPnlMode}
            pnlChartHidden={pnlChartHidden}
            pnlChartToggle={pnlChartToggle}
            earningsData={earningsData}
            earningsDateToLabel={earningsDateToLabel}
          />
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

// ---- Price & Portfolio Weight chart component ----

interface PriceWeightChartProps {
  priceWeightSeries: TickerPortfolioData["price_weight_series"];
  weightMode: "%" | "$";
  setWeightMode: (mode: "%" | "$") => void;
  areaColor: string;
  weightHidden: Set<string>;
  weightToggle: (key: string) => void;
  tradeDateMap: Map<string, TradeRecord[]>;
  earningsData: EarningsData | null;
  earningsDateToLabel: Map<string, string>;
}

function PriceWeightChart({
  priceWeightSeries,
  weightMode,
  setWeightMode,
  areaColor,
  weightHidden,
  weightToggle,
  tradeDateMap,
  earningsData,
  earningsDateToLabel,
}: PriceWeightChartProps) {
  const weightDataKey = weightMode === "%" ? "portfolio_pct" : "portfolio_dollars";
  const weightLabel = weightMode === "%" ? "Portfolio %" : "Portfolio $";
  const priceLabel = "Stock Price";

  const weightVisible = !weightHidden.has(weightDataKey);
  const priceVisible = !weightHidden.has("stock_price");

  const earningsLines = useMemo(() => {
    if (!earningsData?.all_earnings) return [];
    const dateSet = new Set(priceWeightSeries.map((d) => d.date));
    return earningsData.all_earnings
      .filter((e) => dateSet.has(e.report_date))
      .map((e) => e.report_date);
  }, [earningsData, priceWeightSeries]);

  const { plotData, plotLayout } = useMemo(() => {
    const xData = priceWeightSeries.map((d) => d.date);
    const weightYData = priceWeightSeries.map((d) => (d as unknown as Record<string, number>)[weightDataKey]);
    const priceYData = priceWeightSeries.map((d) => d.stock_price);

    // Build trade marker arrays
    const buyX: string[] = [];
    const buyY: number[] = [];
    const sellX: string[] = [];
    const sellY: number[] = [];
    for (const d of priceWeightSeries) {
      if (d.stock_price == null) continue;
      const trades = tradeDateMap.get(d.date);
      if (trades?.length) {
        const hasBuy = trades.some((t) => t.action === "buy");
        const hasSell = trades.some((t) => t.action === "sell");
        if (hasBuy) {
          buyX.push(d.date);
          buyY.push(d.stock_price);
        }
        if (hasSell) {
          sellX.push(d.date);
          sellY.push(d.stock_price);
        }
      }
    }

    // Build custom hover text for price series
    const priceHoverText = priceWeightSeries.map((d) => {
      const parts: string[] = [];
      const earningsLabel = earningsDateToLabel.get(d.date);
      if (earningsLabel) parts.push(`<b>${d.date}</b> - ${earningsLabel}`);
      else parts.push(`<b>${d.date}</b>`);

      if (d.stock_price != null) parts.push(`${priceLabel}: $${d.stock_price.toFixed(2)}`);

      const wVal = (d as unknown as Record<string, number>)[weightDataKey];
      if (wVal != null) {
        const wFormatted = weightMode === "%" ? `${Number(wVal).toFixed(2)}%` : formatCurrency(Number(wVal));
        parts.push(`${weightLabel}: ${wFormatted}`);
      }

      const dateTrades = tradeDateMap.get(d.date);
      if (dateTrades?.length) {
        parts.push("");
        for (const t of dateTrades) {
          parts.push(`${t.action.charAt(0).toUpperCase() + t.action.slice(1)} ${t.shares.toLocaleString()} @ $${t.price.toFixed(2)} (${formatCurrency(t.notional)})`);
        }
      }

      return parts.join("<br>");
    });

    const traces: Plotly.Data[] = [];

    // Weight area trace (on y2)
    traces.push({
      type: "scatter",
      mode: "lines",
      name: weightLabel,
      x: xData,
      y: weightYData,
      yaxis: "y2",
      line: { color: areaColor, width: 1, shape: "hv" },
      fill: "tozeroy",
      fillcolor: areaColor.replace(")", ", 0.15)").replace("rgb", "rgba").replace("#e53e3e", "rgba(229,62,62,0.15)").replace("#38a169", "rgba(56,161,105,0.15)"),
      opacity: 0.4,
      visible: weightVisible ? true : "legendonly",
      hoverinfo: "skip",
    } as Plotly.Data);

    // Fix fillcolor for hex colors
    const weightTrace = traces[0] as Partial<Plotly.PlotData>;
    if (areaColor === "#e53e3e") {
      weightTrace.fillcolor = "rgba(229,62,62,0.15)";
      if (weightTrace.line) (weightTrace.line as Partial<Plotly.ScatterLine>).color = "#e53e3e";
    } else if (areaColor === "#38a169") {
      weightTrace.fillcolor = "rgba(56,161,105,0.15)";
      if (weightTrace.line) (weightTrace.line as Partial<Plotly.ScatterLine>).color = "#38a169";
    }

    // Price line trace (on y1)
    traces.push({
      type: "scatter",
      mode: "lines",
      name: priceLabel,
      x: xData,
      y: priceYData,
      yaxis: "y",
      line: { color: "#1a202c", width: 2 },
      visible: priceVisible ? true : "legendonly",
      text: priceHoverText,
      hoverinfo: "text",
    });

    // Trade buy markers
    if (buyX.length > 0) {
      traces.push({
        type: "scatter",
        mode: "markers",
        name: "Buy",
        x: buyX,
        y: buyY,
        yaxis: "y",
        marker: { color: "#38a169", size: 8, symbol: "circle" },
        showlegend: false,
        hoverinfo: "skip",
      } as Plotly.Data);
    }

    // Trade sell markers
    if (sellX.length > 0) {
      traces.push({
        type: "scatter",
        mode: "markers",
        name: "Sell",
        x: sellX,
        y: sellY,
        yaxis: "y",
        marker: { color: "#e53e3e", size: 8, symbol: "circle" },
        showlegend: false,
        hoverinfo: "skip",
      } as Plotly.Data);
    }

    // Earnings vertical lines as shapes
    const shapes: Partial<Plotly.Shape>[] = earningsLines.map((date) => ({
      type: "line",
      x0: date,
      x1: date,
      y0: 0,
      y1: 1,
      yref: "paper",
      line: { color: "#a0aec0", dash: "dash", width: 1 },
    }));

    const layout: Partial<Plotly.Layout> = {
      ...PLOTLY_LAYOUT_DEFAULTS,
      margin: { l: 55, r: 55, t: 8, b: 55 },
      xaxis: {
        type: "date",
        tickformat: "%b '%y",
        hoverformat: "%-m/%-d/%Y",
        nticks: 8,
        tickfont: { size: 11 },
        rangeslider: { visible: false },
      },
      yaxis: {
        title: { text: "Price", font: { size: 10 } },
        tickformat: "$,.0f",
        tickfont: { size: 11 },
        gridcolor: "#e2e8f0",
        griddash: "dash",
        autorange: true,
      },
      yaxis2: {
        title: { text: weightMode === "%" ? "Weight %" : "Weight $", font: { size: 10 } },
        tickfont: { size: 11 },
        overlaying: "y",
        side: "right",
        showgrid: false,
        tickformat: weightMode === "%" ? ".1f" : "$,.0f",
        ticksuffix: weightMode === "%" ? "%" : "",
      },
      legend: {
        orientation: "h",
        y: -0.12,
        x: 0.5,
        xanchor: "center",
        font: { size: 10 },
        tracegroupgap: 5,
      },
      shapes,
    };

    return { plotData: traces, plotLayout: layout };
  }, [priceWeightSeries, weightMode, weightDataKey, weightLabel, priceLabel, areaColor,
      weightVisible, priceVisible, tradeDateMap, earningsLines, earningsDateToLabel]);

  const handleLegendClick = useCallback((event: Plotly.LegendClickEvent): boolean => {
    const traceName = (plotData[event.curveNumber] as Partial<Plotly.PlotData>)?.name;
    if (traceName === weightLabel) {
      weightToggle(weightDataKey);
      return false; // prevent default plotly legend toggle
    }
    if (traceName === priceLabel) {
      weightToggle("stock_price");
      return false;
    }
    return true;
  }, [weightLabel, weightDataKey, priceLabel, weightToggle, plotData]);

  return (
    <div className="portfolio-chart">
      <div className="portfolio-chart__header">
        <div className="portfolio-chart__title">Price &amp; Portfolio Weight</div>
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
        </div>
      </div>
      <Plot
        data={plotData}
        layout={plotLayout}
        config={PLOTLY_CONFIG}
        style={{ width: "100%", height: 300 }}
        useResizeHandler
        onLegendClick={handleLegendClick}
      />
    </div>
  );
}

// ---- Cumulative PnL chart component ----

interface PnlChartProps {
  pnlSeries: TickerPortfolioData["pnl_series"];
  pnlMode: "$" | "%";
  setPnlMode: (mode: "$" | "%") => void;
  pnlChartHidden: Set<string>;
  pnlChartToggle: (key: string) => void;
  earningsData: EarningsData | null;
  earningsDateToLabel: Map<string, string>;
}

function PnlChart({
  pnlSeries,
  pnlMode,
  setPnlMode,
  pnlChartHidden,
  pnlChartToggle,
  earningsData,
  earningsDateToLabel,
}: PnlChartProps) {
  const cumKey = pnlMode === "$" ? "cumulative_pnl" : "cumulative_pnl_pct";
  const realKey = pnlMode === "$" ? "realized_pnl" : "realized_pnl_pct";
  const cumLabel = "Cumulative PnL";
  const realLabel = "Realized PnL";

  const cumVisible = !pnlChartHidden.has(cumKey);
  const realVisible = !pnlChartHidden.has(realKey);

  const earningsLines = useMemo(() => {
    if (!earningsData?.all_earnings) return [];
    const dateSet = new Set(pnlSeries.map((d) => d.date));
    return earningsData.all_earnings
      .filter((e) => dateSet.has(e.report_date))
      .map((e) => e.report_date);
  }, [earningsData, pnlSeries]);

  const { plotData, plotLayout } = useMemo(() => {
    const xData = pnlSeries.map((d) => d.date);
    const cumYData = pnlSeries.map((d) => (d as unknown as Record<string, number>)[cumKey]);
    const realYData = pnlSeries.map((d) => (d as unknown as Record<string, number>)[realKey]);

    // Build custom hover text
    const hoverText = pnlSeries.map((d) => {
      const parts: string[] = [];
      const earningsLabel = earningsDateToLabel.get(d.date);
      if (earningsLabel) parts.push(`<b>${d.date}</b> - ${earningsLabel}`);
      else parts.push(`<b>${d.date}</b>`);

      const cumVal = (d as unknown as Record<string, number>)[cumKey];
      if (cumVal != null) {
        const formatted = pnlMode === "$" ? formatDollar(cumVal) : `${cumVal.toFixed(2)}%`;
        parts.push(`${cumLabel}: ${formatted}`);
      }

      const realVal = (d as unknown as Record<string, number>)[realKey];
      if (realVal != null) {
        const formatted = pnlMode === "$" ? formatDollar(realVal) : `${realVal.toFixed(2)}%`;
        parts.push(`${realLabel}: ${formatted}`);
      }

      return parts.join("<br>");
    });

    const traces: Plotly.Data[] = [
      {
        type: "scatter",
        mode: "lines",
        name: cumLabel,
        x: xData,
        y: cumYData,
        line: { color: "#3182ce", width: 2 },
        visible: cumVisible ? true : "legendonly",
        text: hoverText,
        hoverinfo: "text",
      },
      {
        type: "scatter",
        mode: "lines",
        name: realLabel,
        x: xData,
        y: realYData,
        line: { color: "#38a169", width: 2 },
        visible: realVisible ? true : "legendonly",
        hoverinfo: "skip",
      } as Plotly.Data,
    ];

    // Earnings vertical lines as shapes
    const shapes: Partial<Plotly.Shape>[] = earningsLines.map((date) => ({
      type: "line",
      x0: date,
      x1: date,
      y0: 0,
      y1: 1,
      yref: "paper",
      line: { color: "#a0aec0", dash: "dash", width: 1 },
    }));

    const layout: Partial<Plotly.Layout> = {
      ...PLOTLY_LAYOUT_DEFAULTS,
      margin: { l: 55, r: 12, t: 8, b: 55 },
      xaxis: {
        type: "date",
        tickformat: "%b '%y",
        hoverformat: "%-m/%-d/%Y",
        nticks: 8,
        tickfont: { size: 11 },
        rangeslider: { visible: false },
      },
      yaxis: {
        tickformat: pnlMode === "$" ? "$,.0f" : ".1f",
        ticksuffix: pnlMode === "%" ? "%" : "",
        tickfont: { size: 11 },
        gridcolor: "#e2e8f0",
        griddash: "dash",
        autorange: true,
      },
      legend: {
        orientation: "h",
        y: -0.12,
        x: 0.5,
        xanchor: "center",
        font: { size: 10 },
        tracegroupgap: 5,
      },
      shapes,
    };

    return { plotData: traces, plotLayout: layout };
  }, [pnlSeries, pnlMode, cumKey, realKey, cumLabel, realLabel, cumVisible, realVisible, earningsLines, earningsDateToLabel]);

  const handleLegendClick = useCallback((event: Plotly.LegendClickEvent): boolean => {
    const traceName = (plotData[event.curveNumber] as Partial<Plotly.PlotData>)?.name;
    if (traceName === cumLabel) {
      pnlChartToggle(cumKey);
      return false;
    }
    if (traceName === realLabel) {
      pnlChartToggle(realKey);
      return false;
    }
    return true;
  }, [cumLabel, realLabel, cumKey, realKey, pnlChartToggle, plotData]);

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
        </div>
      </div>
      <Plot
        data={plotData}
        layout={plotLayout}
        config={PLOTLY_CONFIG}
        style={{ width: "100%", height: 300 }}
        useResizeHandler
        onLegendClick={handleLegendClick}
      />
    </div>
  );
}
