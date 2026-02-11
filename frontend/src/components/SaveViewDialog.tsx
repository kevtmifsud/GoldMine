import { useState } from "react";
import "../styles/views.css";

interface SaveViewDialogProps {
  onSave: (name: string, isShared: boolean) => void;
  onCancel: () => void;
}

export function SaveViewDialog({ onSave, onCancel }: SaveViewDialogProps) {
  const [name, setName] = useState("");
  const [isShared, setIsShared] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    onSave(trimmed, isShared);
  };

  return (
    <div className="save-dialog__overlay" onClick={onCancel}>
      <div className="save-dialog" onClick={(e) => e.stopPropagation()}>
        <h3 className="save-dialog__title">Save View</h3>
        <form onSubmit={handleSubmit}>
          <div className="save-dialog__field">
            <label htmlFor="view-name">View Name</label>
            <input
              id="view-name"
              type="text"
              className="save-dialog__input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Enter view name"
              autoFocus
            />
          </div>
          <label className="save-dialog__checkbox">
            <input
              type="checkbox"
              checked={isShared}
              onChange={(e) => setIsShared(e.target.checked)}
            />
            Share with team
          </label>
          <div className="save-dialog__actions">
            <button
              type="button"
              className="save-dialog__btn save-dialog__btn--cancel"
              onClick={onCancel}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="save-dialog__btn save-dialog__btn--save"
              disabled={!name.trim()}
            >
              Save
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
