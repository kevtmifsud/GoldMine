export interface FinancialLineItem {
  metric: string;
  label: string;
  values: Record<string, number | null>;
  yoy: Record<string, number | null>;
  indent: number;
  is_header: boolean;
  format_type: "currency" | "percent" | "per_share" | "count";
}

export interface FinancialStatementResponse {
  ticker: string;
  statement_type: string;
  period: string;
  dates: string[];
  line_items: FinancialLineItem[];
  fy_end_month: number;
}

export interface SummaryMetric {
  metric: string;
  label: string;
  section: string;
  values: Record<string, number | null>;
  yoy: Record<string, number | null>;
  qoq: Record<string, number | null>;
  format_type: "currency" | "percent" | "per_share" | "count";
}

export interface FinancialSummaryResponse {
  ticker: string;
  period: string;
  dates: string[];
  metrics: SummaryMetric[];
  fy_end_month: number;
}
