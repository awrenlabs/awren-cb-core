"""AgentRegistry — central registry for all agent types."""

from __future__ import annotations

from typing import Any, Optional

from .models import AgentDef


class AgentRegistry:
    """Central registry for agent type definitions.

    Agents are registered by name and can be listed, queried, and
    executed by the AgentEngine.
    """

    def __init__(self) -> None:
        self._agents: dict[str, AgentDef] = {}

    def register(self, agent_def: AgentDef) -> None:
        """Register an agent definition."""
        self._agents[agent_def.name] = agent_def

    def unregister(self, agent_name: str) -> None:
        """Remove an agent registration."""
        self._agents.pop(agent_name, None)

    def get(self, agent_name: str) -> Optional[AgentDef]:
        """Get agent definition by name."""
        return self._agents.get(agent_name)

    def list_agents(self) -> list[AgentDef]:
        """List all registered agents."""
        return list(self._agents.values())

    def has(self, agent_name: str) -> bool:
        """Check if an agent is registered."""
        return agent_name in self._agents

    @property
    def count(self) -> int:
        return len(self._agents)

    def clear(self) -> None:
        self._agents.clear()
