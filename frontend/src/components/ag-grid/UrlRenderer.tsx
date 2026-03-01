import type { ICellRendererParams } from "ag-grid-community";

const HEADER_LABELS: Record<string, string> = {
  "Filing Url": "Filing Link",
  "Web Site": "Website",
};

export function UrlRenderer(params: ICellRendererParams) {
  const value = params.value;
  if (!value) return <span>{"\u2014"}</span>;

  const url = String(value);
  const header = params.colDef?.headerName ?? "";
  const label = HEADER_LABELS[header] ?? "Link";

  return (
    <a
      href={url.startsWith("http") ? url : `https://${url}`}
      target="_blank"
      rel="noopener noreferrer"
      className="smartlist__link"
    >
      {label}
    </a>
  );
}
