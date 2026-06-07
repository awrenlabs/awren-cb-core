"""ActionAgent — executes sequences of actions on ontology objects."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID


async def action_agent_handler(
    agent_def: Any,
    input: dict[str, Any],
    user: Any,
    **context: Any,
) -> dict[str, Any]:
    """Action agent: execute a sequence of actions on entities.

    Input schema:
        steps (list[dict]): Each step has:
            - action_name (str): Name of the action to execute.
            - entity_id (str): Target entity UUID.
            - params (dict): Action parameters.
        continue_on_error (bool): Whether to continue if a step fails.

    Returns:
        dict with results per step, overall status.
    """
    actions: Any = context.get("actions")
    steps = input.get("steps", [])
    continue_on_error = input.get("continue_on_error", False)

    if not steps:
        return {"error": "steps list is required"}

    if not actions:
        return {"error": "ActionLayer not available"}

    step_results = []
    overall_success = True

    for i, step in enumerate(steps):
        action_name = step.get("action_name", "")
        entity_id = step.get("entity_id", "")
        params = step.get("params", {})

        if not action_name or not entity_id:
            step_results.append({
                "step": i,
                "success": False,
                "error": "action_name and entity_id required",
            })
            overall_success = False
            if not continue_on_error:
                break
            continue

        try:
            result = await actions.execute_action(
                action_name=action_name,
                entity_id=UUID(entity_id),
                params=params,
                user=user,
            )
            step_results.append({
                "step": i,
                "action": action_name,
                "entity_id": entity_id,
                "success": result.get("success", False),
                "data": result.get("data", {}),
                "elapsed_ms": result.get("elapsed_ms", 0),
            })
            if not result.get("success", False):
                overall_success = False
                if not continue_on_error:
                    break
        except Exception as e:
            step_results.append({
                "step": i,
                "action": action_name,
                "entity_id": entity_id,
                "success": False,
                "error": str(e),
            })
            overall_success = False
            if not continue_on_error:
                break

    return {
        "overall_success": overall_success,
        "total_steps": len(steps),
        "completed_steps": len(step_results),
        "steps": step_results,
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }
