"""AgentEngine — lifecycle management for agent execution.

Follows the perceive → reason → act → observe → learn cycle
(OODA loop applied to ontology operations).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from awren_core.layers import ActionLayer, KnowledgeLayer, OntologyLayer

from .models import AgentDef, AgentResult, AgentStatus, AgentTask
from .registry import AgentRegistry


class AgentEngine:
    """Engine that manages agent lifecycle and execution.

    Composes with OntologyLayer and ActionLayer so agents can
    read/write entities and execute actions.
    """

    def __init__(
        self,
        registry: AgentRegistry,
        ontology: Optional[OntologyLayer] = None,
        knowledge: Optional[KnowledgeLayer] = None,
        actions: Optional[ActionLayer] = None,
    ) -> None:
        self._registry = registry
        self._ontology = ontology
        self._knowledge = knowledge
        self._actions = actions
        self._tasks: dict[str, AgentTask] = {}

    # ------------------------------------------------------------------
    # Agent query
    # ------------------------------------------------------------------

    def list_agents(self) -> list[dict[str, Any]]:
        return [a.to_dict() for a in self._registry.list_agents()]

    def get_agent(self, agent_name: str) -> Optional[dict[str, Any]]:
        adef = self._registry.get(agent_name)
        return adef.to_dict() if adef else None

    # ------------------------------------------------------------------
    # Task lifecycle
    # ------------------------------------------------------------------

    def create_task(
        self,
        agent_name: str,
        input: dict[str, Any],
        user: Any = None,
    ) -> AgentTask:
        """Create a new task for an agent (does not execute)."""
        adef = self._registry.get(agent_name)
        if not adef:
            raise ValueError(f"Agent '{agent_name}' not found")
        task = AgentTask(
            agent_name=agent_name,
            input=input,
            created_by=str(getattr(user, "id", user)) if user else "system",
        )
        self._tasks[str(task.id)] = task
        return task

    def get_task(self, task_id: str) -> Optional[AgentTask]:
        """Get task by ID."""
        return self._tasks.get(task_id)

    def list_tasks(
        self,
        agent_name: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AgentTask]:
        """List tasks, optionally filtered by agent."""
        all_tasks = list(self._tasks.values())
        if agent_name:
            all_tasks = [t for t in all_tasks if t.agent_name == agent_name]
        all_tasks.sort(key=lambda t: t.created_at, reverse=True)
        return all_tasks[offset : offset + limit]

    async def run_agent(
        self,
        agent_name: str,
        input: dict[str, Any],
        user: Any = None,
    ) -> AgentResult:
        """Execute an agent synchronously and return the result.

        Creates a task, runs it, and returns the result.
        """
        adef = self._registry.get(agent_name)
        if not adef:
            return AgentResult(
                success=False,
                task_id="",
                agent_name=agent_name,
                error=f"Agent '{agent_name}' not found",
            )

        task = self.create_task(agent_name, input, user)
        task.status = AgentStatus.RUNNING
        task.started_at = datetime.now(timezone.utc).isoformat()

        start = time.monotonic()
        try:
            output = await adef.handler(
                agent_def=adef,
                input=input,
                user=user,
                ontology=self._ontology,
                knowledge=self._knowledge,
                actions=self._actions,
                task_id=str(task.id),
            )
            elapsed = (time.monotonic() - start) * 1000
            task.status = AgentStatus.COMPLETED
            task.output = output if isinstance(output, dict) else {"result": output}
            task.completed_at = datetime.now(timezone.utc).isoformat()
            task.elapsed_ms = elapsed

            return AgentResult(
                success=True,
                task_id=str(task.id),
                agent_name=agent_name,
                output=task.output,
                elapsed_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            task.status = AgentStatus.FAILED
            task.error = str(e)
            task.completed_at = datetime.now(timezone.utc).isoformat()
            task.elapsed_ms = elapsed

            return AgentResult(
                success=False,
                task_id=str(task.id),
                agent_name=agent_name,
                error=str(e),
                elapsed_ms=elapsed,
            )

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending or running task."""
        task = self._tasks.get(task_id)
        if task and task.status in (AgentStatus.PENDING, AgentStatus.RUNNING):
            task.status = AgentStatus.CANCELLED
            return True
        return False
