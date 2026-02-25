import { useEffect, useMemo, useState } from "react";
import api from "../../config/api";
import "../../styles/research.css";

interface TranscriptViewerDialogProps {
  symbol: string;
  year: number;
  quarter: number;
  onClose: () => void;
}

interface TranscriptParagraph {
  paragraph_number: number;
  speaker: string;
  content: string;
}

/** Assign a stable color to each unique speaker. */
const SPEAKER_COLORS = [
  { bg: "#dbeafe", fg: "#1e40af" }, // blue
  { bg: "#d1fae5", fg: "#065f46" }, // green
  { bg: "#ede9fe", fg: "#5b21b6" }, // purple
  { bg: "#fef3c7", fg: "#92400e" }, // amber
  { bg: "#fce7f3", fg: "#9d174d" }, // pink
  { bg: "#ffedd5", fg: "#9a3412" }, // orange
  { bg: "#ccfbf1", fg: "#115e59" }, // teal
  { bg: "#e0e7ff", fg: "#3730a3" }, // indigo
];

const OPERATOR_COLOR = { bg: "#f1f5f9", fg: "#475569" }; // grey for Operator

function getSpeakerColor(
  speaker: string,
  colorMap: Map<string, { bg: string; fg: string }>
) {
  if (speaker === "Operator") return OPERATOR_COLOR;
  const existing = colorMap.get(speaker);
  if (existing) return existing;
  const idx = colorMap.size % SPEAKER_COLORS.length;
  const color = SPEAKER_COLORS[idx];
  colorMap.set(speaker, color);
  return color;
}

export function TranscriptViewerDialog({
  symbol,
  year,
  quarter,
  onClose,
}: TranscriptViewerDialogProps) {
  const [paragraphs, setParagraphs] = useState<TranscriptParagraph[] | null>(
    null
  );
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  useEffect(() => {
    setLoading(true);
    setError(false);
    api
      .get<TranscriptParagraph[]>(
        `/api/transcripts/${symbol}/${year}/${quarter}`
      )
      .then((resp) => setParagraphs(resp.data))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [symbol, year, quarter]);

  // Build a stable color map from speaker order of appearance
  const speakerColorMap = useMemo(() => {
    const map = new Map<string, { bg: string; fg: string }>();
    if (!paragraphs) return map;
    for (const p of paragraphs) {
      getSpeakerColor(p.speaker, map);
    }
    return map;
  }, [paragraphs]);

  return (
    <div className="doc-inspector__overlay" onClick={onClose}>
      <div className="doc-inspector" onClick={(e) => e.stopPropagation()}>
        <div className="doc-inspector__header">
          <div className="doc-inspector__header-info">
            <h3 className="doc-inspector__title">
              {symbol} Q{quarter} {year} Transcript
            </h3>
            <div className="doc-inspector__meta">
              <span className="doc-type-badge doc-type-badge--transcript">
                transcript
              </span>
              {paragraphs && (
                <span className="doc-inspector__date">
                  {paragraphs.length} paragraphs
                </span>
              )}
            </div>
          </div>
          <button
            className="doc-inspector__close-btn"
            onClick={onClose}
            title="Close"
          >
            &times;
          </button>
        </div>

        <div className="doc-inspector__body">
          {loading && (
            <div className="doc-inspector__transcript-loading">
              Loading transcript...
            </div>
          )}
          {error && (
            <div className="doc-inspector__transcript-loading">
              Failed to load transcript.
            </div>
          )}
          {!loading && !error && paragraphs && (
            <div className="transcript-viewer">
              {paragraphs.map((p, i) => {
                const color = getSpeakerColor(p.speaker, speakerColorMap);
                const prevSpeaker = i > 0 ? paragraphs[i - 1].speaker : null;
                const showSpeaker = p.speaker !== prevSpeaker;

                return (
                  <div
                    key={p.paragraph_number}
                    className={
                      showSpeaker
                        ? "transcript-para transcript-para--new-speaker"
                        : "transcript-para"
                    }
                  >
                    {showSpeaker && (
                      <div className="transcript-speaker">
                        <span
                          className="transcript-speaker__badge"
                          style={{
                            backgroundColor: color.bg,
                            color: color.fg,
                          }}
                        >
                          {p.speaker}
                        </span>
                      </div>
                    )}
                    <div className="transcript-content">{p.content}</div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="doc-inspector__footer">
          <button
            className="doc-inspector__footer-btn doc-inspector__footer-btn--close"
            onClick={onClose}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
