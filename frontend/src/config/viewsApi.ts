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

export async function resolvePackWidgets(
  packId: string
): Promise<WidgetConfig[]> {
  const resp = await api.get<WidgetConfig[]>(
    `/api/views/packs/${packId}/resolved`
  );
  return resp.data;
}
