import api from "./api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
export interface Conversation {
  id: string;
  title: string | null;
  ticker_context: string[];
  created_at: string;
  origin_path: string | null;
}

export interface ConversationSummary {
  id: string;
  title: string | null;
  ticker_context: string[];
  session_count: number;
  last_active: string | null;
  is_shared: boolean;
  first_message: string | null;
  origin_path: string | null;
}

export interface Session {
  session_id: string;
  conversation_id: string;
  created_at: string;
}

export interface SessionMessage {
  message_id: string;
  role: string;
  content: string;
  query_type: string | null;
  tickers_referenced: string[];
  source_chunks: Record<string, unknown>[];
  feedback: Record<string, unknown> | null;
  created_at: string;
}

export interface SessionDetail {
  session_id: string;
  conversation_id: string;
  messages: SessionMessage[];
  turn_count: number;
  created_at: string;
}

export interface ConversationDetail {
  id: string;
  title: string | null;
  ticker_context: string[];
  messages: SessionMessage[];
  turn_count: number;
  is_shared: boolean;
  created_at: string;
  last_active: string | null;
  origin_path: string | null;
}

// ---------------------------------------------------------------------------
// REST helpers (use axios `api` instance for auth / interceptors)
// ---------------------------------------------------------------------------
export async function createConversation(
  title?: string,
  ticker_context?: string[],
  origin_path?: string
): Promise<Conversation> {
  const resp = await api.post<Conversation>("/api/v1/conversations", {
    title: title ?? null,
    ticker_context: ticker_context ?? [],
    origin_path: origin_path ?? null,
  });
  return resp.data;
}

export async function createSession(
  conversationId: string
): Promise<Session> {
  const resp = await api.post<Session>("/api/v1/chat/session", {
    conversation_id: conversationId,
  });
  return resp.data;
}

export async function getSession(
  sessionId: string
): Promise<SessionDetail> {
  const resp = await api.get<SessionDetail>(
    `/api/v1/chat/session/${sessionId}`
  );
  return resp.data;
}

export async function getConversationDetail(
  conversationId: string
): Promise<ConversationDetail> {
  const resp = await api.get<ConversationDetail>(
    `/api/v1/conversations/${conversationId}`
  );
  return resp.data;
}

export async function renameConversation(
  conversationId: string,
  title: string
): Promise<void> {
  await api.patch(`/api/v1/conversations/${conversationId}`, { title });
}

export async function listConversations(
  limit = 50,
  offset = 0,
  ticker?: string,
  search?: string
): Promise<ConversationSummary[]> {
  const params: Record<string, string | number> = { limit, offset };
  if (ticker) params.ticker = ticker;
  if (search) params.search = search;
  const resp = await api.get<ConversationSummary[]>("/api/v1/conversations", {
    params,
  });
  return resp.data;
}

// ---------------------------------------------------------------------------
// Bug Reports
// ---------------------------------------------------------------------------
export interface BugReportPayload {
  conversation_id?: string | null;
  session_id?: string | null;
  message_id?: string | null;
  category: string;
  description?: string;
  user_query: string;
  llm_response: string;
  error_message?: string;
  tickers_referenced?: string[];
  query_type?: string;
}

export interface BugReportResult {
  bug_id: string;
  status: string;
}

export async function submitBugReport(
  payload: BugReportPayload
): Promise<BugReportResult> {
  const resp = await api.post<BugReportResult>("/api/v1/bug-reports", payload);
  return resp.data;
}

// ---------------------------------------------------------------------------
// SSE streaming (raw fetch — axios doesn't support ReadableStream)
// ---------------------------------------------------------------------------
export async function sendMessageStream(
  sessionId: string,
  conversationId: string,
  content: string,
  contextTickers?: string[],
  signal?: AbortSignal
): Promise<Response> {
  const resp = await fetch("/api/v1/chat/message", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    signal,
    body: JSON.stringify({
      session_id: sessionId,
      conversation_id: conversationId,
      content,
      context_tickers: contextTickers ?? [],
    }),
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Chat request failed (${resp.status}): ${text}`);
  }

  return resp;
}
