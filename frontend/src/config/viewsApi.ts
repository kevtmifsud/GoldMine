import api from "./api";
import type {
  SavedView,
  SavedViewCreate,
  SavedViewUpdate,
  AnalystPack,
  AnalystPackCreate,
  AnalystPackUpdate,
  WidgetConfig,
} from "../types/entities";

export async function listViews(
  entityType?: string,
  entityId?: string
): Promise<SavedView[]> {
  const params: Record<string, string> = {};
  if (entityType) params.entity_type = entityType;
  if (entityId) params.entity_id = entityId;
  const resp = await api.get<SavedView[]>("/api/views/", { params });
  return resp.data;
}

export async function getView(viewId: string): Promise<SavedView> {
  const resp = await api.get<SavedView>(`/api/views/${viewId}`);
  return resp.data;
}

export async function createView(body: SavedViewCreate): Promise<SavedView> {
  const resp = await api.post<SavedView>("/api/views/", body);
  return resp.data;
}

export async function updateView(
  viewId: string,
  body: SavedViewUpdate
): Promise<SavedView> {
  const resp = await api.put<SavedView>(`/api/views/${viewId}`, body);
  return resp.data;
}

export async function deleteView(viewId: string): Promise<void> {
  await api.delete(`/api/views/${viewId}`);
}

export async function listPacks(): Promise<AnalystPack[]> {
  const resp = await api.get<AnalystPack[]>("/api/views/packs/");
  return resp.data;
}

export async function getPack(packId: string): Promise<AnalystPack> {
  const resp = await api.get<AnalystPack>(`/api/views/packs/${packId}`);
  return resp.data;
}

export async function createPack(body: AnalystPackCreate): Promise<AnalystPack> {
  const resp = await api.post<AnalystPack>("/api/views/packs/", body);
  return resp.data;
}

export async function updatePack(
  packId: string,
  body: AnalystPackUpdate
): Promise<AnalystPack> {
  const resp = await api.put<AnalystPack>(`/api/views/packs/${packId}`, body);
  return resp.data;
}

export async function deletePack(packId: string): Promise<void> {
  await api.delete(`/api/views/packs/${packId}`);
}

export async function getEntityPack(
  entityType: string,
  entityId: string
): Promise<AnalystPack> {
  const resp = await api.get<AnalystPack>(
    `/api/views/packs/entity/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`
  );
  return resp.data;
}

export async function resolvePackWidgets(
  packId: string
): Promise<WidgetConfig[]> {
  const resp = await api.get<WidgetConfig[]>(
    `/api/views/packs/${packId}/resolved`
  );
  return resp.data;
}

// --- MCP Tile operations ---

export async function executeTile(
  packId: string,
  tileId: string,
): Promise<{
  rows: Record<string, unknown>[];
  columns: string[];
  row_count: number;
  preferred_presentation: string;
  chart_config: Record<string, unknown> | null;
  formatted_markdown?: string | null;
  display_type: string;
  error?: string;
}> {
  const resp = await api.post(`/api/views/packs/${packId}/tiles/${tileId}/execute`);
  return resp.data;
}

export async function updateTileState(
  packId: string,
  tileId: string,
  state: Record<string, unknown>,
): Promise<void> {
  await api.patch(`/api/views/packs/${packId}/tiles/${tileId}/state`, state);
}

export async function generatePack(body: {
  session_id?: string;
  messages: Array<{
    role: string;
    content: string;
    tool_calls?: Array<{ name: string; input: Record<string, unknown> }>;
  }>;
}): Promise<{
  pack_id: string;
  pack_name: string;
  tile_count: number;
  redirect_url: string;
  error?: string;
}> {
  const resp = await api.post("/api/views/packs/generate", body);
  return resp.data;
}
