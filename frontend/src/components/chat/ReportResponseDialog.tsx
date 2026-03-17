import { useState } from "react";
import { submitBugReport } from "../../config/mode2Api";
import "../../styles/chat.css";

interface ReportResponseDialogProps {
  userQuery: string;
  llmResponse: string;
  conversationId: string | null;
  sessionId: string | null;
  onClose: () => void;
}

const CATEGORIES = [
  { value: "error_no_response", label: "Error - no response" },
  { value: "bad_response", label: "Bad response" },
  { value: "wrong_data", label: "Wrong data / numbers" },
  { value: "missing_sources", label: "Missing sources" },
  { value: "hallucination", label: "Hallucination" },
  { value: "other", label: "Other" },
] as const;

export function ReportResponseDialog({
  userQuery,
  llmResponse,
  conversationId,
  sessionId,
  onClose,
}: ReportResponseDialogProps) {
  const [category, setCategory] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = async () => {
    if (!category) return;
    setSubmitting(true);
    try {
      await submitBugReport({
        conversation_id: conversationId,
        session_id: sessionId,
        category,
        description: description || undefined,
        user_query: userQuery,
        llm_response: llmResponse,
      });
      setSubmitted(true);
    } catch {
      // Still close on error — the report is best-effort
      setSubmitted(true);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="report-dialog__overlay" onClick={onClose}>
      <div className="report-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="report-dialog__header">
          <h3 className="report-dialog__title">Report Response</h3>
          <button className="report-dialog__close" onClick={onClose}>
            &times;
          </button>
        </div>

        {submitted ? (
          <div className="report-dialog__body">
            <div className="report-dialog__success">
              Report submitted. Thank you for helping us improve.
            </div>
            <div className="report-dialog__footer">
              <button className="report-dialog__btn" onClick={onClose}>
                Close
              </button>
            </div>
          </div>
        ) : (
          <div className="report-dialog__body">
            <label className="report-dialog__label">What went wrong?</label>
            <div className="report-dialog__categories">
              {CATEGORIES.map((cat) => (
                <button
                  key={cat.value}
                  className={`report-dialog__cat-btn ${category === cat.value ? "report-dialog__cat-btn--selected" : ""}`}
                  onClick={() => setCategory(cat.value)}
                >
                  {cat.label}
                </button>
              ))}
            </div>

            <label className="report-dialog__label">
              Details (optional)
            </label>
            <textarea
              className="report-dialog__textarea"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What did you expect instead?"
              rows={3}
            />

            <div className="report-dialog__context">
              <span className="report-dialog__context-label">Your query:</span>
              <span className="report-dialog__context-text">
                {userQuery.length > 120
                  ? userQuery.slice(0, 120) + "..."
                  : userQuery}
              </span>
            </div>

            <div className="report-dialog__footer">
              <button
                className="report-dialog__btn report-dialog__btn--cancel"
                onClick={onClose}
              >
                Cancel
              </button>
              <button
                className="report-dialog__btn report-dialog__btn--submit"
                onClick={handleSubmit}
                disabled={!category || submitting}
              >
                {submitting ? "Submitting..." : "Submit Report"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
