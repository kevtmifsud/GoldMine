import { useState, useEffect, useMemo } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import api from "../../../config/api";
import { formatDateLabel, downloadFinancialsExcel } from "../../../config/financialsApi";
import type { FinancialSummaryResponse, SummaryMetric } from "../../../types/financials";
import { useStockEntity } from "../StockEntityPage";
import "../../../styles/fundamentals.css";

const SECTION_LABELS: Record<string, string> = {
  income_statement: "Income Statement",
  balance_sheet: "Balance Sheet",
  cash_flow: "Cash Flow",
};

const SECTION_ORDER = ["income_statement", "balance_sheet", "cash_flow"];

type ChartMode = "value" | "yoy" | "qoq";

function formatAxisValue(value: number, formatType: string): string {
  if (formatType === "per_share") {
    return `$${value.toFixed(0)}`;
  }
  const abs = Math.abs(value);
  let formatted: string;
  if (abs >= 1e12) {
    formatted = `${(value / 1e12).toFixed(1)}T`;
  } else if (abs >= 1e9) {
    formatted = `${(value / 1e9).toFixed(0)}B`;
  } else if (abs >= 1e6) {
    formatted = `${(value / 1e6).toFixed(0)}M`;
  } else if (abs >= 1e3) {
    formatted = `${(value / 1e3).toFixed(0)}K`;
  } else {
    formatted = value.toFixed(0);
  }
  return formatType === "currency" ? `$${formatted}` : formatted;
}

function formatTooltipValue(value: number, formatType: string): string {
  if (formatType === "per_share") {
    return `$${value.toFixed(2)}`;
  }
  const neg = value < 0;
  const abs = Math.abs(value);
  let formatted: string;
  const prefix = formatType === "currency" ? "$" : "";
  if (abs >= 1e12) {
    formatted = `${prefix}${(abs / 1e12).toFixed(1)}T`;
  } else if (abs >= 1e9) {
    formatted = `${prefix}${(abs / 1e9).toFixed(1)}B`;
  } else if (abs >= 1e6) {
    formatted = `${prefix}${(abs / 1e6).toFixed(1)}M`;
  } else if (abs >= 1e3) {
    formatted = `${prefix}${(abs / 1e3).toFixed(1)}K`;
  } else {
    formatted = `${prefix}${abs.toFixed(1)}`;
  }
  return neg ? `(${formatted})` : formatted;
}

interface ChartDataPoint {
  date: string;
  label: string;
  value: number;
  yoy: number | null;
  growth: number | null;
}

function MetricChart({
  metric,
  dates,
  period,
  fyEndMonth,
  chartMode,
}: {
  metric: SummaryMetric;
  dates: string[];
  period: string;
  fyEndMonth: number;
  chartMode: ChartMode;
}) {
  const isGrowthMode = chartMode !== "value";
  const growthSource = chartMode === "qoq" ? metric.qoq : metric.yoy;

  const chartData: ChartDataPoint[] = dates
    .filter((d) => {
      if (isGrowthMode) {
        return growthSource[d] !== null && growthSource[d] !== undefined;
      }
      return metric.values[d] !== null && metric.values[d] !== undefined;
    })
    .map((d) => ({
      date: d,
      label: formatDateLabel(d, period, fyEndMonth),
      value: metric.values[d] ?? 0,
      yoy: metric.yoy[d] ?? null,
      growth: growthSource[d] ?? null,
    }));

  if (chartData.length === 0) return null;

  const growthDataRef = chartData
    .filter((d) => d.growth !== null)
    .map((d) => ({ ...d, growthVal: d.growth! }));

  if (isGrowthMode) {
    if (growthDataRef.length === 0) return null;
    const growthLabel = chartMode === "qoq" ? "QoQ" : "YoY";

    return <MetricGrowthChart data={growthDataRef} growthLabel={growthLabel} metric={metric} />;
  }

  return <MetricValueChart data={chartData} metric={metric} />;
}

