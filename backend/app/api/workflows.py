"""API endpoints for workflow management and execution.

GET  /api/workflows                          — list active workflows
GET  /api/workflows/{name}/runs              — recent runs for a workflow
GET  /api/workflows/{name}/{ticker}/latest   — most recent output
POST /api/workflows/{name}/run               — trigger a workflow on demand
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from pydantic import BaseModel, Field

import structlog

from app.mode2.db import get_conn
from app.mode2.steps import StepCollector

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class RunWorkflowRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)


class RunWorkflowResponse(BaseModel):
    workflow_run_id: str
    status: str = "accepted"


class WorkflowSummary(BaseModel):
    workflow_name: str
    display_name: str
    description: str | None = None
    trigger_type: str
    schedule_rule: str | None = None


class WorkflowRunSummary(BaseModel):
    id: str
    workflow_name: str | None = None
    ticker: str | None = None
    triggered_by: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cost_usd: float | None = None
    output_id: str | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_user_id(request: Request) -> str:
    user = getattr(request.state, "user", None)
    if user and hasattr(user, "username"):
        return user.username
    return "anonymous"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def list_workflows() -> list[WorkflowSummary]:
    """Return all active workflows from workflow_registry."""
    async with get_conn() as conn:
        rows = await conn.fetch(
            """SELECT workflow_name, display_name, description,
                      trigger_type, schedule_rule
               FROM workflow_registry
               WHERE is_active = true
               ORDER BY workflow_name"""
        )
    return [
        WorkflowSummary(
            workflow_name=r["workflow_name"],
            display_name=r["display_name"],
            description=r["description"],
            trigger_type=r["trigger_type"],
            schedule_rule=r["schedule_rule"],
        )
        for r in rows
    ]


@router.get("/{workflow_name}/runs")
async def get_workflow_runs(
    workflow_name: str,
    ticker: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[WorkflowRunSummary]:
    """Return recent runs for a workflow, optionally filtered by ticker."""
    conditions = ["wreg.workflow_name = $1"]
    params: list[Any] = [workflow_name]
    idx = 2

    if ticker:
        conditions.append(f"wr.ticker = ${idx}")
        params.append(ticker.upper())
        idx += 1

    where = " AND ".join(conditions)
    params.extend([limit, offset])

    async with get_conn() as conn:
        rows = await conn.fetch(
            f"""SELECT wr.id, wreg.workflow_name, wr.ticker, wr.triggered_by,
                       wr.status, wr.started_at, wr.completed_at,
                       wr.cost_usd, wr.output_id, wr.created_at
                FROM workflow_runs wr
                JOIN workflow_registry wreg ON wr.workflow_id = wreg.id
                WHERE {where}
                ORDER BY wr.created_at DESC
                LIMIT ${idx} OFFSET ${idx + 1}""",
            *params,
        )

    return [
        WorkflowRunSummary(
            id=str(r["id"]),
            workflow_name=r["workflow_name"],
            ticker=r["ticker"],
            triggered_by=r["triggered_by"],
            status=r["status"],
            started_at=r["started_at"],
            completed_at=r["completed_at"],
            cost_usd=float(r["cost_usd"]) if r["cost_usd"] is not None else None,
            output_id=str(r["output_id"]) if r["output_id"] else None,
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.get("/{workflow_name}/{ticker}/latest")
async def get_latest_workflow_output(
    workflow_name: str,
    ticker: str,
) -> dict[str, Any]:
    """Return the most recent output for a workflow + ticker."""
    async with get_conn() as conn:
        reg = await conn.fetchrow(
            "SELECT output_table FROM workflow_registry WHERE workflow_name = $1",
            workflow_name,
        )
    if not reg:
        raise HTTPException(404, f"Workflow '{workflow_name}' not found")

    output_table = reg["output_table"]
    if not output_table.startswith("workflow_outputs_"):
        raise HTTPException(400, "Invalid output table")

    async with get_conn() as conn:
        row = await conn.fetchrow(
            f"""SELECT * FROM {output_table}
                WHERE ticker = $1
                ORDER BY generated_at DESC
                LIMIT 1""",
            ticker.upper(),
        )

    if not row:
        raise HTTPException(
            404, f"No output found for {workflow_name} / {ticker.upper()}"
        )

    result = dict(row)
    # Ensure UUIDs are strings for JSON serialization
    for key, val in result.items():
        if isinstance(val, uuid.UUID):
            result[key] = str(val)
    return result


@router.post("/{workflow_name}/run", status_code=202)
async def trigger_workflow(
    request: Request,
    workflow_name: str,
    body: RunWorkflowRequest,
    background_tasks: BackgroundTasks,
) -> RunWorkflowResponse:
    """Trigger a workflow on demand. Returns immediately; runs in background."""
    user_id = _get_user_id(request)

    # Validate workflow exists and is active
    async with get_conn() as conn:
        reg = await conn.fetchrow(
            """SELECT id, required_inputs, is_active
               FROM workflow_registry
               WHERE workflow_name = $1""",
            workflow_name,
        )
    if not reg:
        raise HTTPException(404, f"Workflow '{workflow_name}' not found")
    if not reg["is_active"]:
        raise HTTPException(400, f"Workflow '{workflow_name}' is inactive")

    # Validate required inputs
    required = reg["required_inputs"] or {}
    if isinstance(required, str):
        required = json.loads(required)
    missing = [k for k, v in required.items() if v == "required" and k not in body.inputs]
    if missing:
        raise HTTPException(
            422, f"Missing required inputs: {', '.join(missing)}"
        )

    # Import workflow class
    from app.workflows.registry import get_workflow
    workflow = await get_workflow(workflow_name)
    if workflow is None:
        raise HTTPException(500, f"Workflow '{workflow_name}' implementation not found")

    # Generate a run_id to return immediately
    run_id = str(uuid.uuid4())

    # Run workflow in background
    async def _run_in_background():
        try:
            steps = StepCollector()
            await workflow.run(
                inputs=body.inputs,
                triggered_by=user_id,
                user_id=user_id,
                steps=steps,
            )
        except Exception:
            logger.exception("background_workflow_failed",
                              workflow=workflow_name, run_id=run_id)

    background_tasks.add_task(asyncio.ensure_future, _run_in_background())

    return RunWorkflowResponse(workflow_run_id=run_id, status="accepted")


# ---------------------------------------------------------------------------
# Financial Model endpoints
# ---------------------------------------------------------------------------

class ModelVersionSummary(BaseModel):
    version: str
    s3_path: str
    generated_at: datetime
    generated_by: str
    key_kpis: list[str] = Field(default_factory=list)
    sheets_generated: list[str] = Field(default_factory=list)
    kpis_need_user_input: bool = False


class ModelLatestResponse(BaseModel):
    version: str
    s3_path: str
    download_url: str
    expires_in: int = 3600
    generated_at: datetime
    key_kpis: list[str] = Field(default_factory=list)
    kpis_need_user_input: bool = False
    model_outputs_rows: int | None = None


class ModelEditRequest(BaseModel):
    assumption_key: str
    scenario: str = "base"
    new_value: float
    period: str | None = None


class ModelGenerateRequest(BaseModel):
    key_kpis: list[str] = Field(default_factory=list)
    base_assumptions: dict[str, Any] | None = None


@router.get("/financial_model/{ticker}/versions")
async def get_model_versions(ticker: str) -> list[ModelVersionSummary]:
    """List all model versions for a ticker."""
    async with get_conn() as conn:
        rows = await conn.fetch(
            """SELECT version, s3_path, generated_at, generated_by,
                      key_kpis, sheets_generated, kpis_need_user_input
               FROM workflow_outputs_financial_model
               WHERE ticker = $1
               ORDER BY CAST(version AS INTEGER) DESC""",
            ticker.upper(),
        )
    return [
        ModelVersionSummary(
            version=r["version"],
            s3_path=r["s3_path"],
            generated_at=r["generated_at"],
            generated_by=r["generated_by"],
            key_kpis=r["key_kpis"] or [],
            sheets_generated=r["sheets_generated"] or [],
            kpis_need_user_input=r["kpis_need_user_input"],
        )
        for r in rows
    ]


@router.get("/financial_model/{ticker}/latest")
async def get_latest_model(ticker: str) -> ModelLatestResponse:
    """Get the most recent model version with a presigned download URL."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """SELECT version, s3_path, generated_at, key_kpis,
                      kpis_need_user_input
               FROM workflow_outputs_financial_model
               WHERE ticker = $1
               ORDER BY CAST(version AS INTEGER) DESC
               LIMIT 1""",
            ticker.upper(),
        )
    if not row:
        raise HTTPException(
            404,
            f"No model found for {ticker.upper()}. "
            "Ask the chatbot to generate one.",
        )

    from app.workflows.storage import get_presigned_download_url

    download_url = get_presigned_download_url(row["s3_path"])

    # Count model_outputs rows for this version
    async with get_conn() as conn:
        count_row = await conn.fetchrow(
            """SELECT COUNT(*) as cnt FROM model_outputs
               WHERE ticker = $1 AND version = $2""",
            ticker.upper(), row["version"],
        )
    rows_count = count_row["cnt"] if count_row else None

    return ModelLatestResponse(
        version=row["version"],
        s3_path=row["s3_path"],
        download_url=download_url,
        generated_at=row["generated_at"],
        key_kpis=row["key_kpis"] or [],
        kpis_need_user_input=row["kpis_need_user_input"],
        model_outputs_rows=rows_count,
    )


@router.post("/financial_model/{ticker}/edit", status_code=202)
async def edit_model(
    request: Request,
    ticker: str,
    body: ModelEditRequest,
    background_tasks: BackgroundTasks,
) -> RunWorkflowResponse:
    """Edit a model assumption and trigger regeneration. Async — returns immediately."""
    user_id = _get_user_id(request)
    run_id = str(uuid.uuid4())

    # Verify a model exists for this ticker
    async with get_conn() as conn:
        existing = await conn.fetchrow(
            """SELECT version FROM workflow_outputs_financial_model
               WHERE ticker = $1
               ORDER BY CAST(version AS INTEGER) DESC LIMIT 1""",
            ticker.upper(),
        )
    if not existing:
        raise HTTPException(
            404, f"No existing model for {ticker.upper()}. Generate one first."
        )

    async def _run_edit():
        try:
            # Read current assumptions
            async with get_conn() as conn:
                rows = await conn.fetch(
                    """SELECT DISTINCT ON (metric, scenario)
                              metric, scenario, value
                       FROM model_outputs
                       WHERE ticker = $1 AND sheet = 'assumptions'
                       ORDER BY metric, scenario, as_of_date DESC""",
                    ticker.upper(),
                )

            # Build and apply edit
            assumptions: dict[str, float] = {}
            for r in rows:
                if r["scenario"] == "base" and r["value"] is not None:
                    assumptions[r["metric"]] = float(r["value"])

            assumptions[body.assumption_key] = body.new_value

            from app.workflows.financial_model_generation import FinancialModelGenerationWorkflow
            workflow = FinancialModelGenerationWorkflow()
            await workflow.run(
                inputs={
                    "ticker": ticker.upper(),
                    "base_assumptions": assumptions,
                },
                triggered_by=user_id,
                user_id=user_id,
            )
        except Exception:
            logger.exception("model_edit_failed", ticker=ticker, run_id=run_id)

    background_tasks.add_task(asyncio.ensure_future, _run_edit())

    return RunWorkflowResponse(workflow_run_id=run_id, status="accepted")


@router.post("/financial_model/{ticker}/generate", status_code=202)
async def generate_model(
    request: Request,
    ticker: str,
    body: ModelGenerateRequest,
    background_tasks: BackgroundTasks,
) -> RunWorkflowResponse:
    """Generate a financial model for a ticker on demand. Async — returns immediately."""
    user_id = _get_user_id(request)
    run_id = str(uuid.uuid4())

    # Verify ticker exists
    async with get_conn() as conn:
        stock = await conn.fetchrow(
            "SELECT ticker FROM stocks WHERE ticker = $1",
            ticker.upper(),
        )
    if not stock:
        raise HTTPException(404, f"Ticker {ticker.upper()} not found in stocks universe")

    async def _run_generate():
        try:
            from app.workflows.financial_model_generation import FinancialModelGenerationWorkflow
            workflow = FinancialModelGenerationWorkflow()
            await workflow.run(
                inputs={
                    "ticker": ticker.upper(),
                    "key_kpis": body.key_kpis or [],
                    "base_assumptions": body.base_assumptions,
                },
                triggered_by=user_id,
                user_id=user_id,
            )
        except Exception:
            logger.exception("model_generate_failed", ticker=ticker, run_id=run_id)

    background_tasks.add_task(asyncio.ensure_future, _run_generate())

    return RunWorkflowResponse(workflow_run_id=run_id, status="accepted")
