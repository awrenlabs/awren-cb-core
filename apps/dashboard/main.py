"""Awren Core Dashboard — Web interface for the Cognitive OS.

Built with FastAPI + Jinja2 + HTMX for a SPA-like experience
without the complexity of a JavaScript framework.
"""

import json
import logging
import os
import re
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from awren_agents.base import AgentTask
from awren_agents.research_agent import ResearchAgent
from awren_core.database import create_session
from awren_core.models import BaseEntity, BaseRelationship
from awren_core.settings import get_settings
from awren_core.services import EventService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

# Use absolute path for templates to work regardless of working directory
_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")

# Build Jinja2 environment manually to avoid Starlette 1.2.1 template caching bugs
import jinja2 as _jinja2
_jinja_env = _jinja2.Environment(
    loader=_jinja2.FileSystemLoader(_TEMPLATE_DIR),
    enable_async=True,
    autoescape=True,
    cache_size=50,
)

# Register custom Jinja2 filters
def _tojson(value: Any, indent: int = 2) -> str:
    """Custom tojson filter for Jinja2 templates."""
    return json.dumps(value, indent=indent, default=str, ensure_ascii=False)

_jinja_env.filters["tojson"] = _tojson


async def _render(name: str, context: dict[str, Any]) -> str:
    """Render a Jinja2 template asynchronously."""
    template = _jinja_env.get_template(name)
    return await template.render_async(context)


async def _template_response(name: str, context: dict[str, Any], status_code: int = 200) -> HTMLResponse:
    """Render a Jinja2 template and return it as an HTML response.
    
    Bypasses Starlette's TemplateResponse to avoid known caching issues.
    """
    content = await _render(name, context)
    return HTMLResponse(content=content, status_code=status_code)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def get_db() -> Any:
    """Yield a database session for dashboard requests."""
    session = create_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_event_service(db: Session = Depends(get_db)) -> EventService:  # type: ignore[arg-type]
    return EventService(db)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _safe_call(coro: Any, fallback: Any = None) -> Any:
    """Execute a coroutine safely, returning fallback on database errors."""
    try:
        return await coro
    except Exception as e:
        logger.warning("Database call failed (dashboard will show degraded UI): %s", e)
        return fallback


def _entity_to_dict(entity: BaseEntity) -> dict[str, Any]:
    return {
        "id": str(entity.id),
        "type": entity.type,
        "label": entity.label,
        "description": (entity.description or "")[:200],
        "properties": entity.properties,
        "metadata": entity.metadata,
    }


def _event_to_dict(event: Any) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "type": event.type,
        "timestamp": event.timestamp.isoformat() if hasattr(event.timestamp, "isoformat") else str(event.timestamp),
        "source": event.source,
        "subject_id": str(event.subject_id),
        "payload": event.payload,
    }


# ---------------------------------------------------------------------------
# Pages (HTML rendered)
# ---------------------------------------------------------------------------


@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_home(request: Request, svc: EventService = Depends(get_event_service)) -> HTMLResponse:
    """Dashboard home page with summary stats."""
    entities = await _safe_call(svc.list_entities(limit=5), [])
    events = await _safe_call(svc.get_recent_events(limit=5), [])
    total_entities = await _safe_call(svc.count_entities(), 0)

    # Get Memory Engine status
    memory_count = 0
    try:
        settings = get_settings()
        embedding_model = settings.openai_embedding_model
        if settings.openai_api_key:
            memory_status = f"Vector store: ready ({embedding_model})"
        else:
            memory_status = f"Vector store: fallback mode ({embedding_model} requires API key)"
    except Exception:
        memory_status = "Vector store: inactive (Qdrant not connected)"

    return await _template_response("index.html", {
        "request": request,
        "entities": [_entity_to_dict(e) for e in entities],
        "events": [_event_to_dict(e) for e in events],
        "total_entities": total_entities,
        "total_events": len(events),
        "memory_count": memory_count,
        "memory_status": memory_status,
        "db_error": not entities and not events and total_entities == 0,
    })


@router.get("/entities", response_class=HTMLResponse, include_in_schema=False)
async def entities_page(
    request: Request,
    type: Optional[str] = Query(None),
    limit: int = Query(100),
    svc: EventService = Depends(get_event_service),
) -> HTMLResponse:
    """Entity list page with optional type filter."""
    entities = await _safe_call(svc.list_entities(type, limit=limit), [])
    total = await _safe_call(svc.count_entities(type), 0)

    return await _template_response("entities.html", {
        "request": request,
        "entities": [_entity_to_dict(e) for e in entities],
        "total": total,
        "filter_type": type,
        "db_error": not entities,
    })


