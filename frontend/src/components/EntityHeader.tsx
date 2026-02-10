import type { EntityField } from "../types/entities";
import "../styles/entity.css";

interface EntityHeaderProps {
  displayName: string;
  entityType: string;
  headerFields: EntityField[];
}

export function EntityHeader({
  displayName,
  entityType,
  headerFields,
}: EntityHeaderProps) {
  const formatValue = (value: string | null, format: string): string => {
    if (value === null || value === undefined || value === "") return "—";
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
  };

  return (
    <div className="entity-header">
      <div className="entity-header__top">
        <h2 className="entity-header__name">{displayName}</h2>
        <span className={`entity-header__badge entity-header__badge--${entityType}`}>
          {entityType}
        </span>
      </div>
      <div className="entity-header__fields">
        {headerFields.map((field) => (
          <div key={field.label} className="entity-header__field">
            <span className="entity-header__label">{field.label}</span>
            <span className="entity-header__value">
              {formatValue(field.value, field.format)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
