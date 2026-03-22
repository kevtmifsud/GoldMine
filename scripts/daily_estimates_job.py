#!/usr/bin/env python3
"""Daily estimates forward-fill job.

Populates daily_estimates by reading all four log tables and forward-filling
each estimate event across calendar dates.

Usage:
    python scripts/daily_estimates_job.py --tickers AAPL
    python scripts/daily_estimates_job.py --tickers AAPL MSFT --start-date 2023-01-01
    python scripts/daily_estimates_job.py  # all tickers with estimates
"""
from __future__ import annotations

import argparse
import os
from datetime import date, timedelta
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")
DATABASE_URL = os.environ.get("SUPABASE_DATABASE_URL", "")


def period_to_dates(period: str) -> tuple[date, date]:
    if "Q1" in period:
        y = int(period[:4])
        return date(y, 1, 1), date(y, 3, 31)
    elif "Q2" in period:
        y = int(period[:4])
        return date(y, 4, 1), date(y, 6, 30)
    elif "Q3" in period:
        y = int(period[:4])
        return date(y, 7, 1), date(y, 9, 30)
    elif "Q4" in period:
        y = int(period[:4])
        return date(y, 10, 1), date(y, 12, 31)
    elif period.endswith("A"):
        y = int(period[:4])
        return date(y, 1, 1), date(y, 12, 31)
    else:
        raise ValueError(f"Unknown period: {period}")


