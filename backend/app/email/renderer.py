from __future__ import annotations

from typing import Any

from app.config.settings import settings
from app.data_access.factory import get_data_provider
from app.data_access.models import FilterParams
from app.email.chart_renderer import render_chart_image
from app.email.models import WidgetOverrideRef
from app.logging_config import get_logger
from app.object_storage.factory import get_storage_provider

logger = get_logger(__name__)


def render_email(
    entity_type: str,
    entity_id: str,
    schedule_name: str,
    widget_ids: list[str] | None = None,
    widget_overrides: list[WidgetOverrideRef] | None = None,
) -> tuple[str, str, str, list[tuple[str, bytes]]]:
    """Render an email for an entity.

    Returns (subject, html_body, text_body, images).
    images is a list of (cid, png_bytes) for inline chart images.
    """
    provider = get_data_provider()

    # Build entity header
    display_name, header_fields = _get_entity_header(entity_type, entity_id)
    subject = f"GoldMine: {display_name} \u2014 {schedule_name}"

    # Build widget configs for this entity
    all_widgets = _get_entity_widgets(entity_type, entity_id)

    # Filter to requested widgets
    if widget_ids is not None:
        all_widgets = [w for w in all_widgets if w["widget_id"] in widget_ids]

    # Build override lookup
    override_map: dict[str, WidgetOverrideRef] = {}
    if widget_overrides:
        for ov in widget_overrides:
            override_map[ov.widget_id] = ov

    # Render each widget's data
    widget_sections_html: list[str] = []
    widget_sections_text: list[str] = []
    images: list[tuple[str, bytes]] = []
    chart_index = 0

    for widget in all_widgets:
        wid = widget["widget_id"]
        title = widget["title"]
        columns = widget.get("columns", [])
        endpoint = widget.get("endpoint", "")
        chart_config = widget.get("chart_config")
        widget_type = widget.get("widget_type", "table")

        override = override_map.get(wid)

        if chart_config and widget_type == "chart":
            # Render as PNG chart image embedded via CID
            chart_columns = [
                {"key": chart_config["x_key"], "label": chart_config["x_label"]},
                {"key": chart_config["y_key"], "label": chart_config["y_label"]},
            ]
            rows = _fetch_widget_data(entity_type, entity_id, endpoint, chart_columns, override)
            cid = f"chart_{chart_index}"
            chart_index += 1
            png_bytes = render_chart_image(rows, chart_config, title, highlight_value=entity_id)
            images.append((cid, png_bytes))
            widget_sections_html.append(
                f'<div style="margin:1.5rem 0 1rem 0;">'
                f'<img src="cid:{cid}" alt="{_escape(title)}" '
                f'style="max-width:100%;height:auto;display:block;" />'
                f'</div>'
            )
            # Plain-text fallback
            col_keys = [c["key"] for c in chart_columns]
            col_labels = [c["label"] for c in chart_columns]
            widget_sections_text.append(_render_text_table(title, col_keys, col_labels, rows))
        else:
            # Render as HTML table
            if not columns:
                continue

            rows = _fetch_widget_data(entity_type, entity_id, endpoint, columns, override)

            col_keys = [c["key"] for c in columns]
            col_labels = [c["label"] for c in columns]

            # Apply visible_columns override
            if override and override.visible_columns is not None:
                vis = set(override.visible_columns)
                filtered = [(k, l) for k, l in zip(col_keys, col_labels) if k in vis]
                col_keys = [k for k, _ in filtered]
                col_labels = [l for _, l in filtered]

            widget_sections_html.append(_render_html_table(title, col_keys, col_labels, rows))
            widget_sections_text.append(_render_text_table(title, col_keys, col_labels, rows))

    # Compose full email
    html_body = _render_full_html(display_name, entity_type, header_fields, widget_sections_html)
    text_body = _render_full_text(display_name, entity_type, header_fields, widget_sections_text)

    return subject, html_body, text_body, images


