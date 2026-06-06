"""Repository implementation tests using SQLite in-memory database."""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from awren_core.database import Base
from awren_core.models import BaseEntity, BaseEvent, BaseRelationship
from awren_core.repositories import EntityRepository, EventRepository, RelationshipRepository


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


class TestEntityRepository:
    async def test_create_and_get_entity(self, db_session: Session):
        repo = EntityRepository(db_session)
        entity = BaseEntity(type="core:Organization", label="Test Org")

        created = await repo.create(entity)
        assert created.id == entity.id

        retrieved = await repo.get(entity.id)
        assert retrieved is not None
        assert retrieved.id == entity.id
        assert retrieved.label == "Test Org"
        assert retrieved.type == "core:Organization"

    async def test_get_nonexistent_entity(self, db_session: Session):
        repo = EntityRepository(db_session)
        entity = await repo.get(uuid4())
        assert entity is None

    async def test_update_entity(self, db_session: Session):
        repo = EntityRepository(db_session)
        entity = BaseEntity(type="core:Project", label="Old Name")
        await repo.create(entity)

        entity.label = "New Name"
        entity.description = "Updated description"
        updated = await repo.update(entity)
        assert updated.label == "New Name"
        assert updated.description == "Updated description"

        retrieved = await repo.get(entity.id)
        assert retrieved is not None
        assert retrieved.label == "New Name"

    async def test_delete_entity(self, db_session: Session):
        repo = EntityRepository(db_session)
        entity = BaseEntity(type="core:Document", label="Doc to delete")
        await repo.create(entity)

        await repo.delete(entity.id)
        retrieved = await repo.get(entity.id)
        assert retrieved is None

    async def test_list_by_type(self, db_session: Session):
        repo = EntityRepository(db_session)
        org1 = BaseEntity(type="core:Organization", label="Org A")
        org2 = BaseEntity(type="core:Organization", label="Org B")
        person = BaseEntity(type="core:Person", label="John")
        await repo.create(org1)
        await repo.create(org2)
        await repo.create(person)

        orgs = await repo.list_by_type("core:Organization")
        assert len(orgs) == 2

        people = await repo.list_by_type("core:Person")
        assert len(people) == 1

    async def test_count_by_type(self, db_session: Session):
        repo = EntityRepository(db_session)
        await repo.create(BaseEntity(type="core:Organization", label="O1"))
        await repo.create(BaseEntity(type="core:Organization", label="O2"))
        await repo.create(BaseEntity(type="core:Person", label="P1"))

        assert await repo.count_by_type("core:Organization") == 2
        assert await repo.count_by_type("core:Person") == 1

    async def test_query_by_params(self, db_session: Session):
        repo = EntityRepository(db_session)
        await repo.create(BaseEntity(type="core:Organization", label="Acme Corp"))
        await repo.create(BaseEntity(type="core:Person", label="Alice"))
        await repo.create(BaseEntity(type="core:Project", label="Project X"))

        results = await repo.query("", {"type": "core:Organization"})
        assert len(results) == 1
        assert results[0].label == "Acme Corp"


class TestRelationshipRepository:
    async def test_create_and_get_relationship(self, db_session: Session):
        repo = RelationshipRepository(db_session)
        rel = BaseRelationship(
            type="core:employs",
            source_id=uuid4(),
            target_id=uuid4(),
        )
        created = await repo.create(rel)
        assert created.id == rel.id

        retrieved = await repo.get(rel.id)
        assert retrieved is not None
        assert retrieved.type == "core:employs"

    async def test_find_by_source(self, db_session: Session):
        repo = RelationshipRepository(db_session)
        source = uuid4()
        target_a = uuid4()
        target_b = uuid4()

        await repo.create(BaseRelationship(type="core:employs", source_id=source, target_id=target_a))
        await repo.create(BaseRelationship(type="core:employs", source_id=source, target_id=target_b))

        results = await repo.find_by_source(source)
        assert len(results) == 2

    async def test_find_by_target(self, db_session: Session):
        repo = RelationshipRepository(db_session)
        target = uuid4()
        await repo.create(BaseRelationship(type="core:employs", source_id=uuid4(), target_id=target))
        await repo.create(BaseRelationship(type="core:collaboratesWith", source_id=uuid4(), target_id=target))

        results = await repo.find_by_target(target)
        assert len(results) == 2


class TestEventRepository:
    async def test_create_and_get_event(self, db_session: Session):
        repo = EventRepository(db_session)
        event = BaseEvent(
            type="mem:EntityCreated",
            source="test",
            subject_id=uuid4(),
            payload={"key": "value"},
        )
        created = await repo.create(event)
        assert created.id == event.id

        retrieved = await repo.get(event.id)
        assert retrieved is not None
        assert retrieved.type == "mem:EntityCreated"
        assert retrieved.payload["key"] == "value"

    async def test_append_only_raises_on_update(self, db_session: Session):
        repo = EventRepository(db_session)
        event = BaseEvent(type="mem:SystemEvent", source="test", subject_id=uuid4())
        await repo.create(event)
        with pytest.raises(NotImplementedError, match="append-only"):
            await repo.update(event)

    async def test_append_only_raises_on_delete(self, db_session: Session):
        repo = EventRepository(db_session)
        event = BaseEvent(type="mem:SystemEvent", source="test", subject_id=uuid4())
        await repo.create(event)
        with pytest.raises(NotImplementedError, match="append-only"):
            await repo.delete(event.id)

    async def test_replay_events(self, db_session: Session):
        repo = EventRepository(db_session)
        subject = uuid4()

        event1 = BaseEvent(type="mem:EntityCreated", source="test", subject_id=subject)
        event2 = BaseEvent(type="mem:EntityUpdated", source="test", subject_id=subject)

        await repo.create(event1)
        await repo.create(event2)

        events = await repo.replay(subject)
        assert len(events) == 2
        assert events[0].type == "mem:EntityCreated"
        assert events[1].type == "mem:EntityUpdated"
