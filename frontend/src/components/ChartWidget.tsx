import { useEffect, useState, useCallback, useMemo, useRef } from "react";
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
import api from "../config/api";
import type { WidgetConfig, PaginatedResponse } from "../types/entities";
import "../styles/chart.css";

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

  // Sort by y-value descending for bar charts; coerce numeric fields
  const numericData = useMemo(() => {
    const mapped = data.map((row) => {
      const out: Record<string, unknown> = {
        ...row,
        [chartConfig.y_key]: Number(row[chartConfig.y_key]) || 0,
      };
      for (const sl of secondaryLines) {
        const raw = row[sl.y_key];
        // Keep undefined for missing EPS points so Recharts skips them
        out[sl.y_key] = raw != null && raw !== "" ? Number(raw) : undefined;
      }
      return out;
    });
    if (chartConfig.chart_type !== "line") {
      mapped.sort(
        (a, b) =>
          (b[chartConfig.y_key] as number) - (a[chartConfig.y_key] as number)
      );
    }
    return mapped;
  }, [data, chartConfig.y_key, chartConfig.chart_type, secondaryLines]);

  // Build industry color map
  const { barFills, legendItems } = useMemo(() => {
    if (!entityId || chartConfig.chart_type === "line") {
      return { barFills: null, legendItems: [] };
    }

    const selectedIndustry = String(
      numericData.find((r) => String(r[chartConfig.x_key]) === entityId)
        ?.industry ?? ""
    );

    // Assign a color per unique industry (excluding the highlighted one)
    const industries = [
      ...new Set(numericData.map((r) => String(r.industry ?? ""))),
    ];
    const colorMap: Record<string, string> = {};
    let paletteIdx = 0;
    for (const ind of industries) {
      if (ind === selectedIndustry) {
        colorMap[ind] = HIGHLIGHT_COLOR;
      } else {
        colorMap[ind] =
          INDUSTRY_PALETTE[paletteIdx % INDUSTRY_PALETTE.length];
        paletteIdx++;
      }
    }

    const fills = numericData.map((row) => {
      const ticker = String(row[chartConfig.x_key]);
      const industry = String(row.industry ?? "");
      const baseColor = colorMap[industry] ?? INDUSTRY_PALETTE[0];

      if (ticker === entityId) {
        return hexToRgba(HIGHLIGHT_COLOR, HIGHLIGHT_ALPHA);
      }
      if (industry === selectedIndustry) {
        return hexToRgba(HIGHLIGHT_COLOR, SAME_INDUSTRY_ALPHA);
      }
      return hexToRgba(baseColor, OTHER_ALPHA);
    });

    // Build legend entries
    const items = industries.map((ind) => ({
      industry: ind,
      color: colorMap[ind],
      isHighlighted: ind === selectedIndustry,
    }));

    return { barFills: fills, legendItems: items };
  }, [numericData, entityId, chartConfig.x_key, chartConfig.chart_type]);

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
        {isZoomed && (
          <button className="chart-widget__zoom-reset" onClick={handleResetZoom}>
            Reset Zoom
          </button>
        )}
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
            {isLineChart ? (
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
                  label={{ value: chartConfig.y_label, angle: -90, position: "insideLeft" }}
                  domain={["auto", "auto"]}
                />
                {hasSecondaryAxis && (
                  <YAxis
                    yAxisId="right"
                    orientation="right"
                    label={{ value: chartConfig.secondary_y_label ?? "", angle: 90, position: "insideRight" }}
                    domain={["auto", "auto"]}
                  />
                )}
                <Tooltip />
                {hasSecondaryAxis && (
                  <Legend
                    content={() => (
                      <div className="chart-widget__legend">
                        <span className="chart-widget__legend-item">
                          <span className="chart-widget__legend-swatch" style={{ background: chartConfig.color || "#3182ce" }} />
                          {chartConfig.y_label}
                        </span>
                        {secondaryLines.map((sl) => (
                          <span key={sl.y_key} className="chart-widget__legend-item">
                            <span className="chart-widget__legend-swatch" style={{ background: sl.color }} />
                            {sl.label}
                          </span>
                        ))}
                      </div>
                    )}
                  />
                )}
                <Line
                  yAxisId="left"
                  type="monotone"
                  dataKey={chartConfig.y_key}
                  stroke={chartConfig.color || "#3182ce"}
                  dot={false}
                  strokeWidth={1.5}
                  isAnimationActive={false}
                />
                {secondaryLines.map((sl) => (
                  <Line
                    key={sl.y_key}
                    yAxisId={hasSecondaryAxis ? "right" : "left"}
                    type="monotone"
                    dataKey={sl.y_key}
                    stroke={sl.color}
                    dot={{ r: 3, fill: sl.color }}
                    strokeWidth={0}
                    connectNulls={false}
                    isAnimationActive={false}
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
            ) : (
              <BarChart data={numericData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey={chartConfig.x_key} label={{ value: chartConfig.x_label, position: "insideBottom", offset: -5 }} />
                <YAxis label={{ value: chartConfig.y_label, angle: -90, position: "insideLeft" }} />
                <Tooltip />
                <Bar dataKey={chartConfig.y_key} fill={chartConfig.color}>
                  {barFills
                    ? numericData.map((_entry, index) => (
                        <Cell key={index} fill={barFills[index]} />
                      ))
                    : null}
                </Bar>
                {legendItems.length > 0 && (
                  <Legend
                    content={() => (
                      <div className="chart-widget__legend">
                        {legendItems.map((item) => (
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
