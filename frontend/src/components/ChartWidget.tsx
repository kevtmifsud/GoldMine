import { useEffect, useState, useCallback, useMemo, type CSSProperties } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import { useToggleableLegend } from "./ToggleableLegend";
import api from "../config/api";
import type { WidgetConfig, PaginatedResponse } from "../types/entities";
import "../styles/chart.css";

/** Format a numeric value as a compact dollar string, e.g. $1.2M, -$350K */
function formatCurrency(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1_000_000_000) return `${sign}$${(abs / 1_000_000_000).toFixed(1)}B`;
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(0)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

/** Format a numeric value with commas, e.g. 1,234,567 */
function formatNumber(value: number): string {
  return value.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

/** Full dollar format for tooltips: $1,234,567 */
function formatCurrencyFull(value: number): string {
  const sign = value < 0 ? "-" : "";
  return `${sign}$${Math.abs(value).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

/** Compact percent format for axis ticks, e.g. 5.2% */
function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}

/** Full percent format for tooltips, e.g. 5.23% */
function formatPercentFull(value: number): string {
  return `${value.toFixed(2)}%`;
}

const HIGHLIGHT_COLOR = "#e86319";
const HIGHLIGHT_ALPHA = 1.0;
const SAME_INDUSTRY_ALPHA = 0.55;
const OTHER_ALPHA = 0.45;

/** Palette for non-highlighted industries. */
const INDUSTRY_PALETTE = [
  "#3182ce",
  "#38a169",
  "#805ad5",
  "#d53f8c",
  "#dd6b20",
  "#319795",
  "#975a16",
  "#2b6cb0",
  "#e53e3e",
  "#718096",
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

export function ChartWidget({ config, entityId }: ChartWidgetProps) {
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

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const chartConfig = config.chart_config;
  if (!chartConfig) return null;

  const secondaryLines = chartConfig.secondary_lines ?? [];
  const hasSecondaryAxis = secondaryLines.length > 0;
  const barsConfig = chartConfig.bars ?? [];
  const hasBars = barsConfig.length > 0;

  // Toggle between primary and alt y-axis config
  const hasAltToggle = hasBars
    ? barsConfig.some((b) => !!b.y_key_alt)
    : !!chartConfig.y_key_alt || secondaryLines.some((sl) => !!sl.y_key_alt);
  const [useAlt, setUseAlt] = useState(false);
  const { hiddenKeys, handleToggle: legendToggle, handleSolo: legendSolo } = useToggleableLegend();

  const activeYKey = useAlt && chartConfig.y_key_alt ? chartConfig.y_key_alt : chartConfig.y_key;
  const activeYLabel = useAlt && chartConfig.y_label_alt ? chartConfig.y_label_alt : chartConfig.y_label;
  const activeYFormat = useAlt && chartConfig.y_format_alt ? chartConfig.y_format_alt : chartConfig.y_format;

  // Active keys for each grouped bar
  const activeBarsKeys = barsConfig.map((bar) =>
    useAlt && bar.y_key_alt ? bar.y_key_alt : bar.y_key
  );

  // Active keys/labels for secondary lines
  const activeSecondaryKeys = secondaryLines.map((sl) =>
    useAlt && sl.y_key_alt ? sl.y_key_alt : sl.y_key
  );
  const activeSecondaryLabels = secondaryLines.map((sl) =>
    useAlt && sl.label_alt ? sl.label_alt : sl.label
  );
  const activeSecondaryYLabel = useAlt && chartConfig.secondary_y_label_alt
    ? chartConfig.secondary_y_label_alt
    : chartConfig.secondary_y_label;

  const yTickFormatter = useMemo(() => {
    if (activeYFormat === "currency") return (v: number) => formatCurrency(v);
    if (activeYFormat === "number") return (v: number) => formatNumber(v);
    if (activeYFormat === "percent") return (v: number) => formatPercent(v);
    return (v: number) => String(v);
  }, [activeYFormat]);

  const yTooltipFormatter = useMemo(() => {
    if (activeYFormat === "currency") return (v: number) => formatCurrencyFull(v);
    if (activeYFormat === "number") return (v: number) => formatNumber(v);
    if (activeYFormat === "percent") return (v: number) => formatPercentFull(v);
    return (v: number) => String(v);
  }, [activeYFormat]);

  // Sort by y-value descending for bar charts; coerce numeric fields
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
        out[sl.y_key] = raw != null && raw !== "" ? Number(raw) : undefined;
        if (sl.y_key_alt) {
          const rawAlt = row[sl.y_key_alt];
          out[sl.y_key_alt] = rawAlt != null && rawAlt !== "" ? Number(rawAlt) : undefined;
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
        mapped.sort(
          (a, b) =>
            (b[activeYKey] as number) - (a[activeYKey] as number)
        );
      }
    }
    return mapped;
  }, [data, chartConfig.y_key, chartConfig.y_key_alt, chartConfig.chart_type, secondaryLines, activeYKey, barsConfig, hasBars, activeBarsKeys]);

  // Build color maps for bar charts.
  const colorKey = chartConfig.color_key;
  const isStacked = chartConfig.stacked;
  const BAR_ALPHAS = [0.85, 0.45];
  const { barFillSets, sectorLegendItems, barLegendItems } = useMemo(() => {
    const empty = { barFillSets: null as string[][] | null, sectorLegendItems: [] as { industry: string; color: string; isHighlighted: boolean }[], barLegendItems: [] as { label: string; color: string }[] };
    if (chartConfig.chart_type === "line") return empty;

    const numBars = hasBars ? barsConfig.length : 1;
    const bLegend = hasBars && !isStacked ? barsConfig.map((b) => ({ label: b.label, color: b.color })) : [];

    if (colorKey) {
      const groups = [...new Set(numericData.map((r) => String(r[colorKey] ?? "")))].sort();
      const colorMap: Record<string, string> = {};
      groups.forEach((g, i) => { colorMap[g] = INDUSTRY_PALETTE[i % INDUSTRY_PALETTE.length]; });

      const fillSets = Array.from({ length: numBars }, (_, barIdx) =>
        numericData.map((row) => {
          const group = String(row[colorKey] ?? "");
          const alpha = isStacked ? 0.85 : (BAR_ALPHAS[barIdx] ?? 0.7);
          return hexToRgba(colorMap[group] ?? INDUSTRY_PALETTE[0], alpha);
        })
      );
      const sItems = groups.map((g) => ({ industry: g, color: colorMap[g], isHighlighted: false }));
      return { barFillSets: fillSets, sectorLegendItems: sItems, barLegendItems: bLegend };
    }

    if (!entityId) {
      return { barFillSets: null, sectorLegendItems: [], barLegendItems: bLegend };
    }

    const selectedIndustry = String(
      numericData.find((r) => String(r[chartConfig.x_key]) === entityId)?.industry ?? ""
    );
    const industries = [...new Set(numericData.map((r) => String(r.industry ?? "")))];
    const colorMap: Record<string, string> = {};
    let paletteIdx = 0;
    for (const ind of industries) {
      if (ind === selectedIndustry) {
        colorMap[ind] = HIGHLIGHT_COLOR;
      } else {
        colorMap[ind] = INDUSTRY_PALETTE[paletteIdx % INDUSTRY_PALETTE.length];
        paletteIdx++;
      }
    }

    const fills = numericData.map((row) => {
      const ticker = String(row[chartConfig.x_key]);
      const industry = String(row.industry ?? "");
      const baseColor = colorMap[industry] ?? INDUSTRY_PALETTE[0];
      if (ticker === entityId) return hexToRgba(HIGHLIGHT_COLOR, HIGHLIGHT_ALPHA);
      if (industry === selectedIndustry) return hexToRgba(HIGHLIGHT_COLOR, SAME_INDUSTRY_ALPHA);
      return hexToRgba(baseColor, OTHER_ALPHA);
    });

    const sItems = industries.map((ind) => ({
      industry: ind, color: colorMap[ind], isHighlighted: ind === selectedIndustry,
    }));
    return { barFillSets: [fills], sectorLegendItems: sItems, barLegendItems: bLegend };
  }, [numericData, entityId, chartConfig.x_key, chartConfig.chart_type, colorKey, hasBars, barsConfig, isStacked]);

  const isLineChart = chartConfig.chart_type === "line";

  // Build ECharts option
  const option: EChartsOption = useMemo(() => {
    const xData = numericData.map((row) => String(row[chartConfig.x_key]));
    const series: EChartsOption["series"] = [];

    if (isLineChart) {
      // Primary line on left axis
      series.push({
        type: "line",
        name: activeYLabel ?? activeYKey,
        data: numericData.map((row) => {
          const v = row[activeYKey];
          return v != null ? Number(v) : null;
        }),
        yAxisIndex: 0,
        lineStyle: { color: chartConfig.color || "#3182ce", width: 1.5 },
        itemStyle: { color: chartConfig.color || "#3182ce" },
        showSymbol: false,
        animation: false,
        connectNulls: false,
      });

      // Secondary lines on right axis
      for (let idx = 0; idx < secondaryLines.length; idx++) {
        const sl = secondaryLines[idx];
        series.push({
          type: "line",
          name: activeSecondaryLabels[idx],
          data: numericData.map((row) => {
            const v = row[activeSecondaryKeys[idx]];
            return v != null ? Number(v) : null;
          }),
          yAxisIndex: hasSecondaryAxis ? 1 : 0,
          lineStyle: { color: sl.color, width: 1.5, opacity: 0.45 },
          itemStyle: { color: sl.color },
          showSymbol: false,
          animation: false,
          connectNulls: true,
        });
      }
    } else {
      // Bar chart
      if (hasBars) {
        barsConfig.forEach((bar, barIdx) => {
          const dataKey = activeBarsKeys[barIdx];
          series.push({
            type: "bar",
            name: bar.label,
            data: numericData.map((row, i) => ({
              value: Number(row[dataKey]) || 0,
              itemStyle: barFillSets?.[barIdx]?.[i]
                ? { color: barFillSets[barIdx][i] }
                : { color: bar.color },
            })),
            stack: isStacked ? "stack" : undefined,
          });
        });
      } else {
        series.push({
          type: "bar",
          name: activeYLabel ?? activeYKey,
          data: numericData.map((row, i) => ({
            value: Number(row[activeYKey]) || 0,
            itemStyle: barFillSets?.[0]?.[i]
              ? { color: barFillSets[0][i] }
              : { color: chartConfig.color },
          })),
        });
      }
    }

    // Legend
    const legendNames: string[] = [];
    const legendSelected: Record<string, boolean> = {};
    if (isLineChart && hasSecondaryAxis) {
      legendNames.push(activeYLabel ?? activeYKey);
      legendSelected[activeYLabel ?? activeYKey] = !hiddenKeys.has(activeYKey);
      for (let idx = 0; idx < secondaryLines.length; idx++) {
        legendNames.push(activeSecondaryLabels[idx]);
        legendSelected[activeSecondaryLabels[idx]] = !hiddenKeys.has(activeSecondaryKeys[idx]);
      }
    } else if (!isLineChart && (barLegendItems.length > 0 || sectorLegendItems.length > 0)) {
      if (barLegendItems.length > 0) {
        for (let idx = 0; idx < barLegendItems.length; idx++) {
          legendNames.push(barLegendItems[idx].label);
          legendSelected[barLegendItems[idx].label] = !hiddenKeys.has(activeBarsKeys[idx]);
        }
      }
    }

    const showLegend = legendNames.length > 0;

    // Build yAxis
    const yAxes: EChartsOption["yAxis"] = [
      {
        type: "value",
        axisLabel: { fontSize: 11, formatter: (v: number) => yTickFormatter(v) },
        ...(activeYLabel ? { name: activeYLabel, nameLocation: "middle", nameGap: 50, nameTextStyle: { fontSize: 11 } } : {}),
        ...(isLineChart ? { scale: true } : {}),
        splitLine: { lineStyle: { type: "dashed" as const, color: "#e2e8f0" } },
      },
    ];

    if (isLineChart && hasSecondaryAxis) {
      yAxes.push({
        type: "value",
        position: "right",
        axisLabel: { fontSize: 11, formatter: (v: number) => yTickFormatter(v) },
        ...(activeSecondaryYLabel ? { name: activeSecondaryYLabel, nameLocation: "middle", nameGap: 50, nameRotate: -90, nameTextStyle: { fontSize: 11 } } : {}),
        scale: true,
        splitLine: { show: false },
      });
    }

    return {
      grid: { left: 55, right: hasSecondaryAxis ? 55 : 12, top: 8, bottom: isLineChart ? (showLegend ? 55 : 40) : (showLegend ? 30 : 20) },
      xAxis: {
        type: "category",
        data: xData,
        axisLabel: {
          fontSize: 11,
          ...(isLineChart && xData.length > 12
            ? { interval: Math.ceil(xData.length / 10) - 1 }
            : {}),
        },
        ...(chartConfig.x_label
          ? { name: chartConfig.x_label, nameLocation: "middle", nameGap: 25, nameTextStyle: { fontSize: 11 } }
          : {}),
      },
      yAxis: yAxes,
      tooltip: {
        trigger: "axis",
        formatter: (params: unknown) => {
          const items = Array.isArray(params) ? params : [params];
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const first = items[0] as any;
          let html = `<div style="font-weight:600;margin-bottom:4px">${first.axisValue}</div>`;
          for (const item of items) {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const p = item as any;
            if (p.value == null) continue;
            const val = typeof p.value === "object" ? p.value.value : p.value;
            if (val == null) continue;
            html += `<div>${p.marker} ${p.seriesName}: ${yTooltipFormatter(val)}</div>`;
          }
          return html;
        },
      },
      series,
      ...(showLegend ? {
        legend: {
          data: legendNames,
          selected: legendSelected,
          bottom: 0,
          textStyle: { fontSize: 11 },
        },
      } : {}),
      ...(isLineChart ? {
        dataZoom: [
          { type: "inside", xAxisIndex: 0 },
        ],
      } : {}),
    };
  }, [numericData, chartConfig, isLineChart, activeYKey, activeYLabel, activeYFormat, hasSecondaryAxis,
      secondaryLines, activeSecondaryKeys, activeSecondaryLabels, activeSecondaryYLabel,
      hasBars, barsConfig, activeBarsKeys, barFillSets, isStacked, hiddenKeys, barLegendItems,
      sectorLegendItems, yTickFormatter, yTooltipFormatter]);

  // Map legend names back to data keys for toggle/solo
  const legendNameToKeyMap = useMemo(() => {
    const m: Record<string, string> = {};
    if (isLineChart && hasSecondaryAxis) {
      m[activeYLabel ?? activeYKey] = activeYKey;
      for (let idx = 0; idx < secondaryLines.length; idx++) {
        m[activeSecondaryLabels[idx]] = activeSecondaryKeys[idx];
      }
    } else if (!isLineChart && barLegendItems.length > 0) {
      for (let idx = 0; idx < barLegendItems.length; idx++) {
        m[barLegendItems[idx].label] = activeBarsKeys[idx];
      }
    }
    return m;
  }, [isLineChart, hasSecondaryAxis, activeYLabel, activeYKey, secondaryLines, activeSecondaryLabels, activeSecondaryKeys, barLegendItems, activeBarsKeys]);

  const allLegendDataKeys = useMemo(() => Object.values(legendNameToKeyMap), [legendNameToKeyMap]);

  const onEvents = useMemo(() => ({
    legendselectchanged: (params: { name: string }) => {
      const dataKey = legendNameToKeyMap[params.name];
      if (dataKey) legendToggle(dataKey);
    },
  }), [legendNameToKeyMap, legendToggle]);

  // Custom sector legend rendered below the chart (not managed by ECharts legend)
  const showSectorLegend = !isLineChart && sectorLegendItems.length > 0;

  return (
    <div className="chart-widget">
      <div className="chart-widget__header">
        <h3 className="chart-widget__title">{config.title}</h3>
        <div className="chart-widget__header-controls">
          {hasAltToggle && (
            <div className="chart-widget__toggle">
              <button
                className={`chart-widget__toggle-btn${!useAlt ? " chart-widget__toggle-btn--active" : ""}`}
                onClick={() => setUseAlt(false)}
              >
                $
              </button>
              <button
                className={`chart-widget__toggle-btn${useAlt ? " chart-widget__toggle-btn--active" : ""}`}
                onClick={() => setUseAlt(true)}
              >
                %
              </button>
            </div>
          )}
        </div>
      </div>
      {loading && (
        <div className="chart-widget__loading">
          <div className="spinner" />
        </div>
      )}
      {error && (
        <div className="chart-widget__error">
          <p>{error}</p>
          <button onClick={fetchData}>Retry</button>
        </div>
      )}
      {!loading && !error && data.length === 0 && (
        <div className="chart-widget__empty">No data available</div>
      )}
      {!loading && !error && data.length > 0 && (
        <div className="chart-widget__container">
          <ReactECharts
            option={option}
            style={{ height: "100%" }}
            notMerge
            onEvents={onEvents}
          />
          {showSectorLegend && (
            <div className="chart-widget__legend">
              {barLegendItems.map((item, idx) => {
                const dataKey = activeBarsKeys[idx];
                const isHidden = hiddenKeys.has(dataKey);
                const style: CSSProperties = {
                  cursor: "pointer",
                  opacity: isHidden ? 0.35 : 1,
                  textDecoration: isHidden ? "line-through" : "none",
                  userSelect: "none",
                };
                return (
                  <span
                    key={item.label}
                    className="chart-widget__legend-item"
                    style={style}
                    onClick={() => legendToggle(dataKey)}
                    onDoubleClick={(e) => { e.stopPropagation(); legendSolo(dataKey, allLegendDataKeys); }}
                  >
                    <span className="chart-widget__legend-swatch" style={{ background: item.color }} />
                    {item.label}
                  </span>
                );
              })}
              {sectorLegendItems.map((item) => (
                <span key={item.industry} className="chart-widget__legend-item">
                  <span
                    className="chart-widget__legend-swatch"
                    style={{
                      background: item.color,
                      opacity: item.isHighlighted ? SAME_INDUSTRY_ALPHA : OTHER_ALPHA,
                    }}
                  />
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
