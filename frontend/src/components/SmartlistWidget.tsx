import { useEffect, useState, useCallback, useRef, useMemo, forwardRef, useImperativeHandle } from "react";
import type { GridApi, GridReadyEvent, SortChangedEvent } from "ag-grid-community";
import api from "../config/api";
import type { WidgetConfig, PaginatedResponse, WidgetStateOverride } from "../types/entities";
import { buildColumnDefs } from "./ag-grid/columnDefBuilder";
import { AppGrid } from "./ag-grid/AppGrid";
import type { ContextMenuConfig } from "./ag-grid/AppGrid";
import "../styles/smartlist.css";

const COLUMN_STORAGE_PREFIX = "goldmine:grid-columns:smartlist-";

function loadSavedColumns(widgetId: string): string[] | null {
  try {
    const raw = localStorage.getItem(COLUMN_STORAGE_PREFIX + widgetId);
    if (raw) return JSON.parse(raw) as string[];
  } catch {
    // ignore
  }
  return null;
}

function persistColumns(widgetId: string, columns: string[]): void {
  try {
    localStorage.setItem(COLUMN_STORAGE_PREFIX + widgetId, JSON.stringify(columns));
  } catch {
    // ignore
  }
}

function setsEqual(a: Set<string>, b: Set<string>): boolean {
  if (a.size !== b.size) return false;
  for (const v of a) {
    if (!b.has(v)) return false;
  }
  return true;
}

interface SmartlistWidgetProps {
  config: WidgetConfig;
}

export interface SmartlistWidgetHandle {
  getState: () => WidgetStateOverride;
}

