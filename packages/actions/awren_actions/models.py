"""Action data models — schemas for Action Framework."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID


@dataclass
class ActionInput:
    """Definition of an action's input parameter."""

    name: str
    type: str  # string, number, boolean, date, entity_ref
    description: str = ""
    required: bool = True
    default: Optional[Any] = None


@dataclass
class ActionOutput:
    """Definition of an action's output field."""

    name: str
    type: str
    description: str = ""


@dataclass
class ActionDef:
    """Full definition of an executable action."""

    name: str
    types: list[str]  # Which ontology types this action applies to
    description: str
    handler: Any  # The async callable
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    required_permission: str = "execute"
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "types": self.types,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "required_permission": self.required_permission,
            "tags": self.tags,
        }


@dataclass
class ActionResult:
    """Result of executing an action."""

    success: bool
    data: dict[str, Any]
    action_name: str
    entity_id: UUID
    message: str = ""
    error: Optional[str] = None
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "action_name": self.action_name,
            "entity_id": str(self.entity_id),
            "message": self.message,
            "error": self.error,
            "elapsed_ms": round(self.elapsed_ms, 2),
        }
