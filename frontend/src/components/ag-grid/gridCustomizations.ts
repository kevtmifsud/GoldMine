import type { ColDef, ValueFormatterParams } from "ag-grid-community";
import {
  currencyFormatter,
  percentFormatter,
  numberFormatter,
} from "./formatters";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ColumnFormatConfig {
  prefix?: string; // e.g. "$", "EUR "
  decimals?: number; // 0-6
  isPercent?: boolean; // append "%"
}

export interface ColumnCustomization {
  rename?: string;
  format?: ColumnFormatConfig;
}

/** Keyed by column field name. */
export type GridCustomizations = Record<string, ColumnCustomization>;

// ---------------------------------------------------------------------------
// Format presets
// ---------------------------------------------------------------------------

export interface FormatPreset {
  label: string;
  config: ColumnFormatConfig;
}

export const FORMAT_PRESETS: FormatPreset[] = [
  { label: "Currency", config: { prefix: "$", decimals: 2, isPercent: false } },
  { label: "Number", config: { prefix: "", decimals: 2, isPercent: false } },
  { label: "Percent", config: { prefix: "", decimals: 2, isPercent: true } },
  { label: "Integer", config: { prefix: "", decimals: 0, isPercent: false } },
];

// ---------------------------------------------------------------------------
// localStorage CRUD
// ---------------------------------------------------------------------------

const STORAGE_PREFIX = "goldmine:grid-custom:";

export function loadCustomizations(viewKey: string): GridCustomizations {
  const raw = localStorage.getItem(STORAGE_PREFIX + viewKey);
  if (!raw) return {};
  try {
    return JSON.parse(raw) as GridCustomizations;
  } catch {
    return {};
  }
}

export function saveCustomizations(
  viewKey: string,
  customs: GridCustomizations,
): void {
  // Clean out empty entries before saving
  const cleaned: GridCustomizations = {};
  for (const [field, c] of Object.entries(customs)) {
    if (c.rename || c.format) {
      cleaned[field] = c;
    }
  }
  if (Object.keys(cleaned).length === 0) {
    localStorage.removeItem(STORAGE_PREFIX + viewKey);
  } else {
    localStorage.setItem(STORAGE_PREFIX + viewKey, JSON.stringify(cleaned));
  }
}

// ---------------------------------------------------------------------------
// Column helpers
// ---------------------------------------------------------------------------

/** Known numeric formatter function references */
const NUMERIC_FORMATTERS = new Set([
  currencyFormatter,
  percentFormatter,
  numberFormatter,
]);

export function isNumericColumn(colDef: ColDef): boolean {
  if (colDef.filter === "agNumberColumnFilter") return true;
  // AG Grid's built-in `type` can be a string or string[]
  const colType = colDef.type;
  if (colType) {
    const types = Array.isArray(colType) ? colType : [colType];
    if (types.includes("numericColumn")) return true;
  }
  if (
    typeof colDef.valueFormatter === "function" &&
    NUMERIC_FORMATTERS.has(colDef.valueFormatter as never)
  ) {
    return true;
  }
  return false;
}

export function hasRendererColumn(colDef: ColDef): boolean {
  return !!colDef.cellRenderer;
}

// ---------------------------------------------------------------------------
// Custom formatter builder
// ---------------------------------------------------------------------------

export function buildCustomFormatter(
  config: ColumnFormatConfig,
): (params: ValueFormatterParams) => string {
  return (params: ValueFormatterParams): string => {
    const value = params.value;
    if (value === null || value === undefined || value === "") return "\u2014";
    const num = parseFloat(String(value));
    if (isNaN(num)) return String(value);

    const decimals = config.decimals ?? 2;
    const prefix = config.prefix ?? "";

    const formatted = num.toLocaleString("en-US", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });

    const suffix = config.isPercent ? "%" : "";
    return `${prefix}${formatted}${suffix}`;
  };
}

// ---------------------------------------------------------------------------
// Apply customizations to column defs
// ---------------------------------------------------------------------------

/**
 * Returns a new ColDef[] with headerName and valueFormatter overrides applied.
 * Skips valueFormatter override for columns that have a cellRenderer.
 */
export function applyCustomizations(
  columnDefs: ColDef[],
  customs: GridCustomizations,
): ColDef[] {
  if (!customs || Object.keys(customs).length === 0) return columnDefs;

  return columnDefs.map((colDef) => {
    const field = colDef.field;
    if (!field) return colDef;

    const custom = customs[field];
    if (!custom) return colDef;

    const patched = { ...colDef };

    if (custom.rename) {
      patched.headerName = custom.rename;
    }

    if (custom.format && !hasRendererColumn(colDef)) {
      patched.valueFormatter = buildCustomFormatter(custom.format);
    }

    return patched;
  });
}
