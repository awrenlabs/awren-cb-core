"""Neo4j GraphRepository tests using a mocked neo4j driver.

Since Neo4j isn't available in CI, we mock the driver and verify
Cypher query construction and data conversion logic.
"""

from typing import Any
from unittest.mock import ANY, MagicMock, PropertyMock, patch
from uuid import UUID, uuid4

import pytest

from awren_core.graph import GraphRepository, get_graph
from awren_core.models import BaseEntity, BaseRelationship


@pytest.fixture
def mock_driver():
    """Mock the neo4j driver so no real connection is needed."""
    with patch("awren_core.graph.GraphConnection.driver", new_callable=PropertyMock) as mock:
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_session.run.return_value = mock_result
        mock_driver_instance = MagicMock()
        mock_driver_instance.session.return_value.__enter__.return_value = mock_session
        mock.return_value = mock_driver_instance
        yield {
            "driver": mock,
            "session": mock_session,
            "result": mock_result,
        }


@pytest.fixture
def repo(mock_driver) -> GraphRepository:
    """GraphRepository with mocked driver."""
    return GraphRepository()


@pytest.fixture
def sample_entity() -> BaseEntity:
    return BaseEntity(
        type="core:Organization",
        label="Acme Corp",
        description="A test org",
        properties={"industry": "construction"},
    )


@pytest.fixture
def sample_relationship(sample_entity) -> BaseRelationship:
    return BaseRelationship(
        type="core:employs",
        source_id=sample_entity.id,
        target_id=uuid4(),
        properties={"since": "2024"},
    )


def _make_node_props(entity: BaseEntity) -> dict[str, Any]:
    """Return a dict mirroring Neo4j node properties (what dict(node) returns)."""
    return {
        "id": str(entity.id),
        "type": entity.type,
        "label": entity.label,
        "description": entity.description or "",
        "properties": entity.properties,
        "created_at": 1719000000000,
        "updated_at": 1719000000000,
    }


def _make_rel_props(rel: BaseRelationship) -> dict[str, Any]:
    """Return a dict mirroring Neo4j relationship properties (what dict(rel) returns)."""
    return {
        "id": str(rel.id),
        "type": rel.type,
        "source_id": str(rel.source_id),
        "target_id": str(rel.target_id),
        "properties": rel.properties,
    }


class TestGraphRepository:
    """Tests for GraphRepository entity operations."""

    def test_create_entity(self, repo: GraphRepository, mock_driver, sample_entity: BaseEntity):
        result = repo.create_entity(sample_entity)
        assert result.id == sample_entity.id
        mock_driver["session"].run.assert_called_once()

    def test_get_entity_found(self, repo: GraphRepository, mock_driver, sample_entity: BaseEntity):
        node_props = _make_node_props(sample_entity)
        mock_driver["result"].single.return_value = {"e": node_props}

        result = repo.get_entity(sample_entity.id)
        assert result is not None
        assert result.id == sample_entity.id
        assert result.label == "Acme Corp"
        assert result.type == "core:Organization"

    def test_get_entity_not_found(self, repo: GraphRepository, mock_driver):
        mock_driver["result"].single.return_value = None
        result = repo.get_entity(uuid4())
        assert result is None

    def test_update_entity(self, repo: GraphRepository, mock_driver, sample_entity: BaseEntity):
        sample_entity.label = "Updated Corp"
        result = repo.update_entity(sample_entity)
        assert result.label == "Updated Corp"
        mock_driver["session"].run.assert_called_once()

    def test_delete_entity(self, repo: GraphRepository, mock_driver):
        entity_id = uuid4()
        repo.delete_entity(entity_id)
        mock_driver["session"].run.assert_called_once()

    def test_search_entities(self, repo: GraphRepository, mock_driver, sample_entity: BaseEntity):
        node_props = _make_node_props(sample_entity)
        mock_driver["result"].__iter__.return_value = [{"e": node_props}]

        results = repo.search_entities(entity_type="core:Organization")
        assert len(results) == 1
        assert results[0].label == "Acme Corp"

    def test_search_entities_empty(self, repo: GraphRepository, mock_driver):
        mock_driver["result"].__iter__.return_value = []
        results = repo.search_entities(entity_type="core:Nonexistent")
        assert results == []


