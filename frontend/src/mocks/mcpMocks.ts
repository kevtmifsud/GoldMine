export interface McpNamespace {
  namespace: string;
  display_name: string;
  description: string;
  tool_count: number;
}

export interface McpToolParameter {
  name: string;
  type: string;
  description: string;
  required: boolean;
  enum?: string[];
}

export interface McpChartConfig {
  type: string;
  x_column: string;
  y_column: string;
  series_column: string;
}

export interface McpTool {
  name: string;
  namespace: string;
  full_name: string;
  description: string;
  parameters: McpToolParameter[];
  preferred_presentation: "table" | "chart";
  chart_config: McpChartConfig | null;
}

export interface McpExecuteResult {
  rows: Record<string, unknown>[];
  row_count: number;
  columns: string[];
  preferred_presentation: "table" | "chart";
  chart_config: McpChartConfig | null;
}

export const mockNamespaces: McpNamespace[] = [
  {
    namespace: "estimates",
    display_name: "Estimates",
    description: "Forward estimates from all sources — consensus, buyside, internal, sellside.",
    tool_count: 2,
  },
  {
    namespace: "altdata",
    display_name: "Alternative Data",
    description: "Credit card, foot traffic, app downloads, web traffic signals.",
    tool_count: 2,
  },
];

export const mockTools: Record<string, McpTool[]> = {
  estimates: [
    {
      name: "get_estimates",
      namespace: "estimates",
      full_name: "estimates__get_estimates",
      description:
        "Get forward estimates for a ticker from all sources — consensus, buyside, internal, and sellside. Returns current estimates as of today.",
      parameters: [
        {
          name: "ticker",
          type: "string",
          description: "Stock ticker symbol",
          required: true,
        },
        {
          name: "metric",
          type: "string",
          description: "Metric to retrieve",
          required: true,
          enum: [
            "total_revenue",
            "diluted_eps",
            "ebitda",
            "gross_profit",
            "operating_income",
            "free_cash_flow",
          ],
        },
        {
          name: "period",
          type: "string",
          description:
            "Fiscal period e.g. 2026Q1, 2026A. Leave empty for all periods.",
          required: false,
        },
      ],
      preferred_presentation: "chart",
      chart_config: {
        type: "line",
        x_column: "as_of_date",
        y_column: "value",
        series_column: "source",
      },
    },
  ],
  altdata: [
    {
      name: "get_alt_data",
      namespace: "altdata",
      full_name: "altdata__get_alt_data",
      description:
        "Get alternative data signals. Available for CMG, DPZ, SBUX. Signals: credit card transactions, foot traffic, app downloads, web traffic, reservations, job postings.",
      parameters: [
        {
          name: "ticker",
          type: "string",
          description: "CMG, DPZ, or SBUX",
          required: true,
          enum: ["CMG", "DPZ", "SBUX"],
        },
        {
          name: "data_types",
          type: "array",
          description: "Signal types to retrieve. Empty = all signals.",
          required: false,
        },
        {
          name: "limit",
          type: "number",
          description: "Max rows per signal. Default 30.",
          required: false,
        },
      ],
      preferred_presentation: "chart",
      chart_config: {
        type: "line",
        x_column: "date",
        y_column: "growth",
        series_column: "data_type",
      },
    },
  ],
};

export const mockExecuteResults: Record<string, McpExecuteResult> = {
  estimates__get_estimates: {
    rows: [
      { as_of_date: "2026-01-15", value: 124500, source: "consensus", ticker: "AAPL", metric: "total_revenue" },
      { as_of_date: "2026-01-15", value: 126000, source: "internal", ticker: "AAPL", metric: "total_revenue" },
      { as_of_date: "2026-01-15", value: 123800, source: "buyside", ticker: "AAPL", metric: "total_revenue" },
      { as_of_date: "2026-02-01", value: 125200, source: "consensus", ticker: "AAPL", metric: "total_revenue" },
      { as_of_date: "2026-02-01", value: 126500, source: "internal", ticker: "AAPL", metric: "total_revenue" },
    ],
    row_count: 5,
    columns: ["as_of_date", "value", "source", "ticker", "metric"],
    preferred_presentation: "chart",
    chart_config: {
      type: "line",
      x_column: "as_of_date",
      y_column: "value",
      series_column: "source",
    },
  },
  altdata__get_alt_data: {
    rows: [
      { date: "2026-03-01", growth: 0.12, data_type: "credit_card", ticker: "CMG" },
      { date: "2026-03-01", growth: 0.08, data_type: "foot_traffic", ticker: "CMG" },
      { date: "2026-03-15", growth: 0.15, data_type: "credit_card", ticker: "CMG" },
      { date: "2026-03-15", growth: 0.09, data_type: "foot_traffic", ticker: "CMG" },
    ],
    row_count: 4,
    columns: ["date", "growth", "data_type", "ticker"],
    preferred_presentation: "chart",
    chart_config: {
      type: "line",
      x_column: "date",
      y_column: "growth",
      series_column: "data_type",
    },
  },
};
