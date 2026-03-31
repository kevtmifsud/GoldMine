"""Documentation Sync workflow.

Scans codebase and infrastructure, compares against markdown documentation,
reconciles gaps, and produces a sync report.

workflow_name = 'docs_sync'
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from app.mode2.db import get_conn
from app.mode2.steps import StepCollector
from app.workflows.base import WorkflowBase

logger = structlog.get_logger(__name__)

# Root of the repo — three levels up from this file
REPO_ROOT = Path(__file__).resolve().parents[4]


class DocsSyncWorkflow(WorkflowBase):
    workflow_name = "docs_sync"

    # ------------------------------------------------------------------
    # WorkflowBase interface
    # ------------------------------------------------------------------
    async def execute(
        self,
        inputs: dict[str, Any],
        triggered_by: str,
        user_id: str,
        steps: StepCollector,
    ) -> dict[str, Any]:
        files_checked: list[str] = []
        gaps: list[dict] = []
        files_updated: list[str] = []
        human_review: list[dict] = []

        # Run all checks
        await self._check_0_schema_columns(files_checked, gaps, human_review)
        await self._check_1_tables(files_checked, gaps, files_updated, human_review)
        self._check_2_tools_vs_docs(files_checked, gaps, files_updated, human_review)
        self._check_3_alt_data_keywords(files_checked, gaps, files_updated, human_review)
        await self._check_4_workflow_registry(files_checked, gaps, files_updated, human_review)
        self._check_5_pipeline_architecture(files_checked, gaps, files_updated, human_review)
        self._check_6_project_structure(files_checked, gaps, files_updated, human_review)
        self._check_7_skill_files(files_checked, gaps, human_review)
        self._check_A_chatbot_routing(files_checked, gaps, human_review)
        self._check_B_workflow_docs_vs_code(files_checked, gaps, human_review)
        self._check_C_new_tools_not_in_docs(files_checked, gaps, human_review)
        await self._check_D_workflows_not_in_registry(files_checked, gaps, human_review)
        self._check_E_skill_stale_tables(files_checked, gaps, human_review)
        await self._check_F_table_freshness(files_checked, gaps, human_review)

        # Build summary
        auto_fixed = sum(1 for g in gaps if g.get("auto_fixed"))
        n_human = len(human_review)
        summary = f"{len(gaps)} gaps found across 14 checks. {auto_fixed} auto-fixed. {n_human} need human review."

        # Write output row
        output_id = str(uuid.uuid4())
        async with get_conn() as conn:
            await conn.execute(
                """INSERT INTO workflow_outputs_docs_sync
                   (id, workflow_run_id, triggered_by, started_at, completed_at,
                    files_checked, gaps_found, files_updated,
                    items_needing_human_review, summary)
                   VALUES ($1, NULL, $2, NOW(), NOW(), $3, $4::jsonb, $5, $6::jsonb, $7)""",
                uuid.UUID(output_id),
                triggered_by,
                files_checked,
                _json_dumps(gaps),
                files_updated,
                _json_dumps(human_review),
                summary,
            )

        return {
            "output_id": output_id,
            "cost_usd": 0.0,
            "summary": summary,
            "gaps_found": gaps,
            "files_updated": files_updated,
            "items_needing_human_review": human_review,
        }

    @classmethod
    def get_registry_entry(cls) -> dict[str, Any]:
        return {
            "workflow_name": "docs_sync",
            "display_name": "Documentation Sync",
            "description": (
                "Scans codebase, database, and all markdown documentation for consistency gaps. "
                "Checks: DB schema vs docs, tool definitions vs chatbot.md, alt data keywords, "
                "workflow registry vs code, pipeline architecture, project structure, skill files, "
                "chatbot routing rules, pre-calculated table freshness, and workflow code vs specs."
            ),
            "required_inputs": {},
            "output_table": "workflow_outputs_docs_sync",
            "trigger_type": "both",
            "schedule_rule": "on_demand or after major build sessions",
            "is_active": True,
        }

    # ==================================================================
    # CHECK 0: data-schema.md column names vs actual database
    # ==================================================================
    _SCHEMA_CHECK_TABLES = [
        "financial_metrics", "portfolio_trades", "daily_pnl", "sessions",
        "chunks", "stocks", "stock_history", "portfolio_concentration",
        "api_cost_events", "messages",
    ]

    async def _check_0_schema_columns(self, files_checked, gaps, human_review):
        """Compare actual DB columns against what data-schema.md documents."""
        schema_path = REPO_ROOT / "instructions" / "domain" / "data-schema.md"
        files_checked.append(str(schema_path.relative_to(REPO_ROOT)))
        schema_text = schema_path.read_text(encoding="utf-8")

        # Get actual columns per table from information_schema
        async with get_conn() as conn:
            rows = await conn.fetch(
                """SELECT table_name, column_name
                   FROM information_schema.columns
                   WHERE table_schema = 'public'
                     AND table_name = ANY($1)
                   ORDER BY table_name, ordinal_position""",
                self._SCHEMA_CHECK_TABLES,
            )

        db_cols: dict[str, set[str]] = {}
        for r in rows:
            db_cols.setdefault(r["table_name"], set()).add(r["column_name"])

        for table in self._SCHEMA_CHECK_TABLES:
            actual = db_cols.get(table, set())
            if not actual:
                continue

            # Extract documented column names from the table's section
            section_match = re.search(
                rf"###\s+`{table}`.*?(?=###\s+`|\Z)", schema_text, re.DOTALL
            )
            if not section_match:
                continue

            section = section_match.group()
            # Parse column names from "Key columns:" lines and "- `col`" list items.
            # Strategy: extract backtick names from lines that start with "- `" or
            # from the "Key columns:" line itself. Ignore table/function names in prose.
            documented: set[str] = set()
            for line in section.splitlines():
                stripped = line.strip()
                # List-style column definitions: "- `col_name` type ..."
                if stripped.startswith("- `"):
                    m = re.match(r"-\s+`(\w+)`", stripped)
                    if m:
                        documented.add(m.group(1))
                # Inline key columns: "Key columns: `a`, `b`, `c`"
                elif stripped.startswith("Key columns:"):
                    documented.update(re.findall(r"`(\w+)`", stripped))

            # Columns in DB but not in docs
            for col in sorted(actual - documented):
                gaps.append({
                    "file": "instructions/domain/data-schema.md",
                    "type": "missing_entry",
                    "description": f"{table}.{col} exists in DB but not documented in data-schema.md",
                    "auto_fixed": False,
                })
                human_review.append({
                    "file": "instructions/domain/data-schema.md",
                    "description": f"{table}.{col} exists in DB but not in data-schema.md",
                    "suggested_fix": f"Add `{col}` to the `{table}` section in data-schema.md",
                })

            # Columns in docs but not in DB (potential stale docs)
            # Exclude table names that appear in FK references (e.g. "→ `sessions`")
            all_table_names = set(db_cols.keys()) | set(self._SCHEMA_CHECK_TABLES)
            for col in sorted(documented - actual):
                # Skip type keywords, table names, and common tokens
                if col in {"text", "uuid", "date", "numeric", "integer", "boolean",
                           "jsonb", "timestamptz", "vector", "varchar", "true",
                           "false", "null", "any", "the", "not", "all"} | all_table_names:
                    continue
                gaps.append({
                    "file": "instructions/domain/data-schema.md",
                    "type": "wrong_value",
                    "description": f"{table}.{col} documented in data-schema.md but does not exist in DB",
                    "auto_fixed": False,
                })

    # ==================================================================
    # CHECK 1: Database tables vs data-schema.md
    # ==================================================================
    async def _check_1_tables(self, files_checked, gaps, files_updated, human_review):
        schema_path = REPO_ROOT / "instructions" / "domain" / "data-schema.md"
        files_checked.append(str(schema_path.relative_to(REPO_ROOT)))

        schema_text = schema_path.read_text(encoding="utf-8")

        # Get all public tables from DB
        async with get_conn() as conn:
            rows = await conn.fetch(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            )
        db_tables = {r["table_name"] for r in rows}

        # Parse documented tables from data-schema.md (### `table_name` pattern)
        documented_tables = set(re.findall(r"###\s+`(\w+)`", schema_text))

        # Tables in DB but not documented
        # Exclude internal tables that are implementation details
        skip_tables: set[str] = set()
        for table in sorted(db_tables - documented_tables - skip_tables):
            gap = {
                "file": "instructions/domain/data-schema.md",
                "type": "missing_entry",
                "description": f"Table '{table}' exists in database but has no entry in data-schema.md",
                "auto_fixed": False,
            }
            gaps.append(gap)
            human_review.append({
                "file": "instructions/domain/data-schema.md",
                "description": f"Table '{table}' exists in database but is not documented",
                "suggested_fix": f"Add a ### `{table}` section to data-schema.md with grain, key columns, writer, and chatbot access",
            })

        # Tables documented but not in DB
        for table in sorted(documented_tables - db_tables):
            gaps.append({
                "file": "instructions/domain/data-schema.md",
                "type": "missing_entry",
                "description": f"Table '{table}' documented in data-schema.md but does not exist in database",
                "auto_fixed": False,
            })

        # CHECK: daily_pnl migration 020 columns documented
        pnl_section_match = re.search(
            r"###\s+`daily_pnl`.*?(?=###\s+`|\Z)", schema_text, re.DOTALL
        )
        if pnl_section_match:
            pnl_section = pnl_section_match.group()
            migration_020_cols = ["shares_held", "market_value", "cost_basis"]
            missing_cols = [c for c in migration_020_cols if c not in pnl_section]
            if missing_cols:
                # Auto-fix: add the missing columns to data-schema.md
                insert_point = "- `contribution_to_portfolio` numeric"
                if insert_point in schema_text:
                    addition = "\n".join(
                        f"- `{col}` numeric" for col in missing_cols
                    )
                    schema_text = schema_text.replace(
                        insert_point,
                        f"{insert_point}\n{addition}",
                    )
                    schema_path.write_text(schema_text, encoding="utf-8")
                    files_updated.append(str(schema_path.relative_to(REPO_ROOT)))
                    gaps.append({
                        "file": "instructions/domain/data-schema.md",
                        "type": "missing_entry",
                        "description": f"daily_pnl missing columns from migration 020: {missing_cols}",
                        "auto_fixed": True,
                    })

    # ==================================================================
    # CHECK 2: Tool definitions vs data-schema.md and chatbot.md
    # ==================================================================
    def _check_2_tools_vs_docs(self, files_checked, gaps, files_updated, human_review):
        chatbot_path = REPO_ROOT / "instructions" / "domain" / "chatbot.md"
        tools_path = REPO_ROOT / "backend" / "app" / "mode2" / "tools.py"
        files_checked.append(str(chatbot_path.relative_to(REPO_ROOT)))
        files_checked.append(str(tools_path.relative_to(REPO_ROOT)))

        chatbot_text = chatbot_path.read_text(encoding="utf-8")

        # Import tool definitions
        from app.mode2.tools import GOLDMINE_TOOLS

        # Map tool names to the data source they query
        tool_source_map = {
            "search_documents": "chunks",
            "get_financial_metrics": "financial_metrics",
            "get_all_estimates": "daily_estimates",
            "get_daily_pnl": "daily_pnl",
            "get_portfolio_concentration": "portfolio_concentration",
            "get_portfolio_risk": "portfolio_risk",
            "get_trade_requests": "trade_requests",
            "get_stock_history": "stock_history",
            "get_guidance": "guidance",
            "get_alt_data": "alt_data",
            "get_model_outputs": "model_outputs",
            "get_workflow_registry": "workflow_registry",
            "run_workflow": "workflow_runs",
            "get_workflow_output": "workflow_outputs_earnings_preview",
        }

        # Check each tool has a corresponding entry in chatbot.md access map
        access_map_section = ""
        m = re.search(r"## Data source access map.*?(?=\n---|\Z)", chatbot_text, re.DOTALL)
        if m:
            access_map_section = m.group()

        tool_names = {t["name"] for t in GOLDMINE_TOOLS}
        for tool_name in sorted(tool_names):
            source_table = tool_source_map.get(tool_name, "")
            # Skip workflow tools — they're meta-tools, not data source tools
            if tool_name in ("run_workflow", "get_workflow_output", "get_workflow_registry"):
                continue
            if source_table and source_table not in access_map_section:
                gaps.append({
                    "file": "instructions/domain/chatbot.md",
                    "type": "missing_entry",
                    "description": f"Tool '{tool_name}' queries '{source_table}' but it's not in chatbot.md access map",
                    "auto_fixed": False,
                })
                human_review.append({
                    "file": "instructions/domain/chatbot.md",
                    "description": f"Data source '{source_table}' (used by tool '{tool_name}') missing from access map",
                    "suggested_fix": f"Add a row for '{source_table}' to the Data source access map table in chatbot.md",
                })

        # Check each chatbot.md data source has a tool
        # Parse table rows from the access map
        table_pattern = re.compile(r"\|\s*`(\w+)`")
        documented_sources = set()
        for line in access_map_section.split("\n"):
            tables_in_line = table_pattern.findall(line)
            documented_sources.update(tables_in_line)

        tool_sources = set(tool_source_map.values())
        # Sources that don't need their own tool (accessed indirectly or combined)
        indirect_sources = {
            "analyst_notes", "buyside_notes", "sellside_notes",  # accessed via search_documents
            "chunks",  # accessed via search_documents
            "workflow_outputs_earnings_preview",  # accessed via get_workflow_output
            "buyside_estimates", "consensus_estimates", "sellside_estimates",  # accessed via get_all_estimates
            "internal_estimates",  # accessed via get_all_estimates
        }
        for source in sorted(documented_sources - tool_sources - indirect_sources):
            # Only flag if it looks like a real queryable table
            if source in ("doc_type", "data_type"):
                continue
            gaps.append({
                "file": "backend/app/mode2/tools.py",
                "type": "missing_entry",
                "description": f"Data source '{source}' documented in chatbot.md but no corresponding tool in GOLDMINE_TOOLS",
                "auto_fixed": False,
            })

    # ==================================================================
    # CHECK 3: Alt data keyword mapping consistency
    # ==================================================================
    def _check_3_alt_data_keywords(self, files_checked, gaps, files_updated, human_review):
        chatbot_path = REPO_ROOT / "instructions" / "domain" / "chatbot.md"
        classifier_path = REPO_ROOT / "backend" / "app" / "mode2" / "classifier.py"
        tools_path = REPO_ROOT / "backend" / "app" / "mode2" / "tools.py"
        files_checked.append(str(classifier_path.relative_to(REPO_ROOT)))

        # Import the authoritative map
        from app.mode2.classifier import ALT_DATA_KEYWORD_MAP

        # Read chatbot.md keyword section
        chatbot_text = chatbot_path.read_text(encoding="utf-8")
        keyword_section = ""
        m = re.search(r"## Alt data keyword mapping.*?(?=\n---|\Z)", chatbot_text, re.DOTALL)
        if m:
            keyword_section = m.group().lower()

        # Read tools.py alt_data description
        tools_text = tools_path.read_text(encoding="utf-8")
        alt_tool_match = re.search(
            r'"name":\s*"get_alt_data".*?"description":\s*\((.*?)\)',
            tools_text, re.DOTALL,
        )
        alt_tool_desc = alt_tool_match.group(1).lower() if alt_tool_match else ""

        # Check each keyword in ALT_DATA_KEYWORD_MAP
        for keyword, data_type in ALT_DATA_KEYWORD_MAP.items():
            kw_lower = keyword.lower()
            if kw_lower not in keyword_section:
                gaps.append({
                    "file": "instructions/domain/chatbot.md",
                    "type": "missing_entry",
                    "description": f"Alt data keyword '{keyword}' → '{data_type}' in classifier.py but missing from chatbot.md",
                    "auto_fixed": False,
                })

        # Check each data_type in get_alt_data tool description has keywords
        # Extract signal names from the tool description (not enum — tool no longer uses enum)
        alt_data_types_in_tool = set()
        alt_tool_section = re.search(
            r'"name":\s*"get_alt_data".*?"description":\s*\((.*?)\)',
            tools_text, re.DOTALL,
        )
        if alt_tool_section:
            # Extract data_type names from description lines like "credit_card_sss_yoy —"
            alt_data_types_in_tool = set(re.findall(r'(\w+_yoy)\b', alt_tool_section.group(1)))

        keyword_data_types = set(ALT_DATA_KEYWORD_MAP.values())
        for dt in sorted(alt_data_types_in_tool - keyword_data_types):
            gaps.append({
                "file": "backend/app/mode2/classifier.py",
                "type": "needs_human_review",
                "description": f"Alt data type '{dt}' in get_alt_data tool enum but has no keywords in ALT_DATA_KEYWORD_MAP",
                "auto_fixed": False,
            })
            human_review.append({
                "file": "backend/app/mode2/classifier.py",
                "description": f"Alt data type '{dt}' in tool enum but no keyword mappings exist",
                "suggested_fix": f"Add keyword mappings for '{dt}' to ALT_DATA_KEYWORD_MAP in classifier.py",
            })

    # ==================================================================
    # CHECK 4: Workflow registry vs workflows.md
    # ==================================================================
    async def _check_4_workflow_registry(self, files_checked, gaps, files_updated, human_review):
        workflows_path = REPO_ROOT / "instructions" / "domain" / "workflows.md"
        files_checked.append(str(workflows_path.relative_to(REPO_ROOT)))

        workflows_text = workflows_path.read_text(encoding="utf-8")

        # Get all active workflows from registry
        async with get_conn() as conn:
            registry_rows = await conn.fetch(
                "SELECT workflow_name, display_name FROM workflow_registry WHERE is_active = true"
            )
            # Check for recent completed runs
            run_rows = await conn.fetch(
                """SELECT DISTINCT wr.workflow_name
                   FROM workflow_runs r
                   JOIN workflow_registry wr ON r.workflow_id = wr.id
                   WHERE r.status = 'completed'"""
            )
        completed_workflows = {r["workflow_name"] for r in run_rows}

        # Parse workflow specs from workflows.md
        # Look for ## Workflow: or **Registry name:** patterns
        specced_workflows = set(re.findall(
            r"\*\*Registry name:\*\*\s*`(\w+)`", workflows_text
        ))

        for row in registry_rows:
            wf_name = row["workflow_name"]
            if wf_name not in specced_workflows:
                gaps.append({
                    "file": "instructions/domain/workflows.md",
                    "type": "missing_entry",
                    "description": f"Workflow '{wf_name}' is in workflow_registry but has no spec in workflows.md",
                    "auto_fixed": False,
                })
                human_review.append({
                    "file": "instructions/domain/workflows.md",
                    "description": f"Workflow '{wf_name}' registered but not specced",
                    "suggested_fix": f"Add a '## Workflow: {row['display_name']}' section to workflows.md following the template",
                })

        for wf_name in sorted(specced_workflows):
            registry_names = {r["workflow_name"] for r in registry_rows}
            if wf_name not in registry_names:
                gaps.append({
                    "file": "instructions/domain/workflows.md",
                    "type": "needs_human_review",
                    "description": f"Workflow '{wf_name}' specced in workflows.md but missing from workflow_registry",
                    "auto_fixed": False,
                })
                human_review.append({
                    "file": "instructions/domain/workflows.md",
                    "description": f"Workflow '{wf_name}' specced but not in registry",
                    "suggested_fix": f"Run: python scripts/seed_workflow_registry.py",
                })

    # ==================================================================
    # CHECK 5: Pipeline architecture vs chatbot.md and WF-* docs
    # ==================================================================
    def _check_5_pipeline_architecture(self, files_checked, gaps, files_updated, human_review):
        chatbot_path = REPO_ROOT / "instructions" / "domain" / "chatbot.md"
        wf08_path = REPO_ROOT / "instructions" / "architecture" / "WF-08_Retrieval_Orchestration.md"
        wf09_path = REPO_ROOT / "instructions" / "architecture" / "WF-09_Response_Generation.md"
        generator_path = REPO_ROOT / "backend" / "app" / "mode2" / "generator.py"
        router_path = REPO_ROOT / "backend" / "app" / "mode2" / "router.py"

        for p in [chatbot_path, wf08_path, wf09_path, generator_path, router_path]:
            if p.exists():
                files_checked.append(str(p.relative_to(REPO_ROOT)))

        chatbot_text = chatbot_path.read_text(encoding="utf-8")
        generator_text = generator_path.read_text(encoding="utf-8")

        # Check chatbot.md pipeline overview for stale content
        if "required_sources[]" in chatbot_text:
            gaps.append({
                "file": "instructions/domain/chatbot.md",
                "type": "stale_content",
                "description": "Pipeline overview still references required_sources[] — classifier no longer outputs this field",
                "auto_fixed": False,
            })
            human_review.append({
                "file": "instructions/domain/chatbot.md",
                "description": "Pipeline overview describes pre-fetch architecture with required_sources[]. Code now uses agentic tool-calling.",
                "suggested_fix": (
                    "Rewrite the Pipeline overview section to describe: "
                    "WF-06 classifies → WF-07 resolves tickers → WF-09 runs agentic tool-calling loop "
                    "(embeds query, looks up Q&A library, then Claude calls tools as needed). "
                    "Remove all references to required_sources[] and WF-08 as a separate orchestrator."
                ),
            })

        if "WF-08  Retrieval Orchestrator" in chatbot_text:
            gaps.append({
                "file": "instructions/domain/chatbot.md",
                "type": "stale_content",
                "description": "Pipeline overview still shows WF-08 Retrieval Orchestrator as a separate step — it is now tool handlers called by WF-09",
                "auto_fixed": False,
            })

        # Check WF-08 doc
        if wf08_path.exists():
            wf08_text = wf08_path.read_text(encoding="utf-8")
            if "RetrievalContext" in wf08_text:
                gaps.append({
                    "file": "instructions/architecture/WF-08_Retrieval_Orchestration.md",
                    "type": "stale_content",
                    "description": "WF-08 doc references RetrievalContext which was deleted — now uses tool handler architecture",
                    "auto_fixed": False,
                })
                human_review.append({
                    "file": "instructions/architecture/WF-08_Retrieval_Orchestration.md",
                    "description": "Describes pre-fetch context-injection orchestrator that no longer exists",
                    "suggested_fix": (
                        "Rewrite to describe the current architecture: _query_* functions in retrieval.py "
                        "are called by execute_tool() in tools.py. No orchestrator function exists — "
                        "Claude decides which tools to call via the agentic loop in generator.py."
                    ),
                })

        # Check WF-09 doc
        if wf09_path.exists():
            wf09_text = wf09_path.read_text(encoding="utf-8")
            # Check if it describes the agentic loop
            has_tool_calling = "tool" in wf09_text.lower() and ("agentic" in wf09_text.lower() or "tool_use" in wf09_text.lower())
            has_system_prompt_ref = "WF-09_system_prompt.md" in wf09_text
            if not has_tool_calling:
                gaps.append({
                    "file": "instructions/architecture/WF-09_Response_Generation.md",
                    "type": "stale_content",
                    "description": "WF-09 doc does not describe the agentic tool-calling loop",
                    "auto_fixed": False,
                })
                human_review.append({
                    "file": "instructions/architecture/WF-09_Response_Generation.md",
                    "description": "Does not describe the agentic tool-calling architecture",
                    "suggested_fix": (
                        "Rewrite to describe: generator.py embeds query, looks up Q&A library, "
                        "starts Claude with GOLDMINE_TOOLS, loops on tool_use responses, "
                        "streams final text response. Reference WF-09_system_prompt.md for system prompt."
                    ),
                })
            if not has_system_prompt_ref:
                gaps.append({
                    "file": "instructions/architecture/WF-09_Response_Generation.md",
                    "type": "stale_content",
                    "description": "WF-09 doc does not reference WF-09_system_prompt.md",
                    "auto_fixed": False,
                })

    # ==================================================================
    # CHECK 6: CLAUDE.md project structure vs actual directories
    # ==================================================================
    def _check_6_project_structure(self, files_checked, gaps, files_updated, human_review):
        claude_path = REPO_ROOT / "CLAUDE.md"
        files_checked.append("CLAUDE.md")

        claude_text = claude_path.read_text(encoding="utf-8")

        # Get actual top-level modules under backend/app/
        app_dir = REPO_ROOT / "backend" / "app"
        actual_modules = sorted(
            d.name for d in app_dir.iterdir()
            if d.is_dir() and not d.name.startswith("__")
        )

        # Parse what's listed in Project Structure
        structure_match = re.search(
            r"## Project Structure.*?```(.*?)```",
            claude_text, re.DOTALL,
        )
        structure_block = structure_match.group(1) if structure_match else ""

        modified = False
        for module in actual_modules:
            if f"    {module}/" not in structure_block and f"{module}/" not in structure_block:
                # Check if it's just not listed
                if module not in structure_block:
                    # Auto-fix: add to project structure
                    # Find the insertion point after the last app/ entry
                    insert_after = "    tests/          # pytest suite"
                    if insert_after in claude_text:
                        desc = _module_description(module)
                        addition = f"\n    {module + '/':16s}# {desc}"
                        claude_text = claude_text.replace(
                            insert_after,
                            insert_after + addition,
                            1,  # only first occurrence
                        )
                        modified = True
                        gaps.append({
                            "file": "CLAUDE.md",
                            "type": "missing_entry",
                            "description": f"Module 'backend/app/{module}/' missing from Project Structure",
                            "auto_fixed": True,
                        })

        # Check for workflows/qa/ specifically
        qa_dir = app_dir / "workflows" / "qa"
        if qa_dir.exists() and "workflows/qa" not in claude_text and "qa/" not in structure_block:
            gaps.append({
                "file": "CLAUDE.md",
                "type": "missing_entry",
                "description": "backend/app/workflows/qa/ directory not listed in Project Structure",
                "auto_fixed": False,
            })

        if modified:
            claude_path.write_text(claude_text, encoding="utf-8")
            if "CLAUDE.md" not in files_updated:
                files_updated.append("CLAUDE.md")

    # ==================================================================
    # CHECK 7: Skill files in instructions/skills/
    # ==================================================================
    def _check_7_skill_files(self, files_checked, gaps, human_review):
        skills_dir = REPO_ROOT / "instructions" / "skills"
        files_checked.append("instructions/skills/")

        expected_files = [
            "add-new-data-source.md",
            "add-new-workflow.md",
            "add-new-alt-data-type.md",
            "add-new-model-sheet.md",
        ]

        if not skills_dir.exists():
            for f in expected_files:
                gaps.append({
                    "file": f"instructions/skills/{f}",
                    "type": "needs_human_review",
                    "description": f"Skill file not yet created — instructions/skills/ directory does not exist",
                    "auto_fixed": False,
                })
                human_review.append({
                    "file": f"instructions/skills/{f}",
                    "description": "Skill file not yet created",
                    "suggested_fix": "Create instructions/skills/ directory and generate skill file content",
                })
        else:
            for f in expected_files:
                if not (skills_dir / f).exists():
                    gaps.append({
                        "file": f"instructions/skills/{f}",
                        "type": "needs_human_review",
                        "description": f"Skill file '{f}' not yet created",
                        "auto_fixed": False,
                    })
                    human_review.append({
                        "file": f"instructions/skills/{f}",
                        "description": f"Skill file '{f}' not yet created",
                        "suggested_fix": f"Create instructions/skills/{f} with step-by-step instructions for this task",
                    })


    # ==================================================================
    # CHECK A: Chatbot data source routing
    # ==================================================================
    _PREFERRED_QUERY_TABLES = {
        "consensus_estimates": "daily_estimates",
        "buyside_estimates": "daily_estimates",
        "internal_estimates": "daily_estimates",
        "sellside_estimates": "daily_estimates",
    }

    def _check_A_chatbot_routing(self, files_checked, gaps, human_review):
        chatbot_path = REPO_ROOT / "instructions" / "domain" / "chatbot.md"
        files_checked.append(str(chatbot_path.relative_to(REPO_ROOT)))
        chatbot_text = chatbot_path.read_text(encoding="utf-8")

        # Extract the data source access map section
        m = re.search(r"## Data source access map.*?(?=\n---|\n##[^#]|\Z)", chatbot_text, re.DOTALL)
        access_map = m.group() if m else ""

        for raw_table, preferred in self._PREFERRED_QUERY_TABLES.items():
            if raw_table in access_map and preferred not in access_map:
                gaps.append({
                    "file": "instructions/domain/chatbot.md",
                    "type": "stale_content",
                    "description": (
                        f"{raw_table} listed as chatbot accessible but "
                        f"{preferred} should be queried instead. Raw table is Layer 1 (log only)."
                    ),
                    "auto_fixed": False,
                })
                human_review.append({
                    "file": "instructions/domain/chatbot.md",
                    "description": f"{raw_table} should be replaced with {preferred} in access map",
                    "suggested_fix": (
                        f"Replace {raw_table} in the data source access map with {preferred}. "
                        f"Add a note that {preferred} is the single query point for all estimate sources."
                    ),
                })

    # ==================================================================
    # CHECK B: Workflow docs vs actual code
    # ==================================================================
    def _check_B_workflow_docs_vs_code(self, files_checked, gaps, human_review):
        workflows_dir = REPO_ROOT / "backend" / "app" / "workflows"
        workflows_md_path = REPO_ROOT / "instructions" / "domain" / "workflows.md"
        if not workflows_md_path.exists():
            return
        files_checked.append(str(workflows_md_path.relative_to(REPO_ROOT)))
        workflows_text = workflows_md_path.read_text(encoding="utf-8")

        skip = {"__init__.py", "base.py", "registry.py", "storage.py", "excel_builder.py"}
        wf_files = [
            f for f in workflows_dir.iterdir()
            if f.is_file() and f.suffix == ".py" and f.name not in skip
        ]
        # Exclude qa/ subfolder files
        qa_files = list((workflows_dir / "qa").glob("*.py")) if (workflows_dir / "qa").exists() else []
        qa_names = {f.name for f in qa_files}

        for wf_file in wf_files:
            if wf_file.name in qa_names:
                continue
            files_checked.append(str(wf_file.relative_to(REPO_ROOT)))
            code_text = wf_file.read_text(encoding="utf-8")

            # Extract table references from code
            code_tables = set(re.findall(
                r'(?:FROM|JOIN|INTO)\s+(\w+)', code_text, re.IGNORECASE
            ))
            # Filter to likely table names — must be in our known DB tables
            known_tables = {
                "chunks", "stocks", "messages", "sessions", "people", "financial_metrics",
                "daily_pnl", "daily_estimates", "portfolio_trades", "portfolio_concentration",
                "portfolio_risk", "stock_history", "stock_betas", "model_outputs", "model_peers",
                "consensus_estimates", "buyside_estimates", "internal_estimates", "sellside_estimates",
                "alt_data", "guidance", "analyst_notes", "buyside_notes", "sellside_notes",
                "workflow_registry", "workflow_runs", "workflow_outputs_earnings_preview",
                "workflow_outputs_financial_model", "workflow_outputs_docs_sync",
                "earnings_calendar", "sec_filings", "transcripts_list", "trade_requests",
            }
            code_tables = {t.lower() for t in code_tables} & known_tables

            # Find matching section in workflows.md
            wf_name_match = re.search(r"workflow_name\s*=\s*['\"](\w+)['\"]", code_text)
            if not wf_name_match:
                continue
            wf_name = wf_name_match.group(1)

            # Find spec section
            spec_match = re.search(
                rf"Registry name:\*\*\s*`{wf_name}`.*?(?=\n## |\Z)",
                workflows_text, re.DOTALL,
            )
            if not spec_match:
                continue
            spec_text = spec_match.group()
            spec_tables = set(re.findall(r"`(\w+)`", spec_text))
            spec_tables = {t.lower() for t in spec_tables} & known_tables

            for table in sorted(spec_tables - code_tables):
                gaps.append({
                    "file": "instructions/domain/workflows.md",
                    "type": "stale_content",
                    "description": f"workflows.md {wf_name} spec references `{table}` but the workflow code does not use it",
                    "auto_fixed": False,
                })

    # ==================================================================
    # CHECK C: New tools not in chatbot.md
    # ==================================================================
    def _check_C_new_tools_not_in_docs(self, files_checked, gaps, human_review):
        chatbot_path = REPO_ROOT / "instructions" / "domain" / "chatbot.md"
        chatbot_text = chatbot_path.read_text(encoding="utf-8")

        from app.mode2.tools import GOLDMINE_TOOLS
        tool_names = {t["name"] for t in GOLDMINE_TOOLS}

        # Tools mentioned anywhere in chatbot.md (tool name or underlying table)
        # Only flag tools that are completely absent — not even their table is documented
        for tool_name in sorted(tool_names):
            if tool_name in chatbot_text:
                continue
            # Check if tool is documented via its underlying table in CHECK 2's map
            # These are covered by existing CHECK 2 — skip them here
            known_tools = {
                "search_documents", "get_financial_metrics", "get_all_estimates",
                "get_daily_pnl", "get_portfolio_concentration", "get_portfolio_risk",
                "get_trade_requests", "get_stock_history", "get_guidance", "get_alt_data",
                "get_model_outputs", "get_workflow_registry", "run_workflow",
                "get_workflow_output", "model_edit",
            }
            if tool_name in known_tools:
                continue
            gaps.append({
                "file": "instructions/domain/chatbot.md",
                "type": "missing_entry",
                "description": f"Tool '{tool_name}' exists in tools.py but is not documented in chatbot.md",
                "auto_fixed": False,
            })
            human_review.append({
                "file": "instructions/domain/chatbot.md",
                "description": f"Tool '{tool_name}' not documented",
                "suggested_fix": (
                    f"Add '{tool_name}' to the data source access map in chatbot.md "
                    f"with: table queried, retrieval method, citation label, and routing rules."
                ),
            })

    # ==================================================================
    # CHECK D: New workflows not in registry
    # ==================================================================
    async def _check_D_workflows_not_in_registry(self, files_checked, gaps, human_review):
        workflows_dir = REPO_ROOT / "backend" / "app" / "workflows"
        skip = {"__init__.py", "base.py", "registry.py", "storage.py", "excel_builder.py"}

        wf_files = [
            f for f in workflows_dir.iterdir()
            if f.is_file() and f.suffix == ".py" and f.name not in skip
        ]

        for wf_file in wf_files:
            code_text = wf_file.read_text(encoding="utf-8")
            wf_name_match = re.search(r"workflow_name\s*=\s*['\"](\w+)['\"]", code_text)
            if not wf_name_match:
                continue
            wf_name = wf_name_match.group(1)

            async with get_conn() as conn:
                row = await conn.fetchrow(
                    "SELECT COUNT(*) as cnt FROM workflow_registry WHERE workflow_name = $1",
                    wf_name,
                )
            if row and row["cnt"] == 0:
                gaps.append({
                    "file": str(wf_file.relative_to(REPO_ROOT)),
                    "type": "missing_entry",
                    "description": f"Workflow file {wf_file.name} exists but '{wf_name}' is not in workflow_registry",
                    "auto_fixed": False,
                })
                human_review.append({
                    "file": str(wf_file.relative_to(REPO_ROOT)),
                    "description": f"Workflow '{wf_name}' not registered",
                    "suggested_fix": f"Run: python scripts/seed_workflow_registry.py to register '{wf_name}'",
                })

    # ==================================================================
    # CHECK E: Skill files reference stale tables
    # ==================================================================
    _CHATBOT_RESTRICTED_TABLES = {
        "consensus_estimates": "Use daily_estimates instead",
        "buyside_estimates": "Use daily_estimates instead",
        "internal_estimates": "Use daily_estimates instead",
        "sellside_estimates": "Use daily_estimates instead",
    }

    def _check_E_skill_stale_tables(self, files_checked, gaps, human_review):
        skills_dir = REPO_ROOT / "instructions" / "skills"
        if not skills_dir.exists():
            return

        for skill_file in skills_dir.glob("*.md"):
            files_checked.append(str(skill_file.relative_to(REPO_ROOT)))
            skill_text = skill_file.read_text(encoding="utf-8")

            for table, reason in self._CHATBOT_RESTRICTED_TABLES.items():
                if table in skill_text:
                    # Skip if the reference also mentions daily_estimates nearby
                    # (indicates a pipeline flow description, not a direct query instruction)
                    lines_with_table = [
                        line for line in skill_text.splitlines()
                        if table in line
                    ]
                    all_have_context = all(
                        "daily_estimates" in line for line in lines_with_table
                    )
                    if all_have_context:
                        continue
                    gaps.append({
                        "file": str(skill_file.relative_to(REPO_ROOT)),
                        "type": "stale_content",
                        "description": (
                            f"{skill_file.name} references '{table}' which should not "
                            f"be queried directly by the chatbot"
                        ),
                        "auto_fixed": False,
                    })
                    human_review.append({
                        "file": str(skill_file.relative_to(REPO_ROOT)),
                        "description": f"References restricted table '{table}'",
                        "suggested_fix": f"Update to reference 'daily_estimates' instead. {reason}",
                    })

    # ==================================================================
    # CHECK F: Pre-calculated table freshness
    # ==================================================================
    _FRESHNESS_REQUIREMENTS: dict[str, tuple[str, int]] = {
        "daily_estimates": ("as_of_date", 2),
        "daily_pnl": ("date", 2),
        "portfolio_concentration": ("date", 2),
        "portfolio_risk": ("date", 2),
    }

    async def _check_F_table_freshness(self, files_checked, gaps, human_review):
        from datetime import date as date_type

        today = date_type.today()

        async with get_conn() as conn:
            for table, (date_col, threshold) in self._FRESHNESS_REQUIREMENTS.items():
                try:
                    row = await conn.fetchrow(
                        f"SELECT MAX({date_col})::date as max_date FROM {table}"
                    )
                except Exception:
                    continue

                if not row or not row["max_date"]:
                    gaps.append({
                        "file": f"scripts/ (job for {table})",
                        "type": "needs_human_review",
                        "description": f"{table} is empty — nightly job may never have run.",
                        "auto_fixed": False,
                    })
                    human_review.append({
                        "file": f"scripts/ (job for {table})",
                        "description": f"{table} is empty",
                        "suggested_fix": "Run the appropriate nightly job to populate this table.",
                    })
                    continue

                max_date = row["max_date"]
                days_stale = (today - max_date).days
                if days_stale > threshold:
                    gaps.append({
                        "file": f"scripts/ (job for {table})",
                        "type": "needs_human_review",
                        "description": (
                            f"{table} last updated {max_date} — {days_stale} days ago. "
                            f"Nightly job may not be running."
                        ),
                        "auto_fixed": False,
                    })
                    human_review.append({
                        "file": f"scripts/ (job for {table})",
                        "description": f"{table} is {days_stale} days stale (threshold: {threshold})",
                        "suggested_fix": (
                            "Check scheduler logs and run the appropriate job manually: "
                            "python scripts/run_portfolio_jobs.py or python scripts/daily_estimates_job.py"
                        ),
                    })


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _module_description(name: str) -> str:
    """Return a short description for a backend module."""
    descriptions = {
        "api": "REST endpoints (data, entities, documents, financials, etc.)",
        "auth": "JWT auth with httpOnly cookies",
        "config": "Pydantic Settings (env_prefix=\"GOLDMINE_\")",
        "data_access": "Pluggable data providers (supabase or csv)",
        "documents": "User-uploaded document management",
        "email": "Email rendering + SMTP/console delivery",
        "mode2": "AI chat system: classifier → ticker resolver → retrieval → generator",
        "object_storage": "File storage abstraction layer",
        "pipeline": "Offline document ingestion (scan → classify → chunk → embed)",
        "reports": "Report generation (daily P&L)",
        "tests": "pytest suite",
        "views": "Saved view persistence",
        "workflows": "Workflow framework and implementations",
    }
    return descriptions.get(name, f"{name} module")


def _json_dumps(obj: Any) -> str:
    """JSON serialize with default str fallback."""
    import json
    return json.dumps(obj, default=str)
