import { type ReactNode, useRef, useState, useCallback, lazy, Suspense } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CITATION_REGEX, parseSingleCitation } from "../../utils/citationParser";
import type { ParsedCitation } from "../../utils/citationParser";
import { CitationLink } from "./CitationLink";

const ReactECharts = lazy(() => import("echarts-for-react"));

/** Apply JS formatter functions to an ECharts option based on _format hints. */
function applyChartFormatters(option: Record<string, unknown>): Record<string, unknown> {
  const formatters: Record<string, (v: number) => string> = {
    billions: (v) => `$${(v / 1e9).toFixed(1)}B`,
    millions: (v) => `$${(v / 1e6).toFixed(0)}M`,
    currency: (v) => `$${v.toLocaleString()}`,
    percent: (v) => `${v.toFixed(1)}%`,
    number: (v) => v.toLocaleString(),
  };

  // Walk yAxis (single or array) and apply formatter from _format hint
  const processAxisLabel = (label: Record<string, unknown> | undefined) => {
    if (!label || typeof label !== "object") return;
    const fmt = label._format as string;
    if (fmt && formatters[fmt]) {
      label.formatter = formatters[fmt];
      delete label._format;
    }
  };

  const yAxis = option.yAxis;
  if (Array.isArray(yAxis)) {
    for (const ax of yAxis) processAxisLabel(ax?.axisLabel as Record<string, unknown>);
  } else if (yAxis && typeof yAxis === "object") {
    processAxisLabel((yAxis as Record<string, unknown>).axisLabel as Record<string, unknown>);
  }

  return option;
}

interface ChatMarkdownProps {
  children: string;
  onCitationClick: (citation: ParsedCitation) => void;
  onSendPrompt?: (prompt: string) => void;
}

/**
 * Splits a text string on citation patterns, returning a mix of plain strings
 * and CitationLink elements. Partial citations (e.g. during streaming) are
 * left as plain text.
 */
function renderWithCitations(
  text: string,
  onCitationClick: (citation: ParsedCitation) => void
): ReactNode[] {
  const globalRegex = new RegExp(CITATION_REGEX.source, "g");
  const parts: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = globalRegex.exec(text)) !== null) {
    // Text before the match
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    const citation = parseSingleCitation(match[0]);
    if (citation) {
      parts.push(
        <CitationLink
          key={match.index}
          citation={citation}
          onClick={onCitationClick}
        />
      );
    } else {
      parts.push(match[0]);
    }
    lastIndex = match.index + match[0].length;
  }

  // Remaining text after last match
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts;
}

/**
 * Recursively walks React children, replacing text nodes that contain citation
 * patterns with CitationLink components.
 */
function processChildren(
  children: ReactNode,
  onCitationClick: (citation: ParsedCitation) => void
): ReactNode {
  if (typeof children === "string") {
    const parts = renderWithCitations(children, onCitationClick);
    return parts.length === 1 ? parts[0] : <>{parts}</>;
  }
  if (Array.isArray(children)) {
    return children.map((child, i) =>
      typeof child === "string" ? (
        <span key={i}>{processChildren(child, onCitationClick)}</span>
      ) : (
        child
      )
    );
  }
  return children;
}

/**
 * Extract plain text from a ReactNode tree (handles strings, arrays, elements).
 */
function extractText(node: ReactNode): string {
  if (typeof node === "string") return node;
  if (typeof node === "number") return String(node);
  if (node == null || typeof node === "boolean") return "";
  if (Array.isArray(node)) return node.map(extractText).join("");
  if (typeof node === "object" && "props" in node) {
    return extractText((node as React.ReactElement).props.children);
  }
  return "";
}

/**
 * Check if a cell's content is numeric for right-alignment.
 * Strips markdown bold/italic markers and financial formatting
 * before testing. Handles: $1,234.56, -0.5%, +2.3%, 1.23x, N/A.
 */
function isNumericCell(node: ReactNode): boolean {
  const raw = extractText(node).trim();
  if (!raw) return false;
  // Strip markdown bold/italic markers
  const stripped = raw
    .replace(/\*\*/g, "")
    .replace(/\*/g, "")
    .replace(/\$/g, "")
    .replace(/,/g, "")
    .replace(/%/g, "")
    .replace(/x$/i, "")  // multiples like 1.23x
    .trim();
  if (!stripped) return false;
  // N/A is a special case — right-align it as a placeholder for a number
  if (/^N\/?A$/i.test(stripped)) return true;
  // Must parse as a number after stripping formatting
  return !isNaN(parseFloat(stripped)) && /^[+-]?\d/.test(stripped);
}

/**
 * Extract plain text from a table element for clipboard copy.
 */
function extractTableData(table: HTMLTableElement): { headers: string[]; rows: string[][] } {
  const headers: string[] = [];
  const rows: string[][] = [];

  table.querySelectorAll("thead th").forEach((th) => {
    headers.push((th as HTMLElement).innerText.trim());
  });

  table.querySelectorAll("tbody tr").forEach((tr) => {
    const cells: string[] = [];
    tr.querySelectorAll("td").forEach((td) => {
      cells.push((td as HTMLElement).innerText.trim());
    });
    if (cells.length > 0) rows.push(cells);
  });

  return { headers, rows };
}

