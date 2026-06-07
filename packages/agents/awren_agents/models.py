"""Agent data models — definitions, tasks, results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4


class AgentStatus(str, Enum):
    """Lifecycle status of an agent task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentDef:
    """Definition of an agent type."""

    name: str
    description: str
    handler: Any  # async callable(agent_def, input, user, **context) -> dict
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    timeout_seconds: int = 300

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "tags": self.tags,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass
class AgentTask:
    """A task assigned to an agent for execution."""

    id: UUID = field(default_factory=uuid4)
    agent_name: str = ""
    status: AgentStatus = AgentStatus.PENDING
    input: dict[str, Any] = field(default_factory=dict)
    output: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    created_by: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    elapsed_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "agent_name": self.agent_name,
            "status": self.status.value,
            "input": self.input,
            "output": self.output,
            "error": self.error,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "metadata": self.metadata,
        }


@dataclass
class AgentResult:
    """Result of executing an agent task."""

    success: bool
    task_id: str
    agent_name: str
    output: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "task_id": self.task_id,
            "agent_name": self.agent_name,
            "output": self.output or {},
            "error": self.error,
            "elapsed_ms": round(self.elapsed_ms, 2),
        }
