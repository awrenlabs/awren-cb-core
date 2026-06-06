"""Memory domain models for the Awren Cognitive OS."""
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

class MemoryBase(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    content: str
    context: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: Optional[str] = None
    confidence: float = 1.0
    tags: list[str] = Field(default_factory=list)

class EpisodicMemory(MemoryBase):
    """Event-based memory of specific occurrences."""
    memory_type: str = "episodic"
    event_id: Optional[UUID] = None
    participants: list[str] = Field(default_factory=list)

class SemanticMemory(MemoryBase):
    """Factual knowledge about entities and concepts."""
    memory_type: str = "semantic"
    entity_id: Optional[UUID] = None
    facts: dict[str, Any] = Field(default_factory=dict)

class ProceduralMemory(MemoryBase):
    """Knowledge of processes and workflows."""
    memory_type: str = "procedural"
    steps: list[dict[str, Any]] = Field(default_factory=list)
    workflow_id: Optional[str] = None

class WorkingMemory(MemoryBase):
    """Active context for current interactions."""
    memory_type: str = "working"
    ttl: int = 3600  # seconds until expiration
    session_id: Optional[str] = None
