import { useState, useMemo, useCallback } from "react";
import type { ColDef } from "ag-grid-community";
import type { ContextMenuConfig } from "../components/ag-grid/AppGrid";

const STORAGE_PREFIX = "goldmine:grid-columns:";

interface UseGridColumnManagerOptions<T> {
  gridId: string;
  allColumns: ColDef<T>[];
  defaultVisibleFields: string[];
}

interface UseGridColumnManagerResult<T> {
  columnDefs: ColDef<T>[];
  contextMenuConfig: ContextMenuConfig;
}

function loadVisibleFields(gridId: string): string[] | null {
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + gridId);
    if (raw) return JSON.parse(raw) as string[];
  } catch {
    // ignore
  }
  return null;
}

function saveVisibleFields(gridId: string, fields: string[]): void {
  try {
    localStorage.setItem(STORAGE_PREFIX + gridId, JSON.stringify(fields));
  } catch {
    // ignore
  }
}

function setsEqual(a: Set<string>, b: Set<string>): boolean {
  if (a.size !== b.size) return false;
  for (const v of a) {
    if (!b.has(v)) return false;
  }
  return true;
}

export function useGridColumnManager<T>({
  gridId,
  allColumns,
  defaultVisibleFields,
}: UseGridColumnManagerOptions<T>): UseGridColumnManagerResult<T> {
  // The "saved" state is what's persisted in localStorage (or defaults if nothing saved).
  // This is the baseline we compare against for isDirty.
  const [savedFields, setSavedFields] = useState<Set<string>>(() => {
    const saved = loadVisibleFields(gridId);
    if (saved && saved.length > 0) return new Set(saved);
    return new Set(defaultVisibleFields);
  });

  // The "working" state is what the user currently sees — changes are provisional
  // until explicitly saved via the AppGrid save bar.
  const [visibleFields, setVisibleFields] = useState<Set<string>>(
    () => new Set(savedFields)
  );

  const isDirty = useMemo(
    () => !setsEqual(visibleFields, savedFields),
    [visibleFields, savedFields]
  );

  const save = useCallback(() => {
    saveVisibleFields(gridId, Array.from(visibleFields));
    setSavedFields(new Set(visibleFields));
  }, [gridId, visibleFields]);

  const discard = useCallback(() => {
    setVisibleFields(new Set(savedFields));
  }, [savedFields]);

  const handleAddColumn = useCallback((field: string) => {
    setVisibleFields((prev) => {
      const next = new Set(prev);
      next.add(field);
      return next;
    });
  }, []);

  const handleRemoveColumn = useCallback((field: string) => {
    setVisibleFields((prev) => {
      if (prev.size <= 1) return prev;
      const next = new Set(prev);
      next.delete(field);
      return next;
    });
  }, []);

  const columnDefs = useMemo<ColDef<T>[]>(
    () =>
      allColumns.map((col) => {
        const field = col.field ?? col.colId;
        if (!field) return col; // action columns stay as-is
        return { ...col, hide: !visibleFields.has(field) };
      }),
    [allColumns, visibleFields]
  );

  const contextMenuConfig = useMemo<ContextMenuConfig>(() => {
    const hidden: { field: string; headerName: string }[] = [];
    for (const col of allColumns) {
      const field = col.field ?? col.colId;
      if (!field) continue;
      if (!visibleFields.has(field)) {
        const headerName =
          col.headerName ||
          field.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
        hidden.push({ field, headerName });
      }
    }
    return {
      hiddenColumns: hidden,
      onAddColumn: handleAddColumn,
      onRemoveColumn: handleRemoveColumn,
      visibleCount: visibleFields.size,
      isDirty,
      onSave: save,
      onDiscard: discard,
    };
  }, [allColumns, visibleFields, handleAddColumn, handleRemoveColumn, isDirty, save, discard]);

  return { columnDefs, contextMenuConfig };
}
