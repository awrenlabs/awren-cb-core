"""Neo4j graph connection manager and repository.

Stores entities as labeled nodes and relationships as typed edges
in Neo4j, enabling graph-native queries, traversal, and path finding.
"""

from typing import Any, Optional
from uuid import UUID

from awren_core.models import BaseEntity, BaseRelationship
from awren_core.settings import get_settings


class GraphConnection:
    """Manages the Neo4j driver connection lifecycle."""

    def __init__(self) -> None:
        self._driver: Any = None

    @property
    def driver(self) -> Any:
        """Lazy-initialized Neo4j driver."""
        if self._driver is None:
            from neo4j import GraphDatabase

            settings = get_settings()
            self._driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
            )
        return self._driver

    def close(self) -> None:
        """Close the Neo4j driver connection."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def __enter__(self) -> "GraphConnection":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


# Singleton connection
_connection: Optional[GraphConnection] = None


def get_graph() -> GraphConnection:
    """Get or create the singleton graph connection."""
    global _connection
    if _connection is None:
        _connection = GraphConnection()
    return _connection


# ---------------------------------------------------------------------------
# Cypher queries
# ---------------------------------------------------------------------------

MERGE_ENTITY_CYPHER = """
MERGE (e:Entity {id: $id})
SET e.type = $type,
    e.label = $label,
    e.description = $description,
    e.properties = $properties,
    e.updated_at = timestamp()
ON CREATE SET e.created_at = timestamp()
RETURN e
"""

GET_ENTITY_CYPHER = """
MATCH (e:Entity {id: $id})
RETURN e
"""

DELETE_ENTITY_CYPHER = """
MATCH (e:Entity {id: $id})
DETACH DELETE e
"""

SEARCH_ENTITIES_CYPHER = """
MATCH (e:Entity)
WHERE ($type IS NULL OR e.type = $type)
  AND ($label IS NULL OR toLower(e.label) CONTAINS toLower($label))
RETURN e
ORDER BY e.label
SKIP $offset
LIMIT $limit
"""

CREATE_RELATIONSHIP_CYPHER = """
MATCH (source:Entity {id: $source_id})
MATCH (target:Entity {id: $target_id})
MERGE (source)-[r:RELATES_TO {id: $id}]->(target)
SET r.type = $rel_type,
    r.properties = $properties,
    r.source_id = $source_id,
    r.target_id = $target_id
