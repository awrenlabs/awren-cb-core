"""Repository implementations for the Awren Cognitive OS core entities."""

from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from awren_core.interfaces import RepositoryInterface
from awren_core.models import BaseEntity, BaseEvent, BaseRelationship
from awren_core.orm_models import (
    ConversationModel,
    EntityModel,
    EntityVersionModel,
    EventModel,
    LlmSettingsModel,
    MessageModel,
    OntologyPropertyModel,
    OntologyTypeModel,
    RelationshipModel,
)


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
            state=entity.state,
            version_num=entity.version_num,
            provenance=entity.provenance,
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
        model.state = entity.state
        model.version_num = entity.version_num
        model.provenance = entity.provenance
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
        if query:
            stmt = stmt.where(EntityModel.label.ilike(f"%{query}%"))
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
            state=model.state,
            version_num=model.version_num,
            provenance=model.provenance,
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
            object_ids=[str(oid) for oid in event.object_ids],
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
        from uuid import UUID
        object_ids = []
        if model.object_ids:
            for oid in model.object_ids:
                if isinstance(oid, str):
                    try:
                        object_ids.append(UUID(oid))
                    except ValueError:
                        object_ids.append(oid)
                else:
                    object_ids.append(oid)
        return BaseEvent(
            id=model.id,
            type=model.type,
            timestamp=model.timestamp,
            source=model.source,
            subject_id=model.subject_id,
            object_ids=object_ids,
            payload=model.payload,
            metadata=model.metadata_,
        )


class LlmSettingsRepository:
    """Repository for persisted LLM configuration."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def get(self) -> dict[str, str]:
        stmt = select(LlmSettingsModel).where(LlmSettingsModel.id == 1)
        result = self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return {"provider": "openai", "model": "gpt-4o-mini"}
        return {
            "provider": model.provider,
            "model": model.model,
            "openai_api_key": model.openai_api_key or "",
            "anthropic_api_key": model.anthropic_api_key or "",
        }

    async def upsert(self, provider: str, model: str, openai_api_key: str = "", anthropic_api_key: str = "") -> dict[str, str]:
        stmt = select(LlmSettingsModel).where(LlmSettingsModel.id == 1)
        result = self._session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            existing.provider = provider
            existing.model = model
            if openai_api_key:
                existing.openai_api_key = openai_api_key
            if anthropic_api_key:
                existing.anthropic_api_key = anthropic_api_key
        else:
            self._session.add(LlmSettingsModel(
                id=1,
                provider=provider,
                model=model,
                openai_api_key=openai_api_key or None,
                anthropic_api_key=anthropic_api_key or None,
            ))
        self._session.flush()
        return {"provider": provider, "model": model, "openai_api_key": openai_api_key, "anthropic_api_key": anthropic_api_key}

    async def has_key_for(self, provider: str) -> bool:
        stmt = select(LlmSettingsModel).where(LlmSettingsModel.id == 1)
        result = self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return False
        if provider == "anthropic":
            return bool(model.anthropic_api_key)
        return bool(model.openai_api_key)


class ConversationRepository:
    """Repository for chat conversations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def create(self, title: str = "New conversation") -> ConversationModel:
        model = ConversationModel(
            id=uuid4(),
            title=title,
        )
        self._session.add(model)
        self._session.flush()
        return model

    async def get(self, conv_id: UUID) -> Optional[ConversationModel]:
        stmt = select(ConversationModel).where(ConversationModel.id == conv_id)
        return self._session.execute(stmt).scalar_one_or_none()

    async def list_all(self, limit: int = 50) -> list[ConversationModel]:
        stmt = (
            select(ConversationModel)
            .order_by(ConversationModel.updated_at.desc())
            .limit(limit)
        )
        return list(self._session.execute(stmt).scalars().all())

    async def update_title(self, conv_id: UUID, title: str) -> None:
        model = await self.get(conv_id)
        if model:
            model.title = title
            self._session.flush()

    async def delete(self, conv_id: UUID) -> None:
        model = await self.get(conv_id)
        if model:
            # Delete all messages first
            from sqlalchemy import delete
            self._session.execute(
                delete(MessageModel).where(MessageModel.conversation_id == conv_id)
            )
            self._session.delete(model)
            self._session.flush()


