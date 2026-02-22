import { useMemo } from "react";
import { AgGridReact } from "ag-grid-react";
import type { ColDef } from "ag-grid-community";
import type { AnalystPack } from "../../types/entities";
import { PackNameRenderer } from "./PackNameRenderer";
import { PackActionRenderer } from "./PackActionRenderer";
import { gridTheme } from "./theme";

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
  const columnDefs = useMemo<ColDef<AnalystPack>[]>(() => {
    const cols: ColDef<AnalystPack>[] = [
      {
        headerName: "Pack Name",
        field: "name",
        cellRenderer: PackNameRenderer,
        sortable: true,
        filter: "agTextColumnFilter",
      },
      {
        headerName: "Owner",
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
      },
    ];

    if (showVisibility) {
      cols.push({
        headerName: "Visibility",
        field: "is_shared",
        cellRenderer: (params: { data?: AnalystPack }) => {
          if (!params.data) return null;
          const cls =
            "packs-list__visibility-badge" +
            (params.data.is_shared ? " packs-list__visibility-badge--public" : "");
          return (
            <span className={cls}>
              {params.data.is_shared ? "Public" : "Private"}
            </span>
          );
        },
        sortable: true,
        filter: "agTextColumnFilter",
      });
    }

    cols.push({
      headerName: "Actions",
      cellRenderer: PackActionRenderer,
      headerClass: "packs-list__th-actions",
      cellClass: "packs-list__td-actions",
      sortable: false,
      filter: false,
      suppressHeaderMenuButton: true,
    });

    return cols;
  }, [showVisibility]);

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
    <div>
      <AgGridReact<AnalystPack>
        theme={gridTheme}
        rowData={packs}
        columnDefs={columnDefs}
        autoSizeStrategy={{ type: "fitCellContents", skipHeader: true }}
        defaultColDef={{ wrapHeaderText: true, autoHeaderHeight: true, minWidth: 100 }}
        context={context}
        domLayout="autoHeight"
        getRowId={(params) => params.data.pack_id}
        suppressMovableColumns={false}
        suppressPaginationPanel={true}
      />
    </div>
  );
}
