"""Awren Core API — FastAPI Application."""

import json as _json
import logging
import time as _time
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from awren_core.database import create_session, init_db
from awren_core.llm import LLMProvider
from awren_core.models import BaseEntity, BaseEvent, BaseRelationship
from awren_agents.base import AgentTask
from awren_agents.research_agent import ResearchAgent
from awren_core.schemas import (
    AgentQueryRequest,
    AgentQueryResponse,
    ChunkRequest,
    ChunkResponse,
    ChatRequest,
    ChatResponse,
    ConversationListResponse,
    ConversationResponse,
    EntityCreate,
    EntityListResponse,
    EntityResponse,
    EntityUpdate,
    EventListResponse,
    EventResponse,
    ImportJobListResponse,
    ImportJobResponse,
    ImportProcessResponse,
    LLMProviderInfo,
    LLMSettingsResponse,
    LLMSettingsUpdate,
    MessageResponse,
    OCRResponse,
    OntologyPropertyDef,
    OntologyTypeDef,
    RelationshipCreate,
    RelationshipListResponse,
    RelationshipResponse,
    QueryRequest,
    QueryResponse,
    StateTransitionRequest,
    SummarizeRequest,
    SynthesizeRequest,
    SystemStatsResponse,
    TranscriptionListResponse,
    TranscriptionResponse,
    VersionHistoryResponse,
    VoiceChatResponse,
)
from awren_core.audio.engine import AudioEngine, is_supported_audio
from awren_core.auth import (
    create_access_token, get_current_user, get_optional_user,
    hash_password, require_permission, require_role, seed_roles_and_permissions,
    verify_password,
)
from awren_core.causality import CausalEngine
from awren_core.explainability import ExplainabilityEngine, Explanation
from awren_core.knowledge import KnowledgeEngine
from awren_core.ontology.engine import OntologyEngine
from awren_core.orm_models import (
    AudioTranscriptionModel, ImportJobModel, KnowledgeNodeModel,
    KnowledgeEdgeModel, CausalChainModel, UserModel,
)
from awren_core.schemas import (
    APIKeyGenerateRequest,
    APIKeyResponse,
    AgentQueryRequest,
    AgentQueryResponse,
    CausalAnalysisRequest,
    CausalChainResponse,
    CausalPathRequest,
    ChunkRequest,
    ChunkResponse,
    ChatRequest,
    ChatResponse,
    ConversationListResponse,
    ConversationResponse,
    EntityCreate,
    EntityListResponse,
    EntityResponse,
    EntityUpdate,
    EventListResponse,
    EventResponse,
    ExplanationResponse,
    ImportJobListResponse,
    ImportJobResponse,
    ImportProcessResponse,
    KnowledgeEdgeCreate,
    KnowledgeEdgeResponse,
    KnowledgeExtractRequest,
    KnowledgeNodeCreate,
    KnowledgeNodeResponse,
    KnowledgeStatsResponse,
    LLMProviderInfo,
    LLMSettingsResponse,
    LLMSettingsUpdate,
    MessageResponse,
    OCRResponse,
    OntologyPropertyDef,
    OntologyTypeDef,
    RelationshipCreate,
    RelationshipListResponse,
    RelationshipResponse,
    QueryRequest,
    QueryResponse,
    StateTransitionRequest,
    SummarizeRequest,
    SynthesizeRequest,
    SystemStatsResponse,
    TokenResponse,
    TranscriptionListResponse,
    TranscriptionResponse,
    UserLogin,
    UserRegister,
    UserResponse,
    VersionHistoryResponse,
    VoiceChatResponse,
)
from awren_core.services import EventService
from awren_ingestion.compression import chunk_text, summarize_text
from awren_ingestion.ocr import is_image_file, ocr_image
from awren_ingestion.processors import DocumentProcessor, is_allowed_file, save_upload
from apps.dashboard.main import router as dashboard_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[Any, None]:
    """Initialize database and seed ontology types on startup."""
    logger.info("Awren Core API starting up...")
    try:
        init_db()
        logger.info("Database tables initialized.")
        # Run migrations for new columns/tables
        session = create_session()
        try:
            for migration in _MIGRATIONS:
                try:
                    session.execute(sa_text(migration))
                except Exception:
                    pass  # Column/table already exists
            session.commit()
            logger.info("Schema migrations applied.")
        except Exception as e:
            logger.warning("Migration note: %s", e)
        finally:
            session.close()
        # Seed default ontology types
        try:
            session = create_session()
            engine = OntologyEngine(session)
            created = await engine.seed_default_types()
            session.commit()
            if created:
                logger.info("Seeded ontology types: %s", ", ".join(created))
            else:
                logger.info("Ontology types already seeded.")
        except Exception as e:
            logger.warning("Ontology seed skipped: %s", e)
        finally:
            session.close()
        # Seed roles and permissions
        try:
            session = create_session()
            from awren_core.auth import seed_roles_and_permissions
            seed_roles_and_permissions(session)
            logger.info("Roles and permissions seeded.")
        except Exception as e:
            logger.warning("Role seed skipped: %s", e)
        finally:
            session.close()
    except Exception as e:
        logger.warning("Database initialization skipped (not available): %s", e)
    yield
    logger.info("Awren Core API shutting down...")


