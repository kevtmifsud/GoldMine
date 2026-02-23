import { useCallback, useEffect, useMemo, useState } from "react";
import type { ColDef } from "ag-grid-community";
import * as docsApi from "../../config/documentsApi";
import type { DocumentListItem } from "../../types/entities";
import { AppGrid } from "../ag-grid/AppGrid";
import { SetFilter } from "../ag-grid/SetFilter";
import { dateFilterParams } from "../ag-grid/filters";
import { DocTypeBadgeRenderer } from "./DocTypeBadgeRenderer";
import { EntityLinksRenderer } from "./EntityLinksRenderer";
import { DocumentActionRenderer } from "./DocumentActionRenderer";
import type { DocumentActionContext } from "./DocumentActionRenderer";
import { DocumentInspectorDialog } from "./DocumentInspectorDialog";
import "../../styles/research.css";

interface ResearchDocumentsGridProps {
  entityType: string;
  entityId: string;
  title: string;
  docTypeFilter?: string[];
  excludeDocTypes?: string[];
  onUploadClick?: () => void;
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

  const columnDefs = useMemo<ColDef<DocumentListItem>[]>(
    () => [
      {
        headerName: "Title",
        field: "title",
        flex: 1,
        minWidth: 200,
        sortable: true,
        filter: "agTextColumnFilter",
      },
      {
        headerName: "Type",
        field: "doc_type",
        width: 130,
        sortable: true,
        filter: SetFilter,
        cellRenderer: DocTypeBadgeRenderer,
      },
      {
        headerName: "Date",
        field: "date",
        width: 120,
        sortable: true,
        filter: "agDateColumnFilter",
        filterParams: dateFilterParams,
        valueFormatter: (params) => {
          if (!params.value) return "\u2014";
          return params.value;
        },
      },
      {
        headerName: "Entities",
        field: "entities",
        width: 160,
        sortable: false,
        filter: false,
        floatingFilter: false,
        cellRenderer: EntityLinksRenderer,
      },
      {
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
    }),
    [handleDownload]
  );

  return (
    <div className="research-grid">
      <div className="research-grid__header">
        <h3 className="research-grid__title">
          {title}
          <span className="research-grid__count">({filteredDocs.length})</span>
        </h3>
        {onUploadClick && (
          <button
            className="research-grid__upload-btn"
            onClick={onUploadClick}
          >
            Upload Document
          </button>
        )}
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
            getRowId={(params) => params.data.file_id}
          />
        </div>
      )}

      {inspectedDoc && (
        <DocumentInspectorDialog
          document={inspectedDoc}
          onClose={() => setInspectedDoc(null)}
        />
      )}
    </div>
  );
}

// Re-export for parent to call refetch after upload
export type { ResearchDocumentsGridProps };
