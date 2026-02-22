import type { ICellRendererParams } from "ag-grid-community";
import type { AnalystPack } from "../../types/entities";

interface PackActionContext {
  isOwner: (pack: AnalystPack) => boolean;
  onEdit: (pack: AnalystPack) => void;
  onDelete?: (pack: AnalystPack) => void;
  onSendAlert: (pack: AnalystPack) => void;
  deletingId?: string | null;
}

export function PackActionRenderer(params: ICellRendererParams<AnalystPack>) {
  const pack = params.data;
  const ctx = params.context as PackActionContext;
  if (!pack) return null;

  return (
    <div className="packs-list__td-actions">
      {ctx.isOwner(pack) && (
        <>
          <button
            className="packs-list__action-btn"
            onClick={() => ctx.onEdit(pack)}
            title="Edit"
          >
            Edit
          </button>
          {ctx.onDelete && (
            <button
              className="packs-list__action-btn packs-list__action-btn--danger"
              onClick={() => ctx.onDelete!(pack)}
              disabled={ctx.deletingId === pack.pack_id}
              title="Delete"
            >
              {ctx.deletingId === pack.pack_id ? "..." : "Delete"}
            </button>
          )}
        </>
      )}
      <button
        className="packs-list__action-btn packs-list__action-btn--send"
        onClick={() => ctx.onSendAlert(pack)}
        title="Send Alert"
      >
        Send Alert
      </button>
    </div>
  );
}
