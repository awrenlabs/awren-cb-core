"""ActionLayer — implements the ActionLayer protocol for the Awren Core.

Composes with OntologyLayer to read/write entity state.
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from awren_core.layers import ActionLayer, OntologyLayer

from .models import ActionDef
from .registry import ActionRegistry
from .handlers import ALL_BUILTIN_ACTIONS, make_handler


class OntologyActionLayer(ActionLayer):
    """Action layer backed by the OntologyLayer.

    Composes with an OntologyLayer to read/write entity state
    and record action events.
    """

    def __init__(
        self,
        registry: ActionRegistry,
        ontology: OntologyLayer,
    ) -> None:
        self._registry = registry
        self._ontology = ontology

    # ------------------------------------------------------------------
    # ActionLayer protocol
    # ------------------------------------------------------------------

    async def list_actions(
        self, type_name: Optional[str] = None, user: Any = None
    ) -> list[dict[str, Any]]:
        actions = self._registry.list_actions(type_name)
        return [a.to_dict() for a in actions]

    async def get_action(
        self, action_name: str, type_name: str
    ) -> Optional[dict[str, Any]]:
        adef = self._registry.get_action(action_name, type_name)
        return adef.to_dict() if adef else None

    async def execute_action(
        self,
        action_name: str,
        entity_id: UUID,
        params: dict[str, Any],
        user: Any,
    ) -> dict[str, Any]:
        entity = await self._ontology.get_entity(entity_id)
        if not entity:
            return {"success": False, "error": f"Entity {entity_id} not found"}
        type_name = entity.get("type", entity.get("entity_type", "unknown"))

        result = await self._registry.execute(
            action_name=action_name,
            type_name=type_name,
            entity_id=entity_id,
            params=params,
            user=user,
            get_entity_fn=self._ontology.get_entity,
            update_entity_fn=self._ontology.update_entity,
        )
        return result.to_dict()

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create_with_defaults(cls, ontology: OntologyLayer) -> "OntologyActionLayer":
        """Factory: creates an OntologyActionLayer with all built-in actions registered."""
        registry = ActionRegistry()

        for action_name, config in ALL_BUILTIN_ACTIONS.items():
            handler = make_handler(action_name, config)
            action_def = ActionDef(
                name=action_name,
                types=config["types"],
                description=config["description"],
                handler=handler,
                input_schema=config.get("input_schema", {}),
                output_schema=config.get("output_schema", {}),
                required_permission=config.get("required_permission", "execute"),
                tags=config.get("tags", []),
            )
            registry.register(action_def)

        return cls(registry=registry, ontology=ontology)

    @property
    def registry(self) -> ActionRegistry:
        return self._registry
