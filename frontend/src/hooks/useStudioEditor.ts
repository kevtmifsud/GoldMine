import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import type {
  Studio,
  StudioWidget,
  ChatMessage,
} from "../types/studio";
import * as studiosApi from "../config/studiosApi";

const MAX_ROWS = 15;
const MAX_COLS = 3;
const DEFAULT_ROW_HEIGHT = 280;
const MIN_ROW_HEIGHT = 200;
const MAX_ROW_HEIGHT = 800;

export interface StudioEditorState {
  studio: Studio | null;
  loading: boolean;
  error: string | null;
  widgets: StudioWidget[];
  rowColumns: number[];
  rowHeights: number[];
  messages: ChatMessage[];
  chatLoading: boolean;
  saving: boolean;
  dirty: boolean;
  isOwner: boolean;
  widgetMap: Record<string, StudioWidget>;
  dragOverCell: string | null;
  dragSource: React.MutableRefObject<{ row: number; col: number } | null>;
  // Grid operations
  addRow: () => void;
  removeRow: (rowIdx: number) => void;
  addColumn: (rowIdx: number) => void;
  removeColumn: (rowIdx: number) => void;
  removeWidget: (row: number, col: number) => void;
  moveWidget: (fromRow: number, fromCol: number, toRow: number, toCol: number) => void;
  // Drag-and-drop handlers
  handleDragStart: (e: React.DragEvent, row: number, col: number) => void;
  handleDragEnd: (e: React.DragEvent) => void;
  handleDragOver: (e: React.DragEvent, row: number, col: number) => void;
  handleDragLeave: () => void;
  handleDrop: (e: React.DragEvent, toRow: number, toCol: number) => void;
  // Row resize
  handleResizeMouseDown: (rowIdx: number, e: React.MouseEvent) => void;
  // Save
  handleSave: () => void;
  markDirty: () => void;
  updateStudioField: (update: Partial<Studio>) => void;
  // Chat
  sendMessage: (text: string) => void;
  cancelChat: () => void;
}

