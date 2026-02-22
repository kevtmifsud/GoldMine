import { themeQuartz, themeBalham, themeMaterial } from "ag-grid-community";

/**
 * Polished Quartz theme — clean, modern financial look.
 * Navy/gold brand colors, alternating row stripes, compact spacing.
 */
export const gridThemeQuartz = themeQuartz.withParams({
  accentColor: "#d4a843",
  backgroundColor: "#ffffff",
  foregroundColor: "#1a202c",
  borderColor: "#e2e8f0",
  borderRadius: 4,
  headerBackgroundColor: "#f8fafc",
  headerTextColor: "#64748b",
  headerFontSize: 12,
  headerFontWeight: 600,
  headerCellHoverBackgroundColor: "#f1f5f9",
  fontSize: 14,
  oddRowBackgroundColor: "#fafbfc",
  rowHoverColor: "#f1f5f9",
  selectedRowBackgroundColor: "#eff6ff",
  rangeSelectionBorderColor: "#1a365d",
  cellHorizontalPadding: 16,
  spacing: 6,
  wrapperBorderRadius: 0,
  columnBorder: true,
  headerColumnResizeHandleColor: "#cbd5e1",
  headerColumnResizeHandleHeight: "50%",
});

/**
 * Balham theme — tighter, traditional spreadsheet look.
 */
export const gridThemeBalham = themeBalham.withParams({
  accentColor: "#d4a843",
  backgroundColor: "#ffffff",
  foregroundColor: "#1a202c",
  borderColor: "#e2e8f0",
  headerBackgroundColor: "#f1f5f9",
  headerTextColor: "#475569",
  headerFontSize: 11,
  headerFontWeight: 600,
  fontSize: 13,
  oddRowBackgroundColor: "#fafbfc",
  rowHoverColor: "#f1f5f9",
  selectedRowBackgroundColor: "#eff6ff",
  spacing: 4,
  cellHorizontalPadding: 8,
  wrapperBorderRadius: 0,
});

/**
 * Material theme — minimal, Google-inspired.
 */
export const gridThemeMaterial = themeMaterial.withParams({
  accentColor: "#d4a843",
  backgroundColor: "#ffffff",
  foregroundColor: "#1a202c",
  borderColor: "#e2e8f0",
  headerBackgroundColor: "#ffffff",
  headerTextColor: "#64748b",
  headerFontWeight: 500,
  oddRowBackgroundColor: "#fafbfc",
  rowHoverColor: "#f5f5f5",
  selectedRowBackgroundColor: "#fff8e1",
  wrapperBorderRadius: 0,
});

/** Active theme — change this to swap between themes */
export const gridTheme = gridThemeBalham;
