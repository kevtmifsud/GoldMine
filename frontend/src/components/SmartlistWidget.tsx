import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import api from "../config/api";
import type { WidgetConfig, PaginatedResponse } from "../types/entities";
import { Pagination } from "./Pagination";
import "../styles/smartlist.css";

interface SmartlistWidgetProps {
  config: WidgetConfig;
}

export function SmartlistWidget({ config }: SmartlistWidgetProps) {
  const [data, setData] = useState<Record<string, unknown>[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalRecords, setTotalRecords] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<string | null>(null);
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");

  // Server-side filters
  const [serverFilters, setServerFilters] = useState<Record<string, string>>({});

  // Client-side quick filter
  const [clientFilterText, setClientFilterText] = useState("");

  // Column visibility
  const [visibleColumns, setVisibleColumns] = useState<Set<string>>(() =>
    new Set(config.columns.filter((c) => c.visible !== false).map((c) => c.key))
  );
  const [showColumnPicker, setShowColumnPicker] = useState(false);
  const columnPickerRef = useRef<HTMLDivElement>(null);

  const fetchData = useCallback(
    async (p: number, sb: string | null, so: string, filters: Record<string, string>) => {
      setLoading(true);
      setError(null);
      try {
        const params: Record<string, string | number> = {
          page: p,
          page_size: config.default_page_size,
        };
        if (sb) {
          params.sort_by = sb;
          params.sort_order = so;
        }
        // Add server-side filters as query params
        for (const [k, v] of Object.entries(filters)) {
          if (v) params[k] = v;
        }
        const resp = await api.get<PaginatedResponse>(config.endpoint, {
          params,
        });
        setData(resp.data.data);
        setTotalPages(resp.data.total_pages);
        setTotalRecords(resp.data.total_records);
      } catch {
        setError("Failed to load data");
      } finally {
        setLoading(false);
      }
    },
    [config.endpoint, config.default_page_size]
  );

  useEffect(() => {
    fetchData(page, sortBy, sortOrder, serverFilters);
  }, [fetchData, page, sortBy, sortOrder, serverFilters]);

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

  const handleSort = (key: string) => {
    if (sortBy === key) {
      setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(key);
      setSortOrder("asc");
    }
    setPage(1);
  };

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
  };

  const handleServerFilterChange = (field: string, value: string) => {
    setServerFilters((prev) => ({ ...prev, [field]: value }));
    setPage(1);
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

  const formatValue = (value: unknown, format: string): string => {
    if (value === null || value === undefined || value === "") return "\u2014";
    const str = String(value);
    switch (format) {
      case "currency": {
        const num = parseFloat(str);
        return isNaN(num) ? str : `$${num.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
      }
      case "percent": {
        const num = parseFloat(str);
        return isNaN(num) ? str : `${num.toFixed(2)}%`;
      }
      case "number": {
        const num = parseFloat(str);
        return isNaN(num) ? str : num.toLocaleString("en-US");
      }
      default:
        return str;
    }
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

  const activeColumns = config.columns.filter((c) => visibleColumns.has(c.key));
  const hasFilters = config.filter_definitions.length > 0;
  const hasQuickFilter = config.client_filterable_columns.length > 0;
  const hasColumnToggle = config.columns.length > 0;

  return (
    <div className="smartlist">
      <div className="smartlist__header">
        <h3 className="smartlist__title">{config.title}</h3>
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
      {loading && (
        <div className="smartlist__loading">
          <div className="spinner" />
        </div>
      )}
      {error && (
        <div className="smartlist__error">
          <p>{error}</p>
          <button onClick={() => fetchData(page, sortBy, sortOrder, serverFilters)}>
            Retry
          </button>
        </div>
      )}
      {!loading && !error && displayData.length === 0 && (
        <div className="smartlist__empty">No records found</div>
      )}
      {!loading && !error && displayData.length > 0 && (
        <>
          <div className="smartlist__table-wrapper">
            <table className="smartlist__table">
              <thead>
                <tr>
                  {activeColumns.map((col) => (
                    <th
                      key={col.key}
                      className={`smartlist__th ${col.sortable ? "smartlist__th--sortable" : ""}`}
                      onClick={() => col.sortable && handleSort(col.key)}
                    >
                      {col.label}
                      {sortBy === col.key && (
                        <span className="smartlist__sort-indicator">
                          {sortOrder === "asc" ? " \u25B2" : " \u25BC"}
                        </span>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {displayData.map((row, idx) => (
                  <tr key={idx}>
                    {activeColumns.map((col) => (
                      <td key={col.key} className="smartlist__td">
                        {formatValue(row[col.key], col.format)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            page={page}
            totalPages={totalPages}
            totalRecords={totalRecords}
            onPageChange={handlePageChange}
          />
        </>
      )}
    </div>
  );
}
