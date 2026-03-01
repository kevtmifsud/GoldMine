import axios from "axios";
import { useRef, useState } from "react";
import * as docsApi from "../config/documentsApi";
import type { LLMQueryResponse } from "../types/entities";
import "../styles/documents.css";

interface LLMQueryPanelProps {
  entityType: string;
  entityId: string;
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
        return "Anthropic API credit balance too low. Please add credits at console.anthropic.com.";
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

export function LLMQueryPanel({ entityType, entityId }: LLMQueryPanelProps) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<LLMQueryResponse | null>(null);
  const [sourcesExpanded, setSourcesExpanded] = useState(false);
  const [queryHistory, setQueryHistory] = useState<string[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  const handleSubmit = async () => {
    const q = query.trim();
    if (!q || loading) return;

    setLoading(true);
    setError(null);
    setResponse(null);
    setSourcesExpanded(false);

    // Add to history (deduplicated, max 5)
    setQueryHistory((prev) => {
      const filtered = prev.filter((h) => h !== q);
      return [q, ...filtered].slice(0, 5);
    });

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const result = await docsApi.queryLLM(
        q,
        entityType,
        entityId,
        controller.signal
      );
      setResponse(result);
    } catch (err: unknown) {
      if (controller.signal.aborted) {
        // User cancelled — no error to show
        return;
      }
      setError(getErrorMessage(err));
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

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="llm-panel">
      <div className="llm-panel__header">
        <h3 className="llm-panel__title">Research Assistant</h3>
      </div>

      <div className="llm-panel__input-area">
        <textarea
          className="llm-panel__textarea"
          placeholder="Ask a question about this entity..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={3}
        />
        {loading ? (
          <button className="llm-panel__cancel-btn" onClick={handleCancel}>
            Cancel
          </button>
        ) : (
          <button
            className="llm-panel__submit-btn"
            onClick={handleSubmit}
            disabled={!query.trim()}
          >
            Ask
          </button>
        )}
      </div>

      {queryHistory.length > 0 && (
        <div className="llm-panel__history">
          {queryHistory.map((h, i) => (
            <button
              key={i}
              className="llm-panel__history-chip"
              onClick={() => setQuery(h)}
            >
              {h.length > 40 ? h.slice(0, 40) + "..." : h}
            </button>
          ))}
        </div>
      )}

      {loading && (
        <div className="llm-panel__loading">
          <span className="llm-panel__loading-spinner" />
          <span className="llm-panel__loading-text">
            Analyzing documents...
          </span>
        </div>
      )}

      {error && <div className="llm-panel__error">{error}</div>}

      {response && (
        <div className="llm-panel__response">
          <div className="llm-panel__answer">{response.answer}</div>

          {response.sources.length > 0 && (
            <div className="llm-panel__sources">
              <button
                className="llm-panel__sources-title"
                onClick={() => setSourcesExpanded(!sourcesExpanded)}
              >
                Sources ({response.sources.length}){" "}
                {sourcesExpanded ? "\u25B2" : "\u25BC"}
              </button>
              {sourcesExpanded &&
                response.sources.map((source, i) => (
                  <div key={i} className="llm-panel__source">
                    <span className="llm-panel__source-name">
                      {source.filename} (chunk {source.chunk_index})
                    </span>
                    <div className="llm-panel__source-excerpt">
                      {source.excerpt}
                    </div>
                  </div>
                ))}
            </div>
          )}

          <div className="llm-panel__meta">
            Model: {response.model}
            {response.token_usage.input_tokens != null && (
              <>
                {" "}
                &middot; Tokens: {response.token_usage.input_tokens} in /{" "}
                {response.token_usage.output_tokens} out
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
