"""Abstract base class for all GoldMine workflows.

Every workflow inherits from WorkflowBase, which handles:
- workflow_runs lifecycle (insert → running → completed/failed)
- Cost tracking
- Structured logging via structlog
"""
from __future__ import annotations

import abc
import time
import uuid
from datetime import datetime
from typing import Any

import structlog

from app.mode2.db import get_conn
from app.mode2.steps import StepCollector

logger = structlog.get_logger(__name__)


class WorkflowBase(abc.ABC):
    """Base class all workflows inherit from.

    Subclasses must set ``workflow_name`` and implement ``execute()``.
    The public ``run()`` method wraps ``execute()`` with workflow_runs
    lifecycle management.
    """

    workflow_name: str = ""

    # ------------------------------------------------------------------
    # Abstract method — subclasses implement this
    # ------------------------------------------------------------------
    @abc.abstractmethod
    async def execute(
        self,
        inputs: dict[str, Any],
        triggered_by: str,
        user_id: str,
        steps: StepCollector,
    ) -> dict[str, Any]:
        """Execute the workflow logic and return the structured output.

        The returned dict must include an ``output_id`` key (uuid str)
        pointing to the row written in the workflow's output table.
        """
        ...

    # ------------------------------------------------------------------
    # Public entry point — manages workflow_runs lifecycle
    # ------------------------------------------------------------------
    async def run(
        self,
        inputs: dict[str, Any],
        triggered_by: str,
        user_id: str,
        steps: StepCollector | None = None,
    ) -> dict[str, Any]:
        """Run the workflow with full lifecycle management.

        1. Looks up workflow_registry to get workflow_id
        2. Inserts workflow_runs row with status='running'
        3. Calls self.execute()
        4. On success: updates status='completed', cost_usd, output_id
        5. On failure: updates status='failed'
        """
        if steps is None:
            steps = StepCollector()

        ticker = inputs.get("ticker")
        run_id = str(uuid.uuid4())
        start_time = time.monotonic()

        logger.info("workflow_run_start", workflow=self.workflow_name,
                     run_id=run_id, ticker=ticker, triggered_by=triggered_by)

        async with get_conn() as conn:
            # Look up workflow_id from registry
            row = await conn.fetchrow(
                "SELECT id FROM workflow_registry WHERE workflow_name = $1",
                self.workflow_name,
            )
            if not row:
                raise ValueError(
                    f"Workflow '{self.workflow_name}' not found in workflow_registry. "
                    "Run scripts/seed_workflow_registry.py first."
                )
            workflow_id = row["id"]

            # Insert workflow_runs row: status=running
            await conn.execute(
                """INSERT INTO workflow_runs
                   (id, workflow_id, ticker, triggered_by, status, started_at)
                   VALUES ($1, $2, $3, $4, 'running', NOW())""",
                uuid.UUID(run_id), workflow_id, ticker, triggered_by,
            )

        # Execute the workflow
        try:
            result = await self.execute(inputs, triggered_by, user_id, steps)
            elapsed = round(time.monotonic() - start_time, 2)

            # Update workflow_runs: completed
            cost_usd = result.get("cost_usd", 0.0)
            output_id = result.get("output_id")
            async with get_conn() as conn:
                await conn.execute(
                    """UPDATE workflow_runs
                       SET status = 'completed',
                           completed_at = NOW(),
                           cost_usd = $1,
                           output_id = $2
                       WHERE id = $3""",
                    cost_usd,
                    uuid.UUID(output_id) if output_id else None,
                    uuid.UUID(run_id),
                )

            logger.info("workflow_run_completed", workflow=self.workflow_name,
                         run_id=run_id, ticker=ticker,
                         elapsed_seconds=elapsed, cost_usd=cost_usd)

            result["run_id"] = run_id
            result["status"] = "completed"
            return result

        except Exception as exc:
            elapsed = round(time.monotonic() - start_time, 2)
            error_msg = str(exc)

            async with get_conn() as conn:
                await conn.execute(
                    """UPDATE workflow_runs
                       SET status = 'failed', completed_at = NOW()
                       WHERE id = $1""",
                    uuid.UUID(run_id),
                )

            logger.error("workflow_run_failed", workflow=self.workflow_name,
                          run_id=run_id, ticker=ticker,
                          elapsed_seconds=elapsed, error=error_msg)
            raise

    # ------------------------------------------------------------------
    # Class method — returns the registry entry for this workflow
    # ------------------------------------------------------------------
    @classmethod
    def get_registry_entry(cls) -> dict[str, Any]:
        """Return a dict suitable for inserting into workflow_registry.

        Subclasses should override this to provide their specific
        display_name, description, required_inputs, output_table,
        trigger_type, and schedule_rule.
        """
        raise NotImplementedError(
            f"{cls.__name__} must override get_registry_entry()"
        )
