import type { ColDef } from "ag-grid-community";
import type { ColumnConfig } from "../../types/entities";
import { getValueFormatter } from "./formatters";
import { dateFilterParams } from "./filters";
import { getEntityRenderer } from "./EntityLinkRenderer";
import { TranscriptViewButtonRenderer } from "./TranscriptViewButtonRenderer";
import { UrlRenderer } from "./UrlRenderer";

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

    if (col.entity_type) {
      def.cellRenderer = getEntityRenderer(col.entity_type, col.entity_id_field);
      delete def.valueFormatter;
    }

    if (col.format === "url") {
      def.cellRenderer = UrlRenderer;
      delete def.valueFormatter;
    }

    if (col.format === "transcript_viewer") {
      def.cellRenderer = TranscriptViewButtonRenderer;
      def.sortable = false;
      def.filter = false;
      delete def.valueFormatter;
    }

    return def;
  });
}
