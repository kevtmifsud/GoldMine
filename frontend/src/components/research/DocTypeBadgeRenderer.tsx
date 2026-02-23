import type { ICellRendererParams } from "ag-grid-community";
import type { DocumentListItem } from "../../types/entities";

const KNOWN_TYPES = new Set(["audio", "transcript", "report", "data_export", "notes", "sec_filing"]);

export function DocTypeBadgeRenderer(params: ICellRendererParams<DocumentListItem>) {
  const docType = params.value as string;
  if (!docType) return null;

  const modifier = KNOWN_TYPES.has(docType) ? docType : "other";

  return (
    <span className={`doc-type-badge doc-type-badge--${modifier}`}>
      {docType.replace("_", " ")}
    </span>
  );
}