function MetricGrowthChart({
  data,
  growthLabel,
  metric,
}: {
  data: { label: string; value: number; growthVal: number }[];
  growthLabel: string;
  metric: SummaryMetric;
}) {
  const option: EChartsOption = useMemo(() => ({
    grid: { left: 50, right: 8, top: 30, bottom: 10, containLabel: false },
    xAxis: {
      type: "category",
      data: data.map((d) => d.label),
      axisLabel: { fontSize: 10 },
      axisTick: { show: false },
      axisLine: { show: false },
    },
    yAxis: {
      type: "value",
      axisLabel: { fontSize: 10, formatter: (v: number) => `${v}%` },
      axisTick: { show: false },
      axisLine: { show: false },
      splitLine: { lineStyle: { type: "dashed" as const, color: "#e2e8f0" } },
    },
    tooltip: {
      trigger: "axis",
      formatter: (params: unknown) => {
        const items = Array.isArray(params) ? params : [params];
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const first = items[0] as any;
        const idx = first.dataIndex as number;
        const entry = data[idx];
        let html = `<div style="font-weight:600;margin-bottom:4px">${first.axisValue}</div>`;
        html += `<div>${growthLabel} Growth: ${entry.growthVal != null ? `${entry.growthVal.toFixed(1)}%` : "\u2014"}</div>`;
        html += `<div>Value: ${formatTooltipValue(entry.value, metric.format_type)}</div>`;
        return html;
      },
    },
    series: [{
      type: "bar",
      data: data.map((d) => ({
        value: d.growthVal,
        itemStyle: { color: d.growthVal >= 0 ? "#38a169" : "#e53e3e" },
        label: {
          show: true,
          position: "top" as const,
          fontSize: 8,
          fontWeight: 500,
          color: "#1a202c",
          formatter: () => formatTooltipValue(d.value, metric.format_type),
        },
      })),
      barMaxWidth: 40,
      itemStyle: { borderRadius: [3, 3, 0, 0] },
      markLine: {
        silent: true,
        symbol: "none",
        lineStyle: { color: "#e2e8f0", width: 1 },
        data: [{ yAxis: 0 }],
        label: { show: false },
      },
    }],
  }), [data, growthLabel, metric.format_type]);

  return (
    <div className="fundamentals-summary__card">
      <div className="fundamentals-summary__card-title">
        {metric.label} — {growthLabel} Growth
      </div>
      <div className="fundamentals-summary__card-chart">
        <ReactECharts option={option} style={{ height: "100%", width: "100%" }} notMerge />
      </div>
    </div>
  );
}

function MetricValueChart({
  data,
  metric,
}: {
  data: ChartDataPoint[];
  metric: SummaryMetric;
}) {
  const option: EChartsOption = useMemo(() => ({
    grid: { left: 60, right: 8, top: 30, bottom: 10, containLabel: false },
    xAxis: {
      type: "category",
      data: data.map((d) => d.label),
      axisLabel: { fontSize: 10 },
      axisTick: { show: false },
      axisLine: { show: false },
    },
    yAxis: {
      type: "value",
      axisLabel: { fontSize: 10, formatter: (v: number) => formatAxisValue(v, metric.format_type) },
      axisTick: { show: false },
      axisLine: { show: false },
      splitLine: { lineStyle: { type: "dashed" as const, color: "#e2e8f0" } },
    },
    tooltip: {
      trigger: "axis",
      formatter: (params: unknown) => {
        const items = Array.isArray(params) ? params : [params];
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const first = items[0] as any;
        const idx = first.dataIndex as number;
        const entry = data[idx];
        let html = `<div style="font-weight:600;margin-bottom:4px">${first.axisValue}</div>`;
        html += `<div>${metric.label}: ${formatTooltipValue(entry.value, metric.format_type)}</div>`;
        return html;
      },
    },
    series: [{
      type: "bar",
      data: data.map((d) => ({
        value: d.value,
        itemStyle: { color: d.value < 0 ? "#e53e3e" : "#1a365d" },
        label: {
          show: true,
          position: "top" as const,
          fontSize: 9,
          fontWeight: 500,
          formatter: () => {
            if (d.yoy === null || d.yoy === undefined) return "";
            return `{growth|${d.yoy > 0 ? "+" : ""}${d.yoy.toFixed(1)}%}`;
          },
          rich: {
            growth: {
              fontSize: 9,
              fontWeight: 500,
              color: d.yoy != null ? (d.yoy > 0 ? "#38a169" : d.yoy < 0 ? "#e53e3e" : "#718096") : "#718096",
            },
          },
        },
      })),
      barMaxWidth: 40,
      itemStyle: { borderRadius: [3, 3, 0, 0] },
    }],
  }), [data, metric.label, metric.format_type]);

  return (
    <div className="fundamentals-summary__card">
      <div className="fundamentals-summary__card-title">{metric.label}</div>
      <div className="fundamentals-summary__card-chart">
        <ReactECharts option={option} style={{ height: "100%", width: "100%" }} notMerge />
      </div>
    </div>
  );
}

