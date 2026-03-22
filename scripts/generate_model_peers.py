#!/usr/bin/env python3
"""Populate model_peers for tickers that don't have peers defined.

Logic:
  - For each ticker in stocks with no rows in model_peers:
    - Find up to 5 peers with same sector AND industry
    - If fewer than 5, expand to sector-only to fill the set
    - Insert rows with created_by='system'
  - Idempotent: skips tickers that already have peers

Usage:
    python scripts/generate_model_peers.py
    python scripts/generate_model_peers.py --batch-size 100
"""
from __future__ import annotations

import argparse
import os
import uuid
from datetime import datetime
from pathlib import Path

import psycopg2
import structlog
from dotenv import load_dotenv
from psycopg2.extras import execute_values

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / ".env")

DATABASE_URL = os.environ.get("SUPABASE_DATABASE_URL", "")

log = structlog.get_logger()


def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def find_tickers_without_peers(conn) -> list[dict]:
    """Return tickers from stocks that have no rows in model_peers."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT s.ticker, s.sector, s.industry
            FROM stocks s
            LEFT JOIN model_peers mp ON mp.ticker = s.ticker
            WHERE mp.ticker IS NULL
            ORDER BY s.ticker
        """)
        return [
            {"ticker": row[0], "sector": row[1], "industry": row[2]}
            for row in cur.fetchall()
        ]


def find_peers_for_ticker(
    conn, ticker: str, sector: str | None, industry: str | None, limit: int = 5
) -> list[str]:
    """Find up to `limit` peer tickers.

    First tries sector + industry match, then falls back to sector-only.
    """
    peers: list[str] = []

    with conn.cursor() as cur:
        # Try sector + industry first
        if sector and industry:
            cur.execute(
                """SELECT ticker FROM stocks
                   WHERE sector = %s AND industry = %s AND ticker != %s
                   ORDER BY market_cap DESC NULLS LAST
                   LIMIT %s""",
                (sector, industry, ticker, limit),
            )
            peers = [row[0] for row in cur.fetchall()]

        # Fill remaining from sector-only if needed
        remaining = limit - len(peers)
        if remaining > 0 and sector:
            exclude = [ticker] + peers
            cur.execute(
                """SELECT ticker FROM stocks
                   WHERE sector = %s AND ticker != ALL(%s)
                   ORDER BY market_cap DESC NULLS LAST
                   LIMIT %s""",
                (sector, exclude, remaining),
            )
            peers.extend(row[0] for row in cur.fetchall())

    return peers[:limit]


def insert_peers(conn, ticker: str, peer_tickers: list[str]) -> int:
    """Insert peer rows into model_peers. Returns count inserted."""
    if not peer_tickers:
        return 0

    now = datetime.utcnow()
    values = [
        (str(uuid.uuid4()), ticker, peer, now, "system")
        for peer in peer_tickers
    ]

    with conn.cursor() as cur:
        execute_values(
            cur,
            """INSERT INTO model_peers (id, ticker, peer_ticker, created_at, created_by)
               VALUES %s
               ON CONFLICT DO NOTHING""",
            values,
        )
    return len(values)


# ---------------------------------------------------------------------------
# Async importable function (called by workflow)
# ---------------------------------------------------------------------------

async def generate_peers_for_ticker(ticker: str) -> list[str]:
    """Generate and store peer set for one ticker.

    Returns list of peer tickers. Idempotent — if peers already
    exist for this ticker, returns the existing set without inserting.
    """
    import sys
    sys.path.insert(0, str(ROOT / "backend"))

    conn = get_conn()

    # Check if peers already exist
    with conn.cursor() as cur:
        cur.execute(
            "SELECT peer_ticker FROM model_peers WHERE ticker = %s ORDER BY peer_ticker",
            (ticker,),
        )
        existing = [row[0] for row in cur.fetchall()]

    if existing:
        conn.close()
        return existing

    # Look up sector/industry for this ticker
    with conn.cursor() as cur:
        cur.execute(
            "SELECT sector, industry FROM stocks WHERE ticker = %s",
            (ticker,),
        )
        row = cur.fetchone()

    if not row:
        conn.close()
        return []

    sector, industry = row
    peers = find_peers_for_ticker(conn, ticker, sector, industry)
    insert_peers(conn, ticker, peers)
    conn.close()

    log.info("peers_generated", ticker=ticker, peers=peers)
    return peers


# ---------------------------------------------------------------------------
# Main (sync)
# ---------------------------------------------------------------------------

def run(batch_size: int = 100) -> dict:
    """Run peer generation. Returns summary dict."""
    conn = get_conn()

    tickers_to_process = find_tickers_without_peers(conn)
    log.info("tickers_needing_peers", count=len(tickers_to_process))

    if not tickers_to_process:
        log.info("all_tickers_have_peers")
        conn.close()
        return {"processed": 0, "peers_created": 0}

    processed = 0
    peers_created = 0

    for batch_start in range(0, len(tickers_to_process), batch_size):
        batch = tickers_to_process[batch_start : batch_start + batch_size]
        log.info(
            "processing_batch",
            batch_start=batch_start,
            batch_size=len(batch),
            total=len(tickers_to_process),
        )

        for stock in batch:
            peers = find_peers_for_ticker(
                conn, stock["ticker"], stock["sector"], stock["industry"]
            )
            count = insert_peers(conn, stock["ticker"], peers)
            peers_created += count
            processed += 1

            if processed % 50 == 0:
                log.info("progress", processed=processed, total=len(tickers_to_process))

    conn.close()

    summary = {"processed": processed, "peers_created": peers_created}
    log.info("job_complete", **summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description="Generate model peers for tickers")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size (default 100)")
    args = parser.parse_args()

    run(batch_size=args.batch_size)


if __name__ == "__main__":
    main()
