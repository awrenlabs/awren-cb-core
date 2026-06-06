"""Pydantic schemas for API serialization."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Entity schemas
# ---------------------------------------------------------------------------


class EntityCreate(BaseModel):
    type: str
    label: str
    description: Optional[str] = None
    properties: dict[str, Any] = {}
    identifiers: list[dict[str, str]] = []


class EntityUpdate(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    properties: Optional[dict[str, Any]] = None
    identifiers: Optional[list[dict[str, str]]] = None


class EntityResponse(BaseModel):
    id: UUID
    type: str
    label: str
    description: Optional[str] = None
    properties: dict[str, Any]
    identifiers: list[dict[str, str]]
    metadata: dict[str, Any]


class EntityListResponse(BaseModel):
    entities: list[EntityResponse]
    total: int


# ---------------------------------------------------------------------------
# Event schemas
# ---------------------------------------------------------------------------


class EventResponse(BaseModel):
    id: UUID
    type: str
    timestamp: datetime
    source: str
    subject_id: UUID
    object_ids: list[UUID]
    payload: dict[str, Any]
    metadata: dict[str, Any]


class EventListResponse(BaseModel):
    events: list[EventResponse]
    total: int


# ---------------------------------------------------------------------------
# Query schemas
# ---------------------------------------------------------------------------


class QueryRequest(BaseModel):
    query: str
    params: dict[str, Any] = {}
    limit: int = 100
    offset: int = 0


class QueryResponse(BaseModel):
    results: list[dict[str, Any]]
    total: int
    query_time_ms: float


# ---------------------------------------------------------------------------
# Agent schemas
# ---------------------------------------------------------------------------


class AgentQueryRequest(BaseModel):
    query: str
    entity_type: Optional[str] = None
    search_limit: int = 20


class AgentQueryResponse(BaseModel):
    task_id: str
    agent_type: str
    output: dict[str, Any]
    confidence: float
    execution_time_ms: float
