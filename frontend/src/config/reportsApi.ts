import api from "./api";
import type { EmailSchedule } from "../types/entities";

export interface ReportDefinition {
  report_id: string;
  name: string;
  description: string;
  category: string;
  data_sources: string[];
}

export async function listReports(): Promise<ReportDefinition[]> {
  const resp = await api.get<ReportDefinition[]>("/api/reports/");
  return resp.data;
}

export async function getReport(reportId: string): Promise<ReportDefinition> {
  const resp = await api.get<ReportDefinition>(`/api/reports/${reportId}`);
  return resp.data;
}

export async function listReportSubscriptions(
  reportId: string
): Promise<EmailSchedule[]> {
  const resp = await api.get<EmailSchedule[]>(
    `/api/reports/${reportId}/subscriptions`
  );
  return resp.data;
}
