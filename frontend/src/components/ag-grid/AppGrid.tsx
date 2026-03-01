import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import type { AgGridReactProps } from "ag-grid-react";
import type {
  ColumnMovedEvent,
  ColumnResizedEvent,
  FirstDataRenderedEvent,
  GridReadyEvent,
} from "ag-grid-community";
import { gridTheme } from "./theme";
import { GridContextMenu } from "./GridContextMenu";
import { saveGridView, restoreGridView } from "./gridViewPersistence";
import "./AppGrid.css";

export interface ContextMenuConfig {
  hiddenColumns: { field: string; headerName: string }[];
  onAddColumn: (field: string) => void;
  onRemoveColumn: (field: string) => void;
  visibleCount: number;
  isDirty?: boolean;
  onSave?: () => void;
  onDiscard?: () => void;
}

interface AppGridProps<T> extends AgGridReactProps<T> {
  contextMenu?: ContextMenuConfig;
  viewKey?: string;
}

/**
 * Standard AG Grid wrapper for the GoldMine app.
 *
 * Provides consistent defaults across all grids:
 * - Shared theme
 * - Header text wrapping with auto-height
 * - Auto-size columns to content; stretch to fill if few columns
 * - Column reordering enabled
 * - Optional right-click context menu for column management
 * - Optional view persistence with save/discard bar (via viewKey)
 *
 * All props are forwarded to AgGridReact and can override the defaults.
 *
 * IMPORTANT: defaultColDef and onFirstDataRendered are memoized so that
 * parent re-renders do not cause AG Grid to reprocess column definitions
 * and lose user-applied column state (reordering, sizing, etc.).
 */
