"""Ontology Engine for Awren Core — type registry, validation, computed properties, state machine."""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from awren_core.models import BaseEntity
from awren_core.orm_models import (
    EntityModel,
    EntityVersionModel,
    OntologyTypeModel,
    OntologyPropertyModel,
    RelationshipModel,
)
from awren_core.repositories import (
    EntityRepository,
    EntityVersionRepository,
    OntologyTypeRepository,
    OntologyPropertyRepository,
    RelationshipRepository,
)


class PropertyKind:
    STATIC = "static"
    DYNAMIC = "dynamic"
    COMPUTED = "computed"


class OntologyEngine:
    """Enterprise ontology engine — type schemas, validation, computed properties, state machine."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._type_repo = OntologyTypeRepository(session)
        self._prop_repo = OntologyPropertyRepository(session)
        self._entity_repo = EntityRepository(session)
        self._entity_version_repo = EntityVersionRepository(session)
        self._rel_repo = RelationshipRepository(session)

    # ------------------------------------------------------------------
    # Type Registry
    # ------------------------------------------------------------------

    async def register_type(
        self,
        name: str,
        description: str,
        base_type: Optional[str] = None,
        states: Optional[list[str]] = None,
        config: Optional[dict] = None,
    ) -> OntologyTypeModel:
        """Register a new ontology object type."""
        existing = await self._type_repo.get_by_name(name)
        if existing:
            raise ValueError(f"Type '{name}' already registered")
        return await self._type_repo.create(
            name=name,
            description=description,
            base_type=base_type,
            states=states or ["active"],
            config=config or {},
        )

    async def get_type(self, name: str) -> Optional[dict]:
        """Get type definition with all its properties."""
        type_model = await self._type_repo.get_by_name(name)
        if not type_model:
            return None
        props = await self._prop_repo.list_by_type(type_model.id)
        return {
            "id": str(type_model.id),
            "name": type_model.name,
            "description": type_model.description,
            "base_type": type_model.base_type,
            "states": type_model.states,
            "config": type_model.config,
            "properties": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "property_type": p.property_type,
                    "kind": p.kind,
                    "required": p.required,
                    "default_value": p.default_value,
                    "formula": p.formula,
                    "config": p.config,
                }
                for p in props
            ],
        }

    async def list_types(self) -> list[dict]:
        """List all registered ontology types."""
        types = await self._type_repo.list_all()
        result = []
        for t in types:
            props = await self._prop_repo.list_by_type(t.id)
            result.append({
                "name": t.name,
                "description": t.description,
                "base_type": t.base_type,
                "states": t.states,
                "property_count": len(props),
            })
        return result

    async def add_property(
        self,
        type_name: str,
        name: str,
        property_type: str = "string",
        kind: str = "static",
        required: bool = False,
        default_value: Optional[str] = None,
        formula: Optional[str] = None,
        config: Optional[dict] = None,
    ) -> OntologyPropertyModel:
        """Add a property definition to an ontology type."""
        type_model = await self._type_repo.get_by_name(type_name)
        if not type_model:
            raise ValueError(f"Type '{type_name}' not found")
        existing = await self._prop_repo.get_by_name(type_model.id, name)
        if existing:
            raise ValueError(f"Property '{name}' already exists on type '{type_name}'")
        return await self._prop_repo.create(
            type_id=type_model.id,
            name=name,
            property_type=property_type,
            kind=kind,
            required=required,
            default_value=default_value,
            formula=formula,
            config=config or {},
        )

    async def remove_property(self, type_name: str, property_name: str) -> None:
        """Remove a property definition from an ontology type."""
        type_model = await self._type_repo.get_by_name(type_name)
        if not type_model:
            raise ValueError(f"Type '{type_name}' not found")
        prop = await self._prop_repo.get_by_name(type_model.id, property_name)
        if not prop:
            raise ValueError(f"Property '{property_name}' not found on type '{type_name}'")
        await self._prop_repo.delete(prop.id)

    # ------------------------------------------------------------------
    # Entity Validation
    # ------------------------------------------------------------------

    async def validate_entity(self, entity: BaseEntity) -> list[str]:
        """Validate an entity's properties against its type schema. Returns list of errors."""
        errors: list[str] = []
        type_def = await self._type_repo.get_by_name(entity.type)
        if not type_def:
            return []  # No schema defined for this type — skip validation
        props = await self._prop_repo.list_by_type(type_def.id)

        # Check required properties
        for prop in props:
            if prop.required:
                if prop.name not in entity.properties:
                    errors.append(f"Required property '{prop.name}' is missing")
                elif prop.property_type == "string" and not entity.properties.get(prop.name):
                    errors.append(f"Required property '{prop.name}' cannot be empty")

        # Type check properties
        for key, value in entity.properties.items():
            prop_def = next((p for p in props if p.name == key), None)
            if prop_def and value is not None:
                if prop_def.property_type == "number" and not isinstance(value, (int, float)):
                    errors.append(f"Property '{key}' should be number, got {type(value).__name__}")
                elif prop_def.property_type == "boolean" and not isinstance(value, bool):
                    errors.append(f"Property '{key}' should be boolean, got {type(value).__name__}")
                elif prop_def.property_type == "date" and not isinstance(value, str):
                    errors.append(f"Property '{key}' should be date string, got {type(value).__name__}")

        return errors

    async def compute_properties(self, entity: BaseEntity) -> dict[str, Any]:
        """Evaluate and return computed properties for an entity."""
        type_def = await self._type_repo.get_by_name(entity.type)
        if not type_def:
            return {}
        props = await self._prop_repo.list_by_type(type_def.id, kind="computed")
        computed: dict[str, Any] = {}
        for prop in props:
            if prop.formula:
                try:
                    computed[prop.name] = self._evaluate_formula(
                        prop.formula, entity.properties
                    )
                except Exception:
                    computed[prop.name] = None
        return computed

    def _evaluate_formula(self, formula: str, properties: dict) -> Any:
        """Evaluate a formula expression against entity properties.
        Supports basic arithmetic and string operations.
        """
        namespace = {**properties}
        try:
            return eval(formula, {"__builtins__": {}}, namespace)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # State Machine
    # ------------------------------------------------------------------

    async def get_valid_states(self, type_name: str) -> list[str]:
        """Get valid states for a given entity type."""
        type_def = await self._type_repo.get_by_name(type_name)
        if not type_def:
            return ["active"]
        return type_def.states or ["active"]

    async def transition_state(
        self, entity_id: UUID, new_state: str, reason: str = ""
    ) -> dict:
        """Transition an entity to a new state with validation."""
        entity = await self._entity_repo.get(entity_id)
        if not entity:
            raise ValueError(f"Entity {entity_id} not found")

        valid_states = await self.get_valid_states(entity.type)
        if new_state not in valid_states:
            raise ValueError(
                f"Invalid state '{new_state}' for type '{entity.type}'. "
                f"Valid states: {', '.join(valid_states)}"
            )

        old_state = entity.state or "active"
        entity.state = new_state
        entity.metadata["state_changed_at"] = datetime.now(timezone.utc).isoformat()
        entity.metadata["state_change_reason"] = reason
        entity.metadata["previous_state"] = old_state

        updated = await self._entity_repo.update(entity)
        await self._create_version_snapshot(entity_id, f"State change: {old_state} → {new_state}")

        return {
            "entity_id": str(entity_id),
            "previous_state": old_state,
            "new_state": new_state,
            "reason": reason,
        }

    # ------------------------------------------------------------------
    # Version History
    # ------------------------------------------------------------------

    async def _create_version_snapshot(self, entity_id: UUID, change_description: str = "") -> dict:
        """Snapshot current entity state into version history."""
        entity = await self._entity_repo.get(entity_id)
        if not entity:
            raise ValueError(f"Entity {entity_id} not found")
        props = await self.compute_properties(entity)
        return await self._entity_version_repo.create(
            entity_id=entity_id,
            snapshot={
                "type": entity.type,
                "label": entity.label,
                "description": entity.description,
                "properties": {**entity.properties, **props},
                "identifiers": entity.identifiers,
                "metadata": entity.metadata,
            },
            change_description=change_description,
        )

    async def get_version_history(self, entity_id: UUID) -> list[dict]:
        """Get full version history for an entity."""
        versions = await self._entity_version_repo.list_by_entity(entity_id)
        return [
            {
                "version_num": v.version_num,
                "snapshot": v.snapshot,
                "change_description": v.change_description,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ]

    async def get_version(self, entity_id: UUID, version_num: int) -> Optional[dict]:
        """Get a specific version of an entity."""
        v = await self._entity_version_repo.get_by_version(entity_id, version_num)
        if not v:
            return None
        return {
            "version_num": v.version_num,
            "snapshot": v.snapshot,
            "change_description": v.change_description,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }

    # ------------------------------------------------------------------
    # Relationship Enhancements
    # ------------------------------------------------------------------

    async def get_relationships_for_entity(
        self, entity_id: UUID, include_metadata: bool = True
    ) -> list[dict]:
        """Get all relationships involving an entity with full metadata."""
        from awren_core.repositories import RelationshipRepository
        rel_repo = RelationshipRepository(self._session)

        outgoing = await rel_repo.find_by_source(entity_id)
        incoming = await rel_repo.find_by_target(entity_id)

        result = []
        for rel in outgoing + incoming:
            result.append({
                "id": str(rel.id),
                "type": rel.type,
                "source_id": str(rel.source_id),
                "target_id": str(rel.target_id),
                "properties": rel.properties,
                "metadata": rel.metadata if include_metadata else None,
                "confidence": rel.metadata.get("confidence", 1.0),
                "created_at": rel.metadata.get("created", None),
            })
        return result

    # ------------------------------------------------------------------
    # Bulk ops
    # ------------------------------------------------------------------

    async def seed_default_types(self) -> list[str]:
        """Seed standard enterprise ontology types with property schemas.
        Returns list of created type names.
        """
        registry = {
            "core:Project": {
                "description": "A temporary endeavor with a defined beginning and end",
                "states": ["planning", "active", "on_hold", "completed", "cancelled"],
                "properties": [
                    ("budget", "number", PropertyKind.STATIC, False, "0", None),
                    ("start_date", "date", PropertyKind.STATIC, True, None, None),
                    ("end_date", "date", PropertyKind.STATIC, False, None, None),
                    ("status", "string", PropertyKind.DYNAMIC, True, "planning", None),
                    ("progress_pct", "number", PropertyKind.DYNAMIC, False, "0", None),
                    ("current_cost", "number", PropertyKind.DYNAMIC, False, "0", None),
                    ("risk_score", "number", PropertyKind.DYNAMIC, False, "0", None),
                    ("cost_variance", "number", PropertyKind.COMPUTED, False, None, "budget - current_cost"),
                    ("schedule_variance", "number", PropertyKind.COMPUTED, False, None, "progress_pct - 100 if end_date else 0"),
                ],
            },
            "core:Organization": {
                "description": "A company, institution, or other organized group",
                "states": ["active", "inactive", "dissolved"],
                "properties": [
                    ("legal_name", "string", PropertyKind.STATIC, True, None, None),
                    ("tax_id", "string", PropertyKind.STATIC, False, None, None),
                    ("industry", "string", PropertyKind.STATIC, False, None, None),
                    ("employee_count", "number", PropertyKind.DYNAMIC, False, "0", None),
                    ("annual_revenue", "number", PropertyKind.DYNAMIC, False, "0", None),
                ],
            },
            "core:Person": {
                "description": "An individual human being",
                "states": ["active", "inactive"],
                "properties": [
                    ("full_name", "string", PropertyKind.STATIC, True, None, None),
                    ("email", "string", PropertyKind.STATIC, False, None, None),
                    ("phone", "string", PropertyKind.STATIC, False, None, None),
                    ("role", "string", PropertyKind.DYNAMIC, False, None, None),
                    ("department", "string", PropertyKind.DYNAMIC, False, None, None),
                ],
            },
            "core:Contract": {
                "description": "A legally binding agreement between parties",
                "states": ["draft", "negotiation", "signed", "active", "expired", "terminated"],
                "properties": [
                    ("contract_value", "number", PropertyKind.STATIC, False, "0", None),
                    ("start_date", "date", PropertyKind.STATIC, True, None, None),
                    ("end_date", "date", PropertyKind.STATIC, True, None, None),
                    ("party_a", "string", PropertyKind.STATIC, True, None, None),
                    ("party_b", "string", PropertyKind.STATIC, True, None, None),
                    ("renewal_terms", "string", PropertyKind.DYNAMIC, False, None, None),
                    ("days_remaining", "number", PropertyKind.COMPUTED, False, None, "(end_date - start_date) if (start_date and end_date) else 0"),
                ],
            },
            "core:Document": {
                "description": "A written or digital file containing information",
                "states": ["draft", "review", "approved", "archived"],
                "properties": [
                    ("title", "string", PropertyKind.STATIC, True, None, None),
                    ("author", "string", PropertyKind.STATIC, False, None, None),
                    ("file_type", "string", PropertyKind.STATIC, False, None, None),
                    ("version", "string", PropertyKind.DYNAMIC, False, "1.0", None),
                    ("tags", "string", PropertyKind.DYNAMIC, False, None, None),
                ],
            },
            "core:Location": {
                "description": "A geographic place or spatial region",
                "states": ["active"],
                "properties": [
                    ("address", "string", PropertyKind.STATIC, False, None, None),
                    ("city", "string", PropertyKind.STATIC, False, None, None),
                    ("country", "string", PropertyKind.STATIC, False, None, None),
                    ("coordinates", "string", PropertyKind.STATIC, False, None, None),
                ],
            },
            "core:Asset": {
                "description": "A resource of value owned or controlled",
                "states": ["acquired", "active", "maintenance", "retired", "disposed"],
                "properties": [
                    ("asset_tag", "string", PropertyKind.STATIC, True, None, None),
                    ("category", "string", PropertyKind.STATIC, True, None, None),
                    ("purchase_value", "number", PropertyKind.STATIC, False, "0", None),
                    ("purchase_date", "date", PropertyKind.STATIC, False, None, None),
                    ("current_value", "number", PropertyKind.DYNAMIC, False, None, None),
                    ("condition", "string", PropertyKind.DYNAMIC, False, "new", None),
                    ("depreciation", "number", PropertyKind.COMPUTED, False, None, "purchase_value * 0.2 if purchase_value else 0"),
                ],
            },
            "core:Task": {
                "description": "A unit of work to be done",
                "states": ["backlog", "todo", "in_progress", "review", "done", "blocked"],
                "properties": [
                    ("title", "string", PropertyKind.STATIC, True, None, None),
                    ("priority", "string", PropertyKind.STATIC, False, "medium", None),
                    ("assigned_to", "string", PropertyKind.DYNAMIC, False, None, None),
                    ("estimated_hours", "number", PropertyKind.STATIC, False, "0", None),
                    ("actual_hours", "number", PropertyKind.DYNAMIC, False, "0", None),
                    ("due_date", "date", PropertyKind.STATIC, False, None, None),
                    ("completion_pct", "number", PropertyKind.DYNAMIC, False, "0", None),
                ],
            },
        }

        created: list[str] = []
        for type_name, schema in registry.items():
            existing = await self._type_repo.get_by_name(type_name)
            if existing:
                continue
            type_model = await self._type_repo.create(
                name=type_name,
                description=schema["description"],
                states=schema["states"],
            )
            for prop_name, ptype, kind, required, default, formula in schema["properties"]:
                await self._prop_repo.create(
                    type_id=type_model.id,
                    name=prop_name,
                    property_type=ptype,
                    kind=kind,
                    required=required,
                    default_value=default,
                    formula=formula,
                )
            created.append(type_name)
        return created

    # ------------------------------------------------------------------
    # Entity access (implements OntologyLayer protocol)
    # ------------------------------------------------------------------

    async def get_entity(self, entity_id: UUID) -> Optional[dict[str, Any]]:
        """Get an entity by ID as a dict."""
        entity = await self._entity_repo.get(entity_id)
        if not entity:
            return None
        return {
            "id": str(entity.id),
            "type": entity.type,
            "label": entity.label,
            "description": entity.description,
            "properties": entity.properties or {},
            "identifiers": entity.identifiers or [],
            "state": entity.state,
            "provenance": entity.provenance or {},
            "metadata": entity.metadata or {},
        }

    async def update_entity(
        self, entity_id: UUID, **kwargs: Any
    ) -> dict[str, Any]:
        """Update entity attributes."""
        entity = await self._entity_repo.get(entity_id)
        if not entity:
            raise ValueError(f"Entity {entity_id} not found")
        for key, value in kwargs.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
            elif key in ("properties",) and isinstance(value, dict):
                for k, v in value.items():
                    entity.properties[k] = v
        updated = await self._entity_repo.update(entity)
        return await self.get_entity(updated.id)
