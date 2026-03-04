import type { PackEditorState } from "../hooks/usePackEditor";
import { WidgetContainer } from "./WidgetContainer";
import { EntityPicker } from "./EntityPicker";
import "../styles/packs.css";

interface PackGridProps {
  editor: PackEditorState;
}

export function PackGrid({ editor }: PackGridProps) {
  const {
    rowColumns,
    rowHeights,
    rowDescriptions,
    resolvedWidgets,
    widgetMap,
    dragOverCell,
    targetCell,
    pickedEntity,
    editingTitle,
    isOwner,
    pickerRef,
    setRowDescription,
    setWidgetTitle,
    addWidgetToCell,
    removeWidget,
    removeRow,
    addRow,
    addColumn,
    removeColumn,
    handleDragStart,
    handleDragEnd,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    handleResizeMouseDown,
    handleCellClick,
    setTargetCell,
    setPickedEntity,
    setEditingTitle,
    getWidgetTitle,
  } = editor;

  const MAX_ROWS = 15;
  const MAX_COLS = 3;
  const DEFAULT_ROW_HEIGHT = 280;

  return (
    <>
      {rowColumns.map((colCount, rowIdx) => {
        const desc = rowDescriptions[rowIdx] || "";
        return (
          <div key={rowIdx} className="pack-page__row">
            {isOwner ? (
              <input
                className="pack-page__row-desc-input"
                value={desc}
                onChange={(e) =>
                  setRowDescription(rowIdx, e.target.value)
                }
                placeholder="Row description (optional)..."
              />
            ) : (
              desc && (
                <p className="pack-page__row-desc">{desc}</p>
              )
            )}

            {isOwner && rowColumns.length > 1 && (
              <div className="pack-page__row-controls">
                <button
                  className="pack-builder__remove-row-btn"
                  onClick={() => removeRow(rowIdx)}
                  title="Remove row"
                >
                  &times; Remove Row
                </button>
              </div>
            )}

            <div className="pack-page__row-grid-wrap">
              <div
                className="pack-page__grid"
                style={{
                  gridTemplateColumns: `repeat(${colCount}, 1fr)`,
                  height: rowHeights[rowIdx] || DEFAULT_ROW_HEIGHT,
                }}
              >
                {Array.from({ length: colCount }, (_, colIdx) => {
                  const key = `${rowIdx}-${colIdx}`;
                  const widgetRef = widgetMap[key];
                  const resolved = resolvedWidgets[key];
                  const isDragOver = dragOverCell === key;

                  if (widgetRef) {
                    const titleKey = key;
                    const displayTitle = getWidgetTitle(widgetRef);
                    return (
                      <div
                        key={key}
                        className={
                          "pack-builder__cell pack-builder__cell--filled" +
                          (isDragOver
                            ? " pack-builder__cell--drag-over"
                            : "")
                        }
                        draggable={isOwner}
                        onDragStart={
                          isOwner
                            ? (e) =>
                                handleDragStart(e, rowIdx, colIdx)
                            : undefined
                        }
                        onDragEnd={
                          isOwner ? handleDragEnd : undefined
                        }
                        onDragOver={
                          isOwner
                            ? (e) =>
                                handleDragOver(e, rowIdx, colIdx)
                            : undefined
                        }
                        onDragLeave={
                          isOwner ? handleDragLeave : undefined
                        }
                        onDrop={
                          isOwner
                            ? (e) =>
                                handleDrop(e, rowIdx, colIdx)
                            : undefined
                        }
                      >
                        <div className="pack-builder__cell-header">
                          {isOwner && editingTitle === titleKey ? (
                            <input
                              className="pack-builder__title-input"
                              value={
                                widgetRef.title_override ??
                                resolved?.title ??
                                ""
                              }
                              onChange={(e) =>
                                setWidgetTitle(
                                  rowIdx,
                                  colIdx,
                                  e.target.value
                                )
                              }
                              onBlur={() => setEditingTitle(null)}
                              onKeyDown={(e) =>
                                e.key === "Enter" &&
                                setEditingTitle(null)
                              }
                              autoFocus
                            />
                          ) : (
                            <span
                              className={
                                "pack-builder__widget-name" +
                                (isOwner
                                  ? " pack-builder__widget-name--editable"
                                  : "")
                              }
                              onClick={() =>
                                isOwner &&
                                setEditingTitle(titleKey)
                              }
                              title={
                                isOwner
                                  ? "Click to rename"
                                  : undefined
                              }
                            >
                              {displayTitle}
                            </span>
                          )}
                          <span className="pack-builder__widget-source">
                            {widgetRef.source_entity_type}/
                            {widgetRef.source_entity_id}
                          </span>
                          {isOwner && (
                            <div className="pack-builder__cell-actions">
                              <button
                                className="pack-builder__remove-btn"
                                onClick={() =>
                                  removeWidget(rowIdx, colIdx)
                                }
                              >
                                Remove
                              </button>
                            </div>
                          )}
                        </div>
                        {resolved && (
                          <div className="pack-builder__cell-preview">
                            <WidgetContainer config={resolved} entityId={widgetRef.source_entity_id} />
                          </div>
                        )}
                      </div>
                    );
                  }

                  // Empty cell
                  if (isOwner) {
                    return (
                      <div
                        key={key}
                        className={
                          "pack-builder__cell pack-builder__cell--empty" +
                          (isDragOver
                            ? " pack-builder__cell--drag-over"
                            : "")
                        }
                        onClick={() =>
                          handleCellClick(rowIdx, colIdx)
                        }
                        onDragOver={(e) =>
                          handleDragOver(e, rowIdx, colIdx)
                        }
                        onDragLeave={handleDragLeave}
                        onDrop={(e) =>
                          handleDrop(e, rowIdx, colIdx)
                        }
                      >
                        <span className="pack-builder__cell-placeholder">
                          Click to add widget
                        </span>
                      </div>
                    );
                  }

                  return null;
                })}
              </div>

              {isOwner && (
                <div className="pack-page__col-side-btns">
                  {colCount < MAX_COLS && (
                    <button
                      className="pack-page__col-side-btn"
                      onClick={() => addColumn(rowIdx)}
                      title="Add column"
                    >
                      + Add Col
                    </button>
                  )}
                  {colCount > 1 && (
                    <button
                      className="pack-page__col-side-btn pack-page__col-side-btn--remove"
                      onClick={() => removeColumn(rowIdx)}
                      title="Remove column"
                    >
                      - Remove Col
                    </button>
                  )}
                </div>
              )}
            </div>

            {isOwner && (
              <div
                className="pack-page__resize-handle"
                onMouseDown={(e) => handleResizeMouseDown(rowIdx, e)}
              />
            )}
          </div>
        );
      })}

      {isOwner && rowColumns.length < MAX_ROWS && (
        <button className="pack-page__add-row-btn" onClick={addRow}>
          + Add Row
        </button>
      )}

      {targetCell && isOwner && (
        <div
          className="pack-picker__overlay"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setTargetCell(null);
              setPickedEntity(null);
            }
          }}
        >
          <div className="pack-picker__dialog" ref={pickerRef}>
            <div className="pack-picker__header">
              <h3>
                Add Widget to Row {targetCell.row + 1}, Col{" "}
                {targetCell.col + 1}
              </h3>
              <button
                className="pack-picker__close"
                onClick={() => {
                  setTargetCell(null);
                  setPickedEntity(null);
                }}
              >
                &times;
              </button>
            </div>
            {!pickedEntity ? (
              <EntityPicker
                autoFocus
                onSelect={(entity) => setPickedEntity(entity)}
                onCancel={() => {
                  setTargetCell(null);
                  setPickedEntity(null);
                }}
              />
            ) : (
              <div className="pack-builder__search-results">
                <p className="pack-builder__entity-label">
                  {pickedEntity.display_name} (
                  {pickedEntity.entity_type})
                </p>
                <p className="pack-builder__widget-prompt">
                  Select a widget:
                </p>
                <div className="pack-builder__widget-options">
                  {pickedEntity.widgets.map((w) => (
                    <button
                      key={w.widget_id}
                      className="pack-builder__add-btn"
                      onClick={() =>
                        addWidgetToCell(
                          pickedEntity.entity_type,
                          pickedEntity.entity_id,
                          w.widget_id,
                          targetCell.row,
                          targetCell.col
                        )
                      }
                    >
                      + {w.title}
                    </button>
                  ))}
                </div>
                <button
                  className="pack-builder__remove-btn"
                  style={{ marginTop: "0.5rem" }}
                  onClick={() => setPickedEntity(null)}
                >
                  Back to search
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