class TestGraphRelationships:
    """Tests for GraphRepository relationship operations."""

    def test_create_relationship(self, repo: GraphRepository, mock_driver, sample_relationship: BaseRelationship):
        result = repo.create_relationship(sample_relationship)
        assert result.id == sample_relationship.id
        mock_driver["session"].run.assert_called_once()

    def test_get_relationship_found(self, repo: GraphRepository, mock_driver, sample_relationship: BaseRelationship):
        rel_props = _make_rel_props(sample_relationship)
        source_props = _make_node_props(
            BaseEntity(type="source", label="source", id=sample_relationship.source_id)
        )
        target_props = _make_node_props(
            BaseEntity(type="target", label="target", id=sample_relationship.target_id)
        )
        mock_driver["result"].single.return_value = {
            "r": rel_props,
            "source": source_props,
            "target": target_props,
        }

        result = repo.get_relationship(sample_relationship.id)
        assert result is not None
        assert result.id == sample_relationship.id
        assert result.type == "core:employs"
        assert result.source_id == sample_relationship.source_id
        assert result.target_id == sample_relationship.target_id

    def test_get_relationship_not_found(self, repo: GraphRepository, mock_driver):
        mock_driver["result"].single.return_value = None
        result = repo.get_relationship(uuid4())
        assert result is None

    def test_delete_relationship(self, repo: GraphRepository, mock_driver):
        rel_id = uuid4()
        repo.delete_relationship(rel_id)
        mock_driver["session"].run.assert_called_once_with(ANY, {"id": str(rel_id)})


class TestGraphTraversal:
    """Tests for GraphRepository traversal operations."""

    def test_traverse(self, repo: GraphRepository, mock_driver, sample_entity: BaseEntity):
        node_props = _make_node_props(sample_entity)
        mock_driver["result"].__iter__.return_value = [{"related": node_props}]

        results = repo.traverse(sample_entity.id, depth=2)
        assert len(results) == 1
        assert results[0].label == "Acme Corp"

    def test_find_path(self, repo: GraphRepository, mock_driver, sample_relationship: BaseRelationship):
        rel_props = _make_rel_props(sample_relationship)
        source_props = _make_node_props(
            BaseEntity(type="source", label="source", id=sample_relationship.source_id)
        )
        target_props = _make_node_props(
            BaseEntity(type="target", label="target", id=sample_relationship.target_id)
        )
        mock_driver["result"].__iter__.return_value = [{
            "r": rel_props,
            "path_source": source_props,
            "path_target": target_props,
        }]

        results = repo.find_path(
            source_id=sample_relationship.source_id,
            target_id=sample_relationship.target_id,
        )
        assert len(results) == 1
        assert results[0].id == sample_relationship.id
        assert results[0].source_id == sample_relationship.source_id
        assert results[0].target_id == sample_relationship.target_id

    def test_find_path_no_path(self, repo: GraphRepository, mock_driver):
        mock_driver["result"].__iter__.return_value = []
        results = repo.find_path(source_id=uuid4(), target_id=uuid4())
        assert results == []

    def test_get_neighborhood_empty(self, repo: GraphRepository, mock_driver, sample_entity: BaseEntity):
        node_props = _make_node_props(sample_entity)
        mock_driver["result"].single.return_value = {
            "center": node_props,
            "neighbors": [],
        }

        hood = repo.get_neighborhood(sample_entity.id)
        assert hood["center"] is not None
        assert hood["center"].id == sample_entity.id
        assert hood["neighbors"] == []

    def test_get_neighborhood_with_neighbors(
        self,
        repo: GraphRepository,
        mock_driver,
        sample_entity: BaseEntity,
        sample_relationship: BaseRelationship,
    ):
        center_props = _make_node_props(sample_entity)
        neighbor_entity = BaseEntity(type="core:Person", label="Bob")
        neighbor_props = _make_node_props(neighbor_entity)
        rel_props = _make_rel_props(sample_relationship)

        mock_driver["result"].single.return_value = {
            "center": center_props,
            "neighbors": [
                {
                    "rel": rel_props,
                    "node": neighbor_props,
                    "start": center_props,
                    "end": neighbor_props,
                }
            ],
        }

        hood = repo.get_neighborhood(sample_entity.id)
        assert hood["center"] is not None
        assert hood["center"].id == sample_entity.id
        assert len(hood["neighbors"]) == 1
        assert hood["neighbors"][0]["entity"].id == neighbor_entity.id
        assert hood["neighbors"][0]["relationship"].id == sample_relationship.id
        assert hood["neighbors"][0]["relationship"].source_id == sample_relationship.source_id

    def test_get_neighborhood_none_center(self, repo: GraphRepository, mock_driver):
        mock_driver["result"].single.return_value = None
        hood = repo.get_neighborhood(uuid4())
        assert hood["center"] is None
        assert hood["neighbors"] == []


class TestGraphConnection:
    """Tests for the GraphConnection singleton."""

    def test_get_graph_returns_singleton(self):
        g1 = get_graph()
        g2 = get_graph()
        assert g1 is g2

    def test_get_graph_driver_lazy_init(self):
        with patch("awren_core.graph.get_settings") as mock_settings:
            mock_settings.return_value.neo4j_uri = "bolt://localhost:7687"
            mock_settings.return_value.neo4j_user = "neo4j"
            mock_settings.return_value.neo4j_password = "test"

            with patch("neo4j.GraphDatabase") as mock_db:
                g = get_graph()
                driver = g.driver  # Trigger lazy init
                mock_db.driver.assert_called_once_with(
                    "bolt://localhost:7687",
                    auth=("neo4j", "test"),
                )