def _get_entity_header(entity_type: str, entity_id: str) -> tuple[str, list[dict[str, str]]]:
    """Return (display_name, list of {label, value})."""
    provider = get_data_provider()

    if entity_type == "stock":
        record = provider.get_record("stocks", entity_id)
        if record is None:
            return entity_id, []
        display_name = f"{record.get('company_name', entity_id)} ({entity_id})"
        fields = [
            {"label": "Ticker", "value": record.get("ticker", "")},
            {"label": "Sector", "value": record.get("sector", "")},
            {"label": "Price", "value": record.get("price", "")},
            {"label": "Market Cap ($B)", "value": record.get("market_cap_b", "")},
        ]
        return display_name, fields

    elif entity_type == "person":
        record = provider.get_record("people", entity_id)
        if record is None:
            return entity_id, []
        display_name = record.get("name", entity_id)
        fields = [
            {"label": "Title", "value": record.get("title", "")},
            {"label": "Organization", "value": record.get("organization", "")},
            {"label": "Type", "value": record.get("type", "")},
        ]
        return display_name, fields

    elif entity_type == "dataset":
        datasets = provider.list_datasets()
        for ds in datasets:
            if ds.name.lower() == entity_id.lower():
                fields = [
                    {"label": "Records", "value": str(ds.record_count)},
                    {"label": "Category", "value": ds.category},
                ]
                return ds.display_name, fields
        return entity_id, []

    return entity_id, []


def _get_entity_widgets(entity_type: str, entity_id: str) -> list[dict[str, Any]]:
    """Return widget config dicts for the entity (simplified for rendering)."""
    from app.api.entities import _build_stock_detail, _build_person_detail, _build_dataset_detail

    if entity_type == "stock":
        detail = _build_stock_detail(entity_id)
    elif entity_type == "person":
        detail = _build_person_detail(entity_id)
    elif entity_type == "dataset":
        detail = _build_dataset_detail(entity_id)
    else:
        return []

    result = []
    for w in detail.widgets:
        entry: dict[str, Any] = {
            "widget_id": w.widget_id,
            "title": w.title,
            "endpoint": w.endpoint,
            "widget_type": w.widget_type,
            "columns": [{"key": c.key, "label": c.label} for c in w.columns],
        }
        if w.chart_config:
            entry["chart_config"] = {
                "chart_type": w.chart_config.chart_type,
                "x_key": w.chart_config.x_key,
                "y_key": w.chart_config.y_key,
                "x_label": w.chart_config.x_label,
                "y_label": w.chart_config.y_label,
                "color": w.chart_config.color,
            }
        result.append(entry)
    return result