_MIGRATIONS = [
    # Add columns to entities table
    "ALTER TABLE entities ADD COLUMN IF NOT EXISTS state VARCHAR(100)",
    "ALTER TABLE entities ADD COLUMN IF NOT EXISTS version_num INTEGER DEFAULT 1",
    "ALTER TABLE entities ADD COLUMN IF NOT EXISTS provenance JSONB",
    # Add columns to relationships table
    "ALTER TABLE relationships ADD COLUMN IF NOT EXISTS confidence FLOAT DEFAULT 1.0",
    "ALTER TABLE relationships ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ DEFAULT NOW()",
    "ALTER TABLE relationships ADD COLUMN IF NOT EXISTS valid_to TIMESTAMPTZ",
    # Entity versions table
    "CREATE TABLE IF NOT EXISTS entity_versions (id UUID PRIMARY KEY, entity_id UUID NOT NULL, version_num INTEGER NOT NULL, snapshot JSONB NOT NULL, change_description TEXT, created_at TIMESTAMPTZ DEFAULT NOW())",
    "CREATE INDEX IF NOT EXISTS ix_entity_versions_entity_id ON entity_versions(entity_id)",
    # Ontology types table
    "CREATE TABLE IF NOT EXISTS ontology_types (id UUID PRIMARY KEY, name VARCHAR(255) UNIQUE NOT NULL, description TEXT, base_type VARCHAR(255), states JSONB DEFAULT '[\"active\"]', config JSONB DEFAULT '{}', created_at TIMESTAMPTZ DEFAULT NOW())",
    # Ontology properties table
    "CREATE TABLE IF NOT EXISTS ontology_properties (id UUID PRIMARY KEY, type_id UUID NOT NULL, name VARCHAR(255) NOT NULL, property_type VARCHAR(50) DEFAULT 'string', kind VARCHAR(20) DEFAULT 'static', required BOOLEAN DEFAULT FALSE, default_value TEXT, formula TEXT, config JSONB DEFAULT '{}', ordinal INTEGER DEFAULT 0, created_at TIMESTAMPTZ DEFAULT NOW())",
    "CREATE INDEX IF NOT EXISTS ix_ontology_properties_type_id ON ontology_properties(type_id)",
    # Import jobs table
    "CREATE TABLE IF NOT EXISTS import_jobs (id UUID PRIMARY KEY, original_filename VARCHAR(500) NOT NULL, file_path TEXT NOT NULL, file_size INTEGER DEFAULT 0, mime_type VARCHAR(200), status VARCHAR(50) DEFAULT 'pending', total_entities INTEGER DEFAULT 0, total_relationships INTEGER DEFAULT 0, error_messages JSONB DEFAULT '[]', result_summary JSONB, created_at TIMESTAMPTZ DEFAULT NOW(), completed_at TIMESTAMPTZ)",
    "CREATE INDEX IF NOT EXISTS ix_import_jobs_status ON import_jobs(status)",
    # Audio transcriptions table
    "CREATE TABLE IF NOT EXISTS audio_transcriptions (id UUID PRIMARY KEY, original_filename VARCHAR(500) NOT NULL, file_size INTEGER DEFAULT 0, duration_seconds FLOAT DEFAULT 0.0, transcription_text TEXT NOT NULL, language VARCHAR(20) DEFAULT 'unknown', metadata JSONB, created_at TIMESTAMPTZ DEFAULT NOW())",
    # Users table
    "CREATE TABLE IF NOT EXISTS users (id UUID PRIMARY KEY, username VARCHAR(100) UNIQUE NOT NULL, email VARCHAR(255) UNIQUE NOT NULL, hashed_password VARCHAR(200) NOT NULL, role VARCHAR(50) DEFAULT 'viewer', is_active BOOLEAN DEFAULT TRUE, api_key_hash VARCHAR(200) UNIQUE, api_key_expires_at TIMESTAMPTZ, created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW())",
    "CREATE INDEX IF NOT EXISTS ix_users_username ON users(username)",
    "CREATE INDEX IF NOT EXISTS ix_users_role ON users(role)",
    # Roles table
    "CREATE TABLE IF NOT EXISTS roles (id UUID PRIMARY KEY, name VARCHAR(50) UNIQUE NOT NULL, description TEXT, created_at TIMESTAMPTZ DEFAULT NOW())",
    "CREATE INDEX IF NOT EXISTS ix_roles_name ON roles(name)",
    # Permissions table
    "CREATE TABLE IF NOT EXISTS permissions (id UUID PRIMARY KEY, role VARCHAR(50) NOT NULL, resource VARCHAR(100) NOT NULL, action VARCHAR(50) NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW())",
    "CREATE INDEX IF NOT EXISTS ix_permissions_role ON permissions(role)",
    # Knowledge nodes table
    "CREATE TABLE IF NOT EXISTS knowledge_nodes (id UUID PRIMARY KEY, kind VARCHAR(50) NOT NULL, label VARCHAR(500) NOT NULL, content TEXT NOT NULL, source VARCHAR(100) DEFAULT 'system', confidence FLOAT DEFAULT 1.0, tags JSONB DEFAULT '[]', metadata JSONB DEFAULT '{}', entity_ids JSONB DEFAULT '[]', created_at TIMESTAMPTZ DEFAULT NOW())",
    "CREATE INDEX IF NOT EXISTS ix_knowledge_nodes_kind ON knowledge_nodes(kind)",
    # Knowledge edges table
    "CREATE TABLE IF NOT EXISTS knowledge_edges (id UUID PRIMARY KEY, source_id UUID NOT NULL, target_id UUID NOT NULL, relationship_type VARCHAR(100) DEFAULT 'derives_from', confidence FLOAT DEFAULT 1.0, metadata JSONB DEFAULT '{}', created_at TIMESTAMPTZ DEFAULT NOW())",
    "CREATE INDEX IF NOT EXISTS ix_knowledge_edges_source ON knowledge_edges(source_id)",
    "CREATE INDEX IF NOT EXISTS ix_knowledge_edges_target ON knowledge_edges(target_id)",
    # Causal chains table
    "CREATE TABLE IF NOT EXISTS causal_chains (id UUID PRIMARY KEY, head_id UUID NOT NULL, chain JSONB NOT NULL, confidence FLOAT DEFAULT 1.0, source VARCHAR(100) DEFAULT 'system', metadata JSONB DEFAULT '{}', created_at TIMESTAMPTZ DEFAULT NOW())",
    "CREATE INDEX IF NOT EXISTS ix_causal_chains_head ON causal_chains(head_id)",
]


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
        session.commit()
    except Exception:
        session.rollback()
        raise
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
# Authentication
# ---------------------------------------------------------------------------


