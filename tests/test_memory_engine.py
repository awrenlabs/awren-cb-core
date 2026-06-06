"""Memory engine unit tests."""

from uuid import uuid4

import pytest

from awren_memory.engine import MemoryEngine
from awren_memory.models import (
    EpisodicMemory,
    ProceduralMemory,
    SemanticMemory,
    WorkingMemory,
)


class TestMemoryEngine:
    def test_store_and_retrieve_semantic(self):
        engine = MemoryEngine()
        memory = SemanticMemory(
            content="Paris is the capital of France",
            facts={"capital_of": "France"},
            entity_id=uuid4(),
        )
        mem_id = engine.store(memory.model_dump(mode="json"), memory_type="semantic")
        retrieved = engine.retrieve(mem_id, memory_type="semantic")
        assert retrieved is not None
        assert retrieved["content"] == "Paris is the capital of France"

    def test_store_and_retrieve_episodic(self):
        engine = MemoryEngine()
        memory = EpisodicMemory(
            content="Meeting with stakeholders",
            participants=["Alice", "Bob"],
            event_id=uuid4(),
        )
        mem_id = engine.store(memory.model_dump(mode="json"), memory_type="episodic")
        retrieved = engine.retrieve(mem_id, memory_type="episodic")
        assert retrieved is not None
        assert "stakeholders" in retrieved["content"]

    def test_store_and_retrieve_procedural(self):
        engine = MemoryEngine()
        memory = ProceduralMemory(
            content="Deploy pipeline steps",
            steps=[{"step": 1, "action": "build"}, {"step": 2, "action": "test"}],
            workflow_id="deploy-v1",
        )
        mem_id = engine.store(memory.model_dump(mode="json"), memory_type="procedural")
        retrieved = engine.retrieve(mem_id, memory_type="procedural")
        assert retrieved is not None
        assert len(retrieved["steps"]) == 2

    def test_store_and_retrieve_working(self):
        engine = MemoryEngine()
        memory = WorkingMemory(
            content="Current session context",
            session_id="session-123",
            ttl=1800,
        )
        mem_id = engine.store(memory.model_dump(mode="json"), memory_type="working")
        retrieved = engine.retrieve(mem_id, memory_type="working")
        assert retrieved is not None
        assert retrieved["session_id"] == "session-123"

    def test_retrieve_nonexistent(self):
        engine = MemoryEngine()
        result = engine.retrieve("nonexistent-id")
        assert result is None

    def test_query_memory(self):
        engine = MemoryEngine()
        engine.store({"id": "1", "content": "The sky is blue"}, memory_type="semantic")
        engine.store({"id": "2", "content": "Grass is green"}, memory_type="semantic")
        engine.store({"id": "3", "content": "Ocean is blue"}, memory_type="semantic")

        results = engine.query("blue")
        assert len(results) == 2

        results = engine.query("green")
        assert len(results) == 1

    def test_query_with_limit(self):
        engine = MemoryEngine()
        for i in range(5):
            engine.store({"id": str(i), "content": f"Item {i}"}, memory_type="semantic")

        results = engine.query("Item", limit=3)
        assert len(results) == 3

    def test_search_across_types(self):
        engine = MemoryEngine()
        engine.store({"id": "s1", "content": "Semantic fact"}, memory_type="semantic")
        engine.store({"id": "e1", "content": "Episodic event"}, memory_type="episodic")

        results = engine.query("Semantic")
        assert len(results) == 1

        results = engine.query("event")
        assert len(results) == 1


class TestMemoryModels:
    def test_episodic_memory_defaults(self):
        mem = EpisodicMemory(content="Test event")
        assert mem.memory_type == "episodic"
        assert len(mem.participants) == 0
        assert mem.confidence == 1.0

    def test_semantic_memory(self):
        mem = SemanticMemory(content="Fact", facts={"key": "value"})
        assert mem.facts["key"] == "value"

    def test_procedural_memory(self):
        mem = ProceduralMemory(
            content="Process",
            steps=[{"name": "Step 1"}],
        )
        assert len(mem.steps) == 1

    def test_working_memory_ttl(self):
        mem = WorkingMemory(content="Context", session_id="abc")
        assert mem.ttl == 3600  # default
        assert mem.session_id == "abc"
