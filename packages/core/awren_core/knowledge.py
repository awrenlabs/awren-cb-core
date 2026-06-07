"""Knowledge Graph Layer — insights, rules, and learned patterns.

Beyond the base ontology (entities + relationships), this layer captures:
- Insights: actionable conclusions derived from data analysis
- Rules: business logic, heuristics, and decision criteria
- Patterns: recurring structures, behaviors, or trends
- Learned knowledge: patterns discovered by the system over time
"""

import json
import time
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import select, func, text
from sqlalchemy.orm import Session

from awren_core.llm import create_llm_client
from awren_core.orm_models import (
    KnowledgeNodeModel,
    KnowledgeEdgeModel,
)
from awren_core.models import BaseEntity, BaseRelationship


class KnowledgeEngine:
    """Engine for managing the knowledge graph layer.

    Knowledge nodes represent insights, rules, or patterns.
    Knowledge edges represent relationships between knowledge nodes
    or between knowledge nodes and ontology entities.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Knowledge Node CRUD
    # ------------------------------------------------------------------

    async def create_node(
        self,
        kind: str,
        label: str,
        content: str,
        source: str = "system",
        confidence: float = 1.0,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        entity_ids: Optional[list[UUID]] = None,
    ) -> dict[str, Any]:
        """Create a knowledge node (insight, rule, or pattern).

        Avoids duplicates: if a node with the same (kind, label, source) exists,
        returns the existing node instead of creating a new one.

        Args:
            kind: 'insight', 'rule', or 'pattern'
            label: Short human-readable name
            content: The knowledge content (full description, rule text, etc.)
            source: Origin of the knowledge (system, llm, user, ingestion)
            confidence: How confident we are in this knowledge (0-1)
            tags: Categorization tags
            metadata: Additional structured data
            entity_ids: Related ontology entity IDs
        """
        from sqlalchemy import and_, func
        norm_label = label.strip().lower()
        all_nodes = self._session.execute(
            select(KnowledgeNodeModel).where(
                KnowledgeNodeModel.kind == kind,
                KnowledgeNodeModel.source == source,
            )
        ).scalars().all()
        for existing in all_nodes:
            if existing.label.strip().lower() == norm_label:
                return self._node_to_dict(existing)

        node = KnowledgeNodeModel(
            id=uuid4(),
            kind=kind,
            label=label,
            content=content,
            source=source,
            confidence=confidence,
            tags=tags or [],
            metadata_=metadata or {},
            entity_ids=[str(eid) for eid in (entity_ids or [])],
        )
        self._session.add(node)
        self._session.flush()
        return self._node_to_dict(node)

    async def get_node(self, node_id: UUID) -> Optional[dict[str, Any]]:
        node = self._session.get(KnowledgeNodeModel, node_id)
        return self._node_to_dict(node) if node else None

    async def list_nodes(
        self,
        kind: Optional[str] = None,
        source: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        stmt = select(KnowledgeNodeModel).order_by(
            KnowledgeNodeModel.created_at.desc()
        ).limit(limit).offset(offset)
        if kind:
            stmt = stmt.where(KnowledgeNodeModel.kind == kind)
        if source:
            stmt = stmt.where(KnowledgeNodeModel.source == source)
        if tag:
            stmt = stmt.where(KnowledgeNodeModel.tags.any(tag))
        nodes = self._session.execute(stmt).scalars().all()
        return [self._node_to_dict(n) for n in nodes]

    async def delete_node(self, node_id: UUID) -> bool:
        node = self._session.get(KnowledgeNodeModel, node_id)
        if not node:
            return False
        self._session.delete(node)
        self._session.flush()
        return True

    async def count_nodes(self, kind: Optional[str] = None) -> int:
        stmt = select(func.count(KnowledgeNodeModel.id))
        if kind:
            stmt = stmt.where(KnowledgeNodeModel.kind == kind)
        return self._session.execute(stmt).scalar() or 0

    # ------------------------------------------------------------------
    # Knowledge Edge CRUD
    # ------------------------------------------------------------------

    async def create_edge(
        self,
        source_id: UUID,
        target_id: UUID,
        relationship_type: str = "derives_from",
        confidence: float = 1.0,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Connect two knowledge nodes or a node to an ontology entity."""
        edge = KnowledgeEdgeModel(
            id=uuid4(),
            source_id=source_id,
            target_id=target_id,
            relationship_type=relationship_type,
            confidence=confidence,
            metadata_=metadata or {},
        )
        self._session.add(edge)
        self._session.flush()
        return self._edge_to_dict(edge)

    async def get_edges_for_node(self, node_id: UUID) -> list[dict[str, Any]]:
        stmt = select(KnowledgeEdgeModel).where(
            (KnowledgeEdgeModel.source_id == node_id) |
            (KnowledgeEdgeModel.target_id == node_id)
        )
        edges = self._session.execute(stmt).scalars().all()
        return [self._edge_to_dict(e) for e in edges]

    async def delete_edge(self, edge_id: UUID) -> bool:
        edge = self._session.get(KnowledgeEdgeModel, edge_id)
        if not edge:
            return False
        self._session.delete(edge)
        self._session.flush()
        return True

    # ------------------------------------------------------------------
    # LLM-powered knowledge extraction
    # ------------------------------------------------------------------

    async def extract_insights_from_text(
        self,
        text: str,
        source: str = "ingestion",
        max_insights: int = 5,
    ) -> list[dict[str, Any]]:
        """Extract insights, rules, and patterns from text using LLM.

        Returns created knowledge nodes.
        """
        llm = create_llm_client(db_session=self._session)
        if not llm:
            return []

        prompt = (
            f"Analyze the following text and extract up to {max_insights} "
            "knowledge items. For each, classify as:\n"
            "- 'insight': a non-obvious conclusion or trend\n"
            "- 'rule': a business logic rule, constraint, or heuristic\n"
            "- 'pattern': a recurring structure or behavior\n\n"
            f"Text:\n{text[:8000]}\n\n"
            "Return a JSON array of objects with:\n"
            "- kind: 'insight' | 'rule' | 'pattern'\n"
            "- label: short name (max 80 chars)\n"
            "- content: full description (2-5 sentences)\n"
            "- confidence: float 0-1\n"
            "- tags: array of strings\n"
        )

        try:
            raw = llm.chat(system_prompt="You are a knowledge extraction engine.", user_prompt=prompt, temperature=0.3)
            if not raw:
                return []
            items = self._parse_json_list(raw)
            created = []
            for item in items[:max_insights]:
                node = await self.create_node(
                    kind=item.get("kind", "insight"),
                    label=item.get("label", "Unlabeled insight"),
                    content=item.get("content", ""),
                    source=source,
                    confidence=float(item.get("confidence", 0.7)),
                    tags=item.get("tags", []),
                )
                created.append(node)
            return created
        except Exception:
            return []

    async def extract_rules_from_entities(
        self,
        entities: list[BaseEntity],
        relationships: list[BaseRelationship],
    ) -> list[dict[str, Any]]:
        """Analyze entities and relationships to infer business rules."""
        if not entities:
            return []

        llm = create_llm_client(db_session=self._session)
        if not llm:
            return []

        context = {
            "entities": [{"id": str(e.id), "type": e.type, "label": e.label} for e in entities[:20]],
            "relationships": [
                {"type": r.type, "source": str(r.source_id), "target": str(r.target_id)}
                for r in relationships[:20]
            ],
        }

        prompt = (
            f"Analyze this knowledge graph snapshot and infer up to 5 business rules "
            "or domain patterns:\n\n"
            f"{json.dumps(context, indent=2)}\n\n"
            "Return a JSON array of objects:\n"
            "- kind: 'rule' | 'pattern'\n"
            "- label: short name\n"
            "- content: the rule/pattern description\n"
            "- confidence: float 0-1\n"
            "- tags: array of strings\n"
        )

        try:
            raw = llm.chat(system_prompt="You are a business rule extraction engine.", user_prompt=prompt, temperature=0.3)
            if not raw:
                return []
            items = self._parse_json_list(raw)
            created = []
            for item in items[:5]:
                node = await self.create_node(
                    kind=item.get("kind", "rule"),
                    label=item.get("label", "Unlabeled rule"),
                    content=item.get("content", ""),
                    source="knowledge_engine",
                    confidence=float(item.get("confidence", 0.7)),
                    tags=item.get("tags", []),
                    entity_ids=[e.id for e in entities[:10]],
                )
                created.append(node)
            return created
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    async def query_knowledge(
        self,
        query: str,
        kinds: Optional[list[str]] = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search knowledge nodes by content similarity (basic text match).

        Deduplicates by node ID in Python to handle repeated rows safely.
        """
        stmt = select(KnowledgeNodeModel)

        if kinds:
            stmt = stmt.where(KnowledgeNodeModel.kind.in_(kinds))

        results = self._session.execute(stmt).scalars().all()

        # Deduplicate by ID (safety: avoids issues with JSON columns + DISTINCT)
        seen: dict[UUID, KnowledgeNodeModel] = {}
        for r in results:
            if r.id not in seen:
                seen[r.id] = r
        unique = list(seen.values())

        if not query.strip():
            unique.sort(key=lambda r: r.created_at or datetime.min, reverse=True)
            return [self._node_to_dict(r) for r in unique[:limit]]

        # Simple relevance scoring -- prefer label/content match
        query_lower = query.lower()
        scored = {}
        for r in unique:
            score = 0.0
            if query_lower in r.label.lower():
                score += 0.5
            if query_lower in r.content.lower():
                score += 0.3
            if query_lower in " ".join(r.tags or []).lower():
                score += 0.2
            if score > 0:
                scored[r.id] = (score, r)

        sorted_nodes = sorted(scored.values(), key=lambda x: -x[0])
        return [self._node_to_dict(r) for _, r in sorted_nodes[:limit]]

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    async def get_stats(self) -> dict[str, Any]:
        total = await self.count_nodes()
        insights = await self.count_nodes(kind="insight")
        rules = await self.count_nodes(kind="rule")
        patterns = await self.count_nodes(kind="pattern")
        edge_count = self._session.execute(
            select(func.count(KnowledgeEdgeModel.id))
        ).scalar() or 0
        return {
            "total_nodes": total,
            "insights": insights,
            "rules": rules,
            "patterns": patterns,
            "total_edges": edge_count,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _node_to_dict(self, node: KnowledgeNodeModel) -> dict[str, Any]:
        return {
            "id": str(node.id),
            "kind": node.kind,
            "label": node.label,
            "content": node.content[:500],
            "source": node.source,
            "confidence": node.confidence,
            "tags": node.tags or [],
            "entity_ids": [str(eid) for eid in (node.entity_ids or [])],
            "metadata": node.metadata_ or {},
            "created_at": node.created_at.isoformat() if node.created_at else None,
        }

    def _edge_to_dict(self, edge: KnowledgeEdgeModel) -> dict[str, Any]:
        return {
            "id": str(edge.id),
            "source_id": str(edge.source_id),
            "target_id": str(edge.target_id),
            "relationship_type": edge.relationship_type,
            "confidence": edge.confidence,
            "metadata": edge.metadata_ or {},
            "created_at": edge.created_at.isoformat() if edge.created_at else None,
        }

    def _parse_json_list(self, raw: str) -> list[dict]:
        """Extract a JSON array from LLM response, handling markdown fences."""
        import re
        for match in re.finditer(r'```(?:json)?\s*(\[[\s\S]*?\])\s*```', raw):
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return []
