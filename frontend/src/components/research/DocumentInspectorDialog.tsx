import { useEffect, useState, useCallback } from "react";
import type { DocumentListItem } from "../../types/entities";
import api from "../../config/api";
import "../../styles/research.css";

interface DocumentInspectorDialogProps {
  document: DocumentListItem;
  onClose: () => void;
}

export function DocumentInspectorDialog({
  document: doc,
  onClose,
}: DocumentInspectorDialogProps) {
  const [transcriptText, setTranscriptText] = useState<string | null>(null);
  const [transcriptLoading, setTranscriptLoading] = useState(false);

  const fileUrl = `/api/files/${doc.file_id}`;

  // Escape key handler
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  // Fetch transcript text
  useEffect(() => {
    if (doc.doc_type !== "transcript") return;
    setTranscriptLoading(true);
    api
      .get<string>(fileUrl, { responseType: "text" })
      .then((resp) => setTranscriptText(typeof resp.data === "string" ? resp.data : String(resp.data)))
      .catch(() => setTranscriptText("Failed to load transcript."))
      .finally(() => setTranscriptLoading(false));
  }, [doc.doc_type, fileUrl]);

  const handleDownload = useCallback(() => {
    const a = document.createElement("a");
    a.href = fileUrl;
    a.download = doc.filename;
    a.click();
  }, [fileUrl, doc.filename]);

  const renderBody = () => {
    switch (doc.doc_type) {
      case "report":
      case "notes":
        return (
          <iframe
            className="doc-inspector__iframe"
            src={fileUrl}
            title={doc.title}
          />
        );
      case "audio":
        return (
          <div className="doc-inspector__audio">
            <audio controls src={fileUrl}>
              Your browser does not support the audio element.
            </audio>
          </div>
        );
      case "transcript":
        if (transcriptLoading) {
          return (
            <div className="doc-inspector__transcript-loading">
              Loading transcript...
            </div>
          );
        }
        return (
          <pre className="doc-inspector__transcript">
            {transcriptText}
          </pre>
        );
      default:
        return (
          <div className="doc-inspector__no-preview">
            No preview available for this file type. Use the Download button below.
          </div>
        );
    }
  };

  return (
    <div className="doc-inspector__overlay" onClick={onClose}>
      <div className="doc-inspector" onClick={(e) => e.stopPropagation()}>
        <div className="doc-inspector__header">
          <div className="doc-inspector__header-info">
            <h3 className="doc-inspector__title">{doc.title}</h3>
            <div className="doc-inspector__meta">
              <span className={`doc-type-badge doc-type-badge--${["audio", "transcript", "report", "data_export", "notes"].includes(doc.doc_type) ? doc.doc_type : "other"}`}>
                {doc.doc_type.replace("_", " ")}
              </span>
              {doc.date && (
                <span className="doc-inspector__date">{doc.date}</span>
              )}
            </div>
            {doc.description && (
              <div className="doc-inspector__description">{doc.description}</div>
            )}
          </div>
          <button
            className="doc-inspector__close-btn"
            onClick={onClose}
            title="Close"
          >
            &times;
          </button>
        </div>

        <div className="doc-inspector__body">{renderBody()}</div>

        <div className="doc-inspector__footer">
          <button
            className="doc-inspector__footer-btn doc-inspector__footer-btn--download"
            onClick={handleDownload}
          >
            Download
          </button>
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
