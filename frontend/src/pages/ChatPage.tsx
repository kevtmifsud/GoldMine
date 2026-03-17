import { useState, useRef, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Layout } from "../components/Layout";
import { useMode2Chat } from "../hooks/useMode2Chat";
import { ChatMarkdown } from "../components/chat/ChatMarkdown";
import { TranscriptViewerDialog } from "../components/research/TranscriptViewerDialog";
import { FinancialDataDialog } from "../components/chat/FinancialDataDialog";
import { PipelineSteps } from "../components/chat/PipelineSteps";
import type { ParsedCitation } from "../utils/citationParser";
import {
  isInlineViewable,
  isFinancialData,
  docTypeToStatementType,
  parseFiscalPeriod,
  documentTypeToRoute,
} from "../utils/citationParser";
import "../styles/chat.css";

const EXAMPLE_PROMPTS = [
  "What did AAPL say about margins last quarter?",
  "Summarize MSFT's cloud revenue trends",
  "Compare GOOGL and META on ad revenue guidance",
  "What risks did NVDA management highlight recently?",
];

interface ViewingTranscript {
  symbol: string;
  year: number;
  quarter: number;
}

interface ViewingFinancials {
  ticker: string;
  statementType: "income-statement" | "balance-sheet" | "cash-flow";
}

export function ChatPage() {
  const chat = useMode2Chat();
  const navigate = useNavigate();
  const [input, setInput] = useState("");
  const [viewingTranscript, setViewingTranscript] =
    useState<ViewingTranscript | null>(null);
  const [viewingFinancials, setViewingFinancials] =
    useState<ViewingFinancials | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll on new content
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat.messages, chat.streamingContent, chat.chatLoading]);

  const handleSend = () => {
    if (!input.trim() || chat.chatLoading) return;
    chat.sendMessage(input);
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "42px";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handlePromptClick = (prompt: string) => {
    chat.sendMessage(prompt);
  };

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

    // Fallback: navigate to research page
    const route = documentTypeToRoute(citation.docType);
    navigate(`/entity/stock/${citation.ticker}/research/${route}`);
  };

  const handleTextareaInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "42px";
    el.style.height = Math.min(el.scrollHeight, 140) + "px";
  };

  const showWelcome =
    chat.messages.length === 0 && !chat.chatLoading && !chat.streamingContent;

  return (
    <Layout>
      <div className="chat-page">
        <div className="chat-page__header">
          <span className="chat-page__title">Chat</span>
          <div className="chat-page__header-actions">
            <Link to="/chat/history" className="chat-page__history-link">
              History
            </Link>
            <button className="chat-page__new-btn" onClick={chat.startNewChat}>
              New Chat
            </button>
          </div>
        </div>

        <div className="chat-page__messages">
          {showWelcome && (
            <div className="chat-page__welcome">
              <span className="chat-page__welcome-title">
                GoldMine Chat
              </span>
              <span className="chat-page__welcome-desc">
                Ask questions about earnings transcripts, financial metrics, and
                company guidance. Answers are sourced from real filings and
                transcripts.
              </span>
              <div className="chat-page__welcome-prompts">
                {EXAMPLE_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    className="chat-page__prompt-btn"
                    onClick={() => handlePromptClick(prompt)}
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          )}

          {chat.messages.map((msg, idx) => (
            <div
              key={idx}
              className={`chat-page__msg chat-page__msg--${msg.role}`}
            >
              {msg.role === "assistant" ? (
                <ChatMarkdown onCitationClick={handleCitationClick}>
                  {msg.content}
                </ChatMarkdown>
              ) : (
                msg.content
              )}
            </div>
          ))}

          {chat.steps.length > 0 && (
            <PipelineSteps
              steps={chat.steps}
              completed={!chat.chatLoading}
            />
          )}

          {chat.streamingContent && (
            <div className="chat-page__msg chat-page__msg--streaming">
              <ChatMarkdown onCitationClick={handleCitationClick}>
                {chat.streamingContent}
              </ChatMarkdown>
            </div>
          )}

          {chat.chatLoading && !chat.streamingContent && (
            <div className="chat-page__msg chat-page__msg--loading">
              Thinking...
            </div>
          )}

          {chat.error && (
            <div className="chat-page__error">{chat.error}</div>
          )}

          <div ref={messagesEndRef} />
        </div>

        <div className="chat-page__input-area">
          <textarea
            ref={textareaRef}
            className="chat-page__textarea"
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              handleTextareaInput();
            }}
            onKeyDown={handleKeyDown}
            placeholder="Ask about earnings, guidance, margins..."
            rows={1}
            disabled={chat.chatLoading}
          />
          {chat.chatLoading ? (
            <button
              className="chat-page__send-btn chat-page__send-btn--cancel"
              onClick={chat.cancelChat}
            >
              Cancel
            </button>
          ) : (
            <button
              className="chat-page__send-btn"
              onClick={handleSend}
              disabled={!input.trim()}
            >
              Send
            </button>
          )}
        </div>
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
    </Layout>
  );
}
