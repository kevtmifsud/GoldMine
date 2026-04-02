import React, { type ReactNode, useRef, useState, useCallback, useMemo, lazy, Suspense } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CITATION_REGEX, parseSingleCitation } from "../../utils/citationParser";
import type { ParsedCitation } from "../../utils/citationParser";
import { CitationLink } from "./CitationLink";

const LazyPlot = lazy(() => import("react-plotly.js"));

/** Convert an ECharts option JSON (from backend) to Plotly data + layout. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function echartsToPlotly(opt: Record<string, any>): { data: any[]; layout: Record<string, any> } {
  const series = (opt.series || []) as any[];
  const xAxis = opt.xAxis || {};
  const yAxisArr = Array.isArray(opt.yAxis) ? opt.yAxis : [opt.yAxis || {}];
  const yLabel = yAxisArr[0]?.name || "";

  // Detect _format hint for tickformat
  const fmt = yAxisArr[0]?.axisLabel?._format || "";
  const fmtMap: Record<string, string> = { billions: "$,.3s", millions: "$,.3s", currency: "$,.0f", percent: ".1f", number: ",.0f" };
  const tickformat = fmtMap[fmt] || "";

  // Detect data format: separate xAxis.data array OR inline [x,y] pairs in series
  const xData = (xAxis.data || []) as any[];
  const isTimeAxis = xAxis.type === "time";
  const hasInlinePairs = !xData.length && series.length > 0 && Array.isArray(series[0]?.data?.[0]);

  const traces = series
    .filter((s: any) => s && s.type)
    .map((s: any) => {
      let xVals: any[];
      let yVals: any[];

      if (hasInlinePairs || isTimeAxis) {
        // Data is [[x, y], [x, y], ...]
        const pairs = (s.data || []) as any[];
        xVals = pairs.map((d: any) => (Array.isArray(d) ? d[0] : d));
        yVals = pairs.map((d: any) => (Array.isArray(d) ? d[1] : null));
      } else {
        // Data is [y1, y2, ...] with separate xAxis.data — or [{value}, ...]
        xVals = xData;
        yVals = (s.data || []).map((d: any) => {
          if (d === null || d === undefined) return null;
          if (typeof d === "object" && "value" in d) return d.value;
          return d;
        });
      }

      const color = s.lineStyle?.color || s.itemStyle?.color || s.color || undefined;

      if (s.type === "line") {
        return {
          type: "scatter" as const,
          mode: "lines" as const,
          name: s.name || "",
          x: xVals,
          y: yVals,
          line: { color, width: s.lineStyle?.width || 1.5 },
          connectgaps: false,
          hovertemplate: "%{y}<extra>%{fullData.name}</extra>",
        };
      }
      if (s.type === "bar") {
        // Bar colors: per-item from itemStyle or series-level
        const colors = (s.data || []).map((d: any) =>
          (typeof d === "object" && d?.itemStyle?.color) || color || "#3b82f6",
        );
        return {
          type: "bar" as const,
          name: s.name || "",
          x: xVals,
          y: yVals,
          marker: { color: colors.length > 1 ? colors : color || "#3b82f6" },
          hovertemplate: "%{y}<extra>%{fullData.name}</extra>",
        };
      }
      return null;
    })
    .filter(Boolean);

  const layout: Record<string, any> = {
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: { family: "Inter, system-ui, sans-serif", size: 11 },
    margin: { l: 55, r: 12, t: 8, b: traces.length > 1 ? 55 : 40 },
    showlegend: traces.length > 1,
    legend: { orientation: "h", y: -0.12, x: 0.5, xanchor: "center", font: { size: 10 }, tracegroupgap: 5 },
    xaxis: {
      gridcolor: "#e2e8f0",
      tickfont: { size: 10 },
      ...(isTimeAxis ? { type: "date", tickformat: "%b '%y", nticks: 8 } : {}),
    },
    yaxis: {
      title: { text: yLabel, font: { size: 10 } },
      gridcolor: "#e2e8f0",
      griddash: "dash",
      tickfont: { size: 10 },
      tickformat: tickformat || undefined,
    },
    hovermode: "x unified",
    autosize: true,
  };

  return { data: traces, layout };
}

export interface AddToPackConfig {
  tool: string;
  params: Record<string, unknown>;
  chartOption: Record<string, unknown>;
}

/** @deprecated Use AddToPackConfig */
export type AddToPageConfig = AddToPackConfig;

