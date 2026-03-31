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

    # Create a real workflow_runs row so the frontend can poll status
    run_id = str(uuid.uuid4())
    ticker = body.inputs.get("ticker", "").upper() or None
    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO workflow_runs
               (id, workflow_id, ticker, triggered_by, status, started_at, created_at)
               VALUES ($1, $2, $3, $4, 'running', NOW(), NOW())""",
            uuid.UUID(run_id), reg["id"], ticker, user_id,
        )

    # Run workflow in background, update run status on completion
    async def _run_in_background():
        output_id = None
        try:
            steps = StepCollector()
            result = await workflow.run(
                inputs=body.inputs,
                triggered_by=user_id,
                user_id=user_id,
                steps=steps,
            )
            output_id = result.get("output_id")
            cost = result.get("cost_usd", 0)
            async with get_conn() as conn:
                await conn.execute(
                    """UPDATE workflow_runs
                       SET status = 'completed', completed_at = NOW(),
                           output_id = $1, cost_usd = $2
                       WHERE id = $3""",
                    uuid.UUID(output_id) if output_id else None,
                    cost, uuid.UUID(run_id),
                )
        except Exception:
            logger.exception("background_workflow_failed",
                              workflow=workflow_name, run_id=run_id)
            async with get_conn() as conn:
                await conn.execute(
                    "UPDATE workflow_runs SET status = 'failed', completed_at = NOW() WHERE id = $1",
                    uuid.UUID(run_id),
                )

    asyncio.ensure_future(_run_in_background())

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


# ---------------------------------------------------------------------------
# Earnings Preview endpoints
# ---------------------------------------------------------------------------

@router.get("/earnings-preview/upcoming")
async def get_upcoming_earnings() -> list[dict[str, Any]]:
    """Upcoming earnings for portfolio tickers with preview status."""
    async with get_conn() as conn:
        rows = await conn.fetch(
            """SELECT
                  ec.ticker,
                  s.company_name,
                  s.sector,
                  s.industry,
                  ec.report_date,
                  ec.fiscal_quarter_ending,
                  (ec.report_date::date - CURRENT_DATE) as days_away,
                  CASE
                    WHEN ep.id IS NOT NULL THEN 'generated'
                    WHEN (ec.report_date::date - CURRENT_DATE) <= 7 THEN 'scheduled'
                    ELSE 'not_scheduled'
                  END as preview_status,
                  ep.id as preview_id,
                  ep.generated_at
               FROM earnings_calendar ec
               JOIN stocks s ON s.ticker = ec.ticker
               LEFT JOIN (
                  SELECT DISTINCT ON (ticker)
                    id, ticker, reporting_period, generated_at
                  FROM workflow_outputs_earnings_preview
                  ORDER BY ticker, generated_at DESC
               ) ep ON ep.ticker = ec.ticker
               WHERE ec.ticker IN (
                  SELECT DISTINCT ticker FROM portfolio_trades
               )
               AND ec.report_date::date BETWEEN
                  CURRENT_DATE - 7 AND CURRENT_DATE + 60
               ORDER BY ec.report_date::date ASC"""
        )
    results = []
    for r in rows:
        d = dict(r)
        for k, v in d.items():
            if isinstance(v, uuid.UUID):
                d[k] = str(v)
        results.append(d)
    return results


@router.get("/earnings-preview/history")
async def get_preview_history(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """All generated previews ordered by generated_at DESC. Deduplicated."""
    async with get_conn() as conn:
        rows = await conn.fetch(
            """SELECT
                  ep.id,
                  ep.ticker,
                  s.company_name,
                  ep.reporting_period,
                  ep.forward_period,
                  ep.key_kpis,
                  ep.generated_at,
                  ep.generated_by,
                  wr.status,
                  wr.cost_usd,
                  wr.started_at,
                  wr.completed_at,
                  EXTRACT(EPOCH FROM (
                    wr.completed_at - wr.started_at
                  ))::int as duration_seconds
               FROM workflow_outputs_earnings_preview ep
               JOIN stocks s ON s.ticker = ep.ticker
               LEFT JOIN LATERAL (
                  SELECT status, cost_usd, started_at, completed_at
                  FROM workflow_runs
                  WHERE output_id = ep.id
                  ORDER BY created_at DESC
                  LIMIT 1
               ) wr ON true
               ORDER BY ep.generated_at DESC
               LIMIT $1 OFFSET $2""",
            limit, offset,
        )
    results = []
    for r in rows:
        d = dict(r)
        for k, v in d.items():
            if isinstance(v, uuid.UUID):
                d[k] = str(v)
        results.append(d)
    return results


@router.get("/earnings-preview/{preview_id}")
async def get_preview_detail(preview_id: str) -> dict[str, Any]:
    """Full preview including all JSONB sections."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """SELECT ep.*, s.company_name,
                      wr.status as run_status, wr.cost_usd,
                      wr.started_at as run_started_at,
                      wr.completed_at as run_completed_at
               FROM workflow_outputs_earnings_preview ep
               JOIN stocks s ON s.ticker = ep.ticker
               LEFT JOIN workflow_runs wr
                  ON wr.output_id = ep.id
               WHERE ep.id = $1""",
            uuid.UUID(preview_id),
        )
    if not row:
        raise HTTPException(404, "Preview not found")

    result = dict(row)
    jsonb_fields = {
        "estimates_table", "actuals_section", "price_section",
        "portfolio_section", "alt_data_section", "prior_preview_reference",
        "citations",
    }
    for k, v in result.items():
        if isinstance(v, uuid.UUID):
            result[k] = str(v)
        elif k in jsonb_fields and isinstance(v, str):
            try:
                result[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                pass
    return result


@router.get("/earnings-preview/{ticker}/quarterly-actuals")
async def get_quarterly_actuals(
    ticker: str,
    reporting_period: str = Query(..., description="The reporting quarter e.g. 2025Q4"),
    metrics: str = Query(default="total_revenue,gross_profit,operating_income,ebitda,diluted_eps,free_cash_flow"),
) -> dict[str, Any]:
    """Return actuals for comparison quarters, keyed by label.

    Uses position-based logic: finds the most recent quarterly period_ends
    in the DB and assigns labels relative to the reporting quarter.
    No calendar math — purely ordinal from what the DB has.

    Returns: {
      "prev_quarter": {"total_revenue": 123, ...},
      "yoy_comp": {"total_revenue": 456, ...},
    }
    """
    ticker = ticker.upper()
    metric_list = [m.strip() for m in metrics.split(",") if m.strip()]

    async with get_conn() as conn:
        # Get all distinct quarterly period_ends sorted descending
        period_rows = await conn.fetch(
            """SELECT DISTINCT period_end
               FROM financial_metrics
               WHERE ticker = $1 AND period_type = 'quarterly'
               ORDER BY period_end DESC""",
            ticker,
        )
    period_ends = [r["period_end"] for r in period_rows]

    if not period_ends:
        return {}

    # Position 0 = most recently reported quarter (prev quarter to the reporting one)
    # Position 1 = the quarter before that
    # Position 3 = same quarter last year (4 quarters back from most recent = position 3)
    # So: prev_quarter = period_ends[0], yoy_comp = period_ends[3]

    targets: dict[str, object] = {}
    if len(period_ends) > 0:
        targets["prev_quarter"] = period_ends[0]
    if len(period_ends) > 3:
        targets["yoy_comp"] = period_ends[3]

    if not targets:
        return {}

    target_dates = list(targets.values())

    async with get_conn() as conn:
        rows = await conn.fetch(
            """SELECT metric_name, period_end, value
               FROM financial_metrics
               WHERE ticker = $1
               AND metric_name = ANY($2)
               AND period_type = 'quarterly'
               AND period_end = ANY($3)""",
            ticker, metric_list, target_dates,
        )

    # Build result keyed by label
    date_to_label = {v: k for k, v in targets.items()}
    result: dict[str, dict[str, float]] = {}
    for r in rows:
        label = date_to_label.get(r["period_end"])
        if not label or r["value"] is None:
            continue
        if label not in result:
            result[label] = {}
        result[label][r["metric_name"]] = float(r["value"])

    # Add period_end metadata for display
    meta: dict[str, str] = {}
    for label, pe in targets.items():
        meta[label] = str(pe)

    return {"actuals": result, "period_ends": meta}


@router.get("/earnings-preview/{ticker}/beat-miss")
async def get_beat_miss(
    ticker: str,
    reporting_period: str = Query(..., description="The reporting quarter e.g. 2025Q4"),
) -> dict[str, Any]:
    """Compare actuals vs pre-report consensus for the prev quarter and YoY comp.

    Uses position-based logic matching the quarterly-actuals endpoint.
    """
    ticker = ticker.upper()

    async with get_conn() as conn:
        # Get period_ends by position (same logic as quarterly-actuals)
        period_rows = await conn.fetch(
            """SELECT DISTINCT period_end
               FROM financial_metrics
               WHERE ticker = $1 AND period_type = 'quarterly'
               ORDER BY period_end DESC""",
            ticker,
        )
    period_ends = [r["period_end"] for r in period_rows]

    targets: dict[str, object] = {}
    if len(period_ends) > 0:
        targets["prev_quarter"] = period_ends[0]
    if len(period_ends) > 3:
        targets["yoy_comp"] = period_ends[3]

    result: dict[str, dict] = {}

    async with get_conn() as conn:
        for label, pe in targets.items():
            # Get actuals for this period_end
            actuals = await conn.fetch(
                """SELECT metric_name, value FROM financial_metrics
                   WHERE ticker = $1 AND period_type = 'quarterly'
                   AND period_end = $2""",
                ticker, pe,
            )
            actual_map = {r["metric_name"]: float(r["value"]) for r in actuals if r["value"] is not None}

            # Find the consensus estimate period that corresponds to this period_end
            # by looking for estimates with as_of_date <= period_end
            consensus = await conn.fetch(
                """SELECT DISTINCT ON (metric)
                      metric, value
                   FROM daily_estimates
                   WHERE ticker = $1 AND source = 'consensus'
                   AND as_of_date <= $2
                   ORDER BY metric, as_of_date DESC""",
                ticker, pe,
            )
            consensus_map = {r["metric"]: float(r["value"]) for r in consensus if r["value"] is not None}

            period_result: dict[str, dict] = {}
            for metric in set(list(actual_map.keys()) + list(consensus_map.keys())):
                actual = actual_map.get(metric)
                est = consensus_map.get(metric)
                if actual is not None and est is not None and est != 0:
                    diff_pct = round(((actual - est) / abs(est)) * 100, 2)
                    if abs(diff_pct) <= 2:
                        verdict = "inline"
                    elif diff_pct > 0:
                        verdict = "beat"
                    else:
                        verdict = "miss"
                    period_result[metric] = {
                        "actual": actual, "consensus": est,
                        "diff_pct": diff_pct, "verdict": verdict,
                    }
            result[label] = period_result

    return result


@router.get("/earnings-preview/{ticker}/available-alt-data")
async def get_available_alt_data(ticker: str) -> list[dict[str, str]]:
    """Return alt data signal types available for a ticker."""
    async with get_conn() as conn:
        rows = await conn.fetch(
            """SELECT DISTINCT data_type, date_frequency, source_vendor
               FROM alt_data WHERE ticker = $1
               ORDER BY data_type""",
            ticker.upper(),
        )
    return [{"data_type": r["data_type"], "frequency": r["date_frequency"],
             "vendor": r["source_vendor"]} for r in rows]


@router.get("/earnings-preview/{ticker}/alt-data-chart")
async def get_alt_data_chart(
    ticker: str,
    data_type: str = Query(...),
) -> dict[str, Any]:
    """Return alt data signal history + quarterly revenue actuals for chart overlay."""
    ticker = ticker.upper()
    async with get_conn() as conn:
        # Full history of the signal (weekly samples for daily data)
        raw = await conn.fetch(
            """SELECT date, value, growth, date_frequency
               FROM alt_data
               WHERE ticker = $1 AND data_type = $2
               ORDER BY date""",
            ticker, data_type,
        )

        # Quarterly average growth for the signal
        quarterly = await conn.fetch(
            """SELECT
                  date_trunc('quarter', date)::date as quarter_start,
                  ROUND(AVG(growth)::numeric, 2) as avg_growth
               FROM alt_data
               WHERE ticker = $1 AND data_type = $2
               GROUP BY date_trunc('quarter', date)
               ORDER BY quarter_start""",
            ticker, data_type,
        )

        # Revenue YoY growth by quarter (actuals)
        revenue_quarterly = await conn.fetch(
            """WITH q AS (
                  SELECT period_end, value,
                    LAG(value) OVER (ORDER BY period_end) as prev_value
                  FROM financial_metrics
                  WHERE ticker = $1 AND metric_name = 'total_revenue'
                    AND period_type = 'quarterly'
                  ORDER BY period_end
               )
               SELECT period_end as quarter_end,
                  ROUND(((value / NULLIF(prev_value, 0)) - 1) * 100, 2) as revenue_yoy_growth
               FROM q
               WHERE prev_value IS NOT NULL
               ORDER BY period_end""",
            ticker,
        )

        # Consensus revenue estimates — compute YoY growth vs actuals
        consensus_rev = await conn.fetch(
            """SELECT de.period, de.value as est_value, fm.value as actual_prior
               FROM daily_estimates de
               LEFT JOIN financial_metrics fm
                  ON fm.ticker = de.ticker
                  AND fm.metric_name = 'total_revenue'
                  AND fm.period_type = 'quarterly'
                  AND fm.period_end BETWEEN
                      (CASE
                          WHEN de.period LIKE '%%Q1' THEN (CAST(LEFT(de.period,4) AS int)-1 || '-01-01')::date
                          WHEN de.period LIKE '%%Q2' THEN (CAST(LEFT(de.period,4) AS int)-1 || '-04-01')::date
                          WHEN de.period LIKE '%%Q3' THEN (CAST(LEFT(de.period,4) AS int)-1 || '-07-01')::date
                          WHEN de.period LIKE '%%Q4' THEN (CAST(LEFT(de.period,4) AS int)-1 || '-10-01')::date
                      END)
                      AND
                      (CASE
                          WHEN de.period LIKE '%%Q1' THEN (CAST(LEFT(de.period,4) AS int)-1 || '-03-31')::date
                          WHEN de.period LIKE '%%Q2' THEN (CAST(LEFT(de.period,4) AS int)-1 || '-06-30')::date
                          WHEN de.period LIKE '%%Q3' THEN (CAST(LEFT(de.period,4) AS int)-1 || '-09-30')::date
                          WHEN de.period LIKE '%%Q4' THEN (CAST(LEFT(de.period,4) AS int)-1 || '-12-31')::date
                      END)
               WHERE de.ticker = $1 AND de.metric = 'total_revenue' AND de.source = 'consensus'
               AND de.as_of_date = (SELECT MAX(as_of_date) FROM daily_estimates WHERE ticker = $1)
               AND de.period LIKE '%%Q%%'
               ORDER BY de.period""",
            ticker,
        )

    # Build weekly series (sample daily to weekly)
    weekly_points = []
    freq = raw[0]["date_frequency"] if raw else "daily"
    if freq == "daily":
        # Sample to Mondays
        for r in raw:
            d = r["date"]
            if d.weekday() == 0:  # Monday
                weekly_points.append({"date": str(d), "growth": float(r["growth"]) if r["growth"] is not None else None})
    else:
        for r in raw:
            weekly_points.append({"date": str(r["date"]), "growth": float(r["growth"]) if r["growth"] is not None else None})

    # Build quarterly series
    quarterly_points = [
        {"quarter": str(r["quarter_start"]), "avg_growth": float(r["avg_growth"]) if r["avg_growth"] is not None else None}
        for r in quarterly
    ]

    # Build revenue quarterly series
    rev_points = [
        {"quarter_end": str(r["quarter_end"]), "revenue_yoy_growth": float(r["revenue_yoy_growth"]) if r["revenue_yoy_growth"] is not None else None}
        for r in revenue_quarterly
    ]

    # Consensus revenue YoY growth
    consensus_points = []
    for r in consensus_rev:
        period = r["period"]  # e.g. "2026Q1"
        est = float(r["est_value"]) if r["est_value"] is not None else None
        prior = float(r["actual_prior"]) if r["actual_prior"] is not None else None
        yoy = round(((est / prior) - 1) * 100, 2) if est and prior and prior > 0 else None
        # Map period to quarter start date for chart alignment
        y = int(period[:4])
        q = int(period[-1])
        q_start = f"{y}-{(q-1)*3+1:02d}-01"
        consensus_points.append({"quarter": q_start, "consensus_revenue_yoy": yoy})

    return {
        "ticker": ticker,
        "data_type": data_type,
        "frequency": freq,
        "weekly": weekly_points,
        "quarterly": quarterly_points,
        "revenue_quarterly": rev_points,
        "consensus_revenue_quarterly": consensus_points,
    }


@router.get("/earnings-preview/{ticker}/price-context")
async def get_price_context(ticker: str) -> dict[str, Any]:
    """Return enriched price data for a ticker: 52W range, YTD return, 180d history."""
    ticker = ticker.upper()
    async with get_conn() as conn:
        # Stock fundamentals (52W high/low)
        stock = await conn.fetchrow(
            """SELECT price, "52w_high", "52w_low" FROM stocks WHERE ticker = $1""",
            ticker,
        )
        # 180d price history for ticker + SPY
        history = await conn.fetch(
            """SELECT ticker, date::date as date, close::numeric as close
               FROM stock_history
               WHERE ticker IN ($1, 'SPY')
               AND date::date >= CURRENT_DATE - 180
               ORDER BY ticker, date::date""",
            ticker,
        )
        # YTD start price
        ytd_row = await conn.fetchrow(
            """SELECT close::numeric as close FROM stock_history
               WHERE ticker = $1 AND date::date >= (date_trunc('year', CURRENT_DATE))::date
               ORDER BY date::date LIMIT 1""",
            ticker,
        )
        spy_ytd_row = await conn.fetchrow(
            """SELECT close::numeric as close FROM stock_history
               WHERE ticker = 'SPY' AND date::date >= (date_trunc('year', CURRENT_DATE))::date
               ORDER BY date::date LIMIT 1""",
        )

    if not stock:
        return {"error": f"No stock data for {ticker}"}

    price = float(stock["price"]) if stock["price"] else 0
    high52 = float(stock["52w_high"]) if stock["52w_high"] else 0
    low52 = float(stock["52w_low"]) if stock["52w_low"] else 0

    # Build price history arrays
    ticker_prices = []
    spy_prices = []
    for r in history:
        entry = {"date": str(r["date"]), "close": float(r["close"])}
        if r["ticker"] == ticker:
            ticker_prices.append(entry)
        else:
            spy_prices.append(entry)

    # Calculate returns
    last_close = ticker_prices[-1]["close"] if ticker_prices else price
    last_date = ticker_prices[-1]["date"] if ticker_prices else None

    # 90d return
    d90_price = None
    if len(ticker_prices) > 60:
        d90_price = ticker_prices[-min(63, len(ticker_prices))]["close"]
    ret_90d = round((last_close / d90_price - 1) * 100, 2) if d90_price and d90_price > 0 else None

    # YTD return
    ytd_start = float(ytd_row["close"]) if ytd_row else None
    ret_ytd = round((last_close / ytd_start - 1) * 100, 2) if ytd_start and ytd_start > 0 else None

    # SPY returns
    spy_last = spy_prices[-1]["close"] if spy_prices else None
    spy_ytd_start = float(spy_ytd_row["close"]) if spy_ytd_row else None
    spy_ret_ytd = round((spy_last / spy_ytd_start - 1) * 100, 2) if spy_last and spy_ytd_start and spy_ytd_start > 0 else None
    spy_d90_price = spy_prices[-min(63, len(spy_prices))]["close"] if len(spy_prices) > 60 else None
    spy_ret_90d = round((spy_last / spy_d90_price - 1) * 100, 2) if spy_last and spy_d90_price and spy_d90_price > 0 else None
    spy_high52 = max((p["close"] for p in spy_prices), default=0) if spy_prices else 0
    spy_low52 = min((p["close"] for p in spy_prices), default=0) if spy_prices else 0

    return {
        "ticker": ticker,
        "as_of_date": last_date,
        "summary": {
            ticker: {
                "last_close": last_close,
                "high_52w": high52, "low_52w": low52,
                "pct_of_52w_high": round((last_close / high52) * 100, 1) if high52 > 0 else None,
                "pct_of_52w_low": round((last_close / low52) * 100, 1) if low52 > 0 else None,
                "ytd_return": ret_ytd, "return_90d": ret_90d,
            },
            "SPY": {
                "last_close": spy_last,
                "high_52w": spy_high52, "low_52w": spy_low52,
                "pct_of_52w_high": round((spy_last / spy_high52) * 100, 1) if spy_last and spy_high52 > 0 else None,
                "pct_of_52w_low": round((spy_last / spy_low52) * 100, 1) if spy_last and spy_low52 > 0 else None,
                "ytd_return": spy_ret_ytd, "return_90d": spy_ret_90d,
            },
        },
        "chart": {
            "ticker_prices": ticker_prices,
            "spy_prices": spy_prices,
        },
    }


@router.get("/earnings-preview/{ticker}/estimates-deepdive")
async def get_estimates_deepdive(
    ticker: str,
    period: str = Query(...),
) -> list[dict[str, Any]]:
    """Full analyst-level estimate breakdown for a ticker+period from daily_estimates."""
    async with get_conn() as conn:
        rows = await conn.fetch(
            """SELECT source, firm, analyst_name, analyst_person_id,
                      metric, value, unit, estimate_date, as_of_date, staleness_days
               FROM daily_estimates
               WHERE ticker = $1 AND period = $2
               AND as_of_date = (
                   SELECT MAX(as_of_date) FROM daily_estimates WHERE ticker = $1
               )
               ORDER BY
                   CASE source
                       WHEN 'internal' THEN 1
                       WHEN 'consensus' THEN 2
                       WHEN 'buyside' THEN 3
                       WHEN 'sellside' THEN 4
                   END,
                   firm, analyst_name, metric""",
            ticker.upper(), period,
        )
    return [dict(r) for r in rows]


@router.get("/earnings-preview/{ticker}/available-kpis")
async def get_available_kpis(ticker: str) -> list[str]:
    """Return KPI-worthy metrics that exist for a ticker in financial_metrics.

    Filters to a curated set of high-level metrics analysts actually track,
    excludes low-level accounting line items.
    """
    kpi_worthy = [
        "total_revenue", "gross_profit", "operating_income", "ebitda", "ebit",
        "net_income", "diluted_eps", "basic_eps", "free_cash_flow",
        "operating_cash_flow", "capital_expenditure",
        "cost_of_revenue", "operating_expense", "selling_gen_admin",
        "gross_profit",  # margin proxy
        "total_debt", "cash_and_cash_equivalents", "total_assets",
        "stockholders_equity", "working_capital",
        "inventory", "accounts_receivable", "accounts_payable",
        "depreciation_and_amortization", "stock_based_compensation",
        "share_issued", "diluted_average_shares",
    ]
    async with get_conn() as conn:
        rows = await conn.fetch(
            """SELECT DISTINCT metric_name
               FROM financial_metrics
               WHERE ticker = $1 AND metric_name = ANY($2)
               ORDER BY metric_name""",
            ticker.upper(), kpi_worthy,
        )
    return [r["metric_name"] for r in rows]


@router.patch("/earnings-preview/{preview_id}")
async def update_preview_settings(
    preview_id: str,
    body: dict[str, Any],
) -> dict[str, str]:
    """Update KPIs and/or alt data signal selections on a preview."""
    updates = []
    params: list[Any] = []
    idx = 1

    if "key_kpis" in body:
        updates.append(f"key_kpis = ${idx}")
        params.append(body["key_kpis"])
        idx += 1
    if "selected_alt_signals" in body:
        updates.append(f"selected_alt_signals = ${idx}")
        params.append(body["selected_alt_signals"])
        idx += 1

    if not updates:
        raise HTTPException(400, "No fields to update")

    params.append(uuid.UUID(preview_id))
    async with get_conn() as conn:
        await conn.execute(
            f"UPDATE workflow_outputs_earnings_preview SET {', '.join(updates)} WHERE id = ${idx}",
            *params,
        )
    return {"status": "updated"}


@router.get("/runs/{run_id}")
async def get_run_status(run_id: str) -> dict[str, Any]:
    """Run status for polling."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """SELECT id, ticker, status, triggered_by,
                      started_at, completed_at, cost_usd, output_id,
                      EXTRACT(EPOCH FROM (
                        COALESCE(completed_at, NOW()) - started_at
                      ))::int as elapsed_seconds
               FROM workflow_runs
               WHERE id = $1""",
            uuid.UUID(run_id),
        )
    if not row:
        raise HTTPException(404, "Run not found")
    result = dict(row)
    for k, v in result.items():
        if isinstance(v, uuid.UUID):
            result[k] = str(v)
    return result
