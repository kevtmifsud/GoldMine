#!/usr/bin/env python3
"""Supabase data quality checker.

Sweeps all tables in the GoldMine Supabase database and reports data fidelity
issues that could break downstream consumers (API, pipeline, frontend).

Checks:
  1. Fake NULLs      — '<NA>', 'nan', 'None', '', etc. stored instead of real NULL
  2. Duplicates       — rows sharing a natural key that should be unique
  3. Orphaned FKs     — child rows referencing non-existent parent rows
  4. Bad numerics     — varchar columns expected to hold numbers with junk values
  5. Bad dates        — varchar columns expected to hold dates with unparseable values
  6. Empty tables     — core tables that should never be empty
  7. Transcript data  — NULL transcript text, orphaned registry entries, stale chunks
  8. Row-count census — total rows per table (informational)

Usage:
    python scripts/data_quality/supabase/check_all_tables.py             # report only
    python scripts/data_quality/supabase/check_all_tables.py --fix       # auto-fix fake NULLs
    python scripts/data_quality/supabase/check_all_tables.py --verbose   # include row-count census
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(ROOT / "backend" / ".env")

DATABASE_URL = os.environ["SUPABASE_DATABASE_URL"]


# ═══════════════════════════════════════════════════════════════════════
# Config — all table-specific rules live here so they're easy to update
# ═══════════════════════════════════════════════════════════════════════

# Strings that should be NULL
FAKE_NULL_VALUES = {
    "<NA>", "nan", "NaN", "None", "null", "NULL",
    "N/A", "n/a", "NA", "#N/A", "",
}

# Natural-key uniqueness constraints (beyond the PK)
NATURAL_KEYS: dict[str, list[tuple[str, ...]]] = {
    "transcripts_list":  [("symbol", "fiscal_year", "fiscal_quarter")],
    "earnings_calendar": [("ticker", "report_date")],
    "sec_filings":       [("accession_number",)],
    "stocks":            [("ticker",)],
    "stock_betas":       [("ticker",)],
    "stock_history":     [("date", "ticker")],
    "financial_metrics": [("ticker", "metric_name", "period_end", "period_type")],
    "people":            [("person_id",)],
    "portfolio_trades":  [("date", "ticker", "action", "portfolio")],
    "processing_registry": [("file_path",)],
    "chunks":            [("document_id", "chunk_sequence")],
}

# Varchar columns that should hold numeric values
NUMERIC_VARCHAR_COLS: dict[str, list[str]] = {
    "stocks":           ["market_cap_b", "pe_ratio", "price", "52w_high", "52w_low",
                         "dividend_yield", "eps", "revenue_b", "full_time_employees"],
    "stock_betas":      ["beta"],
    "stock_history":    ["close", "eps_estimate", "eps_actual"],
    "portfolio_trades": ["shares", "price"],
    "portfolios":       ["aum", "long_exposure", "short_exposure", "num_positions",
                         "max_position_pct", "total_trades", "unique_tickers"],
    "people":           ["age", "pay", "exercised", "unexercised"],
}

# Varchar columns that should hold YYYY-MM-DD dates
DATE_VARCHAR_COLS: dict[str, list[str]] = {
    "earnings_calendar": ["report_date", "fiscal_quarter_ending"],
    "sec_filings":       ["filing_date", "report_date"],
    "stocks":            ["report_date"],
    "stock_history":     ["date"],
    "portfolio_trades":  ["date"],
    "portfolios":        ["inception_date"],
    "transcripts_list":  ["report_date"],
}

# FK-like references: (child_table, child_col, parent_table, parent_col)
FK_REFERENCES = [
    ("chunks",              "document_id",   "processing_registry", "document_id"),
    ("chunks",              "ticker",        "stocks",              "ticker"),
    ("processing_registry", "ticker",        "stocks",              "ticker"),
    ("transcripts_list",    "symbol",        "stocks",              "ticker"),
    ("sec_filings",         "symbol",        "stocks",              "ticker"),
    ("earnings_calendar",   "ticker",        "stocks",              "ticker"),
    ("stock_history",       "ticker",        "stocks",              "ticker"),
    ("stock_betas",         "ticker",        "stocks",              "ticker"),
    ("financial_metrics",   "ticker",        "stocks",              "ticker"),
    ("portfolio_trades",    "portfolio",     "portfolios",          "portfolio_id"),
    ("sessions",            "conversation_id", "conversations",     "id"),
    ("messages",            "session_id",    "sessions",            "id"),
]

# Tables that must never be empty
CORE_TABLES = {
    "stocks", "stock_history", "financial_metrics", "transcripts_list",
    "sec_filings", "earnings_calendar", "people", "chunks",
    "processing_registry",
}


# ═══════════════════════════════════════════════════════════════════════
# DB helpers
# ═══════════════════════════════════════════════════════════════════════

def _parse_dsn(dsn: str) -> str:
    """Re-encode the DSN so psycopg2 handles special-char passwords."""
    m = re.match(r"postgresql://([^:]+):(.+)@([^:]+):(\d+)/(.+)", dsn)
    if not m:
        return dsn
    user, password, host, port, dbname = m.groups()
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


def _get_text_columns(cur) -> list[tuple[str, str]]:
    """Return all (table, column) pairs for varchar/text columns."""
    cur.execute("""
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND data_type IN ('character varying', 'text')
        ORDER BY table_name, ordinal_position
    """)
    return cur.fetchall()


def _get_all_tables(cur) -> list[str]:
    """Return all public table names."""
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    return [r[0] for r in cur.fetchall()]


# ═══════════════════════════════════════════════════════════════════════
# Checker
# ═══════════════════════════════════════════════════════════════════════

class DataQualityChecker:
    """Runs all data quality checks and collects issues."""

    SEVERITY_ICON = {"ERROR": "!!", "WARN": "! ", "INFO": "  "}

    def __init__(self, cur, *, fix: bool = False, verbose: bool = False):
        self.cur = cur
        self.fix = fix
        self.verbose = verbose
        self.issues: list[dict] = []

    def _add(self, severity: str, table: str, check: str, detail: str, count: int = 0):
        self.issues.append(
            {"severity": severity, "table": table, "check": check,
             "detail": detail, "count": count}
        )

    # ── helpers ────────────────────────────────────────────────────────
    def _safe_query(self, sql: str, params=None) -> list | None:
        """Execute a query, returning None on error (rolls back cleanly)."""
        try:
            self.cur.execute(sql, params)
            return self.cur.fetchall()
        except Exception:
            self.cur.execute("ROLLBACK")
            self.cur.execute("BEGIN")
            return None

    # ── 1. Fake NULLs ─────────────────────────────────────────────────
    def check_fake_nulls(self):
        """Find varchar/text columns containing sentinel values instead of NULL."""
        text_cols = _get_text_columns(self.cur)
        placeholders = ", ".join(["%s"] * len(FAKE_NULL_VALUES))
        fake_list = list(FAKE_NULL_VALUES)

        for table, column in text_cols:
            self.cur.execute(
                f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" IN ({placeholders})',
                fake_list,
            )
            cnt = self.cur.fetchone()[0]
            if cnt == 0:
                continue

            self.cur.execute(
                f'SELECT DISTINCT "{column}" FROM "{table}" '
                f'WHERE "{column}" IN ({placeholders}) LIMIT 5',
                fake_list,
            )
            samples = [r[0] for r in self.cur.fetchall()]

            if self.fix:
                self.cur.execute(
                    f'UPDATE "{table}" SET "{column}" = NULL '
                    f'WHERE "{column}" IN ({placeholders})',
                    fake_list,
                )
                self._add("WARN", table, "fake_null",
                          f"{column}: {cnt} fake NULLs {samples} -> FIXED", cnt)
            else:
                self._add("WARN", table, "fake_null",
                          f"{column}: {cnt} rows with fake NULLs {samples}", cnt)

    # ── 2. Duplicates ──────────────────────────────────────────────────
    def check_duplicates(self):
        """Find duplicate rows on declared natural keys."""
        for table, key_groups in NATURAL_KEYS.items():
            for key_cols in key_groups:
                cols_sql = ", ".join(f'"{c}"' for c in key_cols)
                rows = self._safe_query(f"""
                    SELECT {cols_sql}, COUNT(*) AS cnt
                    FROM "{table}"
                    GROUP BY {cols_sql}
                    HAVING COUNT(*) > 1
                    ORDER BY cnt DESC
                    LIMIT 10
                """)
                if not rows:
                    continue
                total = sum(r[-1] for r in rows)
                key_label = " + ".join(key_cols)
                samples = [dict(zip(list(key_cols) + ["count"], r)) for r in rows[:3]]
                self._add("ERROR", table, "duplicate",
                          f"{key_label}: {len(rows)} duplicate groups "
                          f"({total} extra rows): {samples}", total)

    # ── 3. Orphaned FK references ──────────────────────────────────────
    def check_orphans(self):
        """Find child rows whose FK-like column points to a missing parent."""
        for child_tbl, child_col, parent_tbl, parent_col in FK_REFERENCES:
            rows = self._safe_query(f"""
                SELECT COUNT(*)
                FROM "{child_tbl}" c
                LEFT JOIN "{parent_tbl}" p
                    ON c."{child_col}"::text = p."{parent_col}"::text
                WHERE p."{parent_col}" IS NULL
                  AND c."{child_col}" IS NOT NULL
            """)
            if rows is None:
                continue
            cnt = rows[0][0]
            if cnt == 0:
                continue

            sample_rows = self._safe_query(f"""
                SELECT DISTINCT c."{child_col}"
                FROM "{child_tbl}" c
                LEFT JOIN "{parent_tbl}" p
                    ON c."{child_col}"::text = p."{parent_col}"::text
                WHERE p."{parent_col}" IS NULL
                  AND c."{child_col}" IS NOT NULL
                LIMIT 5
            """) or []
            samples = [r[0] for r in sample_rows]
            self._add("WARN", child_tbl, "orphan_fk",
                      f"{child_col} -> {parent_tbl}.{parent_col}: "
                      f"{cnt} orphaned rows, e.g. {samples}", cnt)

    # ── 4. Numeric-in-varchar ──────────────────────────────────────────
    def check_numeric_varchars(self):
        """Find non-numeric junk in columns that should store numbers."""
        for table, columns in NUMERIC_VARCHAR_COLS.items():
            for col in columns:
                rows = self._safe_query(f"""
                    SELECT COUNT(*),
                           array_agg(DISTINCT "{col}" ORDER BY "{col}" LIMIT 5)
                    FROM (
                        SELECT "{col}" FROM "{table}"
                        WHERE "{col}" IS NOT NULL
                          AND "{col}" !~ '^-?[0-9]*\\.?[0-9]+([eE][+-]?[0-9]+)?$'
                        LIMIT 1000
                    ) sub
                """)
                if rows is None:
                    continue
                cnt = rows[0][0]
                if cnt > 0:
                    samples = rows[0][1] or []
                    self._add("WARN", table, "bad_numeric",
                              f"{col}: {cnt} non-numeric values: {samples[:5]}", cnt)

    # ── 5. Date-in-varchar ─────────────────────────────────────────────
    def check_date_varchars(self):
        """Find non-date junk in columns that should store YYYY-MM-DD dates."""
        for table, columns in DATE_VARCHAR_COLS.items():
            for col in columns:
                rows = self._safe_query(f"""
                    SELECT COUNT(*),
                           array_agg(DISTINCT "{col}" ORDER BY "{col}" LIMIT 5)
                    FROM (
                        SELECT "{col}" FROM "{table}"
                        WHERE "{col}" IS NOT NULL
                          AND "{col}" !~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}'
                        LIMIT 1000
                    ) sub
                """)
                if rows is None:
                    continue
                cnt = rows[0][0]
                if cnt > 0:
                    samples = rows[0][1] or []
                    self._add("WARN", table, "bad_date",
                              f"{col}: {cnt} non-date values: {samples[:5]}", cnt)

    # ── 6. Empty core tables ───────────────────────────────────────────
    def check_empty_tables(self):
        """Flag core tables that are unexpectedly empty."""
        for table in sorted(CORE_TABLES):
            self.cur.execute(f'SELECT COUNT(*) FROM "{table}"')
            cnt = self.cur.fetchone()[0]
            if cnt == 0:
                self._add("ERROR", table, "empty_table",
                          "Core table is empty — expected data", 0)

    # ── 7. Transcript integrity ────────────────────────────────────────
    def check_transcripts(self):
        """Transcript-specific: NULL text, orphaned registry, stale chunks."""
        # Transcripts rows with NULL text body
        self.cur.execute(
            "SELECT COUNT(*) FROM transcripts_list WHERE transcripts IS NULL"
        )
        cnt = self.cur.fetchone()[0]
        if cnt > 0:
            self._add("WARN", "transcripts_list", "null_transcript_text",
                       f"{cnt} rows with NULL transcripts text", cnt)

        # processing_registry entries whose virtual path has no transcript row
        self.cur.execute("""
            SELECT COUNT(*)
            FROM processing_registry pr
            WHERE pr.file_path LIKE '/transcripts/%%'
              AND NOT EXISTS (
                  SELECT 1 FROM transcripts_list tl
                  WHERE tl.symbol = pr.ticker
                    AND '/transcripts/' || tl.symbol || '/'
                        || tl.fiscal_year || '_Q' || tl.fiscal_quarter || '.txt'
                        = pr.file_path
              )
        """)
        cnt = self.cur.fetchone()[0]
        if cnt > 0:
            self._add("WARN", "processing_registry", "orphan_registry",
                       f"{cnt} registry entries with no matching transcript row", cnt)

        # Inactive chunks with zero active replacements for the same document
        self.cur.execute("""
            SELECT COUNT(*)
            FROM chunks c
            WHERE c.is_active = FALSE
              AND NOT EXISTS (
                  SELECT 1 FROM chunks c2
                  WHERE c2.document_id = c.document_id AND c2.is_active = TRUE
              )
        """)
        cnt = self.cur.fetchone()[0]
        if cnt > 0:
            self._add("INFO", "chunks", "inactive_no_replacement",
                       f"{cnt} inactive chunks with no active replacement", cnt)

    # ── 8. Row-count census (verbose only) ─────────────────────────────
    def check_row_counts(self):
        """Print row counts for every table (informational)."""
        tables = _get_all_tables(self.cur)
        for table in tables:
            self.cur.execute(f'SELECT COUNT(*) FROM "{table}"')
            cnt = self.cur.fetchone()[0]
            self._add("INFO", table, "row_count", f"{cnt:,} rows", cnt)

    # ── orchestrator ───────────────────────────────────────────────────
    def run_all(self) -> int:
        """Run every check and print results. Returns error count."""
        checks = [
            ("Fake NULLs",          self.check_fake_nulls),
            ("Duplicates",          self.check_duplicates),
            ("Orphaned FK refs",    self.check_orphans),
            ("Numeric-in-varchar",  self.check_numeric_varchars),
            ("Date-in-varchar",     self.check_date_varchars),
            ("Empty core tables",   self.check_empty_tables),
            ("Transcript integrity", self.check_transcripts),
        ]
        if self.verbose:
            checks.append(("Row-count census", self.check_row_counts))

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"Supabase Data Quality Check — {ts}")

        for label, fn in checks:
            print(f"\n{'─' * 60}")
            print(f"  {label}")
            print(f"{'─' * 60}")
            before = len(self.issues)
            fn()
            found = len(self.issues) - before
            if found == 0:
                print("  PASS")
            else:
                for issue in self.issues[before:]:
                    icon = self.SEVERITY_ICON[issue["severity"]]
                    print(f"  [{icon}] {issue['table']}: {issue['detail']}")

        # summary
        errors = sum(1 for i in self.issues if i["severity"] == "ERROR")
        warns  = sum(1 for i in self.issues if i["severity"] == "WARN")
        infos  = sum(1 for i in self.issues if i["severity"] == "INFO")
        print(f"\n{'═' * 60}")
        print(f"  Result: {errors} errors, {warns} warnings, {infos} info")
        if self.fix:
            fixed = sum(1 for i in self.issues
                        if i["check"] == "fake_null" and "FIXED" in i["detail"])
            print(f"  Fixed:  {fixed} fake-NULL columns cleaned")
        print(f"{'═' * 60}")
        return errors


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════

def main() -> None:
    fix     = "--fix" in sys.argv
    verbose = "--verbose" in sys.argv

    if fix:
        print("** FIX MODE — will convert fake NULLs to real NULLs **\n")

    conn = psycopg2.connect(_parse_dsn(DATABASE_URL))
    conn.autocommit = True
    cur = conn.cursor()

    checker = DataQualityChecker(cur, fix=fix, verbose=verbose)
    errors = checker.run_all()

    cur.close()
    conn.close()
    sys.exit(1 if errors > 0 else 0)


if __name__ == "__main__":
    main()
