import { useCallback, useEffect, useMemo, useState } from "react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import api from "../../config/api";
import { AppGrid } from "../ag-grid/AppGrid";
import { SetFilter } from "../ag-grid/SetFilter";
import { dateFilterParams } from "../ag-grid/filters";
import "../../styles/research.css";

interface SecFiling {
  symbol: string;
  cik: string;
  accession_number: string;
  company_name: string;
  form_type: string;
  form_type_description: string;
  filing_date: string;
  report_date: string;
  acceptance_date_time: string;
  filing_url: string;
}

interface SecFilingsGridProps {
  symbol: string;
}

const FORM_TYPE_COLORS: Record<string, { bg: string; fg: string }> = {
  "10-K": { bg: "#d1fae5", fg: "#065f46" },
  "10-Q": { bg: "#dbeafe", fg: "#1e40af" },
  "8-K": { bg: "#fef3c7", fg: "#92400e" },
  "SC 13G/A": { bg: "#ede9fe", fg: "#5b21b6" },
  "SC 13G": { bg: "#ede9fe", fg: "#5b21b6" },
  DEF14A: { bg: "#fce7f3", fg: "#9d174d" },
};

const DEFAULT_FORM_COLOR = { bg: "#f1f5f9", fg: "#475569" };

function FormTypeBadgeRenderer(params: ICellRendererParams<SecFiling>) {
  const formType = params.value as string;
  if (!formType) return <span>{"\u2014"}</span>;

  const color = FORM_TYPE_COLORS[formType] ?? DEFAULT_FORM_COLOR;

  return (
    <span
      className="filing-form-badge"
      style={{ backgroundColor: color.bg, color: color.fg }}
    >
      {formType}
    </span>
  );
}

function EdgarLinkRenderer(params: ICellRendererParams<SecFiling>) {
  const url = params.value as string;
  if (!url) return <span>{"\u2014"}</span>;

  return (
    <a
      className="filing-link"
      href={url}
      target="_blank"
      rel="noopener noreferrer"
    >
      View on EDGAR
    </a>
  );
}

export function SecFilingsGrid({ symbol }: SecFilingsGridProps) {
  const [filings, setFilings] = useState<SecFiling[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const fetchFilings = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await api.get("/api/data/sec_filings", {
        params: {
          symbol,
          page_size: 1000,
          sort_by: "filing_date",
          sort_order: "desc",
        },
      });
      setFilings(resp.data.data ?? []);
    } catch {
      setError("Failed to load SEC filings");
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  useEffect(() => {
    fetchFilings();
  }, [fetchFilings]);

  const columnDefs = useMemo<ColDef<SecFiling>[]>(
    () => [
      {
        headerName: "Filing Date",
        field: "filing_date",
        width: 120,
        sortable: true,
        sort: "desc",
        filter: "agDateColumnFilter",
        filterParams: dateFilterParams,
      },
      {
        headerName: "Form Type",
        field: "form_type",
        width: 120,
        sortable: true,
        filter: SetFilter,
        cellRenderer: FormTypeBadgeRenderer,
      },
      {
        headerName: "Description",
        field: "form_type_description",
        flex: 1,
        minWidth: 200,
        sortable: true,
        filter: "agTextColumnFilter",
      },
      {
        headerName: "Report Date",
        field: "report_date",
        width: 120,
        sortable: true,
        filter: "agDateColumnFilter",
        filterParams: dateFilterParams,
        valueFormatter: (params) => params.value || "\u2014",
      },
      {
        headerName: "EDGAR",
        field: "filing_url",
        width: 140,
        sortable: false,
        filter: false,
        floatingFilter: false,
        suppressHeaderMenuButton: true,
        cellRenderer: EdgarLinkRenderer,
      },
    ],
    []
  );

  return (
    <div className="research-grid">
      <div className="research-grid__header">
        <h3 className="research-grid__title">
          SEC Filings
          <span className="research-grid__count">({filings.length})</span>
        </h3>
      </div>

      {loading && (
        <div className="research-grid__loading">Loading SEC filings...</div>
      )}
      {error && <div className="research-grid__error">{error}</div>}
      {!loading && !error && filings.length === 0 && (
        <div className="research-grid__empty">No SEC filings found.</div>
      )}

      {!loading && !error && filings.length > 0 && (
        <div className="research-grid__body">
          <AppGrid<SecFiling>
            rowData={filings}
            columnDefs={columnDefs}
            domLayout="autoHeight"
            getRowId={(params) => params.data.accession_number}
          />
        </div>
      )}
    </div>
  );
}
