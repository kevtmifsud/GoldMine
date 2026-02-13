import api from "./api";
import type {
  EmailSchedule,
  EmailScheduleCreate,
  EmailScheduleUpdate,
  EmailLog,
} from "../types/entities";

export async function createSchedule(
  body: EmailScheduleCreate
): Promise<EmailSchedule> {
  const resp = await api.post<EmailSchedule>("/api/schedules/", body);
  return resp.data;
}

export async function listSchedules(
  entityType?: string,
  entityId?: string
): Promise<EmailSchedule[]> {
  const params: Record<string, string> = {};
  if (entityType) params.entity_type = entityType;
  if (entityId) params.entity_id = entityId;
  const resp = await api.get<EmailSchedule[]>("/api/schedules/", { params });
  return resp.data;
}

export async function getSchedule(
  scheduleId: string
): Promise<EmailSchedule> {
  const resp = await api.get<EmailSchedule>(`/api/schedules/${scheduleId}`);
  return resp.data;
}

export async function updateSchedule(
  scheduleId: string,
  body: EmailScheduleUpdate
): Promise<EmailSchedule> {
  const resp = await api.put<EmailSchedule>(
    `/api/schedules/${scheduleId}`,
    body
  );
  return resp.data;
}

export async function deleteSchedule(scheduleId: string): Promise<void> {
  await api.delete(`/api/schedules/${scheduleId}`);
}

export async function getScheduleLogs(
  scheduleId: string
): Promise<EmailLog[]> {
  const resp = await api.get<EmailLog[]>(
    `/api/schedules/${scheduleId}/logs`
  );
  return resp.data;
}

export async function sendNow(scheduleId: string): Promise<EmailLog> {
  const resp = await api.post<EmailLog>(
    `/api/schedules/${scheduleId}/send-now`
  );
  return resp.data;
}
