import { useMemo, useCallback } from "react";
import { AgGridReact } from "ag-grid-react";
import type { ColDef, GridReadyEvent, SortChangedEvent, ValueFormatterParams } from "ag-grid-community";
import { gridTheme } from "./ag-grid/theme";
import type { MCPTileRef } from "../types/entities";
import { updateTileState } from "../config/viewsApi";

interface MCPDataGridProps {
  tile: MCPTileRef;
  packId: string;
  data: Record<string, unknown>[];
  columns: string[];
  isOwner: boolean;
}

function formatCurrencyCell(v: unknown): string {
  if (v == null) return "—";
  const n = Number(v);
  if (isNaN(n)) return String(v);
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
  if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
  return `$${n.toFixed(2)}`;
}

function formatPercentCell(v: unknown): string {
  if (v == null) return "—";
  const n = Number(v);
  if (isNaN(n)) return String(v);
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(1)}%`;
}

function formatDateCell(v: unknown): string {
  if (!v) return "—";
  return String(v).slice(0, 10);
}

function buildColDefs(
  columns: string[],
  data: Record<string, unknown>[],
): ColDef[] {
  return columns
    .filter((col) => !col.startsWith("_"))
    .map((col) => {
      const sampleVal = data[0]?.[col];
      const isNumeric = typeof sampleVal === "number";
      const isDate = col.includes("date") || col.includes("_at");
      const isCurrency =
        isNumeric &&
        (col.includes("value") ||
          col.includes("pnl") ||
          col.includes("revenue") ||
          col.includes("price") ||
          col.includes("market") ||
          col.includes("cost") ||
          col.includes("actual"));
      const isPercent =
        isNumeric &&
        (col.includes("pct") ||
          col.includes("return") ||
          col.includes("growth") ||
          col.includes("yoy") ||
          col.includes("margin") ||
          col.includes("weight"));

      const def: ColDef = {
        field: col,
        headerName: col
          .replace(/_/g, " ")
          .replace(/\b\w/g, (l) => l.toUpperCase()),
        sortable: true,
        resizable: true,
        filter: isNumeric ? "agNumberColumnFilter" : "agTextColumnFilter",
      };

      if (isCurrency) {
        def.valueFormatter = (p: ValueFormatterParams) => formatCurrencyCell(p.value);
        def.type = "numericColumn";
      } else if (isPercent) {
        def.valueFormatter = (p: ValueFormatterParams) => formatPercentCell(p.value);
        def.type = "numericColumn";
        def.cellStyle = (p) => ({
          color:
            p.value != null && p.value < 0
              ? "#e53e3e"
              : p.value != null && p.value > 0
                ? "#38a169"
                : "inherit",
        });
      } else if (isDate) {
        def.valueFormatter = (p: ValueFormatterParams) => formatDateCell(p.value);
      }

      return def;
    });
}

export function MCPDataGrid({ tile, packId, data, columns, isOwner }: MCPDataGridProps) {
  const colDefs = useMemo(() => buildColDefs(columns, data), [columns, data]);

  const onGridReady = useCallback(
    (params: GridReadyEvent) => {
      const stateOverride = tile.state_override as Record<string, unknown> | null;
      if (stateOverride?.sort_by) {
        params.api.applyColumnState({
          state: [
            {
              colId: stateOverride.sort_by as string,
              sort: (stateOverride.sort_order as "asc" | "desc") ?? "asc",
            },
          ],
        });
      }
      if (stateOverride?.column_filters) {
        params.api.setFilterModel(stateOverride.column_filters as Record<string, unknown>);
      }
      params.api.sizeColumnsToFit();
    },
    [tile.state_override],
  );

  const onSortChanged = useCallback(
    (event: SortChangedEvent) => {
      if (!isOwner) return;
      const sortModel = event.api.getColumnState().filter((c) => c.sort);
      if (sortModel.length === 0) return;
      updateTileState(packId, tile.tile_id, {
        sort_by: sortModel[0].colId,
        sort_order: sortModel[0].sort ?? "asc",
      }).catch(() => {});
    },
    [packId, tile.tile_id, isOwner],
  );

  return (
    <div className="mcp-tile__grid" style={{ width: "100%", height: "100%" }}>
      <AgGridReact
        theme={gridTheme}
        rowData={data}
        columnDefs={colDefs}
        onGridReady={onGridReady}
        onSortChanged={onSortChanged}
        pagination={true}
        paginationPageSize={25}
        paginationPageSizeSelector={[10, 25, 50]}
        suppressCellFocus={true}
        animateRows={false}
      />
    </div>
  );
}
