"""AgentLayer — implements the AgentLayer protocol for the Awren Core.

Composes with OntologyLayer, KnowledgeLayer, and ActionLayer.
"""

from __future__ import annotations

from typing import Any, Optional

from awren_core.layers import ActionLayer, AgentLayer, KnowledgeLayer, OntologyLayer

from .engine import AgentEngine
from .models import AgentDef
from .registry import AgentRegistry

# Import built-in agents
from .agents.research import research_agent_handler
from .agents.monitor import monitor_agent_handler
from .agents.action import action_agent_handler


class OntologyAgentLayer(AgentLayer):
    """Agent layer backed by OntologyLayer, KnowledgeLayer, and ActionLayer."""

    def __init__(
        self,
        registry: AgentRegistry,
        engine: AgentEngine,
    ) -> None:
        self._registry = registry
        self._engine = engine

    # ------------------------------------------------------------------
    # AgentLayer protocol
    # ------------------------------------------------------------------

    async def run_agent(
        self,
        agent_name: str,
        input: dict[str, Any],
        user: Any,
    ) -> dict[str, Any]:
        result = await self._engine.run_agent(
            agent_name=agent_name,
            input=input,
            user=user,
        )
        return result.to_dict()

    async def list_agents(self) -> list[dict[str, Any]]:
        return self._engine.list_agents()

    async def get_agent(self, agent_name: str) -> Optional[dict[str, Any]]:
        return self._engine.get_agent(agent_name)

    async def create_task(
        self,
        agent_name: str,
        input: dict[str, Any],
        user: Any,
    ) -> dict[str, Any]:
        task = self._engine.create_task(
            agent_name=agent_name,
            input=input,
            user=user,
        )
        return task.to_dict()

    async def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        task = self._engine.get_task(task_id)
        return task.to_dict() if task else None

    async def list_tasks(
        self,
        agent_name: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        tasks = self._engine.list_tasks(
            agent_name=agent_name, limit=limit, offset=offset
        )
        return [t.to_dict() for t in tasks]

    async def cancel_task(self, task_id: str) -> bool:
        return await self._engine.cancel_task(task_id)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create_with_defaults(
        cls,
        ontology: Optional[OntologyLayer] = None,
        knowledge: Optional[KnowledgeLayer] = None,
        actions: Optional[ActionLayer] = None,
    ) -> "OntologyAgentLayer":
        """Factory: creates an OntologyAgentLayer with all built-in agents registered."""
        registry = AgentRegistry()

        # Register built-in agents
        builtin_agents = [
            AgentDef(
                name="research",
                description="Query ontology entities, knowledge graph, and relationships for research",
                handler=research_agent_handler,
                input_schema={
                    "query": "string",
                    "max_entities": "number",
                    "include_relationships": "boolean",
                    "entity_type": "string",
                },
                output_schema={
                    "entities": "array",
                    "knowledge_nodes": "array",
                    "summary": "string",
                },
                tags=["research", "query", "ontology"],
                timeout_seconds=120,
            ),
            AgentDef(
                name="monitor",
                description="Watch ontology entities for state compliance and conditions",
                handler=monitor_agent_handler,
                input_schema={
                    "entity_type": "string",
                    "state_condition": "string",
                    "max_results": "number",
                },
                output_schema={
                    "compliant_count": "number",
                    "non_compliant_count": "number",
                    "summary": "string",
                },
                tags=["monitor", "state", "compliance"],
                timeout_seconds=60,
            ),
            AgentDef(
                name="action_runner",
                description="Execute sequences of actions on ontology objects",
                handler=action_agent_handler,
                input_schema={
                    "steps": "array",
                    "continue_on_error": "boolean",
                },
                output_schema={
                    "overall_success": "boolean",
                    "steps": "array",
                },
                tags=["action", "workflow", "automation"],
                timeout_seconds=300,
            ),
        ]

        for agent_def in builtin_agents:
            registry.register(agent_def)

        engine = AgentEngine(
            registry=registry,
            ontology=ontology,
            knowledge=knowledge,
            actions=actions,
        )

        return cls(registry=registry, engine=engine)