RETURN r, source, target
"""

GET_RELATIONSHIP_CYPHER = """
MATCH (source)-[r:RELATES_TO {id: $id}]->(target)
RETURN r, source, target
"""

DELETE_RELATIONSHIP_CYPHER = """
MATCH ()-[r:RELATES_TO {id: $id}]->()
DELETE r
"""

TRAVERSE_CYPHER = """
MATCH (e:Entity {id: $start_id})-[:RELATES_TO*1..$depth]->(related:Entity)
RETURN DISTINCT related
LIMIT $limit
"""


class GraphRepository:
    """Neo4j graph repository for entities and relationships.

    Provides graph-native operations:
    - Entity CRUD as labeled nodes
    - Relationship CRUD as typed edges
    - Graph traversal (BFS/DFS up to N hops)
    - Subgraph extraction
    """

    def __init__(self, connection: Optional[GraphConnection] = None) -> None:
        self._connection = connection or get_graph()

    def _run_query(self, query: str, params: Optional[dict[str, Any]] = None) -> Any:
        """Execute a Cypher query and return the result."""
        with self._connection.driver.session() as session:
            result = session.run(query, params or {})
            return result

    def _node_to_entity(self, node: Any) -> BaseEntity:
        """Convert a Neo4j node to a BaseEntity."""
        props = dict(node)
        return BaseEntity(
            id=UUID(props["id"]),
            type=props.get("type", "core:Unknown"),
            label=props.get("label", ""),
            description=props.get("description"),
            properties=props.get("properties", {}),
            identifiers=[],
            metadata={
                "created": str(props.get("created_at", "")),
                "updated": str(props.get("updated_at", "")),
                "source": "neo4j",
            },
        )

    def _rel_to_relationship(
        self,
        rel: Any,
        source_node: Optional[Any] = None,
        target_node: Optional[Any] = None,
    ) -> BaseRelationship:
        """Convert a Neo4j relationship (+ optional endpoints) to a BaseRelationship."""
        props = dict(rel)

        # Prefer endpoint nodes over stored properties for accuracy
        source_id: UUID
        target_id: UUID

        if source_node is not None:
            source_id = UUID(dict(source_node)["id"])
        else:
            source_id = UUID(props["source_id"])

        if target_node is not None:
            target_id = UUID(dict(target_node)["id"])
        else:
            target_id = UUID(props["target_id"])

        return BaseRelationship(
            id=UUID(props["id"]),
            type=props.get("type", "core:unknown"),
            source_id=source_id,
            target_id=target_id,
            properties=props.get("properties", {}),
        )

    # ------------------------------------------------------------------
    # Entity operations
    # ------------------------------------------------------------------

    def create_entity(self, entity: BaseEntity) -> BaseEntity:
        """Create or merge an entity node in Neo4j."""
        self._run_query(MERGE_ENTITY_CYPHER, {
            "id": str(entity.id),
            "type": entity.type,
            "label": entity.label,
            "description": entity.description or "",
            "properties": entity.properties,
        })
        return entity

    def get_entity(self, entity_id: UUID) -> Optional[BaseEntity]:
        """Retrieve an entity node by ID."""
        result = self._run_query(GET_ENTITY_CYPHER, {"id": str(entity_id)})
        record = result.single()
        if record is None:
            return None
        return self._node_to_entity(record["e"])

    def update_entity(self, entity: BaseEntity) -> BaseEntity:
        """Update an entity node (merge overwrites properties)."""
        return self.create_entity(entity)

    def delete_entity(self, entity_id: UUID) -> None:
        """Delete an entity node and all its relationships."""
        self._run_query(DELETE_ENTITY_CYPHER, {"id": str(entity_id)})

    def search_entities(
        self,
        entity_type: Optional[str] = None,
        label: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[BaseEntity]:
        """Search entities by type and/or label."""
        result = self._run_query(SEARCH_ENTITIES_CYPHER, {
            "type": entity_type,
            "label": label,
            "limit": limit,
            "offset": offset,
        })
        return [self._node_to_entity(record["e"]) for record in result]

    # ------------------------------------------------------------------
    # Relationship operations
    # ------------------------------------------------------------------

    def create_relationship(self, rel: BaseRelationship) -> BaseRelationship:
        """Create a relationship edge between two entity nodes."""
        self._run_query(CREATE_RELATIONSHIP_CYPHER, {
            "id": str(rel.id),
            "source_id": str(rel.source_id),
            "target_id": str(rel.target_id),
            "rel_type": rel.type,
            "properties": rel.properties,
        })
        return rel

    def get_relationship(self, rel_id: UUID) -> Optional[BaseRelationship]:
        """Retrieve a relationship by ID."""
        result = self._run_query(GET_RELATIONSHIP_CYPHER, {"id": str(rel_id)})
        record = result.single()
        if record is None:
            return None
        return self._rel_to_relationship(record["r"], source_node=record.get("source"), target_node=record.get("target"))

    def delete_relationship(self, rel_id: UUID) -> None:
        """Delete a relationship edge by ID."""
        self._run_query(DELETE_RELATIONSHIP_CYPHER, {"id": str(rel_id)})

    # ------------------------------------------------------------------
    # Graph traversal
    # ------------------------------------------------------------------

    def traverse(
        self,
        start_id: UUID,
        depth: int = 2,
        limit: int = 100,
    ) -> list[BaseEntity]:
        """Traverse the graph from a start entity up to N hops.

        Returns all reachable entities within the specified depth.
        Useful for neighborhood queries, influence mapping, etc.
        """
        result = self._run_query(TRAVERSE_CYPHER, {
            "start_id": str(start_id),
            "depth": depth,
            "limit": limit,
        })
        return [self._node_to_entity(record["related"]) for record in result]

    def find_path(
        self,
        source_id: UUID,
        target_id: UUID,
        max_depth: int = 6,
    ) -> list[BaseRelationship]:
        """Find the shortest path between two entities.

        Returns the sequence of relationships forming the path.
        Each relationship includes source/target ID via stored properties.
        """
        query = """
        MATCH path = shortestPath(
            (source:Entity {id: $source_id})-[:RELATES_TO*1..$max_depth]-(target:Entity {id: $target_id})
        )
        UNWIND relationships(path) AS r
        RETURN r, startNode(r) AS path_source, endNode(r) AS path_target
        """
        result = self._run_query(query, {
            "source_id": str(source_id),
            "target_id": str(target_id),
            "max_depth": max_depth,
        })
        return [
            self._rel_to_relationship(
                record["r"],
                source_node=record.get("path_source"),
                target_node=record.get("path_target"),
            )
            for record in result
        ]

    def get_neighborhood(
        self,
        entity_id: UUID,
        depth: int = 1,
    ) -> dict[str, Any]:
        """Get the full neighborhood of an entity (entity + connected entities + relationships)."""
        query = """
        MATCH (e:Entity {id: $entity_id})
        OPTIONAL MATCH (e)-[r:RELATES_TO]-(connected:Entity)
        RETURN e AS center,
               collect(DISTINCT {
                   rel: r,
                   node: connected,
                   start: startNode(r),
                   end: endNode(r)
               }) AS neighbors
        """
        result = self._run_query(query, {"entity_id": str(entity_id)})
        record = result.single()
        if record is None:
            return {"center": None, "neighbors": []}

        center = self._node_to_entity(record["center"])
        neighbors: list[dict[str, Any]] = []
        for n in (record["neighbors"] or []):
            if n.get("node") and n.get("rel"):
                neighbors.append({
                    "entity": self._node_to_entity(n["node"]),
                    "relationship": self._rel_to_relationship(
                        n["rel"],
                        source_node=n.get("start"),
                        target_node=n.get("end"),
                    ),
                })

        return {"center": center, "neighbors": neighbors}
