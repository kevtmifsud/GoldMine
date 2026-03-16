"""Pipeline configuration — reads from environment."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from backend directory
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path)

DATABASE_URL: str = os.environ["SUPABASE_DATABASE_URL"]
OPENAI_API_KEY: str = os.environ["OPENAI_API_KEY"]
ANTHROPIC_API_KEY: str = os.environ.get("GOLDMINE_ANTHROPIC_API_KEY", "")

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
TRANSCRIPTS_DIR = PROJECT_ROOT / "data" / "structured" / "transcripts"

# Embedding settings
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSIONS = 1536
EMBEDDING_BATCH_SIZE = 50

# Chunking settings
MIN_CHUNK_TOKENS = 200
MAX_CHUNK_TOKENS = 1000
TARGET_CHUNK_TOKENS = 600

# Pipeline settings
WORKER_CONCURRENCY = 10
STUCK_JOB_TIMEOUT_HOURS = 2
