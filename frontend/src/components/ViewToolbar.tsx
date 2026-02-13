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
  onViewSelect: (viewId: string | null) => void;
  onOverwriteView: () => void;
  onSaveNewView: () => void;
  onDeleteView: (viewId: string) => void;
}

export function ViewToolbar({
  activeViewId,
  views,
  currentUser,
  dirty,
  onViewSelect,
  onOverwriteView,
  onSaveNewView,
  onDeleteView,
}: ViewToolbarProps) {
  const activeView = activeViewId
    ? views.find((v) => v.view_id === activeViewId)
    : null;
  const isOwner = activeView?.owner === currentUser;
  const onSavedView = activeViewId != null;

  return (
    <div className="view-toolbar">
      <select
        className="view-toolbar__select"
        value={activeViewId ?? ""}
        onChange={(e) => onViewSelect(e.target.value || null)}
      >
        <option value="">Default View</option>
        {views.map((v) => (
          <option key={v.view_id} value={v.view_id}>
            {v.name}{v.owner !== currentUser ? ` (${v.owner})` : ""}
          </option>
        ))}
      </select>

      {dirty && onSavedView && isOwner && (
        <button className="view-toolbar__btn view-toolbar__btn--primary" onClick={onOverwriteView}>
          Overwrite View
        </button>
      )}

      {dirty && (
        <button className="view-toolbar__btn" onClick={onSaveNewView}>
          Save New View
        </button>
      )}

      {isOwner && (
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
