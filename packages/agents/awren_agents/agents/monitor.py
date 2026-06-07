"""MonitorAgent — watches ontology entities for state changes and conditions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


async def monitor_agent_handler(
    agent_def: Any,
    input: dict[str, Any],
    user: Any,
    **context: Any,
) -> dict[str, Any]:
    """Monitor agent: check entity state against expected conditions.

    Input schema:
        entity_type (str): Type of entities to monitor.
        state_condition (str): Expected state to check against.
        max_results (int): Max entities to return (default 20).

    Returns:
        dict with compliant_entities, non_compliant_entities, summary.
    """
    ontology = context.get("ontology")
    entity_type = input.get("entity_type", "")
    state_condition = input.get("state_condition", "active")
    max_results = input.get("max_results", 20)

    if not entity_type:
        return {"error": "entity_type is required"}

    compliant: list[dict] = []
    non_compliant: list[dict] = []

    if ontology:
        try:
            entities = await ontology.query_entities(
                type_name=entity_type, query="", limit=max_results
            )
            for e in entities:
                entry = {
                    "id": e.get("id", ""),
                    "label": e.get("label", ""),
                    "state": e.get("state", "unknown"),
                }
                if e.get("state") == state_condition:
                    compliant.append(entry)
                else:
                    non_compliant.append(entry)
        except (AttributeError, NotImplementedError):
            try:
                types_list = await ontology.list_types()
                for t in types_list:
                    if t.get("name") == entity_type:
                        entities = await ontology.get_entity(
                            entity_type
                        ) if hasattr(ontology, "get_entity") else []
                        break
            except Exception:
                pass

    return {
        "entity_type": entity_type,
        "expected_state": state_condition,
        "compliant_count": len(compliant),
        "non_compliant_count": len(non_compliant),
        "compliant": compliant[:10],
        "non_compliant": non_compliant[:10],
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
