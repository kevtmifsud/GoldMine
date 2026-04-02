import React, { useState, useRef, useEffect, useCallback } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Layout } from "../components/Layout";
import { useMode2Chat } from "../hooks/useMode2Chat";
import type { ChatMessage } from "../hooks/useMode2Chat";
import { useSlashCommand, CATEGORY_SLUGS } from "../hooks/useSlashCommand";
import { ChatMarkdown } from "../components/chat/ChatMarkdown";
import { SlashMenu } from "../components/chat/SlashMenu";
import { TranscriptViewerDialog } from "../components/research/TranscriptViewerDialog";
import { FinancialDataDialog } from "../components/chat/FinancialDataDialog";
import { ReportResponseDialog } from "../components/chat/ReportResponseDialog";
import { PipelineSteps } from "../components/chat/PipelineSteps";
import { AddToPageModal } from "../components/chat/AddToPageModal";
import type { AddToPageConfig } from "../components/chat/ChatMarkdown";
import type { ParsedCitation } from "../utils/citationParser";
import {
  isInlineViewable,
  isFinancialData,
  docTypeToStatementType,
  parseFiscalPeriod,
  documentTypeToRoute,
} from "../utils/citationParser";
import { generatePack } from "../config/viewsApi";
import "../styles/chat.css";
import "../styles/slash-menu.css";

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

interface ReportingMessage {
  userQuery: string;
  llmResponse: string;
}

// ---------------------------------------------------------------------------
// Memoized message components — isolate from slash menu re-renders
// ---------------------------------------------------------------------------

interface MessageItemProps {
  message: ChatMessage;
  index: number;
  messages: ChatMessage[];
  onCitationClick: (citation: ParsedCitation) => void;
  onSendPrompt: (prompt: string) => void;
  onAddToPage: (config: AddToPageConfig) => void;
  onReport: (report: ReportingMessage) => void;
}

const MessageItem = React.memo(function MessageItem({
  message: msg,
  index: idx,
  messages,
  onCitationClick,
  onSendPrompt,
  onAddToPage,
  onReport,
}: MessageItemProps) {
  return (
    <div>
      {msg.role === "assistant" && msg.steps && msg.steps.length > 0 && (
        <PipelineSteps steps={msg.steps} completed={true} />
      )}
      <div className={`chat-page__msg chat-page__msg--${msg.role}`}>
        {msg.role === "assistant" ? (
          <ChatMarkdown
            onCitationClick={onCitationClick}
            onSendPrompt={onSendPrompt}
            onAddToPage={onAddToPage}
          >
            {msg.content}
          </ChatMarkdown>
        ) : (
          msg.content
        )}
      </div>
      {msg.role === "assistant" && (
        <button
          className="chat-page__report-btn"
          onClick={() => {
            const prevUser = messages
              .slice(0, idx)
              .reverse()
              .find((m) => m.role === "user");
            onReport({
              userQuery: prevUser?.content ?? "",
              llmResponse: msg.content,
            });
          }}
        >
          Report Response
        </button>
      )}
    </div>
  );
});

interface MessageListProps {
  messages: ChatMessage[];
  onCitationClick: (citation: ParsedCitation) => void;
  onSendPrompt: (prompt: string) => void;
  onAddToPage: (config: AddToPageConfig) => void;
  onReport: (report: ReportingMessage) => void;
}

const MessageList = React.memo(function MessageList({
  messages,
  onCitationClick,
  onSendPrompt,
  onAddToPage,
  onReport,
}: MessageListProps) {
  return (
    <>
      {messages.map((msg, idx) => (
        <MessageItem
          key={idx}
          message={msg}
          index={idx}
          messages={messages}
          onCitationClick={onCitationClick}
          onSendPrompt={onSendPrompt}
          onAddToPage={onAddToPage}
          onReport={onReport}
        />
      ))}
    </>
  );
});

// ---------------------------------------------------------------------------

