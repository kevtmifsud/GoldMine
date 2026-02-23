import type { EntityField } from "../types/entities";

interface StockSummaryBarProps {
  displayName: string;
  headerFields: EntityField[];
}

function formatValue(value: string | null, format: string): string {
  if (value === null || value === undefined || value === "") return "\u2014";
  switch (format) {
    case "currency": {
      const num = parseFloat(value);
      return isNaN(num)
        ? value
        : `$${num.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    }
    case "percent": {
      const num = parseFloat(value);
      return isNaN(num) ? value : `${num.toFixed(2)}%`;
    }
    case "number": {
      const num = parseFloat(value);
      return isNaN(num) ? value : num.toLocaleString("en-US");
    }
    default:
      return value;
  }
}

export function StockSummaryBar({ displayName, headerFields }: StockSummaryBarProps) {
  return (
    <div className="stock-summary">
      <span className="stock-summary__name">{displayName}</span>
      {headerFields.length > 0 && <span className="stock-summary__divider" />}
      <div className="stock-summary__metrics">
        {headerFields.map((field) => (
          <div key={field.label} className="stock-summary__metric">
            <span className="stock-summary__label">{field.label}</span>
            <span className="stock-summary__value">
              {formatValue(field.value, field.format)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
