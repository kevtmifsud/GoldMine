import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { ColumnFormatConfig, ColumnCustomization } from "./gridCustomizations";
import { FORMAT_PRESETS } from "./gridCustomizations";
import type { ComputedColumnDef } from "./computedColumns";
import "./GridContextMenu.css";

interface TargetColumn {
  field: string;
  headerName: string;
  originalHeaderName: string;
  isNumeric: boolean;
  hasRenderer: boolean;
  currentCustom?: ColumnCustomization;
  isComputed?: boolean;
  computedDef?: ComputedColumnDef;
}

interface GridContextMenuProps {
  position: { x: number; y: number };
  targetColumn: TargetColumn | null;
  hiddenColumns: { field: string; headerName: string }[];
  canRemove: boolean;
  onAddColumn: (field: string) => void;
  onRemoveColumn: (field: string) => void;
  onRenameColumn: (field: string, newName: string) => void;
  onFormatColumn: (field: string, format: ColumnFormatConfig) => void;
  onClearFormat: (field: string) => void;
  onCreateComputedColumn?: () => void;
  onEditComputedColumn?: (def: ComputedColumnDef) => void;
  onClose: () => void;
}

const DECIMAL_OPTIONS = [0, 1, 2, 3, 4, 5, 6];

export function GridContextMenu({
  position,
  targetColumn,
  hiddenColumns,
  canRemove,
  onAddColumn,
  onRemoveColumn,
  onRenameColumn,
  onFormatColumn,
  onClearFormat,
  onCreateComputedColumn,
  onEditComputedColumn,
  onClose,
}: GridContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const renameInputRef = useRef<HTMLInputElement>(null);
  const [search, setSearch] = useState("");

  // Rename state
  const [renameMode, setRenameMode] = useState(false);
  const [renameValue, setRenameValue] = useState("");

  // Format state
  const currentFormat = targetColumn?.currentCustom?.format;
  const [formatPrefix, setFormatPrefix] = useState(currentFormat?.prefix ?? "");
  const [formatDecimals, setFormatDecimals] = useState(currentFormat?.decimals ?? 2);
  const [formatIsPercent, setFormatIsPercent] = useState(currentFormat?.isPercent ?? false);

  // Re-initialize state when targetColumn changes (menu opens on a new column)
  useEffect(() => {
    const fmt = targetColumn?.currentCustom?.format;
    setFormatPrefix(fmt?.prefix ?? "");
    setFormatDecimals(fmt?.decimals ?? 2);
    setFormatIsPercent(fmt?.isPercent ?? false);
    setRenameMode(false);
    setRenameValue(targetColumn?.currentCustom?.rename ?? "");
  }, [targetColumn]);

  // Close on click outside; Escape closes rename mode first, then menu
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (renameMode) {
          setRenameMode(false);
        } else {
          onClose();
        }
      }
    };
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [onClose, renameMode]);

  // Auto-focus search input when hidden columns exist (and not in rename mode)
  useEffect(() => {
    if (!renameMode && hiddenColumns.length > 0) {
      requestAnimationFrame(() => searchInputRef.current?.focus());
    }
  }, [hiddenColumns.length, renameMode]);

  // Auto-focus rename input when entering rename mode
  useEffect(() => {
    if (renameMode) {
      requestAnimationFrame(() => {
        renameInputRef.current?.focus();
        renameInputRef.current?.select();
      });
    }
  }, [renameMode]);

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

  const showAddSection = hiddenColumns.length > 0;
  const showFormatSection =
    targetColumn && targetColumn.isNumeric && !targetColumn.hasRenderer;

  // Don't render if nothing to show
  if (!targetColumn && !showAddSection) return null;

  const handleRenameSubmit = () => {
    if (!targetColumn) return;
    const trimmed = renameValue.trim();
    // Empty string = clear rename (revert to original)
    onRenameColumn(targetColumn.field, trimmed);
    setRenameMode(false);
  };

  const handleApplyFormat = () => {
    if (!targetColumn) return;
    onFormatColumn(targetColumn.field, {
      prefix: formatPrefix,
      decimals: formatDecimals,
      isPercent: formatIsPercent,
    });
    onClose();
  };

  const handleResetFormat = () => {
    if (!targetColumn) return;
    onClearFormat(targetColumn.field);
    setFormatPrefix("");
    setFormatDecimals(2);
    setFormatIsPercent(false);
  };

  const handlePresetClick = (config: ColumnFormatConfig) => {
    setFormatPrefix(config.prefix ?? "");
    setFormatDecimals(config.decimals ?? 2);
    setFormatIsPercent(config.isPercent ?? false);
  };

  const isComputed = targetColumn?.isComputed ?? false;

  return createPortal(
    <div ref={menuRef} className="grid-context-menu" style={style}>
      {/* ---- Rename (all columns) ---- */}
      {targetColumn && (
        <>
          {renameMode ? (
            <div className="grid-context-menu__rename-row">
              <input
                ref={renameInputRef}
                className="grid-context-menu__rename-input"
                type="text"
                placeholder={targetColumn.originalHeaderName}
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleRenameSubmit();
                  if (e.key === "Escape") {
                    e.stopPropagation();
                    setRenameMode(false);
                  }
                }}
              />
              <button
                className="grid-context-menu__rename-confirm"
                onClick={handleRenameSubmit}
              >
                OK
              </button>
            </div>
          ) : (
            <button
              className="grid-context-menu__item"
              onClick={() => {
                setRenameValue(targetColumn.currentCustom?.rename ?? "");
                setRenameMode(true);
              }}
            >
              Rename Column
            </button>
          )}
        </>
      )}

      {/* ---- Remove (all columns) ---- */}
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

      {/* ---- Edit Computed Column (computed only) ---- */}
      {targetColumn && isComputed && onEditComputedColumn && targetColumn.computedDef && (
        <button
          className="grid-context-menu__item grid-context-menu__item--computed"
          onClick={() => {
            onEditComputedColumn(targetColumn.computedDef!);
            onClose();
          }}
        >
          Edit Computed Column...
        </button>
      )}

      {/* ---- Format section (regular columns only) ---- */}
      {showFormatSection && !isComputed && (
        <>
          <div className="grid-context-menu__separator" />
          <div className="grid-context-menu__section-label">Format</div>

          {/* Preset pills */}
          <div className="grid-context-menu__format-presets">
            {FORMAT_PRESETS.map((preset) => (
              <button
                key={preset.label}
                className="grid-context-menu__preset-pill"
                onClick={() => handlePresetClick(preset.config)}
              >
                {preset.label}
              </button>
            ))}
          </div>

          {/* Prefix */}
          <div className="grid-context-menu__format-row">
            <label className="grid-context-menu__format-label">Prefix</label>
            <input
              className="grid-context-menu__format-input"
              type="text"
              value={formatPrefix}
              onChange={(e) => setFormatPrefix(e.target.value)}
              placeholder='e.g. "$"'
            />
          </div>

          {/* Decimals */}
          <div className="grid-context-menu__format-row">
            <label className="grid-context-menu__format-label">Decimals</label>
            <select
              className="grid-context-menu__format-select"
              value={formatDecimals}
              onChange={(e) => setFormatDecimals(Number(e.target.value))}
            >
              {DECIMAL_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>

          {/* Percent */}
          <div className="grid-context-menu__format-row">
            <label className="grid-context-menu__format-label">
              <input
                type="checkbox"
                checked={formatIsPercent}
                onChange={(e) => setFormatIsPercent(e.target.checked)}
              />
              {" "}Percent (%)
            </label>
          </div>

          {/* Apply / Reset */}
          <div className="grid-context-menu__format-actions">
            <button
              className="grid-context-menu__format-apply"
              onClick={handleApplyFormat}
            >
              Apply
            </button>
            {currentFormat && (
              <button
                className="grid-context-menu__format-reset"
                onClick={handleResetFormat}
              >
                Reset Format
              </button>
            )}
          </div>
        </>
      )}

      {/* ---- Add column section ---- */}
      {showAddSection && (
        <>
          {targetColumn && <div className="grid-context-menu__separator" />}
          <div className="grid-context-menu__section-label">Add Column</div>
          <div className="grid-context-menu__search">
            <input
              ref={searchInputRef}
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

      {/* ---- Create Computed Column ---- */}
      {onCreateComputedColumn && (
        <>
          <div className="grid-context-menu__separator" />
          <button
            className="grid-context-menu__item grid-context-menu__item--computed"
            onClick={() => {
              onCreateComputedColumn();
              onClose();
            }}
          >
            Create Computed Column...
          </button>
        </>
      )}
    </div>,
    document.body,
  );
}
