#!/usr/bin/env python3
"""GoldMine Daily Usage & Cost Report.

Queries api_cost_events, builds an HTML email report, and sends it.
Designed to run daily via cron or the scheduler.

Usage:
    python scripts/send_cost_report.py              # Send yesterday's report
    python scripts/send_cost_report.py --preview    # Print HTML to stdout
    python scripts/send_cost_report.py --date 2026-03-20
    python scripts/send_cost_report.py --no-send    # Query data but don't send

# Future enhancements:
# - Add tools_used column to api_cost_events so tool-level usage is trackable
# - Add error column to api_cost_events so failed queries are visible in report
# - Add user_display_name join to show which analysts are using the system most
# - Add weekly summary email (Mondays) with prior week comparison
# - Add cost forecast based on usage trends
# - Add per-analyst cost breakdown for chargeback or awareness purposes
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import psycopg2
import structlog
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
load_dotenv(ROOT / "backend" / ".env")

DATABASE_URL = os.environ.get("SUPABASE_DATABASE_URL", "")
RECIPIENT = "kevintdonadio@gmail.com"

logger = structlog.get_logger(__name__)

# Friendly query type names
QUERY_TYPE_LABELS = {
    "single_ticker_qualitative": "Single ticker — qualitative",
    "single_ticker_quantitative": "Single ticker — quantitative",
    "cross_ticker": "Cross ticker comparison",
    "screening": "Universe screening",
    "trend_analysis": "Trend analysis",
    "portfolio": "Portfolio query",
    "estimates": "Estimates query",
    "alt_data": "Alternative data",
    "model_query": "Model query",
    "model_edit": "Model edit",
    "workflow": "Workflow execution",
}


def _fmt_cost(v: float) -> str:
    return f"${v:,.2f}"


def _fmt_int(v: int) -> str:
    return f"{v:,}"


def _fmt_tokens(v: int) -> str:
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v / 1_000:.1f}K"
    return str(v)


# ---------------------------------------------------------------------------
# Data queries
# ---------------------------------------------------------------------------

def fetch_report_data(report_date: date) -> dict:
    """Run all report queries and return structured data."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    data: dict = {"report_date": report_date}

    ds = str(report_date)

    # Yesterday summary
    cur.execute("SELECT COUNT(DISTINCT session_id) FROM api_cost_events WHERE DATE(created_at) = %s AND component = 'response_generator'", (ds,))
    data["queries"] = cur.fetchone()[0] or 0

    cur.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM api_cost_events WHERE DATE(created_at) = %s", (ds,))
    data["total_cost"] = float(cur.fetchone()[0])

    cur.execute("SELECT COUNT(DISTINCT user_id), COUNT(DISTINCT session_id) FROM api_cost_events WHERE DATE(created_at) = %s", (ds,))
    row = cur.fetchone()
    data["users"] = row[0] or 0
    data["sessions"] = row[1] or 0
    data["avg_cost"] = data["total_cost"] / max(data["queries"], 1)

    # By component
    cur.execute("""
        SELECT component, COUNT(*), SUM(cost_usd), AVG(cost_usd), SUM(input_tokens), SUM(output_tokens)
        FROM api_cost_events WHERE DATE(created_at) = %s GROUP BY component ORDER BY SUM(cost_usd) DESC
    """, (ds,))
    data["by_component"] = [
        {"component": r[0], "calls": r[1], "cost": float(r[2] or 0), "avg_cost": float(r[3] or 0),
         "input_tokens": r[4] or 0, "output_tokens": r[5] or 0}
        for r in cur.fetchall()
    ]

    # By query type
    cur.execute("""
        SELECT query_type, COUNT(*), SUM(cost_usd), AVG(cost_usd), MAX(cost_usd), SUM(input_tokens), SUM(output_tokens)
        FROM api_cost_events WHERE DATE(created_at) = %s AND query_type IS NOT NULL AND component = 'response_generator'
        GROUP BY query_type ORDER BY SUM(cost_usd) DESC
    """, (ds,))
    data["by_query_type"] = [
        {"query_type": r[0], "label": QUERY_TYPE_LABELS.get(r[0], r[0]), "queries": r[1],
         "cost": float(r[2] or 0), "avg_cost": float(r[3] or 0), "max_cost": float(r[4] or 0),
         "input_tokens": r[5] or 0, "output_tokens": r[6] or 0}
        for r in cur.fetchall()
    ]

    # Top 5 expensive queries
    cur.execute("""
        SELECT query_type, input_tokens, output_tokens, cost_usd, ticker_count, created_at
        FROM api_cost_events WHERE DATE(created_at) = %s AND component = 'response_generator'
        ORDER BY cost_usd DESC LIMIT 5
    """, (ds,))
    data["top_queries"] = [
        {"query_type": r[0], "input_tokens": r[1] or 0, "output_tokens": r[2] or 0,
         "cost": float(r[3] or 0), "ticker_count": r[4] or 0, "time": r[5]}
        for r in cur.fetchall()
    ]

    # 7-day trend
    cur.execute("""
        SELECT DATE(created_at) as day, COUNT(DISTINCT session_id),
               COUNT(*) FILTER (WHERE component = 'response_generator'), SUM(cost_usd)
        FROM api_cost_events WHERE created_at >= CURRENT_DATE - 7
        GROUP BY day ORDER BY day ASC
    """)
    data["trend_7d"] = [
        {"day": r[0], "sessions": r[1] or 0, "responses": r[2] or 0, "cost": float(r[3] or 0)}
        for r in cur.fetchall()
    ]

    # YTD
    cur.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM api_cost_events WHERE DATE_TRUNC('year', created_at) = DATE_TRUNC('year', CURRENT_DATE)")
    data["ytd_cost"] = float(cur.fetchone()[0])

    cur.execute("""
        SELECT component, COUNT(*), SUM(cost_usd)
        FROM api_cost_events WHERE DATE_TRUNC('year', created_at) = DATE_TRUNC('year', CURRENT_DATE)
        GROUP BY component ORDER BY SUM(cost_usd) DESC
    """)
    data["ytd_by_component"] = [
        {"component": r[0], "calls": r[1], "cost": float(r[2] or 0)}
        for r in cur.fetchall()
    ]

    cur.execute("""
        SELECT query_type, COUNT(*), SUM(cost_usd), AVG(cost_usd)
        FROM api_cost_events WHERE DATE_TRUNC('year', created_at) = DATE_TRUNC('year', CURRENT_DATE)
        AND query_type IS NOT NULL AND component = 'response_generator'
        GROUP BY query_type ORDER BY SUM(cost_usd) DESC
    """)
    data["ytd_by_query_type"] = [
        {"query_type": r[0], "label": QUERY_TYPE_LABELS.get(r[0], r[0]), "queries": r[1],
         "cost": float(r[2] or 0), "avg_cost": float(r[3] or 0)}
        for r in cur.fetchall()
    ]

    cur.execute("""
        SELECT DATE_TRUNC('month', created_at)::date, COUNT(DISTINCT session_id), SUM(cost_usd)
        FROM api_cost_events WHERE DATE_TRUNC('year', created_at) = DATE_TRUNC('year', CURRENT_DATE)
        GROUP BY DATE_TRUNC('month', created_at) ORDER BY DATE_TRUNC('month', created_at) ASC
    """)
    data["ytd_monthly"] = [
        {"month": r[0], "sessions": r[1] or 0, "cost": float(r[2] or 0)}
        for r in cur.fetchall()
    ]

    # Projected annual
    day_of_year = report_date.timetuple().tm_yday
    data["projected_annual"] = (data["ytd_cost"] / max(day_of_year, 1)) * 365

    # Anomalies
    data["anomalies"] = []
    cur.execute("SELECT COUNT(*), MAX(cost_usd) FROM api_cost_events WHERE DATE(created_at) = %s AND cost_usd > 0.50", (ds,))
    row = cur.fetchone()
    if row[0] and row[0] > 0:
        data["anomalies"].append({"level": "warning", "msg": f"{row[0]} queries exceeded $0.50 (max: ${float(row[1]):.2f})"})
    if data["total_cost"] > 10.0:
        data["anomalies"].append({"level": "warning", "msg": f"Daily cost ${data['total_cost']:.2f} exceeds $10 threshold"})
    if data["queries"] == 0:
        data["anomalies"].append({"level": "info", "msg": "No queries yesterday — system may not have been used"})

    cur.close()
    conn.close()
    return data


