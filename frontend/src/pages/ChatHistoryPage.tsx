import { useState, useEffect, useCallback, useRef } from "react";
import { Link } from "react-router-dom";
import { Layout } from "../components/Layout";
import { listConversations } from "../config/mode2Api";
import type { ConversationSummary } from "../config/mode2Api";
import "../styles/chat.css";

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "\u2014";
  const normalized = dateStr.endsWith("Z") || dateStr.includes("+") ? dateStr : dateStr + "Z";
  const d = new Date(normalized);
  if (isNaN(d.getTime())) return "\u2014";
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  if (diffMs < 0) return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHrs = Math.floor(diffMins / 60);
  if (diffHrs < 24) return `${diffHrs}h ago`;
  const diffDays = Math.floor(diffHrs / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen).trimEnd() + "...";
}

export function ChatHistoryPage() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [tickerFilter, setTickerFilter] = useState("");
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [allTickers, setAllTickers] = useState<string[]>([]);
  const PAGE_SIZE = 30;
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  // Debounce search input
  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedSearch(searchInput.trim());
    }, 300);
    return () => clearTimeout(debounceRef.current);
  }, [searchInput]);

  // Load tickers from initial full fetch (no filters)
  useEffect(() => {
    listConversations(200, 0).then((all) => {
      const tickers = Array.from(
        new Set(all.flatMap((c) => c.ticker_context))
      ).sort();
      setAllTickers(tickers);
    }).catch(() => { /* ignore */ });
  }, []);

  // Fetch conversations when filters change
  const fetchConversations = useCallback(async (resetOffset: boolean) => {
    const currentOffset = resetOffset ? 0 : offset;
    setLoading(true);
    setError(null);
    try {
      const results = await listConversations(
        PAGE_SIZE,
        currentOffset,
        tickerFilter || undefined,
        debouncedSearch || undefined,
      );
      if (resetOffset) {
        setConversations(results);
        setOffset(results.length);
      } else {
        setConversations((prev) => [...prev, ...results]);
        setOffset(currentOffset + results.length);
      }
      setHasMore(results.length === PAGE_SIZE);
    } catch {
      setError("Failed to load conversations");
    } finally {
      setLoading(false);
    }
  }, [offset, debouncedSearch, tickerFilter]);

  // Reload on filter/search changes
  useEffect(() => {
    fetchConversations(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch, tickerFilter]);

  return (
    <Layout>
      <div className="chat-history">
        <div className="chat-history__header">
          <div className="chat-history__title-row">
            <h2 className="chat-history__title">Chat History</h2>
            <Link to="/chat" className="chat-history__new-btn">
              New Chat
            </Link>
          </div>
          <div className="chat-history__filters">
            <input
              className="chat-history__search"
              type="text"
              placeholder="Search by title or message content..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
            <select
              className="chat-history__ticker-filter"
              value={tickerFilter}
              onChange={(e) => setTickerFilter(e.target.value)}
            >
              <option value="">All tickers</option>
              {allTickers.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
        </div>

        {error && <div className="chat-history__error">{error}</div>}

        {!loading && conversations.length === 0 && (
          <div className="chat-history__empty">
            {debouncedSearch || tickerFilter
              ? "No conversations match your filters."
              : <>No conversations yet. <Link to="/chat">Start a new chat</Link></>
            }
          </div>
        )}

        <div className="chat-history__grid">
          {conversations.map((conv) => (
            <Link
              key={conv.id}
              to={`/chat/history/${conv.id}`}
              className="chat-history__card"
            >
              <div className="chat-history__card-header">
                <span className="chat-history__card-title">
                  {conv.title || "Untitled conversation"}
                </span>
                <span className="chat-history__card-date">
                  {formatDate(conv.last_active)}
                </span>
              </div>
              {conv.first_message && (
                <div className="chat-history__card-preview">
                  {truncate(conv.first_message, 120)}
                </div>
              )}
              <div className="chat-history__card-meta">
                {conv.ticker_context.length > 0 && (
                  <div className="chat-history__card-tickers">
                    {conv.ticker_context.slice(0, 5).map((t) => (
                      <span key={t} className="chat-history__ticker-badge">{t}</span>
                    ))}
                    {conv.ticker_context.length > 5 && (
                      <span className="chat-history__ticker-badge chat-history__ticker-badge--more">
                        +{conv.ticker_context.length - 5}
                      </span>
                    )}
                  </div>
                )}
                <div className="chat-history__card-stats">
                  <span>{conv.session_count} session{conv.session_count !== 1 ? "s" : ""}</span>
                  {conv.is_shared && <span className="chat-history__shared-badge">Shared</span>}
                </div>
              </div>
            </Link>
          ))}
        </div>

        {loading && (
          <div className="chat-history__loading">Loading conversations...</div>
        )}

        {!loading && hasMore && conversations.length > 0 && (
          <button
            className="chat-history__load-more"
            onClick={() => fetchConversations(false)}
          >
            Load more
          </button>
        )}
      </div>
    </Layout>
  );
}
