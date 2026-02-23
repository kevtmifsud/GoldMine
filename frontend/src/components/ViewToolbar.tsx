import type { SavedView } from "../types/entities";
import "../styles/views.css";

interface ViewToolbarProps {
  entityType: string;
  entityId: string;
  activeViewId: string | null;
  activeViewName: string | null;
  views: SavedView[];
  currentUser: string;
  dirty: boolean;
  viewId: string | null;
  onViewSelect: (viewId: string | null) => void;
  onSaveView: () => void;
  onSaveNewView: () => void;
  onDeleteView: (viewId: string) => void;
}

export function ViewToolbar({
  activeViewId,
  views,
  currentUser,
  dirty,
  viewId,
  onViewSelect,
  onSaveView,
  onSaveNewView,
  onDeleteView,
}: ViewToolbarProps) {
  const activeView = activeViewId
    ? views.find((v) => v.view_id === activeViewId)
    : null;
  const isOwner = activeView?.owner === currentUser;

  return (
    <div className="view-toolbar">
      <select
        className="view-toolbar__select"
        value={viewId ?? ""}
        onChange={(e) => onViewSelect(e.target.value || null)}
      >
        <option value="">
          Default View{views.some((v) => v.is_default && v.owner === currentUser) ? " (customized)" : ""}
        </option>
        {views.filter((v) => !v.is_default).map((v) => (
          <option key={v.view_id} value={v.view_id}>
            {v.name}{v.owner !== currentUser ? ` (${v.owner})` : ""}
          </option>
        ))}
      </select>

      {dirty && (isOwner || !activeViewId) && (
        <button className="view-toolbar__btn view-toolbar__btn--primary" onClick={onSaveView}>
          Save
        </button>
      )}

      {dirty && (
        <button className="view-toolbar__btn" onClick={onSaveNewView}>
          Save As New
        </button>
      )}

      {isOwner && !activeView?.is_default && (
        <button
          className="view-toolbar__btn view-toolbar__btn--danger"
          onClick={() => onDeleteView(activeViewId!)}
        >
          Delete
        </button>
      )}
    </div>
  );
}
