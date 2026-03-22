"""Workflow registry — runtime lookup from workflow_registry table.

The workflow_registry table is the source of truth, not a hardcoded dict.
This module caches the mapping and exposes lookup functions.
"""
from __future__ import annotations

import importlib
from typing import Any

import structlog

from app.mode2.db import get_conn

logger = structlog.get_logger(__name__)

# Maps workflow_name → WorkflowBase subclass instance (lazy-loaded)
_workflow_instances: dict[str, Any] = {}

# Maps workflow_name → module path for lazy import
_WORKFLOW_MODULES: dict[str, str] = {
    "earnings_preview": "app.workflows.earnings_preview",
    "financial_model_generation": "app.workflows.financial_model_generation",
    "docs_sync": "app.workflows.qa.docs_sync",
}


def _get_workflow_class(workflow_name: str) -> Any:
    """Lazy-import and cache a workflow instance by name."""
    if workflow_name in _workflow_instances:
        return _workflow_instances[workflow_name]

    module_path = _WORKFLOW_MODULES.get(workflow_name)
    if not module_path:
        return None

    try:
        mod = importlib.import_module(module_path)
        # Convention: module exposes a class named after the workflow in PascalCase
        # e.g. earnings_preview → EarningsPreviewWorkflow
        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if (
                isinstance(attr, type)
                and hasattr(attr, "workflow_name")
                and getattr(attr, "workflow_name", None) == workflow_name
            ):
                instance = attr()
                _workflow_instances[workflow_name] = instance
                return instance
    except ImportError:
        logger.warning("workflow_module_not_found", workflow_name=workflow_name,
                        module_path=module_path)
    return None


async def get_workflow(name: str) -> Any | None:
    """Look up a workflow by name. Returns a WorkflowBase instance or None.

    Validates against the workflow_registry table to ensure the workflow
    is registered and active before returning it.
    """
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """SELECT workflow_name, is_active
               FROM workflow_registry
               WHERE workflow_name = $1""",
            name,
        )
    if not row:
        return None
    if not row["is_active"]:
        logger.info("workflow_inactive", workflow_name=name)
        return None

    return _get_workflow_class(name)


async def list_workflows() -> list[dict[str, Any]]:
    """Return all active workflows from workflow_registry."""
    async with get_conn() as conn:
        rows = await conn.fetch(
            """SELECT workflow_name, display_name, description,
                      trigger_type, schedule_rule, is_active,
                      required_inputs, output_table
               FROM workflow_registry
               WHERE is_active = true
               ORDER BY workflow_name"""
        )
    return [dict(r) for r in rows]


async def get_workflow_registry_entry(name: str) -> dict[str, Any] | None:
    """Return a single workflow registry entry by name."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """SELECT id, workflow_name, display_name, description,
                      trigger_type, schedule_rule, is_active,
                      required_inputs, output_table
               FROM workflow_registry
               WHERE workflow_name = $1""",
            name,
        )
    return dict(row) if row else None