class MessageRepository:
    """Repository for messages within conversations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def create(self, conversation_id: UUID, role: str, content: str, metadata: Optional[dict] = None) -> MessageModel:
        model = MessageModel(
            id=uuid4(),
            conversation_id=conversation_id,
            role=role,
            content=content,
            metadata_=metadata or {},
        )
        self._session.add(model)
        self._session.flush()
        return model

    async def list_by_conversation(self, conversation_id: UUID, limit: int = 200) -> list[MessageModel]:
        stmt = (
            select(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .order_by(MessageModel.created_at.asc())
            .limit(limit)
        )
        return list(self._session.execute(stmt).scalars().all())

    async def get_recent(self, conversation_id: UUID, count: int = 20) -> list[MessageModel]:
        stmt = (
            select(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .order_by(MessageModel.created_at.desc())
            .limit(count)
        )
        msgs = list(self._session.execute(stmt).scalars().all())
        msgs.reverse()
        return msgs


class OntologyTypeRepository:
    """Repository for ontology type definitions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def create(self, name: str, description: str = "", base_type: str = "", states: Optional[list[str]] = None, config: Optional[dict] = None) -> OntologyTypeModel:
        model = OntologyTypeModel(
            id=uuid4(),
            name=name,
            description=description,
            base_type=base_type or None,
            states=states or ["active"],
            config=config or {},
        )
        self._session.add(model)
        self._session.flush()
        return model

    async def get_by_name(self, name: str) -> Optional[OntologyTypeModel]:
        stmt = select(OntologyTypeModel).where(OntologyTypeModel.name == name)
        return self._session.execute(stmt).scalar_one_or_none()

    async def get(self, type_id: UUID) -> Optional[OntologyTypeModel]:
        stmt = select(OntologyTypeModel).where(OntologyTypeModel.id == type_id)
        return self._session.execute(stmt).scalar_one_or_none()

    async def list_all(self) -> list[OntologyTypeModel]:
        stmt = select(OntologyTypeModel).order_by(OntologyTypeModel.name)
        return list(self._session.execute(stmt).scalars().all())

    async def delete(self, type_id: UUID) -> None:
        stmt = select(OntologyTypeModel).where(OntologyTypeModel.id == type_id)
        model = self._session.execute(stmt).scalar_one_or_none()
        if model:
            # Delete associated properties first
            from sqlalchemy import delete as del_stmt
            self._session.execute(
                del_stmt(OntologyPropertyModel).where(OntologyPropertyModel.type_id == type_id)
            )
            self._session.delete(model)
            self._session.flush()


class OntologyPropertyRepository:
    """Repository for ontology property definitions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def create(self, type_id: UUID, name: str, property_type: str = "string",
                     kind: str = "static", required: bool = False,
                     default_value: Optional[str] = None, formula: Optional[str] = None,
                     config: Optional[dict] = None) -> OntologyPropertyModel:
        model = OntologyPropertyModel(
            id=uuid4(),
            type_id=type_id,
            name=name,
            property_type=property_type,
            kind=kind,
            required=required,
            default_value=default_value,
            formula=formula,
            config=config or {},
        )
        self._session.add(model)
        self._session.flush()
        return model

    async def get_by_name(self, type_id: UUID, name: str) -> Optional[OntologyPropertyModel]:
        stmt = (
            select(OntologyPropertyModel)
            .where(OntologyPropertyModel.type_id == type_id)
            .where(OntologyPropertyModel.name == name)
        )
        return self._session.execute(stmt).scalar_one_or_none()

    async def list_by_type(self, type_id: UUID, kind: Optional[str] = None) -> list[OntologyPropertyModel]:
        stmt = (
            select(OntologyPropertyModel)
            .where(OntologyPropertyModel.type_id == type_id)
            .order_by(OntologyPropertyModel.ordinal)
        )
        if kind:
            stmt = stmt.where(OntologyPropertyModel.kind == kind)
        return list(self._session.execute(stmt).scalars().all())

    async def delete(self, prop_id: UUID) -> None:
        stmt = select(OntologyPropertyModel).where(OntologyPropertyModel.id == prop_id)
        model = self._session.execute(stmt).scalar_one_or_none()
        if model:
            self._session.delete(model)
            self._session.flush()


class EntityVersionRepository:
    """Repository for entity version history."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def create(self, entity_id: UUID, snapshot: dict, change_description: str = "") -> dict:
        # Determine next version number
        stmt = (
            select(EntityVersionModel)
            .where(EntityVersionModel.entity_id == entity_id)
            .order_by(EntityVersionModel.version_num.desc())
            .limit(1)
        )
        last = self._session.execute(stmt).scalar_one_or_none()
        next_version = (last.version_num + 1) if last else 1

        model = EntityVersionModel(
            id=uuid4(),
            entity_id=entity_id,
            version_num=next_version,
            snapshot=snapshot,
            change_description=change_description,
        )
        self._session.add(model)
        self._session.flush()
        return {
            "version_num": next_version,
            "snapshot": snapshot,
            "change_description": change_description,
        }

    async def list_by_entity(self, entity_id: UUID) -> list[EntityVersionModel]:
        stmt = (
            select(EntityVersionModel)
            .where(EntityVersionModel.entity_id == entity_id)
            .order_by(EntityVersionModel.version_num.desc())
        )
        return list(self._session.execute(stmt).scalars().all())

    async def get_by_version(self, entity_id: UUID, version_num: int) -> Optional[EntityVersionModel]:
        stmt = (
            select(EntityVersionModel)
            .where(EntityVersionModel.entity_id == entity_id)
            .where(EntityVersionModel.version_num == version_num)
        )
        return self._session.execute(stmt).scalar_one_or_none()