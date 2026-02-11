import api from "./api";
import type {
  DocumentListItem,
  DocumentSearchResult,
  LLMQueryResponse,
} from "../types/entities";

export async function listDocuments(
  entityType?: string,
  entityId?: string
): Promise<DocumentListItem[]> {
  const params: Record<string, string> = {};
  if (entityType) params.entity_type = entityType;
  if (entityId) params.entity_id = entityId;
  const resp = await api.get<DocumentListItem[]>("/api/documents/", { params });
  return resp.data;
}

export async function searchDocuments(
  query: string,
  entityType?: string,
  entityId?: string
): Promise<DocumentSearchResult[]> {
  const params: Record<string, string> = { q: query };
  if (entityType) params.entity_type = entityType;
  if (entityId) params.entity_id = entityId;
  const resp = await api.get<DocumentSearchResult[]>("/api/documents/search", {
    params,
  });
  return resp.data;
}

export async function uploadDocument(
  file: File,
  entityType: string,
  entityId: string,
  title: string,
  description: string,
  date: string
): Promise<DocumentListItem> {
  const form = new FormData();
  form.append("file", file);
  form.append("entity_type", entityType);
  form.append("entity_id", entityId);
  form.append("title", title);
  form.append("description", description);
  form.append("date", date);
  const resp = await api.post<DocumentListItem>("/api/documents/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return resp.data;
}

export async function queryLLM(
  query: string,
  entityType: string,
  entityId: string
): Promise<LLMQueryResponse> {
  const resp = await api.post<LLMQueryResponse>("/api/documents/query", {
    query,
    entity_type: entityType,
    entity_id: entityId,
  });
  return resp.data;
}
