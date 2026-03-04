import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import type { StudioWidget } from "../types/studio";
import "../styles/studio.css";

function formatCurrency(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1_000_000_000) return `${sign}$${(abs / 1_000_000_000).toFixed(1)}B`;
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(0)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

function formatNumber(value: number): string {
  return value.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function formatCurrencyFull(value: number): string {
  const sign = value < 0 ? "-" : "";
  return `${sign}$${Math.abs(value).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}

function formatPercentFull(value: number): string {
  return `${value.toFixed(2)}%`;
}

interface StudioChartWidgetProps {
  widget: StudioWidget;
}

export function StudioChartWidget({ widget }: StudioChartWidgetProps) {
  if (widget.echarts_option) {
    return (
      <div className="studio-chart-widget">
        <ReactECharts
          option={widget.echarts_option as EChartsOption}
          style={{ height: "100%" }}
          notMerge
        />
      </div>
    );
  }

  const { chart_type, chart_config, data } = widget;

  const yTickFormatter = useMemo(() => {
    if (chart_config.y_format === "currency") return (v: number) => formatCurrency(v);
    if (chart_config.y_format === "number") return (v: number) => formatNumber(v);
    if (chart_config.y_format === "percent") return (v: number) => formatPercent(v);
    return (v: number) => String(v);
  }, [chart_config.y_format]);

  const yTooltipFormatter = useMemo(() => {
    if (chart_config.y_format === "currency") return (v: number) => formatCurrencyFull(v);
    if (chart_config.y_format === "number") return (v: number) => formatNumber(v);
    if (chart_config.y_format === "percent") return (v: number) => formatPercentFull(v);
    return (v: number) => String(v);
  }, [chart_config.y_format]);

  const hasSeries = chart_config.series && chart_config.series.length > 0;

  // Coerce y values to numbers
  const numericData = useMemo(() => {
    if (hasSeries) {
      return data.map((row) => {
        const coerced: Record<string, unknown> = { ...row };
        for (const s of chart_config.series) {
          coerced[s.y_key] = Number(row[s.y_key]) || 0;
        }
        return coerced;
      });
    }
    return data.map((row) => ({
      ...row,
      [chart_config.y_key]: Number(row[chart_config.y_key]) || 0,
    }));
  }, [data, chart_config.y_key, chart_config.series, hasSeries]);

  if (data.length === 0) {
    return (
      <div className="studio-chart-widget__empty">No data available</div>
    );
  }

  const color = chart_config.color || "#3182ce";
  const xData = numericData.map((row) => String(row[chart_config.x_key]));

  const option: EChartsOption = useMemo(() => {
    const series: EChartsOption["series"] = [];

    if (hasSeries) {
      for (const s of chart_config.series) {
        if (chart_type === "bar") {
          series.push({
            type: "bar",
            name: s.label,
            data: numericData.map((row) => Number(row[s.y_key]) || 0),
            itemStyle: { color: s.color },
          });
        } else {
          series.push({
            type: "line",
            name: s.label,
            data: numericData.map((row) => Number(row[s.y_key]) || 0),
            lineStyle: { color: s.color, width: 1.5 },
            itemStyle: { color: s.color },
            showSymbol: false,
            animation: false,
          });
        }
      }
    } else if (chart_type === "line") {
      series.push({
        type: "line",
        data: numericData.map((row) => Number(row[chart_config.y_key]) || 0),
        lineStyle: { color, width: 1.5 },
        itemStyle: { color },
        showSymbol: false,
        animation: false,
      });
    } else {
      series.push({
        type: "bar",
        data: numericData.map((row) => Number(row[chart_config.y_key]) || 0),
        itemStyle: { color },
      });
    }

    return {
      grid: { left: 50, right: 12, top: 8, bottom: hasSeries ? 28 : 20 },
      xAxis: {
        type: "category",
        data: xData,
        axisLabel: { fontSize: 11 },
      },
      yAxis: {
        type: "value",
        axisLabel: {
          fontSize: 11,
          formatter: (v: number) => yTickFormatter(v),
        },
        ...(chart_config.y_label
          ? { name: chart_config.y_label, nameLocation: "middle", nameGap: 45, nameTextStyle: { fontSize: 11 } }
          : {}),
        ...(chart_type === "line" ? { scale: true } : {}),
      },
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
            html += `<div>${p.marker} ${p.seriesName}: ${yTooltipFormatter(p.value)}</div>`;
          }
          return html;
        },
      },
      series,
      ...(hasSeries ? { legend: { show: true, bottom: 0, textStyle: { fontSize: 11 } } } : {}),
    };
  }, [numericData, xData, chart_type, chart_config, color, hasSeries, yTickFormatter, yTooltipFormatter]);

  return (
    <div className="studio-chart-widget">
      <ReactECharts option={option} style={{ height: "100%" }} notMerge />
    </div>
  );
}
