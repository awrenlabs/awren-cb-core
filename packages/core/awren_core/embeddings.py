"""Embedding service for generating vector representations of text.

Supports:
- OpenAI embeddings (text-embedding-3-small, text-embedding-ada-002)
- Deterministic hash-based fallback when no API key is configured

The embedding service is the bridge between raw text and Qdrant vector search.
Without proper embeddings, vector similarity search has no semantic value.
"""

import hashlib
import logging
from abc import ABC, abstractmethod
from typing import Optional

from awren_core.settings import get_settings

logger = logging.getLogger(__name__)

# Default vector dimensions for supported models
EMBEDDING_DIMENSIONS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class EmbeddingClient(ABC):
    """Abstract base for embedding providers."""

    def __init__(self, model: str, dimensions: int) -> None:
        self.model = model
        self.dimensions = dimensions

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Generate a vector embedding for the given text.

        Args:
            text: The input text to embed.

        Returns:
            A list of floats representing the embedding vector.
        """
        ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate vector embeddings for a batch of texts.

        Args:
            texts: The input texts to embed.

        Returns:
            A list of embedding vectors, one per input text.
        """
        ...


class OpenAIEmbeddingClient(EmbeddingClient):
    """Client for OpenAI embedding models (text-embedding-3-small, etc.).

    Requires ``OPENAI_API_KEY`` to be set in environment configuration.
    Gracefully returns a deterministic fallback vector if the API call fails.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: Optional[int] = None,
        base_url: Optional[str] = None,
    ) -> None:
        resolved_dims = dimensions or EMBEDDING_DIMENSIONS.get(model, 1536)
        super().__init__(model, resolved_dims)
        from openai import OpenAI

        kwargs: dict[str, str] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)

    def embed(self, text: str) -> list[float]:
        try:
            kwargs: dict[str, object] = {
                "model": self.model,
                "input": text,
            }
            if self.model.startswith("text-embedding-3"):
                kwargs["dimensions"] = self.dimensions
            response = self._client.embeddings.create(**kwargs)
            return response.data[0].embedding
        except Exception as e:
            logger.warning("OpenAI embedding failed, using fallback: %s", e)
            return _deterministic_vector(text, self.dimensions)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            kwargs: dict[str, object] = {
                "model": self.model,
                "input": texts,
            }
            if self.model.startswith("text-embedding-3"):
                kwargs["dimensions"] = self.dimensions
            response = self._client.embeddings.create(**kwargs)
            # Sort by index to preserve input order
            sorted_data = sorted(response.data, key=lambda d: d.index)
            return [d.embedding for d in sorted_data]
        except Exception as e:
            logger.warning("OpenAI batch embedding failed, using fallback: %s", e)
            return [_deterministic_vector(t, self.dimensions) for t in texts]


class FallbackEmbeddingClient(EmbeddingClient):
    """Deterministic hash-based embedding when no API key is configured.

    Produces a fixed-size vector by hashing the input text and repeating
    the hash pattern to fill the required dimensions.

    This provides ZERO semantic quality — it exists only to satisfy the
    interface contract when embeddings are needed for testing or when
    no embedding API key is available. DO NOT use in production.
    """

    def __init__(self, dimensions: int = 1536) -> None:
        super().__init__("fallback", dimensions)

    def embed(self, text: str) -> list[float]:
        return _deterministic_vector(text, self.dimensions)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [_deterministic_vector(t, self.dimensions) for t in texts]


def _deterministic_vector(text: str, dimensions: int) -> list[float]:
    """Generate a deterministic vector from text using md5 hashing.

    The output is consistent across calls with the same input,
    but has no semantic meaning. Useful as a fallback only.
    """
    h = hashlib.md5(text.encode()).hexdigest()
    values = [(int(h[i : i + 2], 16) / 255.0 - 0.5) * 2 for i in range(0, len(h) - 1, 2)]
    return (values * (dimensions // len(values) + 1))[:dimensions]


def create_embedding_client() -> EmbeddingClient:
    """Factory: create the appropriate embedding client based on settings.

    Priority:
    1. OpenAI embeddings (if ``openai_api_key`` is set)
    2. Fallback deterministic embeddings (no API key required)

    The embedding model and dimensions are configured via environment variables:
    - ``OPENAI_EMBEDDING_MODEL`` (default: ``text-embedding-3-small``)
    - ``OPENAI_EMBEDDING_DIMENSIONS`` (default: ``1536``)
    """
    settings = get_settings()

    model = settings.openai_embedding_model
    dimensions = settings.openai_embedding_dimensions

    if settings.openai_api_key:
        logger.info(
            "Using OpenAI embeddings: model=%s, dimensions=%d",
            model,
            dimensions,
        )
        return OpenAIEmbeddingClient(
            api_key=settings.openai_api_key,
            model=model,
            dimensions=dimensions,
            base_url=settings.openai_base_url or None,
        )

    logger.info("No OpenAI API key set; using fallback deterministic embeddings")
    return FallbackEmbeddingClient(dimensions=dimensions)
