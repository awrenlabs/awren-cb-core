"""Ontology module unit tests."""

import pytest

from awren_ontology.models import Ontology, OntologyClass, OntologyProperty
from awren_ontology.registry import OntologyRegistry
from awren_ontology.validator import SHACLValidator


class TestOntologyModels:
    def test_ontology_class(self):
        cls = OntologyClass(
            id="ex:Person",
            label="Person",
            description="A person",
            parent_classes=["ex:Agent"],
            properties=["ex:name", "ex:age"],
        )
        assert cls.id == "ex:Person"
        assert "ex:Agent" in cls.parent_classes
        assert len(cls.properties) == 2

    def test_ontology_property(self):
        prop = OntologyProperty(
            id="ex:employs",
            label="employs",
            domain=["ex:Organization"],
            range=["ex:Person"],
            characteristics=["functional"],
        )
        assert prop.domain[0] == "ex:Organization"
        assert "functional" in prop.characteristics

    def test_ontology_creation(self):
        ont = Ontology(
            name="test-ontology",
            namespace="https://example.com/test",
            classes={
                "ex:Thing": OntologyClass(id="ex:Thing", label="Thing"),
            },
            properties={},
        )
        assert ont.name == "test-ontology"
        assert ont.version == "0.1.0"
        assert "ex:Thing" in ont.classes
        assert len(ont.imports) == 0

    def test_ontology_with_imports(self):
        ont = Ontology(
            name="extended",
            namespace="https://example.com/ext",
            imports=["https://example.com/base"],
        )
        assert "https://example.com/base" in ont.imports


class TestOntologyRegistry:
    def setup_method(self):
        OntologyRegistry.clear()

    def test_register_and_get(self):
        ont = Ontology(name="test", namespace="https://example.com/test")
        OntologyRegistry.register(ont)
        retrieved = OntologyRegistry.get("test")
        assert retrieved is not None
        assert retrieved.name == "test"

    def test_get_nonexistent(self):
        result = OntologyRegistry.get("nonexistent")
        assert result is None

    def test_load_alias(self):
        ont = Ontology(name="test2", namespace="https://example.com/test2")
        OntologyRegistry.register(ont)
        retrieved = OntologyRegistry.load("test2")
        assert retrieved is not None

    def test_list_ontologies(self):
        OntologyRegistry.register(Ontology(name="a", namespace="https://a.com"))
        OntologyRegistry.register(Ontology(name="b", namespace="https://b.com"))
        names = OntologyRegistry.list_ontologies()
        assert "a" in names
        assert "b" in names
        assert len(names) == 2

    def test_remove(self):
        OntologyRegistry.register(Ontology(name="temp", namespace="https://temp.com"))
        OntologyRegistry.remove("temp")
        assert OntologyRegistry.get("temp") is None

    def test_clear(self):
        OntologyRegistry.register(Ontology(name="x", namespace="https://x.com"))
        OntologyRegistry.clear()
        assert OntologyRegistry.list_ontologies() == []


class TestSHACLValidator:
    def test_validate_conformant_data(self):
        validator = SHACLValidator()
        shapes = {
            "ex:PersonShape": {
                "constraints": [
                    {"type": "minCount", "path": "name", "message": "Name is required"},
                ]
            }
        }
        validator.load_shapes("test", shapes)
        result = validator.validate({"name": "Alice"}, "test")
        assert result.conforms is True
        assert len(result.violations) == 0

    def test_validate_violation(self):
        validator = SHACLValidator()
        shapes = {
            "ex:PersonShape": {
                "constraints": [
                    {"type": "minCount", "path": "email", "message": "Email is required"},
                ]
            }
        }
        validator.load_shapes("test", shapes)
        result = validator.validate({"name": "Alice"}, "test")
        assert result.conforms is False
        assert len(result.violations) == 1

    def test_no_shapes_loaded(self):
        validator = SHACLValidator()
        result = validator.validate({"data": "value"}, "unknown")
        assert result.conforms is True  # no shapes = no violations
