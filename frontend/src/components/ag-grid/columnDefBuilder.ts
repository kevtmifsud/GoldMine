import type { ColDef } from "ag-grid-community";
import type { ColumnConfig } from "../../types/entities";
import { getValueFormatter } from "./formatters";
import { TickerLinkRenderer } from "./TickerLinkRenderer";

export function buildColumnDefs(
  columns: ColumnConfig[],
  visibleColumns: Set<string>,
): ColDef[] {
  return columns.map((col) => {
    const filterType =
      col.format === "currency" || col.format === "percent" || col.format === "number"
        ? "agNumberColumnFilter"
        : "agTextColumnFilter";

    const def: ColDef = {
      field: col.key,
      headerName: col.label,
      sortable: col.sortable,
      hide: !visibleColumns.has(col.key),
      filter: filterType,
      valueFormatter: getValueFormatter(col.format),
    };

    if (col.key === "ticker") {
      def.cellRenderer = TickerLinkRenderer;
      // Don't apply valueFormatter when using a cell renderer
      delete def.valueFormatter;
    }

    return def;
  });
}
