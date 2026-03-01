import { Link } from "react-router-dom";
import type { ICellRendererParams } from "ag-grid-community";

interface EntityLinkRendererOptions {
  entityType: string;
  entityIdField?: string;
}

export function createEntityLinkRenderer({
  entityType,
  entityIdField,
}: EntityLinkRendererOptions) {
  function EntityLinkRenderer(params: ICellRendererParams) {
    const displayValue = params.value;
    if (!displayValue) return <span>{"\u2014"}</span>;

    const raw = String(displayValue);

    // If an entityIdField is specified, use that field from the row data for the link target
    if (entityIdField) {
      const entityId = params.data?.[entityIdField];
      if (!entityId) return <span>{raw}</span>;
      return (
        <Link className="smartlist__link" to={`/entity/${entityType}/${entityId}`}>
          {raw}
        </Link>
      );
    }

    // Handle semicolon-separated multi-value columns (e.g. "AAPL;MSFT;GOOG")
    if (raw.includes(";")) {
      const parts = raw.split(";").map((s) => s.trim()).filter(Boolean);
      return (
        <span>
          {parts.map((part, i) => (
            <span key={part}>
              {i > 0 && "; "}
              <Link className="smartlist__link" to={`/entity/${entityType}/${part}`}>
                {part}
              </Link>
            </span>
          ))}
        </span>
      );
    }

    // Single value
    return (
      <Link className="smartlist__link" to={`/entity/${entityType}/${raw}`}>
        {raw}
      </Link>
    );
  }

  return EntityLinkRenderer;
}

// Cache to avoid creating new renderer components on every column build
const rendererCache = new Map<string, ReturnType<typeof createEntityLinkRenderer>>();

export function getEntityRenderer(
  entityType: string,
  entityIdField?: string | null,
): ReturnType<typeof createEntityLinkRenderer> {
  const key = `${entityType}:${entityIdField ?? ""}`;
  let renderer = rendererCache.get(key);
  if (!renderer) {
    renderer = createEntityLinkRenderer({
      entityType,
      entityIdField: entityIdField ?? undefined,
    });
    rendererCache.set(key, renderer);
  }
  return renderer;
}
