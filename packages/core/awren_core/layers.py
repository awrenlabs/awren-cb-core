"""Layer protocols for modular plug-and-play architecture.

Each layer of the Awren Core implements one or more of these protocols,
allowing layers to be composed, swapped, or tested independently.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable
from uuid import UUID


# ---------------------------------------------------------------------------
# Ontology Layer
# ---------------------------------------------------------------------------


@runtime_checkable
class OntologyLayer(Protocol):
    """Entity type registry, CRUD, state machine, version history."""

    async def get_entity(self, entity_id: UUID) -> Optional[dict[str, Any]]:
        ...

    async def update_entity(self, entity_id: UUID, **kwargs: Any) -> dict[str, Any]:
        ...

    async def get_entity_type(self, type_name: str) -> Optional[dict[str, Any]]:
        ...

    async def list_types(self) -> list[dict[str, Any]]:
        ...

    async def transition_state(
        self, entity_id: UUID, new_state: str, reason: str = ""
    ) -> dict[str, Any]:
        ...

    async def get_version_history(self, entity_id: UUID) -> list[dict[str, Any]]:
        ...


# ---------------------------------------------------------------------------
# Knowledge Layer
# ---------------------------------------------------------------------------


@runtime_checkable
class KnowledgeLayer(Protocol):
    """Knowledge graph — insights, rules, patterns."""

    async def query(
        self, query: str, kinds: Optional[list[str]] = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        ...

    async def create_node(
        self,
        kind: str,
        label: str,
        content: str,
        source: str = "system",
        confidence: float = 1.0,
        tags: Optional[list[str]] = None,
        entity_ids: Optional[list[UUID]] = None,
    ) -> dict[str, Any]:
        ...

    async def get_stats(self) -> dict[str, Any]:
        ...


# ---------------------------------------------------------------------------
# Causal Layer
# ---------------------------------------------------------------------------


@runtime_checkable
class CausalLayer(Protocol):
    """Causal reasoning — chain discovery and analysis."""

    async def forward_chain(
        self,
        entity_id: UUID,
        max_hops: int = 5,
        min_confidence: float = 0.3,
    ) -> list[dict[str, Any]]:
        ...

    async def backward_chain(
        self,
        entity_id: UUID,
        max_hops: int = 5,
        min_confidence: float = 0.3,
    ) -> list[dict[str, Any]]:
        ...

    async def find_paths(
        self, source_id: UUID, target_id: UUID, max_hops: int = 6
    ) -> list[dict[str, Any]]:
        ...


# ---------------------------------------------------------------------------
# Action Layer
# ---------------------------------------------------------------------------


@runtime_checkable
class ActionLayer(Protocol):
    """Executable actions on ontology objects."""

    async def list_actions(
        self, type_name: str, user: Optional[Any] = None
    ) -> list[dict[str, Any]]:
        ...

    async def execute_action(
        self,
        action_name: str,
        entity_id: UUID,
        params: dict[str, Any],
        user: Any,
    ) -> dict[str, Any]:
        ...

    async def get_action(
        self, action_name: str, type_name: str
    ) -> Optional[dict[str, Any]]:
        ...


# ---------------------------------------------------------------------------
# Explainability Layer
# ---------------------------------------------------------------------------


@runtime_checkable
class ExplainabilityLayer(Protocol):
    """Explainability — what, why, evidence, confidence."""

    async def explain(
        self,
        what: str,
        why: str,
        which_data: Optional[list[Any]] = None,
        confidence: float = 0.0,
        assumptions: Optional[list[str]] = None,
        limitations: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        ...


# ---------------------------------------------------------------------------
# Agent Layer (future)
# ---------------------------------------------------------------------------


@runtime_checkable
class AgentLayer(Protocol):
    """Agent runtime — agents operate exclusively through ontology objects."""

    async def run_agent(
        self,
        agent_name: str,
        input: dict[str, Any],
        user: Any,
    ) -> dict[str, Any]:
        ...

    async def list_agents(self) -> list[dict[str, Any]]:
        ...


# ---------------------------------------------------------------------------
# Memory Layer (future)
# ---------------------------------------------------------------------------


@runtime_checkable
class MemoryLayer(Protocol):
    """Organizational memory — episodic, semantic, procedural, strategic."""

    async def store(
        self, memory_type: str, key: str, content: dict[str, Any]
    ) -> None:
        ...

    async def recall(
        self, memory_type: str, query: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        ...

    async def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        ...
