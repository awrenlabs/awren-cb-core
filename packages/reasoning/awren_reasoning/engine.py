"""Multi-modal reasoning engine with flexible LLM integration.

Provides 5 reasoning modes:
- Deductive: deterministic rule-based inference
- Inductive: pattern discovery (powered by LLM when available)
- Abductive: explanation generation (powered by LLM when available)
- Analogical: cross-domain analogy mapping (powered by LLM when available)
- Hybrid: combines deductive + inductive results

Supports multiple LLM providers via the ``awren_core.llm`` abstraction:
- OpenAI (GPT-4, GPT-4o-mini, etc.)
- Anthropic (Claude)
- OpenRouter (multi-model gateway)
- Any OpenAI-compatible API (Together, Groq, etc.)

When no API key is configured, the engine falls back to
internal mock data for LLM-dependent modes.
"""

import json
import logging
from enum import Enum
from typing import Any, Optional, cast

from awren_core.llm import LLMClient, create_llm_client

logger = logging.getLogger(__name__)

# Default prompts for each reasoning mode
SYSTEM_PROMPTS: dict[str, str] = {
    "inductive": (
        "You are an inductive reasoning engine. Analyze the given observations "
        "and identify meaningful patterns, trends, and generalizations. "
        "Return a JSON object with:\n"
        "- patterns: list of objects, each with {pattern (str), support (float 0-1), evidence (str)}\n"
        "- confidence: overall confidence in the patterns (float 0-1)"
    ),
    "abductive": (
        "You are an abductive reasoning engine. Given observations, generate "
        "the most likely explanations or root causes. Evaluate each hypothesis "
        "for plausibility.\n"
        "Return a JSON object with:\n"
        "- explanations: list of objects, each with {hypothesis (str), plausibility (float 0-1), reasoning (str)}\n"
        "- confidence: overall confidence in best explanation (float 0-1)"
    ),
    "analogical": (
        "You are an analogical reasoning engine. Given a target situation, "
        "find relevant analogies from other domains. For each analogy, "
        "explain how the source domain maps to the target domain.\n"
        "Return a JSON object with:\n"
        "- analogs: list of objects, each with {source_domain (str), target_domain (str), "
        "similarity (float 0-1), mapping (str)}\n"
        "- confidence: overall confidence (float 0-1)"
    ),
    "hybrid": "You are a hybrid reasoning engine. Synthesize multiple reasoning approaches.",
}


class ReasoningMode(str, Enum):
    DEDUCTIVE = "deductive"
    INDUCTIVE = "inductive"
    ABDUCTIVE = "abductive"
    ANALOGICAL = "analogical"
    HYBRID = "hybrid"


