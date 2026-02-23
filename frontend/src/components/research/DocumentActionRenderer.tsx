import type { ICellRendererParams } from "ag-grid-community";
import type { DocumentListItem } from "../../types/entities";

export interface DocumentActionContext {
  onInspect: (doc: DocumentListItem) => void;
  onDownload: (doc: DocumentListItem) => void;
  onViewTranscript?: (doc: DocumentListItem) => void;
}

export function DocumentActionRenderer(params: ICellRendererParams<DocumentListItem>) {
  const doc = params.data;
  const ctx = params.context as DocumentActionContext;
  if (!doc) return null;

  // Dataset-sourced transcript: "View Transcript" button
  if (doc.doc_type === "transcript" && doc.metadata?.source === "dataset") {
    return (
      <div className="doc-actions">
        <button
          className="doc-actions__btn doc-actions__btn--primary"
          onClick={() => ctx.onViewTranscript?.(doc)}
        >
          View Transcript
        </button>
      </div>
    );
  }

  // SEC filing: "View on EDGAR" link
  if (doc.doc_type === "sec_filing" && doc.metadata?.filing_url) {
    return (
      <div className="doc-actions">
        <a
          className="doc-actions__btn doc-actions__btn--primary"
          href={doc.metadata.filing_url}
          target="_blank"
          rel="noopener noreferrer"
        >
          View on EDGAR
        </a>
      </div>
    );
  }

  // Default: View + Download
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
