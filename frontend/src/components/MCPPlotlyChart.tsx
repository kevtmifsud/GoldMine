import { useMemo, lazy, Suspense } from "react";
import type { MCPTileRef } from "../types/entities";

const Plot = lazy(() => import("react-plotly.js"));

interface MCPPlotlyChartProps {
  tile: MCPTileRef;
  data: Record<string, unknown>[];
  /** chart_config from the MCP execute response — preferred over tile.chart_config */
  executionChartConfig?: Record<string, unknown> | null;
}

export function MCPPlotlyChart({ tile, data, executionChartConfig }: MCPPlotlyChartProps) {
  // Prefer execution-time config (from MCP server), fall back to saved tile config
  const config = executionChartConfig || tile.chart_config;
  if (!config || data.length === 0) {
    return <div className="mcp-tile__empty">No data to chart</div>;
  }

  const { traces, layout } = useMemo(
    () => buildPlotlyData(data, config, tile.display_type),
    [data, config, tile.display_type],
  );

  return (
    <Suspense fallback={<div className="mcp-tile__loading">Loading chart...</div>}>
      <Plot
        data={traces}
        layout={layout}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: "100%", height: "100%" }}
        useResizeHandler
      />
    </Suspense>
  );
}

function buildPlotlyData(
  data: Record<string, unknown>[],
  config: Record<string, unknown>,
  displayType: string,
): {
  traces: Plotly.Data[];
  layout: Partial<Plotly.Layout>;
} {
  const xCol = (config.x_column as string) || "date";
  const yCol = (config.y_column as string) || "value";
  const seriesCol = config.series_column as string | undefined;
  const yLabel = (config.y_label as string) || yCol;
  const formatters = (config.formatters as Record<string, string>) || {};
  const yFormat = formatters[yCol] || "number";

  let traces: Plotly.Data[];

  if (seriesCol) {
    const groups = new Map<string, Record<string, unknown>[]>();
    for (const row of data) {
      const key = String(row[seriesCol] ?? "");
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(row);
    }

    traces = Array.from(groups.entries()).map(([name, rows]) => ({
      type: (displayType === "plotly_bar" ? "bar" : "scatter") as Plotly.PlotType,
      mode: "lines" as const,
      name,
      x: rows.map((r) => r[xCol]) as Plotly.Datum[],
      y: rows.map((r) => Number(r[yCol])),
      hovertemplate: "%{y}<extra>%{fullData.name}</extra>",
    })) as Plotly.Data[];
  } else {
    traces = [
      {
        type: (displayType === "plotly_bar" ? "bar" : "scatter") as Plotly.PlotType,
        mode: "lines" as const,
        name: yLabel,
        x: data.map((r) => r[xCol]) as Plotly.Datum[],
        y: data.map((r) => Number(r[yCol])),
        hovertemplate: "%{y}<extra></extra>",
      } as Plotly.Data,
    ];
  }

  const layout: Partial<Plotly.Layout> = {
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: { family: "Inter, sans-serif", size: 11 },
    margin: { l: 55, r: 12, t: 8, b: 55 },
    showlegend: traces.length > 1,
    legend: { orientation: "h", y: -0.12, x: 0.5, xanchor: "center", font: { size: 10 }, tracegroupgap: 5 },
    xaxis: { gridcolor: "#e2e8f0", tickfont: { size: 10 }, hoverformat: "%-m/%-d/%Y" },
    yaxis: {
      title: { text: yLabel },
      gridcolor: "#e2e8f0",
      tickfont: { size: 10 },
      tickformat:
        yFormat === "percent"
          ? ".1%"
          : yFormat === "currency"
            ? "$,.0f"
            : yFormat === "millions"
              ? "$,.0f"
              : ",d",
    },
    barmode: ((config.barmode as string) || "group") as Plotly.Layout["barmode"],
    hovermode: "x unified",
    autosize: true,
  };

  return { traces, layout };
}
