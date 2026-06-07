"""Action decorator — registers an action with the ActionRegistry."""

from __future__ import annotations

from typing import Any, Callable, Optional

from .models import ActionDef


def action(
    registry: "ActionRegistry",  # noqa: F821 — forward ref, resolved at runtime
    name: str,
    types: list[str],
    description: str = "",
    input_schema: Optional[dict[str, Any]] = None,
    output_schema: Optional[dict[str, Any]] = None,
    required_permission: str = "execute",
    tags: Optional[list[str]] = None,
) -> Callable:
    """Decorator that registers an async function as an executable action.

    Args:
        registry: The ActionRegistry instance to register with.
        name: Unique action name (e.g. 'approve_budget', 'sign_contract').
        types: Ontology type names this action applies to.
        description: Human-readable description.
        input_schema: Dict of param_name -> type (for validation/docs).
        output_schema: Dict of return_field -> type.
        required_permission: Permission key needed (default: 'execute').
        tags: Categorization tags.

    The decorated function must accept (entity, params, user, **context).
    """
    if input_schema is None:
        input_schema = {}
    if output_schema is None:
        output_schema = {}
    if tags is None:
        tags = []

    def decorator(func: Callable) -> Callable:
        action_def = ActionDef(
            name=name,
            types=types,
            description=description or func.__doc__ or "",
            handler=func,
            input_schema=input_schema,
            output_schema=output_schema,
            required_permission=required_permission,
            tags=tags,
        )
        registry.register(action_def)
        return func

    return decorator
