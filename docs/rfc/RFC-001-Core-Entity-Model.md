# RFC-001: Core Entity Model

**Status**: Draft
**Date**: 2026-06-06

## Summary
Define the fundamental entity model that all domain entities extend.

## Motivation
A consistent entity model is required for interoperability across all packages.

## Design
BaseEntity with UUID, type, label, properties, identifiers, and metadata fields.

## Open Questions
- Should we support soft deletes?
- How do we handle entity versioning?
