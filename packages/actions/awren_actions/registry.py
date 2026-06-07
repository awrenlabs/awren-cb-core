"""ActionRegistry — central registry for all executable actions.

Thread-safe registry that maps (type_name, action_name) → ActionDef.
Layers can query available actions and execute them by name.
"""

from __future__ import annotations

import time
from typing import Any, Optional
from uuid import UUID

from .models import ActionDef, ActionResult


class ActionRegistry:
    """Central registry for executable actions on ontology objects.

    Actions are registered per ontology type and can be listed or
    executed. Each action is an async callable that receives
    (entity, params, user, **context).
    """

    def __init__(self) -> None:
        self._actions: dict[str, ActionDef] = {}  # key: "type_name:action_name"
        self._by_type: dict[str, list[str]] = {}  # type_name -> [action_name]

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, action_def: ActionDef) -> None:
        """Register an action definition."""
        for type_name in action_def.types:
            key = f"{type_name}:{action_def.name}"
            self._actions[key] = action_def
            if type_name not in self._by_type:
                self._by_type[type_name] = []
            if action_def.name not in self._by_type[type_name]:
                self._by_type[type_name].append(action_def.name)

    def unregister(self, action_name: str, type_name: str) -> None:
        """Remove an action registration."""
        key = f"{type_name}:{action_name}"
        self._actions.pop(key, None)
        if type_name in self._by_type:
            self._by_type[type_name] = [
                a for a in self._by_type[type_name] if a != action_name
            ]

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_action(self, action_name: str, type_name: str) -> Optional[ActionDef]:
        """Get action definition for a specific type."""
        key = f"{type_name}:{action_name}"
        return self._actions.get(key)

    def list_actions(self, type_name: Optional[str] = None) -> list[ActionDef]:
        """List all actions, optionally filtered by ontology type."""
        if type_name:
            names = self._by_type.get(type_name, [])
            return [
                self._actions[f"{type_name}:{n}"]
                for n in names
                if f"{type_name}:{n}" in self._actions
            ]
        seen: set[str] = set()
        all_actions: list[ActionDef] = []
        for key, adef in self._actions.items():
            if adef.name not in seen:
                seen.add(adef.name)
                all_actions.append(adef)
        return all_actions

    def list_action_names(self, type_name: Optional[str] = None) -> list[str]:
        """List available action names."""
        return [a.name for a in self.list_actions(type_name)]

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute(
        self,
        action_name: str,
        type_name: str,
        entity_id: UUID,
        params: dict[str, Any],
        user: Any,
        get_entity_fn: Optional[callable] = None,
        update_entity_fn: Optional[callable] = None,
    ) -> ActionResult:
        """Execute an action on an entity.

        Args:
            action_name: Name of the action to execute.
            type_name: Ontology type of the entity.
            entity_id: Entity UUID.
            params: Input parameters for the action.
            user: Authenticated user (or user context).
            get_entity_fn: Optional async callable to load the entity.
            update_entity_fn: Optional async callable to persist changes.

        Returns:
            ActionResult with success/failure and data.
        """
        action_def = self.get_action(action_name, type_name)
        if not action_def:
            return ActionResult(
                success=False,
                data={},
                action_name=action_name,
                entity_id=entity_id,
                error=f"Action '{action_name}' not found for type '{type_name}'",
            )

        # Load entity
        entity = None
        if get_entity_fn:
            entity = await get_entity_fn(entity_id)
            if not entity:
                return ActionResult(
                    success=False,
                    data={},
                    action_name=action_name,
                    entity_id=entity_id,
                    error=f"Entity {entity_id} not found",
                )

        start = time.monotonic()
        try:
            result = await action_def.handler(
                entity=entity,
                params=params,
                user=user,
                entity_id=entity_id,
                type_name=type_name,
                get_entity=get_entity_fn,
                update_entity=update_entity_fn,
            )
            elapsed = (time.monotonic() - start) * 1000
            if result is None:
                result = {}
            return ActionResult(
                success=True,
                data=result if isinstance(result, dict) else {"result": result},
                action_name=action_name,
                entity_id=entity_id,
                elapsed_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return ActionResult(
                success=False,
                data={},
                action_name=action_name,
                entity_id=entity_id,
                error=str(e),
                elapsed_ms=elapsed,
            )

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    @property
    def count(self) -> int:
        """Total unique actions registered."""
        return len(set(adef.name for adef in self._actions.values()))

    def clear(self) -> None:
        """Remove all registered actions."""
        self._actions.clear()
        self._by_type.clear()
