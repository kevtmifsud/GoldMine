import { useState } from "react";
import { createPortal } from "react-dom";
import type { ICellRendererParams } from "ag-grid-community";
import { TranscriptViewerDialog } from "../research/TranscriptViewerDialog";

export function TranscriptViewButtonRenderer(params: ICellRendererParams) {
  const [open, setOpen] = useState(false);
  const data = params.data;
  if (!data) return null;

  const symbol = data.symbol as string;
  const year = Number(data.fiscal_year);
  const quarter = Number(data.fiscal_quarter);

  if (!symbol || !year || !quarter) return null;

  return (
    <>
      <button
        className="doc-actions__btn doc-actions__btn--primary"
        onClick={() => setOpen(true)}
      >
        View Transcript
      </button>
      {open &&
        createPortal(
          <TranscriptViewerDialog
            symbol={symbol}
            year={year}
            quarter={quarter}
            onClose={() => setOpen(false)}
          />,
          document.body,
        )}
    </>
  );
}
