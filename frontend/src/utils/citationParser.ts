export type CitationType = "transcript" | "estimate" | "filing" | "financial" | "alt_data" | "unknown";

export interface ParsedCitation {
  raw: string;
  ticker: string;
  citationType: CitationType;

  // Transcript/filing/financial citations
  docType: string;
  period: string;
  section: string;

  // Estimate citations
  source: string | null;        // consensus|buyside|internal|sellside
  firm: string | null;          // Goldman Sachs, Tiger Global, etc.
  analystName: string | null;   // Alex Rivera, James Wei, etc.
  estimatePeriod: string | null; // 2026A, 2026Q1, etc.
  asOfDate: string | null;      // as of 2026-03-21
}

/**
 * Matches citation patterns with 3 or 4 pipe-separated segments.
 * Supports tickers with dots: BRK.B, BF.B.
 */
export const CITATION_REGEX =
  /\[([A-Z]{1,5}(?:\.[A-Z])?)\s*\|\s*([^|\]]+?)\s*\|\s*([^|\]]+?)(?:\s*\|\s*([^|\]]+?))?\s*\]/;

const BUYSIDE_FIRMS = [
  "Tiger Global", "Coatue", "D1 Capital", "Viking Global", "Lone Pine",
];

const KNOWN_FIRMS = [
  ...BUYSIDE_FIRMS,
  "Goldman Sachs", "Morgan Stanley", "JPMorgan", "Bank of America", "Jefferies",
];

function firmToSource(firm: string): "buyside" | "sellside" {
  return BUYSIDE_FIRMS.some((f) => firm.includes(f)) ? "buyside" : "sellside";
}

function detectCitationType(segment2: string): CitationType {
  const s = segment2.toLowerCase().trim();
  if (s === "consensus" || s === "internal") return "estimate";
  if (KNOWN_FIRMS.some((f) => segment2.includes(f))) return "estimate";
  if (s.includes("transcript")) return "transcript";
  if (["10-k", "10-q", "8-k"].some((t) => s.includes(t))) return "filing";
  if (["income statement", "balance sheet", "cash flow", "financials"].includes(s)) return "financial";
  if (s === "alt data") return "alt_data";
  return "unknown";
}

export function parseSingleCitation(text: string): ParsedCitation | null {
  const m = text.match(CITATION_REGEX);
  if (!m) return null;

  const ticker = m[1].trim();
  const seg2 = m[2].trim();
  const seg3 = m[3].trim();
  const seg4 = m[4]?.trim() ?? "";
  const citationType = detectCitationType(seg2);

  if (citationType === "estimate") {
    const s2lower = seg2.toLowerCase();
    if (s2lower === "consensus") {
      return {
        raw: m[0], ticker, citationType, docType: seg2, period: seg3, section: seg4,
        source: "consensus", firm: null, analystName: null,
        estimatePeriod: seg3, asOfDate: seg4 || null,
      };
    }
    if (s2lower === "internal") {
      return {
        raw: m[0], ticker, citationType, docType: seg2, period: seg3, section: seg4,
        source: "internal", firm: null, analystName: seg3,
        estimatePeriod: seg4 || null, asOfDate: null,
      };
    }
    // Buyside or sellside firm
    return {
      raw: m[0], ticker, citationType, docType: seg2, period: seg3, section: seg4,
      source: firmToSource(seg2), firm: seg2, analystName: seg3,
      estimatePeriod: seg4 || null, asOfDate: null,
    };
  }

  return {
    raw: m[0], ticker, citationType, docType: seg2, period: seg3, section: seg4,
    source: null, firm: null, analystName: null, estimatePeriod: null, asOfDate: null,
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

export function citationToRoute(citation: ParsedCitation): string {
  if (citation.citationType === "estimate") return "estimates";
  if (citation.citationType === "transcript") return "transcripts";
  if (citation.citationType === "filing") return "filings";
  if (citation.citationType === "financial") return "financials";
  if (citation.citationType === "alt_data") return "alt-data";
  return "unknown";
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
