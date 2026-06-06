"""Core repository and service interfaces."""

from abc import ABC, abstractmethod
from typing import Any, Generic, Optional, TypeVar
from uuid import UUID

T = TypeVar("T")


class RepositoryInterface(ABC, Generic[T]):
    """Interface for entity repositories."""

    @abstractmethod
    async def create(self, entity: T) -> T:
        """Persist a new entity."""
        ...

    @abstractmethod
    async def get(self, entity_id: UUID) -> Optional[T]:
        """Retrieve an entity by ID."""
        ...

    @abstractmethod
    async def update(self, entity: T) -> T:
        """Update an existing entity."""
        ...

    @abstractmethod
    async def delete(self, entity_id: UUID) -> None:
        """Delete an entity."""
        ...

    @abstractmethod
    async def query(self, query: str, params: Optional[dict[str, Any]] = None) -> list[T]:
        """Query entities."""
        ...


class ServiceInterface(ABC):
    """Interface for domain services."""

    @abstractmethod
    async def execute(self, **kwargs: object) -> dict[str, object]:
        """Execute the service operation."""
        ...
