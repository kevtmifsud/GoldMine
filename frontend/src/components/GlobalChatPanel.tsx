import { useState, useRef, useEffect, useCallback } from "react";
import { useGlobalChat, type PageContext } from "../context/GlobalChatContext";
import { useSlashCommand, CATEGORY_SLUGS } from "../hooks/useSlashCommand";
import { ChatMarkdown } from "./chat/ChatMarkdown";
import { SlashMenu } from "./chat/SlashMenu";
import { PipelineSteps } from "./chat/PipelineSteps";
import { generatePack, getPack, updatePack } from "../config/viewsApi";
import { AddToPageModal } from "./chat/AddToPageModal";
import type { ParsedCitation } from "../utils/citationParser";
import type { AddToPackConfig } from "./chat/ChatMarkdown";
import type { MCPTileRef } from "../types/entities";
import "../styles/global-chat-panel.css";

const MIN_WIDTH = 360;
const MAX_WIDTH_RATIO = 0.85; // max 85% of viewport

const _TOOL_LABELS: Record<string, string> = {
  get_estimates: "Estimates",
  get_estimate_history: "Estimate Revisions",
  get_alt_data: "Alt Data",
  get_pnl_history: "P&L History",
  get_daily_pnl: "P&L",
  get_financial_metrics: "Financials",
  get_stock_history: "Price History",
  get_portfolio_concentration: "Concentration",
  get_portfolio_risk: "Risk",
  get_guidance: "Guidance",
  get_trade_requests: "Trade Requests",
};

function _tileTitleFromTool(tool: string, params: Record<string, unknown>): string {
  const tickers = (params.tickers as string[]) || (params.ticker ? [params.ticker as string] : []);
  const tickerStr = tickers.slice(0, 3).join(", ");
  const label = _TOOL_LABELS[tool] || tool.replace(/_/g, " ").replace(/\bget\b/i, "").trim();
  return tickerStr ? `${tickerStr} ${label}` : label;
}
const DEFAULT_WIDTH = 440;

