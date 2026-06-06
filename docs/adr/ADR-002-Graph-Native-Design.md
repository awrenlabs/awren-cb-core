# ADR-002: Graph-Native Design

**Status**: Approved
**Date**: 2026-06-06

## Context
The system needs to store and query complex, interconnected data across multiple domains.

## Decision
The primary data store will be a graph database with native RDF/SPARQL support.

## Consequences
- Natural representation of interconnected knowledge
- Direct support for RDF/OWL semantics
- Team must develop graph query expertise

## Alternatives Considered
- Relational (impedance mismatch for graph data)
- Document store (poor relationship support)
