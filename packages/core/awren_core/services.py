"""Domain services that wrap repositories with event sourcing."""

import json as _json
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from awren_core.llm import LLMClient, create_llm_client
from awren_core.models import BaseEntity, BaseEvent, BaseRelationship, EventType
from awren_core.ontology.engine import OntologyEngine
from awren_core.repositories import (
    ConversationRepository,
    EntityRepository,
    EventRepository,
    LlmSettingsRepository,
    MessageRepository,
    RelationshipRepository,
)


class EventService:
    """Wraps entity operations and automatically records events (event sourcing).

    Every create, update, and delete operation generates an event in the
    append-only event log, enabling full auditability and state replay.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._entity_repo = EntityRepository(session)
        self._event_repo = EventRepository(session)
        self._rel_repo = RelationshipRepository(session)
        self._llm_settings_repo = LlmSettingsRepository(session)
        self._conv_repo = ConversationRepository(session)
        self._msg_repo = MessageRepository(session)
        self._ontology = OntologyEngine(session)

    # ------------------------------------------------------------------
    # Entity operations with automatic event recording
    # ------------------------------------------------------------------

    async def create_entity(self, entity: BaseEntity) -> BaseEntity:
        """Create an entity with ontology validation, defaults, and version snapshot."""
        # Apply default state from ontology type
        type_def = await self._ontology._type_repo.get_by_name(entity.type)
        if type_def:
            if entity.state is None and type_def.states:
                entity.state = type_def.states[0]
            # Apply default property values
            props = await self._ontology._prop_repo.list_by_type(type_def.id)
            for prop in props:
                if prop.name not in entity.properties and prop.default_value is not None:
                    entity.properties[prop.name] = prop.default_value

        created = await self._entity_repo.create(entity)
        event = BaseEvent(
            type=EventType.ENTITY_CREATED.value,
            source="api",
            subject_id=created.id,
            payload={
                "entity_type": created.type,
                "label": created.label,
                "properties": created.properties,
                "state": created.state,
            },
        )
        await self._event_repo.create(event)
        # Create initial version snapshot
        await self._ontology._create_version_snapshot(created.id, "Entity created")
        return created

    async def get_entity(self, entity_id: UUID) -> Optional[BaseEntity]:
        """Retrieve an entity by ID (read-only, no event recorded)."""
        return await self._entity_repo.get(entity_id)

    async def update_entity(self, entity: BaseEntity, changes: Optional[dict[str, Any]] = None) -> BaseEntity:
        """Update an entity, record event, and create version snapshot."""
        old = await self._entity_repo.get(entity.id)
        if old:
            entity.version_num = old.version_num + 1 if old.version_num else 1
        updated = await self._entity_repo.update(entity)
        event = BaseEvent(
            type=EventType.ENTITY_UPDATED.value,
            source="api",
            subject_id=updated.id,
            payload={
                "changes": changes or {},
                "previous_state": {
                    "label": old.label if old else None,
                    "description": old.description if old else None,
                } if old else {},
            },
        )
        await self._event_repo.create(event)
        await self._ontology._create_version_snapshot(updated.id, "Entity updated")
        return updated

    async def delete_entity(self, entity_id: UUID) -> None:
        """Delete an entity and record an EntityArchived event."""
        entity = await self._entity_repo.get(entity_id)
        if entity is None:
            raise ValueError(f"Entity {entity_id} not found")
        await self._entity_repo.delete(entity_id)
        event = BaseEvent(
            type=EventType.ENTITY_ARCHIVED.value,
            source="api",
            subject_id=entity_id,
            payload={
                "entity_type": entity.type,
                "label": entity.label,
            },
        )
        await self._event_repo.create(event)

    async def list_entities(self, entity_type: Optional[str] = None, limit: int = 100, offset: int = 0) -> list[BaseEntity]:
        """List entities with optional type filter."""
        if entity_type:
            return await self._entity_repo.list_by_type(entity_type, limit=limit, offset=offset)
        return await self._entity_repo.query("", {"limit": limit, "offset": offset})

    async def count_entities(self, entity_type: Optional[str] = None) -> int:
        """Count entities, optionally filtered by type."""
        return await self._entity_repo.count_by_type(entity_type)

    async def search_entities(self, query: str, params: Optional[dict[str, Any]] = None, limit: int = 100, offset: int = 0) -> list[BaseEntity]:
        """Search entities by query text and optional filters."""
        merged_params = dict(params or {})
        merged_params.setdefault("limit", limit)
        merged_params.setdefault("offset", offset)
        return await self._entity_repo.query(query, merged_params)

    # ------------------------------------------------------------------
    # Relationship operations
    # ------------------------------------------------------------------

    async def create_relationship(self, rel: BaseRelationship) -> BaseRelationship:
        """Create a relationship between two entities and record event."""
        # Validate both entities exist
        source = await self._entity_repo.get(rel.source_id)
        if source is None:
            raise ValueError(f"Source entity {rel.source_id} not found")
        target = await self._entity_repo.get(rel.target_id)
        if target is None:
            raise ValueError(f"Target entity {rel.target_id} not found")

        created = await self._rel_repo.create(rel)
        event = BaseEvent(
            type=EventType.RELATIONSHIP_ADDED.value,
            source="api",
            subject_id=rel.source_id,
            object_ids=[str(rel.target_id)],
            payload={
                "relationship_type": rel.type,
                "relationship_id": str(rel.id),
            },
        )
        await self._event_repo.create(event)
        return created

    async def list_relationships(self, source_id: Optional[UUID] = None, target_id: Optional[UUID] = None, limit: int = 100) -> list[BaseRelationship]:
        """List relationships with optional source/target filter."""
        if source_id:
            return await self._rel_repo.find_by_source(source_id)
        if target_id:
            return await self._rel_repo.find_by_target(target_id)
        return await self._rel_repo.query("", {"limit": limit})

    async def delete_relationship(self, rel_id: UUID) -> None:
        """Delete a relationship and record event."""
        rel = await self._rel_repo.get(rel_id)
        if rel is None:
            raise ValueError(f"Relationship {rel_id} not found")
        await self._rel_repo.delete(rel_id)
        event = BaseEvent(
            type=EventType.RELATIONSHIP_REMOVED.value,
            source="api",
            subject_id=rel.source_id,
            object_ids=[str(rel.target_id)],
            payload={
                "relationship_type": rel.type,
                "relationship_id": str(rel_id),
            },
        )
        await self._event_repo.create(event)

    # ------------------------------------------------------------------
    # Chat / Company Brain
    # ------------------------------------------------------------------

    async def _parse_actions(self, reply: str) -> tuple[str, list[dict[str, Any]]]:
        """Parse executable actions from LLM response JSON blocks.

        Matches both fenced ```json ... ``` and raw JSON objects containing "action".
        """
        actions = []
        cleaned = reply

        # Try fenced blocks first
        for match in re.finditer(r'```(?:json)?\s*(\{.*?"action".*?\})\s*```', reply, re.DOTALL):
            try:
                cmd = _json.loads(match.group(1))
                if cmd.get("action"):
                    actions.append(cmd)
                    cleaned = cleaned.replace(match.group(0), "", 1)
            except (_json.JSONDecodeError, KeyError):
                continue

        # Try raw JSON objects containing "action" (not inside fences)
        if not actions:
            for match in re.finditer(r'(\{.*?"action"\s*:\s*"[^"]+".*?\})', cleaned, re.DOTALL):
                try:
                    cmd = _json.loads(match.group(1))
                    if cmd.get("action"):
                        actions.append(cmd)
                        cleaned = cleaned.replace(match.group(1), "", 1)
                except (_json.JSONDecodeError, KeyError):
                    continue

        cleaned = cleaned.strip().strip('"\'')
        return cleaned, actions

    async def _execute_action(self, cmd: dict[str, Any]) -> dict[str, Any]:
        """Execute a single action parsed from LLM response."""
        action = cmd.get("action", "")
        result = {"action": action, "success": False, "message": ""}
        try:
            if action == "create_entity":
                entity = BaseEntity(
                    type=cmd.get("type", "core:Concept"),
                    label=cmd.get("label", "Unknown"),
                    description=cmd.get("description", ""),
                )
                created = await self.create_entity(entity)
                result.update({"success": True, "message": f"Entity '{created.label}' created", "entity_id": str(created.id)})
            elif action == "create_relationship":
                rel = BaseRelationship(
                    type=cmd.get("type", "core:references"),
                    source_id=UUID(cmd["source_id"]),
                    target_id=UUID(cmd["target_id"]),
                )
                created = await self.create_relationship(rel)
                result.update({"success": True, "message": f"Relationship '{created.type}' created", "relationship_id": str(created.id)})
            elif action == "search_entities":
                params = {}
                if cmd.get("type"):
                    params["type"] = cmd["type"]
                results = await self.search_entities(cmd.get("query", ""), params=params, limit=10)
                result.update({"success": True, "results": [{"id": str(e.id), "label": e.label, "type": e.type} for e in results]})
            else:
                result["message"] = f"Unknown action: {action}"
        except Exception as e:
            result["message"] = f"Action '{action}' failed: {str(e)}"
        return result

    def _build_system_prompt(self, message: str, history: list[dict] | None = None) -> str:
        """Build system prompt with context, history, and action instructions."""
        prompt = (
            "You are Awren Core, a cognitive operating system. "
            "You work with a knowledge graph that contains entities and relationships.\n"
            "RULES:\n"
            "1. NEVER describe what you will do. Just do it.\n"
            "2. NEVER say 'I'll look for', 'I'll search', 'I'll create', 'Let me', "
            "'Here's a request', or similar thinking-out-loud.\n"
            "3. NEVER invent entities, projects, relationships, or data. Only reference "
            "what exists in the knowledge graph context below.\n"
            "4. If asked about something not in the knowledge graph, say "
            "\"I don't have that information in my knowledge graph.\" — nothing else.\n"
            "5. When asked a specific question (e.g. 'what projects?', 'who is...?'), "
            "use search_entities action with a specific query to find matches. "
            "Then respond with ONLY the matching entities, not everything available.\n"
            "6. Keep responses under 2 sentences.\n"
            "7. Output ```json action blocks ONLY as supplements to a response, "
            "never as the response itself."
        )

        # Knowledge graph context
        entities_context = []
        try:
            results = self._session.execute(
                select(EntityModel).limit(10)
            ).scalars().all()
            entities_context = [{"id": str(e.id), "type": e.type, "label": e.label} for e in results]
        except Exception:
            pass

        if entities_context:
            prompt += (
                f"\n\nKnowledge graph entities (use these IDs for relationships):\n"
                f"{_json.dumps(entities_context, indent=2)}"
            )
            # Show available types
            types = sorted(set(e["type"] for e in entities_context))
            prompt += (
                f"\n\nAvailable entity types: {', '.join(types)}\n"
                "When searching, match the user's request to an entity type. "
                "For example, if user asks about 'documents', search with {\"query\":\"\",\"type\":\"core:Document\"}. "
                "If user asks about 'companies' or 'organizations', use {\"query\":\"\",\"type\":\"core:Organization\"}."
            )

        # Action format
        prompt += (
            "\n\nActions — enclose in ```json ... ```:\n"
            '{"action":"create_entity","type":"core:Organization","label":"Name"}\n'
            '{"action":"create_relationship","type":"core:references","source_id":"uuid","target_id":"uuid"}\n'
            '{"action":"search_entities","query":"text"}\n'
            '{"action":"search_entities","query":"","type":"core:Document"}\n'
            "\nRespond. Act. No thinking out loud. Just concise output."
        )

        if history:
            prompt += "\n\nHistory:\n"
            for msg in history[-6:]:
                prompt += f"{msg['role'][:3]}: {msg['content'][:300]}\n"

        return prompt

    async def ensure_conversation(self, conversation_id: Optional[str]) -> tuple[str, list[dict]]:
        """Get or create a conversation. Returns (conv_id, message_history)."""
        from awren_core.orm_models import ConversationModel
        conv_id_str = conversation_id or ""
        msg_history: list[dict] = []
        try:
            if conv_id_str:
                conv = await self._conv_repo.get(UUID(conv_id_str))
                if conv:
                    msgs = await self._msg_repo.list_by_conversation(UUID(conv_id_str))
                    msg_history = [{"role": m.role, "content": m.content} for m in msgs]
                else:
                    conv_id_str = ""
            if not conv_id_str:
                conv = await self._conv_repo.create()
                conv_id_str = str(conv.id)
        except Exception:
            conv = await self._conv_repo.create()
            conv_id_str = str(conv.id)
        return conv_id_str, msg_history

    async def chat(self, message: str, conversation_id: Optional[str] = None,
                   provider: Optional[str] = None, model: Optional[str] = None,
                   temperature: float = 0.7) -> dict[str, Any]:
        """Chat with the Company Brain — persistent, with action execution."""
        from awren_core.orm_models import EntityModel
        from sqlalchemy import select

        start = time.monotonic()

        # Get or create conversation
        conv_id_str, msg_history = await self.ensure_conversation(conversation_id)

        # Save user message
        await self._msg_repo.create(UUID(conv_id_str), "user", message)

        # Build system prompt
        system_prompt = self._build_system_prompt(message, msg_history)

        # Build message history for LLM
        llm_messages = [{"role": "system", "content": system_prompt}]
        for msg in msg_history[-10:]:
            llm_messages.append({"role": msg["role"], "content": msg["content"]})
        llm_messages.append({"role": "user", "content": message})

        # Get LLM client
        llm = create_llm_client(db_session=self._session)
        reply = "I'm sorry, I couldn't process your request. The LLM is not configured. Please add an API key in Settings."
        confidence = 0.0
        provider_used = "none"
        model_used = "none"

        if llm:
            try:
                raw = llm.chat(
                    system_prompt=system_prompt,
                    user_prompt=message,
                    temperature=temperature,
                    max_tokens=4096,
                )
                reply = raw or "Sorry, I couldn't generate a response."
                confidence = 0.85 if raw else 0.0
                provider_used = getattr(llm, "model", "unknown")
                model_used = getattr(llm, "model", "unknown")
            except Exception as e:
                reply = f"I encountered an error: {str(e)}"
                confidence = 0.0

        # Parse and execute actions
        clean_reply, actions = await self._parse_actions(reply)

        action_results = []
        if actions:
            for cmd in actions:
                result = await self._execute_action(cmd)
                action_results.append(result)
                # Feed search results back as a concise reply
                if result.get("action") == "search_entities":
                    items = result.get("results") or []
                    if items:
                        clean_reply = "\n".join(f"- {i['label']} ({i['type']})" for i in items)
                    else:
                        clean_reply = "No matching entities found in the knowledge graph."
                elif result.get("success") and not clean_reply:
                    clean_reply = result["message"]
                elif not result.get("success") and not clean_reply:
                    clean_reply = result["message"]

        # Save assistant message
        await self._msg_repo.create(
            UUID(conv_id_str), "assistant", clean_reply,
            metadata={"actions": action_results} if action_results else None,
        )

        # Auto-title conversation from first exchange
        if len(msg_history) <= 1:
            title = message[:80] + ("..." if len(message) > 80 else "")
            await self._conv_repo.update_title(UUID(conv_id_str), title)

        elapsed = (time.monotonic() - start) * 1000

        return {
            "reply": clean_reply,
            "conversation_id": conv_id_str,
            "provider": provider_used,
            "model": model_used,
            "confidence": confidence,
            "entities_referenced": [],
            "execution_time_ms": round(elapsed, 2),
            "actions_taken": action_results,
        }

    async def get_conversations(self, limit: int = 50) -> list[dict[str, Any]]:
        """List all conversations."""
        from awren_core.orm_models import MessageModel
        from sqlalchemy import func, select
        convs = await self._conv_repo.list_all(limit)
        result = []
        for c in convs:
            count_stmt = select(func.count(MessageModel.id)).where(
                MessageModel.conversation_id == c.id
            )
            count = self._session.execute(count_stmt).scalar_one()
            result.append({
                "id": str(c.id),
                "title": c.title,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
                "message_count": count,
            })
        return result

    async def get_conversation_messages(self, conv_id: UUID) -> list[dict[str, Any]]:
        """Get all messages for a conversation."""
        msgs = await self._msg_repo.list_by_conversation(conv_id)
        return [
            {
                "id": str(m.id),
                "conversation_id": str(m.conversation_id),
                "role": m.role,
                "content": m.content,
                "metadata": m.metadata_,
                "created_at": m.created_at.isoformat(),
            }
            for m in msgs
        ]

    async def delete_conversation(self, conv_id: UUID) -> None:
        """Delete a conversation and its messages."""
        await self._conv_repo.delete(conv_id)

    # ------------------------------------------------------------------
    # Event querying
    # ------------------------------------------------------------------

    async def get_events_for_subject(self, subject_id: UUID) -> list[BaseEvent]:
        """Get all events for a given entity (chronological order)."""
        return await self._event_repo.replay(subject_id)

    # ------------------------------------------------------------------
    # LLM Settings
    # ------------------------------------------------------------------

    async def get_llm_settings(self) -> dict[str, str]:
        return await self._llm_settings_repo.get()

    async def update_llm_settings(self, provider: str, model: str, openai_api_key: str = "", anthropic_api_key: str = "") -> dict[str, str]:
        return await self._llm_settings_repo.upsert(provider, model, openai_api_key, anthropic_api_key)

    async def get_recent_events(self, limit: int = 50) -> list[BaseEvent]:
        """Get the most recent events across all subjects."""
        return await self._event_repo.query("", {"limit": limit})

    async def replay_entity(self, entity_id: UUID) -> list[BaseEvent]:
        """Replay the full event history for an entity (for state reconstruction)."""
        return await self._event_repo.replay(entity_id)
