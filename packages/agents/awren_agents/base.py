"""Base agent classes for the multi-agent framework."""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AgentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentTask(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    agent_type: str
    query: str
    context: Dict[str, Any] = Field(default_factory=dict)
    created: datetime = Field(default_factory=datetime.utcnow)
    priority: int = 0


class AgentResult(BaseModel):
    task_id: UUID
    agent_type: str
    output: Dict[str, Any]
    confidence: float = 1.0
    execution_time_ms: float = 0.0
    error: Optional[str] = None


class BaseAgent(ABC):
    """Abstract base class for all agents."""

    def __init__(self, agent_type: str):
        self.agent_type = agent_type
        self.status = AgentStatus.IDLE

    @abstractmethod
    async def execute(self, task: AgentTask) -> AgentResult:
        """Execute a given task and return the result."""
        ...

    async def validate(self, result: AgentResult) -> bool:
        """Validate the agent's result."""
        return result.error is None
