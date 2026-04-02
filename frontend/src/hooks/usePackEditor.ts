import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import api from "../config/api";
import type {
  EntityDetail,
  PackWidgetRef,
  AnalystPack,
  WidgetConfig,
} from "../types/entities";
import * as viewsApi from "../config/viewsApi";

const MAX_ROWS = 15;
const MAX_COLS = 3;
const DEFAULT_ROW_HEIGHT = 280;
const MIN_ROW_HEIGHT = 200;
const MAX_ROW_HEIGHT = 800;

export interface PackEditorState {
  pack: AnalystPack | null;
  loading: boolean;
  error: string | null;
  packWidgets: PackWidgetRef[];
  rowColumns: number[];
  rowHeights: number[];
  rowDescriptions: string[];
  resolvedWidgets: Record<string, WidgetConfig>;
  targetCell: { row: number; col: number } | null;
  pickedEntity: EntityDetail | null;
  dragOverCell: string | null;
  saving: boolean;
  dirty: boolean;
  editingTitle: string | null;
  isOwner: boolean;
  widgetMap: Record<string, PackWidgetRef>;
  allResolvedWidgets: WidgetConfig[];
  pickerRef: React.RefObject<HTMLDivElement>;
  dragSource: React.MutableRefObject<{ row: number; col: number } | null>;
  // Handlers
  addRow: () => void;
  removeRow: (rowIdx: number) => void;
  addColumn: (rowIdx: number) => void;
  removeColumn: (rowIdx: number) => void;
  setRowDescription: (rowIdx: number, text: string) => void;
  setWidgetTitle: (row: number, col: number, title: string) => void;
  addWidgetToCell: (
    entityType: string,
    entityId: string,
    widgetId: string,
    row: number,
    col: number
  ) => void;
  removeWidget: (row: number, col: number) => void;
  moveWidget: (
    fromRow: number,
    fromCol: number,
    toRow: number,
    toCol: number
  ) => void;
  handleDragStart: (e: React.DragEvent, row: number, col: number) => void;
  handleDragEnd: (e: React.DragEvent) => void;
  handleDragOver: (e: React.DragEvent, row: number, col: number) => void;
  handleDragLeave: () => void;
  handleDrop: (e: React.DragEvent, toRow: number, toCol: number) => void;
  handleResizeMouseDown: (rowIdx: number, e: React.MouseEvent) => void;
  handleCellClick: (row: number, col: number) => void;
  handleSave: () => void;
  markDirty: () => void;
  markClean: (updatedPack?: AnalystPack) => void;
  setTargetCell: React.Dispatch<
    React.SetStateAction<{ row: number; col: number } | null>
  >;
  setPickedEntity: React.Dispatch<React.SetStateAction<EntityDetail | null>>;
  setEditingTitle: React.Dispatch<React.SetStateAction<string | null>>;
  setDragOverCell: React.Dispatch<React.SetStateAction<string | null>>;
  getWidgetTitle: (ref: PackWidgetRef) => string;
  removeMCPTile: (tileId: string) => void;
  updateMCPTileTitle: (tileId: string, title: string) => void;
}

