import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ColDef, GridApi } from "ag-grid-community";
import {
  ComposedChart,
  LineChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { Layout } from "../components/Layout";
import { AppGrid } from "../components/ag-grid/AppGrid";
import { createEntityLinkRenderer } from "../components/ag-grid/EntityLinkRenderer";
import { useGridColumnManager } from "../hooks/useGridColumnManager";
import api from "../config/api";
import type {
  EntityDetail,
  EntityField,
  PaginatedResponse,
} from "../types/entities";
import {
  ToggleableLegend,
  useToggleableLegend,
} from "../components/ToggleableLegend";
import { ResearchSearchBar } from "../components/ResearchSearchBar";
import "../styles/portfolio.css";
import "../styles/portfolios-page.css";

interface PositionRow {
  ticker: string;
  side: string;
  shares: string;
  cost_basis: string;
  current_price: string;
  exposure_dollars: string;
  exposure_pct: string;
  pnl: string;
  pnl_pct: string;
  sector: string;
  industry: string;
  company_name?: string;
  market_cap_b?: string;
  pe_ratio?: string;
  "52w_high"?: string;
  "52w_low"?: string;
  dividend_yield?: string;
  eps?: string;
  revenue_b?: string;
}

interface DailyPnlRow {
  date: string;
  cumulative_pnl: string;
  [key: string]: string;
}

interface ComparisonDataPoint {
  date: string;
  [key: string]: string | number;
}

interface ComparisonResponse {
  series: ComparisonDataPoint[];
  portfolios: string[];
}

function formatCurrency(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}B`;
  if (abs >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
}

function formatPct(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function pnlClass(value: number): string {
  if (value > 0) return "portfolio-summary-card__value--positive";
  if (value < 0) return "portfolio-summary-card__value--negative";
  return "";
}

function getHeaderValue(fields: EntityField[], label: string): string | null {
  const f = fields.find((h) => h.label === label);
  return f?.value ?? null;
}

function parseNumeric(val: string | null): number {
  if (!val) return 0;
  return parseFloat(val.replace(/[^0-9.\-]/g, "")) || 0;
}

const StockLinkRenderer = createEntityLinkRenderer({ entityType: "stock" });

const PORTFOLIO_COLORS: Record<string, string> = {
  Flagship: "#3182ce",
  "Long Only": "#38a169",
};
const SP500_COLOR = "#718096";
const INDUSTRY_PALETTE = [
  "#3182ce",
  "#38a169",
  "#805ad5",
  "#d53f8c",
  "#dd6b20",
  "#319795",
  "#975a16",
  "#2b6cb0",
];

export function PortfoliosPage() {
  const [portfolioNames, setPortfolioNames] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<EntityDetail | null>(null);
  const [positions, setPositions] = useState<PositionRow[]>([]);
  const [ytdPnl, setYtdPnl] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const gridApiRef = useRef<GridApi<PositionRow> | null>(null);
  const [comparisonData, setComparisonData] = useState<ComparisonDataPoint[]>([]);
  const [_comparisonPortfolios, setComparisonPortfolios] = useState<string[]>([]);
  const [groupBy, setGroupBy] = useState<"sector" | "industry">("sector");
  const [breakdownData, setBreakdownData] = useState<ComparisonDataPoint[]>([]);
  const [breakdownGroups, setBreakdownGroups] = useState<string[]>([]);
  const { hiddenKeys: perfHidden, handleToggle: perfToggle, handleSolo: perfSolo } = useToggleableLegend();
  const { hiddenKeys: breakdownHidden, handleToggle: breakdownToggle, handleSolo: breakdownSolo } = useToggleableLegend();
  const [perfMode, setPerfMode] = useState<"$" | "%">("%");
  const [breakdownMode, setBreakdownMode] = useState<"$" | "%">("%");
  const [startDate, setStartDate] = useState<string>("2022-01-01");
  const [appliedStartDate, setAppliedStartDate] = useState<string>("2022-01-01");

  // Fetch comparison chart data when appliedStartDate changes
  useEffect(() => {
    api
      .get<ComparisonResponse>("/api/entities/portfolio/comparison", {
        params: { start_date: appliedStartDate },
      })
      .then((resp) => {
        setComparisonData(resp.data.series);
        setComparisonPortfolios(resp.data.portfolios);
      })
      .catch(() => {
        // Silently fail — chart is supplemental
      });
  }, [appliedStartDate]);

  // Fetch breakdown chart data when portfolio, groupBy, or appliedStartDate changes
  useEffect(() => {
    if (!selected) return;
    const safeName = encodeURIComponent(selected);
    api
      .get<{ series: ComparisonDataPoint[]; groups: string[] }>(
        `/api/entities/portfolio/${safeName}/daily-pnl-by-group`,
        { params: { group_by: groupBy, start_date: appliedStartDate } }
      )
      .then((resp) => {
        setBreakdownData(resp.data.series);
        setBreakdownGroups(resp.data.groups);
      })
      .catch(() => {
        setBreakdownData([]);
        setBreakdownGroups([]);
      });
  }, [selected, groupBy, appliedStartDate]);

  // Fetch portfolio names on mount
  useEffect(() => {
    api
      .get<PaginatedResponse>("/api/data/portfolios", {
        params: { page_size: 10 },
      })
      .then((resp) => {
        const names = resp.data.data.map(
          (d) => d.name as string
        );
        setPortfolioNames(names);
        if (names.length > 0 && !selected) {
          setSelected(names[0]);
        }
      })
      .catch(() => setError("Failed to load portfolios"));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch detail + positions + daily PnL for selected portfolio
  useEffect(() => {
    if (!selected) return;
    setLoading(true);
    setError(null);

    const safeName = encodeURIComponent(selected);

    const detailReq = api.get<EntityDetail>(
      `/api/entities/portfolio/${safeName}`
    );
    const positionsReq = api.get<PaginatedResponse<PositionRow>>(
      `/api/entities/portfolio/${safeName}/positions`,
      { params: { page_size: 500 } }
    );
    const dailyPnlReq = api.get<PaginatedResponse<DailyPnlRow>>(
      `/api/entities/portfolio/${safeName}/daily-pnl`,
      { params: { page_size: 5000 } }
    );

    Promise.all([detailReq, positionsReq, dailyPnlReq])
      .then(([detailResp, posResp, pnlResp]) => {
        setDetail(detailResp.data);
        setPositions(posResp.data.data);

        // Compute YTD PnL from daily series
        const series = pnlResp.data.data;
        if (series.length > 0) {
          const lastCum = parseFloat(series[series.length - 1].cumulative_pnl) || 0;
          // Find Dec 31 of the previous year or the last data point before Jan 1
          const yearStart = `${new Date().getFullYear()}-01-01`;
          let eoyValue = 0;
          for (let i = series.length - 1; i >= 0; i--) {
            if (series[i].date < yearStart) {
              eoyValue = parseFloat(series[i].cumulative_pnl) || 0;
              break;
            }
          }
          setYtdPnl(lastCum - eoyValue);
        } else {
          setYtdPnl(null);
        }
      })
      .catch(() => setError("Failed to load portfolio data"))
      .finally(() => setLoading(false));
  }, [selected]);

  const handleToggle = useCallback((name: string) => {
    setSelected(name);
  }, []);

  const handleGridReady = useCallback(
    (e: { api: GridApi<PositionRow> }) => {
      gridApiRef.current = e.api;
    },
    []
  );

  const allColumns = useMemo<ColDef<PositionRow>[]>(
    () => [
      { field: "ticker", headerName: "Ticker", sort: "asc", cellRenderer: StockLinkRenderer },
      {
        field: "side",
        headerName: "Side",
        width: 100,
        valueFormatter: (p) => p.value ? p.value.charAt(0).toUpperCase() + p.value.slice(1).toLowerCase() : "",
        cellStyle: (params) => ({
          color:
            params.value === "long"
              ? "var(--color-success)"
              : "var(--color-error)",
          fontWeight: 600,
        }),
      },
      {
        field: "shares",
        headerName: "Shares",
        type: "numericColumn",
        valueGetter: (p) => (p.data ? parseFloat(p.data.shares) : null),
        valueFormatter: (p) =>
          p.value != null ? Number(p.value).toLocaleString() : "",
      },
      {
        field: "cost_basis",
        headerName: "Cost Basis",
        type: "numericColumn",
        valueGetter: (p) => (p.data ? parseFloat(p.data.cost_basis) : null),
        valueFormatter: (p) =>
          p.value != null ? `$${Number(p.value).toFixed(2)}` : "",
      },
      {
        field: "current_price",
        headerName: "Current Price",
        type: "numericColumn",
        valueGetter: (p) =>
          p.data ? parseFloat(p.data.current_price) : null,
        valueFormatter: (p) =>
          p.value != null ? `$${Number(p.value).toFixed(2)}` : "",
      },
      {
        field: "exposure_dollars",
        headerName: "Exposure ($)",
        type: "numericColumn",
        valueGetter: (p) =>
          p.data
            ? parseFloat(p.data.exposure_dollars.replace(/,/g, ""))
            : null,
        valueFormatter: (p) =>
          p.value != null
            ? `$${Number(p.value).toLocaleString()}`
            : "",
      },
      { field: "exposure_pct", headerName: "Exposure (%)", width: 120 },
      {
        field: "pnl",
        headerName: "PnL ($)",
        type: "numericColumn",
        valueGetter: (p) =>
          p.data ? parseFloat(p.data.pnl.replace(/,/g, "")) : null,
        valueFormatter: (p) =>
          p.value != null
            ? `$${Number(p.value).toLocaleString()}`
            : "",
        cellStyle: (params) => {
          if (params.value > 0) return { color: "var(--color-success)" };
          if (params.value < 0) return { color: "var(--color-error)" };
          return null;
        },
      },
      {
        field: "pnl_pct",
        headerName: "PnL (%)",
        width: 110,
        type: "numericColumn",
        valueGetter: (p) => (p.data ? parseFloat(p.data.pnl_pct) : null),
        valueFormatter: (p) => (p.value != null ? `${Number(p.value).toFixed(1)}%` : ""),
        cellStyle: (params) => {
          if (params.value > 0) return { color: "var(--color-success)" };
          if (params.value < 0) return { color: "var(--color-error)" };
          return null;
        },
      },
      { field: "sector", headerName: "Sector" },
      { field: "industry", headerName: "Industry" },
      { field: "company_name", headerName: "Company" },
      {
        field: "market_cap_b",
        headerName: "Market Cap ($B)",
        type: "numericColumn",
        valueGetter: (p) => (p.data?.market_cap_b ? parseFloat(p.data.market_cap_b) : null),
        valueFormatter: (p) => (p.value != null ? Number(p.value).toFixed(1) : ""),
      },
      {
        field: "pe_ratio",
        headerName: "P/E Ratio",
        type: "numericColumn",
        valueGetter: (p) => (p.data?.pe_ratio ? parseFloat(p.data.pe_ratio) : null),
        valueFormatter: (p) => (p.value != null ? Number(p.value).toFixed(1) : ""),
      },
      {
        field: "52w_high",
        headerName: "52W High",
        type: "numericColumn",
        valueGetter: (p) => (p.data?.["52w_high"] ? parseFloat(p.data["52w_high"]) : null),
        valueFormatter: (p) => (p.value != null ? `$${Number(p.value).toFixed(2)}` : ""),
      },
      {
        field: "52w_low",
        headerName: "52W Low",
        type: "numericColumn",
        valueGetter: (p) => (p.data?.["52w_low"] ? parseFloat(p.data["52w_low"]) : null),
        valueFormatter: (p) => (p.value != null ? `$${Number(p.value).toFixed(2)}` : ""),
      },
      {
        field: "dividend_yield",
        headerName: "Dividend Yield",
        type: "numericColumn",
        valueGetter: (p) => (p.data?.dividend_yield ? parseFloat(p.data.dividend_yield) : null),
        valueFormatter: (p) => (p.value != null ? `${Number(p.value).toFixed(2)}%` : ""),
      },
      {
        field: "eps",
        headerName: "EPS",
        type: "numericColumn",
        valueGetter: (p) => (p.data?.eps ? parseFloat(p.data.eps) : null),
        valueFormatter: (p) => (p.value != null ? `$${Number(p.value).toFixed(2)}` : ""),
      },
      {
        field: "revenue_b",
        headerName: "Revenue ($B)",
        type: "numericColumn",
        valueGetter: (p) => (p.data?.revenue_b ? parseFloat(p.data.revenue_b) : null),
        valueFormatter: (p) => (p.value != null ? Number(p.value).toFixed(1) : ""),
      },
    ],
    []
  );

  const defaultVisibleFields = useMemo(
    () => [
      "ticker", "side", "shares", "cost_basis", "current_price",
      "exposure_dollars", "exposure_pct", "pnl", "pnl_pct", "sector", "industry",
    ],
    []
  );

  const { columnDefs, contextMenuConfig } =
    useGridColumnManager<PositionRow>({
      gridId: "portfolios-positions",
      allColumns,
      defaultVisibleFields,
    });

  // Extract summary values from header_fields
  const marketValue = detail
    ? parseNumeric(getHeaderValue(detail.header_fields, "Market Value"))
    : 0;
  const positionCount = detail
    ? getHeaderValue(detail.header_fields, "Positions")
    : "—";
  const totalPnl = detail
    ? parseNumeric(getHeaderValue(detail.header_fields, "Total PnL"))
    : 0;
  const totalCost = detail
    ? parseNumeric(getHeaderValue(detail.header_fields, "Total Cost"))
    : 0;
  const pnlPct = totalCost ? totalPnl / totalCost * 100 : 0;
  const ytdPnlPct = totalCost && ytdPnl !== null ? ytdPnl / totalCost * 100 : null;

  // Transform chart data: in $ mode, remap _dollars keys to base names;
  // in % mode, strip _dollars keys. This way Lines always use clean base names.
  const chartComparisonData = useMemo(() => {
    return comparisonData.map((point) => {
      const out: ComparisonDataPoint = { date: point.date };
      for (const [key, value] of Object.entries(point)) {
        if (key === "date") continue;
        // Always carry through market value under a stable key
        if (key.endsWith("_mv")) {
          out[key] = value;
          continue;
        }
        if (perfMode === "%") {
          if (!key.endsWith("_dollars")) out[key] = value;
        } else {
          if (key.endsWith("_dollars")) out[key.slice(0, -8)] = value;
        }
      }
      return out;
    });
  }, [comparisonData, perfMode]);

  const chartBreakdownData = useMemo(() => {
    return breakdownData.map((point) => {
      const out: ComparisonDataPoint = { date: point.date };
      for (const [key, value] of Object.entries(point)) {
        if (key === "date") continue;
        if (breakdownMode === "%") {
          if (!key.endsWith("_dollars")) out[key] = value;
        } else {
          if (key.endsWith("_dollars")) out[key.slice(0, -8)] = value;
        }
      }
      return out;
    });
  }, [breakdownData, breakdownMode]);

  // All dataKeys for each chart (for solo / double-click behavior)
  const perfAllKeys = useMemo(() => {
    const keys: string[] = [];
    if (selected) {
      keys.push(selected);
      keys.push(`${selected}_mv`);
    }
    if (selected !== "Flagship" && perfMode === "%") keys.push("S&P 500");
    return keys;
  }, [selected, perfMode]);

  const breakdownAllKeys = useMemo(() => {
    const keys: string[] = ["Total"];
    for (const g of breakdownGroups) {
      keys.push(g);
    }
    return keys;
  }, [breakdownGroups]);

  return (
    <Layout>
      <div className="portfolios-page">
        {/* Header + toggle */}
        <div className="portfolios-page__header">
          <h2 className="portfolios-page__title">Portfolios</h2>
          <div className="portfolios-page__date-picker">
            <span className="portfolios-page__date-label">Start</span>
            <input
              type="date"
              className="portfolios-page__date-input"
              value={startDate}
              min="2022-01-01"
              max={new Date().toISOString().slice(0, 10)}
              onChange={(e) => setStartDate(e.target.value)}
            />
            <button
              className="portfolios-page__apply-btn"
              disabled={startDate === appliedStartDate}
              onClick={() => setAppliedStartDate(startDate)}
              aria-label="Apply date filter"
            >
              &#x25B6;
            </button>
          </div>
          {portfolioNames.length > 0 && (
            <div className="portfolios-toggle">
              {portfolioNames.map((name) => (
                <button
                  key={name}
                  className={`portfolios-toggle__btn${selected === name ? " portfolios-toggle__btn--active" : ""}`}
                  onClick={() => handleToggle(name)}
                >
                  {name}
                </button>
              ))}
            </div>
          )}
        </div>

        {selected && (
          <ResearchSearchBar entityType="portfolio" entityId={selected} />
        )}

        {/* Charts row */}
        <div className="portfolios-page__charts-row">
          {/* Cumulative performance chart */}
          {comparisonData.length > 0 && (
            <div className="portfolios-page__chart-section">
              <div className="portfolios-page__chart-header">
                <div className="portfolios-page__chart-title">Cumulative Performance</div>
                <div className="portfolios-page__group-toggle">
                  <button
                    className={`portfolios-page__group-toggle-btn${perfMode === "%" ? " portfolios-page__group-toggle-btn--active" : ""}`}
                    onClick={() => setPerfMode("%")}
                  >
                    %
                  </button>
                  <button
                    className={`portfolios-page__group-toggle-btn${perfMode === "$" ? " portfolios-page__group-toggle-btn--active" : ""}`}
                    onClick={() => setPerfMode("$")}
                  >
                    $
                  </button>
                </div>
              </div>
              <ResponsiveContainer width="100%" height={350}>
                <ComposedChart data={chartComparisonData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 11 }}
                    tickFormatter={(d: string) => d.slice(0, 7)}
                    interval="preserveStartEnd"
                    minTickGap={60}
                  />
                  <YAxis
                    yAxisId="mv"
                    tick={{ fontSize: 11 }}
                    tickFormatter={(v: number) => formatCurrency(v)}
                  />
                  <YAxis
                    yAxisId="perf"
                    orientation="right"
                    tick={{ fontSize: 11 }}
                    tickFormatter={perfMode === "%"
                      ? (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`
                      : (v: number) => formatCurrency(v)
                    }
                  />
                  <Tooltip
                    formatter={((value: number, name: string) => {
                      if (name === "Portfolio Value") return [formatCurrency(value), name];
                      if (perfMode === "%") return [`${value >= 0 ? "+" : ""}${value.toFixed(1)}%`, name];
                      return [formatCurrency(value), name];
                    }) as never}
                  />
                  <Legend
                    content={(props) => (
                      <ToggleableLegend
                        payload={props.payload as never}
                        hiddenKeys={perfHidden}
                        onToggle={perfToggle}
                        onSolo={(key) => perfSolo(key, perfAllKeys)}
                      />
                    )}
                  />
                  {selected && (
                    <Area
                      yAxisId="mv"
                      type="monotone"
                      dataKey={`${selected}_mv`}
                      name="Portfolio Value"
                      fill={PORTFOLIO_COLORS[selected] || "#805ad5"}
                      stroke={PORTFOLIO_COLORS[selected] || "#805ad5"}
                      fillOpacity={0.1}
                      strokeWidth={1}
                      strokeOpacity={0.3}
                      connectNulls
                      hide={perfHidden.has(`${selected}_mv`)}
                    />
                  )}
                  {selected && (
                    <Line
                      yAxisId="perf"
                      type="monotone"
                      dataKey={selected}
                      stroke={PORTFOLIO_COLORS[selected] || "#805ad5"}
                      dot={false}
                      strokeWidth={2}
                      connectNulls
                      hide={perfHidden.has(selected)}
                    />
                  )}
                  {selected !== "Flagship" && perfMode === "%" && (
                    <Line
                      yAxisId="perf"
                      type="monotone"
                      dataKey="S&P 500"
                      stroke={SP500_COLOR}
                      dot={false}
                      strokeWidth={2}
                      strokeDasharray="5 5"
                      connectNulls
                      hide={perfHidden.has("S&P 500")}
                    />
                  )}
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Breakdown by sector/industry chart */}
          {breakdownData.length > 0 && (
            <div className="portfolios-page__chart-section">
              <div className="portfolios-page__chart-header">
                <div className="portfolios-page__chart-title">PnL by {groupBy === "sector" ? "Sector" : "Industry"}</div>
                <div className="portfolios-page__chart-header-controls">
                  <div className="portfolios-page__group-toggle">
                    <button
                      className={`portfolios-page__group-toggle-btn${groupBy === "sector" ? " portfolios-page__group-toggle-btn--active" : ""}`}
                      onClick={() => setGroupBy("sector")}
                    >
                      Sector
                    </button>
                    <button
                      className={`portfolios-page__group-toggle-btn${groupBy === "industry" ? " portfolios-page__group-toggle-btn--active" : ""}`}
                      onClick={() => setGroupBy("industry")}
                    >
                      Industry
                    </button>
                  </div>
                  <div className="portfolios-page__group-toggle">
                    <button
                      className={`portfolios-page__group-toggle-btn${breakdownMode === "%" ? " portfolios-page__group-toggle-btn--active" : ""}`}
                      onClick={() => setBreakdownMode("%")}
                    >
                      %
                    </button>
                    <button
                      className={`portfolios-page__group-toggle-btn${breakdownMode === "$" ? " portfolios-page__group-toggle-btn--active" : ""}`}
                      onClick={() => setBreakdownMode("$")}
                    >
                      $
                    </button>
                  </div>
                </div>
              </div>
              <ResponsiveContainer width="100%" height={350}>
                <LineChart data={chartBreakdownData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 11 }}
                    tickFormatter={(d: string) => d.slice(0, 7)}
                    interval="preserveStartEnd"
                    minTickGap={60}
                  />
                  <YAxis
                    tick={{ fontSize: 11 }}
                    tickFormatter={breakdownMode === "%"
                      ? (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`
                      : (v: number) => formatCurrency(v)
                    }
                  />
                  <Tooltip
                    formatter={breakdownMode === "%"
                      ? ((value: number, name: string) => [
                          `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`,
                          name,
                        ]) as never
                      : ((value: number, name: string) => [
                          formatCurrency(value),
                          name,
                        ]) as never
                    }
                  />
                  <Legend
                    content={(props) => (
                      <ToggleableLegend
                        payload={props.payload as never}
                        hiddenKeys={breakdownHidden}
                        onToggle={breakdownToggle}
                        onSolo={(key) => breakdownSolo(key, breakdownAllKeys)}
                      />
                    )}
                  />
                  <Line
                    type="monotone"
                    dataKey="Total"
                    stroke={PORTFOLIO_COLORS[selected ?? ""] || "#805ad5"}
                    dot={false}
                    strokeWidth={2.5}
                    connectNulls
                    hide={breakdownHidden.has("Total")}
                  />
                  {breakdownGroups
                    .filter((g) => g !== "Other")
                    .map((group, idx) => (
                      <Line
                        key={group}
                        type="monotone"
                        dataKey={group}
                        stroke={INDUSTRY_PALETTE[idx % INDUSTRY_PALETTE.length]}
                        dot={false}
                        strokeWidth={1.5}
                        strokeDasharray="4 3"
                        strokeOpacity={0.7}
                        connectNulls
                        hide={breakdownHidden.has(group)}
                      />
                    ))}
                  {breakdownGroups.includes("Other") && (
                    <Line
                      type="monotone"
                      dataKey="Other"
                      stroke="#a0aec0"
                      dot={false}
                      strokeWidth={1.5}
                      strokeDasharray="4 3"
                      strokeOpacity={0.7}
                      connectNulls
                      hide={breakdownHidden.has("Other")}
                    />
                  )}
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        {/* Loading / Error */}
        {loading && (
          <div className="portfolio-loading">
            <div className="spinner" />
          </div>
        )}

        {error && !loading && (
          <div className="portfolio-empty">
            <div className="portfolio-empty__title">Error</div>
            <div className="portfolio-empty__message">{error}</div>
          </div>
        )}

        {/* Summary cards */}
        {!loading && !error && detail && (
          <>
            <div className="portfolio-summary-cards">
              <div className="portfolio-summary-card">
                <span className="portfolio-summary-card__label">
                  Current Value
                </span>
                <span className="portfolio-summary-card__value">
                  {formatCurrency(marketValue)}
                </span>
              </div>
              <div className="portfolio-summary-card">
                <span className="portfolio-summary-card__label">
                  Positions
                </span>
                <span className="portfolio-summary-card__value">
                  {positionCount}
                </span>
              </div>
              <div className="portfolio-summary-card">
                <span className="portfolio-summary-card__label">
                  Lifetime PnL
                </span>
                <span
                  className={`portfolio-summary-card__value ${pnlClass(totalPnl)}`}
                >
                  {formatCurrency(totalPnl)}
                  <span className="portfolio-summary-card__pct">{formatPct(pnlPct)}</span>
                </span>
              </div>
              <div className="portfolio-summary-card">
                <span className="portfolio-summary-card__label">
                  YTD PnL
                </span>
                <span
                  className={`portfolio-summary-card__value ${ytdPnl !== null ? pnlClass(ytdPnl) : ""}`}
                >
                  {ytdPnl !== null ? formatCurrency(ytdPnl) : "—"}
                  {ytdPnlPct !== null && (
                    <span className="portfolio-summary-card__pct">{formatPct(ytdPnlPct)}</span>
                  )}
                </span>
              </div>
            </div>

            {/* Positions grid */}
            <div className="portfolios-page__grid-section">
              <div className="portfolios-page__grid-header">
                <span className="portfolios-page__grid-title">Positions</span>
                <div className="portfolios-page__grid-actions">
                  {positions.length > 0 && (
                    <button
                      className="portfolios-page__download-btn"
                      onClick={() => gridApiRef.current?.exportDataAsCsv()}
                    >
                      Download CSV
                    </button>
                  )}
                </div>
              </div>
              <div className="portfolios-page__grid">
                <AppGrid<PositionRow>
                  rowData={positions}
                  columnDefs={columnDefs}
                  onGridReady={handleGridReady}
                  contextMenu={contextMenuConfig}
                  viewKey="portfolios-positions"
                />
              </div>
            </div>
          </>
        )}
      </div>
    </Layout>
  );
}
