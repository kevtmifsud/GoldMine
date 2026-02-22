import { useState } from "react";
import * as docsApi from "../config/documentsApi";
import type { LLMQueryResponse } from "../types/entities";
import "../styles/research-search.css";

interface ResearchSearchBarProps {
  entityType: string;
  entityId: string;
}

export function ResearchSearchBar({ entityType, entityId }: ResearchSearchBarProps) {
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

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleClear = () => {
    setResponse(null);
    setError(null);
    setQuery("");
  };

  return (
    <div className="research-bar">
      <div className="research-bar__input-row">
        <input
          className="research-bar__input"
          type="text"
          placeholder="Ask the Research Assistant about this entity..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button
          className="research-bar__btn"
          onClick={handleSubmit}
          disabled={loading || !query.trim()}
        >
          {loading ? "Searching..." : "Ask"}
        </button>
        {(response || error) && (
          <button className="research-bar__clear-btn" onClick={handleClear}>
            Clear
          </button>
        )}
      </div>

      {loading && (
        <div className="research-bar__loading">
          <span className="research-bar__spinner" />
          Analyzing documents...
        </div>
      )}

      {error && <div className="research-bar__error">{error}</div>}

      {response && (
        <div className="research-bar__result">
          <div className="research-bar__answer">{response.answer}</div>
          {response.sources.length > 0 && (
            <div className="research-bar__sources">
              <button
                className="research-bar__sources-toggle"
                onClick={() => setSourcesExpanded(!sourcesExpanded)}
              >
                Sources ({response.sources.length}){" "}
                {sourcesExpanded ? "\u25B2" : "\u25BC"}
              </button>
              {sourcesExpanded &&
                response.sources.map((source, i) => (
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
          <div className="research-bar__meta">
            Model: {response.model}
            {response.token_usage.input_tokens != null && (
              <>
                {" "}&middot; Tokens: {response.token_usage.input_tokens} in /{" "}
                {response.token_usage.output_tokens} out
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
