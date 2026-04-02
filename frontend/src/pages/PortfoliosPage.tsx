import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ColDef, GridApi } from "ag-grid-community";
import Plot from "react-plotly.js";
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
  useToggleableLegend,
} from "../components/ToggleableLegend";

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
  return_dollar: string;
  return_pct: string;
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
const MV_AREA_COLOR = "#a0aec0";
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

const PLOTLY_LAYOUT_DEFAULTS: Partial<Plotly.Layout> = {
  paper_bgcolor: "transparent",
  plot_bgcolor: "transparent",
  font: { family: "Inter, system-ui, sans-serif", size: 11 },
  hovermode: "x unified" as const,
};

const PLOTLY_CONFIG: Partial<Plotly.Config> = {
  displayModeBar: false,
  responsive: true,
};

const GRID_STYLE: Partial<Plotly.LayoutAxis> = {
  gridcolor: "#e2e8f0",
  griddash: "dash",
};

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
  const { hiddenKeys: perfHidden, handleToggle: perfToggle } = useToggleableLegend();
  const { hiddenKeys: breakdownHidden, handleToggle: breakdownToggle } = useToggleableLegend();
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
        field: "return_dollar",
        headerName: "Return ($)",
        type: "numericColumn",
        valueGetter: (p) =>
          p.data ? parseFloat(p.data.return_dollar.replace(/,/g, "")) : null,
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
        field: "return_pct",
        headerName: "Return (%)",
        width: 110,
        type: "numericColumn",
        valueGetter: (p) => (p.data ? parseFloat(p.data.return_pct) : null),
        valueFormatter: (p) => (p.value != null ? `${Number(p.value).toFixed(1)}%` : ""),
        cellStyle: (params) => {
          if (params.value > 0) return { color: "var(--color-success)" };
          if (params.value < 0) return { color: "var(--color-error)" };
          return null;
        },
      },
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
      "exposure_dollars", "exposure_pct", "return_dollar", "return_pct", "pnl", "pnl_pct", "sector", "industry",
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
    : "\u2014";
  const totalPnl = detail
    ? parseNumeric(getHeaderValue(detail.header_fields, "Total PnL"))
    : 0;
  const totalCost = detail
    ? parseNumeric(getHeaderValue(detail.header_fields, "Total Cost"))
    : 0;
  const pnlPct = totalCost ? totalPnl / totalCost * 100 : 0;
  const ytdPnlPct = totalCost && ytdPnl !== null ? ytdPnl / totalCost * 100 : null;

  // Transform chart data
  const chartComparisonData = useMemo(() => {
    return comparisonData.map((point) => {
      const out: ComparisonDataPoint = { date: point.date };
      for (const [key, value] of Object.entries(point)) {
        if (key === "date") continue;
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

  // Perf chart legend name <-> data key mappings
  const perfLegendNames = useMemo(() => {
    const names: string[] = [];
    if (selected) {
      names.push("Portfolio Value");
      names.push(selected);
    }
    if (selected !== "Flagship" && perfMode === "%") names.push("S&P 500");
    return names;
  }, [selected, perfMode]);

  const perfNameToKey = useMemo(() => {
    const m: Record<string, string> = {};
    if (selected) {
      m["Portfolio Value"] = `${selected}_mv`;
      m[selected] = selected;
    }
    if (selected !== "Flagship" && perfMode === "%") m["S&P 500"] = "S&P 500";
    return m;
  }, [selected, perfMode]);

  // --- Cumulative Performance Plotly data & layout ---
  const { perfTraces, perfLayout } = useMemo(() => {
    if (chartComparisonData.length === 0 || !selected) {
      return { perfTraces: [] as Plotly.Data[], perfLayout: {} as Partial<Plotly.Layout> };
    }

    const xData = chartComparisonData.map((d) => d.date as string);
    const mvKey = `${selected}_mv`;

    const traces: Plotly.Data[] = [];

    // Market value area (left y-axis)
    const mvVisible = !perfHidden.has(perfNameToKey["Portfolio Value"]);
    traces.push({
      type: "scatter",
      mode: "lines",
      name: "Portfolio Value",
      x: xData,
      y: chartComparisonData.map((d) => {
        const v = d[mvKey];
        return v != null ? Number(v) : null;
      }),
      yaxis: "y",
      line: { color: MV_AREA_COLOR, width: 1 },
      fill: "tozeroy",
      fillcolor: "rgba(160, 174, 192, 0.15)",
      opacity: 0.4,
      connectgaps: true,
      visible: mvVisible ? true : "legendonly",
      hovertemplate: "%{fullData.name}: %{y:$,.0f}<extra></extra>",
    });

    // Portfolio return line (right y-axis)
    const portfolioColor = PORTFOLIO_COLORS[selected] || "#805ad5";
    const portfolioVisible = !perfHidden.has(perfNameToKey[selected]);
    traces.push({
      type: "scatter",
      mode: "lines",
      name: selected,
      x: xData,
      y: chartComparisonData.map((d) => {
        const v = d[selected];
        return v != null ? Number(v) : null;
      }),
      yaxis: "y2",
      line: { color: portfolioColor, width: 2 },
      connectgaps: true,
      visible: portfolioVisible ? true : "legendonly",
      hovertemplate: perfMode === "%"
        ? "%{fullData.name}: %{y:+.1f}%<extra></extra>"
        : "%{fullData.name}: %{y:$,.0f}<extra></extra>",
    });

    // S&P 500 (only in % mode and not Flagship)
    if (selected !== "Flagship" && perfMode === "%") {
      const sp500Visible = !perfHidden.has(perfNameToKey["S&P 500"]);
      traces.push({
        type: "scatter",
        mode: "lines",
        name: "S&P 500",
        x: xData,
        y: chartComparisonData.map((d) => {
          const v = d["S&P 500"];
          return v != null ? Number(v) : null;
        }),
        yaxis: "y2",
        line: { color: SP500_COLOR, width: 2, dash: "dash" },
        connectgaps: true,
        visible: sp500Visible ? true : "legendonly",
        hovertemplate: "%{fullData.name}: %{y:+.1f}%<extra></extra>",
      });
    }

    const layout: Partial<Plotly.Layout> = {
      ...PLOTLY_LAYOUT_DEFAULTS,
      margin: { l: 55, r: 55, t: 8, b: 40 },
      legend: {
        orientation: "h",
        y: -0.12,
        x: 0.5,
        xanchor: "center",
        font: { size: 10 },
        tracegroupgap: 5,
      },
      xaxis: {
        type: "date",
        tickformat: "%b '%y",
        hoverformat: "%-m/%-d/%Y",
        nticks: 8,
        autorange: true,
        ...GRID_STYLE,
        tickfont: { size: 11 },
        rangeslider: { visible: false },
        domain: [0, 1],
      },
      yaxis: {
        ...GRID_STYLE,
        tickfont: { size: 11 },
        tickformat: "$~s",
        side: "left",
        autorange: true,
      },
      yaxis2: {
        ...GRID_STYLE,
        tickfont: { size: 11 },
        tickformat: perfMode === "%" ? "+.1f" : "$~s",
        ticksuffix: perfMode === "%" ? "%" : "",
        side: "right",
        overlaying: "y",
        showgrid: false,
        autorange: true,
      },
    };

    return { perfTraces: traces, perfLayout: layout };
  }, [chartComparisonData, selected, perfMode, perfLegendNames, perfNameToKey, perfHidden]);

  const handlePerfLegendClick = useCallback((event: Readonly<Plotly.LegendClickEvent>) => {
    const traceName = (event.data[event.curveNumber] as Plotly.Data & { name?: string }).name;
    if (traceName) {
      const dataKey = perfNameToKey[traceName];
      if (dataKey) perfToggle(dataKey);
    }
    // Return false to prevent Plotly's default legend toggle behavior
    // since we manage visibility via state
    return false;
  }, [perfNameToKey, perfToggle]);

  // --- PnL Breakdown Plotly data & layout ---
  const { breakdownTraces, breakdownLayout } = useMemo(() => {
    if (chartBreakdownData.length === 0) {
      return { breakdownTraces: [] as Plotly.Data[], breakdownLayout: {} as Partial<Plotly.Layout> };
    }

    const xData = chartBreakdownData.map((d) => d.date as string);
    const traces: Plotly.Data[] = [];

    const hoverTemplateFn = breakdownMode === "%"
      ? "%{fullData.name}: %{y:+.1f}%<extra></extra>"
      : "%{fullData.name}: %{y:$,.0f}<extra></extra>";

    // Total line
    const totalVisible = !breakdownHidden.has("Total");
    traces.push({
      type: "scatter",
      mode: "lines",
      name: "Total",
      x: xData,
      y: chartBreakdownData.map((d) => {
        const v = d["Total"];
        return v != null ? Number(v) : null;
      }),
      line: { color: PORTFOLIO_COLORS[selected ?? ""] || "#805ad5", width: 2.5 },
      connectgaps: true,
      visible: totalVisible ? true : "legendonly",
      hovertemplate: hoverTemplateFn,
    });

    // Group lines (excluding "Other")
    const nonOtherGroups = breakdownGroups.filter((g) => g !== "Other");
    nonOtherGroups.forEach((group, idx) => {
      const groupVisible = !breakdownHidden.has(group);
      traces.push({
        type: "scatter",
        mode: "lines",
        name: group,
        x: xData,
        y: chartBreakdownData.map((d) => {
          const v = d[group];
          return v != null ? Number(v) : null;
        }),
        line: {
          color: INDUSTRY_PALETTE[idx % INDUSTRY_PALETTE.length],
          width: 1.5,
          dash: "dash",
        },
        opacity: 0.7,
        connectgaps: true,
        visible: groupVisible ? true : "legendonly",
        hovertemplate: hoverTemplateFn,
      });
    });

    // "Other" group
    if (breakdownGroups.includes("Other")) {
      const otherVisible = !breakdownHidden.has("Other");
      traces.push({
        type: "scatter",
        mode: "lines",
        name: "Other",
        x: xData,
        y: chartBreakdownData.map((d) => {
          const v = d["Other"];
          return v != null ? Number(v) : null;
        }),
        line: { color: "#a0aec0", width: 1.5, dash: "dash" },
        opacity: 0.7,
        connectgaps: true,
        visible: otherVisible ? true : "legendonly",
        hovertemplate: hoverTemplateFn,
      });
    }

    const layout: Partial<Plotly.Layout> = {
      ...PLOTLY_LAYOUT_DEFAULTS,
      margin: { l: 55, r: 12, t: 8, b: 28 },
      legend: {
        orientation: "h",
        y: -0.12,
        x: 0.5,
        xanchor: "center",
        font: { size: 10 },
        tracegroupgap: 5,
      },
      xaxis: {
        type: "date",
        tickformat: "%b '%y",
        hoverformat: "%-m/%-d/%Y",
        nticks: 8,
        ...GRID_STYLE,
        tickfont: { size: 11 },
      },
      yaxis: {
        ...GRID_STYLE,
        tickfont: { size: 11 },
        tickformat: breakdownMode === "%" ? "+.1f" : "$~s",
        ticksuffix: breakdownMode === "%" ? "%" : "",
      },
    };

    return { breakdownTraces: traces, breakdownLayout: layout };
  }, [chartBreakdownData, breakdownGroups, breakdownMode, breakdownHidden, selected]);

  const handleBreakdownLegendClick = useCallback((event: Readonly<Plotly.LegendClickEvent>) => {
    const traceName = (event.data[event.curveNumber] as Plotly.Data & { name?: string }).name;
    if (traceName) breakdownToggle(traceName);
    return false;
  }, [breakdownToggle]);

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

        {/* Charts row */}
        <div className="portfolios-page__charts-row">
          {/* Cumulative performance chart */}
          {comparisonData.length > 0 && selected && (
            <div className="portfolios-page__chart-section">
              <div className="portfolios-page__chart-header">
                <div className="portfolios-page__chart-title">Cumulative Performance</div>
                <div className="portfolios-page__chart-header-controls">
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
              </div>
              <Plot
                data={perfTraces}
                layout={perfLayout}
                config={PLOTLY_CONFIG}
                style={{ height: 350, width: "100%" }}
                useResizeHandler
                onLegendClick={handlePerfLegendClick}
              />
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
              <Plot
                data={breakdownTraces}
                layout={breakdownLayout}
                config={PLOTLY_CONFIG}
                style={{ height: 350, width: "100%" }}
                useResizeHandler
                onLegendClick={handleBreakdownLegendClick}
              />
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
                  {ytdPnl !== null ? formatCurrency(ytdPnl) : "\u2014"}
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