# ---------------------------------------------------------------------------
# HTML email builder
# ---------------------------------------------------------------------------

def _stat_box(label: str, value: str, sub: str = "") -> str:
    return (
        f'<td style="width:25%;padding:8px;text-align:center;background:#f7f8fa;border-radius:6px;">'
        f'<div style="font-size:11px;color:#718096;text-transform:uppercase;margin-bottom:4px;">{label}</div>'
        f'<div style="font-size:20px;font-weight:700;color:#1a202c;">{value}</div>'
        f'{"<div style=&quot;font-size:11px;color:#718096;&quot;>" + sub + "</div>" if sub else ""}'
        f'</td>'
    )


def _table_header(*cols: str) -> str:
    cells = "".join(
        f'<th style="text-align:{"right" if i > 0 else "left"};padding:6px 10px;background:#f7f8fa;'
        f'border-bottom:2px solid #e2e8f0;font-weight:500;font-size:12px;color:#4a5568;">{c}</th>'
        for i, c in enumerate(cols)
    )
    return f"<tr>{cells}</tr>"


def _table_row(*vals: str, highlight: bool = False) -> str:
    bg = "background:#fffbeb;" if highlight else ""
    cells = "".join(
        f'<td style="text-align:{"right" if i > 0 else "left"};padding:6px 10px;border-bottom:1px solid #e2e8f0;'
        f'font-size:12px;{bg}">{v}</td>'
        for i, v in enumerate(vals)
    )
    return f"<tr>{cells}</tr>"