class ReasoningEngine:
    """Multi-modal reasoning engine with LLM-powered and rule-based modes.

    Usage:
        engine = ReasoningEngine()
        engine.add_rule("risk", {"conditions": [...], "conclusion": "High risk"})
        result = engine.reason("What are the risks?", context, mode=ReasoningMode.DEDUCTIVE)
    """

    def __init__(self) -> None:
        self._rules: dict[str, list[dict[str, Any]]] = {}
        self._llm_client: Any = None

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def add_rule(self, rule_id: str, rule: dict[str, Any]) -> None:
        """Register a deductive rule."""
        if rule_id not in self._rules:
            self._rules[rule_id] = []
        self._rules[rule_id].append(rule)

    # ------------------------------------------------------------------
    # LLM client (lazy, only when API key is configured)
    # ------------------------------------------------------------------

    def _get_llm_client(self) -> Optional[LLMClient]:
        """Lazy-initialize the LLM client via the provider factory.

        Returns None if no API key is configured for the selected provider,
        triggering fallback behavior.
        """
        if self._llm_client is None:
            self._llm_client = create_llm_client()
        return self._llm_client

    def _call_llm(
        self,
        system_prompt: str,
        query: str,
        context: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Call the LLM and return parsed JSON, or None on failure/fallback."""
        client = self._get_llm_client()
        if client is None:
            return None

        try:
            user_prompt = json.dumps({"query": query, "context": context}, default=str)
            # Try JSON mode first (supported by OpenAI-compatible APIs)
            content = client.chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=2000,
            )
            if content:
                return cast(dict[str, Any], json.loads(content))
        except Exception as e:
            logger.warning("LLM call failed, using fallback: %s", e)

        return None

    # ------------------------------------------------------------------
    # Main reasoning entry point
    # ------------------------------------------------------------------

    def reason(
        self,
        query: str,
        context: dict[str, Any],
        mode: ReasoningMode = ReasoningMode.DEDUCTIVE,
    ) -> dict[str, Any]:
        """Execute reasoning in the specified mode.

        Args:
            query: The question or topic to reason about.
            context: A dictionary of facts, observations, or data.
            mode: The reasoning mode to use.

        Returns:
            A structured result dict whose shape varies by mode but always
            includes "mode" and "confidence".
        """
        if mode == ReasoningMode.DEDUCTIVE:
            return self._deductive(query, context)
        elif mode == ReasoningMode.INDUCTIVE:
            return self._inductive(query, context)
        elif mode == ReasoningMode.ABDUCTIVE:
            return self._abductive(query, context)
        elif mode == ReasoningMode.ANALOGICAL:
            return self._analogical(query, context)
        else:
            return self._hybrid(query, context)

    # ------------------------------------------------------------------
    # Deductive reasoning (deterministic, rule-based)
    # ------------------------------------------------------------------

    def _deductive(self, query: str, context: dict[str, Any]) -> dict[str, Any]:
        """Apply rules against the context to derive conclusions."""
        conclusions: list[dict[str, Any]] = []
        for rule_type, rules in self._rules.items():
            for rule in rules:
                if self._evaluate_rule(rule, context):
                    conclusions.append({
                        "rule": rule.get("conclusion", ""),
                        "confidence": rule.get("confidence", 0.9),
                        "explanation": f"Applied rule: {rule.get('name', 'unknown')}",
                    })
        return {
            "query": query,
            "mode": "deductive",
            "conclusions": conclusions,
            "confidence": max((c["confidence"] for c in conclusions), default=0.0),
        }

    def _evaluate_rule(self, rule: dict[str, Any], context: dict[str, Any]) -> bool:
        """Check whether all conditions of a rule are satisfied by the context."""
        conditions = rule.get("conditions", [])
        for cond in conditions:
            prop = cond.get("property")
            expected = cond.get("value")
            if context.get(prop) != expected:
                return False
        return True

    # ------------------------------------------------------------------
    # Inductive reasoning (LLM-powered, fallback to mock)
    # ------------------------------------------------------------------

    def _inductive(self, query: str, context: dict[str, Any]) -> dict[str, Any]:
        """Discover patterns and generalizations from observations."""
        llm_result = self._call_llm(SYSTEM_PROMPTS["inductive"], query, context)
        if llm_result is not None:
            return {
                "query": query,
                "mode": "inductive",
                "patterns": llm_result.get("patterns", []),
                "confidence": llm_result.get("confidence", 0.5),
            }

        # Fallback when LLM unavailable
        logger.info("LLM unavailable for inductive mode; using fallback")
        return {
            "query": query,
            "mode": "inductive",
            "patterns": [{"pattern": "Generalized from observations", "support": 0.75, "evidence": ""}],
            "confidence": 0.75,
        }

    # ------------------------------------------------------------------
    # Abductive reasoning (LLM-powered, fallback to mock)
    # ------------------------------------------------------------------

    def _abductive(self, query: str, context: dict[str, Any]) -> dict[str, Any]:
        """Generate the most likely explanations for observed phenomena."""
        llm_result = self._call_llm(SYSTEM_PROMPTS["abductive"], query, context)
        if llm_result is not None:
            return {
                "query": query,
                "mode": "abductive",
                "explanations": llm_result.get("explanations", []),
                "confidence": llm_result.get("confidence", 0.5),
            }

        # Fallback when LLM unavailable
        logger.info("LLM unavailable for abductive mode; using fallback")
        return {
            "query": query,
            "mode": "abductive",
            "explanations": [
                {
                    "hypothesis": "Best explanation for observed facts",
                    "plausibility": 0.8,
                    "reasoning": "",
                }
            ],
            "confidence": 0.8,
        }

    # ------------------------------------------------------------------
    # Analogical reasoning (LLM-powered, fallback to mock)
    # ------------------------------------------------------------------

    def _analogical(self, query: str, context: dict[str, Any]) -> dict[str, Any]:
        """Find relevant analogies from other domains for a target situation."""
        llm_result = self._call_llm(SYSTEM_PROMPTS["analogical"], query, context)
        if llm_result is not None:
            return {
                "query": query,
                "mode": "analogical",
                "analogs": llm_result.get("analogs", []),
                "confidence": llm_result.get("confidence", 0.5),
            }

        # Fallback when LLM unavailable
        logger.info("LLM unavailable for analogical mode; using fallback")
        return {
            "query": query,
            "mode": "analogical",
            "analogs": [
                {
                    "source_domain": "known",
                    "target_domain": "current",
                    "similarity": 0.7,
                    "mapping": "",
                }
            ],
            "confidence": 0.7,
        }

    # ------------------------------------------------------------------
    # Hybrid reasoning (deductive + LLM inductive)
    # ------------------------------------------------------------------

    def _hybrid(self, query: str, context: dict[str, Any]) -> dict[str, Any]:
        """Combine deductive rule application with inductive pattern discovery."""
        deductive_result = self._deductive(query, context)
        inductive_result = self._inductive(query, context)

        return {
            "query": query,
            "mode": "hybrid",
            "results": {
                "deductive": deductive_result,
                "inductive": inductive_result,
            },
            "confidence": (
                deductive_result["confidence"] + inductive_result["confidence"]
            ) / 2,
        }


class ReasoningPipeline:
    """A pipeline that decomposes a query, routes to reasoners, and composes results.

    Useful for complex questions that benefit from multiple reasoning
    perspectives applied to different sub-queries.
    """

    def __init__(self) -> None:
        self.engine = ReasoningEngine()

    def execute(self, query: str, context: dict[str, Any]) -> dict[str, Any]:
        """Execute the full reasoning pipeline."""
        decomposed = self._decompose(query)
        results: dict[str, Any] = {}
        for sub_query, mode in decomposed:
            results[sub_query] = self.engine.reason(sub_query, context, mode)
        return self._compose(results)

    def _decompose(self, query: str) -> list[tuple[str, ReasoningMode]]:
        """Decompose a query into sub-queries with appropriate reasoning modes."""
        return [(query, ReasoningMode.DEDUCTIVE)]

    def _compose(self, results: dict[str, Any]) -> dict[str, Any]:
        """Combine individual reasoning results into a coherent answer."""
        return {"answer": str(results), "confidence": 0.8}