export function usePackEditor(
  packId: string | null,
  isOwner: boolean
): PackEditorState {
  const [pack, setPack] = useState<AnalystPack | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [packWidgets, setPackWidgets] = useState<PackWidgetRef[]>([]);
  const [rowColumns, setRowColumns] = useState<number[]>([2]);
  const [rowHeights, setRowHeights] = useState<number[]>([]);
  const [rowDescriptions, setRowDescriptions] = useState<string[]>([]);

  const [resolvedWidgets, setResolvedWidgets] = useState<
    Record<string, WidgetConfig>
  >({});

  const [targetCell, setTargetCell] = useState<{
    row: number;
    col: number;
  } | null>(null);
  const [pickedEntity, setPickedEntity] = useState<EntityDetail | null>(null);

  const dragSource = useRef<{ row: number; col: number } | null>(null);
  const [dragOverCell, setDragOverCell] = useState<string | null>(null);
  const resizeRef = useRef<{ rowIdx: number; startY: number; startH: number; gridEl: HTMLElement } | null>(null);

  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  const [editingTitle, setEditingTitle] = useState<string | null>(null);

  const pickerRef = useRef<HTMLDivElement>(null);

  // Load pack
  useEffect(() => {
    if (!packId) {
      setLoading(false);
      return;
    }
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
        setRowHeights(packData.row_heights ?? []);
        setRowDescriptions(packData.row_descriptions || []);
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
    async (widgets: PackWidgetRef[], cols: number[], heights: number[], descs: string[]) => {
      if (!packId) return;
      setSaving(true);
      try {
        const updated = await viewsApi.updatePack(packId, {
          widgets,
          row_columns: cols,
          row_heights: heights,
          row_descriptions: descs,
          mcp_tiles: pack?.mcp_tiles,
        });
        setPack(updated);
        setDirty(false);
      } catch {
        // silent
      } finally {
        setSaving(false);
      }
    },
    [packId, pack?.mcp_tiles]
  );

  const handleSave = () => {
    if (!dirty || !isOwner) return;
    saveChanges(packWidgets, rowColumns, rowHeights, rowDescriptions);
  };

  const markDirty = () => setDirty(true);
  const markClean = (updatedPack?: AnalystPack) => {
    setDirty(false);
    if (updatedPack) setPack(updatedPack);
  };

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
    setRowDescriptions((prev) => [...prev]);
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
    setRowHeights((prev) => prev.filter((_, i) => i !== rowIdx));
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

  // Row resize
  const handleResizeMouseDown = useCallback((rowIdx: number, e: React.MouseEvent) => {
    e.preventDefault();
    const gridEl = (e.target as HTMLElement).previousElementSibling
      ?.querySelector('.pack-page__grid') as HTMLElement | null;
    if (!gridEl) return;
    const startH = gridEl.offsetHeight;
    resizeRef.current = { rowIdx, startY: e.clientY, startH, gridEl };

    const onMouseMove = (ev: MouseEvent) => {
      if (!resizeRef.current) return;
      const delta = ev.clientY - resizeRef.current.startY;
      const newH = Math.max(MIN_ROW_HEIGHT, Math.min(MAX_ROW_HEIGHT, resizeRef.current.startH + delta));
      resizeRef.current.gridEl.style.height = `${newH}px`;
    };

    const onMouseUp = (ev: MouseEvent) => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      if (!resizeRef.current) return;
      const delta = ev.clientY - resizeRef.current.startY;
      const finalH = Math.max(MIN_ROW_HEIGHT, Math.min(MAX_ROW_HEIGHT, resizeRef.current.startH + delta));
      const idx = resizeRef.current.rowIdx;
      resizeRef.current = null;
      setRowHeights(prev => {
        const next = [...prev];
        while (next.length <= idx) next.push(DEFAULT_ROW_HEIGHT);
        next[idx] = finalH;
        return next;
      });
      markDirty();
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  }, [markDirty]);

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

  // All resolved configs
  const allResolvedWidgets = useMemo(() => {
    return packWidgets
      .map((ref) => resolvedWidgets[`${ref.row}-${ref.col}`])
      .filter((c): c is WidgetConfig => !!c);
  }, [packWidgets, resolvedWidgets]);

  const getWidgetTitle = (ref: PackWidgetRef) => {
    if (ref.title_override) return ref.title_override;
    const resolved = resolvedWidgets[`${ref.row}-${ref.col}`];
    return resolved?.title || ref.widget_id;
  };

  const removeMCPTile = useCallback(
    (tileId: string) => {
      setPack((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          mcp_tiles: (prev.mcp_tiles || []).filter((t) => t.tile_id !== tileId),
        };
      });
      setDirty(true);
    },
    [],
  );

  const updateMCPTileTitle = useCallback(
    (tileId: string, title: string) => {
      setPack((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          mcp_tiles: (prev.mcp_tiles || []).map((t) =>
            t.tile_id === tileId ? { ...t, title_override: title } : t,
          ),
        };
      });
      setDirty(true);
    },
    [],
  );

  return {
    pack,
    loading,
    error,
    packWidgets,
    rowColumns,
    rowHeights,
    rowDescriptions,
    resolvedWidgets,
    targetCell,
    pickedEntity,
    dragOverCell,
    saving,
    dirty,
    editingTitle,
    isOwner,
    widgetMap,
    allResolvedWidgets,
    pickerRef,
    dragSource,
    addRow,
    removeRow,
    addColumn,
    removeColumn,
    setRowDescription,
    setWidgetTitle,
    addWidgetToCell,
    removeWidget,
    moveWidget,
    handleDragStart,
    handleDragEnd,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    handleResizeMouseDown,
    handleCellClick,
    handleSave,
    markDirty,
    markClean,
    setTargetCell,
    setPickedEntity,
    setEditingTitle,
    setDragOverCell,
    getWidgetTitle,
    removeMCPTile,
    updateMCPTileTitle,
  };
}
