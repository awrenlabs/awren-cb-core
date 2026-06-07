"""Executable Action Framework for Awren Core.

Each ontology object type can declare executable actions.
Actions are callable by humans, agents, APIs, or workflows.
This is the Palantir-style Action Framework.

Usage:

    from awren_actions import action, ActionRegistry

    registry = ActionRegistry()

    @action(
        registry=registry,
        name="approve_budget",
        types=["core:Project"],
        description="Approve the project budget",
        input_schema={"approved_amount": float},
        output_schema={"status": str, "approved_by": str},
    )
    async def approve_budget(entity, params, user, **context):
        entity["state"] = "approved"
        return {"status": "approved", "approved_by": str(user.id)}
"""

from .registry import ActionRegistry
from .decorator import action
from .models import ActionDef, ActionInput, ActionOutput, ActionResult

__all__ = [
    "ActionRegistry",
    "action",
    "ActionDef",
    "ActionInput",
    "ActionOutput",
    "ActionResult",
]
