"""Awren Core Dashboard — Web interface for the Cognitive OS.

Built with FastAPI + Jinja2 + HTMX for a SPA-like experience
without the complexity of a JavaScript framework.
"""

import json
import logging
import os
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from awren_agents.base import AgentTask
from awren_agents.research_agent import ResearchAgent
from awren_core.database import create_session
from awren_core.models import BaseEntity
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
    return await _template_response("graph.html", {
        "request": request,
        "entities_json": json.dumps([_entity_to_dict(e) for e in entities]),
        "db_error": not entities,
    })


# ---------------------------------------------------------------------------
# API endpoints for HTMX dashboard interactions
# ---------------------------------------------------------------------------


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
