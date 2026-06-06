"""Repository implementations for the Awren Cognitive OS core entities."""

from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from awren_core.interfaces import RepositoryInterface
from awren_core.models import BaseEntity, BaseEvent, BaseRelationship
from awren_core.orm_models import EntityModel, EventModel, RelationshipModel


class EntityRepository(RepositoryInterface[BaseEntity]):
    """PostgreSQL repository for knowledge graph entities."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def create(self, entity: BaseEntity) -> BaseEntity:
        model = EntityModel(
            id=entity.id,
            type=entity.type,
            label=entity.label,
            description=entity.description,
            properties=entity.properties,
            identifiers=entity.identifiers,
            metadata=entity.metadata,
        )
        self._session.add(model)
        self._session.flush()
        return entity

    async def get(self, entity_id: UUID) -> Optional[BaseEntity]:
        stmt = select(EntityModel).where(EntityModel.id == entity_id)
        result = self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._model_to_entity(model)

    async def update(self, entity: BaseEntity) -> BaseEntity:
        stmt = select(EntityModel).where(EntityModel.id == entity.id)
        result = self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Entity {entity.id} not found")
        model.type = entity.type
        model.label = entity.label
        model.description = entity.description
        model.properties = entity.properties
        model.identifiers = entity.identifiers
        model.metadata_ = entity.metadata
        self._session.flush()
        return entity

    async def delete(self, entity_id: UUID) -> None:
        stmt = select(EntityModel).where(EntityModel.id == entity_id)
        result = self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is not None:
            self._session.delete(model)
            self._session.flush()

    async def query(self, query: str, params: Optional[dict[str, Any]] = None) -> list[BaseEntity]:
        stmt = select(EntityModel)
        if params:
            if "type" in params:
                stmt = stmt.where(EntityModel.type == params["type"])
            if "label" in params:
                stmt = stmt.where(EntityModel.label.ilike(f"%{params['label']}%"))
            if "limit" in params:
                stmt = stmt.limit(int(params["limit"]))
            if "offset" in params:
                stmt = stmt.offset(int(params["offset"]))
        result = self._session.execute(stmt)
        models = result.scalars().all()
        return [self._model_to_entity(m) for m in models]

    async def list_by_type(self, entity_type: str, limit: int = 100, offset: int = 0) -> list[BaseEntity]:
        stmt = (
            select(EntityModel)
            .where(EntityModel.type == entity_type)
            .offset(offset)
            .limit(limit)
        )
        result = self._session.execute(stmt)
        models = result.scalars().all()
        return [self._model_to_entity(m) for m in models]

    async def count_by_type(self, entity_type: Optional[str] = None) -> int:
        stmt = select(func.count(EntityModel.id))
        if entity_type:
            stmt = stmt.where(EntityModel.type == entity_type)
        result = self._session.execute(stmt)
        count: int = result.scalar_one()
        return count

    @staticmethod
    def _model_to_entity(model: EntityModel) -> BaseEntity:
        return BaseEntity(
            id=model.id,
            type=model.type,
            label=model.label,
            description=model.description,
            properties=model.properties,
            identifiers=model.identifiers,
            metadata=model.metadata_,
        )


class RelationshipRepository(RepositoryInterface[BaseRelationship]):
    """PostgreSQL repository for relationships."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def create(self, relationship: BaseRelationship) -> BaseRelationship:
        model = RelationshipModel(
            id=relationship.id,
            type=relationship.type,
            source_id=relationship.source_id,
            target_id=relationship.target_id,
            properties=relationship.properties,
            metadata=relationship.metadata,
        )
        self._session.add(model)
        self._session.flush()
        return relationship

    async def get(self, rel_id: UUID) -> Optional[BaseRelationship]:
        stmt = select(RelationshipModel).where(RelationshipModel.id == rel_id)
        result = self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._model_to_relationship(model)

    async def update(self, relationship: BaseRelationship) -> BaseRelationship:
        stmt = select(RelationshipModel).where(RelationshipModel.id == relationship.id)
        result = self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Relationship {relationship.id} not found")
        model.type = relationship.type
        model.properties = relationship.properties
        model.metadata_ = relationship.metadata
        self._session.flush()
        return relationship

    async def delete(self, rel_id: UUID) -> None:
        stmt = select(RelationshipModel).where(RelationshipModel.id == rel_id)
        result = self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is not None:
            self._session.delete(model)
            self._session.flush()

    async def query(self, query: str, params: Optional[dict[str, Any]] = None) -> list[BaseRelationship]:
        stmt = select(RelationshipModel)
        if params:
            if "source_id" in params:
                stmt = stmt.where(RelationshipModel.source_id == params["source_id"])
            if "target_id" in params:
                stmt = stmt.where(RelationshipModel.target_id == params["target_id"])
            if "limit" in params:
                stmt = stmt.limit(int(params["limit"]))
        result = self._session.execute(stmt)
        models = result.scalars().all()
        return [self._model_to_relationship(m) for m in models]

    async def find_by_source(self, source_id: UUID) -> list[BaseRelationship]:
        stmt = select(RelationshipModel).where(RelationshipModel.source_id == source_id)
        result = self._session.execute(stmt)
        models = result.scalars().all()
        return [self._model_to_relationship(m) for m in models]

    async def find_by_target(self, target_id: UUID) -> list[BaseRelationship]:
        stmt = select(RelationshipModel).where(RelationshipModel.target_id == target_id)
        result = self._session.execute(stmt)
        models = result.scalars().all()
        return [self._model_to_relationship(m) for m in models]

    @staticmethod
    def _model_to_relationship(model: RelationshipModel) -> BaseRelationship:
        return BaseRelationship(
            id=model.id,
            type=model.type,
            source_id=model.source_id,
            target_id=model.target_id,
            properties=model.properties,
            metadata=model.metadata_,
        )


