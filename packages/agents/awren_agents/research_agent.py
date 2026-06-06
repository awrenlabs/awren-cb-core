"""Research Agent — queries the knowledge graph and applies multi-modal reasoning.

The ResearchAgent is the first concrete agent in the Awren agent framework.
It combines:
1. Entity search via the AwrenClient SDK
2. Multi-modal reasoning via the ReasoningEngine (deductive + LLM-powered)
3. Structured answer composition

Usage:
    agent = ResearchAgent()
    result = await agent.execute(AgentTask(query="Find project risks", context={...}))
"""

import logging
import time
from typing import Any, Optional, cast

from awren_agents.base import AgentResult, AgentTask, BaseAgent
from awren_reasoning.engine import ReasoningEngine, ReasoningMode

logger = logging.getLogger(__name__)


class ResearchAgent(BaseAgent):
    """An agent that researches a query by searching the knowledge graph
    and applying multi-modal reasoning to produce structured answers.

    Agent type: ``research``
    """

    def __init__(
        self,
        reasoning_engine: Optional[ReasoningEngine] = None,
        api_base_url: Optional[str] = None,
    ) -> None:
        super().__init__(agent_type="research")
        self._engine = reasoning_engine or ReasoningEngine()
        # Use provided URL, or fall back to settings, then hardcoded default
        from awren_core.settings import get_settings
        self._api_base_url = api_base_url or get_settings().api_base_url
        # Client is lazy-initialized on first use
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy-initialize the SDK client."""
        if self._client is None:
            from awren_sdk.client import AwrenClient

            self._client = AwrenClient(base_url=self._api_base_url)
        return self._client

    async def execute(self, task: AgentTask) -> AgentResult:
        """Execute a research task.

        Workflow:
        1. Parse the query and context from the task
        2. Search entities in the knowledge graph related to the query
        3. Build a reasoning context from found entities
        4. Apply deductive reasoning (rules) first
        5. Apply inductive/abductive reasoning (LLM) to discover patterns/explanations
        6. Compose results into a structured answer
        """
        start_time = time.monotonic()
        query = task.query
        context = task.context or {}

        try:
            # Step 1: Search the knowledge graph for related entities
            entities = await self._search_knowledge_graph(query, context)

            # Step 2: Build reasoning context from search results
            reasoning_context = self._build_reasoning_context(query, entities, context)

            # Step 3: Apply deductive reasoning (deterministic rules)
            deductive_result = self._engine.reason(
                query, reasoning_context, mode=ReasoningMode.DEDUCTIVE,
            )

            # Step 4: Apply inductive reasoning (LLM pattern discovery)
            inductive_result = self._engine.reason(
                query, reasoning_context, mode=ReasoningMode.INDUCTIVE,
            )

            # Step 5: Apply abductive reasoning (LLM explanation generation)
            abductive_result = self._engine.reason(
                query, reasoning_context, mode=ReasoningMode.ABDUCTIVE,
            )

            # Step 6: Compose final answer
            output = self._compose_answer(
                query=query,
                entities=entities,
                deductive=deductive_result,
                inductive=inductive_result,
                abductive=abductive_result,
            )

            elapsed_ms = (time.monotonic() - start_time) * 1000
            return AgentResult(
                task_id=task.id,
                agent_type=self.agent_type,
                output=output,
                confidence=output.get("confidence", 0.5),
                execution_time_ms=round(elapsed_ms, 2),
            )

        except Exception as e:
            elapsed_ms = (time.monotonic() - start_time) * 1000
            logger.exception("ResearchAgent failed for query: %s", query)
            return AgentResult(
                task_id=task.id,
                agent_type=self.agent_type,
                output={"error": str(e), "query": query},
                confidence=0.0,
                execution_time_ms=round(elapsed_ms, 2),
                error=str(e),
            )

    async def _search_knowledge_graph(
        self,
        query: str,
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Search entities in the knowledge graph related to the query."""
        client = self._get_client()

        # If context specifies an entity type, filter by it
        entity_type = context.get("entity_type")
        limit = context.get("search_limit", 20)

        try:
            result = await client.list_entities(
                entity_type=entity_type,
                limit=limit,
            )
            return cast(list[dict[str, Any]], result.get("entities", []))
        except Exception as e:
            logger.warning("Knowledge graph search failed: %s", e)
            return []

    def _build_reasoning_context(
        self,
        query: str,
        entities: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Build a rich reasoning context from the knowledge graph results."""
        reasoning_context = dict(context)  # Copy original context

        # Add entity summaries
        entity_summaries = []
        for entity in entities[:10]:  # Limit to top 10 for context size
            entity_summaries.append({
                "id": entity.get("id", ""),
                "type": entity.get("type", ""),
                "label": entity.get("label", ""),
                "description": entity.get("description", ""),
            })
        reasoning_context["entities"] = entity_summaries
        reasoning_context["entity_count"] = len(entities)

        # Extract unique entity types present
        entity_types = list({e.get("type", "") for e in entities if e.get("type")})
        reasoning_context["entity_types"] = entity_types

        return reasoning_context

    def _compose_answer(
        self,
        query: str,
        entities: list[dict[str, Any]],
        deductive: dict[str, Any],
        inductive: dict[str, Any],
        abductive: dict[str, Any],
    ) -> dict[str, Any]:
        """Compose the final answer from all reasoning results."""
        conclusions = deductive.get("conclusions", [])
        patterns = inductive.get("patterns", [])
        explanations = abductive.get("explanations", [])

        # Calculate aggregate confidence
        confidences = [
            deductive.get("confidence", 0.0),
            inductive.get("confidence", 0.0),
            abductive.get("confidence", 0.0),
        ]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        return {
            "query": query,
            "entity_count": len(entities),
            "entities": [
                {
                    "id": e.get("id", ""),
                    "type": e.get("type", ""),
                    "label": e.get("label", ""),
                }
                for e in entities[:20]
            ],
            "deductive_conclusions": [
                {
                    "conclusion": c.get("rule", ""),
                    "confidence": c.get("confidence", 0.0),
                    "explanation": c.get("explanation", ""),
                }
                for c in conclusions
            ],
            "inductive_patterns": [
                {
                    "pattern": p.get("pattern", ""),
                    "support": p.get("support", 0.0),
                }
                for p in patterns
            ],
            "abductive_explanations": [
                {
                    "hypothesis": e.get("hypothesis", ""),
                    "plausibility": e.get("plausibility", 0.0),
                }
                for e in explanations
            ],
            "confidence": round(avg_confidence, 3),
        }