@router.get("/entities/{entity_id}", response_class=HTMLResponse, include_in_schema=False)
async def entity_detail_page(
    request: Request,
    entity_id: UUID,
    svc: EventService = Depends(get_event_service),
) -> HTMLResponse:
    """Entity detail page with event history."""
    entity = await _safe_call(svc.get_entity(entity_id))
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    events = await _safe_call(svc.replay_entity(entity_id), [])

    return await _template_response("entity.html", {
        "request": request,
        "entity": _entity_to_dict(entity),
        "events": [_event_to_dict(e) for e in events],
    })


@router.get("/events", response_class=HTMLResponse, include_in_schema=False)
async def events_page(
    request: Request,
    limit: int = Query(50),
    svc: EventService = Depends(get_event_service),
) -> HTMLResponse:
    """Event timeline page."""
    events = await _safe_call(svc.get_recent_events(limit=limit), [])

    return await _template_response("events.html", {
        "request": request,
        "events": [_event_to_dict(e) for e in events],
        "db_error": not events,
    })


@router.get("/agent", response_class=HTMLResponse, include_in_schema=False)
async def agent_page(request: Request) -> HTMLResponse:
    """Research Agent interface page."""
    return await _template_response("agent.html", {
        "request": request,
    })


@router.get("/graph", response_class=HTMLResponse, include_in_schema=False)
async def graph_page(
    request: Request,
    svc: EventService = Depends(get_event_service),
) -> HTMLResponse:
    """Knowledge graph visualization page."""
    entities = await _safe_call(svc.list_entities(limit=200), [])
    relationships = await _safe_call(svc.list_relationships(limit=500), [])
    return await _template_response("graph.html", {
        "request": request,
        "entities_json": json.dumps([_entity_to_dict(e) for e in entities]),
        "relationships_json": json.dumps([
            {"id": str(r.id), "type": r.type, "source_id": str(r.source_id), "target_id": str(r.target_id)}
            for r in relationships
        ]),
        "db_error": not entities,
    })


@router.get("/chat", response_class=HTMLResponse, include_in_schema=False)
async def chat_page(
    request: Request,
    conv: Optional[str] = Query(None),
    svc: EventService = Depends(get_event_service),
) -> HTMLResponse:
    """Chat interface page — Company Brain with conversations."""
    conversations = await _safe_call(svc.get_conversations(), [])
    messages = []
    current_conv = conv or ""
    if conv:
        try:
            msgs = await svc.get_conversation_messages(UUID(conv))
            messages = msgs
            current_conv = conv
        except Exception:
            pass
    return await _template_response("chat.html", {
        "request": request,
        "conversations": conversations,
        "messages": messages,
        "current_conv": current_conv,
    })


@router.get("/settings", response_class=HTMLResponse, include_in_schema=False)
async def settings_page(
    request: Request,
    svc: EventService = Depends(get_event_service),
) -> HTMLResponse:
    """LLM provider settings page."""
    from awren_core.settings import get_settings
    env = get_settings()
    db = await _safe_call(svc.get_llm_settings(), {})

    providers = [
        {"id": "openai", "name": "OpenAI", "models": [{"id": "gpt-4o", "name": "GPT-4o"}, {"id": "gpt-4o-mini", "name": "GPT-4o Mini"}, {"id": "gpt-4-turbo", "name": "GPT-4 Turbo"}, {"id": "o3-mini", "name": "o3 Mini"}]},
        {"id": "anthropic", "name": "Anthropic", "models": [{"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4"}, {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet"}, {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku"}]},
        {"id": "openrouter", "name": "OpenRouter", "models": [{"id": "openai/gpt-4o", "name": "GPT-4o (OpenRouter)"}, {"id": "anthropic/claude-sonnet-4", "name": "Claude Sonnet 4 (OpenRouter)"}, {"id": "google/gemini-2.0-flash-001", "name": "Gemini 2.0 Flash"}, {"id": "meta-llama/llama-3.3-70b-instruct", "name": "Llama 3.3 70B"}]},
        {"id": "custom_openai", "name": "Custom OpenAI-compatible", "models": [{"id": "custom", "name": "Custom Model"}]},
    ]

    provider = db.get("provider", env.llm_provider)
    model = db.get("model", env.openai_model if env.llm_provider != "anthropic" else env.anthropic_model)

    # Resolve API keys: DB > env
    db_openai = db.get("openai_api_key", "")
    db_anthropic = db.get("anthropic_api_key", "")
    openai_key = db_openai or env.openai_api_key or ""
    anthropic_key = db_anthropic or env.anthropic_api_key or ""

    return await _template_response("settings.html", {
        "request": request,
        "current_provider": provider,
        "current_model": model,
        "providers": providers,
        "providers_json": json.dumps(providers),
        "openai_api_key": openai_key,
        "anthropic_api_key": anthropic_key,
        "has_openai_key": bool(openai_key),
        "has_anthropic_key": bool(anthropic_key),
    })


