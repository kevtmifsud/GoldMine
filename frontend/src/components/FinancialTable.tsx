import { useState, useEffect, useRef, useCallback } from "react";
import api from "../config/api";
import { formatDateLabel, getFiscalQuarter, downloadFinancialsExcel } from "../config/financialsApi";
import type { FinancialStatementResponse, FinancialLineItem } from "../types/financials";
import "../styles/fundamentals.css";

interface FinancialTableProps {
  ticker: string;
  statementType: "income-statement" | "balance-sheet" | "cash-flow";
}

function trimDecimalZeros(fixed: string): string {
  if (!fixed.includes(".")) return fixed;
  return fixed.replace(/0+$/, "").replace(/\.$/, "");
}

function formatValue(value: number | null, formatType: string): { text: string; negative: boolean } {
  if (value === null || value === undefined) {
    return { text: "\u2014", negative: false };
  }

  if (formatType === "percent") {
    const neg = value < 0;
    const abs = Math.abs(value);
    const text = neg ? `(${abs.toFixed(1)}%)` : `${abs.toFixed(1)}%`;
    return { text, negative: neg };
  }

  if (formatType === "per_share") {
    const neg = value < 0;
    const abs = Math.abs(value);
    const text = neg ? `($${abs.toFixed(2)})` : `$${abs.toFixed(2)}`;
    return { text, negative: neg };
  }

  const neg = value < 0;
  const abs = Math.abs(value);
  let formatted: string;
  const prefix = formatType === "currency" ? "$" : "";

  if (abs >= 1e12) {
    formatted = `${prefix}${trimDecimalZeros((abs / 1e12).toFixed(2))}T`;
  } else if (abs >= 1e9) {
    formatted = `${prefix}${trimDecimalZeros((abs / 1e9).toFixed(2))}B`;
  } else if (abs >= 1e6) {
    formatted = `${prefix}${trimDecimalZeros((abs / 1e6).toFixed(2))}M`;
  } else if (abs >= 1e3) {
    formatted = `${prefix}${trimDecimalZeros((abs / 1e3).toFixed(2))}K`;
  } else {
    formatted = `${prefix}${trimDecimalZeros(abs.toFixed(2))}`;
  }

  if (neg) {
    formatted = `(${formatted})`;
  }
  return { text: formatted, negative: neg };
}

function renderCell(item: FinancialLineItem, date: string, isFyEnd = false) {
  const val = item.values[date];
  const yoy = item.yoy[date];
  const { text, negative } = formatValue(val, item.format_type);

  return (
    <td key={date} className={isFyEnd ? "financial-table__fy-end" : ""}>
      <span className={`financial-table__value${negative ? " financial-table__value--negative" : ""}`}>
        {text}
      </span>
      {yoy !== null && yoy !== undefined && (
        <span
          className={`financial-table__yoy${
            yoy > 0
              ? " financial-table__yoy--positive"
              : yoy < 0
                ? " financial-table__yoy--negative"
                : ""
          }`}
        >
          {yoy > 0 ? "+" : ""}
          {yoy.toFixed(1)}%
        </span>
      )}
    </td>
  );
}

export function FinancialTable({ ticker, statementType }: FinancialTableProps) {
  const [period, setPeriod] = useState<"annual" | "quarterly">("annual");
  const [data, setData] = useState<FinancialStatementResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const scrollToRight = useCallback(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollLeft = el.scrollWidth;
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .get<FinancialStatementResponse>(`/api/financials/${ticker}/${statementType}`, {
        params: { period },
      })
      .then((resp) => {
        setData(resp.data);
        // Scroll to right after render to show most recent periods
        requestAnimationFrame(() => scrollToRight());
      })
      .catch(() => setError("Failed to load financial data"))
      .finally(() => setLoading(false));
  }, [ticker, statementType, period, scrollToRight]);

  const handleDownload = async () => {
    if (!data) return;
    setDownloading(true);
    try {
      await downloadFinancialsExcel(ticker);
    } catch {
      // silent fail
    } finally {
      setDownloading(false);
    }
  };

  return (
    <>
      <div className="fundamentals-toggle">
        <span className="fundamentals-toggle__label">Period</span>
        <div className="fundamentals-toggle__buttons">
          <button
            className={`fundamentals-toggle__btn${period === "annual" ? " fundamentals-toggle__btn--active" : ""}`}
            onClick={() => setPeriod("annual")}
          >
            Annual
          </button>
          <button
            className={`fundamentals-toggle__btn${period === "quarterly" ? " fundamentals-toggle__btn--active" : ""}`}
            onClick={() => setPeriod("quarterly")}
          >
            Quarterly
          </button>
        </div>
        <div className="fundamentals-toggle__spacer" />
        <button
          className="fundamentals-toggle__download"
          onClick={handleDownload}
          disabled={downloading || !data}
        >
          {downloading ? "Downloading..." : "Download Excel"}
        </button>
      </div>

      {loading && <div className="financial-table__loading"><div className="spinner" /></div>}
      {error && <div className="financial-table__error">{error}</div>}
      {!loading && !error && data && data.line_items.length === 0 && (
        <div className="financial-table__empty">No financial data available.</div>
      )}
      {!loading && !error && data && data.line_items.length > 0 && (() => {
        // Build set of Q4 dates for year-boundary styling (quarterly only)
        const q4Dates = new Set<string>();
        if (period === "quarterly") {
          for (const d of data.dates) {
            if (getFiscalQuarter(d, data.fy_end_month) === 4) {
              q4Dates.add(d);
            }
          }
        }

        return (
          <div className="financial-table-wrap" ref={scrollRef}>
            <table className="financial-table">
              <thead>
                <tr>
                  <th></th>
                  {data.dates.map((d) => (
                    <th
                      key={d}
                      className={q4Dates.has(d) ? "financial-table__fy-end" : ""}
                    >
                      {formatDateLabel(d, period, data.fy_end_month)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.line_items.map((item) => {
                  const rowClass = [
                    item.is_header ? "financial-table__row--header" : "",
                    item.indent > 0 ? "financial-table__row--detail" : "",
                  ].filter(Boolean).join(" ");

                  return (
                    <tr key={item.metric} className={rowClass}>
                      <td
                        className={
                          item.indent === 1
                            ? "financial-table__label--indent-1"
                            : item.indent === 2
                              ? "financial-table__label--indent-2"
                              : ""
                        }
                      >
                        {item.label}
                      </td>
                      {data.dates.map((d) => renderCell(item, d, q4Dates.has(d)))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        );
      })()}
    </>
  );
}
