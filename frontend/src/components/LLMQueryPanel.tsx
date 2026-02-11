import { useState } from "react";
import * as docsApi from "../config/documentsApi";
import type { LLMQueryResponse } from "../types/entities";
import "../styles/documents.css";

interface LLMQueryPanelProps {
  entityType: string;
  entityId: string;
}

export function LLMQueryPanel({ entityType, entityId }: LLMQueryPanelProps) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<LLMQueryResponse | null>(null);
  const [sourcesExpanded, setSourcesExpanded] = useState(false);

  const handleSubmit = async () => {
    const q = query.trim();
    if (!q || loading) return;

    setLoading(true);
    setError(null);
    setResponse(null);
    setSourcesExpanded(false);

    try {
      const result = await docsApi.queryLLM(q, entityType, entityId);
      setResponse(result);
    } catch (err: unknown) {
      if (
        err &&
        typeof err === "object" &&
        "response" in err &&
        (err as { response?: { status?: number } }).response?.status === 503
      ) {
        setError("LLM not configured. Set ANTHROPIC_API_KEY to enable.");
      } else {
        setError("Failed to get response. Please try again.");
      }
    } finally {
      setLoading(false);
    }
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
        <button
          className="llm-panel__submit-btn"
          onClick={handleSubmit}
          disabled={loading || !query.trim()}
        >
          {loading ? "..." : "Ask"}
        </button>
      </div>

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
