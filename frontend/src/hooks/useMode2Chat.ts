import { useState, useRef, useCallback } from "react";
import {
  createConversation,
  createSession,
  sendMessageStream,
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
}

export interface Mode2ChatState {
  messages: ChatMessage[];
  chatLoading: boolean;
  streamingContent: string;
  conversationId: string | null;
  sessionId: string | null;
  error: string | null;
  steps: ChatStep[];
  sendMessage: (text: string) => void;
  cancelChat: () => void;
  startNewChat: () => void;
}

export function useMode2Chat(): Mode2ChatState {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [steps, setSteps] = useState<ChatStep[]>([]);

  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || chatLoading) return;

      setError(null);
      setChatLoading(true);
      setSteps([]);
      setMessages((prev) => [...prev, { role: "user", content: trimmed }]);

      let convId = conversationId;
      let sessId = sessionId;

      try {
        // Auto-create conversation + session on first message
        if (!convId || !sessId) {
          const conv = await createConversation();
          convId = conv.id;
          setConversationId(convId);

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
        let accumulated = "";
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // Parse SSE lines: "data: {...}\n\n"
          const lines = buffer.split("\n");
          // Keep the last potentially incomplete line in the buffer
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
                },
              ]);
            } else if (event.type === "token" && event.content) {
              accumulated += event.content as string;
              setStreamingContent(accumulated);
            } else if (event.type === "error") {
              setError((event.message as string) ?? "An error occurred");
            } else if (event.type === "done") {
              // Finalize: move accumulated text into messages
              if (accumulated) {
                const finalText = accumulated;
                setMessages((prev) => [
                  ...prev,
                  { role: "assistant", content: finalText },
                ]);
              }
              accumulated = "";
              setStreamingContent("");
            }
            // "metadata" events are silently consumed
          }
        }

        // If stream ended without a "done" event, finalize whatever we have
        if (accumulated) {
          const finalText = accumulated;
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: finalText },
          ]);
          setStreamingContent("");
        }
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === "AbortError") {
          // User cancelled — keep whatever was streamed so far
          if (streamingContent) {
            const partial = streamingContent;
            setMessages((prev) => [
              ...prev,
              { role: "assistant", content: partial },
            ]);
            setStreamingContent("");
          }
        } else {
          const msg =
            err instanceof Error ? err.message : "An unexpected error occurred";
          setError(msg);
        }
      } finally {
        abortRef.current = null;
        setChatLoading(false);
      }
    },
    [chatLoading, conversationId, sessionId, streamingContent]
  );

  const cancelChat = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const startNewChat = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setStreamingContent("");
    setConversationId(null);
    setSessionId(null);
    setError(null);
    setChatLoading(false);
    setSteps([]);
  }, []);

  return {
    messages,
    chatLoading,
    streamingContent,
    conversationId,
    sessionId,
    error,
    steps,
    sendMessage,
    cancelChat,
    startNewChat,
  };
}
