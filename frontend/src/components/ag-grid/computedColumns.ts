import type { ColDef, ValueFormatterParams, ValueGetterParams } from "ag-grid-community";
import type { ColumnFormatConfig } from "./gridCustomizations";
import { buildCustomFormatter } from "./gridCustomizations";
import { parseExpression, evaluate } from "./formulaEngine";
import type { ASTNode } from "./formulaEngine";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ComputedColumnDef {
  id: string; // "computed_<8-char-uuid>" — used as colId + field
  name: string; // display headerName
  expression: string; // e.g. "{current_price} / {52w_high} * 100"
  format?: ColumnFormatConfig; // reuses existing type from gridCustomizations.ts
  createdAt: number; // for stable ordering
}

// ---------------------------------------------------------------------------
// localStorage CRUD
// ---------------------------------------------------------------------------

const STORAGE_PREFIX = "goldmine:grid-computed:";

export function loadComputedColumns(viewKey: string): ComputedColumnDef[] {
  const raw = localStorage.getItem(STORAGE_PREFIX + viewKey);
  if (!raw) return [];
  try {
    return JSON.parse(raw) as ComputedColumnDef[];
  } catch {
    return [];
  }
}

export function saveComputedColumns(
  viewKey: string,
  columns: ComputedColumnDef[],
): void {
  if (columns.length === 0) {
    localStorage.removeItem(STORAGE_PREFIX + viewKey);
  } else {
    localStorage.setItem(STORAGE_PREFIX + viewKey, JSON.stringify(columns));
  }
}

// ---------------------------------------------------------------------------
// Generate unique ID
// ---------------------------------------------------------------------------

export function generateComputedId(): string {
  const hex = Math.random().toString(16).slice(2, 10);
  return `computed_${hex}`;
}

// ---------------------------------------------------------------------------
// Build AG Grid ColDefs from computed column definitions
// ---------------------------------------------------------------------------

export function buildComputedColDefs(columns: ComputedColumnDef[]): ColDef[] {
  return columns.map((col) => {
    // Parse expression once — captured in closure
    let ast: ASTNode | null = null;
    try {
      ast = parseExpression(col.expression);
    } catch {
      // Invalid formula — valueGetter will return null
    }

    const colDef: ColDef = {
      colId: col.id,
      headerName: col.name,
      valueGetter: (params: ValueGetterParams) => {
        if (!ast || !params.data) return null;
        try {
          return evaluate(ast, params.data as Record<string, unknown>);
        } catch {
          return null;
        }
      },
      sortable: true,
      filter: "agTextColumnFilter",
      floatingFilter: true,
    };

    if (col.format) {
      if (col.format.isPercent) {
        // For computed columns, Percent format means ×100 then append "%"
        // (standard convention: 0.27 → "27.00%"). Regular columns use the
        // non-scaled buildCustomFormatter via the context menu instead.
        const baseConfig: ColumnFormatConfig = { ...col.format, isPercent: false };
        const baseFmt = buildCustomFormatter(baseConfig);
        colDef.valueFormatter = (params: ValueFormatterParams) => {
          const v = params.value;
          if (v === null || v === undefined || v === "") return "\u2014";
          const num = typeof v === "number" ? v : parseFloat(String(v));
          if (isNaN(num)) return String(v);
          return baseFmt({ ...params, value: num * 100 } as ValueFormatterParams) + "%";
        };
      } else {
        colDef.valueFormatter = buildCustomFormatter(col.format);
      }
      colDef.filter = "agNumberColumnFilter";
    }

    return colDef;
  });
}
