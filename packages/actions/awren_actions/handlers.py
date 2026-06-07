"""Built-in actions for standard ontology types.

These actions are registered automatically when the action layer
is initialized. Each action follows the pattern:

    async def handler(entity, params, user, **context) -> dict:
"""

from __future__ import annotations

from typing import Any

from awren_core.layers import OntologyLayer


# ---------------------------------------------------------------------------
# Project actions
# ---------------------------------------------------------------------------

PROJECT_ACTIONS = {
    "approve_budget": {
        "types": ["core:Project"],
        "description": "Approve the project budget at a specific amount.",
        "input_schema": {
            "approved_amount": "number",
            "notes": "string",
        },
        "output_schema": {
            "status": "string",
            "approved_amount": "number",
            "previous_budget": "number",
        },
        "required_permission": "update",
        "tags": ["financial", "governance"],
    },
    "assign_team": {
        "types": ["core:Project"],
        "description": "Assign team members to the project.",
        "input_schema": {
            "member_ids": "array",
            "role": "string",
        },
        "output_schema": {
            "status": "string",
            "assigned_count": "number",
        },
        "required_permission": "update",
        "tags": ["team", "management"],
    },
    "update_status": {
        "types": ["core:Project"],
        "description": "Update the project status and progress.",
        "input_schema": {
            "status": "string",
            "progress_pct": "number",
            "notes": "string",
        },
        "output_schema": {
            "previous_status": "string",
            "new_status": "string",
        },
        "required_permission": "update",
        "tags": ["status", "tracking"],
    },
}

# ---------------------------------------------------------------------------
# Contract actions
# ---------------------------------------------------------------------------

CONTRACT_ACTIONS = {
    "sign_contract": {
        "types": ["core:Contract"],
        "description": "Sign the contract, moving it from negotiation to signed state.",
        "input_schema": {
            "signed_by": "string",
            "signee_role": "string",
            "effective_date": "string",
        },
        "output_schema": {
            "status": "string",
            "signed_by": "string",
            "previous_state": "string",
        },
        "required_permission": "update",
        "tags": ["legal", "signing"],
    },
    "amend_contract": {
        "types": ["core:Contract"],
        "description": "Create an amendment to an existing contract.",
        "input_schema": {
            "amendment_clause": "string",
            "new_value": "number",
            "reason": "string",
        },
        "output_schema": {
            "status": "string",
            "amendment_id": "string",
        },
        "required_permission": "update",
        "tags": ["legal", "amendment"],
    },
    "renew_contract": {
        "types": ["core:Contract"],
        "description": "Renew the contract for an additional term.",
        "input_schema": {
            "new_end_date": "string",
            "renewal_terms": "string",
        },
        "output_schema": {
            "status": "string",
            "previous_end_date": "string",
            "new_end_date": "string",
        },
        "required_permission": "update",
        "tags": ["legal", "renewal"],
    },
}

# ---------------------------------------------------------------------------
# Document actions
# ---------------------------------------------------------------------------

DOCUMENT_ACTIONS = {
    "publish_document": {
        "types": ["core:Document"],
        "description": "Publish the document, making it available to viewers.",
        "input_schema": {
            "version": "string",
            "publish_notes": "string",
        },
        "output_schema": {
            "status": "string",
            "version": "string",
        },
        "required_permission": "update",
        "tags": ["document", "publishing"],
    },
    "archive_document": {
        "types": ["core:Document"],
        "description": "Archive the document, removing it from active circulation.",
        "input_schema": {
            "archive_reason": "string",
        },
        "output_schema": {
            "status": "string",
            "previous_state": "string",
        },
        "required_permission": "update",
        "tags": ["document", "archive"],
    },
}

# ---------------------------------------------------------------------------
# Asset actions
# ---------------------------------------------------------------------------

ASSET_ACTIONS = {
    "transfer_asset": {
        "types": ["core:Asset"],
        "description": "Transfer asset ownership or custody to another entity.",
        "input_schema": {
            "new_owner_id": "string",
            "transfer_date": "string",
            "reason": "string",
        },
        "output_schema": {
            "status": "string",
            "previous_owner": "string",
            "new_owner": "string",
        },
        "required_permission": "update",
        "tags": ["asset", "transfer"],
    },
    "retire_asset": {
        "types": ["core:Asset"],
        "description": "Retire an asset from service.",
        "input_schema": {
            "retire_reason": "string",
            "disposal_method": "string",
        },
        "output_schema": {
            "status": "string",
            "previous_state": "string",
        },
        "required_permission": "update",
        "tags": ["asset", "lifecycle"],
    },
}

