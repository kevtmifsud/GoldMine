from __future__ import annotations

import math

from app.config.settings import settings
from app.logging_config import get_logger

logger = get_logger(__name__)


def generate_embedding(text: str) -> list[float]:
    """Generate an embedding vector for the given text using Voyage AI.

    Falls back to a zero vector on error or if the API key is not set.
    """
    if not settings.ANTHROPIC_API_KEY:
        return _zero_vector()

    try:
        import voyageai

        client = voyageai.Client(api_key=settings.ANTHROPIC_API_KEY)
        result = client.embed([text], model=settings.EMBEDDING_MODEL)
        return result.embeddings[0]
    except Exception as e:
        logger.warning("embedding_generation_failed", error=str(e))
        return _zero_vector()


def batch_generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for multiple texts in a single batch call."""
    if not texts:
        return []

    if not settings.ANTHROPIC_API_KEY:
        return [_zero_vector() for _ in texts]

    try:
        import voyageai

        client = voyageai.Client(api_key=settings.ANTHROPIC_API_KEY)
        result = client.embed(texts, model=settings.EMBEDDING_MODEL)
        return result.embeddings
    except Exception as e:
        logger.warning("batch_embedding_failed", error=str(e))
        return [_zero_vector() for _ in texts]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b) or len(a) == 0:
        return 0.0

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot / (norm_a * norm_b)


def _zero_vector() -> list[float]:
    return [0.0] * settings.EMBEDDING_DIMENSIONS
