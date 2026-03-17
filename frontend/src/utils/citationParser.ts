export interface ParsedCitation {
  raw: string;
  ticker: string;
  docType: string;
  period: string;
  section: string;
}

/**
 * Matches citation patterns like [AAPL | Earnings Transcript | Q1 2026 | CFO Remarks]
 * The 'g' flag is intentionally omitted so callers can add it as needed.
 */
export const CITATION_REGEX =
  /\[([A-Z]{1,5})\s*\|\s*([^|\]]+?)\s*\|\s*([^|\]]+?)\s*\|\s*([^|\]]+?)\s*\]/;

export function parseSingleCitation(text: string): ParsedCitation | null {
  const m = text.match(CITATION_REGEX);
  if (!m) return null;
  return {
    raw: m[0],
    ticker: m[1].trim(),
    docType: m[2].trim(),
    period: m[3].trim(),
    section: m[4].trim(),
  };
}

/** Normalize doc type: lowercase + replace underscores with spaces. */
function normalizeDocType(docType: string): string {
  return docType.toLowerCase().replace(/_/g, " ");
}

const DOC_TYPE_ROUTE_MAP: Record<string, string> = {
  "earnings transcript": "transcripts",
  "sec filing": "filings",
  report: "sellside",
  notes: "notes",
  "data export": "data-files",
};

export function documentTypeToRoute(docType: string): string {
  return DOC_TYPE_ROUTE_MAP[normalizeDocType(docType)] ?? "transcripts";
}

export function parseFiscalPeriod(
  period: string
): { year: number; quarter: number } | null {
  const m = period.match(/Q(\d)[_ ](\d{4})/i);
  if (!m) return null;
  return { quarter: parseInt(m[1], 10), year: parseInt(m[2], 10) };
}

const FINANCIAL_DATA_TYPES = new Set([
  "10-q filing",
  "10-k filing",
  "income statement",
  "balance sheet",
  "cash flow",
]);

export function isFinancialData(docType: string): boolean {
  return FINANCIAL_DATA_TYPES.has(normalizeDocType(docType));
}

const DOC_TYPE_TO_STATEMENT: Record<string, "income-statement" | "balance-sheet" | "cash-flow"> = {
  "income statement": "income-statement",
  "10-q filing": "income-statement",
  "10-k filing": "income-statement",
  "balance sheet": "balance-sheet",
  "cash flow": "cash-flow",
};

export function docTypeToStatementType(
  docType: string
): "income-statement" | "balance-sheet" | "cash-flow" {
  return DOC_TYPE_TO_STATEMENT[normalizeDocType(docType)] ?? "income-statement";
}

export function isInlineViewable(docType: string): boolean {
  const norm = normalizeDocType(docType);
  return norm === "earnings transcript" || isFinancialData(docType);
}
