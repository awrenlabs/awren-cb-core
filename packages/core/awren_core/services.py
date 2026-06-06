"""Domain services that wrap repositories with event sourcing."""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from awren_core.models import BaseEntity, BaseEvent, EventType
from awren_core.repositories import EntityRepository, EventRepository


class EventService:
    """Wraps entity operations and automatically records events (event sourcing).

    Every create, update, and delete operation generates an event in the
    append-only event log, enabling full auditability and state replay.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._entity_repo = EntityRepository(session)
        self._event_repo = EventRepository(session)

    # ------------------------------------------------------------------
    # Entity operations with automatic event recording
    # ------------------------------------------------------------------

    async def create_entity(self, entity: BaseEntity) -> BaseEntity:
        """Create an entity and record a EntityCreated event."""
        created = await self._entity_repo.create(entity)
        event = BaseEvent(
            type=EventType.ENTITY_CREATED.value,
            source="api",
            subject_id=created.id,
            payload={
                "entity_type": created.type,
                "label": created.label,
                "properties": created.properties,
            },
        )
        await self._event_repo.create(event)
        return created

    async def get_entity(self, entity_id: UUID) -> Optional[BaseEntity]:
        """Retrieve an entity by ID (read-only, no event recorded)."""
        return await self._entity_repo.get(entity_id)

    async def update_entity(self, entity: BaseEntity, changes: Optional[dict[str, Any]] = None) -> BaseEntity:
        """Update an entity and record an EntityUpdated event."""
        old = await self._entity_repo.get(entity.id)
        updated = await self._entity_repo.update(entity)
        event = BaseEvent(
            type=EventType.ENTITY_UPDATED.value,
            source="api",
            subject_id=updated.id,
            payload={
                "changes": changes or {},
                "previous_state": {
                    "label": old.label if old else None,
                    "description": old.description if old else None,
                } if old else {},
            },
        )
        await self._event_repo.create(event)
        return updated

    async def delete_entity(self, entity_id: UUID) -> None:
        """Delete an entity and record an EntityArchived event."""
        entity = await self._entity_repo.get(entity_id)
        if entity is None:
            raise ValueError(f"Entity {entity_id} not found")
        await self._entity_repo.delete(entity_id)
        event = BaseEvent(
            type=EventType.ENTITY_ARCHIVED.value,
            source="api",
            subject_id=entity_id,
            payload={
                "entity_type": entity.type,
                "label": entity.label,
            },
        )
        await self._event_repo.create(event)

    async def list_entities(self, entity_type: Optional[str] = None, limit: int = 100, offset: int = 0) -> list[BaseEntity]:
        """List entities with optional type filter."""
        if entity_type:
            return await self._entity_repo.list_by_type(entity_type, limit=limit, offset=offset)
        return await self._entity_repo.query("", {"limit": limit, "offset": offset})

    async def count_entities(self, entity_type: Optional[str] = None) -> int:
        """Count entities, optionally filtered by type."""
        return await self._entity_repo.count_by_type(entity_type)

    async def search_entities(self, query: str, params: Optional[dict[str, Any]] = None, limit: int = 100, offset: int = 0) -> list[BaseEntity]:
        """Search entities by query text and optional filters."""
        merged_params = dict(params or {})
        merged_params.setdefault("limit", limit)
        merged_params.setdefault("offset", offset)
        return await self._entity_repo.query(query, merged_params)

    # ------------------------------------------------------------------
    # Event querying
    # ------------------------------------------------------------------

    async def get_events_for_subject(self, subject_id: UUID) -> list[BaseEvent]:
        """Get all events for a given entity (chronological order)."""
        return await self._event_repo.replay(subject_id)

    async def get_recent_events(self, limit: int = 50) -> list[BaseEvent]:
        """Get the most recent events across all subjects."""
        return await self._event_repo.query("", {"limit": limit})

    async def replay_entity(self, entity_id: UUID) -> list[BaseEvent]:
        """Replay the full event history for an entity (for state reconstruction)."""
        return await self._event_repo.replay(entity_id)
