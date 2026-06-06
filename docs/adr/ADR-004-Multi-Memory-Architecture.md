# ADR-004: Multi-Memory Architecture

**Status**: Approved
**Date**: 2026-06-06

## Context
Organizational knowledge spans multiple types that require different storage and retrieval strategies.

## Decision
Implement four memory types: Episodic, Semantic, Procedural, and Working.

## Consequences
- Each memory type optimized for its use case
- More complex query routing
- Natural separation of concerns
