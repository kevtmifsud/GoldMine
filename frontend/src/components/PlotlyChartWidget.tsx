import { useEffect, useState, useCallback, useMemo } from "react";
import Plot from "react-plotly.js";
import type { Data, Layout } from "plotly.js";
import { useToggleableLegend } from "./ToggleableLegend";
import api from "../config/api";
import type { WidgetConfig, PaginatedResponse } from "../types/entities";
import "../styles/chart.css";


const HIGHLIGHT_COLOR = "#e86319";
const HIGHLIGHT_ALPHA = 1.0;
const SAME_INDUSTRY_ALPHA = 0.55;
const OTHER_ALPHA = 0.45;

const INDUSTRY_PALETTE = [
  "#3182ce", "#38a169", "#805ad5", "#d53f8c", "#dd6b20",
  "#319795", "#975a16", "#2b6cb0", "#e53e3e", "#718096",
];

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

interface ChartWidgetProps {
  config: WidgetConfig;
  entityId?: string;
}

export function PlotlyChartWidget({ config, entityId }: ChartWidgetProps) {
  const [data, setData] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await api.get<PaginatedResponse>(config.endpoint);
      setData(resp.data.data);
    } catch {
      setError("Failed to load chart data");
    } finally {
      setLoading(false);
    }
  }, [config.endpoint]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const chartConfig = config.chart_config;
  if (!chartConfig) return null;

  const secondaryLines = chartConfig.secondary_lines ?? [];
  const hasSecondaryAxis = secondaryLines.length > 0;
  const barsConfig = chartConfig.bars ?? [];
  const hasBars = barsConfig.length > 0;

  const hasAltToggle = hasBars
    ? barsConfig.some((b) => !!b.y_key_alt)
    : !!chartConfig.y_key_alt || secondaryLines.some((sl) => !!sl.y_key_alt);
  const [useAlt, setUseAlt] = useState(false);
  const { hiddenKeys } = useToggleableLegend();

  const activeYKey = useAlt && chartConfig.y_key_alt ? chartConfig.y_key_alt : chartConfig.y_key;
  const activeYLabel = useAlt && chartConfig.y_label_alt ? chartConfig.y_label_alt : chartConfig.y_label;
  const activeYFormat = useAlt && chartConfig.y_format_alt ? chartConfig.y_format_alt : chartConfig.y_format;

  const activeBarsKeys = barsConfig.map((bar) =>
    useAlt && bar.y_key_alt ? bar.y_key_alt : bar.y_key
  );

  const activeSecondaryKeys = secondaryLines.map((sl) =>
    useAlt && sl.y_key_alt ? sl.y_key_alt : sl.y_key
  );
  const activeSecondaryLabels = secondaryLines.map((sl) =>
    useAlt && sl.label_alt ? sl.label_alt : sl.label
  );

  const tickformat = useMemo(() => {
    if (activeYFormat === "currency") return "$,.0s";
    if (activeYFormat === "percent") return ".1%";
    if (activeYFormat === "number") return ",.0f";
    return "";
  }, [activeYFormat]);

  // Sort + coerce data
  const numericData = useMemo(() => {
    const mapped = data.map((row) => {
      const out: Record<string, unknown> = {
        ...row,
        [chartConfig.y_key]: Number(row[chartConfig.y_key]) || 0,
      };
      if (chartConfig.y_key_alt) {
        out[chartConfig.y_key_alt] = Number(row[chartConfig.y_key_alt]) || 0;
      }
      for (const bar of barsConfig) {
        out[bar.y_key] = Number(row[bar.y_key]) || 0;
        if (bar.y_key_alt) out[bar.y_key_alt] = Number(row[bar.y_key_alt]) || 0;
      }
      for (const sl of secondaryLines) {
        const raw = row[sl.y_key];
        out[sl.y_key] = raw != null && raw !== "" ? Number(raw) : null;
        if (sl.y_key_alt) {
          const rawAlt = row[sl.y_key_alt];
          out[sl.y_key_alt] = rawAlt != null && rawAlt !== "" ? Number(rawAlt) : null;
        }
      }
      return out;
    });
    if (chartConfig.chart_type !== "line") {
      if (hasBars) {
        mapped.sort((a, b) => {
          const sumA = activeBarsKeys.reduce((s, k) => s + Math.abs(Number(a[k]) || 0), 0);
          const sumB = activeBarsKeys.reduce((s, k) => s + Math.abs(Number(b[k]) || 0), 0);
          return sumB - sumA;
        });
      } else {
        mapped.sort((a, b) => (Number(b[activeYKey]) || 0) - (Number(a[activeYKey]) || 0));
      }
    }
    return mapped;
  }, [data, chartConfig.y_key, chartConfig.y_key_alt, chartConfig.chart_type, secondaryLines, activeYKey, barsConfig, hasBars, activeBarsKeys]);

  // Build colors for bars
  const colorKey = chartConfig.color_key;
  const isStacked = chartConfig.stacked;

  const barColors = useMemo(() => {
    if (chartConfig.chart_type === "line" || !numericData.length) return null;

    if (colorKey) {
      const groups = [...new Set(numericData.map((r) => String(r[colorKey] ?? "")))].sort();
      const colorMap: Record<string, string> = {};
      groups.forEach((g, i) => { colorMap[g] = INDUSTRY_PALETTE[i % INDUSTRY_PALETTE.length]; });
      return numericData.map((row) => hexToRgba(colorMap[String(row[colorKey] ?? "")] ?? INDUSTRY_PALETTE[0], 0.85));
    }

    if (!entityId) return null;

    const selectedIndustry = String(numericData.find((r) => String(r[chartConfig.x_key]) === entityId)?.industry ?? "");
    const colorMap: Record<string, string> = {};
    const industries = [...new Set(numericData.map((r) => String(r.industry ?? "")))];
    let pi = 0;
    for (const ind of industries) {
      if (ind === selectedIndustry) colorMap[ind] = HIGHLIGHT_COLOR;
      else { colorMap[ind] = INDUSTRY_PALETTE[pi % INDUSTRY_PALETTE.length]; pi++; }
    }

    return numericData.map((row) => {
      const ticker = String(row[chartConfig.x_key]);
      const industry = String(row.industry ?? "");
      if (ticker === entityId) return hexToRgba(HIGHLIGHT_COLOR, HIGHLIGHT_ALPHA);
      if (industry === selectedIndustry) return hexToRgba(HIGHLIGHT_COLOR, SAME_INDUSTRY_ALPHA);
      return hexToRgba(colorMap[industry] ?? INDUSTRY_PALETTE[0], OTHER_ALPHA);
    });
  }, [numericData, entityId, chartConfig.x_key, chartConfig.chart_type, colorKey]);

  const isLineChart = chartConfig.chart_type === "line";

  // Build Plotly traces + layout
  const { traces, layout } = useMemo(() => {
    const xData = numericData.map((row) => String(row[chartConfig.x_key]));
    const plotTraces: Data[] = [];

    if (isLineChart) {
      // Primary line
      plotTraces.push({
        type: "scatter",
        mode: "lines",
        name: activeYLabel ?? activeYKey,
        x: xData,
        y: numericData.map((row) => {
          const v = row[activeYKey];
          return v != null ? Number(v) : null;
        }),
        line: { color: chartConfig.color || "#3182ce", width: 1.5 },
        connectgaps: false,
        visible: hiddenKeys.has(activeYKey) ? "legendonly" : true,
        hovertemplate: `%{y}<extra>${activeYLabel ?? activeYKey}</extra>`,
      } as Data);

      // Secondary lines
      for (let idx = 0; idx < secondaryLines.length; idx++) {
        const sl = secondaryLines[idx];
        plotTraces.push({
          type: "scatter",
          mode: "lines",
          name: activeSecondaryLabels[idx],
          x: xData,
          y: numericData.map((row) => {
            const v = row[activeSecondaryKeys[idx]];
            return v != null ? Number(v) : null;
          }),
          yaxis: hasSecondaryAxis ? "y2" : "y",
          line: { color: sl.color, width: 1.5 },
          opacity: 0.45,
          connectgaps: true,
          visible: hiddenKeys.has(activeSecondaryKeys[idx]) ? "legendonly" : true,
          hovertemplate: `%{y}<extra>${activeSecondaryLabels[idx]}</extra>`,
        } as Data);
      }
    } else {
      // Bar chart
      if (hasBars) {
        barsConfig.forEach((bar, barIdx) => {
          const dataKey = activeBarsKeys[barIdx];
          plotTraces.push({
            type: "bar",
            name: bar.label,
            x: xData,
            y: numericData.map((row) => Number(row[dataKey]) || 0),
            marker: { color: barColors ? barColors : bar.color },
            visible: hiddenKeys.has(dataKey) ? "legendonly" : true,
            hovertemplate: `%{y}<extra>${bar.label}</extra>`,
          } as Data);
        });
      } else {
        plotTraces.push({
          type: "bar",
          name: activeYLabel ?? activeYKey,
          x: xData,
          y: numericData.map((row) => Number(row[activeYKey]) || 0),
          marker: { color: barColors ?? chartConfig.color ?? "#3182ce" },
          hovertemplate: `%{y}<extra>${activeYLabel ?? activeYKey}</extra>`,
        } as Data);
      }
    }

    const showLegend = isLineChart && hasSecondaryAxis;

    const plotLayout: Partial<Layout> = {
      paper_bgcolor: "transparent",
      plot_bgcolor: "transparent",
      font: { family: "Inter, system-ui, sans-serif", size: 11 },
      margin: { l: 55, r: hasSecondaryAxis ? 55 : 12, t: 8, b: isLineChart ? (showLegend ? 55 : 40) : 20 },
      showlegend: showLegend,
      legend: { orientation: "h", y: -0.12, x: 0.5, xanchor: "center", font: { size: 10 }, tracegroupgap: 5 },
      xaxis: {
        gridcolor: "#e2e8f0",
        linecolor: "#e2e8f0",
        tickfont: { size: 11 },
        hoverformat: "%-m/%-d/%Y",
        ...(chartConfig.x_label ? { title: { text: chartConfig.x_label, font: { size: 11 } } } : {}),
      },
      yaxis: {
        gridcolor: "#e2e8f0",
        griddash: "dash",
        linecolor: "#e2e8f0",
        tickfont: { size: 11 },
        tickformat,
        ...(activeYLabel ? { title: { text: activeYLabel, font: { size: 11 } } } : {}),
      },
      hovermode: "x unified" as const,
      autosize: true,
      barmode: isStacked ? "stack" : "group",
      ...(hasSecondaryAxis ? {
        yaxis2: {
          overlaying: "y",
          side: "right",
          gridcolor: "transparent",
          linecolor: "#e2e8f0",
          tickfont: { size: 11 },
          tickformat,
        },
      } : {}),
    };

    return { traces: plotTraces, layout: plotLayout };
  }, [numericData, chartConfig, isLineChart, activeYKey, activeYLabel, tickformat,
      hasSecondaryAxis, secondaryLines, activeSecondaryKeys, activeSecondaryLabels,
      hasBars, barsConfig, activeBarsKeys, barColors, isStacked, hiddenKeys]);

  // Sector legend (below chart for bar charts)
  const sectorLegendItems = useMemo(() => {
    if (isLineChart || !colorKey) return [];
    const groups = [...new Set(numericData.map((r) => String(r[colorKey] ?? "")))].sort();
    const colorMap: Record<string, string> = {};
    groups.forEach((g, i) => { colorMap[g] = INDUSTRY_PALETTE[i % INDUSTRY_PALETTE.length]; });
    return groups.map((g) => ({ industry: g, color: colorMap[g] }));
  }, [numericData, isLineChart, colorKey]);

  return (
    <div className="chart-widget">
      <div className="chart-widget__header">
        <h3 className="chart-widget__title">{config.title}</h3>
        <div className="chart-widget__header-controls">
          {hasAltToggle && (
            <div className="chart-widget__toggle">
              <button className={`chart-widget__toggle-btn${!useAlt ? " chart-widget__toggle-btn--active" : ""}`} onClick={() => setUseAlt(false)}>$</button>
              <button className={`chart-widget__toggle-btn${useAlt ? " chart-widget__toggle-btn--active" : ""}`} onClick={() => setUseAlt(true)}>%</button>
            </div>
          )}
        </div>
      </div>
      {loading && <div className="chart-widget__loading"><div className="spinner" /></div>}
      {error && <div className="chart-widget__error"><p>{error}</p><button onClick={fetchData}>Retry</button></div>}
      {!loading && !error && data.length === 0 && <div className="chart-widget__empty">No data available</div>}
      {!loading && !error && data.length > 0 && (
        <div className="chart-widget__container">
          <Plot
            data={traces}
            layout={layout}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: "100%", height: "100%" }}
            useResizeHandler
          />
          {sectorLegendItems.length > 0 && (
            <div className="chart-widget__legend">
              {sectorLegendItems.map((item) => (
                <span key={item.industry} className="chart-widget__legend-item">
                  <span className="chart-widget__legend-swatch" style={{ background: item.color, opacity: OTHER_ALPHA }} />
                  {item.industry}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
