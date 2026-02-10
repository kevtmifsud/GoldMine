import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../config/api";
import type { EntityResolution, EntityCandidate } from "../types/entities";
import "../styles/search.css";

export function SearchBar() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [candidates, setCandidates] = useState<EntityCandidate[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const navigate = useNavigate();

  const handleSearch = async () => {
    const trimmed = query.trim();
    if (!trimmed) return;

    setLoading(true);
    setCandidates([]);
    setMessage(null);

    try {
      const resp = await api.get<EntityResolution>("/api/entities/resolve", {
        params: { q: trimmed },
      });
      const result = resp.data;

      if (result.resolved && result.entity_type && result.entity_id) {
        navigate(`/entity/${result.entity_type}/${result.entity_id}`);
      } else if (result.candidates.length > 0) {
        setCandidates(result.candidates);
      } else {
        setMessage(
          result.message || "No entity found. LLM-powered answers coming soon."
        );
      }
    } catch {
      setMessage("Search failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      handleSearch();
    }
  };

  const handleCandidateClick = (candidate: EntityCandidate) => {
    navigate(`/entity/${candidate.entity_type}/${candidate.entity_id}`);
  };

  return (
    <div className="search">
      <div className="search__input-row">
        <input
          type="text"
          className="search__input"
          placeholder="Search by ticker, name, or dataset..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
        />
        <button
          className="search__button"
          onClick={handleSearch}
          disabled={loading || !query.trim()}
        >
          {loading ? "Searching..." : "Search"}
        </button>
      </div>
      {candidates.length > 0 && (
        <div className="search__candidates">
          <p className="search__candidates-label">
            Multiple matches found. Select one:
          </p>
          <ul className="search__candidates-list">
            {candidates.map((c) => (
              <li
                key={`${c.entity_type}-${c.entity_id}`}
                className="search__candidate"
                onClick={() => handleCandidateClick(c)}
              >
                <span className={`search__candidate-badge search__candidate-badge--${c.entity_type}`}>
                  {c.entity_type}
                </span>
                <span className="search__candidate-name">
                  {c.display_name}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {message && <p className="search__message">{message}</p>}
    </div>
  );
}
