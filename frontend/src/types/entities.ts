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

export interface SecondaryLine {
  y_key: string;
  y_key_alt: string | null;
  label: string;
  label_alt: string | null;
  color: string;
}

export interface BarConfig {
  y_key: string;
  y_key_alt: string | null;
  label: string;
  color: string;
}

export interface ChartConfig {
  chart_type: string; // "bar" | "line"
  x_key: string;
  y_key: string;
  x_label: string;
  y_label: string;
  color: string;
  y_format: string | null; // "currency" | "number" | null
  y_key_alt: string | null;
  y_label_alt: string | null;
  y_format_alt: string | null;
  color_key: string | null;
  bars: BarConfig[];
  stacked: boolean;
  secondary_y_label: string | null;
  secondary_y_label_alt: string | null;
  secondary_lines: SecondaryLine[];
}

export interface ColumnConfig {
  key: string;
  label: string;
  format: string;
  sortable: boolean;
  visible: boolean;
  entity_type?: string;      // e.g. "stock", "person", "portfolio"
  entity_id_field?: string;  // when display value != entity ID (e.g. name → person_id)
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
  full_width: boolean;
  has_overrides: boolean;
  initial_filters: Record<string, string>;
  initial_sort_by: string | null;
  initial_sort_order: string | null;
  initial_column_filters: Record<string, unknown> | null;
}

export interface EntityDetail {
  entity_type: string;
  entity_id: string;
  display_name: string;
  header_fields: EntityField[];
  widgets: WidgetConfig[];
  active_view_id: string | null;
  active_view_name: string | null;
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

// --- Views & Packs ---

export interface WidgetStateOverride {
  widget_id: string;
  server_filters: Record<string, string>;
  sort_by: string | null;
  sort_order: string | null;
  visible_columns: string[] | null;
  page_size: number | null;
  column_filters: Record<string, unknown> | null;
}

export interface SavedView {
  view_id: string;
  name: string;
  owner: string;
  entity_type: string;
  entity_id: string;
  widget_overrides: WidgetStateOverride[];
  is_shared: boolean;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface SavedViewCreate {
  name: string;
  entity_type: string;
  entity_id: string;
  widget_overrides: WidgetStateOverride[];
  is_shared: boolean;
  is_default?: boolean;
}

export interface SavedViewUpdate {
  name?: string;
  widget_overrides?: WidgetStateOverride[];
  is_shared?: boolean;
}

export interface PackWidgetRef {
  source_entity_type: string;
  source_entity_id: string;
  widget_id: string;
  title_override: string | null;
  overrides: WidgetStateOverride | null;
  row: number;
  col: number;
}

export interface MCPTileRef {
  tile_id: string;
  title: string;
  tool: string;
  params: Record<string, unknown>;
  display_type: "ag_grid" | "plotly_line" | "plotly_bar" | "plotly_scatter" | "number_card";
  chart_config?: Record<string, unknown> | null;
  grid_config?: Record<string, unknown> | null;
  state_override?: Record<string, unknown> | null;
  is_template: boolean;
  row: number;
  col: number;
  title_override?: string | null;
}

export interface AnalystPack {
  pack_id: string;
  name: string;
  owner: string;
  owner_display_name: string;
  description: string;
  widgets: PackWidgetRef[];
  mcp_tiles: MCPTileRef[];
  is_shared: boolean;
  created_at: string;
  updated_at: string;
  row_columns: number[];
  row_heights: number[];
  row_descriptions: string[];
  entity_type?: string | null;
  entity_id?: string | null;
  ticker_context?: string | null;
  source_conversation_id?: string | null;
}

export interface AnalystPackCreate {
  name: string;
  description: string;
  widgets: PackWidgetRef[];
  mcp_tiles?: MCPTileRef[];
  is_shared: boolean;
  row_columns: number[];
  row_heights: number[];
  row_descriptions: string[];
  entity_type?: string | null;
  entity_id?: string | null;
  ticker_context?: string | null;
  source_conversation_id?: string | null;
}

export interface AnalystPackUpdate {
  name?: string;
  description?: string;
  widgets?: PackWidgetRef[];
  mcp_tiles?: MCPTileRef[];
  is_shared?: boolean;
  row_columns?: number[];
  row_heights?: number[];
  row_descriptions?: string[];
  ticker_context?: string | null;
}

// --- Documents ---

export interface EntityAssociation {
  entity_type: string;
  entity_id: string;
}

export interface DocumentChunk {
  chunk_id: string;
  file_id: string;
  chunk_index: number;
  text: string;
  char_start: number;
  char_end: number;
}

export interface DocumentListItem {
  file_id: string;
  filename: string;
  title: string;
  doc_type: string;
  date: string;
  description: string;
  entities: EntityAssociation[];
  chunk_count: number;
  indexed_at: string;
  metadata?: Record<string, string>;
}

export interface DocumentSearchResult {
  file_id: string;
  filename: string;
  title: string;
  doc_type: string;
  date: string;
  description: string;
  entities: EntityAssociation[];
  matching_chunks: DocumentChunk[];
  score: number;
}

// --- Email Schedules ---

export type WidgetOverrideRef = WidgetStateOverride;

export interface EmailSchedule {
  schedule_id: string;
  owner: string;
  name: string;
  entity_type: string;
  entity_id: string;
  widget_ids: string[] | null;
  recipients: string[];
  recurrence_type: string;
  time_of_day: string;
  days_of_week: number[];
  day_of_month: number | null;
  next_run_at: string;
  last_run_at: string;
  status: string;
  widget_overrides: WidgetOverrideRef[];
  retry_count: number;
  created_at: string;
  updated_at: string;
}

export interface EmailLog {
  log_id: string;
  schedule_id: string;
  sent_at: string;
  status: string;
  error: string | null;
  recipients: string[];
}

export interface EmailScheduleCreate {
  name: string;
  entity_type: string;
  entity_id: string;
  widget_ids: string[] | null;
  recipients: string[];
  recurrence_type: string;
  time_of_day: string;
  days_of_week: number[];
  day_of_month: number | null;
  widget_overrides: WidgetOverrideRef[];
}

export interface EmailScheduleUpdate {
  name?: string;
  recipients?: string[];
  recurrence_type?: string;
  time_of_day?: string;
  days_of_week?: number[];
  day_of_month?: number | null;
  status?: string;
  widget_overrides?: WidgetOverrideRef[];
}
