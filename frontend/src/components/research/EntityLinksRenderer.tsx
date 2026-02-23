import { Link } from "react-router-dom";
import type { ICellRendererParams } from "ag-grid-community";
import type { DocumentListItem, EntityAssociation } from "../../types/entities";

export function EntityLinksRenderer(params: ICellRendererParams<DocumentListItem>) {
  const entities = params.data?.entities as EntityAssociation[] | undefined;
  if (!entities || entities.length === 0) return <span>&mdash;</span>;

  return (
    <span className="entity-links">
      {entities.map((e, i) => (
        <span key={`${e.entity_type}-${e.entity_id}`}>
          {i > 0 && ", "}
          <Link
            className="entity-links__link"
            to={`/entity/${e.entity_type}/${e.entity_id}`}
          >
            {e.entity_id}
          </Link>
        </span>
      ))}
    </span>
  );
}
