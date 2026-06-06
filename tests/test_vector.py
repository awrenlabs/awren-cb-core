"""VectorRepository tests using a mocked Qdrant client.

Since Qdrant isn't available in CI, we mock the client and verify
the CRUD and search logic.
"""

from unittest.mock import ANY, MagicMock, patch
from uuid import uuid4

import pytest

from awren_core.vector import QdrantConnection, VectorRepository, get_vector_db


@pytest.fixture(autouse=True)
def reset_qdrant():
    """Reset the QdrantConnection singleton between tests so each test gets a fresh client."""
    from awren_core import vector as vec_module

    # Reset the singleton so each test creates a fresh QdrantConnection
    vec_module._connection = None
    yield
    vec_module._connection = None


@pytest.fixture
def mock_qdrant():
    """Mock the QdrantClient so no real connection is needed."""
    with patch("qdrant_client.QdrantClient") as mock_class:
        mock_client = MagicMock()
        mock_class.return_value = mock_client
        # Mock get_collection to raise by default (simulating missing collection on fresh DB)
        mock_client.get_collection.side_effect = RuntimeError("Collection not found")
        yield mock_client


@pytest.fixture
def repo(mock_qdrant) -> VectorRepository:
    """VectorRepository with mocked Qdrant client."""
    return VectorRepository(vector_size=384)


class TestVectorRepository:
    """Tests for VectorRepository CRUD operations."""

    def test_upsert(self, repo: VectorRepository, mock_qdrant: MagicMock):
        memory_id = str(uuid4())
        vector = [0.1] * 384
        payload = {"content": "Test memory", "tags": ["test"]}

        repo.upsert(memory_id, vector, payload, memory_type="semantic")

        mock_qdrant.upsert.assert_called_once()
        args = mock_qdrant.upsert.call_args[1]
        assert args["collection_name"] == "memory_semantic"
        assert len(args["points"]) == 1
        assert args["points"][0].payload["memory_id"] == memory_id

    def test_upsert_different_types(self, repo: VectorRepository, mock_qdrant: MagicMock):
        for mem_type in ("episodic", "semantic", "procedural", "working"):
            memory_id = str(uuid4())
            repo.upsert(memory_id, [0.5] * 384, {"content": "test"}, memory_type=mem_type)

        assert mock_qdrant.upsert.call_count == 4

    def test_get(self, repo: VectorRepository, mock_qdrant: MagicMock):
        memory_id = str(uuid4())
        mock_qdrant.scroll.return_value = (
            [MagicMock(payload={"memory_id": memory_id, "content": "Found"})],
            None,
        )

        result = repo.get(memory_id, "semantic")
        assert result is not None
        assert result["content"] == "Found"

    def test_get_not_found(self, repo: VectorRepository, mock_qdrant: MagicMock):
        mock_qdrant.scroll.return_value = ([], None)
        result = repo.get(str(uuid4()), "semantic")
        assert result is None

    def test_delete(self, repo: VectorRepository, mock_qdrant: MagicMock):
        memory_id = str(uuid4())
        repo.delete(memory_id, "semantic")

        mock_qdrant.delete.assert_called_once()
        args = mock_qdrant.delete.call_args[1]
        assert args["collection_name"] == "memory_semantic"

    def test_ensure_collection_creates_if_missing(self, repo: VectorRepository, mock_qdrant: MagicMock):
        mock_qdrant.get_collection.side_effect = RuntimeError("Not found")

        repo.ensure_collection("episodic")

        mock_qdrant.create_collection.assert_called_once()
        args = mock_qdrant.create_collection.call_args[1]
        assert args["collection_name"] == "memory_episodic"

    def test_ensure_all_collections(self, repo: VectorRepository, mock_qdrant: MagicMock):
        mock_qdrant.get_collection.side_effect = RuntimeError("Not found")

        repo.ensure_all_collections()
        assert mock_qdrant.create_collection.call_count == 4


class TestVectorSearch:
    """Tests for VectorRepository semantic search."""

    def test_search(self, repo: VectorRepository, mock_qdrant: MagicMock):
        mock_qdrant.search.return_value = [
            MagicMock(id=1, score=0.95, payload={"memory_id": "abc", "content": "Result 1"}),
            MagicMock(id=2, score=0.85, payload={"memory_id": "def", "content": "Result 2"}),
        ]

        results = repo.search([0.2] * 384, memory_type="semantic", limit=5)

        assert len(results) == 2
        assert results[0]["score"] == 0.95
        assert results[1]["payload"]["content"] == "Result 2"
        mock_qdrant.search.assert_called_once()

    def test_search_with_filter(self, repo: VectorRepository, mock_qdrant: MagicMock):
        mock_qdrant.search.return_value = [
            MagicMock(id=1, score=0.9, payload={"memory_id": "abc", "content": "Filtered", "type": "risk"}),
        ]

        results = repo.search(
            [0.1] * 384,
            query_filter={"type": "risk"},
            memory_type="semantic",
        )

        assert len(results) == 1
        assert results[0]["payload"]["type"] == "risk"

    def test_search_empty_results(self, repo: VectorRepository, mock_qdrant: MagicMock):
        mock_qdrant.search.return_value = []
        results = repo.search([0.5] * 384, memory_type="semantic")
        assert results == []

    def test_search_across_types(self, repo: VectorRepository, mock_qdrant: MagicMock):
        mock_qdrant.search.return_value = [
            MagicMock(id=1, score=0.95, payload={"memory_id": "abc", "content": "Best match"}),
        ]

        results = repo.search_across_types([0.3] * 384, limit=5)

        # Called once per memory type (4 calls), results sorted by score
        assert mock_qdrant.search.call_count == 4
        assert len(results) > 0
        assert "memory_type" in results[0]


class TestVectorConnection:
    """Tests for QdrantConnection singleton."""

    def test_get_vector_db_returns_singleton(self):
        v1 = get_vector_db()
        v2 = get_vector_db()
        assert v1 is v2

    def test_point_id_deterministic(self):
        """Point IDs should be consistent across calls."""
        repo = VectorRepository()
        memory_id = str(uuid4())
        id1 = repo._point_id(memory_id)
        id2 = repo._point_id(memory_id)
        assert id1 == id2
        assert 0 <= id1 < 2**63

    def test_point_id_uuid_based(self):
        """UUID-based memory IDs should produce valid point IDs."""
        repo = VectorRepository()
        memory_id = "550e8400-e29b-41d4-a716-446655440000"
        point_id = repo._point_id(memory_id)
        assert isinstance(point_id, int)
        assert 0 <= point_id < 2**63

    def test_point_id_non_uuid_fallback(self):
        """Non-UUID strings should use md5 fallback."""
        repo = VectorRepository()
        point_id = repo._point_id("custom-key-123")
        assert isinstance(point_id, int)
        assert 0 <= point_id < 2**63
