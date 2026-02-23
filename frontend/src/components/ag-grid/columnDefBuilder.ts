import type { ColDef } from "ag-grid-community";
import type { ColumnConfig } from "../../types/entities";
import { getValueFormatter } from "./formatters";
import { dateFilterParams } from "./filters";
import { TickerLinkRenderer } from "./TickerLinkRenderer";

function getFilterConfig(format: string): Partial<ColDef> {
  switch (format) {
    case "currency":
    case "percent":
    case "number":
      return { filter: "agNumberColumnFilter" };
    case "date":
      return { filter: "agDateColumnFilter", filterParams: dateFilterParams };
    default:
      return { filter: "agTextColumnFilter" };
  }
}

export function buildColumnDefs(
  columns: ColumnConfig[],
  visibleColumns: Set<string>,
): ColDef[] {
  return columns.map((col) => {
    const def: ColDef = {
      field: col.key,
      headerName: col.label,
      sortable: col.sortable,
      hide: !visibleColumns.has(col.key),
      ...getFilterConfig(col.format),
      valueFormatter: getValueFormatter(col.format),
    };

    if (col.key === "ticker") {
      def.cellRenderer = TickerLinkRenderer;
      delete def.valueFormatter;
    }

    return def;
  });
}
