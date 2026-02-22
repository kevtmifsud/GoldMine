import { Link } from "react-router-dom";
import type { ICellRendererParams } from "ag-grid-community";
import type { AnalystPack } from "../../types/entities";

export function PackNameRenderer(params: ICellRendererParams<AnalystPack>) {
  const pack = params.data;
  if (!pack) return null;
  return (
    <div>
      <Link to={`/pack/${pack.pack_id}`} className="packs-list__name-link">
        {pack.name}
      </Link>
      {pack.description && (
        <span className="packs-list__desc-hint">{pack.description}</span>
      )}
    </div>
  );
}
