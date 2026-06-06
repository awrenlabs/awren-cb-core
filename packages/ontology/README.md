# Awren Core — Ontology Package

OWL 2 ontology management for the Awren Cognitive OS.

## Components

- **OntologyRegistry**: Central registry for domain ontologies
- **OntologyClass**: OWL class definitions
- **OntologyProperty**: OWL property/relationship definitions
- **SHACLValidator**: Data validation against ontology shapes

## Usage

```python
from awren_ontology import OntologyRegistry, Ontology

ontology = Ontology(
    name="construction",
    namespace="https://awren.ai/ontology/construction",
    classes={
        "con:Project": OntologyClass(id="con:Project", label="Construction Project"),
    },
)
OntologyRegistry.register(ontology)
```
