"""Financial Model Generation Workflow.

Generates a standardized 3-statement financial model for a ticker following
the canonical template in instructions/domain/models.md. Pulls historical
financials, estimates, peer comps, and prior model assumptions. Uploads
versioned Excel to Supabase S3 storage. Triggers model processing job to
extract structured outputs into model_outputs and internal_estimates.

See instructions/domain/workflows.md for the full spec.
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from app.config.settings import settings
from app.mode2.db import get_conn
from app.mode2.models import ClassifiedQuery
from app.mode2.steps import StepCollector
from app.workflows.base import WorkflowBase

logger = structlog.get_logger(__name__)

# Ensure scripts/ is importable for model_processing_job and generate_model_peers
_SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


class FinancialModelGenerationWorkflow(WorkflowBase):
    workflow_name = "financial_model_generation"

    async def execute(
        self,
        inputs: dict[str, Any],
        triggered_by: str,
        user_id: str,
        steps: StepCollector,
    ) -> dict[str, Any]:
        # ==============================================================
        # STEP 1 — Validate inputs
        # ==============================================================
        ticker = (inputs.get("ticker") or "").upper()
        if not ticker:
            raise ValueError("ticker is required")

        key_kpis: list[str] = inputs.get("key_kpis") or []
        base_assumptions: dict | None = inputs.get("base_assumptions")

        # Verify ticker exists in stocks table
        async with get_conn() as conn:
            row = await conn.fetchrow(
                "SELECT ticker, sector, industry FROM stocks WHERE ticker = $1",
                ticker,
            )
        if not row:
            raise ValueError(f"Ticker {ticker} not found in stocks universe")

        steps.add(
            label=f"Validated ticker {ticker}",
            detail=f"Sector: {row['sector']}, Industry: {row['industry']}",
            source="supabase",
            result_summary="ticker valid",
        )

        # ==============================================================
        # STEP 2 — Ensure peer set exists
        # ==============================================================
        from generate_model_peers import generate_peers_for_ticker

        peer_tickers = await generate_peers_for_ticker(ticker)

        steps.add(
            label=f"Peer set for {ticker}",
            detail=f"{len(peer_tickers)} peers",
            source="supabase",
            result_summary=", ".join(peer_tickers[:5]),
        )

        # ==============================================================
        # STEP 3 — Pull all data in parallel
        # ==============================================================
        (
            historical_data,
            estimates_data,
            prior_model_rows,
            analyst_chunks,
            stock_price_rows,
        ) = await asyncio.gather(
            self._fetch_historical(ticker, steps),
            self._fetch_estimates(ticker, steps),
            self._fetch_prior_assumptions(ticker),
            self._fetch_analyst_chunks(ticker),
            self._fetch_current_price(ticker),
        )

        # Fetch peer financial data in parallel
        peers_financial: dict[str, list[dict]] = {}
        if peer_tickers:
            peer_coros = [
                self._fetch_peer_financials(pt) for pt in peer_tickers
            ]
            peer_results = await asyncio.gather(*peer_coros, return_exceptions=True)
            for pt, result in zip(peer_tickers, peer_results):
                if isinstance(result, Exception):
                    logger.warning("peer_fetch_failed", peer=pt, error=str(result))
                else:
                    peers_financial[pt] = result

        # Current price
        current_price: float | None = None
        if stock_price_rows:
            current_price = float(stock_price_rows[0].get("close", 0))

        steps.add(
            label="All data retrieved",
            detail=(
                f"{len(historical_data)} historical rows, "
                f"{len(estimates_data)} estimate rows, "
                f"{len(peer_tickers)} peers, "
                f"prior model: {'yes' if prior_model_rows else 'no'}"
            ),
            source="supabase",
            result_summary="assembling model",
        )

        # ==============================================================
        # STEP 4 — Determine key_kpis
        # ==============================================================
        kpis_need_user_input = False

        if not key_kpis:
            # Try prior workflow output
            prior_kpis = await self._fetch_prior_kpis(ticker)
            if prior_kpis:
                key_kpis = prior_kpis
            elif analyst_chunks:
                key_kpis = self._infer_kpis_from_chunks(analyst_chunks)
            else:
                kpis_need_user_input = True

        steps.add(
            label="KPIs determined",
            detail=f"{'user input needed' if kpis_need_user_input else ', '.join(key_kpis[:5])}",
            source="logic",
            result_summary=f"{len(key_kpis)} KPIs",
        )

        # ==============================================================
        # STEP 5 — Determine version number
        # ==============================================================
        async with get_conn() as conn:
            version_row = await conn.fetchrow(
                """SELECT MAX(CAST(version AS INTEGER))
                   FROM workflow_outputs_financial_model
                   WHERE ticker = $1""",
                ticker,
            )
        prior_max = version_row[0] if version_row and version_row[0] else 0
        new_version = prior_max + 1
        version_str = str(new_version)
        date_str = datetime.now().strftime("%Y-%m-%d")

        # ==============================================================
        # STEP 6 — Build Excel
        # ==============================================================
        from app.workflows.excel_builder import FinancialModelBuilder

        builder = FinancialModelBuilder(
            ticker=ticker,
            historical_data=historical_data,
            estimates=estimates_data,
            peers_data=peers_financial,
            prior_assumptions=prior_model_rows,
            key_kpis=key_kpis,
            base_assumptions=base_assumptions,
            current_price=current_price,
        )
        excel_bytes, unmapped_metrics = builder.build()

        steps.add(
            label="Excel built",
            detail=f"{len(builder.sheets_generated)} sheets, {len(unmapped_metrics)} unmapped metrics",
            source="openpyxl",
            result_summary=f"{len(excel_bytes)} bytes",
        )

        # ==============================================================
        # STEP 7 — Upload to Supabase S3
        # ==============================================================
        from app.workflows.storage import upload_model

        s3_key = upload_model(
            ticker=ticker,
            version=version_str,
            date_str=date_str,
            file_bytes=excel_bytes,
        )

        steps.add(
            label=f"Uploaded to S3",
            detail=s3_key,
            source="supabase_s3",
            result_summary="upload complete",
        )

        # ==============================================================
        # STEP 8 — Run model processing job
        # ==============================================================
        from model_processing_job import process_ticker_from_s3

        processing_result = await process_ticker_from_s3(
            ticker=ticker,
            version=version_str,
            s3_key=s3_key,
        )

        steps.add(
            label="Model processed",
            detail=f"{processing_result['rows_written']} rows to model_outputs",
            source="supabase",
            result_summary=f"{processing_result.get('estimates_written', 0)} internal_estimates",
        )

        # ==============================================================
        # STEP 9 — Write output row
        # ==============================================================
        assumptions_snapshot = {
            row["metric"]: {
                "base": row["base"],
                "bull": row["bull"],
                "bear": row["bear"],
            }
            for row in builder.get_assumptions_dict()
        }

        output_id = str(uuid.uuid4())

        async with get_conn() as conn:
            # Get the workflow_run_id
            run_row = await conn.fetchrow(
                """SELECT wr.id FROM workflow_runs wr
                   JOIN workflow_registry wreg ON wr.workflow_id = wreg.id
                   WHERE wreg.workflow_name = 'financial_model_generation'
                     AND wr.ticker = $1
                     AND wr.status = 'running'
                   ORDER BY wr.started_at DESC LIMIT 1""",
                ticker,
            )
            workflow_run_id = run_row["id"] if run_row else None

            await conn.execute(
                """INSERT INTO workflow_outputs_financial_model
                   (id, workflow_run_id, ticker, version, s3_path, s3_bucket,
                    key_kpis, assumptions_snapshot, peer_set, sheets_generated,
                    unmapped_metrics, kpis_need_user_input,
                    generated_at, generated_by)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10,
                           $11, $12, NOW(), $13)""",
                uuid.UUID(output_id),
                workflow_run_id,
                ticker,
                version_str,
                s3_key,
                settings.S3_BUCKET,
                key_kpis,
                json.dumps(assumptions_snapshot),
                peer_tickers,
                builder.sheets_generated,
                unmapped_metrics,
                kpis_need_user_input,
                triggered_by,
            )

        # ==============================================================
        # STEP 10 — Return result
        # ==============================================================
        return {
            "output_id": output_id,
            "cost_usd": 0.0,
            "ticker": ticker,
            "version": version_str,
            "s3_path": s3_key,
            "s3_bucket": settings.S3_BUCKET,
            "key_kpis": key_kpis,
            "kpis_need_user_input": kpis_need_user_input,
            "sheets_generated": builder.sheets_generated,
            "unmapped_metrics": unmapped_metrics,
            "model_outputs_rows": processing_result["rows_written"],
        }

    # ==================================================================
    # Data fetchers
    # ==================================================================

    async def _fetch_historical(self, ticker: str, steps: StepCollector) -> list[dict]:
        """Fetch historical financial_metrics: 3 annual + 8 quarterly."""
        async with get_conn() as conn:
            rows = await conn.fetch(
                """SELECT metric_name, period_end, period_type, value
                   FROM financial_metrics
                   WHERE ticker = $1
                   ORDER BY period_end DESC
                   LIMIT 200""",
                ticker,
            )
        results = [dict(r) for r in rows]
        steps.add(
            label=f"Historical financials for {ticker}",
            detail=f"financial_metrics ({len(results)} rows)",
            source="supabase",
            result_summary=f"{len(results)} rows",
        )
        return results

    async def _fetch_estimates(self, ticker: str, steps: StepCollector) -> list[dict]:
        """Fetch all four estimate sources."""
        queries = {
            "internal_estimates": """
                SELECT DISTINCT ON (ticker, metric, period)
                    ticker, metric, period, value, unit, 'internal_estimates' AS _table
                FROM internal_estimates WHERE ticker = $1
                ORDER BY ticker, metric, period, created_at DESC LIMIT 100""",
            "buyside_estimates": """
                SELECT DISTINCT ON (ticker, metric, period)
                    ticker, metric, period, value, unit, 'buyside_estimates' AS _table
                FROM buyside_estimates WHERE ticker = $1
                ORDER BY ticker, metric, period, as_of_date DESC LIMIT 100""",
            "consensus_estimates": """
                SELECT DISTINCT ON (ticker, metric, period)
                    ticker, metric, period, value, unit, 'consensus_estimates' AS _table
                FROM consensus_estimates WHERE ticker = $1
                ORDER BY ticker, metric, period, as_of_date DESC LIMIT 100""",
            "sellside_estimates": """
                SELECT DISTINCT ON (ticker, metric, period)
                    ticker, metric, period, value, unit, 'sellside_estimates' AS _table
                FROM sellside_estimates WHERE ticker = $1
                ORDER BY ticker, metric, period, as_of_date DESC LIMIT 100""",
        }

        results: list[dict] = []
        async with get_conn() as conn:
            coros = [conn.fetch(sql, ticker) for sql in queries.values()]
            fetched = await asyncio.gather(*coros, return_exceptions=True)

        for table_name, rows_or_err in zip(queries.keys(), fetched):
            if isinstance(rows_or_err, Exception):
                logger.warning("estimate_fetch_failed", table=table_name, error=str(rows_or_err))
                continue
            for r in rows_or_err:
                results.append(dict(r))

        steps.add(
            label=f"Estimates for {ticker}",
            detail=f"4 tables ({len(results)} rows)",
            source="supabase",
            result_summary=f"{len(results)} rows",
        )
        return results

    async def _fetch_prior_assumptions(self, ticker: str) -> list[dict]:
        """Fetch prior ASSUMPTIONS sheet from model_outputs."""
        async with get_conn() as conn:
            rows = await conn.fetch(
                """SELECT DISTINCT ON (metric, scenario)
                          metric, period, scenario, value, unit
                   FROM model_outputs
                   WHERE ticker = $1 AND sheet = 'assumptions'
                   ORDER BY metric, scenario, as_of_date DESC
                   LIMIT 200""",
                ticker,
            )
        return [dict(r) for r in rows]

    async def _fetch_analyst_chunks(self, ticker: str) -> list[dict]:
        """Fetch analyst_note and sellside_note chunks for KPI inference."""
        async with get_conn() as conn:
            rows = await conn.fetch(
                """SELECT chunk_text
                   FROM chunks
                   WHERE ticker = $1
                     AND document_type IN ('analyst_note', 'sellside_note')
                   ORDER BY created_at DESC
                   LIMIT 20""",
                ticker,
            )
        return [dict(r) for r in rows]

    async def _fetch_current_price(self, ticker: str) -> list[dict]:
        """Fetch most recent closing price."""
        async with get_conn() as conn:
            rows = await conn.fetch(
                """SELECT close
                   FROM stock_history
                   WHERE ticker = $1
                   ORDER BY date DESC
                   LIMIT 1""",
                ticker,
            )
        return [dict(r) for r in rows]

    async def _fetch_peer_financials(self, peer_ticker: str) -> list[dict]:
        """Fetch financial_metrics for a single peer ticker."""
        async with get_conn() as conn:
            rows = await conn.fetch(
                """SELECT metric_name, period_end, period_type, value
                   FROM financial_metrics
                   WHERE ticker = $1
                   ORDER BY period_end DESC
                   LIMIT 50""",
                peer_ticker,
            )
        return [dict(r) for r in rows]

    async def _fetch_prior_kpis(self, ticker: str) -> list[str]:
        """Fetch key_kpis from most recent workflow_outputs_financial_model."""
        async with get_conn() as conn:
            row = await conn.fetchrow(
                """SELECT key_kpis
                   FROM workflow_outputs_financial_model
                   WHERE ticker = $1
                   ORDER BY generated_at DESC
                   LIMIT 1""",
                ticker,
            )
        if row and row["key_kpis"]:
            return list(row["key_kpis"])
        return []

    def _infer_kpis_from_chunks(self, chunks: list[dict]) -> list[str]:
        """Infer KPIs from analyst/sellside note chunks."""
        metric_keywords = {
            "arpu": "ARPU", "subscribers": "Subscribers",
            "dau": "DAU", "mau": "MAU", "gmv": "GMV",
            "arr": "ARR", "net adds": "Net Adds",
            "same store sales": "Same Store Sales",
            "comp sales": "Same Store Sales",
            "backlog": "Backlog", "bookings": "Bookings",
            "asp": "ASP", "units": "Units",
            "net revenue retention": "Net Revenue Retention",
        }

        counts: dict[str, int] = {}
        for chunk in chunks:
            text = (chunk.get("chunk_text") or "").lower()
            for keyword, display_name in metric_keywords.items():
                if keyword in text:
                    counts[display_name] = counts.get(display_name, 0) + 1

        sorted_kpis = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return [k for k, _ in sorted_kpis[:5]]

    # ==================================================================
    # Registry entry
    # ==================================================================
    @classmethod
    def get_registry_entry(cls) -> dict[str, Any]:
        return {
            "workflow_name": "financial_model_generation",
            "display_name": "Financial Model Generation",
            "description": (
                "Generates a standardized 3-statement financial model for a ticker "
                "following the canonical template in instructions/domain/models.md."
            ),
            "required_inputs": {
                "ticker": "required",
                "key_kpis": "optional",
                "base_assumptions": "optional",
            },
            "output_table": "workflow_outputs_financial_model",
            "trigger_type": "on_demand",
            "schedule_rule": None,
        }
