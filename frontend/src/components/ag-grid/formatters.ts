import type { ValueFormatterParams } from "ag-grid-community";

export function currencyFormatter(params: ValueFormatterParams): string {
  const value = params.value;
  if (value === null || value === undefined || value === "") return "\u2014";
  const num = parseFloat(String(value));
  return isNaN(num)
    ? String(value)
    : `$${num.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function percentFormatter(params: ValueFormatterParams): string {
  const value = params.value;
  if (value === null || value === undefined || value === "") return "\u2014";
  const num = parseFloat(String(value));
  return isNaN(num) ? String(value) : `${num.toFixed(2)}%`;
}

export function numberFormatter(params: ValueFormatterParams): string {
  const value = params.value;
  if (value === null || value === undefined || value === "") return "\u2014";
  const num = parseFloat(String(value));
  return isNaN(num) ? String(value) : num.toLocaleString("en-US");
}

export function textFormatter(params: ValueFormatterParams): string {
  const value = params.value;
  if (value === null || value === undefined || value === "") return "\u2014";
  return String(value);
}

export function getValueFormatter(format: string) {
  switch (format) {
    case "currency":
      return currencyFormatter;
    case "percent":
      return percentFormatter;
    case "number":
      return numberFormatter;
    default:
      return textFormatter;
  }
}
