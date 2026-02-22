import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import api from "../config/api";
import type {
  EntityDetail,
  PackWidgetRef,
  AnalystPack,
  WidgetConfig,
} from "../types/entities";
import { Layout } from "../components/Layout";
import { WidgetContainer } from "../components/WidgetContainer";
import { EntityPicker } from "../components/EntityPicker";
import { ScheduleEmailDialog } from "../components/ScheduleEmailDialog";
import { useAuth } from "../auth/useAuth";
import * as viewsApi from "../config/viewsApi";
import "../styles/entity.css";
import "../styles/packs.css";

const MAX_ROWS = 15;
const MAX_COLS = 3;

export function PackPage() {
  const { packId } = useParams<{ packId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [pack, setPack] = useState<AnalystPack | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAlertDialog, setShowAlertDialog] = useState(false);

  // Editable state
  const [packWidgets, setPackWidgets] = useState<PackWidgetRef[]>([]);
  const [rowColumns, setRowColumns] = useState<number[]>([2]);
  const [rowDescriptions, setRowDescriptions] = useState<string[]>([]);
  const [packName, setPackName] = useState("");
  const [packDesc, setPackDesc] = useState("");
  const [packShared, setPackShared] = useState(false);

  // Resolved widget configs keyed by "row-col"
  const [resolvedWidgets, setResolvedWidgets] = useState<
    Record<string, WidgetConfig>
  >({});

  // Entity picker state
  const [targetCell, setTargetCell] = useState<{
    row: number;
    col: number;
  } | null>(null);
  const [pickedEntity, setPickedEntity] = useState<EntityDetail | null>(null);

  // Drag-and-drop
  const dragSource = useRef<{ row: number; col: number } | null>(null);
  const [dragOverCell, setDragOverCell] = useState<string | null>(null);

  // Saving
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  // Editing header fields
  const [editingName, setEditingName] = useState(false);
  const [editingDesc, setEditingDesc] = useState(false);

  // Widget title editing
  const [editingTitle, setEditingTitle] = useState<string | null>(null);

  const pickerRef = useRef<HTMLDivElement>(null);

  const isOwner = pack?.owner === user?.username;

  // Load pack
  useEffect(() => {
    if (!packId) return;
    setLoading(true);
    setError(null);

    Promise.all([
      viewsApi.getPack(packId),
      viewsApi.resolvePackWidgets(packId),
    ])
      .then(([packData, resolved]) => {
        setPack(packData);
        setPackWidgets(packData.widgets);
        setRowColumns(
          packData.row_columns.length > 0 ? packData.row_columns : [2]
        );
        setRowDescriptions(packData.row_descriptions || []);
        setPackName(packData.name);
        setPackDesc(packData.description);
        setPackShared(packData.is_shared);
        const map: Record<string, WidgetConfig> = {};
        packData.widgets.forEach((ref, idx) => {
          if (resolved[idx]) {
            map[`${ref.row}-${ref.col}`] = resolved[idx];
          }
        });
        setResolvedWidgets(map);
      })
      .catch(() => setError("Failed to load pack"))
      .finally(() => setLoading(false));
  }, [packId]);

  // Save helper
  const saveChanges = useCallback(
    async (
      widgets: PackWidgetRef[],
      cols: number[],
      descs: string[],
      name: string,
      desc: string,
      shared: boolean
    ) => {
      if (!packId) return;
      setSaving(true);
      try {
        const updated = await viewsApi.updatePack(packId, {
          name: name.trim(),
          description: desc.trim(),
          widgets,
          is_shared: shared,
          row_columns: cols,
          row_descriptions: descs,
        });
        setPack(updated);
        setDirty(false);
      } catch {
        // silent
      } finally {
        setSaving(false);
      }
    },
    [packId]
  );

  const handleSave = () => {
    if (!dirty || !isOwner) return;
    saveChanges(
      packWidgets,
      rowColumns,
      rowDescriptions,
      packName,
      packDesc,
      packShared
    );
  };

  const markDirty = () => setDirty(true);

  // Widget map
  const widgetMap = useMemo(() => {
    const map: Record<string, PackWidgetRef> = {};
    for (const w of packWidgets) {
      map[`${w.row}-${w.col}`] = w;
    }
    return map;
  }, [packWidgets]);

  // Resolve a single widget
  const resolveWidget = useCallback(async (ref: PackWidgetRef) => {
    try {
      const resp = await api.get<EntityDetail>(
        `/api/entities/${ref.source_entity_type}/${ref.source_entity_id}`
      );
      const config = resp.data.widgets.find(
        (w) => w.widget_id === ref.widget_id
      );
      if (config) {
        setResolvedWidgets((prev) => ({
          ...prev,
          [`${ref.row}-${ref.col}`]: config,
        }));
      }
    } catch {
      /* skip */
    }
  }, []);

  // --- Grid mutations ---
  const addRow = () => {
    if (rowColumns.length >= MAX_ROWS) return;
    setRowColumns((prev) => [...prev, 2]);
    setRowDescriptions((prev) => [...prev]); // no desc by default
    markDirty();
  };

  const removeRow = (rowIdx: number) => {
    if (rowColumns.length <= 1) return;
    setPackWidgets((prev) =>
      prev
        .filter((w) => w.row !== rowIdx)
        .map((w) => (w.row > rowIdx ? { ...w, row: w.row - 1 } : w))
    );
    setResolvedWidgets((prev) => {
      const next: Record<string, WidgetConfig> = {};
      for (const [key, val] of Object.entries(prev)) {
        const [r, c] = key.split("-").map(Number);
        if (r === rowIdx) continue;
        const newRow = r > rowIdx ? r - 1 : r;
        next[`${newRow}-${c}`] = val;
      }
      return next;
    });
    setRowColumns((prev) => prev.filter((_, i) => i !== rowIdx));
    setRowDescriptions((prev) => prev.filter((_, i) => i !== rowIdx));
    markDirty();
  };

  const addColumn = (rowIdx: number) => {
    const current = rowColumns[rowIdx];
    if (current >= MAX_COLS) return;
    setRowColumns((prev) =>
      prev.map((v, i) => (i === rowIdx ? v + 1 : v))
    );
    markDirty();
  };

  const removeColumn = (rowIdx: number) => {
    const current = rowColumns[rowIdx];
    if (current <= 1) return;
    const newCount = current - 1;
    // Remove widgets in the last column
    setPackWidgets((prev) =>
      prev.filter((w) => !(w.row === rowIdx && w.col >= newCount))
    );
    setResolvedWidgets((prev) => {
      const next = { ...prev };
      delete next[`${rowIdx}-${newCount}`];
      return next;
    });
    setRowColumns((prev) =>
      prev.map((v, i) => (i === rowIdx ? newCount : v))
    );
    markDirty();
  };

  const setRowDescription = (rowIdx: number, text: string) => {
    setRowDescriptions((prev) => {
      const next = [...prev];
      while (next.length <= rowIdx) next.push("");
      next[rowIdx] = text;
      return next;
    });
    markDirty();
  };

  const setWidgetTitle = (row: number, col: number, title: string) => {
    setPackWidgets((prev) =>
      prev.map((w) =>
        w.row === row && w.col === col
          ? { ...w, title_override: title || null }
          : w
      )
    );
    markDirty();
  };

  const addWidgetToCell = (
    entityType: string,
    entityId: string,
    widgetId: string,
    row: number,
    col: number
  ) => {
    const ref: PackWidgetRef = {
      source_entity_type: entityType,
      source_entity_id: entityId,
      widget_id: widgetId,
      title_override: null,
      overrides: null,
      row,
      col,
    };
    setPackWidgets((prev) => [...prev, ref]);
    setTargetCell(null);
    setPickedEntity(null);
    resolveWidget(ref);
    markDirty();
  };

  const removeWidget = (row: number, col: number) => {
    setPackWidgets((prev) =>
      prev.filter((w) => !(w.row === row && w.col === col))
    );
    setResolvedWidgets((prev) => {
      const next = { ...prev };
      delete next[`${row}-${col}`];
      return next;
    });
    markDirty();
  };

  const moveWidget = (
    fromRow: number,
    fromCol: number,
    toRow: number,
    toCol: number
  ) => {
    if (fromRow === toRow && fromCol === toCol) return;
    const hasSource = packWidgets.some(
      (w) => w.row === fromRow && w.col === fromCol
    );
    const hasTarget = packWidgets.some(
      (w) => w.row === toRow && w.col === toCol
    );

    if (hasSource && hasTarget) {
      setPackWidgets((prev) =>
        prev.map((w) => {
          if (w.row === fromRow && w.col === fromCol)
            return { ...w, row: toRow, col: toCol };
          if (w.row === toRow && w.col === toCol)
            return { ...w, row: fromRow, col: fromCol };
          return w;
        })
      );
      setResolvedWidgets((prev) => {
        const next = { ...prev };
        const fk = `${fromRow}-${fromCol}`,
          tk = `${toRow}-${toCol}`;
        const tmp = next[fk];
        next[fk] = next[tk];
        next[tk] = tmp;
        return next;
      });
    } else if (hasSource) {
      setPackWidgets((prev) =>
        prev.map((w) =>
          w.row === fromRow && w.col === fromCol
            ? { ...w, row: toRow, col: toCol }
            : w
        )
      );
      setResolvedWidgets((prev) => {
        const next = { ...prev };
        const fk = `${fromRow}-${fromCol}`,
          tk = `${toRow}-${toCol}`;
        if (next[fk]) {
          next[tk] = next[fk];
          delete next[fk];
        }
        return next;
      });
    }
    markDirty();
  };

  // --- DnD handlers ---
  const handleDragStart = (
    e: React.DragEvent,
    row: number,
    col: number
  ) => {
    dragSource.current = { row, col };
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", `${row}-${col}`);
    requestAnimationFrame(() => {
      (e.currentTarget as HTMLElement).classList.add(
        "pack-builder__cell--dragging"
      );
    });
  };
  const handleDragEnd = (e: React.DragEvent) => {
    dragSource.current = null;
    setDragOverCell(null);
    (e.currentTarget as HTMLElement).classList.remove(
      "pack-builder__cell--dragging"
    );
  };
  const handleDragOver = (
    e: React.DragEvent,
    row: number,
    col: number
  ) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    const key = `${row}-${col}`;
    if (dragOverCell !== key) setDragOverCell(key);
  };
  const handleDragLeave = () => setDragOverCell(null);
  const handleDrop = (
    e: React.DragEvent,
    toRow: number,
    toCol: number
  ) => {
    e.preventDefault();
    setDragOverCell(null);
    if (!dragSource.current) return;
    const { row: fr, col: fc } = dragSource.current;
    dragSource.current = null;
    moveWidget(fr, fc, toRow, toCol);
  };

  const handleCellClick = (row: number, col: number) => {
    if (!isOwner) return;
    if (!widgetMap[`${row}-${col}`]) {
      setTargetCell({ row, col });
      setPickedEntity(null);
    }
  };

  const handleDelete = async () => {
    if (!packId || !confirm("Delete this pack?")) return;
    await viewsApi.deletePack(packId);
    navigate("/packs");
  };

  // All resolved configs (for ScheduleEmailDialog)
  const allResolvedWidgets = useMemo(() => {
    return packWidgets
      .map((ref) => resolvedWidgets[`${ref.row}-${ref.col}`])
      .filter((c): c is WidgetConfig => !!c);
  }, [packWidgets, resolvedWidgets]);

  // Helper: get display title for a widget cell
  const getWidgetTitle = (ref: PackWidgetRef) => {
    if (ref.title_override) return ref.title_override;
    const resolved = resolvedWidgets[`${ref.row}-${ref.col}`];
    return resolved?.title || ref.widget_id;
  };

  if (loading) {
    return (
      <Layout>
        <div className="entity-page__loading">
          <div className="spinner" />
        </div>
      </Layout>
    );
  }

  if (error || !pack) {
    return (
      <Layout>
        <div className="pack-page">
          <Link to="/packs" className="entity-page__back">
            &larr; Back to Packs
          </Link>
          <div className="entity-page__error">
            {error || "Pack not found"}
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="pack-page">
        <Link to="/packs" className="entity-page__back">
          &larr; Back to Packs
        </Link>

        {/* Header */}
        <div className="pack-page__header">
          <div className="pack-page__header-left">
            {isOwner && editingName ? (
              <input
                className="pack-page__name-input"
                value={packName}
                onChange={(e) => {
                  setPackName(e.target.value);
                  markDirty();
                }}
                onBlur={() => setEditingName(false)}
                onKeyDown={(e) =>
                  e.key === "Enter" && setEditingName(false)
                }
                autoFocus
              />
            ) : (
              <h2
                className={
                  "pack-page__name" +
                  (isOwner ? " pack-page__name--editable" : "")
                }
                onClick={() => isOwner && setEditingName(true)}
                title={isOwner ? "Click to edit" : undefined}
              >
                {packName}
              </h2>
            )}
            {isOwner && editingDesc ? (
              <textarea
                className="pack-page__desc-input"
                value={packDesc}
                onChange={(e) => {
                  setPackDesc(e.target.value);
                  markDirty();
                }}
                onBlur={() => setEditingDesc(false)}
                rows={2}
                autoFocus
              />
            ) : (
              <p
                className={
                  "pack-page__desc" +
                  (isOwner ? " pack-page__desc--editable" : "")
                }
                onClick={() => isOwner && setEditingDesc(true)}
                title={isOwner ? "Click to edit" : undefined}
              >
                {packDesc || (isOwner ? "Click to add description..." : "")}
              </p>
            )}
            <div className="pack-page__meta">
              <span>
                Owner: {pack.owner_display_name || pack.owner}
              </span>
              {isOwner ? (
                <label className="pack-page__shared-toggle">
                  <input
                    type="checkbox"
                    checked={packShared}
                    onChange={(e) => {
                      setPackShared(e.target.checked);
                      markDirty();
                    }}
                  />
                  Public
                </label>
              ) : (
                pack.is_shared && (
                  <span className="pack-page__shared-badge">Shared</span>
                )
              )}
            </div>
          </div>
          <div className="pack-page__actions">
            {isOwner && dirty && (
              <button
                className="entity-page__action-btn entity-page__action-btn--primary"
                onClick={handleSave}
                disabled={saving}
              >
                {saving ? "Saving..." : "Save Pack"}
              </button>
            )}
            {isOwner && (
              <button
                className="entity-page__action-btn entity-page__action-btn--danger"
                onClick={handleDelete}
              >
                Delete
              </button>
            )}
            <button
              className="entity-page__action-btn entity-page__action-btn--primary"
              onClick={() => setShowAlertDialog(true)}
            >
              Send Alert
            </button>
          </div>
        </div>

        {/* Grid rows */}
        {rowColumns.map((colCount, rowIdx) => {
          const desc = rowDescriptions[rowIdx] || "";
          return (
            <div key={rowIdx} className="pack-page__row">
              {/* Row description */}
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

              {/* Row controls: remove row button */}
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

              {/* Grid + side column buttons */}
              <div className="pack-page__row-grid-wrap">
                <div
                  className="pack-page__grid"
                  style={{
                    gridTemplateColumns: `repeat(${colCount}, 1fr)`,
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

                {/* Side column buttons */}
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
            </div>
          );
        })}

        {/* Add row button */}
        {isOwner && rowColumns.length < MAX_ROWS && (
          <button className="pack-page__add-row-btn" onClick={addRow}>
            + Add Row
          </button>
        )}
      </div>

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

      {showAlertDialog && pack && (
        <ScheduleEmailDialog
          entityType="pack"
          entityId={pack.pack_id}
          widgets={allResolvedWidgets}
          userEmail={user?.email}
          onSave={() => setShowAlertDialog(false)}
          onCancel={() => setShowAlertDialog(false)}
        />
      )}
    </Layout>
  );
}
