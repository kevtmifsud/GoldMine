#!/usr/bin/env python3
"""Run LLM regression tests against the Mode 2 pipeline.

Replays user queries from resolved bug reports through the pipeline
(classify → resolve → retrieve) and checks that original errors no longer occur.
Does NOT call the LLM generator to avoid cost — validates the data pipeline only.

Usage:
    python scripts/run_llm_regression.py                    # run all pending/pass/fail tests
    python scripts/run_llm_regression.py --only-failing     # re-run only failing tests
    python scripts/run_llm_regression.py --test-id <uuid>   # run a specific test
    python scripts/run_llm_regression.py --create-missing   # auto-create tests for resolved bugs without one
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

from app.mode2.classifier import classify_query  # noqa: E402
from app.mode2.db import get_conn  # noqa: E402
from app.mode2.models import RetrievalContext  # noqa: E402
from app.mode2.retrieval import retrieve_context  # noqa: E402
from app.mode2.steps import StepCollector  # noqa: E402
from app.mode2.ticker_resolver import resolve_tickers  # noqa: E402


# ---------------------------------------------------------------------------
# Assertion checkers
# ---------------------------------------------------------------------------
def check_no_error(
    error_msg: str | None,
    assertion_value: str | None,
    classified,
    universe,
    context: RetrievalContext,
) -> tuple[bool, str]:
    """Pass if no exception was raised during the pipeline."""
    if error_msg:
        return False, f"Pipeline error: {error_msg}"
    return True, "No error raised"


def check_has_content(
    error_msg: str | None,
    assertion_value: str | None,
    classified,
    universe,
    context: RetrievalContext,
) -> tuple[bool, str]:
    """Pass if retrieval returned at least one chunk or structured data."""
    if error_msg:
        return False, f"Pipeline error: {error_msg}"
    has_chunks = context.total_chunks_retrieved > 0
    has_structured = bool(context.structured_data)
    has_qa = len(context.qa_library_hits) > 0
    if has_chunks or has_structured or has_qa:
        return True, f"{context.total_chunks_retrieved} chunks, {len(context.structured_data or [])} structured rows"
    return False, "No content retrieved"


def check_no_hallucination_keyword(
    error_msg: str | None,
    assertion_value: str | None,
    classified,
    universe,
    context: RetrievalContext,
) -> tuple[bool, str]:
    """Pass if the original error string does not appear in any retrieved chunk."""
    if error_msg:
        return False, f"Pipeline error: {error_msg}"
    if not assertion_value:
        return True, "No assertion value to check"
    needle = assertion_value.lower()
    for chunk in context.chunks:
        if needle in chunk.chunk_text.lower():
            return False, f"Error text found in chunk {chunk.chunk_id}"
    return True, "Error text not found in retrieved content"


ASSERTION_CHECKERS = {
    "no_error": check_no_error,
    "has_content": check_has_content,
    "no_hallucination_keyword": check_no_hallucination_keyword,
}


# ---------------------------------------------------------------------------
# Run a single test
# ---------------------------------------------------------------------------
async def run_single_test(test: dict) -> dict:
    """Execute one regression test through classify → resolve → retrieve."""
    test_id = str(test["id"])
    query = test["user_query"]
    assertion_type = test["assertion_type"]
    assertion_value = test["assertion_value"]

    result = {
        "test_id": test_id,
        "test_name": test["test_name"],
        "query": query,
        "passed": False,
        "detail": "",
        "duration_ms": 0,
        "error": None,
    }

    checker = ASSERTION_CHECKERS.get(assertion_type)
    if not checker:
        result["detail"] = f"Unknown assertion type: {assertion_type}"
        return result

    t0 = time.time()
    error_msg = None
    classified = None
    universe = None
    context = RetrievalContext(query_type="unknown")

    try:
        steps = StepCollector()

        # WF-06: Classify
        classified = await classify_query(
            query, history=[], user_id="regression_runner",
            session_id=None, message_id=None, steps=steps,
        )

        # WF-07: Resolve tickers
        universe = await resolve_tickers(classified, user_id="regression_runner")

        # WF-08: Retrieve context (the expensive but critical step)
        context = await retrieve_context(
            classified, universe, query,
            session_id=None, message_id=None, user_id="regression_runner",
            steps=steps,
        )

    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        result["error"] = error_msg

    duration_ms = int((time.time() - t0) * 1000)
    result["duration_ms"] = duration_ms

    passed, detail = checker(error_msg, assertion_value, classified, universe, context)
    result["passed"] = passed
    result["detail"] = detail

    # Update the test record in DB
    async with get_conn() as conn:
        new_result = "pass" if passed else "fail"
        await conn.execute(
            """UPDATE llm_regression_tests
               SET last_result = $1,
                   last_error = $2,
                   last_run_at = NOW(),
                   run_count = run_count + 1,
                   pass_count = pass_count + $3,
                   fail_count = fail_count + $4
               WHERE id = $5""",
            new_result,
            None if passed else (error_msg or detail),
            1 if passed else 0,
            0 if passed else 1,
            test["id"],
        )

    return result


# ---------------------------------------------------------------------------
# Create missing tests for resolved bugs
# ---------------------------------------------------------------------------
async def create_missing_tests() -> int:
    """Create regression tests for resolved bugs that don't have one yet."""
    created = 0
    async with get_conn() as conn:
        bugs = await conn.fetch(
            """SELECT b.id, b.category, b.user_query, b.error_message, b.llm_response,
                      b.tickers_referenced, b.description
               FROM llm_bug_reports b
               LEFT JOIN llm_regression_tests t ON t.bug_report_id = b.id
               WHERE b.status = 'resolved' AND t.id IS NULL"""
        )
        for bug in bugs:
            error_msg = bug["error_message"] or bug["llm_response"] or ""

            if bug["category"] == "error_no_response":
                assertion_type = "no_error"
                assertion_value = error_msg[:200]
            elif bug["category"] in ("wrong_data", "hallucination"):
                assertion_type = "no_hallucination_keyword"
                assertion_value = error_msg[:200]
            else:
                assertion_type = "has_content"
                assertion_value = None

            tickers_part = "_".join(
                t.lower() for t in (bug["tickers_referenced"] or [])[:2]
            ) or "general"
            test_name = f"regression_{bug['category']}_{tickers_part}"

            await conn.execute(
                """INSERT INTO llm_regression_tests
                   (bug_report_id, test_name, user_query, original_error,
                    assertion_type, assertion_value)
                   VALUES ($1, $2, $3, $4, $5, $6)""",
                bug["id"],
                test_name,
                bug["user_query"],
                error_msg,
                assertion_type,
                assertion_value,
            )
            created += 1

    return created


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def run(
    only_failing: bool,
    test_id: str | None,
    create_missing: bool,
) -> int:
    if create_missing:
        n = await create_missing_tests()
        print(f"Created {n} missing regression test(s)\n")

    # Fetch tests to run
    conditions: list[str] = []
    params: list = []
    idx = 1

    if test_id:
        conditions.append(f"id = ${idx}::uuid")
        params.append(test_id)
        idx += 1
    elif only_failing:
        conditions.append("last_result = 'fail'")

    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    async with get_conn() as conn:
        tests = await conn.fetch(
            f"""SELECT id, bug_report_id, test_name, user_query, original_error,
                       assertion_type, assertion_value, last_result, run_count
                FROM llm_regression_tests{where}
                ORDER BY created_at""",
            *params,
        )

    if not tests:
        print("No regression tests to run.")
        return 0

    print(f"{'='*70}")
    print(f"  LLM Regression Test Suite  —  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  {len(tests)} test(s) to run")
    print(f"{'='*70}\n")

    passed = 0
    failed = 0
    results: list[dict] = []

    for i, test in enumerate(tests, 1):
        print(f"  [{i}/{len(tests)}] {test['test_name']}...", end=" ", flush=True)
        result = await run_single_test(test)
        results.append(result)

        if result["passed"]:
            passed += 1
            print(f"PASS  ({result['duration_ms']}ms)  {result['detail']}")
        else:
            failed += 1
            print(f"FAIL  ({result['duration_ms']}ms)")
            print(f"         {result['detail']}")
            if result["error"]:
                print(f"         Error: {result['error'][:200]}")

    # Summary
    print(f"\n{'='*70}")
    print(f"  Results:  {passed} passed,  {failed} failed,  {len(tests)} total")
    if failed == 0:
        print("  All tests passed!")
    else:
        print(f"\n  Failing tests:")
        for r in results:
            if not r["passed"]:
                print(f"    - {r['test_name']}: {r['detail']}")
    print(f"{'='*70}\n")

    return failed


def main():
    parser = argparse.ArgumentParser(description="Run LLM regression tests")
    parser.add_argument("--only-failing", action="store_true", help="Only re-run failing tests")
    parser.add_argument("--test-id", default=None, help="Run a specific test by UUID")
    parser.add_argument("--create-missing", action="store_true", help="Create tests for resolved bugs that lack one")
    args = parser.parse_args()

    failures = asyncio.run(run(args.only_failing, args.test_id, args.create_missing))
    sys.exit(1 if failures > 0 else 0)


if __name__ == "__main__":
    main()
