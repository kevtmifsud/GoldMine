"""WF-04: Embedding Generation & Vector Storage.

Generates embeddings for chunks using OpenAI text-embedding-3-large and
stores them in the Supabase chunks table.
"""
from __future__ import annotations

import time

from openai import OpenAI

from .config import OPENAI_API_KEY, EMBEDDING_MODEL, EMBEDDING_DIMENSIONS, EMBEDDING_BATCH_SIZE
from .chunking import Chunk


def _build_embedding_input(chunk: Chunk, ticker: str, document_type: str, fiscal_period: str) -> str:
    """Prepend metadata context to chunk text for better retrieval relevance."""
    doc_label = document_type.replace("_", " ").title()
    return f"Ticker: {ticker} | Document: {doc_label} {fiscal_period} | Section: {chunk.section_name}\n{chunk.chunk_text}"


def generate_embeddings(
    chunks: list[Chunk],
    ticker: str,
    document_type: str,
    fiscal_period: str,
) -> list[list[float]]:
    """Generate embeddings for a list of chunks using OpenAI.

    Returns a list of embedding vectors, one per chunk.
    Handles batching and retries.
    """
    client = OpenAI(api_key=OPENAI_API_KEY)
    texts = [_build_embedding_input(c, ticker, document_type, fiscal_period) for c in chunks]

    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch = texts[i : i + EMBEDDING_BATCH_SIZE]

        for attempt in range(3):
            try:
                response = client.embeddings.create(
                    model=EMBEDDING_MODEL,
                    input=batch,
                    dimensions=EMBEDDING_DIMENSIONS,
                )
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)
                break
            except Exception as e:
                if attempt < 2:
                    wait = 2 ** (attempt + 1)
                    print(f"    Embedding API error (attempt {attempt + 1}): {e}. Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    raise

    return all_embeddings


def store_chunks(
    cur,
    document_id: str,
    ticker: str,
    document_type: str,
    fiscal_period: str,
    chunks: list[Chunk],
    embeddings: list[list[float]],
    filing_date=None,
) -> int:
    """Store chunks with embeddings in Supabase.

    Returns the number of chunks stored.
    """
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

        cur.execute(
            """INSERT INTO chunks
               (document_id, ticker, document_type, section_name, section_type,
                fiscal_period, filing_date, chunk_sequence, word_count,
                chunk_text, embedding, is_active)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector, TRUE)""",
            (
                document_id,
                ticker,
                document_type,
                chunk.section_name,
                chunk.section_type,
                fiscal_period,
                filing_date,
                chunk.chunk_sequence,
                chunk.word_count,
                chunk.chunk_text,
                embedding_str,
            ),
        )

    return len(chunks)


def get_embedding_cost(chunk_count: int, avg_tokens_per_chunk: int = 500) -> float:
    """Estimate embedding cost in USD."""
    total_tokens = chunk_count * avg_tokens_per_chunk
    # text-embedding-3-large at 1536 dims: $0.065 per 1M tokens
    return total_tokens / 1_000_000 * 0.065
