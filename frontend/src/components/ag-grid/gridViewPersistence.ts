import type { ColumnState, GridApi } from "ag-grid-community";

const STORAGE_PREFIX = "goldmine:grid-view:";

interface GridViewState {
  columnState: ColumnState[];
  filterModel: Record<string, unknown>;
}

/**
 * Save the current column state and filter model for a grid.
 * The key is grid-type scoped (not entity-scoped) so it propagates across all
 * stock detail pages.
 *
 * IMPORTANT: Columns using valueGetter without a field must have an explicit
 * `colId` for state to be matched correctly on restore.
 */
export function saveGridView(key: string, api: GridApi): void {
  const state: GridViewState = {
    columnState: api.getColumnState(),
    filterModel: api.getFilterModel() ?? {},
  };
  localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(state));
}

/**
 * Restore a previously saved column state and filter model.
 * Returns true if a saved state was found and applied, false otherwise.
 */
export function restoreGridView(key: string, api: GridApi): boolean {
  const raw = localStorage.getItem(STORAGE_PREFIX + key);
  if (!raw) return false;
  try {
    const saved = JSON.parse(raw) as GridViewState;
    api.applyColumnState({ state: saved.columnState, applyOrder: true });
    if (saved.filterModel && Object.keys(saved.filterModel).length > 0) {
      api.setFilterModel(saved.filterModel);
    }
    return true;
  } catch {
    return false;
  }
}

/** Remove the saved view state for a grid. */
export function clearGridView(key: string): void {
  localStorage.removeItem(STORAGE_PREFIX + key);
}

/** Check whether a saved view state exists for a grid. */
export function hasGridView(key: string): boolean {
  return localStorage.getItem(STORAGE_PREFIX + key) !== null;
}