@router.get("/relationships", response_class=HTMLResponse, include_in_schema=False)
async def relationships_page(
    request: Request,
    svc: EventService = Depends(get_event_service),
) -> HTMLResponse:
    """Relationship management page."""
    entities = await _safe_call(svc.list_entities(limit=200), [])
    rels = await _safe_call(svc.list_relationships(limit=500), [])
    return await _template_response("relationships.html", {
        "request": request,
        "entities": [_entity_to_dict(e) for e in entities],
        "relationships": [
            {
                "id": str(r.id),
                "type": r.type,
                "source_id": str(r.source_id),
                "target_id": str(r.target_id),
                "properties": r.properties,
                "metadata": r.metadata,
            }
            for r in rels
        ],
    })


# ---------------------------------------------------------------------------
# API endpoints for HTMX dashboard interactions
# ---------------------------------------------------------------------------


@router.post("/api/chat", response_class=HTMLResponse, include_in_schema=False)
async def chat_htmx(
    request: Request,
    message: str = Form(...),
    provider: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    temperature: float = Form(0.7),
    svc: EventService = Depends(get_event_service),
) -> HTMLResponse:
    """HTMX endpoint: chat with Company Brain and return HTML fragment."""
    try:
        result = await svc.chat(
            message=message,
            provider=provider,
            model=model,
            temperature=temperature,
            include_graph_context=True,
        )
        return await _template_response("partials/_chat_message.html", {
            "request": request,
            "message": message,
            "reply": result["reply"],
            "confidence": result["confidence"],
            "entities": result["entities_referenced"],
            "execution_time_ms": result["execution_time_ms"],
        })
    except Exception as e:
        logger.error("Chat failed: %s", e)
        return HTMLResponse(
            content=f'<div class="chat-message assistant"><div class="chat-bubble error"><p>Error: {str(e)}</p></div></div>',
        )


@router.post("/api/relationships", response_class=HTMLResponse, include_in_schema=False)
async def create_relationship_htmx(
    request: Request,
    type: str = Form(...),
    source_id: str = Form(...),
    target_id: str = Form(...),
    svc: EventService = Depends(get_event_service),
) -> HTMLResponse:
    """HTMX endpoint: create a relationship and return toast."""
    try:
        rel = BaseRelationship(
            type=type,
            source_id=UUID(source_id),
            target_id=UUID(target_id),
        )
        created = await svc.create_relationship(rel)
        logger.info("Relationship created via dashboard: %s", created.id)
        return HTMLResponse(
            content=json.dumps({"message": f"Relationship '{type}' created!", "type": "success"}),
            headers={"Content-Type": "application/json", "HX-Trigger": "show-toast"},
        )
    except Exception as e:
        logger.error("Failed to create relationship: %s", e)
        return HTMLResponse(
            content=json.dumps({"message": f"Error: {str(e)}", "type": "error"}),
            headers={"Content-Type": "application/json", "HX-Trigger": "show-toast"},
        )


@router.delete("/api/relationships/{rel_id}", response_class=HTMLResponse, include_in_schema=False)
async def delete_relationship_htmx(
    request: Request,
    rel_id: UUID,
    svc: EventService = Depends(get_event_service),
) -> HTMLResponse:
    """HTMX endpoint: delete a relationship and return toast."""
    try:
        await svc.delete_relationship(rel_id)
        return HTMLResponse(
            content=json.dumps({"message": "Relationship deleted!", "type": "success"}),
            headers={"Content-Type": "application/json", "HX-Trigger": "show-toast"},
        )
    except Exception as e:
        return HTMLResponse(
            content=json.dumps({"message": f"Error: {str(e)}", "type": "error"}),
            headers={"Content-Type": "application/json", "HX-Trigger": "show-toast"},
        )


