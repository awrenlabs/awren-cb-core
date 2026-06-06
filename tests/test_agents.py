"""ResearchAgent tests.

Covers:
- Successful research with entities found
- Empty knowledge graph (no entities)
- LLM-powered reasoning path (mocked)
- Fallback when no LLM available
- Error handling (API failure, search failure)
- AgentOrchestrator integration
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from awren_agents.base import AgentTask
from awren_agents.orchestrator import AgentOrchestrator
from awren_agents.research_agent import ResearchAgent


@pytest.fixture
def sample_entities() -> list[dict[str, str]]:
    return [
        {"id": str(uuid4()), "type": "core:Project", "label": "Highway Expansion", "description": "Major infrastructure project"},
        {"id": str(uuid4()), "type": "core:Organization", "label": "Acme Corp", "description": "Construction firm"},
        {"id": str(uuid4()), "type": "core:Person", "label": "Alice", "description": "Project manager"},
    ]


@pytest.fixture
def agent() -> ResearchAgent:
    return ResearchAgent()


class TestResearchAgent:
    """Tests for ResearchAgent basic operations."""

    async def test_research_with_entities(self, agent: ResearchAgent, sample_entities):
        """Should search entities and return structured reasoning output."""
        # Mock the SDK client to return entities
        mock_client = AsyncMock()
        mock_client.list_entities.return_value = {"entities": sample_entities, "total": 3}
        agent._get_client = MagicMock(return_value=mock_client)  # type: ignore[method-assign]

        task = AgentTask(agent_type="research", query="Find project risks")
        result = await agent.execute(task)

        assert result.agent_type == "research"
        assert result.error is None
        assert result.output["entity_count"] == 3
        assert len(result.output["entities"]) == 3
        assert "deductive_conclusions" in result.output
        assert "inductive_patterns" in result.output
        assert "abductive_explanations" in result.output
        assert result.confidence > 0

    async def test_research_empty_knowledge_graph(self, agent: ResearchAgent):
        """Should handle empty search results gracefully."""
        mock_client = AsyncMock()
        mock_client.list_entities.return_value = {"entities": [], "total": 0}
        agent._get_client = MagicMock(return_value=mock_client)  # type: ignore[method-assign]

        task = AgentTask(agent_type="research", query="Find something")
        result = await agent.execute(task)

        assert result.error is None
        assert result.output["entity_count"] == 0
        assert result.output["entities"] == []

    async def test_research_with_entity_type_filter(self, agent: ResearchAgent, sample_entities):
        """Should pass entity_type filter to the SDK."""
        mock_client = AsyncMock()
        mock_client.list_entities.return_value = {"entities": sample_entities, "total": 3}
        agent._get_client = MagicMock(return_value=mock_client)  # type: ignore[method-assign]

        task = AgentTask(
            agent_type="research",
            query="Find projects",
            context={"entity_type": "core:Project"},
        )
        result = await agent.execute(task)

        assert result.error is None
        mock_client.list_entities.assert_called_once_with(entity_type="core:Project", limit=20)

    async def test_api_failure_returns_empty_results(self, agent: ResearchAgent):
        """Should handle API errors gracefully and continue with empty context."""
        mock_client = AsyncMock()
        mock_client.list_entities.side_effect = Exception("API unavailable")
        agent._get_client = MagicMock(return_value=mock_client)  # type: ignore[method-assign]

        task = AgentTask(agent_type="research", query="Test query")
        result = await agent.execute(task)

        assert result.error is None  # Error is caught, agent continues
        assert result.output["entity_count"] == 0
        assert result.output["entities"] == []


class TestResearchAgentLLM:
    """Tests for the LLM-powered reasoning path."""

    async def test_llm_reasoning_used_when_available(self, agent: ResearchAgent, sample_entities):
        """Should use the LLM path in ReasoningEngine for inductive/abductive modes."""
        mock_client = AsyncMock()
        mock_client.list_entities.return_value = {"entities": sample_entities, "total": 3}
        agent._get_client = MagicMock(return_value=mock_client)  # type: ignore[method-assign]

        # Mock the ReasoningEngine to return LLM-quality results
        with patch.object(agent._engine, "_call_llm") as mock_llm:
            mock_llm.side_effect = [
                # First call: inductive patterns
                {
                    "patterns": [
                        {"pattern": "Projects with budgets >$10M have 40% cost overrun risk",
                         "support": 0.85, "evidence": "3 out of 5 projects analyzed"}
                    ],
                    "confidence": 0.85,
                },
                # Second call: abductive explanations
                {
                    "explanations": [
                        {"hypothesis": "Cost overruns driven by material price volatility",
                         "plausibility": 0.82, "reasoning": "Steel prices fluctuated 25% in Q2"}
                    ],
                    "confidence": 0.82,
                },
            ]

            task = AgentTask(agent_type="research", query="Analyze project risks")
            result = await agent.execute(task)

            assert result.error is None
            assert result.output["inductive_patterns"][0]["pattern"] == \
                "Projects with budgets >$10M have 40% cost overrun risk"
            assert "material price" in result.output["abductive_explanations"][0]["hypothesis"].lower()
            # Average of (deductive=0.0, inductive=0.85, abductive=0.82) = 0.557
            assert result.confidence > 0.5
            assert result.confidence < 0.6


class TestAgentOrchestratorIntegration:
    """Tests for AgentOrchestrator with ResearchAgent."""

    async def test_orchestrator_with_research_agent(self, sample_entities):
        """Should register and route tasks to ResearchAgent."""
        orchestrator = AgentOrchestrator()
        agent = ResearchAgent()

        # Mock the SDK
        mock_client = AsyncMock()
        mock_client.list_entities.return_value = {"entities": sample_entities, "total": 3}
        agent._get_client = MagicMock(return_value=mock_client)  # type: ignore[method-assign]

        orchestrator.register_agent(agent)

        task = AgentTask(agent_type="research", query="Assess project status")
        result = await orchestrator.execute_task(task)

        assert result.agent_type == "research"
        assert result.error is None
        assert result.output["entity_count"] == 3

    async def test_orchestrator_routes_to_unregistered_agent(self):
        """Should return error when no agent is registered for a type."""
        orchestrator = AgentOrchestrator()

        task = AgentTask(agent_type="nonexistent", query="test")
        result = await orchestrator.execute_task(task)

        assert result.error is not None
        assert "No agent registered" in result.error

    async def test_orchestrator_decompose_and_execute(self, sample_entities):
        """Should run all registered agents via decompose_and_execute."""
        orchestrator = AgentOrchestrator()
        agent = ResearchAgent()

        mock_client = AsyncMock()
        mock_client.list_entities.return_value = {"entities": sample_entities, "total": 3}
        agent._get_client = MagicMock(return_value=mock_client)  # type: ignore[method-assign]

        orchestrator.register_agent(agent)

        results = await orchestrator.decompose_and_execute("Analyze everything")
        assert len(results) == 1  # Only one agent registered
        assert results[0].agent_type == "research"


class TestResearchAgentEdgeCases:
    """Edge cases and error handling."""

    async def test_agent_task_with_context(self):
        """Should accept and pass custom context to reasoning."""
        agent = ResearchAgent()
        mock_client = AsyncMock()
        mock_client.list_entities.return_value = {"entities": [], "total": 0}
        agent._get_client = MagicMock(return_value=mock_client)  # type: ignore[method-assign]

        task = AgentTask(
            agent_type="research",
            query="Custom query",
            context={"custom_field": "custom_value", "search_limit": 5},
        )
        result = await agent.execute(task)

        assert result.error is None
        assert result.output["query"] == "Custom query"

    async def test_large_entity_list_truncated(self):
        """Should not exceed max context size with many entities."""
        agent = ResearchAgent()
        many_entities = [
            {"id": str(uuid4()), "type": "core:Test", "label": f"Entity {i}", "description": ""}
            for i in range(50)
        ]

        mock_client = AsyncMock()
        mock_client.list_entities.return_value = {"entities": many_entities, "total": 50}
        agent._get_client = MagicMock(return_value=mock_client)  # type: ignore[method-assign]

        task = AgentTask(agent_type="research", query="Many entities test")
        result = await agent.execute(task)

        assert result.error is None
        assert result.output["entity_count"] == 50
        assert len(result.output["entities"]) == 20  # Truncated to 20

    async def test_confidence_calculation(self):
        """Should calculate aggregate confidence from all reasoning modes."""
        agent = ResearchAgent()
        mock_client = AsyncMock()
        mock_client.list_entities.return_value = {"entities": [], "total": 0}
        agent._get_client = MagicMock(return_value=mock_client)  # type: ignore[method-assign]

        task = AgentTask(agent_type="research", query="Confidence test")
        result = await agent.execute(task)

        # Deductive: 0.0 (no rules), Inductive: 0.75 (fallback), Abductive: 0.8 (fallback)
        # Average: (0.0 + 0.75 + 0.8) / 3 = 0.517
        assert result.confidence == pytest.approx(0.517, rel=0.01)
