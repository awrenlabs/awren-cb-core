# ADR-001: Ontology-First Architecture

**Status**: Approved
**Date**: 2026-06-06

## Context
Awren Core needs to represent complex, multi-domain knowledge in a machine-readable, verifiable, and composable way.

## Decision
All data MUST be typed against a formal OWL 2 ontology. The ontology is the source of truth for data semantics.

## Consequences
- Formal semantics enable reasoning and inference
- Cross-domain integration through ontology alignment
- Higher initial modeling cost

## Alternatives Considered
- JSON Schema only (too weak for reasoning)
- Relational model only (no graph semantics)
- Free-form vectors (no formal semantics)