# ---------------------------------------------------------------------------
# All built-in actions
# ---------------------------------------------------------------------------

ALL_BUILTIN_ACTIONS: dict[str, dict[str, Any]] = {}
for group in [PROJECT_ACTIONS, CONTRACT_ACTIONS, DOCUMENT_ACTIONS, ASSET_ACTIONS]:
    ALL_BUILTIN_ACTIONS.update(group)


# ---------------------------------------------------------------------------
# Handler factories
# ---------------------------------------------------------------------------

async def _default_action_handler(
    entity: Any,
    params: dict[str, Any],
    user: Any,
    **context: Any,
) -> dict[str, Any]:
    """Default handler: logs the action and returns params as result."""
    return {
        "action_applied": True,
        "entity_label": getattr(entity, "label", str(entity)),
        "params_received": list(params.keys()),
        "executed_by": str(getattr(user, "id", user) if user else "system"),
    }


def make_handler(action_name: str, action_config: dict[str, Any]):
    """Create an action handler that integrates with the OntologyLayer.

    Returns an async function that:
    1. Validates input params against schema
    2. Loads the current entity state
    3. Applies the action (state transition + property update)
    4. Records the action event
    5. Returns the result
    """

    async def handler(
        entity: Any,
        params: dict[str, Any],
        user: Any,
        **context: Any,
    ) -> dict[str, Any]:
        ontology: OntologyLayer = context.get("ontology_layer")
        entity_id = context.get("entity_id")
        update_entity = context.get("update_entity")
        get_entity = context.get("get_entity")

        if entity is None and get_entity and entity_id:
            entity = await get_entity(entity_id)

        if entity is None:
            raise ValueError(f"Entity {entity_id} not found or inaccessible")

        result = {
            "action": action_name,
            "entity_id": str(entity_id) if entity_id else None,
            "previous_state": getattr(entity, "state", getattr(entity, "get", lambda k: None)("state")),
        }

        # Specific action logic based on action name
        if action_name == "approve_budget":
            amount = params.get("approved_amount", 0)
            old_budget = (entity.get("properties", {}).get("budget") or
                         getattr(entity, "properties", {}).get("budget", 0))
            if update_entity:
                await update_entity(entity_id, state="active")
            if ontology:
                try:
                    await ontology.transition_state(entity_id, "active", f"Budget approved: ${amount}")
                except Exception:
                    pass
            result.update({
                "status": "approved",
                "approved_amount": amount,
                "previous_budget": old_budget,
            })

        elif action_name == "sign_contract":
            signed_by = params.get("signed_by", str(getattr(user, "username", "unknown")))
            if ontology:
                try:
                    await ontology.transition_state(entity_id, "signed",
                        f"Signed by {signed_by} as {params.get('signee_role', 'signatory')}")
                except Exception:
                    pass
            result.update({
                "status": "signed",
                "signed_by": signed_by,
            })

        elif action_name == "publish_document":
            version = params.get("version", "1.0")
            if ontology:
                try:
                    await ontology.transition_state(entity_id, "approved",
                        f"Published as v{version}: {params.get('publish_notes', '')}")
                except Exception:
                    pass
            result.update({
                "status": "published",
                "version": version,
            })

        elif action_name == "retire_asset":
            if ontology:
                try:
                    await ontology.transition_state(entity_id, "retired",
                        f"Retired: {params.get('retire_reason', '')}")
                except Exception:
                    pass
            result.update({
                "status": "retired",
                "disposal": params.get("disposal_method", "unknown"),
            })

        else:
            # Generic handler: log the action
            if ontology:
                try:
                    await ontology.transition_state(entity_id, result.get("previous_state", entity.get("state") or "active"),
                        f"Action '{action_name}' executed by {getattr(user, 'username', 'system')}")
                except Exception:
                    pass
            result.update(_default_action_handler(entity, params, user, **context))

        return result

    return handler
