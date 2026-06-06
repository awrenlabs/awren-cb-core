"""SDK client for interacting with Awren Core API."""
from typing import Any, Optional

import httpx


class AwrenClient:
    """Client for the Awren Core API."""

    def __init__(self, base_url: str, api_key: Optional[str] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(headers=self._headers)

    async def create_entity(self, entity_type: str, label: str, **kwargs: Any) -> dict[str, Any]:
        """Create a new entity in the knowledge graph."""
        response = await self._client.post(
            f"{self.base_url}/api/v1/entities",
            json={"type": entity_type, "label": label, **kwargs},
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def get_entity(self, entity_id: str) -> dict[str, Any]:
        """Retrieve an entity by ID."""
        response = await self._client.get(
            f"{self.base_url}/api/v1/entities/{entity_id}",
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def list_entities(self, entity_type: Optional[str] = None, limit: int = 100) -> dict[str, Any]:
        """List entities, optionally filtered by type."""
        params: dict[str, Any] = {"limit": limit}
        if entity_type:
            params["type"] = entity_type
        response = await self._client.get(
            f"{self.base_url}/api/v1/entities",
            params=params,
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def update_entity(self, entity_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an entity's fields (PATCH)."""
        response = await self._client.patch(
            f"{self.base_url}/api/v1/entities/{entity_id}",
            json=data,
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def delete_entity(self, entity_id: str) -> None:
        """Delete an entity by ID."""
        response = await self._client.delete(
            f"{self.base_url}/api/v1/entities/{entity_id}",
        )
        response.raise_for_status()

    async def get_entity_events(self, entity_id: str) -> dict[str, Any]:
        """Get all events for a specific entity."""
        response = await self._client.get(
            f"{self.base_url}/api/v1/entities/{entity_id}/events",
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def get_recent_events(self, limit: int = 50) -> dict[str, Any]:
        """Get the most recent events across all entities."""
        response = await self._client.get(
            f"{self.base_url}/api/v1/events?limit={limit}",
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def replay_entity_events(self, entity_id: str) -> dict[str, Any]:
        """Replay all events for an entity in chronological order."""
        response = await self._client.get(
            f"{self.base_url}/api/v1/entities/{entity_id}/replay",
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def query(self, query: str, limit: int = 100) -> dict[str, Any]:
        """Query the knowledge graph."""
        response = await self._client.post(
            f"{self.base_url}/api/v1/query",
            json={"query": query, "limit": limit},
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def agent_research(
        self,
        query: str,
        entity_type: Optional[str] = None,
        search_limit: int = 20,
    ) -> dict[str, Any]:
        """Run the Research Agent against the knowledge graph."""
        body: dict[str, Any] = {"query": query, "search_limit": search_limit}
        if entity_type:
            body["entity_type"] = entity_type
        response = await self._client.post(
            f"{self.base_url}/api/v1/agent/research",
            json=body,
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def health_check(self) -> dict[str, Any]:
        """Check API health."""
        response = await self._client.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "AwrenClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
