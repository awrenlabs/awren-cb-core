"""Ontology registry for managing OWL 2 ontologies."""

from typing import Dict, Optional

from awren_ontology.models import Ontology


class OntologyRegistry:
    """Central registry for managing domain ontologies."""

    _ontologies: Dict[str, Ontology] = {}

    @classmethod
    def register(cls, ontology: Ontology) -> None:
        """Register an ontology in the registry."""
        cls._ontologies[ontology.name] = ontology

    @classmethod
    def get(cls, name: str) -> Optional[Ontology]:
        """Retrieve an ontology by name."""
        return cls._ontologies.get(name)

    @classmethod
    def load(cls, name: str) -> Optional[Ontology]:
        """Load an ontology by name (alias for get)."""
        return cls.get(name)

    @classmethod
    def list_ontologies(cls) -> list[str]:
        """List all registered ontologies."""
        return list(cls._ontologies.keys())

    @classmethod
    def remove(cls, name: str) -> None:
        """Remove an ontology from the registry."""
        cls._ontologies.pop(name, None)

    @classmethod
    def clear(cls) -> None:
        """Clear all registered ontologies."""
        cls._ontologies.clear()
