"""Tests for the embedding service.

Covers:
- OpenAIEmbeddingClient with mocked API
- FallbackEmbeddingClient deterministic behavior
- Factory function (create_embedding_client) with various settings
- Error handling and graceful degradation
"""

from unittest.mock import MagicMock, patch

import pytest

from awren_core.embeddings import (
    EMBEDDING_DIMENSIONS,
    OpenAIEmbeddingClient,
    FallbackEmbeddingClient,
    create_embedding_client,
    _deterministic_vector,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_embedding_response(vectors: list[list[float]]) -> MagicMock:
    """Build a mock OpenAI embedding response."""
    data = []
    for idx, vec in enumerate(vectors):
        d = MagicMock()
        d.index = idx
        d.embedding = vec
        data.append(d)
    resp = MagicMock()
    resp.data = data
    return resp


# ---------------------------------------------------------------------------
# FallbackEmbeddingClient
# ---------------------------------------------------------------------------


class TestFallbackEmbeddingClient:
    def test_deterministic_output(self):
        """Same input should produce the same vector."""
        client = FallbackEmbeddingClient(dimensions=384)
        v1 = client.embed("hello world")
        v2 = client.embed("hello world")
        assert v1 == v2

    def test_different_inputs_different_vectors(self):
        """Different inputs should produce different vectors."""
        client = FallbackEmbeddingClient(dimensions=384)
        v1 = client.embed("hello")
        v2 = client.embed("world")
        assert v1 != v2

    def test_correct_dimensions(self):
        """Vector should have the expected number of dimensions."""
        client = FallbackEmbeddingClient(dimensions=768)
        vec = client.embed("test")
        assert len(vec) == 768

    def test_batch_embed(self):
        """Batch embedding should return one vector per input."""
        client = FallbackEmbeddingClient(dimensions=128)
        texts = ["first", "second", "third"]
        vectors = client.embed_batch(texts)
        assert len(vectors) == 3
        assert all(len(v) == 128 for v in vectors)

    def test_deterministic_vector_function(self):
        """_deterministic_vector should produce consistent results."""
        v1 = _deterministic_vector("test", 768)
        v2 = _deterministic_vector("test", 768)
        assert v1 == v2
        assert len(v1) == 768
        assert all(isinstance(x, float) for x in v1)

    def test_value_range(self):
        """Vector values should be in a reasonable range [-1, 1]."""
        vec = _deterministic_vector("comprehensive test input", 1536)
        assert all(-1.0 <= x <= 1.0 for x in vec)


# ---------------------------------------------------------------------------
# OpenAIEmbeddingClient
# ---------------------------------------------------------------------------


class TestOpenAIEmbeddingClient:
    def test_init_with_default_model(self):
        """Default model and dimensions should resolve from EMBEDDING_DIMENSIONS."""
        with patch("openai.OpenAI") as mock_openai:
            client = OpenAIEmbeddingClient(api_key="sk-test")
            assert client.model == "text-embedding-3-small"
            assert client.dimensions == EMBEDDING_DIMENSIONS["text-embedding-3-small"]
            mock_openai.assert_called_once_with(api_key="sk-test")

    def test_init_with_custom_dimensions(self):
        """Explicit dimensions should override the model default."""
        with patch("openai.OpenAI"):
            client = OpenAIEmbeddingClient(
                api_key="sk-test",
                model="text-embedding-3-small",
                dimensions=512,
            )
            assert client.dimensions == 512

    def test_embed_success(self):
        """Successful OpenAI embedding API call."""
        expected_vector = [0.1] * 1536
        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_client.embeddings.create.return_value = _make_embedding_response(
                [expected_vector]
            )

            client = OpenAIEmbeddingClient(api_key="sk-test")
            result = client.embed("test text")

            assert result == expected_vector
            mock_client.embeddings.create.assert_called_once_with(
                model="text-embedding-3-small",
                input="test text",
                dimensions=1536,
            )

    def test_embed_api_failure_falls_back(self):
        """When OpenAI API fails, should return fallback deterministic vector."""
        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_client.embeddings.create.side_effect = Exception("API error")

            client = OpenAIEmbeddingClient(api_key="sk-test")
            result = client.embed("test text")

            # Should return a deterministic fallback vector of correct size
            assert len(result) == 1536
            assert isinstance(result[0], float)

    def test_embed_batch_success(self):
        """Successful batch embedding."""
        vectors = [[0.1] * 1536, [0.2] * 1536, [0.3] * 1536]
        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_client.embeddings.create.return_value = _make_embedding_response(vectors)

            client = OpenAIEmbeddingClient(api_key="sk-test")
            results = client.embed_batch(["a", "b", "c"])

            assert len(results) == 3
            assert results == vectors

    def test_embed_batch_maintains_order(self):
        """Batch results should be sorted by index to preserve input order."""
        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            # Return out of order
            resp = MagicMock()
            d2 = MagicMock()
            d2.index = 1
            d2.embedding = [0.2] * 1536
            d0 = MagicMock()
            d0.index = 0
            d0.embedding = [0.1] * 1536
            d1 = MagicMock()
            d1.index = 2
            d1.embedding = [0.3] * 1536
            resp.data = [d2, d0, d1]
            mock_client.embeddings.create.return_value = resp

            client = OpenAIEmbeddingClient(api_key="sk-test")
            results = client.embed_batch(["a", "b", "c"])

            assert results[0] == [0.1] * 1536
            assert results[1] == [0.2] * 1536
            assert results[2] == [0.3] * 1536

    def test_embed_batch_api_failure_falls_back(self):
        """When batch API fails, should return deterministic fallback vectors."""
        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_client.embeddings.create.side_effect = Exception("API error")

            client = OpenAIEmbeddingClient(api_key="sk-test")
            results = client.embed_batch(["a", "b"])

            assert len(results) == 2
            assert all(len(v) == 1536 for v in results)

    def test_embed_with_custom_base_url(self):
        """Custom base URL should be passed to OpenAI client."""
        with patch("openai.OpenAI") as mock_openai:
            OpenAIEmbeddingClient(
                api_key="sk-test",
                base_url="https://openrouter.ai/api/v1",
            )
            mock_openai.assert_called_once_with(
                api_key="sk-test",
                base_url="https://openrouter.ai/api/v1",
            )

    def test_embed_without_dimensions_for_ada(self):
        """For ada-002, should NOT pass dimensions parameter (not supported)."""
        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_client.embeddings.create.return_value = _make_embedding_response(
                [[0.1] * 1536]
            )

            client = OpenAIEmbeddingClient(
                api_key="sk-test",
                model="text-embedding-ada-002",
            )
            client.embed("test")

            call_kwargs = mock_client.embeddings.create.call_args[1]
            assert "dimensions" not in call_kwargs


# ---------------------------------------------------------------------------
# Factory: create_embedding_client
# ---------------------------------------------------------------------------


class TestCreateEmbeddingClient:
    def test_openai_when_key_set(self):
        """Should create OpenAIEmbeddingClient when API key is configured."""
        # Patch at the module that actually calls get_settings
        with patch("awren_core.embeddings.get_settings") as mock_settings:
            settings = MagicMock()
            settings.openai_api_key = "sk-test"
            settings.openai_embedding_model = "text-embedding-3-small"
            settings.openai_embedding_dimensions = 1536
            settings.openai_base_url = ""
            mock_settings.return_value = settings

            client = create_embedding_client()
            assert isinstance(client, OpenAIEmbeddingClient)
            assert client.model == "text-embedding-3-small"
            assert client.dimensions == 1536

    def test_fallback_when_no_key(self):
        """Should create FallbackEmbeddingClient when no API key is set."""
        with patch("awren_core.embeddings.get_settings") as mock_settings:
            settings = MagicMock()
            settings.openai_api_key = ""
            settings.openai_embedding_model = "text-embedding-3-small"
            settings.openai_embedding_dimensions = 1536
            settings.openai_base_url = ""
            mock_settings.return_value = settings

            client = create_embedding_client()
            assert isinstance(client, FallbackEmbeddingClient)
            assert client.dimensions == 1536

    def test_custom_model_and_dimensions(self):
        """Factory should pass custom model and dimensions from settings."""
        with patch("awren_core.embeddings.get_settings") as mock_settings:
            settings = MagicMock()
            settings.openai_api_key = "sk-test"
            settings.openai_embedding_model = "text-embedding-3-large"
            settings.openai_embedding_dimensions = 2048
            settings.openai_base_url = ""
            mock_settings.return_value = settings

            client = create_embedding_client()
            assert isinstance(client, OpenAIEmbeddingClient)
            assert client.model == "text-embedding-3-large"
            assert client.dimensions == 2048
