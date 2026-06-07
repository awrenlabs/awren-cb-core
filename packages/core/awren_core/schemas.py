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
    state: Optional[str] = None
    provenance: Optional[dict[str, Any]] = None


class EntityUpdate(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    properties: Optional[dict[str, Any]] = None
    identifiers: Optional[list[dict[str, str]]] = None
    state: Optional[str] = None
    provenance: Optional[dict[str, Any]] = None


class EntityResponse(BaseModel):
    id: UUID
    type: str
    label: str
    description: Optional[str] = None
    properties: dict[str, Any]
    identifiers: list[dict[str, str]]
    state: Optional[str] = None
    version_num: int = 1
    provenance: Optional[dict[str, Any]] = None
    metadata: dict[str, Any]


class VersionHistoryResponse(BaseModel):
    version_num: int
    snapshot: dict[str, Any]
    change_description: Optional[str] = None
    created_at: Optional[str] = None


class OntologyTypeDef(BaseModel):
    name: str
    description: Optional[str] = None
    base_type: Optional[str] = None
    states: list[str] = ["active"]
    properties: list[dict[str, Any]] = []


class OntologyPropertyDef(BaseModel):
    name: str
    property_type: str = "string"
    kind: str = "static"
    required: bool = False
    default_value: Optional[str] = None
    formula: Optional[str] = None
    config: dict[str, Any] = {}


class StateTransitionRequest(BaseModel):
    new_state: str
    reason: str = ""


class EntityListResponse(BaseModel):
    entities: list[EntityResponse]
    total: int


# ---------------------------------------------------------------------------
# Relationship schemas
# ---------------------------------------------------------------------------


class RelationshipCreate(BaseModel):
    type: str
    source_id: UUID
    target_id: UUID
    properties: dict[str, Any] = {}
    confidence: float = 1.0


class RelationshipResponse(BaseModel):
    id: UUID
    type: str
    source_id: UUID
    target_id: UUID
    properties: dict[str, Any]
    metadata: dict[str, Any]


class RelationshipListResponse(BaseModel):
    relationships: list[RelationshipResponse]
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


# ---------------------------------------------------------------------------
# Chat schemas
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: float = 0.7
    include_graph_context: bool = True


class ChatResponse(BaseModel):
    reply: str
    conversation_id: str
    provider: str
    model: str
    confidence: float
    entities_referenced: list[dict[str, Any]] = []
    execution_time_ms: float
    actions_taken: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {}


class ConversationResponse(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationListResponse(BaseModel):
    conversations: list[ConversationResponse]
    total: int


class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    metadata: dict[str, Any]
    created_at: datetime


# ---------------------------------------------------------------------------
# LLM Provider schemas
# ---------------------------------------------------------------------------


class LLMProviderInfo(BaseModel):
    id: str
    name: str
    models: list[dict[str, str]]
    requires_api_key: bool = True
    has_api_key: bool = False


class LLMSettingsUpdate(BaseModel):
    provider: str
    model: str
    openai_api_key: Optional[str] = ""
    anthropic_api_key: Optional[str] = ""
    api_key: Optional[str] = None  # backward compat
    base_url: Optional[str] = None
    temperature: float = 0.7


class LLMSettingsResponse(BaseModel):
    provider: str
    model: str
    available_providers: list[LLMProviderInfo]
    openai_api_key_configured: bool = False
    anthropic_api_key_configured: bool = False


# ---------------------------------------------------------------------------
# Import / Ingestion schemas
# ---------------------------------------------------------------------------


class ImportJobResponse(BaseModel):
    id: UUID
    original_filename: str
    file_size: int
    mime_type: Optional[str] = None
    status: str
    total_entities: int
    total_relationships: int
    error_messages: list[str]
    result_summary: Optional[dict[str, Any]] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class ImportJobListResponse(BaseModel):
    jobs: list[ImportJobResponse]
    total: int


class ImportProcessResponse(BaseModel):
    status: str
    job_id: str
    entities_created: int
    relationships_created: int
    errors: list[str]
    elapsed_ms: float


# ---------------------------------------------------------------------------
# System Monitoring schemas
# ---------------------------------------------------------------------------


class SystemStatsResponse(BaseModel):
    total_entities: int
    total_relationships: int
    total_events: int
    total_conversations: int
    total_imports: int
    total_transcriptions: int
    entities_by_type: list[dict[str, Any]]
    imports_by_status: dict[str, int]
    recent_activity: list[dict[str, Any]]
    llm_provider: str
    llm_model: str
    uptime_hours: float
    total_users: int = 0
    total_knowledge_nodes: int = 0
    knowledge_by_kind: dict[str, int] = {}
    total_causal_chains: int = 0


# ---------------------------------------------------------------------------
# Audio schemas
# ---------------------------------------------------------------------------


class TranscriptionResponse(BaseModel):
    id: str
    text: str
    language: str
    duration_seconds: float
    segments: list[dict[str, Any]] = []


class SynthesizeRequest(BaseModel):
    text: str
    voice: str = "alloy"
    model: str = "tts-1-hd"


class VoiceChatResponse(BaseModel):
    transcription: TranscriptionResponse
    brain_reply: str
    conversation_id: Optional[str] = None
    actions_taken: list[dict[str, Any]] = []
    audio_data: Optional[str] = None  # base64 encoded
    audio_format: str = "mp3"


class TranscriptionListResponse(BaseModel):
    transcriptions: list[TranscriptionResponse]
    total: int


# ---------------------------------------------------------------------------
# OCR schemas
# ---------------------------------------------------------------------------


class OCRResponse(BaseModel):
    text: str
    pages: int = 1
    method: str  # "vision_api", "pymupdf", "fallback"
    entities_extracted: int = 0
    relationships_extracted: int = 0


# ---------------------------------------------------------------------------
# Compression schemas
# ---------------------------------------------------------------------------


class ChunkRequest(BaseModel):
    text: str
    chunk_size: int = 2000
    overlap: int = 200


class ChunkResponse(BaseModel):
    chunks: list[dict[str, Any]]
    total_chunks: int
    total_characters: int


class SummarizeRequest(BaseModel):
    text: str
    max_length: int = 500


# ---------------------------------------------------------------------------
# Auth schemas
# ---------------------------------------------------------------------------


class UserRegister(BaseModel):
    username: str
    email: str
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str
    role: str


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    role: str
    is_active: bool
    created_at: Optional[str] = None


class APIKeyGenerateRequest(BaseModel):
    expires_days: Optional[int] = None


class APIKeyResponse(BaseModel):
    api_key: str
    key_preview: str
    expires_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Knowledge Graph Layer schemas
# ---------------------------------------------------------------------------


class KnowledgeNodeCreate(BaseModel):
    kind: str  # insight, rule, pattern
    label: str
    content: str
    source: str = "system"
    confidence: float = 1.0
    tags: list[str] = []
    metadata: dict[str, Any] = {}
    entity_ids: list[str] = []


class KnowledgeNodeResponse(BaseModel):
    id: str
    kind: str
    label: str
    content: str
    source: str
    confidence: float
    tags: list[str]
    entity_ids: list[str]
    metadata: dict[str, Any]
    created_at: Optional[str] = None


class KnowledgeEdgeCreate(BaseModel):
    source_id: str
    target_id: str
    relationship_type: str = "derives_from"
    confidence: float = 1.0
    metadata: dict[str, Any] = {}


class KnowledgeEdgeResponse(BaseModel):
    id: str
    source_id: str
    target_id: str
    relationship_type: str
    confidence: float
    metadata: dict[str, Any]
    created_at: Optional[str] = None


class KnowledgeStatsResponse(BaseModel):
    total_nodes: int
    insights: int
    rules: int
    patterns: int
    total_edges: int


class KnowledgeExtractRequest(BaseModel):
    text: str
    source: str = "api"


# ---------------------------------------------------------------------------
# Causal Reasoning schemas
# ---------------------------------------------------------------------------


class CausalChainResponse(BaseModel):
    id: str
    head_id: str
    chain: list[dict[str, Any]]
    confidence: float
    source: str
    metadata: dict[str, Any]
    created_at: Optional[str] = None


class CausalAnalysisRequest(BaseModel):
    entity_id: str
    max_hops: int = 5
    min_confidence: float = 0.3
    method: str = "graph"  # graph, llm, both


class CausalPathRequest(BaseModel):
    source_id: str
    target_id: str
    max_hops: int = 6


# ---------------------------------------------------------------------------
# Explainability schemas
# ---------------------------------------------------------------------------


class ExplanationResponse(BaseModel):
    what: str
    why: str
    which_data: list[dict[str, Any]]
    confidence: float
    confidence_justification: str
    assumptions: list[str]
    alternatives_considered: list[str]
    limitations: list[str]