export function GlobalChatPanel() {
  const { isOpen, close, pageContext, chat, currentPackId } = useGlobalChat();
  const slash = useSlashCommand();
  const [input, setInput] = useState("");
  const [panelWidth, setPanelWidth] = useState(DEFAULT_WIDTH);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const dragging = useRef(false);

  // Resize via left-edge drag handle
  const handleDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = true;
    const startX = e.clientX;
    const startWidth = panelWidth;

    const onMove = (moveEvt: MouseEvent) => {
      if (!dragging.current) return;
      const delta = startX - moveEvt.clientX;
      const maxWidth = window.innerWidth * MAX_WIDTH_RATIO;
      setPanelWidth(Math.max(MIN_WIDTH, Math.min(startWidth + delta, maxWidth)));
    };

    const onUp = () => {
      dragging.current = false;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }, [panelWidth]);

  // Auto-scroll on new content
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat.messages, chat.streamingContent, chat.chatLoading]);

  // Focus input when panel opens
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => textareaRef.current?.focus(), 250);
    }
  }, [isOpen]);

  const [packGenerating, setPackGenerating] = useState(false);
  const [packStatus, setPackStatus] = useState<string | null>(null);
  const [addToPackConfig, setAddToPackConfig] = useState<AddToPackConfig | null>(null);

  const showWelcome =
    chat.messages.length === 0 && !chat.chatLoading && !chat.streamingContent;

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
      return;
    }

    if (slash.slashMode && slash.selectedTool) {
      if (!slash.requiredParamsFilled) return;
      const paramStr = slash.slashParams.join(" ");
      chat.sendMessage(`@${slash.selectedTool.full_name}(${paramStr})`);
    } else {
      chat.sendMessage(input);
    }
    setInput("");
    slash.dismissMenu();
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
          slash.setSelectedIndex((slash.selectedIndex + delta + count) % count);
        }
        return;
      }
      if (e.key === "Tab") {
        e.preventDefault();
        if (slash.menuMode === "params" && slash.selectedTool) {
          const currentP = slash.selectedTool.parameters[slash.currentParamIndex];
          if (currentP && !currentP.required) {
            const newInput = input.trimEnd() + " ";
            setInput(newInput);
            slash.parseInput(newInput);
            return;
          }
          return;
        }
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
          const filtered = CATEGORY_SLUGS.filter((s) => s.startsWith(partial));
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
          const param = slash.selectedTool?.parameters[slash.currentParamIndex];
          if (param?.enum && param.enum[slash.selectedIndex]) {
            const newInput = slash.selectEnumValue(param.enum[slash.selectedIndex]);
            setInput(newInput);
            slash.parseInput(newInput);
            return;
          }
          if (!slash.requiredParamsFilled) return;
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

  const handleSuggestionClick = (text: string) => {
    chat.sendMessage(text);
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

  const handleCitationClick = useCallback((_c: ParsedCitation) => {}, []);

  const handleAddToPack = useCallback(
    async (config: AddToPackConfig) => {
      if (!currentPackId) {
        // Not on a pack page — show the pack picker modal
        setAddToPackConfig(config);
        return;
      }
      try {
        const pack = await getPack(currentPackId);
        const occupied = new Set([
          ...(pack.widgets || []).map((w) => `${w.row}-${w.col}`),
          ...(pack.mcp_tiles || []).map((t) => `${t.row}-${t.col}`),
        ]);
        let row = 0;
        let col = 0;
        let found = false;
        for (let r = 0; r < pack.row_columns.length && !found; r++) {
          for (let c = 0; c < pack.row_columns[r] && !found; c++) {
            if (!occupied.has(`${r}-${c}`)) {
              row = r;
              col = c;
              found = true;
            }
          }
        }
        if (!found) {
          row = pack.row_columns.length;
          col = 0;
        }

        // Determine display type from whether the chart option has series data
        const hasChart = config.chartOption && Object.keys(config.chartOption).length > 0;
        const title =
          (config.chartOption?.title as Record<string, unknown>)?.text as string ||
          _tileTitleFromTool(config.tool, config.params) ||
          "Tile";

        const tile: MCPTileRef = {
          tile_id: crypto.randomUUID(),
          title,
          tool: config.tool,
          params: config.params,
          // Don't save the ECharts option as chart_config — the MCP server
          // provides its own chart_config when the tile is executed.
          // Only set display_type so the renderer knows to show a chart.
          display_type: hasChart ? "plotly_line" : "ag_grid",
          chart_config: null,
          is_template: false,
          row,
          col,
        };

        const updatedTiles = [...(pack.mcp_tiles || []), tile];
        const updatedRowCols = !found ? [...pack.row_columns, 2] : pack.row_columns;
        await updatePack(currentPackId, { mcp_tiles: updatedTiles, row_columns: updatedRowCols });
        setPackStatus(`Added to pack`);
        window.dispatchEvent(new CustomEvent("pack-tile-added", { detail: { packId: currentPackId } }));
      } catch {
        setPackStatus("Failed to add to pack");
      }
    },
    [currentPackId],
  );

  return (
    <div
      className={`gcp${isOpen ? " gcp--open" : ""}`}
      style={{ width: `${panelWidth}px` }}
    >
      {/* Resize drag handle — left edge */}
      <div className="gcp__resize-handle" onMouseDown={handleDragStart} />

      {/* Header */}
      <div className="gcp__header">
        <span className="gcp__title">GoldMine Chat</span>
        <div className="gcp__header-actions">
          <button className="gcp__header-btn" onClick={chat.startNewChat} title="New conversation">
            New Chat
          </button>
          <button className="gcp__close" onClick={close} title="Close (Cmd+/)">
            &times;
          </button>
        </div>
      </div>

      {/* Context banner */}
      {pageContext && (
        <ContextBanner context={pageContext} onSuggestionClick={handleSuggestionClick} />
      )}

      {/* Messages */}
      <div className="gcp__messages">
        {showWelcome && !pageContext && (
          <div className="gcp__welcome">
            Ask about earnings, estimates, portfolios, alt data, or anything in the knowledge base.
          </div>
        )}

        {chat.messages.map((msg, idx) => (
          <div key={idx}>
            {msg.role === "assistant" && msg.steps && msg.steps.length > 0 && (
              <PipelineSteps steps={msg.steps} completed={true} />
            )}
            <div className={`gcp__msg gcp__msg--${msg.role}`}>
              {msg.role === "assistant" ? (
                <ChatMarkdown
                  onCitationClick={handleCitationClick}
                  onSendPrompt={chat.sendMessage}
                  onAddToPage={handleAddToPack}
                >
                  {msg.content}
                </ChatMarkdown>
              ) : (
                msg.content
              )}
            </div>
          </div>
        ))}

        {chat.chatLoading && chat.steps.length > 0 && (
          <PipelineSteps steps={chat.steps} completed={false} />
        )}

        {chat.streamingContent && (
          <div className="gcp__msg gcp__msg--streaming">
            <ChatMarkdown
              onCitationClick={handleCitationClick}
              onSendPrompt={chat.sendMessage}
              onAddToPage={handleAddToPack}
            >
              {chat.streamingContent}
            </ChatMarkdown>
          </div>
        )}

        {chat.chatLoading && !chat.streamingContent && (
          <div className="gcp__msg gcp__msg--loading">Thinking...</div>
        )}

        {chat.error && <div className="gcp__error">{chat.error}</div>}

        <div ref={messagesEndRef} />
      </div>

      {/* Pack generation status */}
      {packGenerating && (
        <div className="gcp__pack-status gcp__pack-status--loading">Generating pack...</div>
      )}
      {packStatus && !packGenerating && (
        <div className="gcp__pack-status">
          {packStatus}
          <button className="gcp__pack-dismiss" onClick={() => setPackStatus(null)}>&times;</button>
        </div>
      )}

      {/* Slash menu */}
      {slash.slashMenuVisible && (
        <SlashMenu
          slash={slash}
          onSelectCategory={handleSlashSelectCategory}
          onSelectTool={handleSlashSelectTool}
          onSelectEnumValue={handleSlashSelectEnum}
          onSendPrompt={chat.sendMessage}
          onDismiss={slash.dismissMenu}
        />
      )}

      {/* Input */}
      <div className={`gcp__input-area${slash.slashMode ? " gcp__input-area--slash" : ""}`}>
        <textarea
          ref={textareaRef}
          className={`gcp__textarea${slash.slashMode ? " gcp__textarea--slash" : ""}`}
          value={input}
          onChange={(e) => handleInputChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={slash.slashMode ? "Type a command... (Esc to cancel)" : "Ask anything..."}
          rows={1}
          disabled={chat.chatLoading}
        />
        {chat.chatLoading ? (
          <button className="gcp__send-btn gcp__send-btn--cancel" onClick={chat.cancelChat}>
            Cancel
          </button>
        ) : (
          <button
            className="gcp__send-btn"
            onClick={handleSend}
            disabled={!input.trim() || (slash.slashMode && slash.menuMode === "params" && !slash.requiredParamsFilled)}
          >
            Send
          </button>
        )}
      </div>

      {/* /pack hint — show after analyst has received at least 2 responses */}
      {chat.messages.filter((m) => m.role === "assistant").length >= 2 && (
        <div className="gcp__pack-hint">
          Type <code>/pack</code> + Enter to save as a pack
        </div>
      )}

      <AddToPageModal
        isOpen={!!addToPackConfig}
        onClose={() => setAddToPackConfig(null)}
        tileConfig={addToPackConfig}
      />
    </div>
  );
}

/* ── Context Banner ── */

function ContextBanner({
  context,
  onSuggestionClick,
}: {
  context: PageContext;
  onSuggestionClick: (text: string) => void;
}) {
  const label =
    context.ticker && context.period
      ? `${context.ticker} · ${context.period}`
      : context.ticker
        ? context.ticker
        : context.page.replace(/_/g, " ");

  return (
    <div className="gcp__context">
      <span className="gcp__context-label">{label}</span>
      {context.suggestions && context.suggestions.length > 0 && (
        <div className="gcp__suggestions">
          {context.suggestions.map((s) => (
            <button key={s} className="gcp__suggestion" onClick={() => onSuggestionClick(s)}>
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
