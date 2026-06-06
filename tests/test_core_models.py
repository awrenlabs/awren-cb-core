"""Core model unit tests."""

import pytest
from uuid import UUID, uuid4
from datetime import datetime

from awren_core.models import (
    BaseEntity,
    BaseRelationship,
    BaseEvent,
    EntityType,
    RelationshipType,
    EventType,
)


class TestBaseEntity:
    def test_create_entity_with_defaults(self):
        entity = BaseEntity(type="core:Organization", label="Test Org")
        assert isinstance(entity.id, UUID)
        assert entity.type == "core:Organization"
        assert entity.label == "Test Org"
        assert entity.description is None
        assert entity.properties == {}
        assert entity.identifiers == []
        assert "created" in entity.metadata
        assert "updated" in entity.metadata

    def test_create_entity_with_all_fields(self):
        entity = BaseEntity(
            type="core:Person",
            label="John Doe",
            description="A test person",
            properties={"age": 30, "email": "john@example.com"},
            identifiers=[{"system": "internal", "value": "EMP-001"}],
        )
        assert entity.description == "A test person"
        assert entity.properties["age"] == 30
        assert entity.identifiers[0]["value"] == "EMP-001"

    def test_entity_uses_entity_type_enum(self):
        entity = BaseEntity(type=EntityType.ORGANIZATION, label="Acme")
        assert entity.type == "core:Organization"

    def test_entity_json_serializable(self):
        entity = BaseEntity(type="core:Project", label="Project Alpha")
        data = entity.model_dump(mode="json")
        assert data["type"] == "core:Project"
        assert data["label"] == "Project Alpha"
        assert isinstance(data["id"], str)  # UUID serialized to string

    def test_two_entities_have_different_ids(self):
        e1 = BaseEntity(type="core:Organization", label="Org A")
        e2 = BaseEntity(type="core:Organization", label="Org B")
        assert e1.id != e2.id


class TestBaseRelationship:
    def test_create_relationship(self):
        source_id = uuid4()
        target_id = uuid4()
        rel = BaseRelationship(
            type="core:employs",
            source_id=source_id,
            target_id=target_id,
        )
        assert isinstance(rel.id, UUID)
        assert rel.type == "core:employs"
        assert rel.source_id == source_id
        assert rel.target_id == target_id
        assert rel.properties == {}
        assert "valid_from" in rel.metadata

    def test_relationship_with_properties(self):
        rel = BaseRelationship(
            type="core:owns",
            source_id=uuid4(),
            target_id=uuid4(),
            properties={"since": "2024-01-01", "share": 0.75},
        )
        assert rel.properties["share"] == 0.75

    def test_relationship_uses_enum(self):
        rel = BaseRelationship(
            type=RelationshipType.EMPLOYS,
            source_id=uuid4(),
            target_id=uuid4(),
        )
        assert rel.type == "core:employs"


class TestBaseEvent:
    def test_create_event(self):
        subject_id = uuid4()
        event = BaseEvent(
            type="mem:EntityCreated",
            source="test",
            subject_id=subject_id,
        )
        assert isinstance(event.id, UUID)
        assert event.type == "mem:EntityCreated"
        assert event.source == "test"
        assert event.subject_id == subject_id
        assert event.object_ids == []
        assert event.payload == {}
        assert isinstance(event.timestamp, datetime)

    def test_event_with_payload(self):
        event = BaseEvent(
            type="mem:EntityUpdated",
            source="system",
            subject_id=uuid4(),
            object_ids=[uuid4()],
            payload={"changes": {"name": "New Name"}},
        )
        assert len(event.object_ids) == 1
        assert event.payload["changes"]["name"] == "New Name"

    def test_event_uses_enum(self):
        event = BaseEvent(
            type=EventType.ENTITY_CREATED,
            source="test",
            subject_id=uuid4(),
        )
        assert event.type == "mem:EntityCreated"
