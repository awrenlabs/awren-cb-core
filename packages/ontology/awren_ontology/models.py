"""Ontology domain models."""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class OntologyClass(BaseModel):
    """An OWL class definition."""
    id: str
    label: str
    description: Optional[str] = None
    parent_classes: list[str] = Field(default_factory=list)
    properties: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    axioms: list[str] = Field(default_factory=list)


class OntologyProperty(BaseModel):
    """An OWL property/relationship definition."""
    id: str
    label: str
    description: Optional[str] = None
    domain: list[str] = Field(default_factory=list)
    range: list[str] = Field(default_factory=list)
    characteristics: list[str] = Field(default_factory=list)  # functional, transitive, symmetric, etc.


class Ontology(BaseModel):
    """A complete OWL 2 ontology."""
    id: UUID = Field(default_factory=uuid4)
    name: str
    version: str = "0.1.0"
    namespace: str
    description: Optional[str] = None
    classes: dict[str, OntologyClass] = Field(default_factory=dict)
    properties: dict[str, OntologyProperty] = Field(default_factory=dict)
    imports: list[str] = Field(default_factory=list)
    created: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
