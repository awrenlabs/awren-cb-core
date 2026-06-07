"""ResearchAgent — queries ontology, knowledge graph, and LLM to answer questions."""

from __future__ import annotations

from typing import Any

from awren_core.layers import ActionLayer, KnowledgeLayer, OntologyLayer


async def research_agent_handler(
    agent_def: Any,
    input: dict[str, Any],
    user: Any,
    **context: Any,
) -> dict[str, Any]:
    """Research agent: given a query, search ontology + knowledge + LLM.

    Input schema:
        query (str): The research question or topic.
        max_entities (int): Max entities to return (default 10).
        include_relationships (bool): Include relationships (default True).

    Returns:
        dict with entities, relationships, knowledge_nodes, summary.
    """
    ontology: OntologyLayer = context.get("ontology")
    knowledge: KnowledgeLayer = context.get("knowledge")
    query = input.get("query", "")
    max_entities = input.get("max_entities", 10)
    include_relationships = input.get("include_relationships", True)

    if not query:
        return {"error": "query is required", "entities": [], "knowledge_nodes": [], "summary": ""}

    results: dict[str, Any] = {
        "query": query,
        "entities": [],
        "relationships": [],
        "knowledge_nodes": [],
        "summary": "",
    }

    # Search ontology entities by label
    if ontology:
        try:
            entity_type = input.get("entity_type")
            types_list = await ontology.list_types()
            if entity_type:
                type_names = [entity_type]
            else:
                type_names = [t.get("name") for t in types_list if t.get("name")]

            for tn in type_names[:5]:
                try:
                    entities = await ontology.query_entities(
                        type_name=tn, query=query, limit=max_entities
                    )
                    for e in entities:
                        results["entities"].append({
                            "id": e.get("id", ""),
                            "type": e.get("type", tn),
                            "label": e.get("label", ""),
                            "description": e.get("description", ""),
                        })
                except (AttributeError, NotImplementedError):
                    pass
        except Exception:
            pass

    # Search knowledge graph
    if knowledge:
        try:
            kresults = await knowledge.query(query, limit=max_entities)
            for kn in kresults:
                results["knowledge_nodes"].append({
                    "id": kn.get("id", ""),
                    "kind": kn.get("kind", "insight"),
                    "label": kn.get("label", ""),
                    "content": kn.get("content", "")[:200],
                })
        except Exception:
            pass

    # Build summary
    entity_count = len(results["entities"])
    knowledge_count = len(results["knowledge_nodes"])
    results["summary"] = (
        f"Found {entity_count} entities and {knowledge_count} knowledge "
        f"nodes related to '{query}'."
    )

    return results
