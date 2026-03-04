import axios from "axios";
import { useEffect, useRef, useState } from "react";
import * as docsApi from "../config/documentsApi";
import type { ConversationMessage, LLMQueryResponse, LLMSource } from "../types/entities";
import "../styles/research-search.css";

interface ResearchSearchBarProps {
  entityType: string;
  entityId: string;
}

interface ThreadMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: LLMSource[];
  model?: string;
  tokenUsage?: Record<string, number>;
  error?: boolean;
  sourcesExpanded?: boolean;
}

function getErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err) && err.response) {
    const status = err.response.status;
    const detail =
      err.response.data &&
      typeof err.response.data === "object" &&
      "detail" in err.response.data
        ? (err.response.data as { detail: string }).detail
        : null;

    switch (status) {
      case 400:
        return detail || "Invalid request. Please try rephrasing your query.";
      case 401:
        return "Invalid API key. Check ANTHROPIC_API_KEY configuration.";
      case 402:
        return "Anthropic API credit balance too low. Please add credits.";
      case 429:
        return "Too many requests. Please wait and try again.";
      case 502:
        return "LLM service unavailable. Try again later.";
      case 503:
        return "LLM not configured. Set ANTHROPIC_API_KEY to enable.";
      case 504:
        return "Request timed out. Try a simpler query.";
      default:
        return detail || `Request failed (${status}). Please try again.`;
    }
  }
  return "Failed to get response. Please try again.";
}

let nextId = 0;
function genId(): string {
  return `msg-${++nextId}`;
}

export function ResearchSearchBar({ entityType, entityId }: ResearchSearchBarProps) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [thread, setThread] = useState<ThreadMessage[]>([]);
  const [queryHistory, setQueryHistory] = useState<string[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const threadEndRef = useRef<HTMLDivElement | null>(null);

  const hasThread = thread.length > 0;

  // Auto-scroll thread container to bottom when thread updates
  // (only scroll within the thread, not the entire page)
  useEffect(() => {
    if (hasThread) {
      const el = threadEndRef.current;
      if (el?.parentElement) {
        el.parentElement.scrollTop = el.parentElement.scrollHeight;
      }
    }
  }, [thread, hasThread]);

  const handleSubmit = async () => {
    const q = query.trim();
    if (!q || loading) return;

    const isFirst = thread.length === 0;

    // Add user message to thread immediately
    const userMsg: ThreadMessage = { id: genId(), role: "user", content: q };
    setThread((prev) => [...prev, userMsg]);
    setQuery("");
    setLoading(true);

    setQueryHistory((prev) => {
      const filtered = prev.filter((h) => h !== q);
      return [q, ...filtered].slice(0, 5);
    });

    // Build conversation history from existing thread
    const conversationHistory: ConversationMessage[] = thread.map((msg) => ({
      role: msg.role,
      content: msg.content,
    }));

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const result: LLMQueryResponse = await docsApi.queryLLM(
        q,
        entityType,
        entityId,
        controller.signal,
        conversationHistory,
        isFirst,
      );
      const assistantMsg: ThreadMessage = {
        id: genId(),
        role: "assistant",
        content: result.answer,
        sources: result.sources,
        model: result.model,
        tokenUsage: result.token_usage,
        sourcesExpanded: false,
      };
      setThread((prev) => [...prev, assistantMsg]);
    } catch (err: unknown) {
      if (controller.signal.aborted) return;
      const errorMsg: ThreadMessage = {
        id: genId(),
        role: "assistant",
        content: getErrorMessage(err),
        error: true,
      };
      setThread((prev) => [...prev, errorMsg]);
    } finally {
      abortRef.current = null;
      setLoading(false);
    }
  };

  const handleCancel = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setLoading(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleClear = () => {
    setThread([]);
    setQuery("");
  };

  const toggleSources = (msgId: string) => {
    setThread((prev) =>
      prev.map((msg) =>
        msg.id === msgId ? { ...msg, sourcesExpanded: !msg.sourcesExpanded } : msg
      )
    );
  };

  return (
    <div className={`research-bar${hasThread ? " research-bar--threaded" : ""}`}>
      {hasThread && (
        <div className="research-bar__thread">
          {thread.map((msg) => (
            <div
              key={msg.id}
              className={`research-bar__message research-bar__message--${msg.role}`}
            >
              <div
                className={`research-bar__message-content research-bar__message-content--${msg.role}${msg.error ? " research-bar__message-content--error" : ""}`}
              >
                <div className="research-bar__message-text">{msg.content}</div>
                {msg.role === "assistant" && !msg.error && msg.sources && msg.sources.length > 0 && (
                  <div className="research-bar__sources">
                    <button
                      className="research-bar__sources-toggle"
                      onClick={() => toggleSources(msg.id)}
                    >
                      Sources ({msg.sources.length}){" "}
                      {msg.sourcesExpanded ? "\u25B2" : "\u25BC"}
                    </button>
                    {msg.sourcesExpanded &&
                      msg.sources.map((source, i) => (
                        <div key={i} className="research-bar__source">
                          <span className="research-bar__source-name">
                            {source.filename} (chunk {source.chunk_index})
                          </span>
                          <div className="research-bar__source-excerpt">
                            {source.excerpt}
                          </div>
                        </div>
                      ))}
                  </div>
                )}
                {msg.role === "assistant" && !msg.error && msg.model && (
                  <div className="research-bar__meta">
                    Model: {msg.model}
                    {msg.tokenUsage?.input_tokens != null && (
                      <>
                        {" "}&middot; Tokens: {msg.tokenUsage.input_tokens} in /{" "}
                        {msg.tokenUsage.output_tokens} out
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
          {loading && (
            <div className="research-bar__message research-bar__message--assistant">
              <div className="research-bar__message-content research-bar__message-content--assistant">
                <div className="research-bar__loading">
                  <span className="research-bar__spinner" />
                  Analyzing...
                </div>
              </div>
            </div>
          )}
          <div ref={threadEndRef} />
        </div>
      )}

      <div className="research-bar__input-row">
        <input
          className="research-bar__input"
          type="text"
          placeholder={hasThread ? "Ask a follow-up question..." : "Ask the Research Assistant about this entity..."}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        {loading ? (
          <button className="research-bar__cancel-btn" onClick={handleCancel}>
            Cancel
          </button>
        ) : (
          <button
            className="research-bar__btn"
            onClick={handleSubmit}
            disabled={!query.trim()}
          >
            {hasThread ? "Send" : "Ask"}
          </button>
        )}
        {hasThread && (
          <button className="research-bar__clear-btn" onClick={handleClear}>
            Clear
          </button>
        )}
      </div>

      {queryHistory.length > 0 && !hasThread && !loading && (
        <div className="research-bar__history">
          {queryHistory.map((h, i) => (
            <button
              key={i}
              className="research-bar__history-chip"
              onClick={() => setQuery(h)}
            >
              {h.length > 50 ? h.slice(0, 50) + "..." : h}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
