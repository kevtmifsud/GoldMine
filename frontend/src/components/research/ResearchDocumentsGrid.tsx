import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ColDef, GridApi } from "ag-grid-community";
import * as docsApi from "../../config/documentsApi";
import type { DocumentListItem } from "../../types/entities";
import { AppGrid } from "../ag-grid/AppGrid";
import { SetFilter } from "../ag-grid/SetFilter";
import { dateFilterParams } from "../ag-grid/filters";
import {
  saveGridView,
  restoreGridView,
  clearGridView,
  hasGridView,
} from "../ag-grid/gridViewPersistence";
import { DocTypeBadgeRenderer } from "./DocTypeBadgeRenderer";
import { EntityLinksRenderer } from "./EntityLinksRenderer";
import { DocumentActionRenderer } from "./DocumentActionRenderer";
import type { DocumentActionContext } from "./DocumentActionRenderer";
import { FormTypeBadgeRenderer } from "./SecFilingsGrid";
import { DocumentInspectorDialog } from "./DocumentInspectorDialog";
import { TranscriptViewerDialog } from "./TranscriptViewerDialog";
import "../../styles/research.css";

const VIEW_KEY = "research-documents";

interface ResearchDocumentsGridProps {
  entityType: string;
  entityId: string;
  title: string;
  docTypeFilter?: string[];
  excludeDocTypes?: string[];
  onUploadClick?: () => void;
}

interface TranscriptViewerState {
  symbol: string;
  year: number;
  quarter: number;
}

