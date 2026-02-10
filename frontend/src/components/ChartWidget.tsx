import { useEffect, useState, useCallback } from "react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import api from "../config/api";
import type { WidgetConfig, PaginatedResponse } from "../types/entities";
import "../styles/chart.css";

interface ChartWidgetProps {
  config: WidgetConfig;
}

export function ChartWidget({ config }: ChartWidgetProps) {
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

  const numericData = data.map((row) => ({
    ...row,
    [chartConfig.y_key]: Number(row[chartConfig.y_key]) || 0,
  }));

  return (
    <div className="chart-widget">
      <h3 className="chart-widget__title">{config.title}</h3>
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
          <ResponsiveContainer width="100%" height={300}>
            {chartConfig.chart_type === "line" ? (
              <LineChart data={numericData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey={chartConfig.x_key} label={{ value: chartConfig.x_label, position: "insideBottom", offset: -5 }} />
                <YAxis label={{ value: chartConfig.y_label, angle: -90, position: "insideLeft" }} />
                <Tooltip />
                <Line type="monotone" dataKey={chartConfig.y_key} stroke={chartConfig.color} />
              </LineChart>
            ) : (
              <BarChart data={numericData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey={chartConfig.x_key} label={{ value: chartConfig.x_label, position: "insideBottom", offset: -5 }} />
                <YAxis label={{ value: chartConfig.y_label, angle: -90, position: "insideLeft" }} />
                <Tooltip />
                <Bar dataKey={chartConfig.y_key} fill={chartConfig.color} />
              </BarChart>
            )}
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
