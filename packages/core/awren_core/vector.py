"""Qdrant vector store connection manager and repository.

Provides persistent vector storage for the Memory Engine,
enabling semantic search across episodic, semantic, procedural,
and working memory types.
"""

import logging
from typing import Any, Optional
from uuid import UUID

from awren_core.settings import get_settings

logger = logging.getLogger(__name__)

# Collection names for each memory type
COLLECTION_EPISODIC = "memory_episodic"
COLLECTION_SEMANTIC = "memory_semantic"
COLLECTION_PROCEDURAL = "memory_procedural"
COLLECTION_WORKING = "memory_working"
COLLECTION_ENTITIES = "entities"

# Default vector size (1536 = text-embedding-3-small compatible)
DEFAULT_VECTOR_SIZE = 1536


class QdrantConnection:
    """Manages the Qdrant client connection lifecycle (lazy singleton)."""

    def __init__(self) -> None:
        self._client: Any = None

    @property
    def client(self) -> Any:
        """Lazy-initialized Qdrant client."""
        if self._client is None:
            from qdrant_client import QdrantClient

            settings = get_settings()
            self._client = QdrantClient(url=settings.qdrant_url)
        return self._client

    def close(self) -> None:
        """Close the Qdrant client connection."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "QdrantConnection":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


_connection: Optional[QdrantConnection] = None


def get_vector_db() -> QdrantConnection:
    """Get or create the singleton Qdrant connection."""
    global _connection
    if _connection is None:
        _connection = QdrantConnection()
    return _connection


class VectorRepository:
    """Qdrant-based vector repository for storing and searching memories.

    Each memory type (episodic, semantic, procedural, working) is stored
    in its own collection with configurable vector size.

    Uses payload filtering for metadata queries and dense vector search
    for semantic similarity.
    """

    def __init__(
        self,
        connection: Optional[QdrantConnection] = None,
        vector_size: int = DEFAULT_VECTOR_SIZE,
    ) -> None:
        self._connection = connection or get_vector_db()
        self._vector_size = vector_size

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    def _collection_name(self, memory_type: str) -> str:
        """Get the collection name for a memory type."""
        mapping = {
            "episodic": COLLECTION_EPISODIC,
            "semantic": COLLECTION_SEMANTIC,
            "procedural": COLLECTION_PROCEDURAL,
            "working": COLLECTION_WORKING,
        }
        return mapping.get(memory_type, COLLECTION_SEMANTIC)

    def ensure_collection(self, memory_type: str) -> None:
        """Create the collection if it doesn't exist."""
        from qdrant_client.http.models import Distance, VectorParams

        name = self._collection_name(memory_type)
        try:
            self._connection.client.get_collection(name)
        except Exception:
            # Collection doesn't exist — create it
            self._connection.client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(
                    size=self._vector_size,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("Created Qdrant collection: %s", name)

    def ensure_all_collections(self) -> None:
        """Ensure all memory type collections exist."""
        for mem_type in ("episodic", "semantic", "procedural", "working"):
            self.ensure_collection(mem_type)

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    @staticmethod
    def _point_id(memory_id: str) -> int:
        """Generate a deterministic Qdrant point ID from a string memory ID.

        Uses UUID parsing when possible, falls back to a stable hash.
        """
        try:
            return UUID(memory_id).int % (2**63)
        except (ValueError, AttributeError):
            import hashlib

            return int(hashlib.md5(memory_id.encode()).hexdigest(), 16) % (2**63)

    def upsert(
        self,
        memory_id: str,
        vector: list[float],
        payload: dict[str, Any],
        memory_type: str = "semantic",
    ) -> None:
        """Insert or update a memory vector and its payload."""
        from qdrant_client.http.models import PointStruct

        self.ensure_collection(memory_type)
        point = PointStruct(
            id=self._point_id(memory_id),
            vector=vector,
            payload={"memory_id": memory_id, **payload},
        )
        self._connection.client.upsert(
            collection_name=self._collection_name(memory_type),
            points=[point],
        )

    def delete(self, memory_id: str, memory_type: str = "semantic") -> None:
        """Delete a memory by ID."""
        from qdrant_client.http import models as qdrant_models

        self._connection.client.delete(
            collection_name=self._collection_name(memory_type),
            points_selector=qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="memory_id",
                        match=qdrant_models.MatchValue(value=memory_id),
                    )
                ]
            ),
        )

    def get(self, memory_id: str, memory_type: str = "semantic") -> Optional[dict[str, Any]]:
        """Retrieve a memory by ID."""
        from qdrant_client.http import models as qdrant_models

        result = self._connection.client.scroll(
            collection_name=self._collection_name(memory_type),
            scroll_filter=qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="memory_id",
                        match=qdrant_models.MatchValue(value=memory_id),
                    )
                ]
            ),
            limit=1,
        )
        points = result[0]
        if points:
            return points[0].payload
        return None

    # ------------------------------------------------------------------
    # Semantic search
    # ------------------------------------------------------------------

    def search(
        self,
        vector: list[float],
        query_filter: Optional[dict[str, Any]] = None,
        memory_type: str = "semantic",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search memories by vector similarity with optional payload filter."""
        from qdrant_client.http import models as qdrant_models

        filter_conditions: list[Any] = []
        if query_filter:
            for key, value in query_filter.items():
                filter_conditions.append(
                    qdrant_models.FieldCondition(
                        key=key,
                        match=qdrant_models.MatchValue(value=value),
                    )
                )

        search_result = self._connection.client.search(
            collection_name=self._collection_name(memory_type),
            query_vector=vector,
            query_filter=qdrant_models.Filter(must=filter_conditions) if filter_conditions else None,
            limit=limit,
        )
        return [
            {
                "id": hit.id,
                "score": hit.score,
                "payload": hit.payload,
            }
            for hit in search_result
        ]

    def search_across_types(
        self,
        vector: list[float],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search across all memory types and return combined results."""
        results: list[dict[str, Any]] = []
        for mem_type in ("episodic", "semantic", "procedural", "working"):
            mem_results = self.search(
                vector=vector,
                memory_type=mem_type,
                limit=limit,
            )
            for r in mem_results:
                r["memory_type"] = mem_type
                results.append(r)
        # Sort by score descending
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return results[:limit]