class EventRepository(RepositoryInterface[BaseEvent]):
    """Append-only repository for events (event sourcing)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def create(self, event: BaseEvent) -> BaseEvent:
        model = EventModel(
            id=event.id,
            type=event.type,
            timestamp=event.timestamp,
            source=event.source,
            subject_id=event.subject_id,
            object_ids=list(event.object_ids),
            payload=event.payload,
            metadata=event.metadata,
        )
        self._session.add(model)
        self._session.flush()
        return event

    async def get(self, event_id: UUID) -> Optional[BaseEvent]:
        stmt = select(EventModel).where(EventModel.id == event_id)
        result = self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._model_to_event(model)

    async def update(self, event: BaseEvent) -> BaseEvent:
        raise NotImplementedError("Events are append-only and cannot be updated")

    async def delete(self, event_id: UUID) -> None:
        raise NotImplementedError("Events are append-only and cannot be deleted")

    async def query(self, query: str, params: Optional[dict[str, Any]] = None) -> list[BaseEvent]:
        stmt = select(EventModel).order_by(EventModel.timestamp.desc())
        if params:
            if "subject_id" in params:
                stmt = stmt.where(EventModel.subject_id == params["subject_id"])
            if "type" in params:
                stmt = stmt.where(EventModel.type == params["type"])
            if "limit" in params:
                stmt = stmt.limit(int(params["limit"]))
            if "offset" in params:
                stmt = stmt.offset(int(params["offset"]))
        result = self._session.execute(stmt)
        models = result.scalars().all()
        return [self._model_to_event(m) for m in models]

    async def replay(self, subject_id: UUID) -> list[BaseEvent]:
        """Replay all events for a given subject in chronological order."""
        stmt = (
            select(EventModel)
            .where(EventModel.subject_id == subject_id)
            .order_by(EventModel.timestamp.asc())
        )
        result = self._session.execute(stmt)
        models = result.scalars().all()
        return [self._model_to_event(m) for m in models]

    @staticmethod
    def _model_to_event(model: EventModel) -> BaseEvent:
        return BaseEvent(
            id=model.id,
            type=model.type,
            timestamp=model.timestamp,
            source=model.source,
            subject_id=model.subject_id,
            object_ids=list(model.object_ids) if model.object_ids else [],
            payload=model.payload,
            metadata=model.metadata_,
        )
