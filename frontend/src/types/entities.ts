export interface EntityCandidate {
  entity_type: string;
  entity_id: string;
  display_name: string;
}

export interface EntityResolution {
  resolved: boolean;
  entity_type: string | null;
  entity_id: string | null;
  display_name: string | null;
  message: string | null;
  candidates: EntityCandidate[];
}

export interface EntityField {
  label: string;
  value: string | null;
  format: string; // "currency" | "percent" | "number" | "text"
}

export interface FilterOption {
  value: string;
  label: string;
}

export interface FilterDefinition {
  field: string;
  label: string;
  filter_type: string;
  options: FilterOption[];
}

export interface ChartConfig {
  chart_type: string; // "bar" | "line"
  x_key: string;
  y_key: string;
  x_label: string;
  y_label: string;
  color: string;
}

export interface ColumnConfig {
  key: string;
  label: string;
  format: string;
  sortable: boolean;
  visible: boolean;
}

export interface WidgetConfig {
  widget_id: string;
  title: string;
  endpoint: string;
  columns: ColumnConfig[];
  default_page_size: number;
  widget_type: string;
  chart_config: ChartConfig | null;
  filter_definitions: FilterDefinition[];
  client_filterable_columns: string[];
}

export interface EntityDetail {
  entity_type: string;
  entity_id: string;
  display_name: string;
  header_fields: EntityField[];
  widgets: WidgetConfig[];
}

export interface PaginatedResponse<T = Record<string, unknown>> {
  data: T[];
  page: number;
  page_size: number;
  total_records: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}