# Source table configs: (source_name, table_name, firm_col, analyst_name_expr, user_id_col)
SOURCE_CONFIGS = [
    ("consensus", "consensus_estimates", None, None, None),
    ("buyside", "buyside_estimates", "firm", "analyst_name", None),
    ("internal", "internal_estimates", None, None, "user_id"),
    ("sellside", "sellside_estimates", "firm", "analysts[1]", None),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily estimates forward-fill job")
    parser.add_argument("--tickers", nargs="+", default=None)
    parser.add_argument("--start-date", default="2023-01-01")
    parser.add_argument("--end-date", default=date.today().isoformat())
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Build analyst lookup: (name, org) -> person_id
    cur.execute(
        """SELECT person_id, name, organization
           FROM people
           WHERE type IN ('buyside_analyst', 'sellside_analyst')"""
    )
    analyst_lookup = {(r[1], r[2]): r[0] for r in cur.fetchall()}

    # Build user display_name lookup
    cur.execute("SELECT user_id, display_name FROM user_profiles")
    user_display_names = {str(r[0]): r[1] for r in cur.fetchall()}

    # Determine tickers
    if args.tickers:
        tickers = args.tickers
    else:
        # All tickers with any estimates
        ticker_set = set()
        for _, table, _, _, _ in SOURCE_CONFIGS:
            cur.execute(f"SELECT DISTINCT ticker FROM {table}")
            for r in cur.fetchall():
                ticker_set.add(r[0])
        tickers = sorted(ticker_set)

    if not tickers:
        print("No tickers found with estimates.")
        return

    print(f"Processing {len(tickers)} ticker(s): {', '.join(tickers[:10])}{'...' if len(tickers) > 10 else ''}")
    print(f"Date range: {start_date} to {end_date}")

    total_inserted = 0

    for ticker in tickers:
        ticker_counts = {}

        for source, table, firm_col, analyst_expr, user_id_col in SOURCE_CONFIGS:
            source_count = 0

            # Build SELECT columns
            select_cols = "metric, period, value, unit, estimate_date"
            if firm_col:
                select_cols += f", {firm_col}"
            if analyst_expr:
                select_cols += f", {analyst_expr} AS analyst_name"
            if user_id_col:
                select_cols += f", {user_id_col}"

            # Get distinct combos
            group_cols = "metric, period"
            if firm_col:
                group_cols += f", {firm_col}"
            if analyst_expr:
                group_cols += f", {analyst_expr}"

            cur.execute(
                f"SELECT DISTINCT {group_cols} FROM {table} WHERE ticker = %s",
                (ticker,),
            )
            combos = cur.fetchall()

            for combo in combos:
                metric = combo[0]
                period = combo[1]
                col_idx = 2
                firm = None
                combo_analyst_name = None
                if firm_col:
                    firm = combo[col_idx]
                    col_idx += 1
                if analyst_expr:
                    combo_analyst_name = combo[col_idx]
                    col_idx += 1

                try:
                    period_start, period_end = period_to_dates(period)
                except ValueError:
                    continue

                # Fetch all events for this combo
                where = "ticker = %s AND metric = %s AND period = %s"
                params: list = [ticker, metric, period]
                if firm_col and firm is not None:
                    where += f" AND {firm_col} = %s"
                    params.append(firm)
                if analyst_expr and combo_analyst_name is not None:
                    where += f" AND {analyst_expr} = %s"
                    params.append(combo_analyst_name)

                cur.execute(
                    f"SELECT {select_cols} FROM {table} WHERE {where} ORDER BY estimate_date ASC",
                    params,
                )
                events = cur.fetchall()
                if not events:
                    continue

                # Parse events into dicts
                parsed_events = []
                for ev in events:
                    d = {
                        "metric": ev[0],
                        "period": ev[1],
                        "value": ev[2],
                        "unit": ev[3],
                        "estimate_date": ev[4],
                    }
                    col_idx = 5
                    if firm_col:
                        d["firm"] = ev[col_idx]
                        col_idx += 1
                    if analyst_expr:
                        d["analyst_name"] = ev[col_idx]
                        col_idx += 1
                    if user_id_col:
                        d["user_id"] = ev[col_idx]
                        col_idx += 1
                    parsed_events.append(d)

                # Forward fill
                first_estimate_date = parsed_events[0]["estimate_date"]
                fill_start = max(start_date, first_estimate_date)
                fill_end = min(end_date, period_end + timedelta(days=90))

                if fill_start > fill_end:
                    continue

                rows_to_insert = []
                event_idx = 0
                cal_date = fill_start

                while cal_date <= fill_end:
                    # Advance to most recent event for this date
                    while (
                        event_idx + 1 < len(parsed_events)
                        and parsed_events[event_idx + 1]["estimate_date"] <= cal_date
                    ):
                        event_idx += 1

                    active = parsed_events[event_idx]
                    if active["estimate_date"] > cal_date:
                        cal_date += timedelta(days=1)
                        continue

                    # Resolve analyst info
                    analyst_name = None
                    analyst_person_id = None
                    user_id = None

                    if source == "internal":
                        user_id = active.get("user_id")
                        if user_id:
                            analyst_name = user_display_names.get(str(user_id))
                    elif source in ("buyside", "sellside"):
                        analyst_name = active.get("analyst_name")
                        if analyst_name and firm:
                            analyst_person_id = analyst_lookup.get((analyst_name, firm))

                    rows_to_insert.append((
                        ticker,
                        active["metric"],
                        period,
                        period_start,
                        period_end,
                        source,
                        firm or "",
                        analyst_name or "",
                        analyst_person_id,
                        str(user_id) if user_id else None,
                        float(active["value"]),
                        active.get("unit"),
                        active["estimate_date"],
                        cal_date,
                    ))

                    # Batch insert every 1000 rows
                    if len(rows_to_insert) >= 1000:
                        execute_values(
                            cur,
                            """INSERT INTO daily_estimates
                               (ticker, metric, period, period_start_date, period_end_date,
                                source, firm, analyst_name, analyst_person_id, user_id,
                                value, unit, estimate_date, as_of_date)
                               VALUES %s
                               ON CONFLICT ON CONSTRAINT daily_estimates_unique_key
                               DO NOTHING""",
                            rows_to_insert,
                        )
                        source_count += len(rows_to_insert)
                        total_inserted += len(rows_to_insert)
                        rows_to_insert = []
                        if total_inserted % 10000 < 1000:
                            print(f"  ... {total_inserted:,} rows inserted so far")

                    cal_date += timedelta(days=1)

                if rows_to_insert:
                    execute_values(
                        cur,
                        """INSERT INTO daily_estimates
                           (ticker, metric, period, period_start_date, period_end_date,
                            source, firm, analyst_name, analyst_person_id, user_id,
                            value, unit, estimate_date, as_of_date)
                           VALUES %s
                           ON CONFLICT ON CONSTRAINT daily_estimates_unique_key
                           DO NOTHING""",
                        rows_to_insert,
                    )
                    source_count += len(rows_to_insert)
                    total_inserted += len(rows_to_insert)

            ticker_counts[source] = source_count
            conn.commit()

        # Print ticker summary
        ticker_total = sum(ticker_counts.values())
        print(f"\n{ticker} daily_estimates complete:")
        for src, cnt in ticker_counts.items():
            print(f"  {src + ':':12s} {cnt:>8,} rows")
        print(f"  {'Total:':12s} {ticker_total:>8,} rows")
        print(f"  Date range: {start_date} to {end_date}")

    # Final summary
    cur.execute("SELECT ROUND(AVG(staleness_days), 1) FROM daily_estimates WHERE ticker = ANY(%s)", (tickers,))
    avg_staleness = cur.fetchone()[0]
    print(f"\nAll done. {total_inserted:,} total rows inserted. Avg staleness: {avg_staleness} days")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