export function FundamentalsSummarySubPage() {
  const { detail } = useStockEntity();
  const [period, setPeriod] = useState<"annual" | "quarterly">("annual");
  const [chartMode, setChartMode] = useState<ChartMode>("value");
  const [data, setData] = useState<FinancialSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .get<FinancialSummaryResponse>(`/api/financials/${detail.entity_id}/summary`, {
        params: { period },
      })
      .then((resp) => setData(resp.data))
      .catch(() => setError("Failed to load summary data"))
      .finally(() => setLoading(false));
  }, [detail.entity_id, period]);

  // Reset QoQ mode when switching to annual
  useEffect(() => {
    if (period === "annual" && chartMode === "qoq") {
      setChartMode("yoy");
    }
  }, [period, chartMode]);

  const handleDownload = async () => {
    if (!data) return;
    setDownloading(true);
    try {
      await downloadFinancialsExcel(detail.entity_id);
    } catch {
      // silent fail
    } finally {
      setDownloading(false);
    }
  };

  const grouped: Record<string, SummaryMetric[]> = {};
  if (data) {
    for (const m of data.metrics) {
      if (!grouped[m.section]) grouped[m.section] = [];
      grouped[m.section].push(m);
    }
  }

  return (
    <>
      <div className="fundamentals-toggle">
        <span className="fundamentals-toggle__label">Period</span>
        <div className="fundamentals-toggle__buttons">
          <button
            className={`fundamentals-toggle__btn${period === "annual" ? " fundamentals-toggle__btn--active" : ""}`}
            onClick={() => setPeriod("annual")}
          >
            Annual
          </button>
          <button
            className={`fundamentals-toggle__btn${period === "quarterly" ? " fundamentals-toggle__btn--active" : ""}`}
            onClick={() => setPeriod("quarterly")}
          >
            Quarterly
          </button>
        </div>
        <span className="fundamentals-toggle__label">View</span>
        <div className="fundamentals-toggle__buttons">
          <button
            className={`fundamentals-toggle__btn${chartMode === "value" ? " fundamentals-toggle__btn--active" : ""}`}
            onClick={() => setChartMode("value")}
          >
            Value
          </button>
          <button
            className={`fundamentals-toggle__btn${chartMode === "yoy" ? " fundamentals-toggle__btn--active" : ""}`}
            onClick={() => setChartMode("yoy")}
          >
            YoY Growth
          </button>
          {period === "quarterly" && (
            <button
              className={`fundamentals-toggle__btn${chartMode === "qoq" ? " fundamentals-toggle__btn--active" : ""}`}
              onClick={() => setChartMode("qoq")}
            >
              QoQ Growth
            </button>
          )}
        </div>
        <div className="fundamentals-toggle__spacer" />
        <button
          className="fundamentals-toggle__download"
          onClick={handleDownload}
          disabled={downloading || !data}
        >
          {downloading ? "Downloading..." : "Download Excel"}
        </button>
      </div>

      {loading && <div className="financial-table__loading"><div className="spinner" /></div>}
      {error && <div className="financial-table__error">{error}</div>}
      {!loading && !error && data && (
        <div className="fundamentals-summary">
          {SECTION_ORDER.map((section) => {
            const metrics = grouped[section];
            if (!metrics || metrics.length === 0) return null;
            return (
              <div key={section} className="fundamentals-summary__section">
                <h3 className="fundamentals-summary__section-title">
                  {SECTION_LABELS[section]}
                </h3>
                <div className="fundamentals-summary__grid">
                  {metrics.map((m) => (
                    <MetricChart
                      key={m.metric}
                      metric={m}
                      dates={data.dates}
                      period={period}
                      fyEndMonth={data.fy_end_month}
                      chartMode={chartMode}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}
