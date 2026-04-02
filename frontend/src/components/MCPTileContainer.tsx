import { useState, useEffect, useCallback } from "react";
import type { MCPTileRef } from "../types/entities";
import { executeTile } from "../config/viewsApi";
import { ChatMarkdown } from "./chat/ChatMarkdown";
import { MCPDataGrid } from "./MCPDataGrid";
import { MCPPlotlyChart } from "./MCPPlotlyChart";

interface MCPTileContainerProps {
  tile: MCPTileRef;
  packId: string;
  isOwner: boolean;
  onRemove?: () => void;
  onTitleChange?: (title: string) => void;
}

export function MCPTileContainer({
  tile,
  packId,
  isOwner,
  onRemove,
  onTitleChange,
}: MCPTileContainerProps) {
  const [tileData, setTileData] = useState<{
    rows: Record<string, unknown>[];
    columns: string[];
    formatted_markdown?: string | null;
    chart_config?: Record<string, unknown> | null;
  }>({ rows: [], columns: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastFetched, setLastFetched] = useState<Date | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await executeTile(packId, tile.tile_id);
      if (result.error) {
        setError(result.error);
        return;
      }
      setTileData({
        rows: result.rows,
        columns: result.columns,
        formatted_markdown: result.formatted_markdown,
        chart_config: result.chart_config,
      });
      setLastFetched(new Date());
    } catch {
      setError("Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [packId, tile.tile_id]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const displayTitle = tile.title_override || tile.title;

  return (
    <div className="mcp-tile">
      <div className="mcp-tile__header">
        {isOwner ? (
          <input
            className="mcp-tile__title-input"
            value={displayTitle}
            onChange={(e) => onTitleChange?.(e.target.value)}
          />
        ) : (
          <h3 className="mcp-tile__title">{displayTitle}</h3>
        )}
        <div className="mcp-tile__controls">
          <button
            className="mcp-tile__refresh"
            onClick={fetchData}
            disabled={loading}
            title="Refresh data"
          >
            ↻
          </button>
          {lastFetched && (
            <span className="mcp-tile__freshness">
              {formatRelativeTime(lastFetched)}
            </span>
          )}
          {isOwner && onRemove && (
            <button className="mcp-tile__remove" onClick={onRemove} title="Remove tile">
              ×
            </button>
          )}
        </div>
      </div>

      {loading && (
        <div className="mcp-tile__loading">Loading...</div>
      )}

      {error && (
        <div className="mcp-tile__error">
          {error}
          <button onClick={fetchData}>Retry</button>
        </div>
      )}

      {!loading && !error && (
        <>
          {tile.display_type === "ag_grid" && tileData.formatted_markdown ? (
            <div className="mcp-tile__markdown">
              <ChatMarkdown onCitationClick={() => {}}>
                {tileData.formatted_markdown}
              </ChatMarkdown>
            </div>
          ) : tile.display_type === "ag_grid" ? (
            <MCPDataGrid
              tile={tile}
              packId={packId}
              data={tileData.rows}
              columns={tileData.columns}
              isOwner={isOwner}
            />
          ) : tile.display_type.startsWith("plotly") ? (
            <MCPPlotlyChart
              tile={tile}
              data={tileData.rows}
              executionChartConfig={tileData.chart_config}
            />
          ) : tile.display_type === "number_card" ? (
            <MCPNumberCard data={tileData.rows} columns={tileData.columns} />
          ) : null}
        </>
      )}
    </div>
  );
}

function MCPNumberCard({
  data,
  columns,
}: {
  data: Record<string, unknown>[];
  columns: string[];
}) {
  if (data.length === 0 || columns.length === 0) {
    return <div className="mcp-tile__empty">No data</div>;
  }
  const row = data[0];
  return (
    <div className="mcp-number-card">
      {columns
        .filter((c) => !c.startsWith("_"))
        .map((col) => (
          <div key={col} className="mcp-number-card__item">
            <span className="mcp-number-card__label">{col.replace(/_/g, " ")}</span>
            <span className="mcp-number-card__value">{String(row[col] ?? "—")}</span>
          </div>
        ))}
    </div>
  );
}

function formatRelativeTime(date: Date): string {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}
