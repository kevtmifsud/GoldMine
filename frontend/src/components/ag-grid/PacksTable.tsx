import { useMemo } from "react";
import type { ColDef } from "ag-grid-community";
import type { AnalystPack } from "../../types/entities";
import { PackNameRenderer } from "./PackNameRenderer";
import { PackActionRenderer } from "./PackActionRenderer";
import { AppGrid } from "./AppGrid";
import { useGridColumnManager } from "../../hooks/useGridColumnManager";
import { SetFilter } from "./SetFilter";
import { dateFilterParams } from "./filters";

export interface PacksTableProps {
  packs: AnalystPack[];
  showVisibility?: boolean;
  showDelete?: boolean;
  isOwner: (pack: AnalystPack) => boolean;
  onEdit: (pack: AnalystPack) => void;
  onDelete?: (pack: AnalystPack) => void;
  onSendAlert: (pack: AnalystPack) => void;
  deletingId?: string | null;
}

export function PacksTable({
  packs,
  showVisibility = true,
  showDelete = true,
  isOwner,
  onEdit,
  onDelete,
  onSendAlert,
  deletingId,
}: PacksTableProps) {
  const allColumns = useMemo<ColDef<AnalystPack>[]>(
    () => [
      {
        headerName: "Pack Name",
        field: "name",
        cellRenderer: PackNameRenderer,
        sortable: true,
        filter: "agTextColumnFilter",
      },
      {
        headerName: "Tiles",
        colId: "tile_count",
        valueGetter: (params) => {
          const widgetCount = params.data?.widgets?.length ?? 0;
          const tileCount = params.data?.mcp_tiles?.length ?? 0;
          return widgetCount + tileCount;
        },
        valueFormatter: (params) =>
          params.value ? `${params.value} tile${params.value !== 1 ? "s" : ""}` : "—",
        sortable: true,
        width: 90,
        filter: false,
      },
      {
        headerName: "Source",
        colId: "source",
        valueGetter: (params) =>
          params.data?.source_conversation_id ? "Chat" : "Manual",
        cellRenderer: (params: { value?: string }) =>
          params.value === "Chat" ? (
            <span title="Generated from chat conversation" style={{ cursor: "default" }}>
              💬 Chat
            </span>
          ) : (
            <span style={{ color: "var(--color-text-secondary)" }}>Manual</span>
          ),
        sortable: true,
        width: 90,
        filter: false,
      },
      {
        headerName: "Owner",
        colId: "owner",
        valueGetter: (params) =>
          params.data?.owner_display_name || params.data?.owner || "",
        sortable: true,
        filter: "agTextColumnFilter",
      },
      {
        headerName: "Created",
        field: "created_at",
        valueFormatter: (params) =>
          params.value
            ? new Date(params.value).toLocaleDateString()
            : "\u2014",
        sortable: true,
        filter: "agDateColumnFilter",
        filterParams: dateFilterParams,
      },
      {
        headerName: "Visibility",
        field: "is_shared",
        valueGetter: (params) =>
          params.data?.is_shared ? "Public" : "Private",
        cellRenderer: (params: { value?: string }) => {
          if (!params.value) return null;
          const cls =
            "packs-list__visibility-badge" +
            (params.value === "Public" ? " packs-list__visibility-badge--public" : "");
          return (
            <span className={cls}>
              {params.value}
            </span>
          );
        },
        sortable: true,
        filter: SetFilter,
      },
      {
        headerName: "Actions",
        cellRenderer: PackActionRenderer,
        headerClass: "packs-list__th-actions",
        cellClass: "packs-list__td-actions",
        sortable: false,
        filter: false,
        floatingFilter: false,
        suppressHeaderMenuButton: true,
      },
    ],
    []
  );

  const defaultVisibleFields = useMemo(
    () => {
      const fields = ["name", "tile_count", "source", "owner", "created_at"];
      if (showVisibility) fields.push("is_shared");
      return fields;
    },
    [showVisibility]
  );

  const { columnDefs, contextMenuConfig } = useGridColumnManager<AnalystPack>({
    gridId: "analyst-packs",
    allColumns,
    defaultVisibleFields,
  });

  const context = useMemo(
    () => ({
      isOwner,
      onEdit,
      onDelete: showDelete ? onDelete : undefined,
      onSendAlert,
      deletingId,
    }),
    [isOwner, onEdit, onDelete, showDelete, onSendAlert, deletingId]
  );

  return (
    <AppGrid<AnalystPack>
      rowData={packs}
      columnDefs={columnDefs}
      context={context}
      domLayout="autoHeight"
      getRowId={(params) => params.data.pack_id}
      suppressPaginationPanel={true}
      contextMenu={contextMenuConfig}
      viewKey="analyst-packs"
    />
  );
}
