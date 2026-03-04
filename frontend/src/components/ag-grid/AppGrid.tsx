import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import type { AgGridReactProps } from "ag-grid-react";
import type { ColDef } from "ag-grid-community";
import type {
  ColumnMovedEvent,
  ColumnResizedEvent,
  FirstDataRenderedEvent,
  GridReadyEvent,
} from "ag-grid-community";
import { gridTheme } from "./theme";
import { GridContextMenu } from "./GridContextMenu";
import { saveGridView, restoreGridView } from "./gridViewPersistence";
import {
  applyCustomizations,
  isNumericColumn,
  hasRendererColumn,
  loadCustomizations,
  saveCustomizations,
} from "./gridCustomizations";
import type {
  ColumnFormatConfig,
  GridCustomizations,
} from "./gridCustomizations";
import {
  loadComputedColumns,
  saveComputedColumns,
  buildComputedColDefs,
  generateComputedId,
} from "./computedColumns";
import type { ComputedColumnDef } from "./computedColumns";
import { ComputedColumnDialog } from "./ComputedColumnDialog";
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
 * - Column rename & number formatting customizations (via viewKey)
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
    columnDefs: rawColumnDefs,
    ...rest
  } = props;

  const gridApiRef = useRef<import("ag-grid-community").GridApi<T> | null>(null);
  const restoringRef = useRef(false);
  const [gridReady, setGridReady] = useState(false);
  const [gridDirty, setGridDirty] = useState(false);

  // Column customizations (rename + format) — persisted to localStorage per viewKey.
  // Use lazy initializers so the first render already has localStorage data,
  // preventing a delayed column addition that would trigger AG Grid events and
  // falsely mark the grid as dirty.
  const [savedCustomizations, setSavedCustomizations] = useState<GridCustomizations>(
    () => (viewKey ? loadCustomizations(viewKey) : {}),
  );
  const [workingCustomizations, setWorkingCustomizations] = useState<GridCustomizations>(
    () => (viewKey ? loadCustomizations(viewKey) : {}),
  );

  // Computed columns — persisted to localStorage per viewKey
  const [savedComputedColumns, setSavedComputedColumns] = useState<ComputedColumnDef[]>(
    () => (viewKey ? loadComputedColumns(viewKey) : []),
  );
  const [workingComputedColumns, setWorkingComputedColumns] = useState<ComputedColumnDef[]>(
    () => (viewKey ? loadComputedColumns(viewKey) : []),
  );
  const [computedColumnDialog, setComputedColumnDialog] = useState<{
    editing: ComputedColumnDef | null;
  } | null>(null);

  // Reload customizations and computed columns when viewKey changes after mount
  const customInitRef = useRef(false);
  useEffect(() => {
    // Skip first run — lazy initializers already loaded the correct data
    if (!customInitRef.current) {
      customInitRef.current = true;
      return;
    }

    if (viewKey) {
      const loaded = loadCustomizations(viewKey);
      setSavedCustomizations(loaded);
      setWorkingCustomizations(loaded);

      const computedLoaded = loadComputedColumns(viewKey);
      setSavedComputedColumns(computedLoaded);
      setWorkingComputedColumns(computedLoaded);
    } else {
      setSavedCustomizations({});
      setWorkingCustomizations({});
      setSavedComputedColumns([]);
      setWorkingComputedColumns([]);
    }
  }, [viewKey]);

  // Keep a ref to the raw (pre-customization) columnDefs for looking up original info
  const rawColumnDefsRef = useRef(rawColumnDefs);
  rawColumnDefsRef.current = rawColumnDefs;

  // Apply customizations to produce customized columnDefs
  const customizedColumnDefs = useMemo(
    () =>
      rawColumnDefs
        ? applyCustomizations(rawColumnDefs as ColDef[], workingCustomizations)
        : undefined,
    [rawColumnDefs, workingCustomizations],
  );

  // Build computed column ColDefs and apply rename customizations
  const computedColDefs = useMemo(() => {
    const defs = buildComputedColDefs(workingComputedColumns);
    return defs.map((d) => {
      const id = d.colId as string;
      const custom = workingCustomizations[id];
      if (custom?.rename) {
        return { ...d, headerName: custom.rename };
      }
      return d;
    });
  }, [workingComputedColumns, workingCustomizations]);
  const finalColumnDefs = useMemo(
    () =>
      customizedColumnDefs
        ? [...customizedColumnDefs, ...computedColDefs]
        : undefined,
    [customizedColumnDefs, computedColDefs],
  );

  // Context menu state
  const [menuState, setMenuState] = useState<{
    position: { x: number; y: number };
    targetColumn: {
      field: string;
      headerName: string;
      originalHeaderName: string;
      isNumeric: boolean;
      hasRenderer: boolean;
      currentCustom?: import("./gridCustomizations").ColumnCustomization;
      isComputed?: boolean;
      computedDef?: ComputedColumnDef;
    } | null;
    hiddenComputedColumns: { field: string; headerName: string }[];
    totalVisibleCount: number;
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

  const workingCustomizationsRef = useRef(workingCustomizations);
  workingCustomizationsRef.current = workingCustomizations;

  const workingComputedColumnsRef = useRef(workingComputedColumns);
  workingComputedColumnsRef.current = workingComputedColumns;

  // Track where to insert a newly created computed column
  const insertAfterFieldRef = useRef<string | undefined>(undefined);
  const pendingMoveRef = useRef<{ colId: string; afterField: string } | null>(null);

  // Available fields for formula editor (from raw column defs)
  const availableFieldsForFormula = useMemo(() => {
    if (!rawColumnDefs) return [];
    return (rawColumnDefs as ColDef[])
      .filter((d) => d.field)
      .map((d) => ({
        field: d.field!,
        headerName:
          d.headerName ||
          d.field!.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      }));
  }, [rawColumnDefs]);

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

      // Delay resetting restoringRef so any AG Grid events that fire
      // asynchronously after restoration are still suppressed.
      setTimeout(() => {
        restoringRef.current = false;
      }, 0);
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

  // Restore / position computed columns after state changes
  useEffect(() => {
    const pending = pendingMoveRef.current;
    if (!pending || !gridApiRef.current) return;
    pendingMoveRef.current = null;

    // Wait for AG Grid to process the new column defs after React render
    setTimeout(() => {
      const api = gridApiRef.current;
      if (!api) return;
      const allCols = api.getAllGridColumns();
      if (!allCols) return;

      restoringRef.current = true;
      if (pending.afterField === "") {
        // Move to the very first position
        api.moveColumns([pending.colId], 0);
      } else {
        const targetIdx = allCols.findIndex(
          (c) => c.getColId() === pending.afterField,
        );
        if (targetIdx >= 0) {
          api.moveColumns([pending.colId], targetIdx + 1);
        }
      }
      restoringRef.current = false;
    }, 0);
  }, [workingComputedColumns]);

  // Customization dirty tracking
  const customizationsDirty =
    JSON.stringify(workingCustomizations) !== JSON.stringify(savedCustomizations);
  const computedColumnsDirty =
    JSON.stringify(workingComputedColumns) !== JSON.stringify(savedComputedColumns);

  // Combined dirty: grid-level changes OR column visibility changes OR customization/computed changes
  const isDirty = viewKey
    ? gridDirty || (contextMenu?.isDirty ?? false) || customizationsDirty || computedColumnsDirty
    : false;

  const handleSave = useCallback(() => {
    if (viewKeyRef.current && gridApiRef.current) {
      saveGridView(viewKeyRef.current, gridApiRef.current);
    }
    // Persist customizations
    if (viewKeyRef.current) {
      saveCustomizations(viewKeyRef.current, workingCustomizationsRef.current);
      setSavedCustomizations({ ...workingCustomizationsRef.current });
    }
    // Persist computed columns
    if (viewKeyRef.current) {
      saveComputedColumns(viewKeyRef.current, workingComputedColumnsRef.current);
      setSavedComputedColumns([...workingComputedColumnsRef.current]);
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
    // Revert customizations to saved
    const saved = viewKeyRef.current ? loadCustomizations(viewKeyRef.current) : {};
    setSavedCustomizations(saved);
    setWorkingCustomizations(saved);

    // Revert computed columns to saved
    const savedComputed = viewKeyRef.current ? loadComputedColumns(viewKeyRef.current) : [];
    setSavedComputedColumns(savedComputed);
    setWorkingComputedColumns(savedComputed);

    contextMenuRef.current?.onDiscard?.();
    setGridDirty(false);
  }, []);

  // ---- Customization callbacks ----

  const handleRenameColumn = useCallback((field: string, newName: string) => {
    setWorkingCustomizations((prev) => {
      const next = { ...prev };
      const existing = next[field] ?? {};
      if (newName) {
        next[field] = { ...existing, rename: newName };
      } else {
        // Clear rename
        const { rename: _, ...rest } = existing;
        if (Object.keys(rest).length === 0 || (!rest.format)) {
          delete next[field];
        } else {
          next[field] = rest;
        }
      }
      return next;
    });
  }, []);

  const handleFormatColumn = useCallback((field: string, format: ColumnFormatConfig) => {
    setWorkingCustomizations((prev) => {
      const next = { ...prev };
      const existing = next[field] ?? {};
      next[field] = { ...existing, format };
      return next;
    });
  }, []);

  const handleClearFormat = useCallback((field: string) => {
    setWorkingCustomizations((prev) => {
      const next = { ...prev };
      const existing = next[field];
      if (!existing) return prev;
      const { format: _, ...rest } = existing;
      if (Object.keys(rest).length === 0 || !rest.rename) {
        delete next[field];
      } else {
        next[field] = rest;
      }
      return next;
    });
  }, []);

  // ---- Computed column CRUD callbacks ----

  const handleAddComputedColumn = useCallback((def: ComputedColumnDef) => {
    const withId = { ...def, id: def.id || generateComputedId() };
    // Schedule a column move if we know where to insert
    if (insertAfterFieldRef.current) {
      pendingMoveRef.current = {
        colId: withId.id,
        afterField: insertAfterFieldRef.current,
      };
      insertAfterFieldRef.current = undefined;
    }
    setWorkingComputedColumns((prev) => [...prev, withId]);
    setComputedColumnDialog(null);
  }, []);

  const handleUpdateComputedColumn = useCallback((def: ComputedColumnDef) => {
    // Snapshot the column's current position so we can restore it after the
    // state update causes AG Grid to rebuild the ColDef (new valueGetter closure).
    const api = gridApiRef.current;
    if (api) {
      const allCols = api.getAllGridColumns();
      const colIdx = allCols?.findIndex((c) => c.getColId() === def.id) ?? -1;
      if (colIdx > 0) {
        // Record the column to the left as the anchor
        pendingMoveRef.current = {
          colId: def.id,
          afterField: allCols![colIdx - 1].getColId(),
        };
      } else if (colIdx === 0 && allCols && allCols.length > 1) {
        // Column is first — we'll handle this as "move to index 0" by using
        // a special sentinel; but simpler: use the existing move logic which
        // places after afterField, so use a beforeField approach instead.
        pendingMoveRef.current = { colId: def.id, afterField: "" };
      }
    }
    setWorkingComputedColumns((prev) =>
      prev.map((c) => (c.id === def.id ? def : c)),
    );
    setComputedColumnDialog(null);
  }, []);

  const handleDeleteComputedColumn = useCallback((id: string) => {
    setWorkingComputedColumns((prev) => prev.filter((c) => c.id !== id));
    setComputedColumnDialog(null);
  }, []);

  const handleSaveComputedColumn = useCallback(
    (def: ComputedColumnDef) => {
      if (def.id && workingComputedColumnsRef.current.some((c) => c.id === def.id)) {
        handleUpdateComputedColumn(def);
      } else {
        handleAddComputedColumn(def);
      }
    },
    [handleAddComputedColumn, handleUpdateComputedColumn],
  );

  // Wrap onRemoveColumn — computed columns are hidden via AG Grid API,
  // regular columns delegate to the parent's handler.
  const handleRemoveColumn = useCallback(
    (field: string) => {
      if (field.startsWith("computed_")) {
        gridApiRef.current?.setColumnsVisible([field], false);
        if (!restoringRef.current) setGridDirty(true);
      } else {
        contextMenu?.onRemoveColumn(field);
      }
    },
    [contextMenu],
  );

  // Wrap onAddColumn — re-show hidden computed columns via AG Grid API,
  // regular columns delegate to the parent's handler.
  const handleAddColumn = useCallback(
    (field: string) => {
      if (field.startsWith("computed_")) {
        gridApiRef.current?.setColumnsVisible([field], true);
        if (!restoringRef.current) setGridDirty(true);
      } else {
        contextMenu?.onAddColumn(field);
      }
    },
    [contextMenu],
  );

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
      const field = colDef.field || column.getColId();
      if (!field) return; // Skip action columns without a field

      // Look up the RAW (pre-customization) colDef for original info
      const rawDefs = (rawColumnDefsRef.current ?? []) as ColDef[];
      const rawColDef = rawDefs.find((d) => d.field === field) ?? colDef;

      const originalHeaderName =
        rawColDef.headerName ||
        field.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

      const currentCustom = workingCustomizationsRef.current[field];

      // Check if this is a computed column
      const isComputed = field.startsWith("computed_");
      const computedDef = isComputed
        ? workingComputedColumnsRef.current.find((c) => c.id === field)
        : undefined;

      // For computed columns, the definition name is the "original" name;
      // any rename customization is a user-applied nickname.
      const resolvedOriginalName = computedDef?.name ?? originalHeaderName;
      const resolvedHeaderName = currentCustom?.rename || resolvedOriginalName;

      // Compute hidden computed columns for the "Add Column" section
      const hiddenComputed = workingComputedColumnsRef.current
        .filter((c) => {
          const col = api.getColumn(c.id);
          return col && !col.isVisible();
        })
        .map((c) => ({
          field: c.id,
          headerName: workingCustomizationsRef.current[c.id]?.rename || c.name,
        }));

      const totalVisibleCount = api.getAllDisplayedColumns().length;

      setMenuState({
        position: { x: e.clientX, y: e.clientY },
        targetColumn: {
          field,
          headerName: resolvedHeaderName,
          originalHeaderName: resolvedOriginalName,
          isNumeric: isComputed ? false : isNumericColumn(rawColDef),
          hasRenderer: isComputed ? false : hasRendererColumn(rawColDef),
          currentCustom,
          isComputed,
          computedDef,
        },
        hiddenComputedColumns: hiddenComputed,
        totalVisibleCount,
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
          columnDefs={finalColumnDefs}
          {...rest}
        />
      </div>
      {contextMenu && menuState && (
        <GridContextMenu
          position={menuState.position}
          targetColumn={menuState.targetColumn}
          hiddenColumns={[
            ...contextMenu.hiddenColumns,
            ...menuState.hiddenComputedColumns,
          ]}
          canRemove={menuState.totalVisibleCount > 1}
          onAddColumn={handleAddColumn}
          onRemoveColumn={handleRemoveColumn}
          onRenameColumn={handleRenameColumn}
          onFormatColumn={handleFormatColumn}
          onClearFormat={handleClearFormat}
          onCreateComputedColumn={() => {
            insertAfterFieldRef.current = menuState?.targetColumn?.field;
            setComputedColumnDialog({ editing: null });
            setMenuState(null);
          }}
          onEditComputedColumn={(def) => {
            setComputedColumnDialog({ editing: def });
            setMenuState(null);
          }}
          onClose={() => setMenuState(null)}
        />
      )}
      {computedColumnDialog && (
        <ComputedColumnDialog
          existingColumn={computedColumnDialog.editing}
          availableFields={availableFieldsForFormula}
          onSave={handleSaveComputedColumn}
          onDelete={handleDeleteComputedColumn}
          onCancel={() => setComputedColumnDialog(null)}
        />
      )}
    </div>
  );
}
