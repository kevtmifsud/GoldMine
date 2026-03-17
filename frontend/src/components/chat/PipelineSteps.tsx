import { useState } from "react";

export interface ChatStep {
  label: string;
  detail: string;
  source: string;
  model: string | null;
  cost_usd: number;
  duration_ms: number;
  result_summary: string;
}

interface PipelineStepsProps {
  steps: ChatStep[];
  completed: boolean;
}

const SOURCE_COLORS: Record<string, { bg: string; fg: string }> = {
  anthropic: { bg: "#fff7ed", fg: "#c2410c" },
  openai: { bg: "#f0fdf4", fg: "#15803d" },
  supabase: { bg: "#f0fdfa", fg: "#0f766e" },
  cache: { bg: "#f1f5f9", fg: "#475569" },
};

function formatCost(cost: number): string {
  if (cost <= 0) return "";
  if (cost < 0.001) return `$${cost.toFixed(5)}`;
  return `$${cost.toFixed(4)}`;
}

function formatDuration(ms: number): string {
  if (ms <= 0) return "";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function PipelineSteps({ steps, completed }: PipelineStepsProps) {
  const [expanded, setExpanded] = useState(false);

  if (steps.length === 0) return null;

  // Collapsed summary after completion
  if (completed && !expanded) {
    const totalCost = steps.reduce((sum, s) => sum + s.cost_usd, 0);
    const totalDuration = steps.reduce((sum, s) => sum + s.duration_ms, 0);

    return (
      <button
        className="chat-steps__summary"
        onClick={() => setExpanded(true)}
      >
        <span className="chat-steps__summary-icon">&#9662;</span>
        {steps.length} steps
        {totalCost > 0 && <> &middot; {formatCost(totalCost)}</>}
        {totalDuration > 0 && <> &middot; {formatDuration(totalDuration)}</>}
      </button>
    );
  }

  return (
    <div className="chat-steps">
      {completed && (
        <button
          className="chat-steps__collapse-btn"
          onClick={() => setExpanded(false)}
        >
          &#9652; Collapse
        </button>
      )}
      {steps.map((step, i) => {
        const sourceStyle = SOURCE_COLORS[step.source] ?? SOURCE_COLORS.cache;
        return (
          <div key={i} className="chat-step">
            <span className="chat-step__check">&#10003;</span>
            <span className="chat-step__label">{step.label}</span>
            <span
              className="chat-step__source"
              style={{ backgroundColor: sourceStyle.bg, color: sourceStyle.fg }}
            >
              {step.source}
              {step.model && ` · ${step.model}`}
            </span>
            {step.cost_usd > 0 && (
              <span className="chat-step__cost">{formatCost(step.cost_usd)}</span>
            )}
            {step.duration_ms > 0 && (
              <span className="chat-step__duration">{formatDuration(step.duration_ms)}</span>
            )}
          </div>
        );
      })}
    </div>
  );
}
