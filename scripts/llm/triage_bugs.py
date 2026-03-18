#!/usr/bin/env python3
"""Triage LLM bug reports: deduplicate, classify pipeline stage, and prioritize.

Usage:
    python scripts/triage_llm_bugs.py                  # triage all new bugs
    python scripts/triage_llm_bugs.py --status new     # only new bugs
    python scripts/triage_llm_bugs.py --dry-run        # preview without writing
    python scripts/triage_llm_bugs.py --generate-tests # also create regression tests for resolved bugs
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from difflib import SequenceMatcher

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

from app.mode2.db import get_conn  # noqa: E402

# ---------------------------------------------------------------------------
# Pipeline stage detection patterns
# ---------------------------------------------------------------------------
STAGE_PATTERNS: list[tuple[str, list[str]]] = [
    ("classifier", ["classify", "query_type", "classification", "JSON", "preamble"]),
    ("ticker_resolver", ["tickers", "stocks", "ticker", "resolution", "relation", "does not exist"]),
    ("retrieval", ["chunks", "vector", "embedding", "pgvector", "cosine", "similarity", "qa_library"]),
    ("generator", ["generate", "streaming", "anthropic", "claude", "max_tokens", "completion"]),
    ("session", ["session", "conversation", "compress", "summary", "turn_count"]),
    ("structured_data", ["financial_metrics", "metric_name", "period_end", "structured"]),
]


def detect_pipeline_stage(error_msg: str, description: str | None) -> str:
    """Guess which pipeline stage a bug originates from."""
    text = f"{error_msg} {description or ''}".lower()
    scores: dict[str, int] = defaultdict(int)
    for stage, keywords in STAGE_PATTERNS:
        for kw in keywords:
            if kw.lower() in text:
                scores[stage] += 1
    if scores:
        return max(scores, key=scores.get)
    return "unknown"


def similarity(a: str, b: str) -> float:
    """Quick string similarity ratio."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def error_fingerprint(error_msg: str) -> str:
    """Normalize an error message to a dedup key."""
    # Strip line numbers, UUIDs, timestamps
    normalized = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<UUID>", error_msg)
    normalized = re.sub(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}", "<TS>", normalized)
    normalized = re.sub(r"line \d+", "line N", normalized)
    normalized = normalized.strip().lower()
    return hashlib.md5(normalized.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Main triage logic
# ---------------------------------------------------------------------------
async def triage(status_filter: str | None, dry_run: bool, generate_tests: bool) -> None:
    conditions = []
    params: list = []
    idx = 1

    if status_filter:
        conditions.append(f"status = ${idx}")
        params.append(status_filter)
        idx += 1

    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    async with get_conn() as conn:
        bugs = await conn.fetch(
            f"""SELECT id, category, description, user_query, llm_response,
                       error_message, tickers_referenced, query_type, status,
                       user_id, created_at
                FROM llm_bug_reports{where}
                ORDER BY created_at DESC""",
            *params,
        )

    if not bugs:
        print("No bug reports found.")
        return

    print(f"\n{'='*70}")
    print(f"  LLM Bug Triage Report  —  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  {len(bugs)} report(s) found")
    print(f"{'='*70}\n")

    # -----------------------------------------------------------------------
    # Step 1: Deduplicate by error fingerprint
    # -----------------------------------------------------------------------
    clusters: dict[str, list[dict]] = defaultdict(list)
    for bug in bugs:
        fp = error_fingerprint(bug["error_message"] or bug["llm_response"] or "")
        clusters[fp].append(bug)

    # Also merge clusters with very similar error messages (>0.85 similarity)
    fingerprints = list(clusters.keys())
    merged: dict[str, str] = {}  # child_fp -> canonical_fp
    for i, fp_a in enumerate(fingerprints):
        if fp_a in merged:
            continue
        msg_a = clusters[fp_a][0]["error_message"] or clusters[fp_a][0]["llm_response"] or ""
        for fp_b in fingerprints[i + 1:]:
            if fp_b in merged:
                continue
            msg_b = clusters[fp_b][0]["error_message"] or clusters[fp_b][0]["llm_response"] or ""
            if similarity(msg_a, msg_b) > 0.85:
                merged[fp_b] = fp_a

    # Apply merges
    for child_fp, canonical_fp in merged.items():
        clusters[canonical_fp].extend(clusters.pop(child_fp))

    # -----------------------------------------------------------------------
    # Step 2: Classify each cluster
    # -----------------------------------------------------------------------
    print(f"  Unique issues: {len(clusters)}  (from {len(bugs)} reports)\n")

    cluster_data: list[dict] = []
    for fp, group in sorted(clusters.items(), key=lambda x: -len(x[1])):
        canonical = group[0]
        error_msg = canonical["error_message"] or canonical["llm_response"] or ""
        stage = detect_pipeline_stage(error_msg, canonical["description"])
        all_tickers = set()
        all_users = set()
        categories = set()
        statuses = set()
        for b in group:
            for t in (b["tickers_referenced"] or []):
                all_tickers.add(t)
            all_users.add(b["user_id"])
            categories.add(b["category"])
            statuses.add(b["status"])

        cluster_data.append({
            "fingerprint": fp,
            "count": len(group),
            "stage": stage,
            "error_preview": error_msg[:120],
            "tickers": sorted(all_tickers),
            "users": sorted(all_users),
            "categories": sorted(categories),
            "statuses": sorted(statuses),
            "canonical_id": str(canonical["id"]),
            "canonical_query": canonical["user_query"],
            "canonical_error": error_msg,
            "bugs": group,
        })

    # -----------------------------------------------------------------------
    # Step 3: Print triage report
    # -----------------------------------------------------------------------
    for i, c in enumerate(cluster_data, 1):
        status_str = ", ".join(c["statuses"])
        dup_note = f"  ({c['count']} duplicate reports)" if c["count"] > 1 else ""

        print(f"  [{i}] {c['stage'].upper():20s}  |  {status_str:10s}  |  reports: {c['count']}{dup_note}")
        print(f"      Error:    {c['error_preview']}")
        print(f"      Query:    {c['canonical_query'][:100]}")
        print(f"      Tickers:  {', '.join(c['tickers']) or '—'}")
        print(f"      Users:    {', '.join(c['users'])}")
        print(f"      Category: {', '.join(c['categories'])}")
        print()

    # -----------------------------------------------------------------------
    # Step 4: Auto-tag pipeline stage on new bugs
    # -----------------------------------------------------------------------
    if not dry_run:
        async with get_conn() as conn:
            for c in cluster_data:
                for bug in c["bugs"]:
                    if bug["status"] == "new":
                        # Update status to triaged and add stage info to description
                        existing_desc = bug["description"] or ""
                        stage_tag = f"[pipeline_stage: {c['stage']}]"
                        if stage_tag not in existing_desc:
                            new_desc = f"{stage_tag} {existing_desc}".strip()
                            await conn.execute(
                                """UPDATE llm_bug_reports
                                   SET status = 'triaged', description = $1
                                   WHERE id = $2 AND status = 'new'""",
                                new_desc, bug["id"],
                            )
                        # Link duplicates: if >1 report in cluster, mark extras
                        if c["count"] > 1 and str(bug["id"]) != c["canonical_id"]:
                            dup_note = f"[duplicate_of: {c['canonical_id']}]"
                            if dup_note not in (bug["description"] or ""):
                                await conn.execute(
                                    """UPDATE llm_bug_reports
                                       SET description = COALESCE(description, '') || ' ' || $1
                                       WHERE id = $2""",
                                    dup_note, bug["id"],
                                )

            print(f"  Updated {sum(1 for c in cluster_data for b in c['bugs'] if b['status'] == 'new')} new reports → triaged")

    # -----------------------------------------------------------------------
    # Step 5: Generate regression tests for resolved bugs
    # -----------------------------------------------------------------------
    if generate_tests and not dry_run:
        tests_created = 0
        async with get_conn() as conn:
            for c in cluster_data:
                for bug in c["bugs"]:
                    if bug["status"] != "resolved":
                        continue

                    # Check if a test already exists for this bug
                    existing = await conn.fetchrow(
                        "SELECT id FROM llm_regression_tests WHERE bug_report_id = $1",
                        bug["id"],
                    )
                    if existing:
                        continue

                    error_msg = bug["error_message"] or bug["llm_response"] or ""

                    # Determine assertion type based on the bug
                    if bug["category"] == "error_no_response":
                        assertion_type = "no_error"
                        assertion_value = error_msg[:200]
                    elif bug["category"] in ("wrong_data", "hallucination"):
                        assertion_type = "no_hallucination_keyword"
                        assertion_value = error_msg[:200]
                    else:
                        assertion_type = "has_content"
                        assertion_value = None

                    test_name = (
                        f"regression_{bug['category']}_{c['stage']}_"
                        f"{'_'.join(t.lower() for t in (bug['tickers_referenced'] or [])[:2]) or 'general'}"
                    )

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
                    tests_created += 1

        print(f"  Created {tests_created} regression test(s)")

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print(f"\n{'='*70}")
    by_stage = defaultdict(int)
    by_status = defaultdict(int)
    for c in cluster_data:
        by_stage[c["stage"]] += c["count"]
        for s in c["statuses"]:
            by_status[s] += c["count"]

    print("  By pipeline stage:")
    for stage, count in sorted(by_stage.items(), key=lambda x: -x[1]):
        print(f"    {stage:22s}  {count}")

    print("  By status:")
    for status, count in sorted(by_status.items(), key=lambda x: -x[1]):
        print(f"    {status:22s}  {count}")
    print(f"{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(description="Triage LLM bug reports")
    parser.add_argument("--status", default=None, help="Filter by status (new, triaged, resolved)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing changes")
    parser.add_argument("--generate-tests", action="store_true", help="Create regression tests for resolved bugs")
    args = parser.parse_args()

    asyncio.run(triage(args.status, args.dry_run, args.generate_tests))


if __name__ == "__main__":
    main()
