import { useEffect, useState, useCallback, useMemo } from "react";
import api from "../config/api";
import type { WidgetConfig, PaginatedResponse } from "../types/entities";
import "../styles/top-positions.css";

interface TopPosition {
  ticker: string;
  sector: string;
  side: string;
  exposure_dollars: number;
  exposure_pct: number;
}

function formatCompactCurrency(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1_000_000_000) return `${sign}$${(abs / 1_000_000_000).toFixed(1)}B`;
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(0)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

function rowBackground(
  exposure: number,
  maxExposure: number,
  side: "long" | "short",
): string {
  const minAlpha = 0.05;
  const maxAlpha = 0.35;
  const ratio = maxExposure > 0 ? Math.abs(exposure) / maxExposure : 0;
  // Power curve (^0.6) spreads out the middle values for more visible gradations
  const scaled = Math.pow(ratio, 0.6);
  const alpha = minAlpha + scaled * (maxAlpha - minAlpha);
  const color = side === "long" ? "56, 161, 105" : "229, 62, 62";
  return `rgba(${color}, ${alpha.toFixed(3)})`;
}

interface Props {
  config: WidgetConfig;
}

export function TopPositionsWidget({ config }: Props) {
  const [data, setData] = useState<TopPosition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sector, setSector] = useState("All");

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<PaginatedResponse<TopPosition>>(config.endpoint);
      setData(res.data.data);
    } catch {
      setError("Failed to load top positions");
    } finally {
      setLoading(false);
    }
  }, [config.endpoint]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const sectors = useMemo(() => {
    const unique = Array.from(new Set(data.map((r) => r.sector))).sort();
    return ["All", ...unique];
  }, [data]);

  const { longs, shorts } = useMemo(() => {
    const filtered = sector === "All" ? data : data.filter((r) => r.sector === sector);
    const l = filtered
      .filter((r) => r.side === "long")
      .sort((a, b) => Math.abs(b.exposure_dollars) - Math.abs(a.exposure_dollars))
      .slice(0, 10);
    const s = filtered
      .filter((r) => r.side === "short")
      .sort((a, b) => Math.abs(b.exposure_dollars) - Math.abs(a.exposure_dollars))
      .slice(0, 10);
    return { longs: l, shorts: s };
  }, [data, sector]);

  const maxLong = longs.length > 0 ? Math.abs(longs[0].exposure_dollars) : 0;
  const maxShort = shorts.length > 0 ? Math.abs(shorts[0].exposure_dollars) : 0;

  return (
    <div className="top-positions">
      <div className="top-positions__header">
        <span className="top-positions__title">{config.title}</span>
        <select
          className="top-positions__sector-select"
          value={sector}
          onChange={(e) => setSector(e.target.value)}
        >
          {sectors.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>
      {loading && <div className="top-positions__loading">Loading…</div>}
      {error && (
        <div className="top-positions__error">
          <span>{error}</span>
          <button onClick={fetchData}>Retry</button>
        </div>
      )}
      {!loading && !error && data.length === 0 && (
        <div className="top-positions__body">
          <div className="top-positions__empty">No positions data</div>
        </div>
      )}
      {!loading && !error && data.length > 0 && (
        <div className="top-positions__body">
          <PositionSection
            label="Long"
            side="long"
            rows={longs}
            maxExposure={maxLong}
          />
          <PositionSection
            label="Short"
            side="short"
            rows={shorts}
            maxExposure={maxShort}
          />
        </div>
      )}
    </div>
  );
}

function PositionSection({
  label,
  side,
  rows,
  maxExposure,
}: {
  label: string;
  side: "long" | "short";
  rows: TopPosition[];
  maxExposure: number;
}) {
  return (
    <div className="top-positions__section">
      <div
        className={`top-positions__section-label top-positions__section-label--${side}`}
      >
        {label}
      </div>
      <table className="top-positions__table">
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Sector</th>
            <th>Exposure</th>
            <th>Weight</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.ticker}
              style={{
                backgroundColor: rowBackground(row.exposure_dollars, maxExposure, side),
              }}
            >
              <td>{row.ticker}</td>
              <td>{row.sector}</td>
              <td>{formatCompactCurrency(row.exposure_dollars)}</td>
              <td>{row.exposure_pct.toFixed(1)}%</td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={4} style={{ textAlign: "center", color: "var(--color-text-secondary)" }}>
                None
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
