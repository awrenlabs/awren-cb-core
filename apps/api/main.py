"""Awren Core API — FastAPI Application."""

import logging
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager
from typing import Any, Optional
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from awren_core.database import create_session, init_db
from awren_core.models import BaseEntity, BaseEvent
from awren_agents.base import AgentTask
from awren_agents.research_agent import ResearchAgent
from awren_core.schemas import (
    AgentQueryRequest,
    AgentQueryResponse,
    EntityCreate,
    EntityListResponse,
    EntityResponse,
    EntityUpdate,
    EventListResponse,
    EventResponse,
    QueryRequest,
    QueryResponse,
)
from awren_core.services import EventService
from apps.dashboard.main import router as dashboard_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[Any, None]:
    """Initialize database tables on startup."""
    logger.info("Awren Core API starting up...")
    try:
        init_db()
        logger.info("Database tables initialized.")
    except Exception as e:
        logger.warning("Database initialization skipped (not available): %s", e)
    yield
    logger.info("Awren Core API shutting down...")


app = FastAPI(
    title="Awren Core API",
    description="Cognitive Operating System for Institutional Intelligence",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount dashboard routes
app.include_router(dashboard_router)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    session = create_session()
    try:
        yield session
    finally:
        session.close()


def get_event_service(db: Session = Depends(get_db)) -> EventService:
    """FastAPI dependency that yields an EventService."""
    return EventService(db)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health", tags=["System"])
async def health_check() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


# ---------------------------------------------------------------------------
# Entity CRUD (event-sourced)
# ---------------------------------------------------------------------------


def _entity_to_response(entity: BaseEntity) -> EntityResponse:
    return EntityResponse(
        id=entity.id,
        type=entity.type,
        label=entity.label,
        description=entity.description,
        properties=entity.properties,
        identifiers=entity.identifiers,
        metadata=entity.metadata,
    )


@app.post("/api/v1/entities", response_model=EntityResponse, status_code=201, tags=["Entities"])
async def create_entity(
    payload: EntityCreate,
    svc: EventService = Depends(get_event_service),
) -> EntityResponse:
    """Create a new entity in the knowledge graph (event is recorded)."""
    entity = BaseEntity(
        type=payload.type,
        label=payload.label,
        description=payload.description,
        properties=payload.properties,
        identifiers=payload.identifiers,
    )
    created = await svc.create_entity(entity)
    return _entity_to_response(created)


@app.get("/api/v1/entities", response_model=EntityListResponse, tags=["Entities"])
async def list_entities(
    type: Optional[str] = Query(None, alias="type"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    svc: EventService = Depends(get_event_service),
) -> EntityListResponse:
    """List entities, optionally filtered by type."""
    entities = await svc.list_entities(type, limit=limit, offset=offset)
    total = await svc.count_entities(type)
    return EntityListResponse(
        entities=[_entity_to_response(e) for e in entities],
        total=total,
    )


@app.get("/api/v1/entities/{entity_id}", response_model=EntityResponse, tags=["Entities"])
async def get_entity(
    entity_id: UUID,
    svc: EventService = Depends(get_event_service),
) -> EntityResponse:
    """Retrieve a single entity by ID."""
    entity = await svc.get_entity(entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return _entity_to_response(entity)


@app.patch("/api/v1/entities/{entity_id}", response_model=EntityResponse, tags=["Entities"])
async def update_entity(
    entity_id: UUID,
    payload: EntityUpdate,
    svc: EventService = Depends(get_event_service),
) -> EntityResponse:
    """Update an entity (event is recorded with change tracking)."""
    entity = await svc.get_entity(entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    changes: dict[str, Any] = {}
    if payload.label is not None:
        changes["label"] = payload.label
        entity.label = payload.label
    if payload.description is not None:
        changes["description"] = payload.description
        entity.description = payload.description
    if payload.properties is not None:
        changes["properties"] = payload.properties
        entity.properties = payload.properties
    if payload.identifiers is not None:
        changes["identifiers"] = payload.identifiers
        entity.identifiers = payload.identifiers

    updated = await svc.update_entity(entity, changes=changes)
    return _entity_to_response(updated)


@app.delete("/api/v1/entities/{entity_id}", status_code=204, tags=["Entities"])
async def delete_entity(
    entity_id: UUID,
    svc: EventService = Depends(get_event_service),
) -> None:
    """Delete an entity by ID (event is recorded)."""
    entity = await svc.get_entity(entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    await svc.delete_entity(entity_id)


# ---------------------------------------------------------------------------
# Event endpoints
# ---------------------------------------------------------------------------


def _event_to_response(event: BaseEvent) -> EventResponse:
    return EventResponse(
        id=event.id,
        type=event.type,
        timestamp=event.timestamp,
        source=event.source,
        subject_id=event.subject_id,
        object_ids=list(event.object_ids),
        payload=event.payload,
        metadata=event.metadata,
    )


@app.get("/api/v1/events", response_model=EventListResponse, tags=["Events"])
async def list_events(
    limit: int = Query(50, ge=1, le=500),
    svc: EventService = Depends(get_event_service),
) -> EventListResponse:
    """List recent events across all entities."""
    events = await svc.get_recent_events(limit=limit)
    return EventListResponse(
        events=[_event_to_response(e) for e in events],
        total=len(events),
    )


@app.get("/api/v1/entities/{entity_id}/events", response_model=EventListResponse, tags=["Events"])
async def get_entity_events(
    entity_id: UUID,
    svc: EventService = Depends(get_event_service),
) -> EventListResponse:
    """Get the full event history for a specific entity (replay)."""
    events = await svc.replay_entity(entity_id)
    return EventListResponse(
        events=[_event_to_response(e) for e in events],
        total=len(events),
    )


@app.get("/api/v1/entities/{entity_id}/replay", response_model=EventListResponse, tags=["Events"])
async def replay_entity(
    entity_id: UUID,
    svc: EventService = Depends(get_event_service),
) -> EventListResponse:
    """Replay all events for an entity in chronological order.
    Useful for reconstructing entity state from event history.
    """
    events = await svc.replay_entity(entity_id)
    return EventListResponse(
        events=[_event_to_response(e) for e in events],
        total=len(events),
    )


# ---------------------------------------------------------------------------
# Agent / Research
# ---------------------------------------------------------------------------


@app.post("/api/v1/agent/research", response_model=AgentQueryResponse, tags=["Agent"])
async def agent_research(
    payload: AgentQueryRequest,
) -> AgentQueryResponse:
    """Run a research agent query against the knowledge graph.

    The ResearchAgent searches entities, applies deductive rules,
    and uses LLM-powered reasoning (inductive + abductive) to
    produce a structured answer.
    """
    agent = ResearchAgent()
    task = AgentTask(
        agent_type="research",
        query=payload.query,
        context={
            "entity_type": payload.entity_type,
            "search_limit": payload.search_limit,
        },
    )
    result = await agent.execute(task)
    return AgentQueryResponse(
        task_id=str(result.task_id),
        agent_type=result.agent_type,
        output=result.output,
        confidence=result.confidence,
        execution_time_ms=result.execution_time_ms,
    )


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


@app.post("/api/v1/query", response_model=QueryResponse, tags=["Query"])
async def query(
    payload: QueryRequest,
    svc: EventService = Depends(get_event_service),
) -> QueryResponse:
    """Query the knowledge graph."""
    import time

    start = time.monotonic()
    results = await svc.search_entities(payload.query, params=payload.params, limit=payload.limit, offset=payload.offset)
    total = len(results)
    elapsed = (time.monotonic() - start) * 1000
    return QueryResponse(
        results=[e.model_dump(mode="json") for e in results],
        total=total,
        query_time_ms=round(elapsed, 2),
    )