interface ChatMarkdownProps {
  children: string;
  onCitationClick: (citation: ParsedCitation) => void;
  onSendPrompt?: (prompt: string) => void;
  onAddToPage?: (config: AddToPackConfig) => void;
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

/** Memoized chart block — only re-renders when rawContent changes. */
const ChartBlock = React.memo(function ChartBlock({
  rawContent,
  onAddToPage,
}: {
  rawContent: string;
  onAddToPage?: (config: AddToPageConfig) => void;
}) {
  const parsed = useMemo(() => {
    try {
      const lines = rawContent.split("\n");
      let tool = "";
      let params: Record<string, unknown> = {};
      const jsonLines: string[] = [];
      for (const line of lines) {
        if (line.startsWith("// tool:")) {
          tool = line.replace("// tool:", "").trim();
        } else if (line.startsWith("// params:")) {
          try {
            params = JSON.parse(line.replace("// params:", "").trim());
          } catch { /* ignore */ }
        } else {
          jsonLines.push(line);
        }
      }
      const echartsOption = JSON.parse(jsonLines.join("\n"));
      const { data, layout } = echartsToPlotly(echartsOption);
      return { plotData: data, plotLayout: layout, toolName: tool, toolParams: params, chartOption: echartsOption, error: null as string | null };
    } catch (err) {
      return { plotData: null, plotLayout: null, toolName: "", toolParams: {} as Record<string, unknown>, chartOption: null, error: err instanceof Error ? err.message : "Invalid chart data" };
    }
  }, [rawContent]);

  if (parsed.error || !parsed.plotData) {
    return <pre className="chat-chart-error"><code>{rawContent}</code></pre>;
  }

  const { plotData, plotLayout, toolName, toolParams, chartOption } = parsed;

  return (
    <Suspense fallback={<div className="chat-chart-container">Loading chart...</div>}>
      <div className="chat-chart-container">
        <LazyPlot
          data={plotData}
          layout={plotLayout}
          config={PLOTLY_CONFIG}
          style={CHART_STYLE}
          useResizeHandler
        />
        {toolName && onAddToPage && (
          <div className="chat-chart-actions">
            <button
              className="chat-chart-add-btn"
              onClick={() => onAddToPage({ tool: toolName, params: toolParams, chartOption: chartOption! })}
            >
              + Add to Pack
            </button>
          </div>
        )}
      </div>
    </Suspense>
  );
});

const CHART_STYLE = { height: "320px", width: "100%" } as const;
const PLOTLY_CONFIG = { displayModeBar: false, responsive: true } as const;

export function ChatMarkdown({ children, onCitationClick, onSendPrompt, onAddToPage }: ChatMarkdownProps) {
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
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        code({ className, children: kids, node, ...rest }: any) {
          // Detect ```chart fenced code blocks and render as Plotly chart.
          // In react-markdown v10, fenced code blocks create <pre><code className="language-X">.
          // We handle detection in both `code` and `pre` for robustness.
          const isChart = typeof className === "string" && className.includes("language-chart");
          if (isChart) {
            const rawContent = String(kids).trim();
            return <ChartBlock rawContent={rawContent} onAddToPage={onAddToPage} />;
          }
          return <code className={className} {...rest}>{kids}</code>;
        },
        pre({ children: kids }) {
          // If the code component already rendered a ChartBlock, unwrap from <pre>
          const child = (Array.isArray(kids) ? kids[0] : kids) as React.ReactElement | undefined;
          if (child?.type === ChartBlock) {
            return <>{child}</>;
          }
          // Fallback: check raw code element className (in case code handler didn't fire)
          if (child?.props?.className && typeof child.props.className === "string" && child.props.className.includes("language-chart")) {
            const rawContent = String(child.props.children).trim();
            return <ChartBlock rawContent={rawContent} onAddToPage={onAddToPage} />;
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
