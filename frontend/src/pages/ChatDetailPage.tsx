import { useState, useEffect } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { Layout } from "../components/Layout";
import { ChatMarkdown } from "../components/chat/ChatMarkdown";
import { TranscriptViewerDialog } from "../components/research/TranscriptViewerDialog";
import { FinancialDataDialog } from "../components/chat/FinancialDataDialog";
import { ReportResponseDialog } from "../components/chat/ReportResponseDialog";
import { getConversationDetail } from "../config/mode2Api";
import type { ConversationDetail, SessionMessage } from "../config/mode2Api";
import type { ParsedCitation } from "../utils/citationParser";
import {
  isInlineViewable,
  isFinancialData,
  docTypeToStatementType,
  parseFiscalPeriod,
  documentTypeToRoute,
} from "../utils/citationParser";
import "../styles/chat.css";

function formatTimestamp(dateStr: string): string {
  // Ensure UTC interpretation — backend returns naive UTC datetimes without Z
  const normalized = dateStr.endsWith("Z") || dateStr.includes("+") ? dateStr : dateStr + "Z";
  const d = new Date(normalized);
  if (isNaN(d.getTime())) return dateStr;
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function MessageBubble({
  msg,
  onCitationClick,
  onReport,
}: {
  msg: SessionMessage;
  onCitationClick: (citation: ParsedCitation) => void;
  onReport: (llmResponse: string) => void;
}) {
  return (
    <div className="chat-detail__message-row">
      <div className="chat-detail__message-meta">
        <span className={`chat-detail__role chat-detail__role--${msg.role}`}>
          {msg.role === "user" ? "You" : "GoldMine"}
        </span>
        <span className="chat-detail__timestamp">
          {formatTimestamp(msg.created_at)}
        </span>
      </div>
      <div className={`chat-page__msg chat-page__msg--${msg.role}`}>
        {msg.role === "assistant" ? (
          <ChatMarkdown onCitationClick={onCitationClick}>
            {msg.content}
          </ChatMarkdown>
        ) : (
          msg.content
        )}
      </div>
      {msg.role === "assistant" && (
        <div className="chat-detail__message-info">
          {msg.query_type && (
            <span className="chat-detail__query-type">{msg.query_type.replace(/_/g, " ")}</span>
          )}
          {msg.tickers_referenced.length > 0 && (
            <span className="chat-detail__tickers-ref">
              {msg.tickers_referenced.join(", ")}
            </span>
          )}
          {msg.source_chunks.length > 0 && (
            <span className="chat-detail__chunk-count">
              {msg.source_chunks.length} source{msg.source_chunks.length !== 1 ? "s" : ""}
            </span>
          )}
          <button
            className="chat-page__report-btn"
            onClick={() => onReport(msg.content)}
          >
            Report Response
          </button>
        </div>
      )}
    </div>
  );
}

export function ChatDetailPage() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [viewingTranscript, setViewingTranscript] = useState<{
    symbol: string;
    year: number;
    quarter: number;
  } | null>(null);
  const [viewingFinancials, setViewingFinancials] = useState<{
    ticker: string;
    statementType: "income-statement" | "balance-sheet" | "cash-flow";
  } | null>(null);
  const [reporting, setReporting] = useState<{
    userQuery: string;
    llmResponse: string;
  } | null>(null);

  useEffect(() => {
    if (!conversationId) return;
    setLoading(true);
    setError(null);
    getConversationDetail(conversationId)
      .then(setDetail)
      .catch(() => setError("Failed to load conversation"))
      .finally(() => setLoading(false));
  }, [conversationId]);

  const handleCitationClick = (citation: ParsedCitation) => {
    if (isFinancialData(citation.docType)) {
      setViewingFinancials({
        ticker: citation.ticker,
        statementType: docTypeToStatementType(citation.docType),
      });
      return;
    }

    if (isInlineViewable(citation.docType)) {
      const fp = parseFiscalPeriod(citation.period);
      if (fp) {
        setViewingTranscript({
          symbol: citation.ticker,
          year: fp.year,
          quarter: fp.quarter,
        });
        return;
      }
    }

    const route = documentTypeToRoute(citation.docType);
    navigate(`/entity/stock/${citation.ticker}/research/${route}`);
  };

  return (
    <Layout>
      <div className="chat-detail">
        <div className="chat-detail__header">
          <Link to="/chat/history" className="chat-detail__back">
            &larr; History
          </Link>
          {detail && (
            <div className="chat-detail__header-info">
              <h2 className="chat-detail__title">
                {detail.title || "Untitled conversation"}
              </h2>
              <div className="chat-detail__header-meta">
                <span className="chat-detail__date">
                  {formatTimestamp(detail.created_at)}
                </span>
                {detail.ticker_context.length > 0 && (
                  <div className="chat-detail__header-tickers">
                    {detail.ticker_context.map((t) => (
                      <span key={t} className="chat-history__ticker-badge">{t}</span>
                    ))}
                  </div>
                )}
                <span className="chat-detail__msg-count">
                  {detail.turn_count} message{detail.turn_count !== 1 ? "s" : ""}
                </span>
                {detail.is_shared && (
                  <span className="chat-history__shared-badge">Shared</span>
                )}
                {detail.origin_path && (
                  <span className="chat-detail__origin">{detail.origin_path}</span>
                )}
              </div>
            </div>
          )}
        </div>

        {loading && (
          <div className="chat-detail__loading">Loading conversation...</div>
        )}
        {error && <div className="chat-history__error">{error}</div>}

        {!loading && !error && detail && (
          <div className="chat-detail__messages">
            {detail.messages.length === 0 ? (
              <div className="chat-history__empty">
                No messages in this conversation.
              </div>
            ) : (
              detail.messages.map((msg, idx) => (
                <MessageBubble
                  key={msg.message_id}
                  msg={msg}
                  onCitationClick={handleCitationClick}
                  onReport={(llmResponse) => {
                    const prevUser = detail.messages
                      .slice(0, idx)
                      .reverse()
                      .find((m) => m.role === "user");
                    setReporting({
                      userQuery: prevUser?.content ?? "",
                      llmResponse,
                    });
                  }}
                />
              ))
            )}
          </div>
        )}
      </div>

      {viewingTranscript && (
        <TranscriptViewerDialog
          symbol={viewingTranscript.symbol}
          year={viewingTranscript.year}
          quarter={viewingTranscript.quarter}
          onClose={() => setViewingTranscript(null)}
        />
      )}

      {viewingFinancials && (
        <FinancialDataDialog
          ticker={viewingFinancials.ticker}
          statementType={viewingFinancials.statementType}
          onClose={() => setViewingFinancials(null)}
        />
      )}

      {reporting && (
        <ReportResponseDialog
          userQuery={reporting.userQuery}
          llmResponse={reporting.llmResponse}
          conversationId={conversationId ?? null}
          sessionId={null}
          onClose={() => setReporting(null)}
        />
      )}
    </Layout>
  );
}