export function useStudioEditor(
  studioId: string | null,
  username: string | null
): StudioEditorState {
  const [studio, setStudio] = useState<Studio | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [widgets, setWidgets] = useState<StudioWidget[]>([]);
  const [rowColumns, setRowColumns] = useState<number[]>([2]);
  const [rowHeights, setRowHeights] = useState<number[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const [chatLoading, setChatLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  const dragSource = useRef<{ row: number; col: number } | null>(null);
  const [dragOverCell, setDragOverCell] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const resizeRef = useRef<{ rowIdx: number; startY: number; startH: number; gridEl: HTMLElement } | null>(null);

  const isOwner = studio?.owner === username;

  // Load studio
  useEffect(() => {
    if (!studioId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);

    studiosApi
      .getStudio(studioId)
      .then((data) => {
        setStudio(data);
        setWidgets(data.widgets);
        setRowColumns(data.row_columns.length > 0 ? data.row_columns : [2]);
        setRowHeights(data.row_heights ?? []);
        setMessages(data.messages);
      })
      .catch(() => setError("Failed to load studio"))
      .finally(() => setLoading(false));
  }, [studioId]);

  // Widget map
  const widgetMap = useMemo(() => {
    const map: Record<string, StudioWidget> = {};
    for (const w of widgets) {
      map[`${w.row}-${w.col}`] = w;
    }
    return map;
  }, [widgets]);

  const markDirty = () => setDirty(true);

  const updateStudioField = useCallback((update: Partial<Studio>) => {
    setStudio((prev) => prev ? { ...prev, ...update } : prev);
  }, []);

  // Save
  const handleSave = useCallback(async () => {
    if (!studioId || !isOwner) return;
    setSaving(true);
    try {
      const updated = await studiosApi.updateStudio(studioId, {
        widgets,
        row_columns: rowColumns,
        row_heights: rowHeights,
        messages,
      });
      setStudio(updated);
      setDirty(false);
    } catch {
      // silent
    } finally {
      setSaving(false);
    }
  }, [studioId, isOwner, widgets, rowColumns, rowHeights, messages]);

  // Grid mutations
  const addRow = () => {
    if (rowColumns.length >= MAX_ROWS) return;
    setRowColumns((prev) => [...prev, 2]);
    markDirty();
  };

  const removeRow = (rowIdx: number) => {
    if (rowColumns.length <= 1) return;
    setWidgets((prev) =>
      prev
        .filter((w) => w.row !== rowIdx)
        .map((w) => (w.row > rowIdx ? { ...w, row: w.row - 1 } : w))
    );
    setRowColumns((prev) => prev.filter((_, i) => i !== rowIdx));
    setRowHeights((prev) => prev.filter((_, i) => i !== rowIdx));
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
    setWidgets((prev) =>
      prev.filter((w) => !(w.row === rowIdx && w.col >= newCount))
    );
    setRowColumns((prev) =>
      prev.map((v, i) => (i === rowIdx ? newCount : v))
    );
    markDirty();
  };

  const removeWidget = (row: number, col: number) => {
    setWidgets((prev) =>
      prev.filter((w) => !(w.row === row && w.col === col))
    );
    markDirty();
  };

  const moveWidget = (
    fromRow: number,
    fromCol: number,
    toRow: number,
    toCol: number
  ) => {
    if (fromRow === toRow && fromCol === toCol) return;
    const hasSource = widgets.some(
      (w) => w.row === fromRow && w.col === fromCol
    );
    const hasTarget = widgets.some(
      (w) => w.row === toRow && w.col === toCol
    );

    if (hasSource && hasTarget) {
      setWidgets((prev) =>
        prev.map((w) => {
          if (w.row === fromRow && w.col === fromCol)
            return { ...w, row: toRow, col: toCol };
          if (w.row === toRow && w.col === toCol)
            return { ...w, row: fromRow, col: fromCol };
          return w;
        })
      );
    } else if (hasSource) {
      setWidgets((prev) =>
        prev.map((w) =>
          w.row === fromRow && w.col === fromCol
            ? { ...w, row: toRow, col: toCol }
            : w
        )
      );
    }
    markDirty();
  };

  // Row resize
  const handleResizeMouseDown = useCallback((rowIdx: number, e: React.MouseEvent) => {
    e.preventDefault();
    const gridEl = (e.target as HTMLElement).previousElementSibling
      ?.querySelector('.studio-grid__grid') as HTMLElement | null;
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

  // DnD handlers
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
        "studio-grid__cell--dragging"
      );
    });
  };

  const handleDragEnd = (e: React.DragEvent) => {
    dragSource.current = null;
    setDragOverCell(null);
    (e.currentTarget as HTMLElement).classList.remove(
      "studio-grid__cell--dragging"
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

  // Chat
  const sendMessage = useCallback(
    async (text: string) => {
      if (!studioId || !text.trim() || chatLoading) return;

      const userMsg: ChatMessage = { role: "user", content: text.trim() };
      setMessages((prev) => [...prev, userMsg]);
      setChatLoading(true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const conversationHistory = [...messages, userMsg];
        const resp = await studiosApi.chatStudio(
          studioId,
          {
            message: text.trim(),
            conversation_history: conversationHistory,
          },
          controller.signal
        );

        const assistantMsg: ChatMessage = {
          role: "assistant",
          content: resp.reply,
        };
        setMessages((prev) => [...prev, assistantMsg]);
        setWidgets(resp.widgets);
        setRowColumns(resp.row_columns);
        setRowHeights(resp.row_heights ?? []);
        setDirty(true);
      } catch (err: unknown) {
        if (err instanceof Error && err.name === "CanceledError") {
          // User cancelled
        } else {
          const errorMsg: ChatMessage = {
            role: "assistant",
            content: "Sorry, something went wrong. Please try again.",
          };
          setMessages((prev) => [...prev, errorMsg]);
        }
      } finally {
        setChatLoading(false);
        abortRef.current = null;
      }
    },
    [studioId, messages, chatLoading]
  );

  const cancelChat = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
      setChatLoading(false);
    }
  }, []);

  return {
    studio,
    loading,
    error,
    widgets,
    rowColumns,
    rowHeights,
    messages,
    chatLoading,
    saving,
    dirty,
    isOwner,
    widgetMap,
    dragOverCell,
    dragSource,
    addRow,
    removeRow,
    addColumn,
    removeColumn,
    removeWidget,
    moveWidget,
    handleDragStart,
    handleDragEnd,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    handleResizeMouseDown,
    handleSave,
    markDirty,
    updateStudioField,
    sendMessage,
    cancelChat,
  };
}
