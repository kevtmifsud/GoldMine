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
  has_overrides: boolean;
  initial_filters: Record<string, string>;
  initial_sort_by: string | null;
  initial_sort_order: string | null;
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
}

export interface SavedView {
  view_id: string;
  name: string;
  owner: string;
  entity_type: string;
  entity_id: string;
  widget_overrides: WidgetStateOverride[];
  is_shared: boolean;
  created_at: string;
  updated_at: string;
}

export interface SavedViewCreate {
  name: string;
  entity_type: string;
  entity_id: string;
  widget_overrides: WidgetStateOverride[];
  is_shared: boolean;
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
}

export interface AnalystPack {
  pack_id: string;
  name: string;
  owner: string;
  description: string;
  widgets: PackWidgetRef[];
  is_shared: boolean;
  created_at: string;
  updated_at: string;
}

export interface AnalystPackCreate {
  name: string;
  description: string;
  widgets: PackWidgetRef[];
  is_shared: boolean;
}

export interface AnalystPackUpdate {
  name?: string;
  description?: string;
  widgets?: PackWidgetRef[];
  is_shared?: boolean;
}

// --- Documents & LLM ---

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

export interface LLMSource {
  file_id: string;
  filename: string;
  chunk_index: number;
  excerpt: string;
}

export interface LLMQueryResponse {
  answer: string;
  sources: LLMSource[];
  model: string;
  token_usage: Record<string, number>;
}
