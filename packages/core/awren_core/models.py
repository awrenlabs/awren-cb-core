"""Core domain models for the Awren Cognitive OS."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


def _utc_now() -> str:
    """Return current UTC timestamp as ISO string."""
    return datetime.now(timezone.utc).isoformat()


class BaseEntity(BaseModel):
    """Fundamental unit of representation in the knowledge graph."""

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "type": "core:Organization",
            "label": "Acme Construction",
            "description": "A major construction firm",
        }
    })

    id: UUID = Field(default_factory=uuid4)
    type: str
    label: str
    description: Optional[str] = None
    properties: dict[str, Any] = Field(default_factory=dict)
    identifiers: list[dict[str, str]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=lambda: {
        "created": _utc_now(),
        "updated": _utc_now(),
        "created_by": "system",
        "confidence": 1.0,
    })


class BaseRelationship(BaseModel):
    """Edge connecting two entities in the knowledge graph."""

    id: UUID = Field(default_factory=uuid4)
    type: str
    source_id: UUID
    target_id: UUID
    properties: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=lambda: {
        "created": _utc_now(),
        "created_by": "system",
        "confidence": 1.0,
        "valid_from": _utc_now(),
        "valid_to": None,
    })


class BaseEvent(BaseModel):
    """Temporal record of an occurrence or change."""

    id: UUID = Field(default_factory=uuid4)
    type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str
    subject_id: UUID
    object_ids: list[UUID] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=lambda: {
        "correlation_id": None,
        "causation_id": None,
        "confidence": 1.0,
    })


class EntityType(str, Enum):
    """Core ontology entity types."""
    ORGANIZATION = "core:Organization"
    PERSON = "core:Person"
    PROJECT = "core:Project"
    DOCUMENT = "core:Document"
    EVENT = "core:Event"
    CONCEPT = "core:Concept"
    ASSET = "core:Asset"
    LOCATION = "core:Location"


class RelationshipType(str, Enum):
    """Core ontology relationship types."""
    OWNS = "core:owns"
    EMPLOYS = "core:employs"
    PARTICIPATES_IN = "core:participatesIn"
    LOCATED_AT = "core:locatedAt"
    PRODUCES = "core:produces"
    INVESTS_IN = "core:investsIn"
    REGULATES = "core:regulates"
    COLLABORATES_WITH = "core:collaboratesWith"
    DERIVED_FROM = "core:derivedFrom"
    REFERENCES = "core:references"


class EventType(str, Enum):
    """Core ontology event types."""
    ENTITY_CREATED = "mem:EntityCreated"
    ENTITY_UPDATED = "mem:EntityUpdated"
    ENTITY_ARCHIVED = "mem:EntityArchived"
    RELATIONSHIP_ADDED = "mem:RelationshipAdded"
    RELATIONSHIP_REMOVED = "mem:RelationshipRemoved"
    OBSERVATION_RECORDED = "mem:ObservationRecorded"
    DECISION_MADE = "mem:DecisionMade"
    SYSTEM_EVENT = "mem:SystemEvent"
    QUERY_EXECUTED = "mem:QueryExecuted"
    AGENT_ACTION = "mem:AgentAction"
