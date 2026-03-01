import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import "./GridContextMenu.css";

interface GridContextMenuProps {
  position: { x: number; y: number };
  targetColumn: { field: string; headerName: string } | null;
  hiddenColumns: { field: string; headerName: string }[];
  canRemove: boolean;
  onAddColumn: (field: string) => void;
  onRemoveColumn: (field: string) => void;
  onClose: () => void;
}

export function GridContextMenu({
  position,
  targetColumn,
  hiddenColumns,
  canRemove,
  onAddColumn,
  onRemoveColumn,
  onClose,
}: GridContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [search, setSearch] = useState("");

  // Close on click outside or Escape
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [onClose]);

  // Auto-focus search input when hidden columns exist
  useEffect(() => {
    if (hiddenColumns.length > 0) {
      // Small delay to let the portal render
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [hiddenColumns.length]);

  // Clamp position to viewport
  const style: React.CSSProperties = { left: position.x, top: position.y };
  if (menuRef.current) {
    const rect = menuRef.current.getBoundingClientRect();
    if (rect.right > window.innerWidth) {
      style.left = window.innerWidth - rect.width - 8;
    }
    if (rect.bottom > window.innerHeight) {
      style.top = window.innerHeight - rect.height - 8;
    }
  }

  const searchLower = search.toLowerCase();
  const filtered = hiddenColumns
    .filter((c) => c.headerName.toLowerCase().includes(searchLower))
    .sort((a, b) => a.headerName.localeCompare(b.headerName));

  const showRemove = targetColumn && canRemove;
  const showAddSection = hiddenColumns.length > 0;

  // Don't render if nothing to show
  if (!showRemove && !showAddSection) return null;

  return createPortal(
    <div ref={menuRef} className="grid-context-menu" style={style}>
      {targetColumn && (
        <button
          className="grid-context-menu__item grid-context-menu__item--destructive"
          disabled={!canRemove}
          onClick={() => {
            onRemoveColumn(targetColumn.field);
            onClose();
          }}
        >
          Remove {targetColumn.headerName}
        </button>
      )}
      {targetColumn && showAddSection && (
        <div className="grid-context-menu__separator" />
      )}
      {showAddSection && (
        <>
          <div className="grid-context-menu__section-label">Add Column</div>
          <div className="grid-context-menu__search">
            <input
              ref={inputRef}
              className="grid-context-menu__search-input"
              type="text"
              placeholder="Search columns..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="grid-context-menu__add-list">
            {filtered.length === 0 && (
              <div className="grid-context-menu__no-results">No matches</div>
            )}
            {filtered.map((col) => (
              <button
                key={col.field}
                className="grid-context-menu__item"
                onClick={() => {
                  onAddColumn(col.field);
                  onClose();
                }}
              >
                {col.headerName}
              </button>
            ))}
          </div>
        </>
      )}
    </div>,
    document.body
  );
}
