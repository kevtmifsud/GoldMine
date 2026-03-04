import api from "./api";
import type {
  Studio,
  StudioCreate,
  StudioUpdate,
  StudioChatRequest,
  StudioChatResponse,
} from "../types/studio";

export async function listStudios(): Promise<Studio[]> {
  const resp = await api.get<Studio[]>("/api/studios/");
  return resp.data;
}

export async function getStudio(studioId: string): Promise<Studio> {
  const resp = await api.get<Studio>(`/api/studios/${studioId}`);
  return resp.data;
}

export async function createStudio(body: StudioCreate): Promise<Studio> {
  const resp = await api.post<Studio>("/api/studios/", body);
  return resp.data;
}

export async function updateStudio(
  studioId: string,
  body: StudioUpdate
): Promise<Studio> {
  const resp = await api.put<Studio>(`/api/studios/${studioId}`, body);
  return resp.data;
}

export async function deleteStudio(studioId: string): Promise<void> {
  await api.delete(`/api/studios/${studioId}`);
}

export async function chatStudio(
  studioId: string,
  body: StudioChatRequest,
  signal?: AbortSignal
): Promise<StudioChatResponse> {
  const resp = await api.post<StudioChatResponse>(
    `/api/studios/${studioId}/chat`,
    body,
    { signal }
  );
  return resp.data;
}