@app.post("/api/v1/auth/register", response_model=TokenResponse, tags=["Auth"])
async def register(
    payload: UserRegister,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Register a new user account."""
    existing = db.query(UserModel).filter(
        (UserModel.username == payload.username) | (UserModel.email == payload.email)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Username or email already exists")
    user = UserModel(
        id=uuid4(),
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role="viewer",
        is_active=True,
    )
    db.add(user)
    db.flush()
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return TokenResponse(
        access_token=token,
        user_id=str(user.id),
        username=user.username,
        role=user.role,
    )


@app.post("/api/v1/auth/login", response_model=TokenResponse, tags=["Auth"])
async def login(
    payload: UserLogin,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Authenticate and receive a JWT token."""
    user = db.query(UserModel).filter(UserModel.username == payload.username).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return TokenResponse(
        access_token=token,
        user_id=str(user.id),
        username=user.username,
        role=user.role,
    )


@app.get("/api/v1/auth/me", response_model=UserResponse, tags=["Auth"])
async def get_me(
    current_user: UserModel = Depends(get_current_user),
) -> UserResponse:
    """Get the currently authenticated user's profile."""
    return UserResponse(
        id=str(current_user.id),
        username=current_user.username,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
        created_at=current_user.created_at.isoformat() if current_user.created_at else None,
    )


@app.post("/api/v1/auth/api-key", response_model=APIKeyResponse, tags=["Auth"])
async def generate_api_key(
    payload: APIKeyGenerateRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> APIKeyResponse:
    """Generate a new API key for the authenticated user."""
    import secrets
    import hashlib
    from datetime import timedelta
    user = db.merge(current_user)
    api_key = f"awr_{secrets.token_hex(24)}"
    user.api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    if payload.expires_days:
        user.api_key_expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_days)
    db.flush()
    return APIKeyResponse(
        api_key=api_key,
        key_preview=api_key[:12] + "...",
        expires_at=user.api_key_expires_at.isoformat() if user.api_key_expires_at else None,
    )


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
        state=entity.state,
        version_num=entity.version_num,
        provenance=entity.provenance,
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
        state=payload.state,
        provenance=payload.provenance,
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


# ---------------------------------------------------------------------------
# Relationship CRUD
# ---------------------------------------------------------------------------


def _rel_to_response(rel: BaseRelationship) -> RelationshipResponse:
    return RelationshipResponse(
        id=rel.id,
        type=rel.type,
        source_id=rel.source_id,
        target_id=rel.target_id,
        properties=rel.properties,
        metadata=rel.metadata,
    )


@app.post("/api/v1/relationships", response_model=RelationshipResponse, status_code=201, tags=["Relationships"])
async def create_relationship(
    payload: RelationshipCreate,
    svc: EventService = Depends(get_event_service),
) -> RelationshipResponse:
    """Create a relationship between two entities."""
    rel = BaseRelationship(
        type=payload.type,
        source_id=payload.source_id,
        target_id=payload.target_id,
        properties=payload.properties,
        metadata={"confidence": payload.confidence, "created_by": "api"},
    )
    created = await svc.create_relationship(rel)
    return _rel_to_response(created)


@app.get("/api/v1/relationships", response_model=RelationshipListResponse, tags=["Relationships"])
async def list_relationships(
    source_id: Optional[UUID] = Query(None),
    target_id: Optional[UUID] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    svc: EventService = Depends(get_event_service),
) -> RelationshipListResponse:
    """List relationships, optionally filtered by source or target entity."""
    rels = await svc.list_relationships(source_id=source_id, target_id=target_id, limit=limit)
    return RelationshipListResponse(
        relationships=[_rel_to_response(r) for r in rels],
        total=len(rels),
    )


@app.delete("/api/v1/relationships/{rel_id}", status_code=204, tags=["Relationships"])
async def delete_relationship(
    rel_id: UUID,
    svc: EventService = Depends(get_event_service),
) -> None:
    """Delete a relationship by ID (event is recorded)."""
    await svc.delete_relationship(rel_id)


# ---------------------------------------------------------------------------
# Chat / Company Brain
# ---------------------------------------------------------------------------


@app.post("/api/v1/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(
    payload: ChatRequest,
    svc: EventService = Depends(get_event_service),
) -> ChatResponse:
    """Chat with the Company Brain — persistent, with action execution."""
    result = await svc.chat(
        message=payload.message,
        conversation_id=payload.conversation_id,
        provider=payload.provider,
        model=payload.model,
        temperature=payload.temperature,
    )

    # Build explainability layer
    explainer = ExplainabilityEngine(svc._session)
    explanation = await explainer.explain_chat_response(
        reply=result["reply"],
        entities_used=result.get("entities_referenced", []),
        actions_taken=result.get("actions_taken", []),
        confidence=result["confidence"],
        model_used=result.get("model", "unknown"),
        provider=result.get("provider", "unknown"),
    )

    return ChatResponse(
        reply=result["reply"],
        conversation_id=result["conversation_id"],
        provider=result["provider"],
        model=result["model"],
        confidence=result["confidence"],
        entities_referenced=result["entities_referenced"],
        execution_time_ms=result["execution_time_ms"],
        actions_taken=result.get("actions_taken", []),
        # Inject explanation into response metadata
        metadata={"explanation": explanation.to_dict()},
    )


@app.get("/api/v1/conversations", response_model=ConversationListResponse, tags=["Chat"])
async def list_conversations(
    svc: EventService = Depends(get_event_service),
) -> ConversationListResponse:
    """List all conversations."""
    convs = await svc.get_conversations()
    return ConversationListResponse(
        conversations=[ConversationResponse(**c) for c in convs],
        total=len(convs),
    )


@app.get("/api/v1/conversations/{conv_id}/messages", tags=["Chat"])
async def get_conversation_messages(
    conv_id: UUID,
    svc: EventService = Depends(get_event_service),
) -> list[MessageResponse]:
    """Get all messages for a conversation."""
    msgs = await svc.get_conversation_messages(conv_id)
    return [MessageResponse(**m) for m in msgs]


@app.delete("/api/v1/conversations/{conv_id}", status_code=204, tags=["Chat"])
async def delete_conversation(
    conv_id: UUID,
    svc: EventService = Depends(get_event_service),
) -> None:
    """Delete a conversation."""
    await svc.delete_conversation(conv_id)


@app.get("/api/v1/chat/stream/{conv_id}", tags=["Chat"])
async def chat_stream_sse(
    conv_id: str,
    message: str,
    svc: EventService = Depends(get_event_service),
):
    """SSE streaming chat endpoint with explainability."""
    from fastapi.responses import StreamingResponse

    async def event_stream():
        conv_id_str, msg_history = await svc.ensure_conversation(conv_id)
        yield f"data: {{\"type\":\"meta\",\"conversation_id\":\"{conv_id_str}\"}}\n\n"

        await svc._msg_repo.create(UUID(conv_id_str), "user", message)
        system_prompt = svc._build_system_prompt(message, msg_history)
        llm = create_llm_client(db_session=svc._session)
        if llm:
            full_reply = ""
            try:
                for chunk in llm.chat_stream(
                    system_prompt=system_prompt,
                    user_prompt=message,
                    temperature=0.7,
                    max_tokens=4096,
                ):
                    full_reply += chunk
                    yield f"data: {{\"type\":\"chunk\",\"content\":{_json.dumps(chunk)}}}\n\n"
            except Exception as e:
                yield f"data: {{\"type\":\"error\",\"content\":{_json.dumps(str(e))}}}\n\n"
            else:
                clean_reply, actions = await svc._parse_actions(full_reply)
                action_results = []
                if actions:
                    for cmd in actions:
                        result = await svc._execute_action(cmd)
                        action_results.append(result)
                    success_msgs = [a["message"] for a in action_results if a["success"]]
                    if success_msgs:
                        clean_reply += "\n\n" + "\n".join(success_msgs)

                await svc._msg_repo.create(
                    UUID(conv_id_str), "assistant", clean_reply,
                    metadata={"actions": action_results} if action_results else None,
                )

                if len(msg_history) <= 1:
                    title = message[:80] + ("..." if len(message) > 80 else "")
                    await svc._conv_repo.update_title(UUID(conv_id_str), title)

                # Build explainability layer
                explainer = ExplainabilityEngine(svc._session)
                explanation = await explainer.explain_chat_response(
                    reply=clean_reply,
                    actions_taken=action_results,
                    confidence=0.85 if llm else 0.0,
                    model_used=getattr(llm, "model", "unknown"),
                    provider=getattr(llm, "model", "unknown"),
                )

                yield f"data: {{\"type\":\"explanation\",\"content\":{_json.dumps(explanation.to_dict())}}}\n\n"
                yield f"data: {{\"type\":\"done\",\"actions\":{_json.dumps(action_results)}}}\n\n"
        else:
            yield "data: {\"type\":\"error\",\"content\":\"No LLM configured\"}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# LLM Provider Settings
# ---------------------------------------------------------------------------


def _resolve_api_key(db_cfg: dict, env_settings: Any, provider: str) -> str:
    """Check DB first, then .env for API keys."""
    if provider == "anthropic":
        return db_cfg.get("anthropic_api_key") or env_settings.anthropic_api_key or ""
    return db_cfg.get("openai_api_key") or env_settings.openai_api_key or ""


def _build_providers(env: Any, db: dict) -> list[LLMProviderInfo]:
    return [
        LLMProviderInfo(id="openai", name="OpenAI",
            models=[{"id": "gpt-4o", "name": "GPT-4o"}, {"id": "gpt-4o-mini", "name": "GPT-4o Mini"}, {"id": "gpt-4-turbo", "name": "GPT-4 Turbo"}, {"id": "o3-mini", "name": "o3 Mini"}],
            has_api_key=bool(_resolve_api_key(db, env, "openai"))),
        LLMProviderInfo(id="anthropic", name="Anthropic",
            models=[{"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4"}, {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet"}, {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku"}],
            has_api_key=bool(_resolve_api_key(db, env, "anthropic"))),
        LLMProviderInfo(id="openrouter", name="OpenRouter",
            models=[{"id": "openai/gpt-4o", "name": "GPT-4o (OpenRouter)"}, {"id": "anthropic/claude-sonnet-4", "name": "Claude Sonnet 4 (OpenRouter)"}, {"id": "google/gemini-2.0-flash-001", "name": "Gemini 2.0 Flash"}, {"id": "meta-llama/llama-3.3-70b-instruct", "name": "Llama 3.3 70B"}],
            has_api_key=bool(_resolve_api_key(db, env, "openai"))),
        LLMProviderInfo(id="custom_openai", name="Custom OpenAI-compatible",
            models=[{"id": "custom", "name": "Custom Model"}],
            has_api_key=bool(_resolve_api_key(db, env, "openai"))),
    ]


@app.get("/api/v1/settings/llm", response_model=LLMSettingsResponse, tags=["Settings"])
async def get_llm_settings(
    svc: EventService = Depends(get_event_service),
) -> LLMSettingsResponse:
    """Get current LLM provider configuration and available options."""
    from awren_core.settings import get_settings
    env = get_settings()
    db = await svc.get_llm_settings()
    return LLMSettingsResponse(
        provider=db.get("provider", env.llm_provider),
        model=db.get("model", env.openai_model if env.llm_provider != "anthropic" else env.anthropic_model),
        openai_api_key_configured=bool(_resolve_api_key(db, env, "openai")),
        anthropic_api_key_configured=bool(_resolve_api_key(db, env, "anthropic")),
        available_providers=_build_providers(env, db),
    )


@app.put("/api/v1/settings/llm", response_model=LLMSettingsResponse, tags=["Settings"])
async def update_llm_settings(
    payload: LLMSettingsUpdate,
    svc: EventService = Depends(get_event_service),
) -> LLMSettingsResponse:
    """Update LLM provider, model, and API keys (persisted to DB)."""
    from awren_core.settings import get_settings
    env = get_settings()
    await svc.update_llm_settings(
        provider=payload.provider,
        model=payload.model,
        openai_api_key=payload.openai_api_key or "",
        anthropic_api_key=payload.anthropic_api_key or "",
    )
    db = await svc.get_llm_settings()
    return LLMSettingsResponse(
        provider=db.get("provider", env.llm_provider),
        model=db.get("model", env.openai_model if env.llm_provider != "anthropic" else env.anthropic_model),
        openai_api_key_configured=bool(_resolve_api_key(db, env, "openai")),
        anthropic_api_key_configured=bool(_resolve_api_key(db, env, "anthropic")),
        available_providers=_build_providers(env, db),
    )


# ---------------------------------------------------------------------------
# Ontology Type Registry
# ---------------------------------------------------------------------------


def _get_ontology_engine(db: Session = Depends(get_db)) -> OntologyEngine:
    return OntologyEngine(db)


@app.post("/api/v1/ontology/types", tags=["Ontology"])
async def register_ontology_type(
    payload: OntologyTypeDef,
    engine: OntologyEngine = Depends(_get_ontology_engine),
) -> dict:
    """Register a new ontology object type with property definitions."""
    try:
        type_model = await engine.register_type(
            name=payload.name,
            description=payload.description or "",
            base_type=payload.base_type,
            states=payload.states,
        )
        for prop in payload.properties:
            await engine.add_property(
                type_name=payload.name,
                name=prop["name"],
                property_type=prop.get("property_type", "string"),
                kind=prop.get("kind", "static"),
                required=prop.get("required", False),
                default_value=prop.get("default_value"),
                formula=prop.get("formula"),
                config=prop.get("config", {}),
            )
        return {"status": "created", "name": payload.name, "properties_count": len(payload.properties)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/v1/ontology/types", tags=["Ontology"])
async def list_ontology_types(
    engine: OntologyEngine = Depends(_get_ontology_engine),
) -> list[dict]:
    """List all registered ontology types with property counts."""
    return await engine.list_types()


@app.get("/api/v1/ontology/types/{type_name}", tags=["Ontology"])
async def get_ontology_type(
    type_name: str,
    engine: OntologyEngine = Depends(_get_ontology_engine),
) -> dict:
    """Get full definition of an ontology type including all properties."""
    type_def = await engine.get_type(type_name)
    if not type_def:
        raise HTTPException(status_code=404, detail=f"Type '{type_name}' not found")
    return type_def


@app.delete("/api/v1/ontology/types/{type_name}", tags=["Ontology"])
async def delete_ontology_type(
    type_name: str,
    engine: OntologyEngine = Depends(_get_ontology_engine),
) -> dict:
    """Delete an ontology type and its property definitions."""
    try:
        type_def = await engine._type_repo.get_by_name(type_name)
        if not type_def:
            raise HTTPException(status_code=404, detail=f"Type '{type_name}' not found")
        await engine._type_repo.delete(type_def.id)
        return {"status": "deleted", "name": type_name}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v1/ontology/types/{type_name}/properties", tags=["Ontology"])
async def add_ontology_property(
    type_name: str,
    payload: OntologyPropertyDef,
    engine: OntologyEngine = Depends(_get_ontology_engine),
) -> dict:
    """Add a property definition to an existing ontology type."""
    try:
        await engine.add_property(
            type_name=type_name,
            name=payload.name,
            property_type=payload.property_type,
            kind=payload.kind,
            required=payload.required,
            default_value=payload.default_value,
            formula=payload.formula,
            config=payload.config,
        )
        return {"status": "created", "type": type_name, "property": payload.name}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/v1/ontology/types/{type_name}/properties/{prop_name}", tags=["Ontology"])
async def remove_ontology_property(
    type_name: str,
    prop_name: str,
    engine: OntologyEngine = Depends(_get_ontology_engine),
) -> dict:
    """Remove a property definition from an ontology type."""
    try:
        await engine.remove_property(type_name, prop_name)
        return {"status": "deleted", "type": type_name, "property": prop_name}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------------------------------------------------------
# Entity Version History
# ---------------------------------------------------------------------------


@app.get("/api/v1/entities/{entity_id}/versions", tags=["Entities"])
async def get_entity_versions(
    entity_id: UUID,
    engine: OntologyEngine = Depends(_get_ontology_engine),
) -> list[VersionHistoryResponse]:
    """Get full version history for an entity."""
    versions = await engine.get_version_history(entity_id)
    return [VersionHistoryResponse(**v) for v in versions]


@app.get("/api/v1/entities/{entity_id}/versions/{version_num}", tags=["Entities"])
async def get_entity_version(
    entity_id: UUID,
    version_num: int,
    engine: OntologyEngine = Depends(_get_ontology_engine),
) -> VersionHistoryResponse:
    """Get a specific version snapshot of an entity."""
    version = await engine.get_version(entity_id, version_num)
    if not version:
        raise HTTPException(status_code=404, detail=f"Version {version_num} not found")
    return VersionHistoryResponse(**version)


# ---------------------------------------------------------------------------
# State Machine
# ---------------------------------------------------------------------------


@app.post("/api/v1/entities/{entity_id}/state", tags=["Entities"])
async def transition_entity_state(
    entity_id: UUID,
    payload: StateTransitionRequest,
    engine: OntologyEngine = Depends(_get_ontology_engine),
) -> dict:
    """Transition an entity to a new lifecycle state."""
    try:
        result = await engine.transition_state(
            entity_id=entity_id,
            new_state=payload.new_state,
            reason=payload.reason,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Import / Ingestion
# ---------------------------------------------------------------------------


@app.post("/api/v1/ingestion/upload", status_code=201, tags=["Ingestion"])
async def upload_file(
    file: Any = File(...),
    db: Session = Depends(get_db),
) -> ImportJobResponse:
    """Upload a file for ingestion into the knowledge graph.
    
    Supported formats: PDF, DOCX, CSV, JSON, TXT, MD.
    The file is saved and queued for processing.
    Returns an ImportJob with status 'pending'.
    """
    if not is_allowed_file(file.filename):
        raise HTTPException(
            status_code=400,
            detail=f"File type '{file.filename.split('.')[-1]}' not supported. "
                   f"Supported: PDF, DOCX, CSV, JSON, TXT, MD",
        )

    content = await file.read()
    file_path = save_upload(content, file.filename)

    import_job = ImportJobModel(
        id=uuid4(),
        original_filename=file.filename,
        file_path=file_path,
        file_size=len(content),
        mime_type=file.content_type or "application/octet-stream",
        status="pending",
        error_messages=[],
    )
    db.add(import_job)
    db.flush()

    return ImportJobResponse(
        id=import_job.id,
        original_filename=import_job.original_filename,
        file_size=import_job.file_size,
        mime_type=import_job.mime_type,
        status=import_job.status,
        total_entities=0,
        total_relationships=0,
        error_messages=[],
        created_at=import_job.created_at,
    )


@app.get("/api/v1/ingestion/jobs", tags=["Ingestion"])
async def list_import_jobs(
    status: Optional[str] = Query(None, description="Filter by status (pending, processing, completed, failed)"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> ImportJobListResponse:
    """List all import jobs, optionally filtered by status."""
    from sqlalchemy import select
    stmt = select(ImportJobModel).order_by(ImportJobModel.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(ImportJobModel.status == status)
    results = list(db.execute(stmt).scalars().all())
    return ImportJobListResponse(
        jobs=[_import_job_to_response(j) for j in results],
        total=len(results),
    )


@app.get("/api/v1/ingestion/jobs/{job_id}", tags=["Ingestion"])
async def get_import_job(
    job_id: UUID,
    db: Session = Depends(get_db),
) -> ImportJobResponse:
    """Get the status and results of an import job."""
    from sqlalchemy import select
    stmt = select(ImportJobModel).where(ImportJobModel.id == job_id)
    job = db.execute(stmt).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")
    return _import_job_to_response(job)


@app.post("/api/v1/ingestion/jobs/{job_id}/process", tags=["Ingestion"])
async def process_import_job(
    job_id: UUID,
    db: Session = Depends(get_db),
) -> ImportProcessResponse:
    """Process a pending import job: extract text, identify entities via LLM, create in ontology."""
    from sqlalchemy import select
    stmt = select(ImportJobModel).where(ImportJobModel.id == job_id)
    job = db.execute(stmt).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")
    if job.status != "pending":
        raise HTTPException(status_code=400, detail=f"Job already {job.status}")

    start = _time.monotonic()
    job.status = "processing"
    db.flush()

    processor = DocumentProcessor(db)
    result = await processor.process(
        job_id=job.id,
        file_path=job.file_path,
        original_filename=job.original_filename,
    )

    job.status = "completed" if not result["errors"] else "completed_with_errors"
    job.total_entities = result["entities_created"]
    job.total_relationships = result["relationships_created"]
    job.error_messages = result["errors"]
    job.result_summary = result
    job.completed_at = datetime.now(timezone.utc)
    db.flush()

    elapsed = (_time.monotonic() - start) * 1000
    return ImportProcessResponse(
        status=job.status,
        job_id=str(job.id),
        entities_created=result["entities_created"],
        relationships_created=result["relationships_created"],
        errors=result["errors"],
        elapsed_ms=round(elapsed, 2),
    )


def _import_job_to_response(job: ImportJobModel) -> ImportJobResponse:
    return ImportJobResponse(
        id=job.id,
        original_filename=job.original_filename,
        file_size=job.file_size,
        mime_type=job.mime_type,
        status=job.status,
        total_entities=job.total_entities,
        total_relationships=job.total_relationships,
        error_messages=job.error_messages or [],
        result_summary=job.result_summary,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


# ---------------------------------------------------------------------------
# System Monitoring / Stats
# ---------------------------------------------------------------------------


@app.get("/api/v1/system/stats", response_model=SystemStatsResponse, tags=["System"])
async def system_stats(
    db: Session = Depends(get_db),
) -> SystemStatsResponse:
    """Get comprehensive system statistics for monitoring dashboard.
    
    Returns counts of entities, relationships, events, conversations, imports;
    breakdown by entity type; import status summary; recent activity; LLM config.
    """
    from sqlalchemy import func, select, text
    from awren_core.orm_models import (
        ConversationModel,
        EntityModel,
        EventModel,
        RelationshipModel,
    )

    # Counts
    total_entities = db.execute(select(func.count(EntityModel.id))).scalar() or 0
    total_relationships = db.execute(select(func.count(RelationshipModel.id))).scalar() or 0
    total_events = db.execute(select(func.count(EventModel.id))).scalar() or 0
    total_conversations = db.execute(select(func.count(ConversationModel.id))).scalar() or 0
    total_imports = db.execute(select(func.count(ImportJobModel.id))).scalar() or 0
    total_transcriptions = db.execute(select(func.count(AudioTranscriptionModel.id))).scalar() or 0

    # Entities by type
    type_counts = db.execute(
        select(EntityModel.type, func.count(EntityModel.id).label("count"))
        .group_by(EntityModel.type)
        .order_by(text("count DESC"))
    ).all()
    entities_by_type = [{"type": row[0], "count": row[1]} for row in type_counts]

    # Imports by status
    status_counts = db.execute(
        select(ImportJobModel.status, func.count(ImportJobModel.id).label("count"))
        .group_by(ImportJobModel.status)
    ).all()
    imports_by_status = {row[0]: row[1] for row in status_counts} if status_counts else {}

    # Recent activity (last 10 events)
    recent_events = db.execute(
        select(EventModel)
        .order_by(EventModel.timestamp.desc())
        .limit(10)
    ).scalars().all()
    recent_activity = [
        {
            "type": e.type,
            "subject_id": str(e.subject_id),
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            "source": e.source,
        }
        for e in recent_events
    ]

    # LLM config
    llm_settings = await _get_llm_settings(db)

    # Uptime
    start_time = _uptime_start.get("time", _time.time())
    uptime_hours = (_time.time() - start_time) / 3600

    # Knowledge graph layer stats
    total_knowledge_nodes = db.execute(
        select(func.count(KnowledgeNodeModel.id))
    ).scalar() or 0
    knowledge_by_kind = db.execute(
        select(KnowledgeNodeModel.kind, func.count(KnowledgeNodeModel.id).label("count"))
        .group_by(KnowledgeNodeModel.kind)
    ).all()
    knowledge_by_kind_dict = {row[0]: row[1] for row in knowledge_by_kind}

    # Causal chains count
    total_causal_chains = db.execute(
        select(func.count(CausalChainModel.id))
    ).scalar() or 0

    # User counts
    total_users = db.execute(
        select(func.count(UserModel.id))
    ).scalar() or 0

    return SystemStatsResponse(
        total_entities=total_entities,
        total_relationships=total_relationships,
        total_events=total_events,
        total_conversations=total_conversations,
        total_imports=total_imports,
        total_transcriptions=total_transcriptions,
        entities_by_type=entities_by_type,
        imports_by_status=imports_by_status,
        recent_activity=recent_activity,
        llm_provider=llm_settings.get("provider", "unknown"),
        llm_model=llm_settings.get("model", "unknown"),
        uptime_hours=round(uptime_hours, 2),
        # New fields for new layers
        total_users=total_users,
        total_knowledge_nodes=total_knowledge_nodes,
        knowledge_by_kind=knowledge_by_kind_dict,
        total_causal_chains=total_causal_chains,
    )


_uptime_start: dict = {"time": _time.time()}


async def _get_llm_settings(db: Session) -> dict:
    """Get current LLM settings from DB."""
    from awren_core.repositories import LlmSettingsRepository
    repo = LlmSettingsRepository(db)
    try:
        return await repo.get()
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Knowledge Graph Layer — Insights, Rules, Patterns
# ---------------------------------------------------------------------------


def _get_knowledge_engine(db: Session = Depends(get_db)) -> KnowledgeEngine:
    return KnowledgeEngine(db)


@app.post("/api/v1/knowledge/nodes", tags=["Knowledge"])
async def create_knowledge_node(
    payload: KnowledgeNodeCreate,
    engine: KnowledgeEngine = Depends(_get_knowledge_engine),
) -> KnowledgeNodeResponse:
    """Create a knowledge node (insight, rule, or pattern)."""
    node = await engine.create_node(
        kind=payload.kind,
        label=payload.label,
        content=payload.content,
        source=payload.source,
        confidence=payload.confidence,
        tags=payload.tags,
        metadata=payload.metadata,
        entity_ids=[UUID(eid) for eid in payload.entity_ids],
    )
    return KnowledgeNodeResponse(**node)


@app.get("/api/v1/knowledge/nodes", tags=["Knowledge"])
async def list_knowledge_nodes(
    kind: Optional[str] = Query(None, description="Filter by kind: insight, rule, pattern"),
    source: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    engine: KnowledgeEngine = Depends(_get_knowledge_engine),
) -> dict[str, Any]:
    """List knowledge nodes with optional filters."""
    nodes = await engine.list_nodes(kind=kind, source=source, tag=tag, limit=limit, offset=offset)
    total = await engine.count_nodes(kind=kind)
    return {"nodes": [KnowledgeNodeResponse(**n) for n in nodes], "total": total}


@app.get("/api/v1/knowledge/nodes/{node_id}", tags=["Knowledge"])
async def get_knowledge_node(
    node_id: UUID,
    engine: KnowledgeEngine = Depends(_get_knowledge_engine),
) -> KnowledgeNodeResponse:
    """Get a specific knowledge node by ID."""
    node = await engine.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Knowledge node not found")
    return KnowledgeNodeResponse(**node)


@app.delete("/api/v1/knowledge/nodes/{node_id}", tags=["Knowledge"])
async def delete_knowledge_node(
    node_id: UUID,
    engine: KnowledgeEngine = Depends(_get_knowledge_engine),
) -> dict[str, str]:
    """Delete a knowledge node."""
    deleted = await engine.delete_node(node_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Knowledge node not found")
    return {"status": "deleted"}


@app.post("/api/v1/knowledge/edges", tags=["Knowledge"])
async def create_knowledge_edge(
    payload: KnowledgeEdgeCreate,
    engine: KnowledgeEngine = Depends(_get_knowledge_engine),
) -> KnowledgeEdgeResponse:
    """Create a connection between two knowledge nodes or to entities."""
    edge = await engine.create_edge(
        source_id=UUID(payload.source_id),
        target_id=UUID(payload.target_id),
        relationship_type=payload.relationship_type,
        confidence=payload.confidence,
        metadata=payload.metadata,
    )
    return KnowledgeEdgeResponse(**edge)


@app.get("/api/v1/knowledge/nodes/{node_id}/edges", tags=["Knowledge"])
async def get_knowledge_edges(
    node_id: UUID,
    engine: KnowledgeEngine = Depends(_get_knowledge_engine),
) -> list[KnowledgeEdgeResponse]:
    """Get all edges connected to a knowledge node."""
    edges = await engine.get_edges_for_node(node_id)
    return [KnowledgeEdgeResponse(**e) for e in edges]


@app.post("/api/v1/knowledge/extract", tags=["Knowledge"])
async def extract_knowledge(
    payload: KnowledgeExtractRequest,
    engine: KnowledgeEngine = Depends(_get_knowledge_engine),
) -> dict[str, Any]:
    """Extract insights, rules, and patterns from text using LLM."""
    nodes = await engine.extract_insights_from_text(
        text=payload.text,
        source=payload.source,
    )
    return {
        "extracted": len(nodes),
        "nodes": [KnowledgeNodeResponse(**n) for n in nodes],
    }


@app.get("/api/v1/knowledge/stats", tags=["Knowledge"])
async def knowledge_stats(
    engine: KnowledgeEngine = Depends(_get_knowledge_engine),
) -> KnowledgeStatsResponse:
    """Get statistics about the knowledge graph layer."""
    stats = await engine.get_stats()
    return KnowledgeStatsResponse(**stats)


@app.post("/api/v1/knowledge/query", tags=["Knowledge"])
async def knowledge_query(
    query: str,
    kind: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    engine: KnowledgeEngine = Depends(_get_knowledge_engine),
) -> dict[str, Any]:
    """Query knowledge nodes by content relevance."""
    kinds = [kind] if kind else None
    nodes = await engine.query_knowledge(query=query, kinds=kinds, limit=limit)
    return {
        "query": query,
        "results": [KnowledgeNodeResponse(**n) for n in nodes],
        "total": len(nodes),
    }


# ---------------------------------------------------------------------------
# Causal Reasoning — Multi-hop Causal Chains
# ---------------------------------------------------------------------------


def _get_causal_engine(db: Session = Depends(get_db)) -> CausalEngine:
    return CausalEngine(db)


@app.post("/api/v1/causal/forward", tags=["Causal"])
async def causal_forward_chain(
    payload: CausalAnalysisRequest,
    engine: CausalEngine = Depends(_get_causal_engine),
) -> dict[str, Any]:
    """Forward causal chaining — what does this entity cause?

    Traverses 'causes', 'enables', 'triggers', 'leads_to' relationships.
    """
    entity_id = UUID(payload.entity_id)
    chains = await engine.forward_chain(
        entity_id=entity_id,
        max_hops=payload.max_hops,
        min_confidence=payload.min_confidence,
    )
    return {
        "entity_id": payload.entity_id,
        "method": "forward_chain",
        "chains": chains,
        "total": len(chains),
    }


@app.post("/api/v1/causal/backward", tags=["Causal"])
async def causal_backward_chain(
    payload: CausalAnalysisRequest,
    engine: CausalEngine = Depends(_get_causal_engine),
) -> dict[str, Any]:
    """Backward causal chaining — what causes this entity?

    Traces root causes by following reverse causal relationships.
    """
    entity_id = UUID(payload.entity_id)
    chains = await engine.backward_chain(
        entity_id=entity_id,
        max_hops=payload.max_hops,
        min_confidence=payload.min_confidence,
    )
    return {
        "entity_id": payload.entity_id,
        "method": "backward_chain",
        "chains": chains,
        "total": len(chains),
    }


@app.post("/api/v1/causal/analyze", tags=["Causal"])
async def causal_llm_analysis(
    payload: CausalAnalysisRequest,
    engine: CausalEngine = Depends(_get_causal_engine),
) -> dict[str, Any]:
    """LLM-powered causal analysis — infer causal relationships from entity data.

    Uses the LLM to suggest causal chains not explicitly stored in the graph.
    """
    entity_id = UUID(payload.entity_id)
    chains = await engine.llm_causal_analysis(
        entity_id=entity_id,
        max_chains=payload.max_hops,
    )
    return {
        "entity_id": payload.entity_id,
        "method": "llm_analysis",
        "chains": chains,
        "total": len(chains),
    }


@app.post("/api/v1/causal/paths", tags=["Causal"])
async def causal_find_paths(
    payload: CausalPathRequest,
    engine: CausalEngine = Depends(_get_causal_engine),
) -> dict[str, Any]:
    """Find causal paths between two entities using graph traversal."""
    paths = await engine.find_paths(
        source_id=UUID(payload.source_id),
        target_id=UUID(payload.target_id),
        max_hops=payload.max_hops,
    )
    return {
        "source_id": payload.source_id,
        "target_id": payload.target_id,
        "paths": paths,
        "total": len(paths),
    }


@app.get("/api/v1/causal/chains", tags=["Causal"])
async def list_causal_chains(
    entity_id: Optional[str] = Query(None, description="Filter chains involving this entity"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    engine: CausalEngine = Depends(_get_causal_engine),
) -> dict[str, Any]:
    """List recorded causal chains."""
    eid = UUID(entity_id) if entity_id else None
    chains = await engine.list_chains(entity_id=eid, limit=limit, offset=offset)
    return {"chains": chains, "total": len(chains)}


# ---------------------------------------------------------------------------
# Audio — Speech-to-Text & Text-to-Speech
# ---------------------------------------------------------------------------


def _get_audio_engine(db: Session = Depends(get_db)) -> AudioEngine:
    return AudioEngine(db)


@app.post("/api/v1/audio/transcribe", tags=["Audio"])
async def transcribe_audio(
    file: UploadFile = File(..., description="Audio file (mp3, wav, m4a, ogg, flac, webm)"),
    engine: AudioEngine = Depends(_get_audio_engine),
) -> TranscriptionResponse:
    """Transcribe speech to text using Whisper API.
    
    Upload an audio file and get back the transcription with timing segments.
    Supports MP3, WAV, M4A, OGG, FLAC, WEBM formats.
    """
    if not is_supported_audio(file.filename):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format. Supported: {', '.join(sorted(is_supported_audio.__wrapped__.__globals__['SUPPORTED_AUDIO_FORMATS']))}",
        )
    content = await file.read()
    result = await engine.transcribe(content, file.filename)
    return TranscriptionResponse(
        id=result["id"],
        text=result["text"],
        language=result["language"],
        duration_seconds=result["duration_seconds"],
        segments=result.get("segments", []),
    )


@app.post("/api/v1/audio/synthesize", tags=["Audio"])
async def synthesize_speech(
    payload: SynthesizeRequest,
    engine: AudioEngine = Depends(_get_audio_engine),
):
    """Synthesize text to speech audio.
    
    Returns MP3 audio bytes. Available voices: alloy, echo, fable, onyx, nova, shimmer.
    """
    audio_bytes = await engine.synthesize(
        text=payload.text,
        voice=payload.voice,
        model=payload.model,
    )
    from fastapi.responses import Response
    return Response(
        content=audio_bytes,
        media_type="audio/mpeg",
        headers={"Content-Disposition": f"attachment; filename=speech.mp3"},
    )


@app.post("/api/v1/audio/voice-chat", tags=["Audio"])
async def voice_chat(
    file: UploadFile = File(..., description="Audio recording of your question"),
    conversation_id: Optional[str] = Query(None, description="Existing conversation ID to continue"),
    voice: str = Query("alloy", description="TTS voice for the response"),
    db: Session = Depends(get_db),
):
    """Full voice interaction: speak to the Company Brain and get a spoken response.
    
    1. Upload audio (your question)
    2. System transcribes via Whisper
    3. Brain processes the query with full ontology context
    4. Response is synthesized back to audio (MP3)
    
    Returns the transcription, brain's text reply, and audio as base64.
    """
    if not is_supported_audio(file.filename):
        raise HTTPException(status_code=400, detail="Unsupported audio format")
    
    content = await file.read()
    engine = AudioEngine(db)
    result = await engine.voice_chat(
        audio_data=content,
        filename=file.filename,
        conversation_id=conversation_id,
        voice=voice,
    )
    
    import base64
    audio_b64 = base64.b64encode(result["audio_data"]).decode("utf-8")
    
    return VoiceChatResponse(
        transcription=TranscriptionResponse(
            id=result["transcription"]["id"],
            text=result["transcription"]["text"],
            language=result["transcription"]["language"],
            duration_seconds=result["transcription"]["duration_seconds"],
            segments=result["transcription"].get("segments", []),
        ),
        brain_reply=result["brain_reply"],
        conversation_id=result["conversation_id"],
        actions_taken=result["actions_taken"],
        audio_data=audio_b64,
    )


@app.get("/api/v1/audio/transcriptions", tags=["Audio"])
async def list_transcriptions(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> TranscriptionListResponse:
    """List recent audio transcription records."""
    from sqlalchemy import select
    stmt = select(AudioTranscriptionModel).order_by(
        AudioTranscriptionModel.created_at.desc()
    ).limit(limit)
    results = list(db.execute(stmt).scalars().all())
    return TranscriptionListResponse(
        transcriptions=[
            TranscriptionResponse(
                id=str(t.id),
                text=t.transcription_text[:200],
                language=t.language,
                duration_seconds=t.duration_seconds,
            )
            for t in results
        ],
        total=len(results),
    )


# ---------------------------------------------------------------------------
# OCR — Image & Scanned PDF Text Extraction
# ---------------------------------------------------------------------------


@app.post("/api/v1/ocr", tags=["OCR"])
async def ocr_document(
    file: UploadFile = File(..., description="Image (PNG, JPG, TIFF) or scanned PDF"),
    db: Session = Depends(get_db),
) -> OCRResponse:
    """Extract text from images and scanned PDFs using Vision AI.
    
    Upload an image or scanned PDF document.
    The system uses LLM Vision API to recognize and extract all visible text.
    """
    import tempfile
    content = await file.read()
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix or ".png") as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        if not is_image_file(tmp_path):
            raise HTTPException(status_code=400, detail="File must be an image (PNG, JPG, TIFF)")
        
        text = await ocr_image(tmp_path, db)
        
        # Optionally extract entities from OCR text
        processor = DocumentProcessor(db)
        extracted = await processor._extract_via_llm(
            text[:8000],
            [t["name"] for t in await OntologyEngine(db).list_types()],
        )
        
        return OCRResponse(
            text=text[:5000],
            pages=1,
            method="vision_api",
            entities_extracted=len(extracted.get("entities", [])),
            relationships_extracted=len(extracted.get("relationships", [])),
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Compression — Smart Chunking & Summarization
# ---------------------------------------------------------------------------


@app.post("/api/v1/compression/chunk", tags=["Compression"])
async def chunk_document(
    payload: ChunkRequest,
) -> ChunkResponse:
    """Split text into semantically-aware chunks with configurable overlap.
    
    Useful for preparing documents for embedding, RAG, or batch processing.
    Chunks break at sentence boundaries when possible.
    """
    chunks = chunk_text(
        text=payload.text,
        chunk_size=payload.chunk_size,
        overlap=payload.overlap,
    )
    return ChunkResponse(
        chunks=chunks,
        total_chunks=len(chunks),
        total_characters=len(payload.text),
    )


@app.post("/api/v1/compression/summarize", tags=["Compression"])
async def summarize_document(
    payload: SummarizeRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Compress text into a concise summary using the LLM.
    
    Preserves key entities, facts, and relationships while reducing token count.
    Useful for condensing large documents before storage or analysis.
    """
    summary = await summarize_text(
        text=payload.text,
        session=db,
        max_length=payload.max_length,
    )
    original_chars = len(payload.text)
    summary_chars = len(summary)
    return {
        "summary": summary,
        "original_length": original_chars,
        "summary_length": summary_chars,
        "compression_ratio": round(summary_chars / original_chars, 3) if original_chars > 0 else 1.0,
    }