@router.put("/api/settings/llm", response_class=HTMLResponse, include_in_schema=False)
async def update_llm_settings_htmx(
    request: Request,
    provider: str = Form(...),
    model: str = Form(""),
    openai_api_key: str = Form(""),
    anthropic_api_key: str = Form(""),
    svc: EventService = Depends(get_event_service),
) -> HTMLResponse:
    """HTMX endpoint: save LLM provider/model/API keys."""
    try:
        await svc.update_llm_settings(
            provider=provider,
            model=model,
            openai_api_key=openai_api_key,
            anthropic_api_key=anthropic_api_key,
        )
        return HTMLResponse(
            content='<span class="toast-success" style="padding: var(--sp-1) var(--sp-3); border-radius: var(--radius-md); font-size: var(--text-xs);">Saved ✓</span>',
        )
    except Exception as e:
        logger.error("Failed to save LLM settings: %s", e)
        return HTMLResponse(
            content=f'<span class="toast-error" style="padding: var(--sp-1) var(--sp-3); border-radius: var(--radius-md); font-size: var(--text-xs);">Error: {str(e)}</span>',
        )


@router.post("/api/entities", response_class=HTMLResponse, include_in_schema=False)
async def create_entity_htmx(
    request: Request,
    type: str = Form(...),
    label: str = Form(...),
    description: Optional[str] = Form(None),
    svc: EventService = Depends(get_event_service),
) -> HTMLResponse:
    """HTMX endpoint: create a new entity and return a toast notification."""
    try:
        entity = BaseEntity(
            type=type,
            label=label,
            description=description or "",
        )
        created = await svc.create_entity(entity)
        logger.info("Entity created via dashboard: %s (%s)", created.label, created.type)
        return HTMLResponse(
            content=json.dumps({"message": f"Entity '{label}' created successfully!", "type": "success"}),
            headers={"Content-Type": "application/json", "HX-Trigger": "show-toast"},
        )
    except Exception as e:
        logger.error("Failed to create entity via dashboard: %s", e)
        return HTMLResponse(
            content=json.dumps({"message": f"Error creating entity: {str(e)}", "type": "error"}),
            headers={"Content-Type": "application/json", "HX-Trigger": "show-toast"},
        )


@router.patch("/api/entities/{entity_id}", response_class=HTMLResponse, include_in_schema=False)
async def update_entity_htmx(
    request: Request,
    entity_id: UUID,
    label: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    svc: EventService = Depends(get_event_service),
) -> HTMLResponse:
    """HTMX endpoint: update an entity and return a toast notification."""
    try:
        entity = await svc.get_entity(entity_id)
        if entity is None:
            raise HTTPException(status_code=404, detail="Entity not found")

        changes: dict[str, Any] = {}
        if label is not None:
            changes["label"] = label
            entity.label = label
        if description is not None:
            changes["description"] = description
            entity.description = description

        if changes:
            await svc.update_entity(entity, changes=changes)
            logger.info("Entity updated via dashboard: %s", entity_id)
            return HTMLResponse(
                content=json.dumps({"message": f"Entity '{entity.label}' updated!", "type": "success"}),
                headers={"Content-Type": "application/json", "HX-Trigger": "show-toast"},
            )
        else:
            return HTMLResponse(
                content=json.dumps({"message": "No changes provided", "type": "info"}),
                headers={"Content-Type": "application/json", "HX-Trigger": "show-toast"},
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update entity via dashboard: %s", e)
        return HTMLResponse(
            content=json.dumps({"message": f"Error updating entity: {str(e)}", "type": "error"}),
            headers={"Content-Type": "application/json", "HX-Trigger": "show-toast"},
        )


# ---------------------------------------------------------------------------
# Chat streaming + conversation endpoints
# ---------------------------------------------------------------------------


@router.get("/api/chat/stream")
async def chat_stream_dashboard(
    conv_id: str = "",
    message: str = "",
    svc: EventService = Depends(get_event_service),
):
    """SSE streaming chat endpoint for the dashboard."""
    from fastapi.responses import StreamingResponse
    from awren_core.llm import create_llm_client

    async def event_stream():
        nonlocal conv_id
        conv_id_str, msg_history = await svc.ensure_conversation(conv_id)
        yield f"data: {json.dumps({'type':'meta','conversation_id':conv_id_str})}\n\n"

        await svc._msg_repo.create(UUID(conv_id_str), "user", message)
        system_prompt = svc._build_system_prompt(message, msg_history)
        llm = create_llm_client(db_session=svc._session)

        if llm:
            full_reply = ""
            action_pattern = re.compile(r'```(?:json)?\s*\{.*?"action".*?\}\s*```', re.DOTALL)
            in_action = False

            def should_filter(buffer: str, new_chunk: str) -> bool:
                nonlocal in_action
                combined = buffer + new_chunk
                # Check if we entered an action block
                if not in_action:
                    # Look for opening fence with json
                    for m in re.finditer(r'```(?:json)?\s*\{', combined):
                        # Check if there's a closing fence before an "action"
                        rest = combined[m.end():]
                        if '"action"' in rest[:200]:
                            in_action = True
                            return True
                # If inside action block, check for closing
                if in_action:
                    if '```' in new_chunk:
                        in_action = False
                    return True
                return False

            try:
                for chunk in llm.chat_stream(
                    system_prompt=system_prompt,
                    user_prompt=message,
                    temperature=0.7,
                    max_tokens=4096,
                ):
                    full_reply += chunk
                    if not should_filter(full_reply, chunk):
                        yield f"data: {json.dumps({'type':'chunk','content':chunk})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type':'error','content':str(e)})}\n\n"
            else:
                in_action = False  # reset
                clean_reply, actions = await svc._parse_actions(full_reply)
                action_results = []
                if actions:
                    for cmd in actions:
                        result = await svc._execute_action(cmd)
                        action_results.append(result)

                # Enrich reply with action results (replaces LLM text for search_entities)
                for a in action_results:
                    if a.get("action") == "search_entities":
                        items = a.get("results") or []
                        if items:
                            by_type = {}
                            for i in items:
                                t = i["type"].split(":")[-1]
                                by_type.setdefault(t, []).append(i["label"])
                            parts = [f"{t}: {', '.join(ls)}" for t, ls in by_type.items()]
                            clean_reply = f"I found {len(items)} entities — {'. '.join(parts)}."
                        else:
                            clean_reply = "No matching entities found in the knowledge graph."
                    elif a.get("success") and not clean_reply:
                        clean_reply = a["message"]

                await svc._msg_repo.create(
                    UUID(conv_id_str), "assistant", clean_reply,
                    metadata={"actions": action_results} if action_results else None,
                )
                if len(msg_history) <= 1:
                    title = message[:80] + ("..." if len(message) > 80 else "")
                    await svc._conv_repo.update_title(UUID(conv_id_str), title)

                # Send cleaned reply if we filtered anything
                yield f"data: {json.dumps({'type':'cleaned','content':clean_reply})}\n\n"
                yield f"data: {json.dumps({'type':'done','actions':action_results})}\n\n"
        else:
            yield f"data: {json.dumps({'type':'error','content':'No LLM configured'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/api/conversations")