export const SmartlistWidget = forwardRef<SmartlistWidgetHandle, SmartlistWidgetProps>(
  function SmartlistWidget({ config }, ref) {
  const [data, setData] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<string | null>(config.initial_sort_by ?? null);
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">(
    (config.initial_sort_order as "asc" | "desc") ?? "asc"
  );

  // Server-side filters — initialize from overrides if present
  const [serverFilters, setServerFilters] = useState<Record<string, string>>(
    () => (config.initial_filters && Object.keys(config.initial_filters).length > 0
      ? { ...config.initial_filters }
      : {})
  );

  // Client-side quick filter
  const [clientFilterText, setClientFilterText] = useState("");

  // Column visibility — saved state is what's persisted in localStorage
  // (or config defaults if nothing saved). Working state is what the user sees.
  const [savedVisibleColumns, setSavedVisibleColumns] = useState<Set<string>>(() => {
    const saved = loadSavedColumns(config.widget_id);
    if (saved && saved.length > 0) return new Set(saved);
    return new Set(config.columns.filter((c) => c.visible !== false).map((c) => c.key));
  });
  const [visibleColumns, setVisibleColumns] = useState<Set<string>>(
    () => new Set(savedVisibleColumns)
  );
  const [showColumnPicker, setShowColumnPicker] = useState(false);
  const columnPickerRef = useRef<HTMLDivElement>(null);
  const gridApiRef = useRef<GridApi | null>(null);

  // Expose state to parent via ref
  useImperativeHandle(ref, () => ({
    getState(): WidgetStateOverride {
      return {
        widget_id: config.widget_id,
        server_filters: { ...serverFilters },
        sort_by: sortBy,
        sort_order: sortOrder,
        visible_columns: Array.from(visibleColumns),
        page_size: null,
        column_filters: gridApiRef.current?.getFilterModel() ?? null,
      };
    },
  }));

  const fetchData = useCallback(
    async (filters: Record<string, string>) => {
      setLoading(true);
      setError(null);
      try {
        const baseParams: Record<string, string | number> = {
          page: 1,
          page_size: config.default_page_size ?? 200,
        };
        // Add server-side filters as query params
        for (const [k, v] of Object.entries(filters)) {
          if (v) baseParams[k] = v;
        }
        const firstResp = await api.get<PaginatedResponse>(config.endpoint, {
          params: baseParams,
        });
        let allRows = firstResp.data.data;

        if (firstResp.data.total_pages > 1) {
          const remaining = Array.from(
            { length: firstResp.data.total_pages - 1 },
            (_, i) => api.get<PaginatedResponse>(config.endpoint, {
              params: { ...baseParams, page: i + 2 },
            })
          );
          const responses = await Promise.all(remaining);
          for (const resp of responses) {
            allRows = allRows.concat(resp.data.data);
          }
        }

        setData(allRows);
      } catch (err) {
        console.error("[SmartlistWidget] Data fetch error:", config.endpoint, err);
        setError("Failed to load data");
      } finally {
        setLoading(false);
      }
    },
    [config.endpoint]
  );

  useEffect(() => {
    fetchData(serverFilters);
  }, [fetchData, serverFilters]);

  // Click-outside handler for column picker
  useEffect(() => {
    if (!showColumnPicker) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (columnPickerRef.current && !columnPickerRef.current.contains(e.target as Node)) {
        setShowColumnPicker(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showColumnPicker]);

  const handleSortChanged = useCallback((event: SortChangedEvent) => {
    const colState = event.api.getColumnState();
    const sorted = colState.find((c) => c.sort);
    if (sorted) {
      setSortBy(sorted.colId);
      setSortOrder(sorted.sort as "asc" | "desc");
    } else {
      setSortBy(null);
      setSortOrder("asc");
    }
  }, []);

  const handleServerFilterChange = (field: string, value: string) => {
    setServerFilters((prev) => ({ ...prev, [field]: value }));
  };

  const handleToggleColumn = (key: string) => {
    setVisibleColumns((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        if (next.size > 1) next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  // Client-side filtered data
  const displayData = useMemo(() => {
    if (!clientFilterText || config.client_filterable_columns.length === 0) return data;
    const lower = clientFilterText.toLowerCase();
    return data.filter((row) =>
      config.client_filterable_columns.some((col) =>
        String(row[col] ?? "").toLowerCase().includes(lower)
      )
    );
  }, [data, clientFilterText, config.client_filterable_columns]);

  const columnDefs = useMemo(
    () => buildColumnDefs(config.columns, visibleColumns),
    [config.columns, visibleColumns]
  );

  const columnsDirty = useMemo(
    () => !setsEqual(visibleColumns, savedVisibleColumns),
    [visibleColumns, savedVisibleColumns]
  );

  const saveColumns = useCallback(() => {
    persistColumns(config.widget_id, Array.from(visibleColumns));
    setSavedVisibleColumns(new Set(visibleColumns));
  }, [config.widget_id, visibleColumns]);

  const discardColumns = useCallback(() => {
    setVisibleColumns(new Set(savedVisibleColumns));
  }, [savedVisibleColumns]);

  const contextMenuConfig = useMemo<ContextMenuConfig>(() => ({
    hiddenColumns: config.columns
      .filter((c) => !visibleColumns.has(c.key))
      .map((c) => ({ field: c.key, headerName: c.label })),
    onAddColumn: (field: string) => handleToggleColumn(field),
    onRemoveColumn: (field: string) => handleToggleColumn(field),
    visibleCount: visibleColumns.size,
    isDirty: columnsDirty,
    onSave: saveColumns,
    onDiscard: discardColumns,
  }), [config.columns, visibleColumns, columnsDirty, saveColumns, discardColumns]); // eslint-disable-line react-hooks/exhaustive-deps

  const initialState = useMemo(() => ({
    sort: {
      sortModel: config.initial_sort_by
        ? [{ colId: config.initial_sort_by, sort: (config.initial_sort_order ?? "asc") as "asc" | "desc" }]
        : [],
    },
    filter: {
      filterModel: config.initial_column_filters ?? undefined,
    },
  }), [config.initial_sort_by, config.initial_sort_order, config.initial_column_filters]);

  const handleGridReady = useCallback((event: GridReadyEvent) => {
    gridApiRef.current = event.api;
  }, []);

  const hasFilters = config.filter_definitions.length > 0;
  const hasQuickFilter = config.client_filterable_columns.length > 0;
  const hasColumnToggle = config.columns.length > 0;

  return (
    <div className="smartlist">
      <div className="smartlist__header">
        <h3 className="smartlist__title">
          {config.title}
        </h3>
        {hasColumnToggle && (
          <div className="smartlist__column-toggle" ref={columnPickerRef}>
            <button
              className="smartlist__column-toggle-btn"
              onClick={() => setShowColumnPicker((p) => !p)}
            >
              Columns
            </button>
            {showColumnPicker && (
              <div className="smartlist__column-picker">
                {config.columns.map((col) => (
                  <label key={col.key} className="smartlist__column-picker-item">
                    <input
                      type="checkbox"
                      checked={visibleColumns.has(col.key)}
                      onChange={() => handleToggleColumn(col.key)}
                      disabled={visibleColumns.has(col.key) && visibleColumns.size === 1}
                    />
                    {col.label}
                  </label>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
      {(hasFilters || hasQuickFilter) && (
        <div className="smartlist__filters">
          {config.filter_definitions.map((fd) => (
            <select
              key={fd.field}
              className="smartlist__filter-select"
              value={serverFilters[fd.field] || ""}
              onChange={(e) => handleServerFilterChange(fd.field, e.target.value)}
            >
              <option value="">All {fd.label}</option>
              {fd.options.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          ))}
          {hasQuickFilter && (
            <input
              type="text"
              className="smartlist__quick-filter"
              placeholder="Quick filter..."
              value={clientFilterText}
              onChange={(e) => setClientFilterText(e.target.value)}
            />
          )}
        </div>
      )}
      {loading && data.length === 0 && (
        <div className="smartlist__loading">
          <div className="spinner" />
        </div>
      )}
      {error && (
        <div className="smartlist__error">
          <p>{error}</p>
          <button onClick={() => fetchData(serverFilters)}>
            Retry
          </button>
        </div>
      )}
      {!error && !loading && data.length === 0 && (
        <div className="smartlist__empty">No records found</div>
      )}
      {!error && data.length > 0 && (
          <div className="smartlist__grid" style={{ height: 600 }}>
            <AppGrid
              loading={loading}
              rowData={displayData}
              columnDefs={columnDefs}
              initialState={initialState}
              onGridReady={handleGridReady}
              onSortChanged={handleSortChanged}
              suppressPaginationPanel={true}
              contextMenu={contextMenuConfig}
              viewKey={`smartlist-${config.widget_id}`}
            />
          </div>
      )}
    </div>
  );
  }
);
