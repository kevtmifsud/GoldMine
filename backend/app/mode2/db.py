"""Async database connection pool for Mode 2."""
from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager

import asyncpg
from dotenv import load_dotenv

_env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
load_dotenv(_env_path)

DATABASE_URL: str = os.environ["SUPABASE_DATABASE_URL"]


def _parse_dsn(dsn: str) -> dict:
    """Parse a PostgreSQL DSN with special characters in password."""
    # postgresql://user:pass@host:port/dbname
    m = re.match(r"postgresql://([^:]+):(.+)@([^:]+):(\d+)/(.+)", dsn)
    if not m:
        raise ValueError(f"Cannot parse DSN: {dsn[:30]}...")
    return {
        "user": m.group(1),
        "password": m.group(2),
        "host": m.group(3),
        "port": int(m.group(4)),
        "database": m.group(5),
    }


_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Get or create the connection pool."""
    global _pool
    if _pool is None:
        params = _parse_dsn(DATABASE_URL)
        _pool = await asyncpg.create_pool(min_size=2, max_size=10, **params)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_conn():
    """Async context manager for a database connection."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn
