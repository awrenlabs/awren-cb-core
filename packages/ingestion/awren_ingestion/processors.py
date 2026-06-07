"""Document processing and entity extraction pipeline."""

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Optional
from uuid import UUID, uuid4

from awren_core.llm import create_llm_client
from awren_core.models import BaseEntity, BaseRelationship
from awren_core.ontology.engine import OntologyEngine
from awren_core.orm_models import ImportJobModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from awren_ingestion.extractors import extract_text

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(os.environ.get("AWREN_UPLOAD_DIR", "/tmp/awren_uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".csv", ".json", ".txt", ".md", ".xml", ".html"}

_ENTITY_EXTRACTION_PROMPT = """You are an ontology extraction engine. Analyze the following document text and extract all business entities and their relationships.

For each entity, identify:
1. The entity type (choose from: {types})
2. A clear label/name
3. Properties specific to that type (e.g., for Person: email, role; for Project: budget, start_date; for Organization: legal_name, industry)
4. A suggested state based on the entity lifecycle

For each relationship between entities, identify:
1. The relationship type (choose from: owns, employs, participatesIn, locatedAt, produces, investsIn, collaboratesWith, references, manages, reportsTo)
2. The source entity and target entity

Return ONLY valid JSON with this exact structure:
{{
  "entities": [
    {{"type": "core:Person", "label": "John Doe", "properties": {{"email": "john@example.com", "role": "Manager"}}, "state": "active"}}
  ],
  "relationships": [
    {{"type": "core:manages", "source_label": "John Doe", "target_label": "Acme Corp"}}
  ]
}}

Document text:
{text}"""


class DocumentProcessor:
    """Processes uploaded documents: extract text → LLM extraction → create entities."""

    def __init__(self, session: Session):
        self._session = session
        self._ontology = OntologyEngine(session)

    async def process(self, job_id: UUID, file_path: str, original_filename: str) -> dict:
        """Process an uploaded document. Returns result summary."""
        result = {
            "entities_created": 0,
            "relationships_created": 0,
            "entity_ids": [],
            "errors": [],
        }

        # 1. Extract text
        try:
            raw_text = extract_text(file_path)
        except Exception as e:
            result["errors"].append(f"Text extraction failed: {e}")
            return result

        if not raw_text.strip():
            result["errors"].append("No text content extracted from file")
            return result

        # 2. Get available ontology types for the LLM prompt
        types = await self._ontology.list_types()
        type_names = [t["name"] for t in types]
        if not type_names:
            type_names = ["core:Person", "core:Organization", "core:Project", "core:Document", "core:Location"]

        # 3. Extract entities via LLM
        try:
            extracted = await self._extract_via_llm(raw_text, type_names)
        except Exception as e:
            result["errors"].append(f"LLM extraction failed: {e}")
            return result

        if not extracted:
            result["errors"].append("No entities extracted from document")
            return result

        # 4. Create entities
        entity_map = {}  # label -> entity_id
        for ent in extracted.get("entities", []):
            try:
                entity = BaseEntity(
                    type=ent.get("type", "core:Document"),
                    label=ent.get("label", "Unknown"),
                    description=ent.get("description", None),
                    properties=ent.get("properties", {}),
                    state=ent.get("state", None),
                    provenance={"source": original_filename, "extracted_by": "llm", "import_job": str(job_id)},
                )
                from awren_core.services import EventService
                svc = EventService(self._session)
                created = await svc.create_entity(entity)
                entity_map[ent["label"]] = created.id
                result["entities_created"] += 1
                result["entity_ids"].append(str(created.id))
            except Exception as e:
                result["errors"].append(f"Failed to create entity '{ent.get('label', '?')}': {e}")

        # 5. Create relationships
        for rel in extracted.get("relationships", []):
            source_label = rel.get("source_label", "")
            target_label = rel.get("target_label", "")
            source_id = entity_map.get(source_label)
            target_id = entity_map.get(target_label)
            if source_id and target_id:
                try:
                    relationship = BaseRelationship(
                        type=f"core:{rel.get('type', 'references').replace('core:', '')}",
                        source_id=source_id,
                        target_id=target_id,
                        properties={"extracted_from": original_filename},
                    )
                    from awren_core.services import EventService
                    svc = EventService(self._session)
                    await svc.create_relationship(relationship)
                    result["relationships_created"] += 1
                except Exception as e:
                    result["errors"].append(f"Failed to create relationship '{rel.get('type', '?')}': {e}")
            elif source_label and target_label:
                result["errors"].append(f"Could not resolve relationship: {source_label} → {target_label}")

        # 6. Auto-generate knowledge nodes (insights/rules/patterns) from extracted text
        try:
            from awren_core.knowledge import KnowledgeEngine
            from awren_core.orm_models import EntityModel, RelationshipModel
            ke = KnowledgeEngine(self._session)
            created_entities = []
            for eid_str in result["entity_ids"]:
                e = self._session.get(EntityModel, UUID(eid_str))
                if e:
                    created_entities.append(e)
            knowledge_nodes = await ke.extract_insights_from_text(
                text=raw_text[:12000],
                source="ingestion",
                max_insights=5,
            )
            if knowledge_nodes:
                result["knowledge_nodes_created"] = len(knowledge_nodes)
                for kn in knowledge_nodes:
                    for e in created_entities[:10]:
                        await ke.create_edge(
                            source_id=UUID(kn["id"]),
                            target_id=e.id,
                            relationship_type="derives_from",
                        )
            if created_entities:
                stmt = select(RelationshipModel).where(
                    RelationshipModel.source_id.in_([e.id for e in created_entities])
                )
                entity_rels = self._session.execute(stmt).scalars().all()
                rule_nodes = await ke.extract_rules_from_entities(
                    entities=created_entities,
                    relationships=list(entity_rels),
                )
                if rule_nodes:
                    result["rules_created"] = len(rule_nodes)
        except Exception as e:
            logger.warning("Knowledge extraction failed: %s", e)
            result["errors"].append(f"Knowledge extraction: {e}")

        # 7. Auto-discover causal chains from new entities
        try:
            from awren_core.causality import CausalEngine
            ce = CausalEngine(self._session)
            entity_uuids = [UUID(eid_str) for eid_str in result["entity_ids"]]
            chains = await ce.auto_discover_chains(entity_uuids, max_hops=4, max_chains=50)
            if chains:
                result["causal_chains_created"] = len(chains)
        except Exception as e:
            logger.warning("Causal discovery failed: %s", e)
            result["errors"].append(f"Causal discovery: {e}")

        return result

    async def _extract_via_llm(self, text: str, type_names: list[str]) -> dict:
        """Use LLM to extract entities and relationships from text."""
        llm = create_llm_client(db_session=self._session)
        if not llm:
            # Fallback: extract as a single Document entity
            return {
                "entities": [{
                    "type": "core:Document",
                    "label": f"Imported Document ({len(text)} chars)",
                    "properties": {"content_preview": text[:500]},
                }],
                "relationships": [],
            }

        prompt = _ENTITY_EXTRACTION_PROMPT.format(
            types=", ".join(type_names),
            text=text[:8000],  # Limit to avoid token overflow
        )

        try:
            raw = llm.chat(
                system_prompt="You are an ontology extraction engine. Return ONLY valid JSON.",
                user_prompt=prompt,
                temperature=0.1,
                max_tokens=4096,
            )
            # Parse JSON from response
            return self._parse_llm_json(raw)
        except Exception as e:
            logger.warning("LLM extraction failed: %s", e)
            return {"entities": [], "relationships": []}

    def _parse_llm_json(self, raw: str) -> dict:
        """Extract JSON from LLM response (handles markdown fences)."""
        # Strip markdown code fences
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            if "```" in text:
                text = text.rsplit("```", 1)[0]
        text = text.strip()

        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON block
        import re
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return {"entities": [], "relationships": []}


def save_upload(file_bytes: bytes, original_filename: str) -> str:
    """Save uploaded file to disk and return the path."""
    # Sanitize filename
    safe_name = Path(original_filename).name
    dest = UPLOAD_DIR / f"{uuid4().hex}_{safe_name}"
    dest.write_bytes(file_bytes)
    return str(dest)


def is_allowed_file(filename: str) -> bool:
    """Check if file extension is allowed."""
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_EXTENSIONS or not ext  # Allow no-extension files as text
