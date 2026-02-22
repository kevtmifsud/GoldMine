import { Link } from "react-router-dom";
import type { ICellRendererParams } from "ag-grid-community";

export function TickerLinkRenderer(params: ICellRendererParams) {
  const value = params.value;
  if (!value) return <span>{"\u2014"}</span>;
  return (
    <Link className="smartlist__link" to={`/entity/stock/${value}`}>
      {String(value)}
    </Link>
  );
}
