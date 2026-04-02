import { useCallback } from "react";
import type { ParsedCitation } from "../../utils/citationParser";

interface CitationLinkProps {
  citation: ParsedCitation;
  onClick: (citation: ParsedCitation) => void;
}

function getCitationLabel(citation: ParsedCitation): string {
  if (citation.citationType === "estimate") {
    if (citation.source === "consensus") {
      return `${citation.ticker} · Consensus · ${citation.estimatePeriod ?? ""}`;
    }
    if (citation.source === "internal") {
      return `${citation.ticker} · Internal · ${citation.analystName ?? ""} · ${citation.estimatePeriod ?? ""}`;
    }
    const firm = citation.firm ?? "";
    const analyst = citation.analystName ?? "";
    const period = citation.estimatePeriod ?? "";
    if (analyst) return `${citation.ticker} · ${firm} · ${analyst} · ${period}`;
    return `${citation.ticker} · ${firm} · ${period}`;
  }
  // Transcript / filing / financial / unknown
  return `${citation.ticker} · ${citation.section || citation.period}`;
}

function DocumentIcon() {
  return (
    <svg className="chat-citation__icon" width="14" height="14" viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
      <polyline points="10 9 9 9 8 9" />
    </svg>
  );
}

/** Citation types for structured database data — these link nowhere useful. */
const SUPPRESSED_TYPES = new Set(["estimate", "financial", "alt_data", "unknown"]);

export function CitationLink({ citation, onClick }: CitationLinkProps) {
  // Suppress citations for structured data — they add visual clutter
  // with no actionable link. The source is shown inline in tables.
  if (SUPPRESSED_TYPES.has(citation.citationType)) {
    return null;
  }

  const label = getCitationLabel(citation);

  const handleClick = useCallback(() => {
    onClick(citation);
  }, [citation, onClick]);

  return (
    <button
      className="chat-citation"
      onClick={handleClick}
      title={label}
    >
      <DocumentIcon />
      <span className="chat-citation__text">{label}</span>
    </button>
  );
}