function toTSV(headers: string[], rows: string[][]): string {
  const lines = [headers.join("\t")];
  for (const row of rows) lines.push(row.join("\t"));
  return lines.join("\n");
}

function toCSV(headers: string[], rows: string[][]): string {
  const escape = (s: string) => (s.includes(",") || s.includes('"') ? `"${s.replace(/"/g, '""')}"` : s);
  const lines = [headers.map(escape).join(",")];
  for (const row of rows) lines.push(row.map(escape).join(","));
  return lines.join("\n");
}

async function writeClipboard(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // Fallback for older browsers or insecure contexts
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    document.body.removeChild(textarea);
  }
}

function CopyTableButton({ tableRef }: { tableRef: React.RefObject<HTMLTableElement | null> }) {
  const [status, setStatus] = useState<"idle" | "menu" | "copied">("idle");

  const handleCopy = useCallback(
    async (format: "tsv" | "csv") => {
      const table = tableRef.current;
      if (!table) return;
      const { headers, rows } = extractTableData(table);
      const text = format === "tsv" ? toTSV(headers, rows) : toCSV(headers, rows);
      await writeClipboard(text);
      setStatus("copied");
      setTimeout(() => setStatus("idle"), 1500);
    },
    [tableRef]
  );

  if (status === "copied") {
    return <span className="chat-table-copy chat-table-copy--done">Copied!</span>;
  }

  if (status === "menu") {
    return (
      <span className="chat-table-copy chat-table-copy--menu">
        <button onClick={() => handleCopy("tsv")} className="chat-table-copy__option">
          TSV (Excel)
        </button>
        <button onClick={() => handleCopy("csv")} className="chat-table-copy__option">
          CSV
        </button>
        <button onClick={() => setStatus("idle")} className="chat-table-copy__option chat-table-copy__option--cancel">
          &times;
        </button>
      </span>
    );
  }

  return (
    <button className="chat-table-copy" onClick={() => setStatus("menu")} title="Copy table">
      Copy
    </button>
  );
}

function ChatTableWrapper({ children: kids }: { children: ReactNode }) {
  const tableRef = useRef<HTMLTableElement | null>(null);

  return (
    <div className="chat-table-wrap">
      <CopyTableButton tableRef={tableRef} />
      <table ref={tableRef}>{kids}</table>
    </div>
  );
}

export function ChatMarkdown({ children, onCitationClick, onSendPrompt }: ChatMarkdownProps) {
  return (
    <Markdown
      remarkPlugins={[remarkGfm]}
      components={{
        p({ children: kids }) {
          return <p>{processChildren(kids, onCitationClick)}</p>;
        },
        li({ children: kids }) {
          return <li>{processChildren(kids, onCitationClick)}</li>;
        },
        strong({ children: kids }) {
          return <strong>{processChildren(kids, onCitationClick)}</strong>;
        },
        em({ children: kids }) {
          return <em>{processChildren(kids, onCitationClick)}</em>;
        },
        table({ children: kids }) {
          return <ChatTableWrapper>{kids}</ChatTableWrapper>;
        },
        td({ children: kids }) {
          const align = isNumericCell(kids) ? "right" : undefined;
          return (
            <td style={align ? { textAlign: align } : undefined}>
              {processChildren(kids, onCitationClick)}
            </td>
          );
        },
        th({ children: kids }) {
          return <th>{processChildren(kids, onCitationClick)}</th>;
        },
        pre({ children: kids }) {
          // Fenced code blocks render as <pre><code className="language-X">...</code></pre>.
          // Detect ```chart blocks and render ECharts instead of a code block.
          const child = kids as React.ReactElement;
          if (child?.props?.className === "language-chart") {
            try {
              const chartOption = applyChartFormatters(
                JSON.parse(String(child.props.children).trim())
              );
              return (
                <Suspense fallback={<div className="chat-chart-container">Loading chart...</div>}>
                  <div className="chat-chart-container">
                    <ReactECharts
                      option={chartOption}
                      style={{ height: "320px", width: "100%" }}
                      opts={{ renderer: "canvas" }}
                      notMerge={true}
                    />
                  </div>
                </Suspense>
              );
            } catch {
              return <pre>{kids}</pre>;
            }
          }
          return <pre>{kids}</pre>;
        },
        a({ href, children: kids }) {
          if (href === "#plot-over-time" && onSendPrompt) {
            return (
              <button
                className="chat-plot-toggle"
                onClick={() =>
                  onSendPrompt(
                    "Plot the data from your last response over time as a line chart"
                  )
                }
              >
                {kids}
              </button>
            );
          }
          return <a href={href}>{kids}</a>;
        },
      }}
    >
      {children}
    </Markdown>
  );
}
