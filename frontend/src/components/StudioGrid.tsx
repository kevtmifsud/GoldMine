import type { StudioEditorState } from "../hooks/useStudioEditor";
import { StudioChartWidget } from "./StudioChartWidget";
import "../styles/studio.css";

const MAX_ROWS = 15;
const MAX_COLS = 3;
const DEFAULT_ROW_HEIGHT = 280;

interface StudioGridProps {
  editor: StudioEditorState;
}

export function StudioGrid({ editor }: StudioGridProps) {
  const {
    widgets,
    rowColumns,
    rowHeights,
    widgetMap,
    dragOverCell,
    isOwner,
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
  } = editor;

  if (widgets.length === 0) {
    return (
      <div className="studio-grid__empty-canvas">
        <span>No charts yet</span>
        <span className="studio-grid__empty-canvas-hint">
          Use the chat to create charts, e.g. "Show me AAPL revenue trend"
        </span>
      </div>
    );
  }

  return (
    <>
      {rowColumns.map((colCount, rowIdx) => (
        <div key={rowIdx} className="studio-grid__row">
          {isOwner && rowColumns.length > 1 && (
            <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "0.25rem" }}>
              <button
                className="studio-grid__col-side-btn studio-grid__col-side-btn--remove"
                onClick={() => removeRow(rowIdx)}
                style={{ fontSize: "0.7rem", padding: "0.2rem 0.4rem" }}
              >
                Remove Row
              </button>
            </div>
          )}

          <div className="studio-grid__row-grid-wrap">
            <div
              className="studio-grid__grid"
              style={{
                gridTemplateColumns: `repeat(${colCount}, 1fr)`,
                height: rowHeights[rowIdx] || DEFAULT_ROW_HEIGHT,
              }}
            >
              {Array.from({ length: colCount }, (_, colIdx) => {
                const key = `${rowIdx}-${colIdx}`;
                const widget = widgetMap[key];
                const isDragOver = dragOverCell === key;

                if (widget) {
                  return (
                    <div
                      key={key}
                      className={
                        "studio-grid__cell studio-grid__cell--filled" +
                        (isDragOver ? " studio-grid__cell--drag-over" : "")
                      }
                      draggable={isOwner}
                      onDragStart={
                        isOwner
                          ? (e) => handleDragStart(e, rowIdx, colIdx)
                          : undefined
                      }
                      onDragEnd={isOwner ? handleDragEnd : undefined}
                      onDragOver={
                        isOwner
                          ? (e) => handleDragOver(e, rowIdx, colIdx)
                          : undefined
                      }
                      onDragLeave={isOwner ? handleDragLeave : undefined}
                      onDrop={
                        isOwner
                          ? (e) => handleDrop(e, rowIdx, colIdx)
                          : undefined
                      }
                    >
                      <div className="studio-grid__cell-header">
                        <span className="studio-grid__cell-title">
                          {widget.title}
                        </span>
                        {isOwner && (
                          <button
                            className="studio-grid__cell-remove"
                            onClick={() => removeWidget(rowIdx, colIdx)}
                            title="Remove chart"
                          >
                            &times;
                          </button>
                        )}
                      </div>
                      <div className="studio-grid__cell-body">
                        <StudioChartWidget widget={widget} />
                      </div>
                    </div>
                  );
                }

                // Empty cell
                return (
                  <div
                    key={key}
                    className={
                      "studio-grid__cell studio-grid__cell--empty" +
                      (isDragOver ? " studio-grid__cell--drag-over" : "")
                    }
                    onDragOver={
                      isOwner
                        ? (e) => handleDragOver(e, rowIdx, colIdx)
                        : undefined
                    }
                    onDragLeave={isOwner ? handleDragLeave : undefined}
                    onDrop={
                      isOwner
                        ? (e) => handleDrop(e, rowIdx, colIdx)
                        : undefined
                    }
                  >
                    <span className="studio-grid__cell-placeholder">
                      Empty
                    </span>
                  </div>
                );
              })}
            </div>

            {isOwner && (
              <div className="studio-grid__col-side-btns">
                {colCount < MAX_COLS && (
                  <button
                    className="studio-grid__col-side-btn"
                    onClick={() => addColumn(rowIdx)}
                    title="Add column"
                  >
                    + Col
                  </button>
                )}
                {colCount > 1 && (
                  <button
                    className="studio-grid__col-side-btn studio-grid__col-side-btn--remove"
                    onClick={() => removeColumn(rowIdx)}
                    title="Remove column"
                  >
                    - Col
                  </button>
                )}
              </div>
            )}
          </div>

          {isOwner && (
            <div
              className="studio-grid__resize-handle"
              onMouseDown={(e) => handleResizeMouseDown(rowIdx, e)}
            />
          )}
        </div>
      ))}

      {isOwner && rowColumns.length < MAX_ROWS && (
        <button className="studio-grid__add-row-btn" onClick={addRow}>
          + Add Row
        </button>
      )}
    </>
  );
}
