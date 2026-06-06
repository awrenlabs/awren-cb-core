# ADR-003: Event Sourcing Strategy

**Status**: Approved
**Date**: 2026-06-06

## Context
The system needs a complete, auditable history of all changes.

## Decision
Use an append-only event log as the primary record. Current state is derived by replaying events.

## Consequences
- Complete audit trail
- Temporal query support
- Event log grows unbounded (requires compaction)
