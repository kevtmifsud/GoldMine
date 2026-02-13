import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api from "../config/api";
import type { EntityResolution, EntityCandidate } from "../types/entities";
import "../styles/search.css";

export function SearchBar({ compact = false }: { compact?: boolean }) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [candidates, setCandidates] = useState<EntityCandidate[]>([]);
  const [message, setMessage] = useState<string | null>(null);

  // Autocomplete state
  const [suggestions, setSuggestions] = useState<EntityCandidate[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();
  const containerRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  // Fetch autocomplete suggestions
  const fetchSuggestions = useCallback(async (q: string) => {
    if (q.trim().length === 0) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }
    try {
      const resp = await api.get<EntityCandidate[]>("/api/entities/autocomplete", {
        params: { q: q.trim(), limit: 10 },
      });
      setSuggestions(resp.data);
      setShowSuggestions(resp.data.length > 0);
      setActiveIndex(-1);
    } catch {
      setSuggestions([]);
      setShowSuggestions(false);
    }
  }, []);

  // Debounced input handler
  const handleInputChange = (value: string) => {
    setQuery(value);
    setCandidates([]);
    setMessage(null);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchSuggestions(value), 200);
  };

  // Close suggestions when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Cleanup debounce on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const handleSelect = (candidate: EntityCandidate) => {
    setShowSuggestions(false);
    setSuggestions([]);
    setQuery("");
    setCandidates([]);
    setMessage(null);
    navigate(`/entity/${candidate.entity_type}/${candidate.entity_id}`);
  };

  const handleSearch = async () => {
    const trimmed = query.trim();
    if (!trimmed) return;

    setShowSuggestions(false);
    setSuggestions([]);
    setLoading(true);
    setCandidates([]);
    setMessage(null);

    try {
      const resp = await api.get<EntityResolution>("/api/entities/resolve", {
        params: { q: trimmed },
      });
      const result = resp.data;

      if (result.resolved && result.entity_type && result.entity_id) {
        setQuery("");
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
    if (showSuggestions && suggestions.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((prev) => (prev < suggestions.length - 1 ? prev + 1 : 0));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((prev) => (prev > 0 ? prev - 1 : suggestions.length - 1));
      } else if (e.key === "Enter" && activeIndex >= 0) {
        e.preventDefault();
        handleSelect(suggestions[activeIndex]);
        return;
      } else if (e.key === "Escape") {
        setShowSuggestions(false);
        return;
      }
    }
    if (e.key === "Enter") {
      handleSearch();
    }
  };

  return (
    <div className={compact ? "search search--compact" : "search"} ref={containerRef}>
      <div className="search__input-row">
        <input
          type="text"
          className="search__input"
          placeholder={compact ? "Search..." : "Search by ticker, name, or dataset..."}
          value={query}
          onChange={(e) => handleInputChange(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => { if (suggestions.length > 0) setShowSuggestions(true); }}
          disabled={loading}
          autoComplete="off"
        />
        <button
          className="search__button"
          onClick={handleSearch}
          disabled={loading || !query.trim()}
        >
          {loading ? "..." : "Search"}
        </button>
      </div>
      {showSuggestions && suggestions.length > 0 && (
        <ul className="search__autocomplete">
          {suggestions.map((s, idx) => (
            <li
              key={`${s.entity_type}-${s.entity_id}`}
              className={`search__autocomplete-item${idx === activeIndex ? " search__autocomplete-item--active" : ""}`}
              onMouseDown={() => handleSelect(s)}
              onMouseEnter={() => setActiveIndex(idx)}
            >
              <span className={`search__candidate-badge search__candidate-badge--${s.entity_type}`}>
                {s.entity_type}
              </span>
              <span className="search__autocomplete-name">
                {s.display_name}
              </span>
            </li>
          ))}
        </ul>
      )}
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
                onClick={() => handleSelect(c)}
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
