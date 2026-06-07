"""Causal Reasoning Engine — multi-hop causal chain analysis.

Enables querying and discovering cause-effect relationships across
the knowledge graph, supporting:
- Forward chaining: "What does X cause?"
- Backward chaining: "What causes Y?"
- Multi-hop traversal: "A → B → C → D"
- Causal path analysis with confidence scoring
"""

import json
import time
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from awren_core.llm import create_llm_client
from awren_core.orm_models import (
    CausalChainModel,
    EntityModel,
    RelationshipModel,
)


class CausalEngine:
    """Engine for causal reasoning across the knowledge graph.

    Discovers and traverses cause-effect chains using:
    1. Explicit causal relationships in the graph (type: 'causes', 'enables', 'prevents', etc.)
    2. LLM-inferred causal links from entity descriptions and relationships
    3. Multi-hop traversal with confidence decay
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Causal Chain CRUD
    # ------------------------------------------------------------------

    async def record_chain(
        self,
        head_id: UUID,
        chain: list[dict[str, Any]],
        confidence: float = 1.0,
        source: str = "system",
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Record a discovered causal chain.

        Args:
            head_id: The root cause entity ID
            chain: List of hops — each is {"entity_id": UUID, "entity_label": str, "relationship": str}
            confidence: Overall confidence in this chain
            source: How it was discovered (llm, rule, manual)
            metadata: Additional context
        """
        chain_model = CausalChainModel(
            id=uuid4(),
            head_id=head_id,
            chain=chain,
            confidence=confidence,
            source=source,
            metadata_=metadata or {},
        )
        self._session.add(chain_model)
        self._session.flush()
        return self._chain_to_dict(chain_model)

    async def get_chain(self, chain_id: UUID) -> Optional[dict[str, Any]]:
        chain = self._session.get(CausalChainModel, chain_id)
        return self._chain_to_dict(chain) if chain else None

    def _chain_to_dict(self, chain: CausalChainModel) -> dict[str, Any]:
        return {
            "id": str(chain.id),
            "head_id": str(chain.head_id),
            "chain": chain.chain,
            "confidence": chain.confidence,
            "source": chain.source,
            "metadata": chain.metadata_ or {},
            "created_at": chain.created_at.isoformat() if chain.created_at else None,
        }

    async def list_chains(
        self,
        entity_id: Optional[UUID] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        stmt = select(CausalChainModel).order_by(
            CausalChainModel.confidence.desc()
        ).limit(limit).offset(offset)
        if entity_id:
            stmt = stmt.where(
                (CausalChainModel.head_id == entity_id) |
                (CausalChainModel.chain["entity_id"].as_string() == str(entity_id))
            )
        chains = self._session.execute(stmt).scalars().all()
        return [self._chain_to_dict(c) for c in chains]

    # ------------------------------------------------------------------
    # Causal Discovery
    # ------------------------------------------------------------------

    async def forward_chain(
        self,
        entity_id: UUID,
        max_hops: int = 5,
        min_confidence: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Forward chaining: given an entity, what does it cause?

        Traverses relationships to find downstream effects.
        """
        from sqlalchemy import text as sa_text

        # Get entity label
        entity = self._session.get(EntityModel, entity_id)
        if not entity:
            return []

        # BFS traversal following causal relationships
        causal_types = ["causes", "enables", "triggers", "leads_to", "produces", "results_in",
                        "core:causes", "core:enables", "core:produces"]
        visited: set[UUID] = {entity_id}
        chain = [{"entity_id": str(entity_id), "entity_label": entity.label, "relationship": "start"}]
        queue: list[tuple[UUID, int]] = [(entity_id, 0)]

        chains_found = []

        while queue:
            current_id, depth = queue.pop(0)
            if depth >= max_hops:
                continue

            # Follow outgoing relationships of causal types
            stmt = select(RelationshipModel).where(
                RelationshipModel.source_id == current_id,
                RelationshipModel.type.in_(causal_types),
            )
            rels = self._session.execute(stmt).scalars().all()

            for rel in rels:
                target = self._session.get(EntityModel, rel.target_id)
                if target and rel.target_id not in visited:
                    visited.add(rel.target_id)
                    new_chain = chain + [{
                        "entity_id": str(rel.target_id),
                        "entity_label": target.label,
                        "relationship": rel.type,
                    }]
                    chains_found.append({
                        "chain": new_chain,
                        "confidence": min(1.0, rel.metadata_.get("confidence", 0.5) if rel.metadata_ else 0.5),
                        "hops": len(new_chain) - 1,
                    })
                    queue.append((rel.target_id, depth + 1))

        # Also follow incoming relationships (reverse causal)
        stmt = select(RelationshipModel).where(
            RelationshipModel.target_id == entity_id,
            RelationshipModel.type.in_(causal_types),
        )
        rels = self._session.execute(stmt).scalars().all()
        for rel in rels:
            source = self._session.get(EntityModel, rel.source_id)
            if source and rel.source_id not in visited:
                visited.add(rel.source_id)
                reverse_chain = [{
                    "entity_id": str(rel.source_id),
                    "entity_label": source.label,
                    "relationship": f"reverse_{rel.type}",
                }] + chain
                chains_found.append({
                    "chain": reverse_chain,
                    "confidence": min(1.0, rel.metadata_.get("confidence", 0.4) if rel.metadata_ else 0.4),
                    "hops": len(reverse_chain) - 1,
                })

        chains_found.sort(key=lambda x: -x["confidence"])
        return [c for c in chains_found if c["confidence"] >= min_confidence]

    async def backward_chain(
        self,
        entity_id: UUID,
        max_hops: int = 5,
        min_confidence: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Backward chaining: given an entity, what causes it?

        Traverses relationships backward to find root causes.
        """
        # Reverse: look for relationships that point TO this entity
        causal_types = ["causes", "enables", "triggers", "leads_to", "produces", "results_in",
                        "core:causes", "core:enables", "core:produces"]

        entity = self._session.get(EntityModel, entity_id)
        if not entity:
            return []

        chain = [{"entity_id": str(entity_id), "entity_label": entity.label, "relationship": "target"}]
        visited: set[UUID] = {entity_id}
        chains_found = []
        queue: list[tuple[UUID, int]] = [(entity_id, 0)]

        while queue:
            current_id, depth = queue.pop(0)
            if depth >= max_hops:
                continue

            stmt = select(RelationshipModel).where(
                RelationshipModel.target_id == current_id,
                RelationshipModel.type.in_(causal_types),
            )
            rels = self._session.execute(stmt).scalars().all()

            for rel in rels:
                source = self._session.get(EntityModel, rel.source_id)
                if source and rel.source_id not in visited:
                    visited.add(rel.source_id)
                    new_chain = [{
                        "entity_id": str(rel.source_id),
                        "entity_label": source.label,
                        "relationship": rel.type,
                    }] + chain
                    chains_found.append({
                        "chain": new_chain,
                        "confidence": min(1.0, rel.metadata_.get("confidence", 0.5) if rel.metadata_ else 0.5),
                        "hops": len(new_chain) - 1,
                    })
                    queue.append((rel.source_id, depth + 1))

        chains_found.sort(key=lambda x: -x["confidence"])
        return [c for c in chains_found if c["confidence"] >= min_confidence]

    async def llm_causal_analysis(
        self,
        entity_id: UUID,
        max_chains: int = 5,
    ) -> list[dict[str, Any]]:
        """Use LLM to infer causal relationships from entity data.

        Analyzes entity descriptions and relationships to suggest
        causal chains not explicitly in the graph.
        """
        entity = self._session.get(EntityModel, entity_id)
        if not entity:
            return []

        # Gather entity context
        related_entities = self._session.execute(
            select(EntityModel).limit(10)
        ).scalars().all()

        related_rels = self._session.execute(
            select(RelationshipModel).where(
                (RelationshipModel.source_id == entity_id) |
                (RelationshipModel.target_id == entity_id)
            ).limit(20)
        ).scalars().all()

        context = {
            "target_entity": {"id": str(entity.id), "type": entity.type, "label": entity.label, "description": entity.description},
            "related_entities": [{"id": str(e.id), "type": e.type, "label": e.label} for e in related_entities if e.id != entity_id][:10],
            "relationships": [
                {"type": r.type, "source": str(r.source_id), "target": str(r.target_id)}
                for r in related_rels
            ],
        }

        llm = create_llm_client(db_session=self._session)
        if not llm:
            return []

        prompt = (
            f"Analyze the following knowledge graph context and identify up to {max_chains} "
            "causal chains. A causal chain is a sequence where each entity "
            "causes, enables, or influences the next.\n\n"
            f"{json.dumps(context, indent=2)}\n\n"
            "Return a JSON array of objects:\n"
            "- chain: array of {\"entity_label\": str, \"entity_id\": str (if known), \"relationship\": str}\n"
            "- confidence: float 0-1\n"
            "- reasoning: str (why you think this chain exists)\n"
        )

        try:
            raw = llm.chat(system_prompt="You are a causal analysis engine.", user_prompt=prompt, temperature=0.3)
            if not raw:
                return []
            return self._parse_json_list(raw)
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Multi-hop reasoning
    # ------------------------------------------------------------------

    async def find_paths(
        self,
        source_id: UUID,
        target_id: UUID,
        max_hops: int = 6,
    ) -> list[dict[str, Any]]:
        """Find causal paths between two entities.

        Uses BFS through relationships of all types, then filters
        to the most causally-relevant paths.
        """
        from collections import deque

        # BFS to find all paths
        visited: set[UUID] = set()
        queue = deque()
        queue.append((source_id, [source_id], []))
        visited.add(source_id)
        paths = []

        while queue:
            current_id, path_ids, path_rels = queue.popleft()
            if len(path_ids) > max_hops:
                continue

            if current_id == target_id and len(path_ids) > 1:
                # Found a path
                path_entities = []
                for pid in path_ids:
                    e = self._session.get(EntityModel, pid)
                    if e:
                        path_entities.append({"id": str(pid), "label": e.label})
                paths.append({
                    "path": path_entities,
                    "relationships": path_rels,
                    "hops": len(path_ids) - 1,
                })
                continue

            # Get outgoing relationships
            rels = self._session.execute(
                select(RelationshipModel).where(
                    RelationshipModel.source_id == current_id
                )
            ).scalars().all()

            for rel in rels:
                if rel.target_id not in visited or rel.target_id == target_id:
                    new_visited = visited | {rel.target_id}
                    # Use a new visited set for each branch
                    queue.append(
                        (rel.target_id, path_ids + [rel.target_id], path_rels + [rel.type])
                    )

        paths.sort(key=lambda x: x["hops"])
        return paths[:10]

    async def auto_discover_chains(
        self,
        entity_ids: list[UUID],
        max_hops: int = 4,
        max_chains: int = 50,
    ) -> list[dict[str, Any]]:
        """Auto-discover and record causal chains from entities.

        Called automatically after ingestion to populate causal relationships.

        Args:
            entity_ids: Newly created entity IDs to analyze
            max_hops: Maximum chain depth
            max_chains: Maximum chains to record

        Returns:
            List of recorded chain dicts
        """
        recorded = []
        for eid in entity_ids:
            # Forward chains
            chains = await self.forward_chain(eid, max_hops=max_hops, min_confidence=0.0)
            for c in chains:
                existing = self._session.execute(
                    select(CausalChainModel).where(CausalChainModel.head_id == eid).limit(1)
                ).first()
                if existing:
                    continue
                chain = await self.record_chain(
                    head_id=eid,
                    chain=c["chain"],
                    confidence=c["confidence"],
                    source="ingestion_auto",
                    metadata={"auto_discovered": True, "hop_count": c["hops"]},
                )
                recorded.append(chain)
                if len(recorded) >= max_chains:
                    return recorded

            # Backward chains
            chains = await self.backward_chain(eid, max_hops=max_hops, min_confidence=0.0)
            for c in chains:
                existing = self._session.execute(
                    select(CausalChainModel).where(
                        CausalChainModel.head_id == UUID(c["chain"][0]["entity_id"])
                    ).limit(1)
                ).first()
                if existing:
                    continue
                chain = await self.record_chain(
                    head_id=UUID(c["chain"][0]["entity_id"]),
                    chain=c["chain"],
                    confidence=c["confidence"],
                    source="ingestion_auto",
                    metadata={"auto_discovered": True, "hop_count": c["hops"]},
                )
                recorded.append(chain)
                if len(recorded) >= max_chains:
                    return recorded

        return recorded

    def _parse_json_list(self, raw: str) -> list[dict]:
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