def _fetch_widget_data(
    entity_type: str,
    entity_id: str,
    endpoint: str,
    columns: list[dict[str, str]],
    override: WidgetOverrideRef | None,
) -> list[dict[str, Any]]:
    """Fetch widget data by parsing the endpoint and querying directly."""
    provider = get_data_provider()
    max_rows = settings.EMAIL_MAX_ROWS_PER_WIDGET

    # Build filter params from override
    filters: dict[str, str] = {}
    sort_by: str | None = None
    sort_order: str = "asc"
    page_size: int = max_rows

    if override:
        filters = dict(override.server_filters) if override.server_filters else {}
        sort_by = override.sort_by
        sort_order = override.sort_order or "asc"
        if override.page_size:
            page_size = min(override.page_size, max_rows)

    # Parse endpoint to determine data source
    # Patterns:
    #   /api/entities/stock/{ticker}/people
    #   /api/entities/stock/{ticker}/files
    #   /api/entities/stock/{ticker}/peers
    #   /api/entities/person/{id}/stocks
    #   /api/entities/person/{id}/coverage-sectors
    #   /api/entities/dataset/{name}/distribution?group_by=...
    #   /api/data/{dataset}

    if endpoint.startswith("/api/data/"):
        dataset = endpoint.split("/api/data/")[1].split("?")[0]
        params = FilterParams(
            page=1, page_size=page_size, sort_by=sort_by, sort_order=sort_order, filters=filters,
        )
        result = provider.query(dataset, params)
        return result.data[:max_rows]

    if "/stock/" in endpoint and endpoint.endswith("/people"):
        ticker = entity_id.upper()
        all_people = provider.query("people", FilterParams(page=1, page_size=200)).data
        filtered = [
            p for p in all_people
            if ticker in [t.strip() for t in p.get("tickers", "").split(";")]
        ]
        return _apply_in_memory_overrides(filtered, filters, sort_by, sort_order)[:max_rows]

    if "/stock/" in endpoint and endpoint.endswith("/files"):
        ticker = entity_id.upper()
        storage = get_storage_provider()
        all_files = storage.list_files()
        filtered = [
            {
                "file_id": f.file_id,
                "filename": f.filename,
                "type": f.type,
                "date": f.date,
                "description": f.description,
            }
            for f in all_files
            if ticker in f.tickers
        ]
        return _apply_in_memory_overrides(filtered, filters, sort_by, sort_order)[:max_rows]

    if "/stock/" in endpoint and endpoint.endswith("/peers"):
        ticker = entity_id.upper()
        stock = provider.get_record("stocks", ticker)
        if stock:
            sector = stock.get("sector", "")
            all_stocks = provider.query("stocks", FilterParams(page=1, page_size=200)).data
            peers = [s for s in all_stocks if s.get("sector") == sector]
            peers.sort(key=lambda s: float(s.get("market_cap_b", 0) or 0), reverse=True)
            return peers[:max_rows]
        return []

    if "/person/" in endpoint and endpoint.endswith("/stocks"):
        person = provider.get_record("people", entity_id)
        if person:
            tickers_str = person.get("tickers", "")
            ticker_list = [t.strip() for t in tickers_str.split(";") if t.strip()]
            stock_records = []
            for ticker in ticker_list:
                stock = provider.get_record("stocks", ticker)
                if stock:
                    stock_records.append(stock)
            return _apply_in_memory_overrides(stock_records, filters, sort_by, sort_order)[:max_rows]
        return []

    if "/person/" in endpoint and "coverage-sectors" in endpoint:
        person = provider.get_record("people", entity_id)
        if person:
            tickers_str = person.get("tickers", "")
            ticker_list = [t.strip() for t in tickers_str.split(";") if t.strip()]
            sector_counts: dict[str, int] = {}
            for ticker in ticker_list:
                stock = provider.get_record("stocks", ticker)
                if stock:
                    sector = stock.get("sector", "Unknown")
                    sector_counts[sector] = sector_counts.get(sector, 0) + 1
            return [{"sector": s, "count": str(c)} for s, c in sorted(sector_counts.items())][:max_rows]
        return []

    if "/dataset/" in endpoint and "distribution" in endpoint:
        parts = endpoint.split("/dataset/")[1]
        dataset_name = parts.split("/")[0]
        all_data = provider.query(dataset_name, FilterParams(page=1, page_size=200)).data
        # Parse group_by from endpoint
        group_by = "sector"
        if "group_by=" in endpoint:
            group_by = endpoint.split("group_by=")[1].split("&")[0]
        counts: dict[str, int] = {}
        for row in all_data:
            val = str(row.get(group_by, "Unknown") or "Unknown")
            counts[val] = counts.get(val, 0) + 1
        return [{group_by: k, "count": str(v)} for k, v in sorted(counts.items())][:max_rows]

    return []


def _apply_in_memory_overrides(
    data: list[dict[str, Any]],
    filters: dict[str, str],
    sort_by: str | None,
    sort_order: str,
) -> list[dict[str, Any]]:
    """Apply filter/sort overrides to in-memory data."""
    result = data
    for field, value in filters.items():
        result = [r for r in result if str(r.get(field, "")).lower() == value.lower()]
    if sort_by and result:
        reverse = sort_order == "desc"
        try:
            result.sort(key=lambda r: _sort_key(r.get(sort_by, "")), reverse=reverse)
        except Exception:
            pass
    return result


def _sort_key(value: Any) -> Any:
    try:
        return float(value)
    except (ValueError, TypeError):
        return str(value).lower()


