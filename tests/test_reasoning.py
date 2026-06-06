"""Reasoning engine unit tests.

Tests cover:
- Deductive reasoning (rule-based, deterministic)
- Inductive/abductive/analogical reasoning (LLM-powered with fallback)
- Hybrid reasoning (deductive + inductive combined)
- Reasoning pipeline decomposition and composition
- LLM integration path (when API key is configured)
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from awren_reasoning.engine import ReasoningEngine, ReasoningMode, ReasoningPipeline


@pytest.fixture
def engine() -> ReasoningEngine:
    eng = ReasoningEngine()
    eng.add_rule("test", {
        "name": "capital_city_rule",
        "conditions": [
            {"property": "country", "value": "France"},
        ],
        "conclusion": "Capital is Paris",
        "confidence": 0.95,
    })
    return eng


class TestDeductiveReasoning:
    """Deterministic rule-based reasoning — no LLM needed."""

    def test_basic_deduction(self, engine: ReasoningEngine):
        result = engine.reason(
            "What is the capital of France?",
            {"country": "France"},
            mode=ReasoningMode.DEDUCTIVE,
        )
        assert result["mode"] == "deductive"
        assert len(result["conclusions"]) == 1
        assert "Paris" in result["conclusions"][0]["rule"]
        assert result["confidence"] == 0.95

    def test_no_match(self, engine: ReasoningEngine):
        result = engine.reason(
            "What is the capital of Germany?",
            {"country": "Germany"},
            mode=ReasoningMode.DEDUCTIVE,
        )
        assert len(result["conclusions"]) == 0
        assert result["confidence"] == 0.0

    def test_multiple_rules(self):
        eng = ReasoningEngine()
        eng.add_rule("risk", {
            "name": "high_risk",
            "conditions": [{"property": "budget", "value": "overrun"}],
            "conclusion": "High risk",
            "confidence": 0.9,
        })
        eng.add_rule("risk", {
            "name": "low_risk",
            "conditions": [{"property": "budget", "value": "on_track"}],
            "conclusion": "Low risk",
            "confidence": 0.8,
        })

        result = eng.reason("Assess risk", {"budget": "overrun"}, mode=ReasoningMode.DEDUCTIVE)
        assert len(result["conclusions"]) == 1
        assert "High risk" in result["conclusions"][0]["rule"]
        assert result["confidence"] == 0.9


class TestNonDeductiveFallback:
    """Inductive/abductive/analogical modes use LLM, fallback to mock when no API key."""

    def test_inductive_fallback(self, engine: ReasoningEngine):
        result = engine.reason(
            "Find patterns in data",
            {"data": [1, 2, 3]},
            mode=ReasoningMode.INDUCTIVE,
        )
        assert result["mode"] == "inductive"
        assert len(result["patterns"]) == 1
        assert result["patterns"][0]["pattern"] == "Generalized from observations"

    def test_abductive_fallback(self, engine: ReasoningEngine):
        result = engine.reason(
            "Explain the observation",
            {"observation": "wet ground"},
            mode=ReasoningMode.ABDUCTIVE,
        )
        assert result["mode"] == "abductive"
        assert len(result["explanations"]) == 1
        assert result["explanations"][0]["hypothesis"] == "Best explanation for observed facts"

    def test_analogical_fallback(self, engine: ReasoningEngine):
        result = engine.reason(
            "Find similar cases",
            {"current": "problem"},
            mode=ReasoningMode.ANALOGICAL,
        )
        assert result["mode"] == "analogical"
        assert len(result["analogs"]) == 1
        assert result["analogs"][0]["source_domain"] == "known"

    def test_hybrid_with_fallback(self, engine: ReasoningEngine):
        result = engine.reason(
            "Combined reasoning",
            {"country": "France"},
            mode=ReasoningMode.HYBRID,
        )
        assert result["mode"] == "hybrid"
        assert "deductive" in result["results"]
        assert "inductive" in result["results"]
        # Deductive finds the rule
        assert len(result["results"]["deductive"]["conclusions"]) == 1

    def test_all_modes_available(self, engine: ReasoningEngine):
        for mode in ReasoningMode:
            result = engine.reason("test", {}, mode=mode)
            assert result["mode"] == mode.value


class TestLLMIntegration:
    """Test that the LLM path is used when an LLM client is configured.

    We mock `_get_llm_client` directly to return a controlled mock client,
    bypassing the import chain and settings resolution.

    The mock client must expose a ``chat()`` method (the unified LLMClient
    interface), not the raw OpenAI ``chat.completions.create`` API.
    """

    @patch("awren_reasoning.engine.ReasoningEngine._get_llm_client")
    def test_inductive_llm_path(self, mock_get_client: MagicMock, engine: ReasoningEngine):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.chat.return_value = (
            '{"patterns": [{"pattern": "Revenue grows 20% QoQ", "support": 0.85, "evidence": "3 quarters of data"}], "confidence": 0.85}'
        )

        result = engine.reason(
            "Analyze revenue trends",
            {"revenue": [100, 120, 144]},
            mode=ReasoningMode.INDUCTIVE,
        )

        assert result["mode"] == "inductive"
        assert len(result["patterns"]) == 1
        assert result["patterns"][0]["pattern"] == "Revenue grows 20% QoQ"
        assert result["confidence"] == 0.85
        mock_client.chat.assert_called_once()

    @patch("awren_reasoning.engine.ReasoningEngine._get_llm_client")
    def test_abductive_llm_path(self, mock_get_client: MagicMock, engine: ReasoningEngine):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.chat.return_value = (
            '{"explanations": [{"hypothesis": "Budget overrun due to material cost spike", "plausibility": 0.9, "reasoning": "Steel prices increased 30% in Q2"}], "confidence": 0.9}'
        )

        result = engine.reason(
            "Why is the project over budget?",
            {"budget_status": "overrun", "costs": {"steel": "+30%"}},
            mode=ReasoningMode.ABDUCTIVE,
        )

        assert result["mode"] == "abductive"
        assert len(result["explanations"]) == 1
        assert "material cost" in result["explanations"][0]["hypothesis"].lower()

    @patch("awren_reasoning.engine.ReasoningEngine._get_llm_client")
    def test_analogical_llm_path(self, mock_get_client: MagicMock, engine: ReasoningEngine):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.chat.return_value = (
            '{"analogs": [{"source_domain": "aerospace", "target_domain": "construction", "similarity": 0.82, "mapping": "Quality assurance processes are transferable"}], "confidence": 0.82}'
        )

        result = engine.reason(
            "Find analogies for quality control",
            {"domain": "construction", "challenge": "inspection delays"},
            mode=ReasoningMode.ANALOGICAL,
        )

        assert result["mode"] == "analogical"
        assert len(result["analogs"]) == 1
        assert result["analogs"][0]["source_domain"] == "aerospace"

    @patch("awren_reasoning.engine.ReasoningEngine._get_llm_client")
    def test_llm_failure_fallback(self, mock_get_client: MagicMock, engine: ReasoningEngine):
        """When LLM raises an exception, should fall back gracefully."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.chat.return_value = None  # Simulate LLM failure

        result = engine.reason(
            "Analyze trends",
            {"data": [1, 2, 3]},
            mode=ReasoningMode.INDUCTIVE,
        )

        assert result["mode"] == "inductive"
        assert len(result["patterns"]) == 1  # Falls back to mock
        assert result["patterns"][0]["pattern"] == "Generalized from observations"


