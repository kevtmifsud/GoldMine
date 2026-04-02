"""Pipeline step collector for real-time transparency.

Accumulates step metadata during pipeline execution so the router
can emit them as SSE events between top-level calls.
"""
from __future__ import annotations


def format_sql(sql: str, params: list | tuple = ()) -> str:
    """Format a SQL query + params for display in pipeline steps.

    Replaces $1, $2, etc. with the actual parameter values (truncated)
    so analysts can see the full query that was executed.
    """
    display = sql.strip()
    for i, p in enumerate(params, start=1):
        placeholder = f"${i}"
        if isinstance(p, list):
            val_str = str(p[:5]) + ("..." if len(p) > 5 else "")
        elif isinstance(p, str) and len(p) > 80:
            val_str = f"'{p[:80]}...'"
        elif isinstance(p, str):
            val_str = f"'{p}'"
        else:
            val_str = str(p)
        display = display.replace(placeholder, val_str, 1)
    return display


class StepCollector:
    """Mutable collector that pipeline functions append steps to."""

    def __init__(self) -> None:
        self.steps: list[dict] = []

    def add(
        self,
        label: str,
        detail: str,
        source: str,
        model: str | None = None,
        cost_usd: float = 0.0,
        duration_ms: int = 0,
        result_summary: str = "",
        query: str | None = None,
    ) -> None:
        step: dict = {
            "type": "step",
            "label": label,
            "detail": detail,
            "source": source,
            "model": model,
            "cost_usd": cost_usd,
            "duration_ms": duration_ms,
            "result_summary": result_summary,
        }
        if query:
            step["query"] = query
        self.steps.append(step)

    def drain(self) -> list[dict]:
        """Return all accumulated steps and clear the internal list."""
        items = self.steps
        self.steps = []
        return items