def build_html(data: dict) -> str:
    """Build the full HTML email from report data."""
    rd = data["report_date"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    sections: list[str] = []

    # --- Section 1: Yesterday at a glance ---
    sections.append('<h2 style="color:#1a365d;font-size:16px;margin:0 0 12px 0;">Yesterday at a Glance</h2>')
    sections.append(
        '<table style="width:100%;border-collapse:separate;border-spacing:8px 0;margin-bottom:20px;"><tr>'
        + _stat_box("Total Cost", _fmt_cost(data["total_cost"]), str(rd))
        + _stat_box("Queries", str(data["queries"]), "responses")
        + _stat_box("Active Users", str(data["users"]), f'{data["sessions"]} sessions')
        + _stat_box("Avg Cost/Query", _fmt_cost(data["avg_cost"]))
        + '</tr></table>'
    )

    # --- Section 2: By component ---
    if data["by_component"]:
        sections.append('<h2 style="color:#1a365d;font-size:14px;margin:20px 0 8px 0;">Cost by Pipeline Component</h2>')
        rows_html = _table_header("Component", "Calls", "Total Cost", "Avg Cost", "Input Tokens", "Output Tokens")
        total_calls = total_cost = total_in = total_out = 0
        for r in data["by_component"]:
            rows_html += _table_row(
                r["component"], _fmt_int(r["calls"]), _fmt_cost(r["cost"]),
                _fmt_cost(r["avg_cost"]), _fmt_tokens(r["input_tokens"]), _fmt_tokens(r["output_tokens"]),
                highlight=r["cost"] > 0.25,
            )
            total_calls += r["calls"]
            total_cost += r["cost"]
            total_in += r["input_tokens"]
            total_out += r["output_tokens"]
        rows_html += _table_row(
            "<b>TOTAL</b>", f"<b>{_fmt_int(total_calls)}</b>", f"<b>{_fmt_cost(total_cost)}</b>",
            f"<b>{_fmt_cost(total_cost / max(total_calls, 1))}</b>",
            f"<b>{_fmt_tokens(total_in)}</b>", f"<b>{_fmt_tokens(total_out)}</b>",
        )
        sections.append(f'<table style="width:100%;border-collapse:collapse;margin-bottom:16px;">{rows_html}</table>')

    # --- Section 3: By query type ---
    if data["by_query_type"]:
        sections.append('<h2 style="color:#1a365d;font-size:14px;margin:20px 0 8px 0;">Cost by Query Type</h2>')
        rows_html = _table_header("Query Type", "Queries", "Total Cost", "Avg Cost", "Max Cost", "Input Tokens")
        for r in data["by_query_type"]:
            rows_html += _table_row(
                r["label"], str(r["queries"]), _fmt_cost(r["cost"]),
                _fmt_cost(r["avg_cost"]), _fmt_cost(r["max_cost"]), _fmt_tokens(r["input_tokens"]),
                highlight=r == data["by_query_type"][0],
            )
        sections.append(f'<table style="width:100%;border-collapse:collapse;margin-bottom:16px;">{rows_html}</table>')

    # --- Section 4: Top 5 expensive ---
    if data["top_queries"]:
        sections.append('<h2 style="color:#1a365d;font-size:14px;margin:20px 0 8px 0;">Top 5 Most Expensive Queries</h2>')
        rows_html = _table_header("Time", "Query Type", "Tickers", "Cost", "Tokens")
        for r in data["top_queries"]:
            t = r["time"].strftime("%H:%M") if r["time"] else ""
            label = QUERY_TYPE_LABELS.get(r["query_type"] or "", r["query_type"] or "—")
            rows_html += _table_row(
                t, label, str(r["ticker_count"]), _fmt_cost(r["cost"]),
                _fmt_tokens(r["input_tokens"] + r["output_tokens"]),
                highlight=r["cost"] > 0.25,
            )
        sections.append(f'<table style="width:100%;border-collapse:collapse;margin-bottom:16px;">{rows_html}</table>')

    # --- Section 5: 7-day trend ---
    if data["trend_7d"]:
        sections.append('<h2 style="color:#1a365d;font-size:14px;margin:20px 0 8px 0;">7-Day Trend</h2>')
        rows_html = _table_header("Date", "Sessions", "Responses", "Daily Cost")
        max_cost = max((r["cost"] for r in data["trend_7d"]), default=1)
        for r in data["trend_7d"]:
            bar_width = int((r["cost"] / max(max_cost, 0.01)) * 100)
            bar = f'<span style="display:inline-block;width:{bar_width}px;height:10px;background:#d4a843;border-radius:2px;vertical-align:middle;"></span>'
            rows_html += _table_row(
                str(r["day"]), str(r["sessions"]), str(r["responses"]),
                f'{_fmt_cost(r["cost"])} {bar}',
            )
        sections.append(f'<table style="width:100%;border-collapse:collapse;margin-bottom:16px;">{rows_html}</table>')

    # --- Section 6: YTD summary ---
    sections.append('<h2 style="color:#1a365d;font-size:14px;margin:20px 0 8px 0;">Year to Date Summary</h2>')
    day_of_year = rd.timetuple().tm_yday
    avg_daily = data["ytd_cost"] / max(day_of_year, 1)
    sections.append(
        f'<table style="margin-bottom:12px;font-size:13px;">'
        f'<tr><td style="padding:3px 16px 3px 0;color:#718096;">YTD Total Cost</td><td style="font-weight:600;">{_fmt_cost(data["ytd_cost"])}</td></tr>'
        f'<tr><td style="padding:3px 16px 3px 0;color:#718096;">Avg Daily Cost</td><td>{_fmt_cost(avg_daily)}</td></tr>'
        f'<tr><td style="padding:3px 16px 3px 0;color:#718096;">Projected Annual</td><td style="font-weight:600;">{_fmt_cost(data["projected_annual"])}</td></tr>'
        f'</table>'
    )

    if data["ytd_by_component"]:
        rows_html = _table_header("Component", "Calls", "Cost", "% of Total")
        for r in data["ytd_by_component"]:
            pct = (r["cost"] / max(data["ytd_cost"], 0.01)) * 100
            rows_html += _table_row(r["component"], _fmt_int(r["calls"]), _fmt_cost(r["cost"]), f"{pct:.1f}%")
        sections.append(f'<table style="width:100%;border-collapse:collapse;margin-bottom:16px;">{rows_html}</table>')

    # --- Section 7: Monthly breakdown ---
    if data["ytd_monthly"]:
        sections.append('<h2 style="color:#1a365d;font-size:14px;margin:20px 0 8px 0;">Monthly Breakdown (YTD)</h2>')
        rows_html = _table_header("Month", "Sessions", "Cost")
        for r in data["ytd_monthly"]:
            month_label = r["month"].strftime("%b %Y") if hasattr(r["month"], "strftime") else str(r["month"])[:7]
            rows_html += _table_row(month_label, str(r["sessions"]), _fmt_cost(r["cost"]))
        sections.append(f'<table style="width:100%;border-collapse:collapse;margin-bottom:16px;">{rows_html}</table>')

    # --- Section 8: Anomalies ---
    if data["anomalies"]:
        sections.append('<h2 style="color:#1a365d;font-size:14px;margin:20px 0 8px 0;">Anomaly Flags</h2>')
        for a in data["anomalies"]:
            icon = "⚠️" if a["level"] == "warning" else "ℹ️"
            color = "#975a16" if a["level"] == "warning" else "#2b6cb0"
            sections.append(f'<p style="color:{color};font-size:13px;margin:4px 0;">{icon} {a["msg"]}</p>')
    else:
        sections.append('<p style="color:#38a169;font-size:13px;margin:20px 0;">✓ No anomalies detected yesterday</p>')

    # Compose
    body = "\n".join(sections)

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,Helvetica,sans-serif;background:#f7f8fa;margin:0;padding:20px;">
<div style="max-width:800px;margin:0 auto;background:#ffffff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.12);overflow:hidden;">
  <div style="background:#1a365d;padding:16px 24px;">
    <h1 style="color:#d4a843;margin:0;font-size:20px;">GoldMine</h1>
    <p style="color:#a0aec0;margin:4px 0 0 0;font-size:12px;">Daily Usage &amp; Cost Report — {rd} | Generated {now}</p>
  </div>
  <div style="padding:24px;">
    {body}
    <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0 12px 0;">
    <p style="color:#718096;font-size:11px;">
      This report covers api_cost_events for {rd}. Generated by GoldMine reporting pipeline.
    </p>
  </div>
</div>
</body>
</html>"""


def build_text(data: dict) -> str:
    """Build plain text version."""
    rd = data["report_date"]
    lines = [
        f"GoldMine — Daily Usage & Cost Report — {rd}",
        f"Total Cost: {_fmt_cost(data['total_cost'])} | Queries: {data['queries']} | Users: {data['users']}",
        "",
    ]
    if data["by_component"]:
        lines.append("Cost by Component:")
        for r in data["by_component"]:
            lines.append(f"  {r['component']}: {r['calls']} calls, {_fmt_cost(r['cost'])}")
    lines.append(f"\nYTD Cost: {_fmt_cost(data['ytd_cost'])}")
    lines.append(f"Projected Annual: {_fmt_cost(data['projected_annual'])}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------

def send_report(html: str, text: str, subject: str) -> bool:
    """Send via the GoldMine email system."""
    from app.email.factory import get_email_provider
    provider = get_email_provider()
    return provider.send_email(
        recipients=[RECIPIENT],
        subject=subject,
        html_body=html,
        text_body=text,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="GoldMine Daily Usage & Cost Report")
    parser.add_argument("--date", type=str, default=None, help="Report date (YYYY-MM-DD). Default: yesterday.")
    parser.add_argument("--preview", action="store_true", help="Print HTML to stdout instead of sending.")
    parser.add_argument("--send", dest="send", action="store_true", default=True)
    parser.add_argument("--no-send", dest="send", action="store_false")
    args = parser.parse_args()

    if args.date:
        report_date = date.fromisoformat(args.date)
    else:
        report_date = date.today() - timedelta(days=1)

    logger.info("cost_report_start", report_date=str(report_date))

    data = fetch_report_data(report_date)
    html = build_html(data)
    text = build_text(data)
    subject = f"GoldMine Usage Report — {report_date} | {_fmt_cost(data['total_cost'])} yesterday | {_fmt_cost(data['ytd_cost'])} YTD"

    if args.preview:
        print(html)
        return

    if args.send:
        try:
            send_report(html, text, subject)
            logger.info("cost_report_sent", recipient=RECIPIENT, report_date=str(report_date))
            print(f"Report sent to {RECIPIENT}")
        except Exception:
            logger.exception("cost_report_send_failed")
            print("ERROR: Failed to send report. Check SMTP settings.")
            sys.exit(1)
    else:
        print(f"Report generated for {report_date} (not sent)")
        print(f"  Total cost: {_fmt_cost(data['total_cost'])}")
        print(f"  Queries: {data['queries']}")
        print(f"  YTD cost: {_fmt_cost(data['ytd_cost'])}")


if __name__ == "__main__":
    main()
