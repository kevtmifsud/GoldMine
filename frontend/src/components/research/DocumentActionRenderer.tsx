import type { ICellRendererParams } from "ag-grid-community";
import type { DocumentListItem } from "../../types/entities";

export interface DocumentActionContext {
  onInspect: (doc: DocumentListItem) => void;
  onDownload: (doc: DocumentListItem) => void;
}

export function DocumentActionRenderer(params: ICellRendererParams<DocumentListItem>) {
  const doc = params.data;
  const ctx = params.context as DocumentActionContext;
  if (!doc) return null;

  return (
    <div className="doc-actions">
      <button
        className="doc-actions__btn doc-actions__btn--primary"
        onClick={() => ctx.onInspect(doc)}
      >
        View
      </button>
      <button
        className="doc-actions__btn"
        onClick={() => ctx.onDownload(doc)}
      >
        Download
      </button>
    </div>
  );
}
