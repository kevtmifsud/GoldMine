import { useEffect, useState, useCallback, useMemo, useRef, type CSSProperties } from "react";
import {
  BarChart,
  Bar,
  Cell,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceArea,
} from "recharts";
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
    return undefined;
  }, [activeYFormat]);

  const yTooltipFormatter = useMemo(() => {
    if (activeYFormat === "currency") return (v: number) => formatCurrencyFull(v);
    if (activeYFormat === "number") return (v: number) => formatNumber(v);
    if (activeYFormat === "percent") return (v: number) => formatPercentFull(v);
    return undefined;
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
        // Keep undefined for missing EPS points so Recharts skips them
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
        // Sort by sum of active bar values descending
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
  // barFillSets[i] is the Cell fill array for the i-th <Bar>.
  const colorKey = chartConfig.color_key;
  const isStacked = chartConfig.stacked;
  const BAR_ALPHAS = [0.85, 0.45];
  const { barFillSets, sectorLegendItems, barLegendItems } = useMemo(() => {
    const empty = { barFillSets: null as string[][] | null, sectorLegendItems: [] as { industry: string; color: string; isHighlighted: boolean }[], barLegendItems: [] as { label: string; color: string }[] };
    if (chartConfig.chart_type === "line") return empty;

    const numBars = hasBars ? barsConfig.length : 1;
    // When stacked, both bars share sector color — skip bar legend
    const bLegend = hasBars && !isStacked ? barsConfig.map((b) => ({ label: b.label, color: b.color })) : [];

    // Color by a generic grouping field (e.g. sector) — sort alphabetically for consistent palette
    if (colorKey) {
      const groups = [...new Set(numericData.map((r) => String(r[colorKey] ?? "")))].sort();
      const colorMap: Record<string, string> = {};
      groups.forEach((g, i) => { colorMap[g] = INDUSTRY_PALETTE[i % INDUSTRY_PALETTE.length]; });

      const fillSets = Array.from({ length: numBars }, (_, barIdx) =>
        numericData.map((row) => {
          const group = String(row[colorKey] ?? "");
          // Stacked: same alpha for all bars; grouped: differentiate by opacity
          const alpha = isStacked ? 0.85 : (BAR_ALPHAS[barIdx] ?? 0.7);
          return hexToRgba(colorMap[group] ?? INDUSTRY_PALETTE[0], alpha);
        })
      );
      const sItems = groups.map((g) => ({ industry: g, color: colorMap[g], isHighlighted: false }));
      return { barFillSets: fillSets, sectorLegendItems: sItems, barLegendItems: bLegend };
    }

    // Highlight a specific entity and its industry peers
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
  }, [numericData, entityId, chartConfig.x_key, chartConfig.chart_type, colorKey, hasBars, barsConfig]);

  // --- Zoom state for line charts ---
  const isLineChart = chartConfig.chart_type === "line";
  const [zoomLeft, setZoomLeft] = useState<string | null>(null);
  const [zoomRight, setZoomRight] = useState<string | null>(null);
  const [selectingLeft, setSelectingLeft] = useState<string | null>(null);
  const [selectingRight, setSelectingRight] = useState<string | null>(null);
  const isDragging = useRef(false);

  const zoomedData = useMemo(() => {
    if (!isLineChart || !zoomLeft || !zoomRight) return numericData;
    const xKey = chartConfig.x_key;
    const leftIdx = numericData.findIndex((d) => String(d[xKey]) === zoomLeft);
    const rightIdx = numericData.findIndex((d) => String(d[xKey]) === zoomRight);
    if (leftIdx === -1 || rightIdx === -1) return numericData;
    const lo = Math.min(leftIdx, rightIdx);
    const hi = Math.max(leftIdx, rightIdx);
    return numericData.slice(lo, hi + 1);
  }, [numericData, zoomLeft, zoomRight, isLineChart, chartConfig.x_key]);

  const isZoomed = isLineChart && zoomLeft !== null && zoomRight !== null;

  const handleMouseDown = useCallback(
    (e: { activeLabel?: string }) => {
      if (!isLineChart || !e?.activeLabel) return;
      isDragging.current = true;
      setSelectingLeft(e.activeLabel);
      setSelectingRight(null);
    },
    [isLineChart]
  );

  const handleMouseMove = useCallback(
    (e: { activeLabel?: string }) => {
      if (!isDragging.current || !e?.activeLabel) return;
      setSelectingRight(e.activeLabel);
    },
    []
  );

  const handleMouseUp = useCallback(() => {
    if (!isDragging.current) return;
    isDragging.current = false;
    if (selectingLeft && selectingRight && selectingLeft !== selectingRight) {
      // Determine correct order based on data indices
      const xKey = chartConfig.x_key;
      const leftIdx = numericData.findIndex((d) => String(d[xKey]) === selectingLeft);
      const rightIdx = numericData.findIndex((d) => String(d[xKey]) === selectingRight);
      if (leftIdx !== -1 && rightIdx !== -1 && leftIdx !== rightIdx) {
        const lo = Math.min(leftIdx, rightIdx);
        const hi = Math.max(leftIdx, rightIdx);
        setZoomLeft(String(numericData[lo][xKey]));
        setZoomRight(String(numericData[hi][xKey]));
      }
    }
    setSelectingLeft(null);
    setSelectingRight(null);
  }, [selectingLeft, selectingRight, numericData, chartConfig.x_key]);

  const handleResetZoom = useCallback(() => {
    setZoomLeft(null);
    setZoomRight(null);
    setSelectingLeft(null);
    setSelectingRight(null);
  }, []);

  // Thin out x-axis ticks for line charts to avoid overlap
  const lineXTicks = useMemo(() => {
    if (!isLineChart) return undefined;
    const src = zoomedData;
    if (src.length <= 12) return undefined;
    const step = Math.ceil(src.length / 10);
    return src
      .filter((_, i) => i % step === 0)
      .map((d) => String(d[chartConfig.x_key]));
  }, [isLineChart, zoomedData, chartConfig.x_key]);

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
          {isZoomed && (
            <button className="chart-widget__zoom-reset" onClick={handleResetZoom}>
              Reset Zoom
            </button>
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
        <div
          className={`chart-widget__container${isLineChart ? (isZoomed ? " chart-widget__container--zoomed" : " chart-widget__container--zoomable") : ""}`}
          onDoubleClick={isZoomed ? handleResetZoom : undefined}
        >
          <ResponsiveContainer width="100%" height={300}>
            {isLineChart && hasSecondaryAxis ? (
              <LineChart
                data={zoomedData}
                onMouseDown={handleMouseDown as (e: unknown) => void}
                onMouseMove={handleMouseMove as (e: unknown) => void}
                onMouseUp={handleMouseUp}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey={chartConfig.x_key}
                  ticks={lineXTicks}
                  tick={{ fontSize: 11 }}
                  label={{ value: chartConfig.x_label, position: "insideBottom", offset: -5 }}
                />
                <YAxis
                  yAxisId="left"
                  tickFormatter={yTickFormatter}
                  label={{ value: activeYLabel, angle: -90, position: "insideLeft" }}
                  domain={["auto", "auto"]}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  tickFormatter={yTickFormatter}
                  label={{ value: activeSecondaryYLabel ?? "", angle: 90, position: "insideRight" }}
                  domain={["auto", "auto"]}
                />
                <Tooltip formatter={yTooltipFormatter as never} />
                <Legend
                  content={() => {
                    const items: { key: string; label: string; color: string }[] = [
                      { key: activeYKey, label: activeYLabel ?? activeYKey, color: chartConfig.color || "#3182ce" },
                      ...secondaryLines.map((sl, idx) => ({
                        key: activeSecondaryKeys[idx],
                        label: activeSecondaryLabels[idx],
                        color: sl.color,
                      })),
                    ];
                    const allKeys = items.map((i) => i.key);
                    return (
                      <div className="chart-widget__legend">
                        {items.map((item) => {
                          const isHidden = hiddenKeys.has(item.key);
                          const style: CSSProperties = {
                            cursor: "pointer",
                            opacity: isHidden ? 0.35 : 1,
                            textDecoration: isHidden ? "line-through" : "none",
                            userSelect: "none",
                          };
                          return (
                            <span
                              key={item.key}
                              className="chart-widget__legend-item"
                              style={style}
                              onClick={() => legendToggle(item.key)}
                              onDoubleClick={(e) => { e.stopPropagation(); legendSolo(item.key, allKeys); }}
                            >
                              <span className="chart-widget__legend-swatch" style={{ background: item.color }} />
                              {item.label}
                            </span>
                          );
                        })}
                      </div>
                    );
                  }}
                />
                <Line
                  yAxisId="left"
                  type="linear"
                  dataKey={activeYKey}
                  stroke={chartConfig.color || "#3182ce"}
                  dot={false}
                  strokeWidth={1.5}
                  isAnimationActive={false}
                  hide={hiddenKeys.has(activeYKey)}
                />
                {secondaryLines.map((sl, idx) => (
                  <Line
                    key={sl.y_key}
                    yAxisId="right"
                    type="linear"
                    dataKey={activeSecondaryKeys[idx]}
                    stroke={sl.color}
                    strokeOpacity={0.45}
                    dot={false}
                    strokeWidth={1.5}
                    connectNulls
                    isAnimationActive={false}
                    hide={hiddenKeys.has(activeSecondaryKeys[idx])}
                  />
                ))}
                {selectingLeft && selectingRight && (
                  <ReferenceArea
                    yAxisId="left"
                    x1={selectingLeft}
                    x2={selectingRight}
                    strokeOpacity={0.3}
                    fill="#3182ce"
                    fillOpacity={0.15}
                  />
                )}
              </LineChart>
            ) : isLineChart ? (
              <LineChart
                data={zoomedData}
                onMouseDown={handleMouseDown as (e: unknown) => void}
                onMouseMove={handleMouseMove as (e: unknown) => void}
                onMouseUp={handleMouseUp}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey={chartConfig.x_key}
                  ticks={lineXTicks}
                  tick={{ fontSize: 11 }}
                  label={{ value: chartConfig.x_label, position: "insideBottom", offset: -5 }}
                />
                <YAxis
                  yAxisId="left"
                  tickFormatter={yTickFormatter}
                  label={{ value: chartConfig.y_label, angle: -90, position: "insideLeft" }}
                  domain={["auto", "auto"]}
                />
                <Tooltip formatter={yTooltipFormatter as never} />
                <Line
                  yAxisId="left"
                  type="linear"
                  dataKey={chartConfig.y_key}
                  stroke={chartConfig.color || "#3182ce"}
                  dot={false}
                  strokeWidth={1.5}
                  isAnimationActive={false}
                />
                {selectingLeft && selectingRight && (
                  <ReferenceArea
                    yAxisId="left"
                    x1={selectingLeft}
                    x2={selectingRight}
                    strokeOpacity={0.3}
                    fill="#3182ce"
                    fillOpacity={0.15}
                  />
                )}
              </LineChart>
            ) : (
              <BarChart data={numericData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey={chartConfig.x_key} label={{ value: chartConfig.x_label, position: "insideBottom", offset: -5 }} />
                <YAxis tickFormatter={yTickFormatter} label={{ value: activeYLabel, angle: -90, position: "insideLeft" }} />
                <Tooltip formatter={yTooltipFormatter as never} />
                {hasBars ? (
                  barsConfig.map((bar, barIdx) => (
                    <Bar key={bar.y_key} dataKey={activeBarsKeys[barIdx]} fill={bar.color} name={bar.label} stackId={isStacked ? "stack" : undefined} hide={hiddenKeys.has(activeBarsKeys[barIdx])}>
                      {barFillSets?.[barIdx]?.map((fill, i) => (
                        <Cell key={i} fill={fill} />
                      ))}
                    </Bar>
                  ))
                ) : (
                  <Bar dataKey={activeYKey} fill={chartConfig.color}>
                    {barFillSets?.[0]?.map((fill, i) => (
                      <Cell key={i} fill={fill} />
                    ))}
                  </Bar>
                )}
                {(barLegendItems.length > 0 || sectorLegendItems.length > 0) && (
                  <Legend
                    content={() => (
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
                              onDoubleClick={(e) => { e.stopPropagation(); legendSolo(dataKey, [...activeBarsKeys]); }}
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
                  />
                )}
              </BarChart>
            )}
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
