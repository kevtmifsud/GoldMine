import { useEffect, useState, useCallback } from "react";
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

  const fetchData = useCallback(
    async (p: number, sb: string | null, so: string) => {
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
    fetchData(page, sortBy, sortOrder);
  }, [fetchData, page, sortBy, sortOrder]);

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

  const formatValue = (value: unknown, format: string): string => {
    if (value === null || value === undefined || value === "") return "—";
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

  return (
    <div className="smartlist">
      <h3 className="smartlist__title">{config.title}</h3>
      {loading && (
        <div className="smartlist__loading">
          <div className="spinner" />
        </div>
      )}
      {error && (
        <div className="smartlist__error">
          <p>{error}</p>
          <button onClick={() => fetchData(page, sortBy, sortOrder)}>
            Retry
          </button>
        </div>
      )}
      {!loading && !error && data.length === 0 && (
        <div className="smartlist__empty">No records found</div>
      )}
      {!loading && !error && data.length > 0 && (
        <>
          <div className="smartlist__table-wrapper">
            <table className="smartlist__table">
              <thead>
                <tr>
                  {config.columns.map((col) => (
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
                {data.map((row, idx) => (
                  <tr key={idx}>
                    {config.columns.map((col) => (
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