class TestReasoningPipeline:
    """Tests for query decomposition and composition."""

    def test_execute_pipeline(self):
        pipeline = ReasoningPipeline()
        pipeline.engine.add_rule("test", {
            "name": "rule_1",
            "conditions": [{"property": "x", "value": 1}],
            "conclusion": "Found match",
            "confidence": 0.9,
        })
        result = pipeline.execute("test query", {"x": 1})
        assert "answer" in result
        assert "confidence" in result
        assert result["confidence"] == 0.8


class TestEdgeCases:
    """Edge cases and error handling."""

    def test_empty_context(self, engine: ReasoningEngine):
        result = engine.reason("test", {}, mode=ReasoningMode.DEDUCTIVE)
        assert result["confidence"] == 0.0
        assert len(result["conclusions"]) == 0

    def test_empty_query(self, engine: ReasoningEngine):
        result = engine.reason("", {"country": "France"}, mode=ReasoningMode.DEDUCTIVE)
        assert result["confidence"] == 0.95  # Rules still match context
        assert len(result["conclusions"]) == 1

    def test_no_rules(self):
        eng = ReasoningEngine()
        result = eng.reason("test", {"country": "France"}, mode=ReasoningMode.DEDUCTIVE)
        assert result["confidence"] == 0.0
        assert len(result["conclusions"]) == 0
