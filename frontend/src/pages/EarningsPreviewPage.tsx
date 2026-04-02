import { Component, Fragment, lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import type { ErrorInfo, ReactNode } from "react";

const LazyPlot = lazy(() => import("react-plotly.js"));
const PLOTLY_CFG = { displayModeBar: false, responsive: true } as const;
import { Layout } from "../components/Layout";
import { usePageContext } from "../hooks/usePageContext";
import {
  fetchUpcomingEarnings,
  fetchPreviewHistory,
  fetchPreviewDetail,
  fetchPriceContext,
  fetchEstimatesDeepdive,
  fetchQuarterlyActuals,
  fetchBeatMiss,
  fetchAvailableAltData,
  fetchAltDataChart,
  fetchAvailableKpis,
  updatePreviewSettings,
  triggerPreview,
  fetchRunStatus,
} from "../config/earningsApi";
import "../styles/earnings-preview.css";

// Error boundary to catch render errors and show them instead of white screen
class EarningsBoundary extends Component<{ children: ReactNode }, { error: string | null }> {
  state = { error: null as string | null };
  static getDerivedStateFromError(err: Error) { return { error: err.message }; }
  componentDidCatch(err: Error, info: ErrorInfo) { console.error("EarningsPreviewPage crash:", err, info); }
  render() {
    if (this.state.error) return <div style={{ padding: "2rem", color: "red" }}>Page error: {this.state.error}</div>;
    return this.props.children;
  }
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface UpcomingEarning {
  ticker: string;
  company_name: string;
  sector: string;
  industry: string;
  report_date: string;
  fiscal_quarter_ending: string;
  days_away: number;
  preview_status: string;
  preview_id: string | null;
  generated_at: string | null;
}

interface PreviewSummary {
  id: string;
  ticker: string;
  company_name: string;
  reporting_period: string;
  forward_period: string;
  key_kpis: string[];
  generated_at: string;
  generated_by: string;
  status: string | null;
  cost_usd: number | null;
  duration_seconds: number | null;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type PreviewDetail = Record<string, any>;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function timeAgo(dateStr: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function formatCurrency(v: number | null | undefined, precise = false): string {
  if (v == null) return "\u2014";
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (precise) {
    // Full millions — no rounding ambiguity
    if (abs >= 1e6) return `${sign}$${Math.round(abs / 1e6).toLocaleString()}M`;
    return `${sign}$${abs.toFixed(2)}`;
  }
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(0)}K`;
  return `${sign}$${abs.toFixed(2)}`;
}

function daysAwayClass(days: number): string {
  if (days <= 2) return "ep-badge--danger";
  if (days <= 7) return "ep-badge--warning";
  return "ep-badge--ok";
}

// Default KPIs pre-selected for new tickers (subset of what financial_metrics has)
const DEFAULT_SELECTED = new Set([
  "total_revenue", "gross_profit", "operating_income", "ebitda",
  "diluted_eps", "free_cash_flow",
]);

// KPI selection modal — loads real metrics from the DB
function KpiModal({
  ticker,
  initialSelected,
  queuePosition,
  queueTotal,
  onConfirm,
  onCancel,
  onSkip,
}: {
  ticker: string;
  initialSelected?: string[];
  queuePosition?: number;
  queueTotal?: number;
  onConfirm: (kpis: string[]) => void;
  onCancel: () => void;
  onSkip?: () => void;
}) {
  const [available, setAvailable] = useState<string[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const kpis = await fetchAvailableKpis(ticker);
        setAvailable(kpis);
        // Use initial selection if provided, otherwise defaults
        if (initialSelected && initialSelected.length > 0) {
          setSelected(new Set(initialSelected));
        } else {
          setSelected(new Set(kpis.filter((k) => DEFAULT_SELECTED.has(k))));
        }
      } catch {
        setAvailable([]);
      } finally {
        setLoading(false);
      }
    })();
  }, [ticker, initialSelected]);

  const toggle = (kpi: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(kpi)) next.delete(kpi);
      else next.add(kpi);
      return next;
    });
  };

  return (
    <div className="ep-modal-overlay" onClick={onCancel}>
      <div className="ep-modal" onClick={(e) => e.stopPropagation()}>
        <div className="ep-modal__header">
          <h3>
            Select KPIs for {ticker}
            {queueTotal && queueTotal > 1 && (
              <span className="ep-modal__queue-badge">
                {queuePosition} of {queueTotal}
              </span>
            )}
          </h3>
          <button className="ep-modal__close" onClick={onCancel}>&times;</button>
        </div>
        <p className="ep-modal__desc">
          Choose the key metrics to track in the earnings preview.
          Only metrics available in the database for {ticker} are shown.
        </p>
        {loading ? (
          <div className="ep-modal__loading">Loading metrics...</div>
        ) : (
          <div className="ep-modal__tags">
            {available.map((kpi) => (
              <button
                key={kpi}
                className={`ep-kpi-tag-btn${selected.has(kpi) ? " ep-kpi-tag-btn--active" : ""}`}
                onClick={() => toggle(kpi)}
              >
                {selected.has(kpi) ? "\u2713 " : ""}
                {kpi.replace(/_/g, " ")}
              </button>
            ))}
            {available.length === 0 && (
              <div className="ep-muted">No metrics found for {ticker}.</div>
            )}
          </div>
        )}
        <div className="ep-modal__footer">
          <button
            className="ep-btn ep-btn--primary"
            onClick={() => onConfirm([...selected])}
            disabled={selected.size === 0}
          >
            Generate with {selected.size} KPI{selected.size !== 1 ? "s" : ""}
          </button>
          {onSkip && (
            <button className="ep-btn ep-btn--secondary" onClick={onSkip}>
              Skip
            </button>
          )}
          <button className="ep-btn ep-btn--secondary" onClick={onCancel}>
            Cancel{queueTotal && queueTotal > 1 ? " All" : ""}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export function EarningsPreviewPage() {
  const [upcoming, setUpcoming] = useState<UpcomingEarning[]>([]);
  const [history, setHistory] = useState<PreviewSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<PreviewDetail | null>(null);
  const [activeTab, setActiveTab] = useState<string>("summary");
  const [generating, setGenerating] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [kpiPromptQueue, setKpiPromptQueue] = useState<UpcomingEarning[]>([]);
  const viewerRef = useRef<HTMLDivElement>(null);

  // Inject page context into global chat panel
  usePageContext({
    page: "earnings_preview",
    ticker: detail?.ticker as string | undefined,
    period: (detail?.reporting_period as string) ?? undefined,
    suggestions: detail
      ? [
          `What are ${detail.ticker}'s estimates?`,
          `Show me ${detail.ticker} credit card data`,
          `How has ${detail.ticker} traded recently?`,
        ]
      : undefined,
  });

  // Fetch data on mount
  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const [u, h] = await Promise.all([
          fetchUpcomingEarnings(),
          fetchPreviewHistory(),
        ]);
        setUpcoming(u as UpcomingEarning[]);
        setHistory(h as PreviewSummary[]);
      } catch {
        // silently ignore — empty state shown
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // Fetch detail when selection changes
  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    (async () => {
      try {
        const d = await fetchPreviewDetail(selectedId);
        setDetail(d as PreviewDetail);
      } catch {
        setDetail(null);
      }
    })();
  }, [selectedId]);

  // Check if ticker has prior KPIs — if not, show the popover
  const handleGenerateClick = useCallback(
    (earnings: UpcomingEarning | UpcomingEarning[]) => {
      const list = Array.isArray(earnings) ? earnings : [earnings];
      const needKpis: UpcomingEarning[] = [];
      for (const earning of list) {
        if (generating.has(earning.ticker)) continue;
        const prior = history.find((h) => h.ticker === earning.ticker && h.key_kpis?.length > 0);
        if (prior) {
          handleGenerate(earning.ticker, prior.key_kpis);
        } else {
          needKpis.push(earning);
        }
      }
      if (needKpis.length > 0) {
        setKpiPromptQueue(needKpis);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [generating, history]
  );

  const handleGenerate = useCallback(
    async (ticker: string, keyKpis?: string[]) => {
      if (generating.has(ticker)) return;
      // Remove this ticker from the KPI queue (advance to next)
      setKpiPromptQueue((prev) => prev.filter((e) => e.ticker !== ticker));
      setGenerating((prev) => new Set(prev).add(ticker));
      try {
        const result = await triggerPreview(ticker, keyKpis);
        // Poll for completion
        const runId = result.workflow_run_id;
        const poll = setInterval(async () => {
          try {
            const status = await fetchRunStatus(runId);
            if (status.status === "completed" || status.status === "failed") {
              clearInterval(poll);
              setGenerating((prev) => {
                const next = new Set(prev);
                next.delete(ticker);
                return next;
              });
              // Refresh data
              const [u, h] = await Promise.all([
                fetchUpcomingEarnings(),
                fetchPreviewHistory(),
              ]);
              setUpcoming(u as UpcomingEarning[]);
              setHistory(h as PreviewSummary[]);
            }
          } catch {
            clearInterval(poll);
            setGenerating((prev) => {
              const next = new Set(prev);
              next.delete(ticker);
              return next;
            });
          }
        }, 3000);
      } catch {
        setGenerating((prev) => {
          const next = new Set(prev);
          next.delete(ticker);
          return next;
        });
      }
    },
    [generating]
  );

  const handleSelectPreview = useCallback(
    (id: string) => {
      setSelectedId(id);
      setActiveTab("summary");
      viewerRef.current?.scrollIntoView({ behavior: "smooth" });
    },
    []
  );

  // Upcoming tickers that need preview
  const needPreview = upcoming.filter(
    (e) => e.days_away <= 7 && e.preview_status !== "generated"
  );

  const TABS = ["summary", "price", "alt data", "prior preview", "citations"];

  return (
    <Layout>
      <EarningsBoundary>
      <div className="ep-page">
        <h2 className="ep-page__title">Earnings Previews</h2>

        {/* ---- SECTION 1: UPCOMING EARNINGS STRIP ---- */}
        {needPreview.length > 0 && (
          <div className="ep-banner">
            <span className="ep-banner__icon">&#9889;</span>
            <span>
              {needPreview.length} preview(s) due:{" "}
              {needPreview.map((e) => e.ticker).join(", ")}
            </span>
            <button
              className="ep-banner__btn"
              onClick={() => handleGenerateClick(needPreview)}
            >
              Generate All
            </button>
          </div>
        )}

        <div className="ep-strip">
          {upcoming.length === 0 && !loading && (
            <div className="ep-strip__empty">No upcoming earnings for portfolio tickers.</div>
          )}
          {upcoming.map((e) => (
            <div
              key={e.ticker}
              className={`ep-card${e.preview_id ? " ep-card--has-preview" : ""}`}
              onClick={() => e.preview_id && handleSelectPreview(e.preview_id)}
            >
              <div className="ep-card__ticker">{e.ticker}</div>
              <div className="ep-card__name">{e.company_name}</div>
              <div className="ep-card__date">
                {e.report_date}
              </div>
              <span className={`ep-badge ${daysAwayClass(e.days_away)}`}>
                {e.days_away <= 0 ? "Today" : e.days_away === 1 ? "Tomorrow" : `${e.days_away}d`}
              </span>
              {e.preview_status === "generated" && (
                <span className="ep-status ep-status--ready">&#10003; Ready</span>
              )}
              {generating.has(e.ticker) && (
                <span className="ep-status ep-status--running">&#8635; Generating...</span>
              )}
              <button
                className="ep-card__btn"
                disabled={generating.has(e.ticker)}
                onClick={(ev) => {
                  ev.stopPropagation();
                  handleGenerateClick(e);
                }}
              >
                {generating.has(e.ticker) ? "..." : "Generate"}
              </button>
            </div>
          ))}
        </div>

        {/* ---- SECTION 2: PREVIEW VIEWER + CHAT ---- */}
        <div className="ep-viewer" ref={viewerRef}>
          {/* Left: list */}
          <div className="ep-list">
            <div className="ep-list__header">
              All Previews
              <span className="ep-list__count">{history.length}</span>
            </div>
            {history.length === 0 && (
              <div className="ep-list__empty">
                No previews generated yet. Use the earnings strip above to generate your first preview.
              </div>
            )}
            {history.map((p) => (
              <button
                key={p.id}
                className={`ep-list__item${selectedId === p.id ? " ep-list__item--selected" : ""}`}
                onClick={() => handleSelectPreview(p.id)}
              >
                <span className="ep-list__ticker">{p.ticker}</span>
                <span className="ep-list__company">{p.company_name}</span>
                <span className="ep-list__period">{p.reporting_period}</span>
                <span className="ep-list__meta">
                  {timeAgo(p.generated_at)} &middot; {p.generated_by}
                </span>
              </button>
            ))}
          </div>

          {/* Center: detail */}
          <div className="ep-detail">
            {!selectedId && (
              <div className="ep-detail__empty">
                <span className="ep-detail__empty-icon">&#128203;</span>
                Select a preview from the list
              </div>
            )}

            {detail && (
              <>
                <div className="ep-detail__header">
                  <div>
                    <h3 className="ep-detail__ticker">
                      {detail.ticker}
                      <span className="ep-detail__company">{detail.company_name}</span>
                    </h3>
                    <div className="ep-detail__meta">
                      {detail.reporting_period} Earnings Preview
                      {detail.generated_at && <> &middot; {timeAgo(detail.generated_at)}</>}
                      {detail.generated_by && <> by {detail.generated_by}</>}
                      {Number(detail.cost_usd) > 0 && (
                        <span className="ep-detail__cost">${Number(detail.cost_usd).toFixed(4)}</span>
                      )}
                    </div>
                  </div>
                  <div className="ep-detail__actions">
                    <button
                      className="ep-btn ep-btn--secondary"
                      onClick={() => handleGenerate(detail.ticker, detail.key_kpis ?? [])}
                      disabled={generating.has(detail.ticker)}
                    >
                      Re-generate
                    </button>
                  </div>
                </div>

                <div className="ep-tabs">
                  {TABS.map((tab) => (
                    <button
                      key={tab}
                      className={`ep-tabs__tab${activeTab === tab ? " ep-tabs__tab--active" : ""}`}
                      onClick={() => setActiveTab(tab)}
                    >
                      {tab.charAt(0).toUpperCase() + tab.slice(1)}
                    </button>
                  ))}
                </div>

                <div className="ep-tab-content">
                  {activeTab === "summary" && <SummaryTab detail={detail} onDetailUpdated={() => {
                    // Refresh detail
                    fetchPreviewDetail(selectedId!).then((d) => setDetail(d as PreviewDetail)).catch(() => {});
                  }} />}
                  {activeTab === "price" && <PriceTab detail={detail} />}
                  {activeTab === "alt data" && <AltDataTab detail={detail} onDetailUpdated={() => {
                    fetchPreviewDetail(selectedId!).then((d) => setDetail(d as PreviewDetail)).catch(() => {});
                  }} />}
                  {activeTab === "prior preview" && <PriorPreviewTab detail={detail} />}
                  {activeTab === "citations" && <CitationsTab detail={detail} />}
                </div>
              </>
            )}
          </div>

        </div>

        {/* ---- SECTION 3: RUN HISTORY TABLE ---- */}
        <div className="ep-runs">
          <h3 className="ep-runs__title">Run History</h3>
          <table className="ep-runs__table">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Company</th>
                <th>Period</th>
                <th>Triggered By</th>
                <th>Generated</th>
                <th>Duration</th>
                <th>Status</th>
                <th>Cost</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {history.map((p) => (
                <tr key={p.id}>
                  <td className="ep-runs__ticker">{p.ticker}</td>
                  <td>{p.company_name}</td>
                  <td>{p.reporting_period}</td>
                  <td>{p.generated_by}</td>
                  <td>{timeAgo(p.generated_at)}</td>
                  <td>{p.duration_seconds ? `${p.duration_seconds}s` : "\u2014"}</td>
                  <td>
                    <span className={`ep-status-pill ep-status-pill--${p.status ?? "completed"}`}>
                      {p.status ?? "completed"}
                    </span>
                  </td>
                  <td>{p.cost_usd ? `$${Number(p.cost_usd).toFixed(4)}` : "\u2014"}</td>
                  <td>
                    <button
                      className="ep-btn ep-btn--small"
                      onClick={() => handleSelectPreview(p.id)}
                    >
                      View
                    </button>
                  </td>
                </tr>
              ))}
              {history.length === 0 && (
                <tr>
                  <td colSpan={9} className="ep-runs__empty">
                    No previews generated yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {kpiPromptQueue.length > 0 && (
        <KpiModal
          key={kpiPromptQueue[0].ticker}
          ticker={kpiPromptQueue[0].ticker}
          queuePosition={1}
          queueTotal={kpiPromptQueue.length}
          onConfirm={(kpis) => handleGenerate(kpiPromptQueue[0].ticker, kpis)}
          onCancel={() => setKpiPromptQueue([])}
          onSkip={kpiPromptQueue.length > 1
            ? () => setKpiPromptQueue((prev) => prev.slice(1))
            : undefined
          }
        />
      )}
      </EarningsBoundary>
    </Layout>
  );
}

// ---------------------------------------------------------------------------
// Tab components
// ---------------------------------------------------------------------------
function SummaryTab({ detail, onDetailUpdated }: { detail: PreviewDetail; onDetailUpdated: () => void }) {
  const kpis: string[] = detail.key_kpis ?? [];
  const estimates = detail.estimates_table ?? {};
  const [editingKpis, setEditingKpis] = useState(false);
  const [viewMode, setViewMode] = useState<"value" | "yoy">("value");

  const handleSaveKpis = useCallback(async (newKpis: string[]) => {
    await updatePreviewSettings(detail.id as string, { key_kpis: newKpis });
    setEditingKpis(false);
    onDetailUpdated();
  }, [detail.id, onDetailUpdated]);

  return (
    <div className="ep-summary">
      {/* KPIs */}
      <div className="ep-section">
        <div className="ep-section__header">
          <h4>Key KPIs</h4>
          <button className="ep-btn ep-btn--small ep-btn--secondary" onClick={() => setEditingKpis(true)}>
            Edit
          </button>
        </div>
        {kpis.length === 0 ? (
          <div className="ep-warning">
            No KPIs configured for {detail.ticker}. Key metrics could not be personalized.
            <button className="ep-btn ep-btn--small" style={{ marginLeft: 8 }} onClick={() => setEditingKpis(true)}>
              Select KPIs
            </button>
          </div>
        ) : (
          <div className="ep-kpi-tags">
            {kpis.map((k: string) => (
              <span key={k} className="ep-kpi-tag">{k.replace(/_/g, " ")}</span>
            ))}
          </div>
        )}
        {editingKpis && (
          <KpiModal
            ticker={detail.ticker as string}
            initialSelected={kpis}
            onConfirm={handleSaveKpis}
            onCancel={() => setEditingKpis(false)}
          />
        )}
      </div>

      {/* Value / YoY toggle — shared by both tables */}
      <div className="ep-view-toggle" style={{ marginTop: "0.5rem" }}>
        <button className={`ep-toggle-btn${viewMode === "value" ? " ep-toggle-btn--active" : ""}`} onClick={() => setViewMode("value")}>$ Value</button>
        <button className={`ep-toggle-btn${viewMode === "yoy" ? " ep-toggle-btn--active" : ""}`} onClick={() => setViewMode("yoy")}>YoY Growth</button>
      </div>

      {/* Consolidated overview table */}
      <div className="ep-section">
        <h4>Quarterly Overview</h4>
        <ConsolidatedTable detail={detail} estimates={estimates} viewMode={viewMode} />
      </div>

      {/* Estimates Deepdive */}
      <div className="ep-section">
        <h4>Estimates Deepdive — {detail.reporting_period}</h4>
        <EstimatesDeepdive ticker={detail.ticker} period={detail.reporting_period} kpis={kpis} viewMode={viewMode} />
      </div>

    </div>
  );
}

/**
 * Estimates Deepdive: rows = sources/analysts, columns = metrics.
 * Internal at top, then consensus, then each buyside/sellside analyst.
 * Shows the full analyst-level breakdown for the reporting quarter.
 */
function EstimatesDeepdive({
  ticker,
  period,
  kpis,
  viewMode,
}: {
  ticker: string;
  period: string;
  kpis: string[];
  viewMode: "value" | "yoy";
}) {
  const [data, setData] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!ticker || !period) return;
    (async () => {
      setLoading(true);
      try {
        const rows = await fetchEstimatesDeepdive(ticker, period);
        setData(rows);
      } catch {
        setData([]);
      } finally {
        setLoading(false);
      }
    })();
  }, [ticker, period]);

  if (loading) return <div className="ep-muted">Loading estimates...</div>;
  if (data.length === 0) return <div className="ep-muted">No estimates available for {ticker} {period}.</div>;

  // Only show selected KPIs as columns
  const allMetrics = [...new Set(data.map((r) => r.metric as string))];
  const metricOrder = kpis.length > 0
    ? kpis.filter((k) => allMetrics.includes(k))
    : allMetrics;

  // Build rows: group by source+firm+analyst
  type RowKey = { source: string; firm: string; analyst: string; label: string };
  const rowMap = new Map<string, { key: RowKey; values: Record<string, number | null> }>();

  for (const r of data) {
    const source = r.source as string;
    const firm = (r.firm as string) || "";
    const analyst = (r.analyst_name as string) || "";
    const metric = r.metric as string;
    const rawValue = r.value != null ? Number(r.value) : null;
    const yoyValue = r.yoy_vs_actual != null ? Number(r.yoy_vs_actual) : null;
    const value = viewMode === "yoy" ? yoyValue : rawValue;

    let label: string;
    let rowId: string;
    if (source === "internal") {
      label = analyst ? `Internal — ${analyst}` : "Internal";
      rowId = `internal-${analyst}`;
    } else if (source === "consensus") {
      label = "Consensus";
      rowId = "consensus";
    } else {
      label = analyst ? `${analyst} (${firm})` : firm;
      rowId = `${source}-${firm}-${analyst}`;
    }

    if (!rowMap.has(rowId)) {
      rowMap.set(rowId, { key: { source, firm, analyst, label }, values: {} });
    }
    rowMap.get(rowId)!.values[metric] = value;
  }

  // Sort: internal first, consensus second, then buyside, then sellside
  const sourceOrder: Record<string, number> = { internal: 0, consensus: 1, buyside: 2, sellside: 3 };
  const sortedRows = [...rowMap.values()].sort((a, b) => {
    const sa = sourceOrder[a.key.source] ?? 9;
    const sb = sourceOrder[b.key.source] ?? 9;
    if (sa !== sb) return sa - sb;
    return a.key.label.localeCompare(b.key.label);
  });

  // Get internal row for diff coloring
  const internalRow = sortedRows.find((r) => r.key.source === "internal");

  function cellClass(source: string, metric: string, value: number | null): string {
    if (source === "internal" || !internalRow || value == null) return "";
    const intVal = internalRow.values[metric];
    if (intVal == null) return "";
    // Compare this row's value to our internal estimate
    // Above internal = green (street is higher), below = red (street is lower)
    const diff = ((value - intVal) / Math.abs(intVal)) * 100;
    if (Math.abs(diff) <= 0.5) return "";
    return diff > 0 ? "ep-cell--above" : "ep-cell--below";
  }

  return (
    <div className="ep-deepdive-wrap">
      <table className="ep-table ep-table--deepdive">
        <thead>
          <tr>
            <th>Source</th>
            {metricOrder.map((m) => (
              <th key={m}>{m.replace(/_/g, " ")}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row, i) => {
            const isInternal = row.key.source === "internal";
            const isConsensus = row.key.source === "consensus";
            return (
              <tr
                key={i}
                className={
                  isInternal ? "ep-deepdive__internal" : isConsensus ? "ep-deepdive__consensus" : ""
                }
              >
                <td className="ep-deepdive__source">
                  <span className={`ep-source-dot ep-source-dot--${row.key.source}`} />
                  {row.key.label}
                </td>
                {metricOrder.map((m) => {
                  const val = row.values[m];
                  let display: string;
                  if (val == null) {
                    display = "\u2014";
                  } else if (viewMode === "yoy") {
                    display = `${val >= 0 ? "+" : ""}${val.toFixed(1)}%`;
                  } else {
                    display = formatCurrency(val, true);
                  }
                  return (
                    <td key={m} className={cellClass(row.key.source, m, val)}>
                      {display}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}


/**
 * Consolidated table: 4 quarters across columns.
 * Fetches actuals from the API to populate YoY comp and prev quarter.
 * Estimate quarters: Internal | Consensus | Diff sub-columns.
 */
function ConsolidatedTable({
  detail,
  estimates,
  viewMode,
}: {
  detail: PreviewDetail;
  estimates: PreviewDetail;
  viewMode: "value" | "yoy";
}) {
  const ticker = detail.ticker as string;
  const reportingPeriod: string = estimates.reporting_period ?? "";
  const forwardPeriod: string = estimates.forward_period ?? "";
  const [actualsMap, setActualsMap] = useState<Record<string, Record<string, number>>>({});
  const [periodEnds, setPeriodEnds] = useState<Record<string, string>>({});
  const [beatMiss, setBeatMiss] = useState<Record<string, Record<string, { actual: number; consensus: number; diff_pct: number; verdict: string }>>>({});

  // YoY growth data from the actuals_section
  const yoyGrowth = (detail.actuals_section?.yoy_growth ?? {}) as Record<
    string, Record<string, { current: number; prior: number; growth_pct: number | null }>
  >;

  useEffect(() => {
    if (!ticker || !reportingPeriod) return;
    (async () => {
      try {
        const [actualsResp, bm] = await Promise.all([
          fetchQuarterlyActuals(ticker, reportingPeriod),
          fetchBeatMiss(ticker, reportingPeriod),
        ]);
        setActualsMap(actualsResp.actuals ?? {});
        setPeriodEnds(actualsResp.period_ends ?? {});
        setBeatMiss(bm ?? {});
      } catch { /* ignore */ }
    })();
  }, [ticker, reportingPeriod]);

  if (!reportingPeriod) return <div className="ep-muted">No period data available.</div>;

  type EstEntry = { value: number | null; yoy_vs_actual?: number | null; vs_consensus?: number | null };
  const estMetrics = (estimates.metrics ?? {}) as Record<
    string, Record<string, Record<string, EstEntry>>
  >;

  const rpMatch = reportingPeriod.match(/^(\d{4})Q(\d)$/);
  const rpYear = rpMatch ? parseInt(rpMatch[1]) : 0;
  const rpQ = rpMatch ? parseInt(rpMatch[2]) : 0;
  const prevQLabel = rpQ === 1 ? `${rpYear - 1}Q4` : `${rpYear}Q${rpQ - 1}`;
  const yoyQLabel = `${rpYear - 1}Q${rpQ}`;

  const kpis = (detail.key_kpis ?? []) as string[];
  const allMetrics = kpis.length > 0 ? kpis : [...new Set([...Object.keys(estMetrics)])];

  if (allMetrics.length === 0) {
    return <div className="ep-muted">No data available for consolidated view.</div>;
  }

  // Format helpers
  function fmtVal(value: number | null, metric: string): string {
    if (value == null) return "\u2014";
    if (viewMode === "yoy") {
      const sign = value >= 0 ? "+" : "";
      return `${sign}${value.toFixed(1)}%`;
    }
    const isEps = metric.includes("eps");
    if (isEps) return `$${value.toFixed(2)}`;
    if (Math.abs(value) >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
    if (Math.abs(value) >= 1e6) return `$${(value / 1e6).toFixed(0)}M`;
    return `$${value.toFixed(2)}`;
  }

  function fmtDiff(value: number | null, metric: string): string {
    if (value == null) return "\u2014";
    const sign = value >= 0 ? "+" : "";
    if (viewMode === "yoy") return `${sign}${value.toFixed(1)}pp`;
    const isEps = metric.includes("eps");
    if (isEps) return `${sign}$${value.toFixed(2)}`;
    if (Math.abs(value) >= 1e9) return `${sign}$${(value / 1e9).toFixed(1)}B`;
    if (Math.abs(value) >= 1e6) return `${sign}$${(value / 1e6).toFixed(0)}M`;
    return `${sign}$${value.toFixed(2)}`;
  }

  function ActualCell({ metric, posLabel }: { metric: string; posLabel: string }) {
    const bm = beatMiss[posLabel]?.[metric] as
      | { actual: number; consensus: number; diff_pct: number; verdict: string }
      | undefined;

    if (viewMode === "yoy") {
      const pe = periodEnds[posLabel];
      if (!pe) return <td>{"\u2014"}</td>;
      const growth = yoyGrowth[pe]?.[metric]?.growth_pct;
      if (growth == null) return <td>{"\u2014"}</td>;
      const cls = bm ? `ep-actual--${bm.verdict}` : "";
      return (
        <td className={cls}>
          {`${growth >= 0 ? "+" : ""}${growth.toFixed(1)}%`}
          {bm && bm.verdict !== "inline" && (
            <span className={`ep-actual__vs ep-actual__vs--${bm.verdict}`}>
              {bm.verdict === "beat" ? "Beat" : "Miss"} {Math.abs(bm.diff_pct).toFixed(1)}%
            </span>
          )}
        </td>
      );
    }

    const val = actualsMap[posLabel]?.[metric];
    if (val == null) return <td>{"\u2014"}</td>;
    const cls = bm ? `ep-actual--${bm.verdict}` : "";
    return (
      <td className={cls}>
        {fmtVal(val, metric)}
        {bm && bm.verdict !== "inline" && (
          <span className={`ep-actual__vs ep-actual__vs--${bm.verdict}`}>
            vs {fmtVal(bm.consensus, metric)}
          </span>
        )}
      </td>
    );
  }

  function getEstDisplay(metric: string, period: string, source: string): string {
    const entry = estMetrics[metric]?.[period]?.[source];
    if (!entry || entry.value == null) return "\u2014";
    if (viewMode === "yoy") {
      const yoy = entry.yoy_vs_actual;
      if (yoy == null) return "\u2014";
      return `${yoy >= 0 ? "+" : ""}${yoy.toFixed(1)}%`;
    }
    return fmtVal(entry.value, metric);
  }

  function getDiffDisplay(metric: string, period: string): { text: string; cls: string } {
    const internal = estMetrics[metric]?.[period]?.["Internal"];
    const consensus = estMetrics[metric]?.[period]?.["Consensus"];
    if (!internal?.value || !consensus?.value) return { text: "\u2014", cls: "" };

    if (viewMode === "yoy") {
      const intYoy = internal.yoy_vs_actual;
      const conYoy = consensus.yoy_vs_actual;
      if (intYoy == null || conYoy == null) return { text: "\u2014", cls: "" };
      const diff = intYoy - conYoy;
      const cls = Math.abs(diff) <= 0.5 ? "ep-diff--inline" : diff > 0 ? "ep-diff--beat" : "ep-diff--miss";
      return { text: fmtDiff(diff, metric), cls };
    }

    // Value mode: use vs_consensus from data, or calculate
    const diff = internal.vs_consensus ?? (internal.value - consensus.value);
    const pct = consensus.value !== 0 ? (diff / Math.abs(consensus.value)) * 100 : 0;
    const cls = Math.abs(pct) <= 0.5 ? "ep-diff--inline" : diff > 0 ? "ep-diff--beat" : "ep-diff--miss";
    return { text: fmtDiff(diff, metric), cls };
  }

  const estPeriods = [
    { key: reportingPeriod, label: reportingPeriod },
    ...(forwardPeriod ? [{ key: forwardPeriod, label: forwardPeriod }] : []),
  ];

  return (
    <div>
    <table className="ep-table ep-table--consolidated">
      <thead>
        <tr>
          <th rowSpan={2}>Metric</th>
          <th rowSpan={2}>{yoyQLabel}<div className="ep-table__sub-header">YoY Comp</div></th>
          <th rowSpan={2}>{prevQLabel}<div className="ep-table__sub-header">Prev Quarter</div></th>
          {estPeriods.map((p) => (
            <th key={p.key} colSpan={3} className="ep-table__est-header">
              {p.label} <span className="ep-table__est-tag">Est</span>
            </th>
          ))}
        </tr>
        <tr>
          {estPeriods.map((p) => (
            <Fragment key={p.key + "-sub"}>
              <th className="ep-table__sub-header ep-table__est-header">Internal</th>
              <th className="ep-table__sub-header ep-table__est-header">Consensus</th>
              <th className="ep-table__sub-header ep-table__est-header">Diff</th>
            </Fragment>
          ))}
        </tr>
      </thead>
      <tbody>
        {allMetrics.map((metric) => {
          const diffData = estPeriods.map((p) => getDiffDisplay(metric, p.key));
          return (
            <tr key={metric}>
              <td>{metric.replace(/_/g, " ")}</td>
              <ActualCell metric={metric} posLabel="yoy_comp" />
              <ActualCell metric={metric} posLabel="prev_quarter" />
              {estPeriods.map((p, i) => {
                const d = diffData[i];
                return (
                  <Fragment key={p.key}>
                    <td className="ep-table__est-cell">
                      {getEstDisplay(metric, p.key, "Internal")}
                    </td>
                    <td className="ep-table__est-cell">
                      {getEstDisplay(metric, p.key, "Consensus")}
                    </td>
                    <td className={`ep-table__est-cell ${d.cls}`}>
                      {d.text}
                    </td>
                  </Fragment>
                );
              })}
            </tr>
          );
        })}
      </tbody>
    </table>
    </div>
  );
}



function PriceTab({ detail }: { detail: PreviewDetail }) {
  const portfolio = detail.portfolio_section ?? {};
  const positions = portfolio.positions as Array<Record<string, number | string>> | undefined;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [priceCtx, setPriceCtx] = useState<Record<string, any> | null>(null);
  const [loadingPrice, setLoadingPrice] = useState(true);

  useEffect(() => {
    if (!detail.ticker) return;
    (async () => {
      setLoadingPrice(true);
      try {
        const data = await fetchPriceContext(detail.ticker);
        setPriceCtx(data as Record<string, unknown>);
      } catch { setPriceCtx(null); }
      finally { setLoadingPrice(false); }
    })();
  }, [detail.ticker]);

  const ticker = detail.ticker as string;
  const summary = priceCtx?.summary as Record<string, Record<string, number | null>> | undefined;
  const chart = priceCtx?.chart as { ticker_prices: { date: string; close: number }[]; spy_prices: { date: string; close: number }[] } | undefined;
  const asOfDate = priceCtx?.as_of_date as string | undefined;

  function fmtRet(v: number | null | undefined) {
    if (v == null) return "\u2014";
    const cls = v >= 0 ? "ep-green" : "ep-red";
    return <span className={cls}>{v >= 0 ? "+" : ""}{v.toFixed(1)}%</span>;
  }
  function fmtPct(v: number | null | undefined) {
    if (v == null) return "\u2014";
    return `${v.toFixed(1)}%`;
  }
  function fmtPrice(v: number | null | undefined) {
    if (v == null) return "\u2014";
    return `$${Number(v).toFixed(2)}`;
  }

  // Build indexed Plotly chart
  const priceChart = (() => {
    if (!chart?.ticker_prices?.length) return null;
    const tp = chart.ticker_prices;
    const sp = chart.spy_prices;
    const base_t = tp[0].close;
    const base_s = sp.length > 0 ? sp[0].close : 1;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const data: any[] = [
      { type: "scatter", mode: "lines", name: ticker, x: tp.map((p: { date: string }) => p.date), y: tp.map((p: { close: number }) => (p.close / base_t) * 100), line: { color: "#3b82f6", width: 2 } },
      ...(sp.length > 0 ? [{ type: "scatter", mode: "lines", name: "S&P 500", x: sp.map((p: { date: string }) => p.date), y: sp.map((p: { close: number }) => (p.close / base_s) * 100), line: { color: "#94a3b8", width: 1.5, dash: "dash" } }] : []),
    ];
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const layout: any = {
      paper_bgcolor: "transparent", plot_bgcolor: "transparent",
      font: { family: "Inter, system-ui, sans-serif", size: 11 },
      margin: { l: 50, r: 20, t: 20, b: 40 },
      showlegend: true, legend: { orientation: "h", y: -0.12, x: 0.5, xanchor: "center", font: { size: 10 }, tracegroupgap: 5 },
      xaxis: { type: "date", tickformat: "%b '%y", hoverformat: "%-m/%-d/%Y", nticks: 8, gridcolor: "#e2e8f0", tickfont: { size: 10 } },
      yaxis: { title: { text: "Indexed (100)", font: { size: 10 } }, gridcolor: "#e2e8f0", griddash: "dash", tickfont: { size: 10 } },
      hovermode: "x unified", autosize: true,
    };
    return { data, layout };
  })();

  return (
    <div className="ep-summary">
      {/* Price comparison table */}
      <div className="ep-section">
        <h4>Price Overview {asOfDate && <span className="ep-muted">as of {asOfDate}</span>}</h4>
        {loadingPrice ? (
          <div className="ep-muted">Loading price data...</div>
        ) : summary ? (
          <table className="ep-table">
            <thead>
              <tr>
                <th>Ticker</th><th>Last Close</th><th>52W High</th><th>% of High</th>
                <th>52W Low</th><th>% of Low</th><th>YTD Return</th><th>90D Return</th>
              </tr>
            </thead>
            <tbody>
              {[ticker, "SPY"].map((sym) => {
                const s = summary[sym];
                if (!s) return null;
                return (
                  <tr key={sym}>
                    <td style={{ fontWeight: sym === ticker ? 700 : 400 }}>{sym}</td>
                    <td>{fmtPrice(s.last_close)}</td>
                    <td>{fmtPrice(s.high_52w)}</td>
                    <td>{fmtPct(s.pct_of_52w_high)}</td>
                    <td>{fmtPrice(s.low_52w)}</td>
                    <td>{fmtPct(s.pct_of_52w_low)}</td>
                    <td>{fmtRet(s.ytd_return)}</td>
                    <td>{fmtRet(s.return_90d)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <div className="ep-muted">No price data available.</div>
        )}
      </div>

      {/* 180-day indexed chart */}
      {priceChart && (
        <div className="ep-section">
          <h4>180-Day Price (Indexed to 100)</h4>
          <Suspense fallback={<div className="ep-muted">Loading chart...</div>}>
            <div style={{ border: "1px solid var(--color-border)", borderRadius: "var(--radius)", padding: "8px 0" }}>
              <LazyPlot data={priceChart.data} layout={priceChart.layout} config={PLOTLY_CFG} style={{ width: "100%", height: "300px" }} useResizeHandler />
            </div>
          </Suspense>
        </div>
      )}

      {/* Portfolio positions */}
      <div className="ep-section">
        <h4>Portfolio Positions</h4>
        {!positions || positions.length === 0 ? (
          <div className="ep-muted">{portfolio.note || "Not currently held in any portfolio."}</div>
        ) : (
          <table className="ep-table">
            <thead>
              <tr>
                <th>Portfolio</th><th>Side</th><th>Shares</th>
                <th>Market Value</th><th>Unrealized P&L</th><th>Weight</th>
                <th>ITD Return</th><th>YTD P&L</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((pos, i) => (
                <tr key={i}>
                  <td>{pos.portfolio}</td>
                  <td>{pos.side}</td>
                  <td>{Number(pos.shares_held).toLocaleString()}</td>
                  <td>{formatCurrency(Number(pos.market_value))}</td>
                  <td className={Number(pos.unrealized_pnl) >= 0 ? "ep-green" : "ep-red"}>
                    {formatCurrency(Number(pos.unrealized_pnl))}
                  </td>
                  <td>{pos.position_weight != null ? `${Number(pos.position_weight).toFixed(1)}%` : "\u2014"}</td>
                  <td className={Number(pos.cumulative_return) >= 0 ? "ep-green" : "ep-red"}>
                    {Number(pos.cumulative_return).toFixed(1)}%
                  </td>
                  <td className={Number(pos.ytd_pnl || 0) >= 0 ? "ep-green" : "ep-red"}>
                    {pos.ytd_pnl != null ? formatCurrency(Number(pos.ytd_pnl)) : "\u2014"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function AltDataTab({ detail, onDetailUpdated: _onDetailUpdated }: { detail: PreviewDetail; onDetailUpdated: () => void }) {
  const ticker = detail.ticker as string;
  const savedSignals = (detail.selected_alt_signals ?? []) as string[];
  const [available, setAvailable] = useState<{ data_type: string; frequency: string; vendor: string }[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!ticker) return;
    (async () => {
      setLoading(true);
      try {
        const signals = await fetchAvailableAltData(ticker);
        setAvailable(signals);
        // Use saved selection if exists, otherwise select top 3
        if (savedSignals.length > 0) {
          setSelected(new Set(savedSignals));
        } else {
          setSelected(new Set(signals.slice(0, 3).map((s) => s.data_type)));
        }
      } catch { setAvailable([]); }
      finally { setLoading(false); }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker]);

  if (loading) return <div className="ep-muted">Loading alt data signals...</div>;
  if (available.length === 0) {
    return <div className="ep-muted">No alternative data available for {ticker}. Alt data is currently available for CMG, DPZ, and SBUX.</div>;
  }

  const toggle = (dt: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(dt)) next.delete(dt); else next.add(dt);
      // Save selection to backend
      updatePreviewSettings(detail.id as string, { selected_alt_signals: [...next] }).catch(() => {});
      return next;
    });
  };

  return (
    <div className="ep-summary">
      {/* Signal selection */}
      <div className="ep-section">
        <h4>Alt Data Signals</h4>
        <div className="ep-kpi-tags">
          {available.map((s) => (
            <button
              key={s.data_type}
              className={`ep-kpi-tag-btn${selected.has(s.data_type) ? " ep-kpi-tag-btn--active" : ""}`}
              onClick={() => toggle(s.data_type)}
            >
              {selected.has(s.data_type) ? "\u2713 " : ""}
              {s.data_type.replace(/_/g, " ")}
              <span className="ep-muted" style={{ marginLeft: 4, fontSize: "0.65rem" }}>{s.vendor}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Charts for each selected signal */}
      {[...selected].map((dt) => (
        <AltDataSignalChart key={dt} ticker={ticker} dataType={dt} />
      ))}
    </div>
  );
}

function AltDataSignalChart({ ticker, dataType }: { ticker: string; dataType: string }) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [data, setData] = useState<Record<string, any> | null>(null);
  const [view, setView] = useState<"weekly" | "quarterly">("quarterly");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const d = await fetchAltDataChart(ticker, dataType);
        setData(d);
        // Default to quarterly if available, else weekly
        if (!(d as Record<string, unknown[]>).quarterly?.length) setView("weekly");
      } catch { setData(null); }
      finally { setLoading(false); }
    })();
  }, [ticker, dataType]);

  if (loading) return <div className="ep-muted">Loading {dataType.replace(/_/g, " ")}...</div>;
  if (!data) return <div className="ep-muted">No data for {dataType}.</div>;

  const weekly = (data.weekly ?? []) as { date: string; growth: number | null }[];
  const quarterly = (data.quarterly ?? []) as { quarter: string; avg_growth: number | null }[];
  const revQuarterly = (data.revenue_quarterly ?? []) as { quarter_end: string; revenue_yoy_growth: number | null }[];
  const consensusQuarterly = (data.consensus_revenue_quarterly ?? []) as { quarter: string; consensus_revenue_yoy: number | null }[];
  const hasQuarterly = quarterly.length > 0;

  // Build Plotly chart
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let plotData: any[] | null = null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let plotLayout: any = null;

  const basePlotLayout = {
    paper_bgcolor: "transparent", plot_bgcolor: "transparent",
    font: { family: "Inter, system-ui, sans-serif", size: 11 },
    showlegend: true, legend: { orientation: "h" as const, y: -0.12, x: 0.5, xanchor: "center" as const, font: { size: 10 }, tracegroupgap: 5 },
    xaxis: { gridcolor: "#e2e8f0", tickfont: { size: 10 } },
    yaxis: { title: { text: "YoY %", font: { size: 10 } }, gridcolor: "#e2e8f0", griddash: "dash", tickfont: { size: 10 }, tickformat: ".0f", ticksuffix: "%" },
    hovermode: "x unified" as const, autosize: true,
  };

  if (view === "quarterly" && hasQuarterly) {
    const revByQ: Record<string, number> = {};
    for (const r of revQuarterly) {
      const d = new Date(r.quarter_end);
      const qStart = new Date(d.getFullYear(), Math.floor(d.getMonth() / 3) * 3, 1);
      revByQ[qStart.toISOString().slice(0, 10)] = r.revenue_yoy_growth ?? 0;
    }
    const consByQ: Record<string, number | null> = {};
    for (const r of consensusQuarterly) { consByQ[r.quarter] = r.consensus_revenue_yoy; }

    const categories = quarterly.map((q) => q.quarter);
    const qLabels = categories.map((q) => {
      const d = new Date(q);
      return `Q${Math.floor(d.getMonth() / 3) + 1}'${String(d.getFullYear()).slice(2)}`;
    });

    plotData = [
      { type: "scatter", mode: "lines+markers", name: dataType.replace(/_/g, " "), x: qLabels, y: quarterly.map((q) => q.avg_growth), line: { color: "#3b82f6", width: 2 }, marker: { size: 4 }, hovertemplate: "%{y:.1f}%<extra>%{fullData.name}</extra>" },
      { type: "scatter", mode: "lines+markers", name: "Revenue YoY (Actual)", x: qLabels, y: categories.map((q) => revByQ[q] ?? null), line: { color: "#f59e0b", width: 2 }, marker: { size: 5 }, hovertemplate: "%{y:.1f}%<extra>Revenue YoY</extra>" },
      { type: "scatter", mode: "lines+markers", name: "Revenue YoY (Consensus)", x: qLabels, y: categories.map((q) => consByQ[q] ?? null), line: { color: "#ef4444", width: 2, dash: "dash" }, marker: { size: 6, symbol: "diamond" }, hovertemplate: "%{y:.1f}%<extra>Consensus</extra>" },
    ];
    plotLayout = { ...basePlotLayout, margin: { l: 50, r: 20, t: 20, b: 50 } };
  } else {
    plotData = [
      { type: "scatter", mode: "lines", name: dataType.replace(/_/g, " "), x: weekly.map((w) => w.date), y: weekly.map((w) => w.growth), line: { color: "#3b82f6", width: 1.5 }, hovertemplate: "%{y:.1f}%<extra>%{fullData.name}</extra>" },
    ];
    plotLayout = { ...basePlotLayout, margin: { l: 50, r: 20, t: 20, b: 30 }, yaxis: { ...basePlotLayout.yaxis, title: { text: "YoY Growth %", font: { size: 10 } } } };
  }

  return (
    <div className="ep-section">
      <div className="ep-altchart__header">
        <h4>{dataType.replace(/_/g, " ")}</h4>
        <div className="ep-altchart__toggle">
          {hasQuarterly && (
            <button
              className={`ep-altchart__btn${view === "quarterly" ? " ep-altchart__btn--active" : ""}`}
              onClick={() => setView("quarterly")}
            >
              Quarterly
            </button>
          )}
          <button
            className={`ep-altchart__btn${view === "weekly" ? " ep-altchart__btn--active" : ""}`}
            onClick={() => setView("weekly")}
          >
            Weekly
          </button>
        </div>
      </div>
      {plotData && (
        <Suspense fallback={<div className="ep-muted">Loading chart...</div>}>
          <div style={{ border: "1px solid var(--color-border)", borderRadius: "var(--radius)", padding: "8px 0" }}>
            <LazyPlot data={plotData} layout={plotLayout} config={PLOTLY_CFG} style={{ width: "100%", height: "280px" }} useResizeHandler />
          </div>
        </Suspense>
      )}
    </div>
  );
}

function PriorPreviewTab({ detail }: { detail: PreviewDetail }) {
  const prior = detail.prior_preview_reference;
  if (!prior) return <div className="ep-muted">This is the first preview generated for {detail.ticker}.</div>;
  return (
    <div className="ep-summary">
      <div className="ep-section">
        <h4>Prior Preview</h4>
        <table className="ep-table">
          <tbody>
            <tr><td>Prior Period</td><td>{prior.prior_reporting_period}</td></tr>
            <tr><td>Generated</td><td>{prior.prior_generated_at}</td></tr>
            <tr><td>KPIs</td><td>{(prior.prior_key_kpis ?? []).join(", ") || "\u2014"}</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CitationsTab({ detail }: { detail: PreviewDetail }) {
  const citations = detail.citations as Array<Record<string, string>> | undefined;
  if (!citations || citations.length === 0) {
    return <div className="ep-muted">No citations recorded for this preview.</div>;
  }
  return (
    <div className="ep-summary">
      <table className="ep-table">
        <thead>
          <tr><th>Source</th><th>Metric</th><th>Period</th><th>Citation</th></tr>
        </thead>
        <tbody>
          {citations.map((c, i) => (
            <tr key={i}>
              <td>{c.source}</td>
              <td>{c.metric}</td>
              <td>{c.period}</td>
              <td className="ep-muted">{c.citation}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
