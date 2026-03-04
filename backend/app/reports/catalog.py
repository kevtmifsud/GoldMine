from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class ReportDefinition:
    report_id: str
    name: str
    description: str
    category: str
    data_sources: list[str]
    render: Callable[[], tuple[str, str, str, list[tuple[str, bytes]]]]


_REGISTRY: dict[str, ReportDefinition] = {}


def register_report(report: ReportDefinition) -> None:
    _REGISTRY[report.report_id] = report


def get_report(report_id: str) -> ReportDefinition | None:
    return _REGISTRY.get(report_id)


def list_reports() -> list[ReportDefinition]:
    return list(_REGISTRY.values())
