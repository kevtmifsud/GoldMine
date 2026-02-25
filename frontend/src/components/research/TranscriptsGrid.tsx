import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ColDef, GridApi, ICellRendererParams } from "ag-grid-community";
import api from "../../config/api";
import { AppGrid } from "../ag-grid/AppGrid";
import { SetFilter } from "../ag-grid/SetFilter";
import { dateFilterParams } from "../ag-grid/filters";
import {
  saveGridView,
  restoreGridView,
  clearGridView,
  hasGridView,
} from "../ag-grid/gridViewPersistence";
import { TranscriptViewerDialog } from "./TranscriptViewerDialog";
import "../../styles/research.css";

const VIEW_KEY = "research-transcripts";

interface TranscriptRecord {
  symbol: string;
  fiscal_year: string;
  fiscal_quarter: string;
  report_date: string;
  transcripts_id: string;
}

interface TranscriptsGridProps {
  symbol: string;
}

interface ViewingTranscript {
  year: number;
  quarter: number;
}

function ViewButtonRenderer(params: ICellRendererParams<TranscriptRecord>) {
  const ctx = params.context as {
    onView: (year: number, quarter: number) => void;
  };
  const data = params.data;
  if (!data) return null;

  return (
    <button
      className="doc-actions__btn doc-actions__btn--primary"
      onClick={() =>
        ctx.onView(Number(data.fiscal_year), Number(data.fiscal_quarter))
      }
    >
      View Transcript
    </button>
  );
}

export function TranscriptsGrid({
  symbol,
}: TranscriptsGridProps) {
  const [transcripts, setTranscripts] = useState<TranscriptRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [viewing, setViewing] = useState<ViewingTranscript | null>(null);
  const [dirty, setDirty] = useState(false);
  const [savedViewExists, setSavedViewExists] = useState(() => hasGridView(VIEW_KEY));
  const gridApiRef = useRef<GridApi<TranscriptRecord> | null>(null);
  const restoringRef = useRef(false);

  const fetchTranscripts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await api.get("/api/data/transcripts_list", {
        params: {
          symbol,
          page_size: 1000,
          sort_by: "fiscal_year",
          sort_order: "desc",
        },
      });
      setTranscripts(resp.data.data ?? []);
    } catch {
      setError("Failed to load transcripts");
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  useEffect(() => {
    fetchTranscripts();
  }, [fetchTranscripts]);

  const handleView = useCallback((year: number, quarter: number) => {
    setViewing({ year, quarter });
  }, []);

  const markDirty = useCallback(() => {
    if (!restoringRef.current) setDirty(true);
  }, []);

  const handleSaveView = useCallback(() => {
    if (gridApiRef.current) {
      saveGridView(VIEW_KEY, gridApiRef.current);
      setSavedViewExists(true);
      setDirty(false);
    }
  }, []);

  const handleResetView = useCallback(() => {
    clearGridView(VIEW_KEY);
    gridApiRef.current?.resetColumnState();
    gridApiRef.current?.setFilterModel(null);
    setSavedViewExists(false);
    setDirty(false);
  }, []);

  const getRowId = useCallback(
    (params: { data: TranscriptRecord }) => params.data.transcripts_id,
    []
  );

  const onGridReady = useCallback(
    (e: { api: import("ag-grid-community").GridApi<TranscriptRecord> }) => {
      gridApiRef.current = e.api;
    },
    []
  );

  const onFirstDataRendered = useCallback(
    (e: { api: import("ag-grid-community").GridApi<TranscriptRecord> }) => {
      restoringRef.current = true;
      restoreGridView(VIEW_KEY, e.api);
      restoringRef.current = false;
    },
    []
  );

  const columnDefs = useMemo<ColDef<TranscriptRecord>[]>(
    () => [
      {
        colId: "fiscal_year",
        headerName: "Year",
        field: "fiscal_year",
        width: 100,
        sortable: true,
        sort: "desc",
        filter: "agNumberColumnFilter",
      },
      {
        colId: "fiscal_quarter",
        headerName: "Quarter",
        field: "fiscal_quarter",
        width: 100,
        sortable: true,
        filter: SetFilter,
        valueFormatter: (params) =>
          params.value ? `Q${params.value}` : "\u2014",
      },
      {
        colId: "report_date",
        headerName: "Report Date",
        field: "report_date",
        width: 130,
        sortable: true,
        filter: "agDateColumnFilter",
        filterParams: dateFilterParams,
        valueFormatter: (params) => params.value || "\u2014",
      },
      {
        colId: "actions",
        headerName: "",
        width: 150,
        sortable: false,
        filter: false,
        floatingFilter: false,
        suppressHeaderMenuButton: true,
        cellRenderer: ViewButtonRenderer,
      },
    ],
    []
  );

  const context = useMemo(() => ({ onView: handleView }), [handleView]);

  return (
    <div className="research-grid">
      <div className="research-grid__header">
        <h3 className="research-grid__title">
          Transcripts
          <span className="research-grid__count">({transcripts.length})</span>
        </h3>
        <div className="research-grid__header-actions">
          <button
            className={dirty ? "research-grid__save-view-btn research-grid__save-view-btn--dirty" : "research-grid__save-view-btn"}
            onClick={handleSaveView}
          >
            Save Default View
          </button>
          {savedViewExists && (
            <button
              className="research-grid__download-btn"
              onClick={handleResetView}
            >
              Reset View
            </button>
          )}
          {transcripts.length > 0 && (
            <button
              className="research-grid__download-btn"
              onClick={() => gridApiRef.current?.exportDataAsCsv()}
            >
              Download CSV
            </button>
          )}
        </div>
      </div>

      {loading && (
        <div className="research-grid__loading">
          Loading transcripts...
        </div>
      )}
      {error && <div className="research-grid__error">{error}</div>}
      {!loading && !error && transcripts.length === 0 && (
        <div className="research-grid__empty">
          No transcripts found.
        </div>
      )}

      {!loading && !error && transcripts.length > 0 && (
        <div className="research-grid__body">
          <AppGrid<TranscriptRecord>
            rowData={transcripts}
            columnDefs={columnDefs}
            context={context}
            domLayout="autoHeight"
            getRowId={getRowId}
            onGridReady={onGridReady}
            onFirstDataRendered={onFirstDataRendered}
            onSortChanged={markDirty}
            onColumnMoved={markDirty}
            onColumnResized={markDirty}
            onFilterChanged={markDirty}
          />
        </div>
      )}

      {viewing && (
        <TranscriptViewerDialog
          symbol={symbol}
          year={viewing.year}
          quarter={viewing.quarter}
          onClose={() => setViewing(null)}
        />
      )}
    </div>
  );
}
