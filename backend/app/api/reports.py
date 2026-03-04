from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.email.factory import get_schedule_provider
from app.email.models import EmailSchedule
from app.exceptions import NotFoundError
from app.reports.catalog import get_report, list_reports

# Ensure reports are registered on import
import app.reports.register  # noqa: F401

router = APIRouter(prefix="/api/reports", tags=["reports"])


class ReportResponse(BaseModel):
    report_id: str
    name: str
    description: str
    category: str
    data_sources: list[str]


@router.get("/")
async def list_all_reports() -> list[ReportResponse]:
    return [
        ReportResponse(
            report_id=r.report_id,
            name=r.name,
            description=r.description,
            category=r.category,
            data_sources=r.data_sources,
        )
        for r in list_reports()
    ]


@router.get("/{report_id}")
async def get_report_detail(report_id: str) -> ReportResponse:
    r = get_report(report_id)
    if r is None:
        raise NotFoundError(f"Report '{report_id}' not found")
    return ReportResponse(
        report_id=r.report_id,
        name=r.name,
        description=r.description,
        category=r.category,
        data_sources=r.data_sources,
    )


@router.get("/{report_id}/subscriptions")
async def list_report_subscriptions(request: Request, report_id: str) -> list[EmailSchedule]:
    r = get_report(report_id)
    if r is None:
        raise NotFoundError(f"Report '{report_id}' not found")
    user = request.state.user
    provider = get_schedule_provider()
    return provider.list_schedules(owner=user.username, entity_type="report", entity_id=report_id)
