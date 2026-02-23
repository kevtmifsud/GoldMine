import { useRef } from "react";
import { AgGridReact } from "ag-grid-react";
import type { AgGridReactProps } from "ag-grid-react";
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
 */
export function AppGrid<T = unknown>(props: AgGridReactProps<T>) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const {
    defaultColDef: userDefaultColDef,
    onFirstDataRendered: userOnFirstDataRendered,
    ...rest
  } = props;

  return (
    <div ref={wrapperRef} style={{ height: "100%" }}>
      <AgGridReact<T>
        theme={gridTheme}
        defaultColDef={{
          wrapHeaderText: true,
          autoHeaderHeight: true,
          minWidth: 100,
          filter: "agTextColumnFilter",
          floatingFilter: true,
          ...userDefaultColDef,
        }}
        onFirstDataRendered={(event) => {
          event.api.autoSizeAllColumns(true);
          const totalWidth = event.api
            .getAllDisplayedColumns()
            .reduce((w, col) => w + col.getActualWidth(), 0);
          const gridWidth = wrapperRef.current?.clientWidth ?? 0;
          if (totalWidth < gridWidth) {
            event.api.sizeColumnsToFit();
          }
          userOnFirstDataRendered?.(event);
        }}
        suppressMovableColumns={false}
        {...rest}
      />
    </div>
  );
}
