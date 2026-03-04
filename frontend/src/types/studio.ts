export interface ChartSeries {
  y_key: string;
  label: string;
  color: string;
}

export interface StudioChartConfig {
  x_key: string;
  y_key: string;
  y_label: string;
  y_format: string | null; // "currency" | "number" | "percent"
  color: string;
  series: ChartSeries[];
}

export interface DataSource {
  type: string; // "financials" | "dataset" | "price_history" | "portfolio_pnl" | "multi_price_indexed" | "multi_financials"
  ticker?: string | null;
  statement_type?: string | null;
  period?: string | null;
  metrics?: string[] | null;
  dataset?: string | null;
  filters?: Record<string, string> | null;
  sort_by?: string | null;
  sort_order?: string | null;
  limit?: number | null;
  portfolio_name?: string | null;
  metric?: string | null;
  tickers?: string[] | null;
  indexed?: boolean;
}

export interface StudioWidget {
  widget_id: string;
  title: string;
  chart_type: string; // "bar" | "line" | "echarts"
  chart_config: StudioChartConfig;
  data_source: DataSource;
  data: Record<string, unknown>[];
  echarts_option?: Record<string, unknown> | null;
  row: number;
  col: number;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface Studio {
  studio_id: string;
  name: string;
  owner: string;
  owner_display_name: string;
  description: string;
  is_shared: boolean;
  widgets: StudioWidget[];
  row_columns: number[];
  row_heights: number[];
  messages: ChatMessage[];
  created_at: string;
  updated_at: string;
}

export interface StudioCreate {
  name: string;
  description: string;
  is_shared: boolean;
}

export interface StudioUpdate {
  name?: string;
  description?: string;
  is_shared?: boolean;
  widgets?: StudioWidget[];
  row_columns?: number[];
  row_heights?: number[];
  messages?: ChatMessage[];
}

export interface StudioChatRequest {
  message: string;
  conversation_history: ChatMessage[];
}

export interface StudioChatResponse {
  reply: string;
  widgets: StudioWidget[];
  row_columns: number[];
  row_heights: number[];
  model: string;
  token_usage: Record<string, number>;
}
