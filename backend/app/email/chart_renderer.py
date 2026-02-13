"""Generate chart images (PNG bytes) for embedding in HTML emails."""
from __future__ import annotations

import io
from typing import Any

import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


HIGHLIGHT_COLOR = "#e86319"
HIGHLIGHT_ALPHA = 1.0
SAME_INDUSTRY_ALPHA = 0.55
OTHER_ALPHA = 0.45

INDUSTRY_PALETTE = [
    "#3182ce",
    "#38a169",
    "#805ad5",
    "#d53f8c",
    "#dd6b20",
    "#319795",
    "#975a16",
    "#2b6cb0",
    "#e53e3e",
    "#718096",
]


def _hex_to_rgba(hex_color: str, alpha: float) -> tuple[float, float, float, float]:
    r = int(hex_color[1:3], 16) / 255
    g = int(hex_color[3:5], 16) / 255
    b = int(hex_color[5:7], 16) / 255
    return (r, g, b, alpha)


def render_chart_image(
    data: list[dict[str, Any]],
    chart_config: dict[str, str],
    title: str,
    highlight_value: str | None = None,
) -> bytes:
    """Render a chart as PNG bytes using matplotlib.

    highlight_value: the entity_id (e.g. ticker) to highlight.
    Bars are sorted by y-value descending and colored by industry.
    """
    chart_type = chart_config.get("chart_type", "bar")
    x_key = chart_config["x_key"]
    y_key = chart_config["y_key"]
    x_label = chart_config.get("x_label", "")
    y_label = chart_config.get("y_label", "")
    default_color = chart_config.get("color", "#2a4a7f")

    # Parse numeric values and sort descending for bar charts
    parsed = []
    for row in data:
        label = str(row.get(x_key, ""))
        try:
            val = float(row.get(y_key, 0) or 0)
        except (ValueError, TypeError):
            val = 0.0
        industry = str(row.get("industry", ""))
        parsed.append((label, val, industry))

    if chart_type != "line":
        parsed.sort(key=lambda t: t[1], reverse=True)

    labels = [t[0] for t in parsed]
    values = [t[1] for t in parsed]
    industries = [t[2] for t in parsed]

    # Determine highlight industry
    highlight_industry = ""
    if highlight_value:
        for label, _, ind in parsed:
            if label == highlight_value:
                highlight_industry = ind
                break

    # Build industry → color map
    unique_industries = list(dict.fromkeys(industries))  # preserve order
    industry_color_map: dict[str, str] = {}
    palette_idx = 0
    for ind in unique_industries:
        if ind == highlight_industry:
            industry_color_map[ind] = HIGHLIGHT_COLOR
        else:
            industry_color_map[ind] = INDUSTRY_PALETTE[palette_idx % len(INDUSTRY_PALETTE)]
            palette_idx += 1

    # Compute per-bar RGBA colors
    bar_colors = []
    has_industry_data = any(industries)
    if has_industry_data and highlight_value:
        for label, _, ind in parsed:
            base = industry_color_map.get(ind, default_color)
            if label == highlight_value:
                bar_colors.append(_hex_to_rgba(HIGHLIGHT_COLOR, HIGHLIGHT_ALPHA))
            elif ind == highlight_industry:
                bar_colors.append(_hex_to_rgba(HIGHLIGHT_COLOR, SAME_INDUSTRY_ALPHA))
            else:
                bar_colors.append(_hex_to_rgba(base, OTHER_ALPHA))
    else:
        for label in labels:
            if highlight_value and label == highlight_value:
                bar_colors.append(_hex_to_rgba(HIGHLIGHT_COLOR, HIGHLIGHT_ALPHA))
            else:
                bar_colors.append(_hex_to_rgba(default_color, 0.8))

    fig, ax = plt.subplots(figsize=(7, 3.5), dpi=150)

    if chart_type == "line":
        ax.plot(range(len(labels)), values, color=default_color, linewidth=2, marker="o", markersize=4)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
    else:
        ax.bar(range(len(labels)), values, color=bar_colors, width=0.6)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)

        # Add legend for industries
        if has_industry_data and highlight_value:
            legend_patches = []
            for ind in unique_industries:
                c = industry_color_map[ind]
                alpha = SAME_INDUSTRY_ALPHA if ind == highlight_industry else OTHER_ALPHA
                legend_patches.append(mpatches.Patch(
                    facecolor=_hex_to_rgba(c, alpha),
                    edgecolor="none",
                    label=ind,
                ))
            ax.legend(
                handles=legend_patches,
                fontsize=6,
                loc="upper right",
                framealpha=0.8,
                handlelength=1,
                handleheight=0.8,
            )

    ax.set_title(title, fontsize=11, fontweight="bold", color="#1a365d", pad=10)
    ax.set_xlabel(x_label, fontsize=8, color="#718096")
    ax.set_ylabel(y_label, fontsize=8, color="#718096")
    ax.tick_params(axis="y", labelsize=7)
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
