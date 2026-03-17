import { type ReactNode } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CITATION_REGEX, parseSingleCitation } from "../../utils/citationParser";
import type { ParsedCitation } from "../../utils/citationParser";
import { CitationLink } from "./CitationLink";

interface ChatMarkdownProps {
  children: string;
  onCitationClick: (citation: ParsedCitation) => void;
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

export function ChatMarkdown({ children, onCitationClick }: ChatMarkdownProps) {
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
        td({ children: kids }) {
          return <td>{processChildren(kids, onCitationClick)}</td>;
        },
        th({ children: kids }) {
          return <th>{processChildren(kids, onCitationClick)}</th>;
        },
      }}
    >
      {children}
    </Markdown>
  );
}
