"""Event sourcing integration tests.

Tests that the EventService correctly records events for every entity
operation, and that events can be replayed to reconstruct state.
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from awren_core.database import Base
from awren_core.models import BaseEntity, BaseEvent, EventType
from awren_core.services import EventService


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(bind=engine)
    session = session_local()
    try:
        yield session
    finally:
        session.close()


class TestEventService:
    """Tests that EventService correctly records events for entity operations."""

    async def test_create_entity_records_event(self, db_session: Session):
        svc = EventService(db_session)
        entity = BaseEntity(type="core:Organization", label="Acme Corp")

        created = await svc.create_entity(entity)

        # Should have exactly one event
        events = await svc.get_events_for_subject(created.id)
        assert len(events) == 1
        assert events[0].type == EventType.ENTITY_CREATED.value
        assert events[0].subject_id == created.id
        assert events[0].payload["entity_type"] == "core:Organization"
        assert events[0].payload["label"] == "Acme Corp"

    async def test_get_entity_no_event(self, db_session: Session):
        svc = EventService(db_session)
        entity = BaseEntity(type="core:Person", label="Alice")
        created = await svc.create_entity(entity)

        # get_entity is read-only, should not record an event
        retrieved = await svc.get_entity(created.id)
        assert retrieved is not None
        assert retrieved.label == "Alice"

        events = await svc.get_events_for_subject(created.id)
        assert len(events) == 1  # Still only the create event

    async def test_update_entity_records_event(self, db_session: Session):
        svc = EventService(db_session)
        entity = BaseEntity(type="core:Project", label="Old Name")
        created = await svc.create_entity(entity)

        # Update the entity
        created.label = "New Name"
        changes = {"label": "New Name"}
        updated = await svc.update_entity(created, changes=changes)

        assert updated.label == "New Name"

        # Should have create + update events
        events = await svc.get_events_for_subject(created.id)
        assert len(events) == 2
        assert events[0].type == EventType.ENTITY_CREATED.value
        assert events[1].type == EventType.ENTITY_UPDATED.value
        assert events[1].payload["changes"]["label"] == "New Name"
        assert events[1].payload["previous_state"]["label"] == "Old Name"

    async def test_delete_entity_records_event(self, db_session: Session):
        svc = EventService(db_session)
        entity = BaseEntity(type="core:Document", label="Doc to delete")
        created = await svc.create_entity(entity)

        await svc.delete_entity(created.id)

        # Should have create + archive events
        events = await svc.get_events_for_subject(created.id)
        assert len(events) == 2
        assert events[0].type == EventType.ENTITY_CREATED.value
        assert events[1].type == EventType.ENTITY_ARCHIVED.value

        # Entity should no longer exist
        gone = await svc.get_entity(created.id)
        assert gone is None

    async def test_delete_nonexistent_entity(self, db_session: Session):
        svc = EventService(db_session)
        with pytest.raises(ValueError, match="not found"):
            await svc.delete_entity(uuid4())

    async def test_replay_events_chronological(self, db_session: Session):
        svc = EventService(db_session)
        entity = BaseEntity(type="core:Asset", label="Server-01")
        created = await svc.create_entity(entity)

        created.label = "Server-01-updated"
        await svc.update_entity(created, changes={"label": "Server-01-updated"})

        created.label = "Server-01-prod"
        await svc.update_entity(created, changes={"label": "Server-01-prod"})

        # Replay should return events in chronological order
        events = await svc.replay_entity(created.id)
        assert len(events) == 3
        assert events[0].type == EventType.ENTITY_CREATED.value
        assert events[1].type == EventType.ENTITY_UPDATED.value
        assert events[2].type == EventType.ENTITY_UPDATED.value

        # State reconstruction from events
        state_types = [e.type for e in events]
        last_event = events[-1]
        assert last_event.payload["changes"]["label"] == "Server-01-prod"

    async def test_list_entities(self, db_session: Session):
        svc = EventService(db_session)
        await svc.create_entity(BaseEntity(type="core:Organization", label="Org A"))
        await svc.create_entity(BaseEntity(type="core:Organization", label="Org B"))
        await svc.create_entity(BaseEntity(type="core:Person", label="Person C"))

        all_entities = await svc.list_entities()
        assert len(all_entities) == 3

        orgs = await svc.list_entities(entity_type="core:Organization")
        assert len(orgs) == 2

        assert await svc.count_entities() == 3
        assert await svc.count_entities("core:Organization") == 2

    async def test_get_recent_events_across_subjects(self, db_session: Session):
        svc = EventService(db_session)
        e1 = BaseEntity(type="core:Organization", label="Org 1")
        e2 = BaseEntity(type="core:Document", label="Doc 1")

        await svc.create_entity(e1)
        await svc.create_entity(e2)

        recent = await svc.get_recent_events(limit=10)
        assert len(recent) == 2  # Two create events
        assert EventType.ENTITY_CREATED.value in {e.type for e in recent}

    async def test_mixed_operations_generate_correct_event_sequence(self, db_session: Session):
        """Integration test: full lifecycle of an entity with event trace."""
        svc = EventService(db_session)

        # Create
        entity = BaseEntity(type="core:Project", label="Project X")
        created = await svc.create_entity(entity)
        assert created.id is not None

        # Update twice
        created.label = "Project X v2"
        await svc.update_entity(created, changes={"label": "Project X v2"})

        created.label = "Project X v3"
        created.description = "Final version"
        await svc.update_entity(created, changes={
            "label": "Project X v3",
            "description": "Final version",
        })

        # Delete
        await svc.delete_entity(created.id)

        # Full event trace: Create → Update → Update → Archive
        events = await svc.replay_entity(created.id)
        assert len(events) == 4
        event_types = [e.type for e in events]
        assert event_types == [
            EventType.ENTITY_CREATED.value,
            EventType.ENTITY_UPDATED.value,
            EventType.ENTITY_UPDATED.value,
            EventType.ENTITY_ARCHIVED.value,
        ]