export function ResearchDocumentsGrid({
  entityType,
  entityId,
  title,
  docTypeFilter,
  excludeDocTypes,
  onUploadClick,
}: ResearchDocumentsGridProps) {
  const [allDocs, setAllDocs] = useState<DocumentListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [inspectedDoc, setInspectedDoc] = useState<DocumentListItem | null>(null);
  const [viewingTranscript, setViewingTranscript] = useState<TranscriptViewerState | null>(null);
  const [dirty, setDirty] = useState(false);
  const [savedViewExists, setSavedViewExists] = useState(() => hasGridView(VIEW_KEY));
  const gridApiRef = useRef<GridApi<DocumentListItem> | null>(null);
  const restoringRef = useRef(false);

  const fetchDocs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const docs = await docsApi.listDocuments(entityType, entityId);
      setAllDocs(docs);
    } catch {
      setError("Failed to load documents");
    } finally {
      setLoading(false);
    }
  }, [entityType, entityId]);

  useEffect(() => {
    fetchDocs();
  }, [fetchDocs]);

  // Client-side filtering
  const filteredDocs = useMemo(() => {
    let docs = allDocs;
    if (docTypeFilter && docTypeFilter.length > 0) {
      docs = docs.filter((d) => docTypeFilter.includes(d.doc_type));
    }
    if (excludeDocTypes && excludeDocTypes.length > 0) {
      docs = docs.filter((d) => !excludeDocTypes.includes(d.doc_type));
    }
    return docs;
  }, [allDocs, docTypeFilter, excludeDocTypes]);

  const handleDownload = useCallback((doc: DocumentListItem) => {
    const a = document.createElement("a");
    a.href = `/api/files/${doc.file_id}`;
    a.download = doc.filename;
    a.click();
  }, []);

  const handleViewTranscript = useCallback((doc: DocumentListItem) => {
    if (doc.metadata) {
      const symbol = doc.metadata.symbol || entityId;
      const year = parseInt(doc.metadata.fiscal_year, 10);
      const quarter = parseInt(doc.metadata.fiscal_quarter, 10);
      if (symbol && !isNaN(year) && !isNaN(quarter)) {
        setViewingTranscript({ symbol, year, quarter });
      }
    }
  }, [entityId]);

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
    (params: { data: DocumentListItem }) => params.data.file_id,
    []
  );

  const onGridReady = useCallback(
    (e: { api: import("ag-grid-community").GridApi<DocumentListItem> }) => {
      gridApiRef.current = e.api;
    },
    []
  );

  const onFirstDataRendered = useCallback(
    (e: { api: import("ag-grid-community").GridApi<DocumentListItem> }) => {
      restoringRef.current = true;
      restoreGridView(VIEW_KEY, e.api);
      restoringRef.current = false;
    },
    []
  );

  const columnDefs = useMemo<ColDef<DocumentListItem>[]>(
    () => [
      {
        colId: "title",
        headerName: "Title",
        field: "title",
        flex: 1,
        minWidth: 200,
        sortable: true,
        filter: "agTextColumnFilter",
      },
      {
        colId: "doc_type",
        headerName: "Type",
        field: "doc_type",
        width: 130,
        sortable: true,
        filter: SetFilter,
        cellRenderer: DocTypeBadgeRenderer,
      },
      {
        colId: "date",
        headerName: "Date",
        field: "date",
        width: 120,
        sortable: true,
        sort: "desc",
        filter: "agDateColumnFilter",
        filterParams: dateFilterParams,
        valueFormatter: (params) => {
          if (!params.value) return "\u2014";
          return params.value;
        },
      },
      {
        colId: "form_type",
        headerName: "Form Type",
        width: 120,
        sortable: true,
        filter: SetFilter,
        valueGetter: (params) => params.data?.metadata?.form_type ?? null,
        cellRenderer: FormTypeBadgeRenderer,
      },
      {
        colId: "report_year",
        headerName: "Report Year",
        width: 120,
        sortable: true,
        filter: "agNumberColumnFilter",
        valueGetter: (params) => {
          const v = params.data?.metadata?.fiscal_year;
          return v ? Number(v) : null;
        },
        valueFormatter: (params) => params.value ?? "\u2014",
      },
      {
        colId: "report_qtr",
        headerName: "Report Qtr",
        width: 115,
        sortable: true,
        filter: SetFilter,
        valueGetter: (params) => {
          const v = params.data?.metadata?.fiscal_quarter;
          return v ? `Q${v}` : null;
        },
        valueFormatter: (params) => params.value ?? "\u2014",
      },
      {
        colId: "entities",
        headerName: "Entities",
        field: "entities",
        width: 160,
        sortable: false,
        filter: false,
        floatingFilter: false,
        cellRenderer: EntityLinksRenderer,
      },
      {
        colId: "actions",
        headerName: "Actions",
        width: 150,
        sortable: false,
        filter: false,
        floatingFilter: false,
        suppressHeaderMenuButton: true,
        cellRenderer: DocumentActionRenderer,
      },
    ],
    []
  );

  const context = useMemo<DocumentActionContext>(
    () => ({
      onInspect: (doc: DocumentListItem) => setInspectedDoc(doc),
      onDownload: handleDownload,
      onViewTranscript: handleViewTranscript,
    }),
    [handleDownload, handleViewTranscript]
  );

  return (
    <div className="research-grid">
      <div className="research-grid__header">
        <h3 className="research-grid__title">
          {title}
          <span className="research-grid__count">({filteredDocs.length})</span>
        </h3>
        <div className="research-grid__header-actions">
          {onUploadClick && (
            <button
              className="research-grid__upload-btn"
              onClick={onUploadClick}
            >
              Upload Document
            </button>
          )}
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
          {filteredDocs.length > 0 && (
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
        <div className="research-grid__loading">Loading documents...</div>
      )}
      {error && <div className="research-grid__error">{error}</div>}
      {!loading && !error && filteredDocs.length === 0 && (
        <div className="research-grid__empty">No documents found.</div>
      )}

      {!loading && !error && filteredDocs.length > 0 && (
        <div className="research-grid__body">
          <AppGrid<DocumentListItem>
            rowData={filteredDocs}
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

      {inspectedDoc && (
        <DocumentInspectorDialog
          document={inspectedDoc}
          onClose={() => setInspectedDoc(null)}
        />
      )}

      {viewingTranscript && (
        <TranscriptViewerDialog
          symbol={viewingTranscript.symbol}
          year={viewingTranscript.year}
          quarter={viewingTranscript.quarter}
          onClose={() => setViewingTranscript(null)}
        />
      )}
    </div>
  );
}

// Re-export for parent to call refetch after upload
export type { ResearchDocumentsGridProps };
