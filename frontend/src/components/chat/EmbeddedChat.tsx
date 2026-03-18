import { useState, useRef, useEffect } from "react";
import { useMode2Chat } from "../../hooks/useMode2Chat";
import { ChatMarkdown } from "./ChatMarkdown";
import { PipelineSteps } from "./PipelineSteps";
import { ReportResponseDialog } from "./ReportResponseDialog";
import type { ParsedCitation } from "../../utils/citationParser";
import "../../styles/chat.css";
import "../../styles/embedded-chat.css";

interface EmbeddedChatProps {
  onCitationClick?: (citation: ParsedCitation) => void;
}

export function EmbeddedChat({ onCitationClick }: EmbeddedChatProps) {
  const chat = useMode2Chat();
  const [input, setInput] = useState("");
  const [reporting, setReporting] = useState<{
    userQuery: string;
    llmResponse: string;
  } | null>(null);
  const threadEndRef = useRef<HTMLDivElement>(null);

  const hasThread =
    chat.messages.length > 0 || chat.chatLoading || !!chat.streamingContent;

  useEffect(() => {
    if (hasThread) {
      const el = threadEndRef.current;
      if (el?.parentElement) {
        el.parentElement.scrollTop = el.parentElement.scrollHeight;
      }
    }
  }, [chat.messages, chat.streamingContent, chat.chatLoading, hasThread]);

  const handleSubmit = () => {
    const q = input.trim();
    if (!q || chat.chatLoading) return;
    chat.sendMessage(q);
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleClear = () => {
    chat.startNewChat();
    setInput("");
  };

  const noop = () => {};
  const citationHandler = onCitationClick ?? noop;

  return (
    <div className={`embedded-chat${hasThread ? " embedded-chat--open" : ""}`}>
      {hasThread && (
        <div className="embedded-chat__thread">
          {chat.messages.map((msg, idx) => (
            <div
              key={idx}
              className={`embedded-chat__message embedded-chat__message--${msg.role}`}
            >
              <div
                className={`embedded-chat__bubble embedded-chat__bubble--${msg.role}`}
              >
                {msg.role === "assistant" ? (
                  <ChatMarkdown onCitationClick={citationHandler}>
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
                    const prevUser = chat.messages
                      .slice(0, idx)
                      .reverse()
                      .find((m) => m.role === "user");
                    setReporting({
                      userQuery: prevUser?.content ?? "",
                      llmResponse: msg.content,
                    });
                  }}
                >
                  Report Response
                </button>
              )}
            </div>
          ))}

          {chat.steps.length > 0 && (
            <PipelineSteps steps={chat.steps} completed={!chat.chatLoading} />
          )}

          {chat.streamingContent && (
            <div className="embedded-chat__bubble embedded-chat__bubble--assistant embedded-chat__bubble--streaming">
              <ChatMarkdown onCitationClick={citationHandler}>
                {chat.streamingContent}
              </ChatMarkdown>
            </div>
          )}

          {chat.chatLoading && !chat.streamingContent && (
            <div className="embedded-chat__bubble embedded-chat__bubble--loading">
              Thinking...
            </div>
          )}

          {chat.error && (
            <div className="embedded-chat__error">{chat.error}</div>
          )}

          <div ref={threadEndRef} />
        </div>
      )}

      <div className="embedded-chat__input-row">
        <input
          className="embedded-chat__input"
          type="text"
          placeholder={
            hasThread
              ? "Ask a follow-up question..."
              : "Ask GoldMine about this entity..."
          }
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={chat.chatLoading}
        />
        {chat.chatLoading ? (
          <button
            className="embedded-chat__btn embedded-chat__btn--cancel"
            onClick={chat.cancelChat}
          >
            Cancel
          </button>
        ) : (
          <button
            className="embedded-chat__btn"
            onClick={handleSubmit}
            disabled={!input.trim()}
          >
            {hasThread ? "Send" : "Ask"}
          </button>
        )}
        {hasThread && !chat.chatLoading && (
          <button className="embedded-chat__btn--clear" onClick={handleClear}>
            Clear
          </button>
        )}
      </div>

      {reporting && (
        <ReportResponseDialog
          userQuery={reporting.userQuery}
          llmResponse={reporting.llmResponse}
          conversationId={chat.conversationId}
          sessionId={chat.sessionId}
          onClose={() => setReporting(null)}
        />
      )}
    </div>
  );
}
