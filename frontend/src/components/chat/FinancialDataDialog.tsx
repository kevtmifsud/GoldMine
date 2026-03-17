import { useEffect } from "react";
import { FinancialTable } from "../FinancialTable";
import "../../styles/research.css";

interface FinancialDataDialogProps {
  ticker: string;
  statementType: "income-statement" | "balance-sheet" | "cash-flow";
  onClose: () => void;
}

const STATEMENT_LABELS: Record<string, string> = {
  "income-statement": "Income Statement",
  "balance-sheet": "Balance Sheet",
  "cash-flow": "Cash Flow",
};

export function FinancialDataDialog({
  ticker,
  statementType,
  onClose,
}: FinancialDataDialogProps) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div className="doc-inspector__overlay" onClick={onClose}>
      <div className="doc-inspector" onClick={(e) => e.stopPropagation()}>
        <div className="doc-inspector__header">
          <div className="doc-inspector__header-info">
            <h3 className="doc-inspector__title">
              {ticker} {STATEMENT_LABELS[statementType] ?? statementType}
            </h3>
            <div className="doc-inspector__meta">
              <span className="doc-type-badge doc-type-badge--data_export">
                financials
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
          <FinancialTable ticker={ticker} statementType={statementType} />
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
