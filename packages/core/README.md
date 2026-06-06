# Awren Core — Core Package

Base entity, event, and relationship models for the Awren Cognitive OS.

## Components

- **BaseEntity**: Fundamental unit of representation in the knowledge graph
- **BaseRelationship**: Typed edge connecting two entities
- **BaseEvent**: Temporal record of occurrences and changes
- **RepositoryInterface**: Abstract data access interface
- **ServiceInterface**: Abstract service interface

## Usage

```python
from awren_core import BaseEntity, EntityType

organization = BaseEntity(
    type=EntityType.ORGANIZATION,
    label="Acme Construction",
    properties={"revenue": "500M", "employees": 1200},
)
```
