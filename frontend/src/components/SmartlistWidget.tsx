import { useEffect, useState, useCallback, useRef, useMemo, forwardRef, useImperativeHandle } from "react";
import { AgGridReact } from "ag-grid-react";
import type { SortChangedEvent } from "ag-grid-community";
import api from "../config/api";
import type { WidgetConfig, PaginatedResponse, WidgetStateOverride } from "../types/entities";
import { buildColumnDefs } from "./ag-grid/columnDefBuilder";
import { gridTheme } from "./ag-grid/theme";
import "../styles/smartlist.css";

interface SmartlistWidgetProps {
  config: WidgetConfig;
  onStateChange?: () => void;
}

export interface SmartlistWidgetHandle {
  getState: () => WidgetStateOverride;
}

export const SmartlistWidget = forwardRef<SmartlistWidgetHandle, SmartlistWidgetProps>(
  function SmartlistWidget({ config, onStateChange }, ref) {
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

  // Column visibility
  const [visibleColumns, setVisibleColumns] = useState<Set<string>>(() =>
    new Set(config.columns.filter((c) => c.visible !== false).map((c) => c.key))
  );
  const [showColumnPicker, setShowColumnPicker] = useState(false);
  const columnPickerRef = useRef<HTMLDivElement>(null);
  const mountedRef = useRef(false);

  // Notify parent when user changes widget state
  useEffect(() => {
    if (!mountedRef.current) {
      mountedRef.current = true;
      return;
    }
    onStateChange?.();
  }, [serverFilters, sortBy, sortOrder, visibleColumns]); // eslint-disable-line react-hooks/exhaustive-deps

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
      };
    },
  }));

  const fetchData = useCallback(
    async (filters: Record<string, string>) => {
      setLoading(true);
      setError(null);
      try {
        const params: Record<string, string | number> = {
          page: 1,
          page_size: 200,
        };
        // Add server-side filters as query params
        for (const [k, v] of Object.entries(filters)) {
          if (v) params[k] = v;
        }
        const resp = await api.get<PaginatedResponse>(config.endpoint, {
          params,
        });
        setData(resp.data.data);
      } catch {
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

  const initialState = useMemo(() => ({
    sort: {
      sortModel: config.initial_sort_by
        ? [{ colId: config.initial_sort_by, sort: (config.initial_sort_order ?? "asc") as "asc" | "desc" }]
        : [],
    },
  }), [config.initial_sort_by, config.initial_sort_order]);

  const hasFilters = config.filter_definitions.length > 0;
  const hasQuickFilter = config.client_filterable_columns.length > 0;
  const hasColumnToggle = config.columns.length > 0;

  return (
    <div className="smartlist">
      <div className="smartlist__header">
        <h3 className="smartlist__title">
          {config.title}
          {config.has_overrides && (
            <span className="smartlist__override-badge">modified</span>
          )}
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
            <AgGridReact
              theme={gridTheme}
              loading={loading}
              rowData={displayData}
              columnDefs={columnDefs}
              initialState={initialState}
              autoSizeStrategy={{ type: "fitCellContents", skipHeader: true }}
              defaultColDef={{ wrapHeaderText: true, autoHeaderHeight: true, minWidth: 100 }}
              onSortChanged={handleSortChanged}
              suppressPaginationPanel={true}
              suppressMovableColumns={false}
            />
          </div>
      )}
    </div>
  );
  }
);