export function AppGrid<T = unknown>(props: AppGridProps<T>) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const {
    defaultColDef: userDefaultColDef,
    onFirstDataRendered: userOnFirstDataRendered,
    onGridReady: userOnGridReady,
    contextMenu,
    viewKey,
    ...rest
  } = props;

  const gridApiRef = useRef<import("ag-grid-community").GridApi<T> | null>(null);
  const restoringRef = useRef(false);
  const [gridReady, setGridReady] = useState(false);
  const [gridDirty, setGridDirty] = useState(false);

  // Context menu state
  const [menuState, setMenuState] = useState<{
    position: { x: number; y: number };
    targetColumn: { field: string; headerName: string } | null;
  } | null>(null);

  // Keep refs to latest callbacks/props so our stable wrappers always
  // invoke the most recent version without changing identity.
  const userOnFirstDataRenderedRef = useRef(userOnFirstDataRendered);
  userOnFirstDataRenderedRef.current = userOnFirstDataRendered;

  const userOnGridReadyRef = useRef(userOnGridReady);
  userOnGridReadyRef.current = userOnGridReady;

  const viewKeyRef = useRef(viewKey);
  viewKeyRef.current = viewKey;

  const contextMenuRef = useRef(contextMenu);
  contextMenuRef.current = contextMenu;

  const mergedDefaultColDef = useMemo(
    () => ({
      wrapHeaderText: true,
      autoHeaderHeight: true,
      minWidth: 100,
      filter: "agTextColumnFilter" as const,
      floatingFilter: true,
      ...userDefaultColDef,
    }),
    [userDefaultColDef]
  );

  const handleFirstDataRendered = useCallback(
    (event: FirstDataRenderedEvent<T>) => {
      // Suppress dirty tracking during initial auto-sizing and view restoration
      restoringRef.current = true;

      event.api.autoSizeAllColumns(true);
      const totalWidth = event.api
        .getAllDisplayedColumns()
        .reduce((w, col) => w + col.getActualWidth(), 0);
      const gridWidth = wrapperRef.current?.clientWidth ?? 0;
      if (totalWidth < gridWidth) {
        event.api.sizeColumnsToFit();
      }

      // Restore saved view after auto-sizing (saved state overwrites auto-size)
      if (viewKeyRef.current) {
        restoreGridView(viewKeyRef.current, event.api);
      }

      restoringRef.current = false;
      userOnFirstDataRenderedRef.current?.(event);
    },
    []
  );

  const handleGridReady = useCallback(
    (event: GridReadyEvent<T>) => {
      gridApiRef.current = event.api;
      setGridReady(true);
      userOnGridReadyRef.current?.(event);
    },
    []
  );

  // Attach AG Grid event listeners for dirty tracking when viewKey is set.
  // Only track user-initiated changes — ignore programmatic resizing from
  // auto-size, sizeColumnsToFit, layout shifts, scrollbar changes, etc.
  useEffect(() => {
    if (!gridReady || !viewKey) return;
    const api = gridApiRef.current;
    if (!api) return;

    const markDirty = () => {
      if (!restoringRef.current) setGridDirty(true);
    };

    const onColumnResized = (e: ColumnResizedEvent) => {
      if (e.source === "uiColumnResized" && e.finished) markDirty();
    };

    const onColumnMoved = (e: ColumnMovedEvent) => {
      if (e.source === "uiColumnMoved") markDirty();
    };

    api.addEventListener("sortChanged", markDirty);
    api.addEventListener("filterChanged", markDirty);
    api.addEventListener("columnMoved", onColumnMoved);
    api.addEventListener("columnResized", onColumnResized);

    return () => {
      api.removeEventListener("sortChanged", markDirty);
      api.removeEventListener("filterChanged", markDirty);
      api.removeEventListener("columnMoved", onColumnMoved);
      api.removeEventListener("columnResized", onColumnResized);
    };
  }, [gridReady, viewKey]);

  // Combined dirty: grid-level changes OR column visibility changes
  const isDirty = viewKey
    ? gridDirty || (contextMenu?.isDirty ?? false)
    : false;

  const handleSave = useCallback(() => {
    if (viewKeyRef.current && gridApiRef.current) {
      saveGridView(viewKeyRef.current, gridApiRef.current);
    }
    contextMenuRef.current?.onSave?.();
    setGridDirty(false);
  }, []);

  const handleDiscard = useCallback(() => {
    const api = gridApiRef.current;
    if (viewKeyRef.current && api) {
      restoringRef.current = true;
      const restored = restoreGridView(viewKeyRef.current, api);
      if (!restored) {
        api.resetColumnState();
        api.setFilterModel(null);
      }
      restoringRef.current = false;
    }
    contextMenuRef.current?.onDiscard?.();
    setGridDirty(false);
  }, []);

  // Right-click handler for context menu
  const handleContextMenu = useCallback(
    (e: React.MouseEvent) => {
      if (!contextMenu) return;

      // Walk up to find the header cell or body cell
      let target = e.target as HTMLElement | null;
      let colId: string | null = null;
      while (target && target !== wrapperRef.current) {
        if (
          target.classList.contains("ag-header-cell") ||
          target.classList.contains("ag-cell")
        ) {
          colId = target.getAttribute("col-id");
          break;
        }
        target = target.parentElement;
      }

      if (!colId) return;

      e.preventDefault();

      // Look up column info from AG Grid API
      const api = gridApiRef.current;
      if (!api) return;

      const column = api.getColumn(colId);
      if (!column) return;

      const colDef = column.getColDef();
      const field = colDef.field;
      if (!field) return; // Skip action columns without a field

      const headerName =
        colDef.headerName || field.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

      setMenuState({
        position: { x: e.clientX, y: e.clientY },
        targetColumn: { field, headerName },
      });
    },
    [contextMenu]
  );

  return (
    <div
      ref={wrapperRef}
      className="app-grid-wrapper"
      onContextMenu={handleContextMenu}
    >
      {isDirty && (
        <div className="app-grid-save-bar">
          <span className="app-grid-save-bar__label">View modified</span>
          <div className="app-grid-save-bar__actions">
            <button
              className="app-grid-save-bar__btn app-grid-save-bar__btn--discard"
              onClick={handleDiscard}
            >
              Discard
            </button>
            <button
              className="app-grid-save-bar__btn app-grid-save-bar__btn--save"
              onClick={handleSave}
            >
              Save
            </button>
          </div>
        </div>
      )}
      <div className="app-grid-body">
        <AgGridReact<T>
          theme={gridTheme}
          defaultColDef={mergedDefaultColDef}
          onFirstDataRendered={handleFirstDataRendered}
          onGridReady={handleGridReady}
          suppressMovableColumns={false}
          {...rest}
        />
      </div>
      {contextMenu && menuState && (
        <GridContextMenu
          position={menuState.position}
          targetColumn={menuState.targetColumn}
          hiddenColumns={contextMenu.hiddenColumns}
          canRemove={contextMenu.visibleCount > 1}
          onAddColumn={contextMenu.onAddColumn}
          onRemoveColumn={contextMenu.onRemoveColumn}
          onClose={() => setMenuState(null)}
        />
      )}
    </div>
  );
}