async def list_conversations_api(svc: EventService = Depends(get_event_service)):
    """JSON endpoint to list conversations."""
    convs = await svc.get_conversations()
    return {"conversations": convs}


@router.get("/api/conversations/{conv_id}/messages")
async def get_conversation_messages_api(
    conv_id: UUID,
    svc: EventService = Depends(get_event_service),
):
    """JSON endpoint to get conversation messages."""
    return await svc.get_conversation_messages(conv_id)


@router.put("/api/conversations/{conv_id}/rename")
async def rename_conversation_api(
    conv_id: UUID,
    title: str = "",
    svc: EventService = Depends(get_event_service),
):
    """Rename a conversation."""
    await svc._conv_repo.update_title(conv_id, title)
    return {"ok": True}


@router.delete("/api/conversations/{conv_id}")
async def delete_conversation_api(
    conv_id: UUID,
    svc: EventService = Depends(get_event_service),
):
    """Delete a conversation and its messages."""
    await svc.delete_conversation(conv_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# HTMX partials (return HTML fragments)
# ---------------------------------------------------------------------------


@router.post("/agent/research", response_class=HTMLResponse, include_in_schema=False)
async def agent_research_htmx(
    request: Request,
    query: str = Form(...),
    entity_type: Optional[str] = Form(None),
) -> HTMLResponse:
    """HTMX endpoint: run research agent and return HTML fragment."""
    try:
        agent = ResearchAgent()
        task = AgentTask(
            agent_type="research",
            query=query,
            context={"entity_type": entity_type or None, "search_limit": 20},
        )
        result = await agent.execute(task)
        return await _template_response("partials/_agent_result.html", {
            "request": request,
            "result": result,
            "query": query,
        })
    except Exception as e:
        logger.error("Research agent failed: %s", e)
        return HTMLResponse(
            content=f'<div class="agent-result" style="color: var(--red);"><p>Research failed: {str(e)}</p></div>',
        )


@router.get("/partials/entity-list", response_class=HTMLResponse, include_in_schema=False)
async def entity_list_partial(
    request: Request,
    type: Optional[str] = Query(None),
    svc: EventService = Depends(get_event_service),
) -> HTMLResponse:
    """HTMX partial: entity list for infinite scroll / filtering."""
    entities = await svc.list_entities(type, limit=100)
    return await _template_response("partials/_entity_list.html", {
        "request": request,
        "entities": [_entity_to_dict(e) for e in entities],
    })
