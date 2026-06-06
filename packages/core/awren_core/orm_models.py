"""SQLAlchemy ORM models for the Awren Cognitive OS core entities."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import DateTime, JSON, String, Text, func
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<EntityModel id={self.id} type={self.type} label={self.label}>"


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
