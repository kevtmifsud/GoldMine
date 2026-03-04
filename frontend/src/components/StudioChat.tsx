import { useState, useRef, useEffect } from "react";
import type { StudioEditorState } from "../hooks/useStudioEditor";
import "../styles/studio.css";

interface StudioChatProps {
  editor: StudioEditorState;
}

const EXAMPLE_PROMPTS = [
  "Show me AAPL revenue trend",
  "Compare MSFT and GOOGL net income",
  "Show TSLA stock price history",
  "What datasets are available?",
];

export function StudioChat({ editor }: StudioChatProps) {
  const { messages, chatLoading, sendMessage, cancelChat } = editor;
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, chatLoading]);

  const handleSend = () => {
    if (!input.trim() || chatLoading) return;
    sendMessage(input);
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "38px";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handlePromptClick = (prompt: string) => {
    sendMessage(prompt);
  };

  const handleTextareaInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "38px";
    el.style.height = Math.min(el.scrollHeight, 120) + "px";
  };

  return (
    <div className="studio-chat">
      <div className="studio-chat__messages">
        {messages.length === 0 && !chatLoading && (
          <div className="studio-chat__welcome">
            <span className="studio-chat__welcome-title">
              Data Studio Assistant
            </span>
            <span className="studio-chat__welcome-desc">
              Ask me to create charts using GoldMine's financial data. I can
              explore datasets, pull financial metrics, and build visualizations
              for you.
            </span>
            <div className="studio-chat__welcome-prompts">
              {EXAMPLE_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  className="studio-chat__prompt-btn"
                  onClick={() => handlePromptClick(prompt)}
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`studio-chat__msg studio-chat__msg--${msg.role}`}
          >
            {msg.content}
          </div>
        ))}

        {chatLoading && (
          <div className="studio-chat__msg studio-chat__msg--loading">
            Thinking...
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div className="studio-chat__input-area">
        <textarea
          ref={textareaRef}
          className="studio-chat__textarea"
          value={input}
          onChange={(e) => {
            setInput(e.target.value);
            handleTextareaInput();
          }}
          onKeyDown={handleKeyDown}
          placeholder="Ask about financial data..."
          rows={1}
          disabled={chatLoading}
        />
        {chatLoading ? (
          <button
            className="studio-chat__send-btn studio-chat__send-btn--cancel"
            onClick={cancelChat}
          >
            Cancel
          </button>
        ) : (
          <button
            className="studio-chat__send-btn"
            onClick={handleSend}
            disabled={!input.trim()}
          >
            Send
          </button>
        )}
      </div>
    </div>
  );
}
