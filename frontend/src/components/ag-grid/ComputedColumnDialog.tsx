import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { ComputedColumnDef } from "./computedColumns";
import type { ColumnFormatConfig } from "./gridCustomizations";
import { FORMAT_PRESETS } from "./gridCustomizations";
import { validateExpression } from "./formulaEngine";
import "./ComputedColumnDialog.css";

interface ComputedColumnDialogProps {
  existingColumn: ComputedColumnDef | null; // null = create, non-null = edit
  availableFields: { field: string; headerName: string }[];
  onSave: (def: ComputedColumnDef) => void;
  onDelete?: (id: string) => void;
  onCancel: () => void;
}

const DECIMAL_OPTIONS = [0, 1, 2, 3, 4, 5, 6];

function presetMatches(
  a: ColumnFormatConfig,
  b: ColumnFormatConfig,
): boolean {
  return (
    (a.prefix ?? "") === (b.prefix ?? "") &&
    (a.decimals ?? 2) === (b.decimals ?? 2) &&
    (a.isPercent ?? false) === (b.isPercent ?? false)
  );
}

export function ComputedColumnDialog({
  existingColumn,
  availableFields,
  onSave,
  onDelete,
  onCancel,
}: ComputedColumnDialogProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Form state
  const [name, setName] = useState(existingColumn?.name ?? "");
  const [expression, setExpression] = useState(existingColumn?.expression ?? "");

  // Format state
  const initFormat = existingColumn?.format;
  const [formatPrefix, setFormatPrefix] = useState(initFormat?.prefix ?? "");
  const [formatDecimals, setFormatDecimals] = useState(initFormat?.decimals ?? 2);
  const [formatIsPercent, setFormatIsPercent] = useState(initFormat?.isPercent ?? false);

  // Validation
  const [validationResult, setValidationResult] = useState<
    { valid: true } | { valid: false; error: string } | null
  >(null);

  const fieldNames = useMemo(
    () => availableFields.map((f) => f.field),
    [availableFields],
  );

  // Debounced validation
  useEffect(() => {
    if (!expression.trim()) {
      setValidationResult(null);
      return;
    }
    const timer = setTimeout(() => {
      setValidationResult(validateExpression(expression, fieldNames));
    }, 300);
    return () => clearTimeout(timer);
  }, [expression, fieldNames]);

  // Escape to close
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onCancel]);

  // Insert field reference at cursor
  const handlePillClick = useCallback((field: string) => {
    const ta = textareaRef.current;
    if (!ta) return;
    const ref = `{${field}}`;
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    const before = ta.value.substring(0, start);
    const after = ta.value.substring(end);
    const newVal = before + ref + after;
    setExpression(newVal);
    // Restore cursor position after the inserted text
    requestAnimationFrame(() => {
      ta.focus();
      const newPos = start + ref.length;
      ta.setSelectionRange(newPos, newPos);
    });
  }, []);

  const handlePresetClick = useCallback((config: ColumnFormatConfig) => {
    setFormatPrefix(config.prefix ?? "");
    setFormatDecimals(config.decimals ?? 2);
    setFormatIsPercent(config.isPercent ?? false);
  }, []);

  // Build format config — only include if any format setting is non-default
  const currentFormat: ColumnFormatConfig = {
    prefix: formatPrefix,
    decimals: formatDecimals,
    isPercent: formatIsPercent,
  };

  const hasFormat = formatPrefix !== "" || formatDecimals !== 2 || formatIsPercent;

  const canSave =
    name.trim() !== "" &&
    expression.trim() !== "" &&
    validationResult?.valid === true;

  const handleSave = () => {
    if (!canSave) return;
    onSave({
      id: existingColumn?.id ?? "", // AppGrid assigns ID for new columns
      name: name.trim(),
      expression: expression.trim(),
      format: hasFormat ? currentFormat : undefined,
      createdAt: existingColumn?.createdAt ?? Date.now(),
    });
  };

  const isEditing = existingColumn !== null;

  return createPortal(
    <div className="computed-dialog__overlay" onClick={onCancel}>
      <div className="computed-dialog" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="computed-dialog__header">
          <h3 className="computed-dialog__title">
            {isEditing ? "Edit Computed Column" : "Create Computed Column"}
          </h3>
          <button className="computed-dialog__close" onClick={onCancel}>
            &times;
          </button>
        </div>

        {/* Column Name */}
        <div className="computed-dialog__field">
          <label className="computed-dialog__label">Column Name</label>
          <input
            type="text"
            className="computed-dialog__input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Price % of 52W High"
            autoFocus
          />
        </div>

        {/* Formula */}
        <div className="computed-dialog__field">
          <label className="computed-dialog__label">Formula</label>
          <textarea
            ref={textareaRef}
            className="computed-dialog__textarea"
            value={expression}
            onChange={(e) => setExpression(e.target.value)}
            placeholder='e.g. {current_price} / {52w_high} * 100'
            rows={2}
          />
        </div>

        {/* Available columns pills */}
        <div className="computed-dialog__pills-label">
          Available columns (click to insert)
        </div>
        <div className="computed-dialog__pills">
          {availableFields.map((f) => (
            <button
              key={f.field}
              className="computed-dialog__pill"
              onClick={() => handlePillClick(f.field)}
              title={f.headerName}
            >
              {f.field}
            </button>
          ))}
        </div>

        {/* Format section */}
        <div className="computed-dialog__field">
          <div className="computed-dialog__format-label">Format</div>
          <div className="computed-dialog__format-presets">
            {FORMAT_PRESETS.map((preset) => {
              const isActive = presetMatches(currentFormat, preset.config);
              return (
                <button
                  key={preset.label}
                  className={`computed-dialog__format-pill${isActive ? " computed-dialog__format-pill--active" : ""}`}
                  onClick={() => handlePresetClick(preset.config)}
                >
                  {preset.label}
                </button>
              );
            })}
          </div>
          <div className="computed-dialog__format-row">
            <label className="computed-dialog__format-row-label">Prefix</label>
            <input
              className="computed-dialog__format-input"
              type="text"
              value={formatPrefix}
              onChange={(e) => setFormatPrefix(e.target.value)}
              placeholder='e.g. "$"'
            />
          </div>
          <div className="computed-dialog__format-row">
            <label className="computed-dialog__format-row-label">Decimals</label>
            <select
              className="computed-dialog__format-select"
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
          <div className="computed-dialog__format-row">
            <label className="computed-dialog__format-row-label">
              <input
                type="checkbox"
                checked={formatIsPercent}
                onChange={(e) => setFormatIsPercent(e.target.checked)}
              />
              {" "}Percent (%)
            </label>
          </div>
        </div>

        {/* Validation feedback */}
        <div className="computed-dialog__validation">
          {validationResult !== null &&
            (validationResult.valid ? (
              <span className="computed-dialog__validation--valid">
                &#10003; Valid formula
              </span>
            ) : (
              <span className="computed-dialog__validation--error">
                &#10007; {validationResult.error}
              </span>
            ))}
        </div>

        {/* Actions */}
        <div className="computed-dialog__actions">
          <div>
            {isEditing && onDelete && (
              <button
                className="computed-dialog__btn computed-dialog__btn--delete"
                onClick={() => onDelete(existingColumn.id)}
              >
                Delete
              </button>
            )}
          </div>
          <div className="computed-dialog__actions-right">
            <button
              className="computed-dialog__btn computed-dialog__btn--cancel"
              onClick={onCancel}
            >
              Cancel
            </button>
            <button
              className="computed-dialog__btn computed-dialog__btn--save"
              disabled={!canSave}
              onClick={handleSave}
            >
              Save
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
