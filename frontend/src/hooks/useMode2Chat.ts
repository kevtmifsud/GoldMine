import { useState, useRef, useCallback } from "react";
import {
  createConversation,
  createSession,
  sendMessageStream,
  renameConversation,
} from "../config/mode2Api";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatStep {
  label: string;
  detail: string;
  source: string;
  model: string | null;
  cost_usd: number;
  duration_ms: number;
  result_summary: string;
  query?: string;
}

export interface CostWarning {
  ticker_count: number;
  message: string;
}

export interface Mode2ChatState {
  messages: ChatMessage[];
  chatLoading: boolean;
  streamingContent: string;
  isStreaming: boolean;
  conversationId: string | null;
  sessionId: string | null;
  error: string | null;
  steps: ChatStep[];
  conversationTitle: string | null;
  costWarning: CostWarning | null;
  sendMessage: (text: string) => void;
  cancelChat: () => void;
  startNewChat: () => void;
  renameChat: (newTitle: string) => void;
  confirmCostWarning: () => void;
  dismissCostWarning: () => void;
}

export function useMode2Chat(): Mode2ChatState {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [steps, setSteps] = useState<ChatStep[]>([]);
  const [conversationTitle, setConversationTitle] = useState<string | null>(null);
  const [costWarning, setCostWarning] = useState<CostWarning | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const pendingQueryRef = useRef<string | null>(null);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || chatLoading) return;

      setError(null);
      setChatLoading(true);
      setIsStreaming(false);
      setSteps([]);
      setStreamingContent("");
      setCostWarning(null);
      pendingQueryRef.current = trimmed;
      setMessages((prev) => [...prev, { role: "user", content: trimmed }]);

      let convId = conversationId;
      let sessId = sessionId;

      try {
        // Auto-create conversation + session on first message
        if (!convId || !sessId) {
          const defaultTitle = `Chat — ${new Date().toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`;
          const conv = await createConversation(defaultTitle, undefined, window.location.pathname);
          convId = conv.id;
          setConversationId(convId);
          setConversationTitle(defaultTitle);

          const sess = await createSession(convId);
          sessId = sess.session_id;
          setSessionId(sessId);
        }

        const controller = new AbortController();
        abortRef.current = controller;

        const response = await sendMessageStream(
          sessId,
          convId,
          trimmed,
          undefined,
          controller.signal
        );

        const reader = response.body?.getReader();
        if (!reader) throw new Error("No response body");

        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // Parse SSE lines: "data: {...}\n\n"
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            const trimmedLine = line.trim();
            if (!trimmedLine || !trimmedLine.startsWith("data: ")) continue;

            const jsonStr = trimmedLine.slice(6);
            let event: Record<string, unknown>;
            try {
              event = JSON.parse(jsonStr);
            } catch {
              continue;
            }

            if (event.type === "step") {
              setSteps((prev) => [
                ...prev,
                {
                  label: (event.label as string) ?? "",
                  detail: (event.detail as string) ?? "",
                  source: (event.source as string) ?? "",
                  model: (event.model as string | null) ?? null,
                  cost_usd: (event.cost_usd as number) ?? 0,
                  duration_ms: (event.duration_ms as number) ?? 0,
                  result_summary: (event.result_summary as string) ?? "",
                  query: (event.query as string) ?? undefined,
                },
              ]);
            } else if (event.type === "token" && event.content) {
              // First token: switch from loading to streaming
              setIsStreaming(true);
              // Functional update — guarantees each token appends to latest state
              setStreamingContent((prev) => prev + (event.content as string));
            } else if (event.type === "error") {
              setError(
                (event.user_message as string) ??
                (event.message as string) ??
                "An error occurred"
              );
            } else if (event.type === "cost_warning") {
              // Pause: show warning and wait for user decision
              setCostWarning({
                ticker_count: (event.ticker_count as number) ?? 0,
                message: (event.message as string) ?? "",
              });
              setChatLoading(false);
            } else if (event.type === "done") {
              // Finalize: move streaming content into messages
              setStreamingContent((prev) => {
                if (prev) {
                  setMessages((msgs) => [
                    ...msgs,
                    { role: "assistant", content: prev },
                  ]);
                }
                return "";
              });
              setIsStreaming(false);
            }
            if (event.type === "metadata" && event.title) {
              setConversationTitle(event.title as string);
            }
          }
        }

        // If stream ended without a "done" event, finalize whatever we have
        setStreamingContent((prev) => {
          if (prev) {
            setMessages((msgs) => [
              ...msgs,
              { role: "assistant", content: prev },
            ]);
          }
          return "";
        });
        setIsStreaming(false);
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === "AbortError") {
          // User cancelled — keep whatever was streamed so far
          setStreamingContent((prev) => {
            if (prev) {
              setMessages((msgs) => [
                ...msgs,
                { role: "assistant", content: prev },
              ]);
            }
            return "";
          });
        } else {
          const msg =
            err instanceof Error ? err.message : "An unexpected error occurred";
          setError(msg);
        }
        setIsStreaming(false);
      } finally {
        abortRef.current = null;
        setChatLoading(false);
      }
    },
    [chatLoading, conversationId, sessionId]
  );

  const cancelChat = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const startNewChat = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setStreamingContent("");
    setIsStreaming(false);
    setConversationId(null);
    setSessionId(null);
    setError(null);
    setChatLoading(false);
    setSteps([]);
    setConversationTitle(null);
    setCostWarning(null);
    pendingQueryRef.current = null;
  }, []);

  const renameChat = useCallback(
    async (newTitle: string) => {
      if (!conversationId) return;
      setConversationTitle(newTitle);
      try {
        await renameConversation(conversationId, newTitle);
      } catch {
        // Revert on failure — could show an error, but keep it simple
      }
    },
    [conversationId]
  );

  const confirmCostWarning = useCallback(() => {
    setCostWarning(null);
    pendingQueryRef.current = null;
    sendMessage("yes, run it");
  }, [sendMessage]);

  const dismissCostWarning = useCallback(() => {
    setCostWarning(null);
    pendingQueryRef.current = null;
    abortRef.current?.abort();
    setMessages((prev) => [
      ...prev,
      { role: "user", content: "cancel" },
    ]);
  }, []);

  return {
    messages,
    chatLoading,
    streamingContent,
    isStreaming,
    conversationId,
    sessionId,
    error,
    steps,
    conversationTitle,
    costWarning,
    sendMessage,
    cancelChat,
    startNewChat,
    renameChat,
    confirmCostWarning,
    dismissCostWarning,
  };
}