def _render_html_table(title: str, col_keys: list[str], col_labels: list[str], rows: list[dict[str, Any]]) -> str:
    """Render a single widget as an HTML table with inline styles."""
    html = f'<h3 style="color:#1a365d;margin:1.5rem 0 0.5rem 0;font-size:16px;">{_escape(title)}</h3>\n'

    if not rows:
        html += '<p style="color:#718096;font-style:italic;">No data available.</p>\n'
        return html

    html += '<table style="border-collapse:collapse;width:100%;font-size:13px;margin-bottom:1rem;">\n'
    html += "<thead><tr>\n"
    for label in col_labels:
        html += f'<th style="background:#1a365d;color:#fff;padding:8px 12px;text-align:left;border:1px solid #2a4a7f;">{_escape(label)}</th>\n'
    html += "</tr></thead>\n<tbody>\n"

    for i, row in enumerate(rows):
        bg = "#f7f8fa" if i % 2 == 0 else "#ffffff"
        html += f'<tr style="background:{bg};">\n'
        for key in col_keys:
            val = str(row.get(key, ""))
            html += f'<td style="padding:6px 12px;border:1px solid #e2e8f0;">{_escape(val)}</td>\n'
        html += "</tr>\n"

    html += "</tbody></table>\n"
    return html


def _render_text_table(title: str, col_keys: list[str], col_labels: list[str], rows: list[dict[str, Any]]) -> str:
    """Render a single widget as a plain-text table."""
    lines = [f"\n{title}", "=" * len(title)]

    if not rows:
        lines.append("No data available.")
        return "\n".join(lines)

    lines.append("\t".join(col_labels))
    lines.append("\t".join("-" * len(l) for l in col_labels))
    for row in rows:
        lines.append("\t".join(str(row.get(k, "")) for k in col_keys))

    return "\n".join(lines)


def _render_full_html(
    display_name: str,
    entity_type: str,
    header_fields: list[dict[str, str]],
    widget_sections: list[str],
) -> str:
    """Compose the full HTML email."""
    badge_colors = {
        "stock": ("#ebf8ff", "#2b6cb0"),
        "person": ("#faf5ff", "#6b46c1"),
        "dataset": ("#f0fff4", "#276749"),
    }
    bg, fg = badge_colors.get(entity_type, ("#f7f8fa", "#1a365d"))

    fields_html = ""
    for f in header_fields:
        fields_html += (
            f'<td style="padding:4px 16px 4px 0;vertical-align:top;">'
            f'<span style="color:#718096;font-size:11px;text-transform:uppercase;">{_escape(f["label"])}</span><br>'
            f'<span style="color:#1a202c;font-weight:500;">{_escape(f["value"])}</span>'
            f"</td>\n"
        )

    widgets_html = "\n".join(widget_sections)

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,Helvetica,sans-serif;background:#f7f8fa;margin:0;padding:20px;">
<div style="max-width:800px;margin:0 auto;background:#ffffff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.12);overflow:hidden;">
  <div style="background:#1a365d;padding:16px 24px;">
    <h1 style="color:#d4a843;margin:0;font-size:20px;">GoldMine</h1>
  </div>
  <div style="padding:24px;">
    <div style="margin-bottom:16px;">
      <span style="font-size:22px;font-weight:700;color:#1a202c;">{_escape(display_name)}</span>
      <span style="background:{bg};color:{fg};font-size:11px;font-weight:600;text-transform:uppercase;padding:3px 8px;border-radius:4px;margin-left:8px;">{_escape(entity_type)}</span>
    </div>
    <table style="margin-bottom:16px;"><tr>{fields_html}</tr></table>
    {widgets_html}
    <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0 12px 0;">
    <p style="color:#718096;font-size:11px;">This is an automated email from GoldMine. Data reflects the latest available at time of delivery.</p>
  </div>
</div>
</body>
</html>"""


def _render_full_text(
    display_name: str,
    entity_type: str,
    header_fields: list[dict[str, str]],
    widget_sections: list[str],
) -> str:
    """Compose the full plain-text email."""
    lines = [
        f"GoldMine: {display_name} [{entity_type}]",
        "",
    ]
    for f in header_fields:
        lines.append(f"{f['label']}: {f['value']}")
    lines.append("")
    lines.extend(widget_sections)
    lines.append("")
    lines.append("---")
    lines.append("This is an automated email from GoldMine.")
    return "\n".join(lines)


def _escape(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