export function ChatPage() {
  const chat = useMode2Chat();
  const slash = useSlashCommand();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [input, setInput] = useState("");
  const promptHandled = useRef(false);
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const [viewingTranscript, setViewingTranscript] =
    useState<ViewingTranscript | null>(null);
  const [viewingFinancials, setViewingFinancials] =
    useState<ViewingFinancials | null>(null);
  const [reporting, setReporting] = useState<ReportingMessage | null>(null);
  const [addToPageConfig, setAddToPageConfig] = useState<AddToPageConfig | null>(null);
  const [, setPackGenerating] = useState(false);
  const [, setPackStatus] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-send prompt from query param (e.g. ?prompt=Show+me+...)
  useEffect(() => {
    const prompt = searchParams.get("prompt");
    if (prompt && !promptHandled.current && !chat.chatLoading) {
      promptHandled.current = true;
      chat.sendMessage(prompt);
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, chat, setSearchParams]);

  // Auto-scroll on new content
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat.messages, chat.streamingContent, chat.chatLoading]);

  const handleGeneratePack = useCallback(async () => {
    if (chat.messages.length === 0) {
      setPackStatus("No conversation to generate a pack from.");
      return;
    }
    setPackGenerating(true);
    setPackStatus(null);
    try {
      const apiMessages = chat.messages.map((m) => ({
        role: m.role,
        content: m.content,
        tool_calls: m.tool_calls || [],
      }));
      const result = await generatePack({
        session_id: chat.sessionId ?? undefined,
        messages: apiMessages,
      });
      if (result.error) {
        setPackStatus(result.error);
      } else {
        setPackStatus(`Pack "${result.pack_name}" created with ${result.tile_count} tiles.`);
        window.open(result.redirect_url, "_blank");
      }
    } catch {
      setPackStatus("Failed to generate pack. Try again.");
    } finally {
      setPackGenerating(false);
    }
  }, [chat.messages, chat.sessionId]);

  const handleSend = () => {
    if (!input.trim() || chat.chatLoading) return;

    // Direct command: /pack
    if (input.trim().toLowerCase() === "/pack") {
      setInput("");
      slash.dismissMenu();
      handleGeneratePack();
      if (textareaRef.current) textareaRef.current.style.height = "42px";
      return;
    }

    if (slash.slashMode && slash.selectedTool) {
      if (!slash.requiredParamsFilled) return;
      const tool = slash.selectedTool;
      const paramStr = slash.slashParams.join(" ");
      chat.sendMessage(`@${tool.full_name}(${paramStr})`);
    } else {
      chat.sendMessage(input);
    }
    setInput("");
    slash.dismissMenu();
    if (textareaRef.current) {
      textareaRef.current.style.height = "42px";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (slash.slashMenuVisible) {
      if (e.key === "Escape") {
        e.preventDefault();
        slash.dismissMenu();
        setInput("");
        return;
      }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const count = slash.menuItemCount();
        if (count > 0) {
          const delta = e.key === "ArrowDown" ? 1 : -1;
          slash.setSelectedIndex(
            (slash.selectedIndex + delta + count) % count,
          );
        }
        return;
      }
      if (e.key === "Tab") {
        e.preventDefault();
        // In params mode: Tab skips optional params (adds empty placeholder)
        if (slash.menuMode === "params" && slash.selectedTool) {
          const currentP = slash.selectedTool.parameters[slash.currentParamIndex];
          if (currentP && !currentP.required) {
            // Skip this optional param — append a space to advance
            const newInput = input.trimEnd() + " ";
            setInput(newInput);
            slash.parseInput(newInput);
            return;
          }
          // Required param — don't skip, stay here
          return;
        }
        // In category/tool mode: autocomplete
        const completed = slash.autocomplete(input);
        if (completed) {
          setInput(completed);
          slash.parseInput(completed);
        }
        return;
      }
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();

        if (slash.menuMode === "categories") {
          const partial = slash.slashCategory?.toLowerCase() ?? "";
          const filtered = CATEGORY_SLUGS.filter((s) =>
            s.startsWith(partial),
          );
          if (filtered[slash.selectedIndex]) {
            const newInput = slash.selectCategory(filtered[slash.selectedIndex]);
            setInput(newInput);
            slash.parseInput(newInput);
          }
          return;
        }

        if (slash.menuMode === "tools") {
          const partial = slash.slashToolName?.toLowerCase() ?? "";
          const filtered = slash.categoryTools.filter((t) =>
            t.name.toLowerCase().startsWith(partial),
          );
          if (filtered[slash.selectedIndex]) {
            const newInput = slash.selectTool(filtered[slash.selectedIndex].name);
            setInput(newInput);
            slash.parseInput(newInput);
          }
          return;
        }

        if (slash.menuMode === "params") {
          // If enum is showing, select the highlighted enum value
          const param = slash.selectedTool?.parameters[slash.currentParamIndex];
          if (param?.enum && param.enum[slash.selectedIndex]) {
            const newInput = slash.selectEnumValue(param.enum[slash.selectedIndex]);
            setInput(newInput);
            slash.parseInput(newInput);
            return;
          }
          // Block send if required params are missing
          if (!slash.requiredParamsFilled) {
            // Do nothing — user needs to keep filling params
            return;
          }
          handleSend();
          return;
        }
      }
    }

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInputChange = (value: string) => {
    setInput(value);
    slash.parseInput(value);
  };

  const handleSlashSelectCategory = (slug: string) => {
    const newInput = slash.selectCategory(slug);
    setInput(newInput);
    slash.parseInput(newInput);
    textareaRef.current?.focus();
  };

  const handleSlashSelectTool = (toolName: string) => {
    const newInput = slash.selectTool(toolName);
    setInput(newInput);
    slash.parseInput(newInput);
    textareaRef.current?.focus();
  };

  const handleSlashSelectEnum = (value: string) => {
    const newInput = slash.selectEnumValue(value);
    setInput(newInput);
    slash.parseInput(newInput);
    textareaRef.current?.focus();
  };

  const handleSlashSendPrompt = (prompt: string) => {
    slash.dismissMenu();
    setInput("");
    chat.sendMessage(prompt);
  };

  const handlePromptClick = (prompt: string) => {
    chat.sendMessage(prompt);
  };

  const handleCitationClick = useCallback((citation: ParsedCitation) => {
    // Estimate citations — no page to navigate to (structured DB data)
    if (citation.citationType === "estimate") {
      return;
    }

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
  }, [navigate]);

  const handleAddToPage = useCallback((config: AddToPageConfig) => {
    setAddToPageConfig(config);
  }, []);

  const handleReport = useCallback((report: ReportingMessage) => {
    setReporting(report);
  }, []);

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
          {editingTitle ? (
            <input
              className="chat-page__title-input"
              value={titleDraft}
              onChange={(e) => setTitleDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  const trimmed = titleDraft.trim();
                  if (trimmed) chat.renameChat(trimmed);
                  setEditingTitle(false);
                } else if (e.key === "Escape") {
                  setEditingTitle(false);
                }
              }}
              onBlur={() => {
                const trimmed = titleDraft.trim();
                if (trimmed && trimmed !== (chat.conversationTitle ?? "Chat")) {
                  chat.renameChat(trimmed);
                }
                setEditingTitle(false);
              }}
              autoFocus
            />
          ) : (
            <span
              className={`chat-page__title${chat.conversationId ? " chat-page__title--editable" : ""}`}
              onClick={() => {
                if (!chat.conversationId) return;
                setTitleDraft(chat.conversationTitle ?? "Chat");
                setEditingTitle(true);
              }}
            >
              {chat.conversationTitle ?? "Chat"}
              {chat.conversationId && (
                <svg className="chat-page__title-edit-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
                  <path d="m15 5 4 4" />
                </svg>
              )}
            </span>
          )}
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
            <>
              <div className="chat-page__spacer" />
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
            </>
          )}

          <MessageList
            messages={chat.messages}
            onCitationClick={handleCitationClick}
            onSendPrompt={chat.sendMessage}
            onAddToPage={handleAddToPage}
            onReport={handleReport}
          />

          {chat.chatLoading && chat.steps.length > 0 && (
            <PipelineSteps
              steps={chat.steps}
              completed={false}
            />
          )}

          {chat.streamingContent && (
            <div className="chat-page__msg chat-page__msg--streaming">
              <ChatMarkdown onCitationClick={handleCitationClick} onSendPrompt={chat.sendMessage} onAddToPage={handleAddToPage}>
                {chat.streamingContent}
              </ChatMarkdown>
            </div>
          )}

          {chat.chatLoading && !chat.streamingContent && (
            <div className="chat-page__msg chat-page__msg--loading">
              Thinking...
            </div>
          )}

          {chat.costWarning && (
            <div className="chat-page__cost-warning">
              <span className="chat-page__cost-warning-icon">&#9888;</span>
              <span className="chat-page__cost-warning-text">
                {chat.costWarning.message}
              </span>
              <div className="chat-page__cost-warning-actions">
                <button
                  className="chat-page__cost-warning-btn chat-page__cost-warning-btn--confirm"
                  onClick={chat.confirmCostWarning}
                >
                  Run it
                </button>
                <button
                  className="chat-page__cost-warning-btn chat-page__cost-warning-btn--cancel"
                  onClick={chat.dismissCostWarning}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {chat.error && (
            <>
              <div className="chat-page__error">{chat.error}</div>
              <button
                className="chat-page__report-btn"
                onClick={() => {
                  const lastUser = [...chat.messages]
                    .reverse()
                    .find((m) => m.role === "user");
                  handleReport({
                    userQuery: lastUser?.content ?? "",
                    llmResponse: "",
                  });
                }}
              >
                Report Response
              </button>
            </>
          )}

          {/* Sticky input — follows messages but pins to bottom of viewport */}
          <div className="chat-page__input-sticky">
            {slash.slashMenuVisible && (
              <SlashMenu
                slash={slash}
                onSelectCategory={handleSlashSelectCategory}
                onSelectTool={handleSlashSelectTool}
                onSelectEnumValue={handleSlashSelectEnum}
                onSendPrompt={handleSlashSendPrompt}
                onDismiss={slash.dismissMenu}
              />
            )}
            <div className={`chat-page__input-area${slash.slashMode ? " chat-page__input-area--slash" : ""}`}>
              <textarea
                ref={textareaRef}
                className={`chat-page__textarea${slash.slashMode ? " chat-page__textarea--slash" : ""}`}
                value={input}
                onChange={(e) => {
                  handleInputChange(e.target.value);
                  handleTextareaInput();
                }}
                onKeyDown={handleKeyDown}
                placeholder={slash.slashMode ? "Type a command... (Esc to cancel)" : "Ask about earnings, guidance, margins..."}
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
                  disabled={!input.trim() || (slash.slashMode && slash.menuMode === "params" && !slash.requiredParamsFilled)}
                >
                  Send
                </button>
              )}
            </div>
          </div>

          <div ref={messagesEndRef} />
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

      {reporting && (
        <ReportResponseDialog
          userQuery={reporting.userQuery}
          llmResponse={reporting.llmResponse}
          conversationId={chat.conversationId}
          sessionId={chat.sessionId}
          onClose={() => setReporting(null)}
        />
      )}

      <AddToPageModal
        isOpen={!!addToPageConfig}
        onClose={() => setAddToPageConfig(null)}
        tileConfig={addToPageConfig}
      />
    </Layout>
  );
}
