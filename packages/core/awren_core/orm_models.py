"""SQLAlchemy ORM models for the Awren Cognitive OS core entities."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, Integer, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from awren_core.database import Base


class EntityModel(Base):
    """SQLAlchemy model for knowledge graph entities."""

    __tablename__ = "entities"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    type: Mapped[str] = mapped_column(String(255), index=True)
    label: Mapped[str] = mapped_column(String(500))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    properties: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    identifiers: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True, default=None)
    version_num: Mapped[int] = mapped_column(Integer, default=1)
    provenance: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<EntityModel id={self.id} type={self.type} label={self.label}>"


class EntityVersionModel(Base):
    """Append-only version history for entities — full snapshots."""

    __tablename__ = "entity_versions"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    entity_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), index=True, nullable=False
    )
    version_num: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    change_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<EntityVersionModel entity={self.entity_id} v{self.version_num}>"


class OntologyTypeModel(Base):
    """Registered ontology object types with schema definitions."""

    __tablename__ = "ontology_types"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    base_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    states: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["active"])
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<OntologyTypeModel name={self.name}>"


class OntologyPropertyModel(Base):
    """Property schema definition for an ontology type."""

    __tablename__ = "ontology_properties"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    type_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    property_type: Mapped[str] = mapped_column(String(50), nullable=False, default="string")
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="static")
    required: Mapped[bool] = mapped_column(default=False)
    default_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    formula: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<OntologyPropertyModel type={self.type_id} name={self.name}>"


class RelationshipModel(Base):
    """SQLAlchemy model for relationships between entities."""

    __tablename__ = "relationships"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    type: Mapped[str] = mapped_column(String(255), index=True)
    source_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), index=True, nullable=False
    )
    target_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), index=True, nullable=False
    )
    properties: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<RelationshipModel id={self.id} type={self.type} "
            f"source={self.source_id} target={self.target_id}>"
        )


class LlmSettingsModel(Base):
    """Persisted LLM provider/model/keys configuration (single row)."""

    __tablename__ = "llm_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="openai")
    model: Mapped[str] = mapped_column(String(200), nullable=False, default="gpt-4o-mini")
    openai_api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    anthropic_api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ConversationModel(Base):
    """Persisted chat conversation."""

    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    title: Mapped[str] = mapped_column(String(500), default="New conversation")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<ConversationModel id={self.id} title={self.title}>"


class MessageModel(Base):
    """A single message within a conversation."""

    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<MessageModel id={self.id} role={self.role}>"


class EventModel(Base):
    """SQLAlchemy model for the append-only event log."""

    __tablename__ = "events"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    type: Mapped[str] = mapped_column(String(255), index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, server_default=func.now()
    )
    source: Mapped[str] = mapped_column(String(255), default="system")
    subject_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), index=True, nullable=False
    )
    object_ids: Mapped[list[UUID]] = mapped_column(JSON, default=list)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<EventModel id={self.id} type={self.type} subject={self.subject_id}>"


class ImportJobModel(Base):
    """Tracks file import jobs — upload to ontology pipeline."""

    __tablename__ = "import_jobs"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(default=0)
    mime_type: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    total_entities: Mapped[int] = mapped_column(default=0)
    total_relationships: Mapped[int] = mapped_column(default=0)
    error_messages: Mapped[list[str]] = mapped_column(JSON, default=list)
    result_summary: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<ImportJobModel id={self.id} file={self.original_filename} status={self.status}>"


class AudioTranscriptionModel(Base):
    """Persisted audio transcription records."""

    __tablename__ = "audio_transcriptions"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(default=0)
    duration_seconds: Mapped[float] = mapped_column(default=0.0)
    transcription_text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(20), default="unknown")
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<AudioTranscriptionModel id={self.id} file={self.original_filename}>"
