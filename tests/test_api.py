"""FastAPI integration tests using TestClient with SQLite."""

from collections.abc import Generator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from awren_core.database import Base
from awren_core.services import EventService
from apps.api.main import app, get_event_service


@pytest.fixture
def client(tmp_path) -> Generator[TestClient, None, None]:
    """Create a TestClient with an isolated file-based SQLite database.
    Each test gets its own database file, guaranteeing complete isolation.
    """
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)

    def _get_test_service() -> Generator[EventService, None, None]:
        session = session_factory()
        try:
            yield EventService(session)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_event_service] = _get_test_service
    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_check(self, client: TestClient):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"


# ---------------------------------------------------------------------------
# Entity CRUD
# ---------------------------------------------------------------------------


class TestCreateEntity:
    def test_create_entity(self, client: TestClient):
        response = client.post("/api/v1/entities", json={
            "type": "core:Organization",
            "label": "Acme Corp",
            "description": "A test organization",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["type"] == "core:Organization"
        assert data["label"] == "Acme Corp"
        assert "id" in data
        UUID(data["id"])

    def test_create_entity_with_properties(self, client: TestClient):
        response = client.post("/api/v1/entities", json={
            "type": "core:Person",
            "label": "Alice",
            "properties": {"email": "alice@example.com", "age": 30},
            "identifiers": [{"system": "internal", "value": "EMP-001"}],
        })
        assert response.status_code == 201
        data = response.json()
        assert data["properties"]["email"] == "alice@example.com"
        assert data["identifiers"][0]["value"] == "EMP-001"

    def test_create_entity_validation_error(self, client: TestClient):
        response = client.post("/api/v1/entities", json={
            "label": "Missing type",
        })
        assert response.status_code == 422


class TestListEntities:
    def test_list_empty(self, client: TestClient):
        response = client.get("/api/v1/entities")
        assert response.status_code == 200
        data = response.json()
        assert data["entities"] == []
        assert data["total"] == 0

    def test_list_with_entities(self, client: TestClient):
        client.post("/api/v1/entities", json={
            "type": "core:Organization", "label": "Org A",
        })
        client.post("/api/v1/entities", json={
            "type": "core:Organization", "label": "Org B",
        })

        response = client.get("/api/v1/entities")
        assert response.status_code == 200
        data = response.json()
        assert len(data["entities"]) == 2
        assert data["total"] == 2

    def test_list_filter_by_type(self, client: TestClient):
        client.post("/api/v1/entities", json={
            "type": "core:Organization", "label": "Org",
        })
        client.post("/api/v1/entities", json={
            "type": "core:Person", "label": "Person",
        })

        response = client.get("/api/v1/entities?type=core:Organization")
        assert response.status_code == 200
        data = response.json()
        assert len(data["entities"]) == 1
        assert data["total"] == 1
        assert data["entities"][0]["type"] == "core:Organization"

    def test_list_with_limit(self, client: TestClient):
        for i in range(5):
            client.post("/api/v1/entities", json={
                "type": "core:Document", "label": f"Doc {i}",
            })

        response = client.get("/api/v1/entities?limit=2")
        data = response.json()
        assert len(data["entities"]) == 2
        assert data["total"] == 5


class TestGetEntity:
    def test_get_entity(self, client: TestClient):
        create_resp = client.post("/api/v1/entities", json={
            "type": "core:Project", "label": "Project X",
        })
        entity_id = create_resp.json()["id"]

        response = client.get(f"/api/v1/entities/{entity_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == entity_id
        assert data["label"] == "Project X"

    def test_get_nonexistent_entity(self, client: TestClient):
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = client.get(f"/api/v1/entities/{fake_id}")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_entity_invalid_uuid(self, client: TestClient):
        response = client.get("/api/v1/entities/not-a-uuid")
        assert response.status_code == 422


class TestUpdateEntity:
    def test_update_entity_label(self, client: TestClient):
        create_resp = client.post("/api/v1/entities", json={
            "type": "core:Project", "label": "Old Name",
        })
        entity_id = create_resp.json()["id"]

        response = client.patch(f"/api/v1/entities/{entity_id}", json={
            "label": "New Name",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["label"] == "New Name"

    def test_update_nonexistent(self, client: TestClient):
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = client.patch(f"/api/v1/entities/{fake_id}", json={
            "label": "New Name",
        })
        assert response.status_code == 404

    def test_update_partial(self, client: TestClient):
        create_resp = client.post("/api/v1/entities", json={
            "type": "core:Person", "label": "Alice",
            "description": "Original description",
        })
        entity_id = create_resp.json()["id"]

        response = client.patch(f"/api/v1/entities/{entity_id}", json={
            "description": "Updated description",
        })
        data = response.json()
        assert data["label"] == "Alice"
        assert data["description"] == "Updated description"


class TestDeleteEntity:
    def test_delete_entity(self, client: TestClient):
        create_resp = client.post("/api/v1/entities", json={
            "type": "core:Document", "label": "To delete",
        })
        entity_id = create_resp.json()["id"]

        response = client.delete(f"/api/v1/entities/{entity_id}")
        assert response.status_code == 204

        get_resp = client.get(f"/api/v1/entities/{entity_id}")
        assert get_resp.status_code == 404

    def test_delete_nonexistent(self, client: TestClient):
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = client.delete(f"/api/v1/entities/{fake_id}")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Event Sourcing
# ---------------------------------------------------------------------------


class TestEventRecording:
    def test_create_records_event(self, client: TestClient):
        create_resp = client.post("/api/v1/entities", json={
            "type": "core:Organization", "label": "Eventful Org",
        })
        entity_id = create_resp.json()["id"]

        events_resp = client.get(f"/api/v1/entities/{entity_id}/events")
        assert events_resp.status_code == 200
        events = events_resp.json()
        assert events["total"] == 1
        assert events["events"][0]["type"] == "mem:EntityCreated"

    def test_update_records_event(self, client: TestClient):
        create_resp = client.post("/api/v1/entities", json={
            "type": "core:Project", "label": "Project Alpha",
        })
        entity_id = create_resp.json()["id"]

        client.patch(f"/api/v1/entities/{entity_id}", json={"label": "v2"})

        events_resp = client.get(f"/api/v1/entities/{entity_id}/events")
        events = events_resp.json()
        assert events["total"] == 2
        assert events["events"][0]["type"] == "mem:EntityCreated"
        assert events["events"][1]["type"] == "mem:EntityUpdated"

    def test_delete_records_event(self, client: TestClient):
        create_resp = client.post("/api/v1/entities", json={
            "type": "core:Document", "label": "Delete me",
        })
        entity_id = create_resp.json()["id"]

        client.delete(f"/api/v1/entities/{entity_id}")

        events_resp = client.get(f"/api/v1/entities/{entity_id}/events")
        events = events_resp.json()
        assert events["total"] == 2
        assert events["events"][0]["type"] == "mem:EntityCreated"
        assert events["events"][1]["type"] == "mem:EntityArchived"

    def test_full_lifecycle_events(self, client: TestClient):
        create_resp = client.post("/api/v1/entities", json={
            "type": "core:Project", "label": "Lifecycle",
        })
        entity_id = create_resp.json()["id"]

        client.patch(f"/api/v1/entities/{entity_id}", json={"label": "v2"})
        client.patch(f"/api/v1/entities/{entity_id}", json={"label": "v3"})
        client.delete(f"/api/v1/entities/{entity_id}")

        replay_resp = client.get(f"/api/v1/entities/{entity_id}/replay")
        events = replay_resp.json()["events"]
        event_types = [e["type"] for e in events]
        assert event_types == [
            "mem:EntityCreated",
            "mem:EntityUpdated",
            "mem:EntityUpdated",
            "mem:EntityArchived",
        ]


class TestListEvents:
    def test_list_recent_events(self, client: TestClient):
        client.post("/api/v1/entities", json={
            "type": "core:Organization", "label": "Org 1",
        })
        client.post("/api/v1/entities", json={
            "type": "core:Organization", "label": "Org 2",
        })
        client.post("/api/v1/entities", json={
            "type": "core:Organization", "label": "Org 3",
        })

        response = client.get("/api/v1/events")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 3

    def test_list_events_with_limit(self, client: TestClient):
        for i in range(5):
            client.post("/api/v1/entities", json={
                "type": "core:Document", "label": f"Doc {i}",
            })

        response = client.get("/api/v1/events?limit=2")
        data = response.json()
        assert len(data["events"]) == 2

    def test_events_across_entities(self, client: TestClient):
        org_id = client.post("/api/v1/entities", json={
            "type": "core:Organization", "label": "Org",
        }).json()["id"]
        person_id = client.post("/api/v1/entities", json={
            "type": "core:Person", "label": "Person",
        }).json()["id"]

        org_events = client.get(f"/api/v1/entities/{org_id}/events").json()
        person_events = client.get(f"/api/v1/entities/{person_id}/events").json()
        assert org_events["total"] == 1
        assert person_events["total"] == 1


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


class TestQuery:
    def test_query_returns_entities(self, client: TestClient):
        client.post("/api/v1/entities", json={
            "type": "core:Organization", "label": "Queryable Org",
        })

        response = client.post("/api/v1/query", json={
            "query": "",
            "limit": 100,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert "query_time_ms" in data

    def test_query_with_params(self, client: TestClient):
        client.post("/api/v1/entities", json={
            "type": "core:Organization", "label": "Org A",
        })
        client.post("/api/v1/entities", json={
            "type": "core:Person", "label": "Person B",
        })

        response = client.post("/api/v1/query", json={
            "query": "",
            "params": {"type": "core:Organization"},
            "limit": 100,
        })
        data = response.json()
        assert data["total"] == 1
        assert data["results"][0]["type"] == "core:Organization"


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------


class TestCORS:
    def test_cors_headers_present(self, client: TestClient):
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers
