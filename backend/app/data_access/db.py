"""Shared synchronous psycopg2 connection for the data-access layer."""
from __future__ import annotations

import os
import re

import psycopg2
from dotenv import load_dotenv

_env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
load_dotenv(_env_path)

_DSN: str = os.environ["SUPABASE_DATABASE_URL"]

_conn: psycopg2.extensions.connection | None = None


def _parse_dsn(dsn: str) -> str:
    """Re-encode the DSN so psycopg2 handles special-char passwords."""
    m = re.match(r"postgresql://([^:]+):(.+)@([^:]+):(\d+)/(.+)", dsn)
    if not m:
        return dsn
    user, password, host, port, dbname = m.groups()
    return (
        f"host={host} port={port} dbname={dbname} "
        f"user={user} password={password}"
    )


def get_sync_conn() -> psycopg2.extensions.connection:
    """Return a module-level singleton psycopg2 connection."""
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(_parse_dsn(_DSN))
        _conn.autocommit = True
    return _conn
