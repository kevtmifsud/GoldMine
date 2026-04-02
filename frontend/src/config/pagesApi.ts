import api from "./api";

export interface PageSummary {
  id: string;
  user_id: string;
  title: string;
  description: string | null;
  is_shared: boolean;
  tile_count: number;
  created_at: string;
  updated_at: string;
}

export interface PageDetail extends PageSummary {
  tiles: TileConfig[];
}

export interface TileConfig {
  id: string;
  title: string;
  tool: string;
  params: Record<string, unknown>;
  chart: Record<string, unknown> | null;
  position: { row: number; col: number; width: number; height: number };
}

export async function fetchPages(): Promise<PageSummary[]> {
  const res = await api.get<PageSummary[]>("/api/pages");
  return res.data;
}

export async function createPage(
  title: string,
  description?: string,
): Promise<PageDetail> {
  const res = await api.post<PageDetail>("/api/pages", {
    title,
    description: description ?? null,
    tiles: [],
  });
  return res.data;
}

export async function getPage(pageId: string): Promise<PageDetail> {
  const res = await api.get<PageDetail>(`/api/pages/${pageId}`);
  return res.data;
}

export async function addTile(
  pageId: string,
  tile: Omit<TileConfig, "id">,
): Promise<PageDetail> {
  const res = await api.post<PageDetail>(`/api/pages/${pageId}/tiles`, tile);
  return res.data;
}

export async function removeTile(
  pageId: string,
  tileId: string,
): Promise<PageDetail> {
  const res = await api.delete<PageDetail>(
    `/api/pages/${pageId}/tiles/${tileId}`,
  );
  return res.data;
}
