import { useEffect, useState } from "react";
import api from "../../config/api";
import "../../styles/research.css";

interface TranscriptViewerDialogProps {
  symbol: string;
  year: number;
  quarter: number;
  onClose: () => void;
}

export function TranscriptViewerDialog({
  symbol,
  year,
  quarter,
  onClose,
}: TranscriptViewerDialogProps) {
  const [text, setText] = useState<string | null>(null);
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
    api
      .get<string>(`/api/transcripts/${symbol}/${year}/${quarter}`, {
        responseType: "text",
      })
      .then((resp) =>
        setText(typeof resp.data === "string" ? resp.data : String(resp.data))
      )
      .catch(() => setText("Failed to load transcript."))
      .finally(() => setLoading(false));
  }, [symbol, year, quarter]);

  return (
    <div className="doc-inspector__overlay" onClick={onClose}>
      <div className="doc-inspector" onClick={(e) => e.stopPropagation()}>
        <div className="doc-inspector__header">
          <div className="doc-inspector__header-info">
            <h3 className="doc-inspector__title">
              {symbol} Q{quarter} {year} Earnings Call Transcript
            </h3>
            <div className="doc-inspector__meta">
              <span className="doc-type-badge doc-type-badge--transcript">
                transcript
              </span>
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
          {loading ? (
            <div className="doc-inspector__transcript-loading">
              Loading transcript...
            </div>
          ) : (
            <pre className="doc-inspector__transcript">{text}</pre>
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
