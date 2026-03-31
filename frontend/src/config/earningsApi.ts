import api from "./api";

export async function fetchUpcomingEarnings(): Promise<unknown[]> {
  const resp = await api.get("/api/workflows/earnings-preview/upcoming");
  return resp.data;
}

export async function fetchPreviewHistory(
  limit = 50,
  offset = 0
): Promise<unknown[]> {
  const resp = await api.get("/api/workflows/earnings-preview/history", {
    params: { limit, offset },
  });
  return resp.data;
}

export async function fetchPreviewDetail(previewId: string): Promise<unknown> {
  const resp = await api.get(`/api/workflows/earnings-preview/${previewId}`);
  return resp.data;
}

export async function triggerPreview(
  ticker: string,
  keyKpis?: string[],
): Promise<{ workflow_run_id: string; status: string }> {
  const resp = await api.post("/api/workflows/earnings_preview/run", {
    inputs: {
      ticker,
      reporting_period: guessReportingPeriod(),
      forward_period: guessForwardPeriod(),
      ...(keyKpis && keyKpis.length > 0 ? { key_kpis: keyKpis } : {}),
    },
  });
  return resp.data;
}

export async function fetchBeatMiss(
  ticker: string,
  reportingPeriod: string
): Promise<Record<string, Record<string, { actual: number; consensus: number; diff_pct: number; verdict: string }>>> {
  const resp = await api.get(`/api/workflows/earnings-preview/${ticker}/beat-miss`, {
    params: { reporting_period: reportingPeriod },
  });
  return resp.data;
}

export async function fetchQuarterlyActuals(
  ticker: string,
  reportingPeriod: string,
  metrics?: string[]
): Promise<{ actuals: Record<string, Record<string, number>>; period_ends: Record<string, string> }> {
  const params: Record<string, string> = { reporting_period: reportingPeriod };
  if (metrics) params.metrics = metrics.join(",");
  const resp = await api.get(`/api/workflows/earnings-preview/${ticker}/quarterly-actuals`, { params });
  return resp.data;
}

export async function updatePreviewSettings(
  previewId: string,
  settings: { key_kpis?: string[]; selected_alt_signals?: string[] }
): Promise<void> {
  await api.patch(`/api/workflows/earnings-preview/${previewId}`, settings);
}

export async function fetchAvailableAltData(
  ticker: string
): Promise<{ data_type: string; frequency: string; vendor: string }[]> {
  const resp = await api.get(`/api/workflows/earnings-preview/${ticker}/available-alt-data`);
  return resp.data;
}

export async function fetchAltDataChart(
  ticker: string,
  dataType: string
): Promise<Record<string, unknown>> {
  const resp = await api.get(`/api/workflows/earnings-preview/${ticker}/alt-data-chart`, {
    params: { data_type: dataType },
  });
  return resp.data;
}

export async function fetchPriceContext(
  ticker: string
): Promise<Record<string, unknown>> {
  const resp = await api.get(`/api/workflows/earnings-preview/${ticker}/price-context`);
  return resp.data;
}

export async function fetchEstimatesDeepdive(
  ticker: string,
  period: string
): Promise<Record<string, unknown>[]> {
  const resp = await api.get(
    `/api/workflows/earnings-preview/${ticker}/estimates-deepdive`,
    { params: { period } }
  );
  return resp.data;
}

export async function fetchAvailableKpis(ticker: string): Promise<string[]> {
  const resp = await api.get(`/api/workflows/earnings-preview/${ticker}/available-kpis`);
  return resp.data;
}

export async function fetchRunStatus(
  runId: string
): Promise<{ status: string; elapsed_seconds: number; output_id: string | null }> {
  const resp = await api.get(`/api/workflows/runs/${runId}`);
  return resp.data;
}

function guessReportingPeriod(): string {
  const now = new Date();
  const q = Math.ceil((now.getMonth() + 1) / 3);
  const y = now.getFullYear();
  // Most recent completed quarter
  if (q === 1) return `${y - 1}Q4`;
  return `${y}Q${q - 1}`;
}

function guessForwardPeriod(): string {
  const now = new Date();
  const q = Math.ceil((now.getMonth() + 1) / 3);
  const y = now.getFullYear();
  return `${y}Q${q}`;
}
