import { useCallback, useMemo, useRef } from "react";
import { AgGridReact } from "ag-grid-react";
import type { AgGridReactProps } from "ag-grid-react";
import type { FirstDataRenderedEvent } from "ag-grid-community";
import { gridTheme } from "./theme";

/**
 * Standard AG Grid wrapper for the GoldMine app.
 *
 * Provides consistent defaults across all grids:
 * - Shared theme
 * - Header text wrapping with auto-height
 * - Auto-size columns to content; stretch to fill if few columns
 * - Column reordering enabled
 *
 * All props are forwarded to AgGridReact and can override the defaults.
 *
 * IMPORTANT: defaultColDef and onFirstDataRendered are memoized so that
 * parent re-renders do not cause AG Grid to reprocess column definitions
 * and lose user-applied column state (reordering, sizing, etc.).
 */
export function AppGrid<T = unknown>(props: AgGridReactProps<T>) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const {
    defaultColDef: userDefaultColDef,
    onFirstDataRendered: userOnFirstDataRendered,
    ...rest
  } = props;

  // Keep a ref to the latest user callback so our stable wrapper always
  // invokes the most recent version without changing identity.
  const userOnFirstDataRenderedRef = useRef(userOnFirstDataRendered);
  userOnFirstDataRenderedRef.current = userOnFirstDataRendered;

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
      event.api.autoSizeAllColumns(true);
      const totalWidth = event.api
        .getAllDisplayedColumns()
        .reduce((w, col) => w + col.getActualWidth(), 0);
      const gridWidth = wrapperRef.current?.clientWidth ?? 0;
      if (totalWidth < gridWidth) {
        event.api.sizeColumnsToFit();
      }
      userOnFirstDataRenderedRef.current?.(event);
    },
    []
  );

  return (
    <div ref={wrapperRef} style={{ height: "100%" }}>
      <AgGridReact<T>
        theme={gridTheme}
        defaultColDef={mergedDefaultColDef}
        onFirstDataRendered={handleFirstDataRendered}
        suppressMovableColumns={false}
        {...rest}
      />
    </div>
  );
}
