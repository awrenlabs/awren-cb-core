"""Agent orchestrator for task decomposition and routing."""

from typing import Any, Dict, List, Optional

from awren_agents.base import AgentResult, AgentTask, BaseAgent


class AgentOrchestrator:
    """Central orchestrator that decomposes tasks and routes to specialized agents."""

    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}

    def register_agent(self, agent: BaseAgent) -> None:
        self._agents[agent.agent_type] = agent

    def unregister_agent(self, agent_type: str) -> None:
        self._agents.pop(agent_type, None)

    def get_agent(self, agent_type: str) -> Optional[BaseAgent]:
        return self._agents.get(agent_type)

    async def execute_task(self, task: AgentTask) -> AgentResult:
        agent = self._agents.get(task.agent_type)
        if not agent:
            return AgentResult(
                task_id=task.id,
                agent_type=task.agent_type,
                output={},
                error=f"No agent registered for type: {task.agent_type}",
            )
        return await agent.execute(task)

    async def decompose_and_execute(self, query: str) -> List[AgentResult]:
        results = []
        for agent_type, agent in self._agents.items():
            task = AgentTask(agent_type=agent_type, query=query)
            result = await agent.execute(task)
            results.append(result)
        return results
