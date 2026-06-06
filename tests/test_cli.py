"""CLI tests using Typer CliRunner with mocked HTTP responses."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from typer.testing import CliRunner

from apps.cli.main import app

runner = CliRunner()

SAMPLE_ENTITY: dict[str, Any] = {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "type": "core:Organization",
    "label": "Acme Corp",
    "description": "A test org",
    "properties": {},
    "identifiers": [],
    "metadata": {"created": "2026-01-01T00:00:00"},
}

SAMPLE_ENTITIES = {
    "entities": [SAMPLE_ENTITY],
    "total": 1,
}

SAMPLE_EVENT: dict[str, Any] = {
    "id": "660e8400-e29b-41d4-a716-446655440000",
    "type": "mem:EntityCreated",
    "timestamp": "2026-01-01T00:00:00",
    "source": "api",
    "subject_id": SAMPLE_ENTITY["id"],
    "object_ids": [],
    "payload": {"entity_type": "core:Organization", "label": "Acme Corp"},
    "metadata": {},
}

SAMPLE_EVENTS = {
    "events": [SAMPLE_EVENT],
    "total": 1,
}


@pytest.fixture
def mock_client():
    """Mock AwrenClient for all tests."""
    with patch("apps.cli.main.AwrenClient") as mock:
        client_instance = MagicMock()
        client_instance.health_check = AsyncMock(
            return_value={"status": "ok", "version": "0.1.0"}
        )
        client_instance.create_entity = AsyncMock(return_value=SAMPLE_ENTITY)
        client_instance.get_entity = AsyncMock(return_value=SAMPLE_ENTITY)
        client_instance.list_entities = AsyncMock(return_value=SAMPLE_ENTITIES)
        client_instance.delete_entity = AsyncMock(return_value=None)
        client_instance.query = AsyncMock(
            return_value={
                "results": [SAMPLE_ENTITY],
                "total": 1,
                "query_time_ms": 12.34,
            }
        )
        mock.return_value = client_instance
        yield mock


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_ok(self, mock_client):
        result = runner.invoke(app, ["health"])
        assert result.exit_code == 0
        assert "ok" in result.stdout
        assert "0.1.0" in result.stdout

    def test_health_error(self):
        with patch("apps.cli.main.AwrenClient") as mock:
            client_instance = MagicMock()
            client_instance.health_check = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock.return_value = client_instance
            result = runner.invoke(app, ["health"])
            assert result.exit_code == 1
            assert "Error" in result.stdout


# ---------------------------------------------------------------------------
# Entity commands
# ---------------------------------------------------------------------------


class TestEntityCreate:
    def test_create_basic(self, mock_client):
        result = runner.invoke(app, [
            "entity", "create", "core:Organization", "Acme Corp",
        ])
        assert result.exit_code == 0
        assert "Acme Corp" in result.stdout
        assert "created" in result.stdout.lower()

    def test_create_with_description(self, mock_client):
        result = runner.invoke(app, [
            "entity", "create", "core:Organization", "Acme",
            "--description", "A test org",
        ])
        assert result.exit_code == 0

    def test_create_error(self):
        with patch("apps.cli.main.AwrenClient") as mock:
            client_instance = MagicMock()
            client_instance.create_entity = AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "Bad Request", request=MagicMock(), response=MagicMock()
                )
            )
            mock.return_value = client_instance
            result = runner.invoke(app, [
                "entity", "create", "core:Org", "Fail",
            ])
            assert result.exit_code == 1
            assert "Error" in result.stdout


class TestEntityGet:
    def test_get_entity(self, mock_client):
        result = runner.invoke(app, [
            "entity", "get", SAMPLE_ENTITY["id"],
        ])
        assert result.exit_code == 0
        assert "Acme Corp" in result.stdout

    def test_get_nonexistent(self):
        with patch("apps.cli.main.AwrenClient") as mock:
            client_instance = MagicMock()
            client_instance.get_entity = AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "Not Found", request=MagicMock(), response=MagicMock(status_code=404)
                )
            )
            mock.return_value = client_instance
            result = runner.invoke(app, [
                "entity", "get", "00000000-0000-0000-0000-000000000000",
            ])
            assert result.exit_code == 1


class TestEntityList:
    def test_list_all(self, mock_client):
        result = runner.invoke(app, ["entity", "list"])
        assert result.exit_code == 0
        assert "Acme Corp" in result.stdout

    def test_list_filter_by_type(self, mock_client):
        result = runner.invoke(app, ["entity", "list", "--type", "core:Organization"])
        assert result.exit_code == 0

    def test_list_empty(self):
        with patch("apps.cli.main.AwrenClient") as mock:
            client_instance = MagicMock()
            client_instance.list_entities = AsyncMock(
                return_value={"entities": [], "total": 0}
            )
            mock.return_value = client_instance
            result = runner.invoke(app, ["entity", "list"])
            assert result.exit_code == 0
            assert "No entities" in result.stdout

    def test_list_with_limit(self, mock_client):
        result = runner.invoke(app, ["entity", "list", "--limit", "50"])
        assert result.exit_code == 0


class TestEntityDelete:
    def test_delete_with_confirmation(self, mock_client):
        result = runner.invoke(app, [
            "entity", "delete", SAMPLE_ENTITY["id"], "--yes",
        ])
        assert result.exit_code == 0
        assert "deleted" in result.stdout.lower()

    def test_delete_without_confirmation_aborts(self, mock_client):
        result = runner.invoke(app, [
            "entity", "delete", SAMPLE_ENTITY["id"],
        ], input="y\n")
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Event commands
# ---------------------------------------------------------------------------


class TestEventList:
    def test_list_events(self, mock_client):
        mock_client.return_value.get_recent_events = AsyncMock(return_value=SAMPLE_EVENTS)
        result = runner.invoke(app, ["event", "list"])
        assert result.exit_code == 0

    def test_list_events_for_entity(self, mock_client):
        mock_client.return_value.get_entity_events = AsyncMock(return_value=SAMPLE_EVENTS)
        result = runner.invoke(app, [
            "event", "list", "--entity-id", SAMPLE_ENTITY["id"],
        ])
        assert result.exit_code == 0


class TestEventReplay:
    def test_replay_events(self, mock_client):
        mock_client.return_value.replay_entity_events = AsyncMock(return_value=SAMPLE_EVENTS)
        result = runner.invoke(app, [
            "event", "replay", SAMPLE_ENTITY["id"],
        ])
        assert result.exit_code == 0
        assert "Event History" in result.stdout

    def test_replay_no_events(self, mock_client):
        mock_client.return_value.replay_entity_events = AsyncMock(
            return_value={"events": [], "total": 0}
        )
        result = runner.invoke(app, [
            "event", "replay", SAMPLE_ENTITY["id"],
        ])
        assert result.exit_code == 0
        assert "No events" in result.stdout


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


class TestQuery:
    def test_query(self, mock_client):
        result = runner.invoke(app, ["query", "find all organizations"])
        assert result.exit_code == 0
        assert "Acme Corp" in result.stdout
        assert "12.34ms" in result.stdout

    def test_query_no_results(self):
        with patch("apps.cli.main.AwrenClient") as mock:
            client_instance = MagicMock()
            client_instance.query = AsyncMock(
                return_value={"results": [], "total": 0, "query_time_ms": 1.0}
            )
            mock.return_value = client_instance
            result = runner.invoke(app, ["query", "nonexistent"])
            assert result.exit_code == 0
            assert "No results" in result.stdout


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------


class TestHelp:
    def test_help_shows_commands(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "entity" in result.stdout
        assert "event" in result.stdout
        assert "query" in result.stdout
        assert "health" in result.stdout

    def test_entity_help(self):
        result = runner.invoke(app, ["entity", "--help"])
        assert result.exit_code == 0
        assert "create" in result.stdout
        assert "get" in result.stdout
        assert "list" in result.stdout
        assert "update" in result.stdout
        assert "delete" in result.stdout

    def test_event_help(self):
        result = runner.invoke(app, ["event", "--help"])
        assert result.exit_code == 0
        assert "list" in result.stdout
        assert "replay" in result.stdout
