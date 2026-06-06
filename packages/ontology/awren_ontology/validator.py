"""SHACL validation framework for ontology conformance."""

from typing import Any, Dict, List


class SHACLValidationResult:
    """Result of a SHACL validation operation."""
    def __init__(self, conforms: bool, violations: List[Dict[str, Any]]):
        self.conforms = conforms
        self.violations = violations


class SHACLValidator:
    """Validates data against SHACL shapes defined in an ontology."""

    def __init__(self):
        self._shapes: Dict[str, Any] = {}

    def load_shapes(self, ontology_name: str, shapes: Dict[str, Any]) -> None:
        """Load SHACL shapes for an ontology."""
        self._shapes[ontology_name] = shapes

    def validate(self, data: Dict[str, Any], ontology_name: str) -> SHACLValidationResult:
        """Validate data against the ontology's shapes."""
        shapes = self._shapes.get(ontology_name, {})
        violations = []
        for shape_id, shape_def in shapes.items():
            for constraint in shape_def.get("constraints", []):
                if not self._check_constraint(data, constraint):
                    violations.append({
                        "shape": shape_id,
                        "constraint": constraint,
                        "message": f"Constraint violated: {constraint.get('message', '')}",
                    })
        return SHACLValidationResult(conforms=len(violations) == 0, violations=violations)

    def _check_constraint(self, data: Dict[str, Any], constraint: Dict[str, Any]) -> bool:
        """Check a single constraint against data."""
        constraint_type = constraint.get("type")
        path = constraint.get("path")
        value = data.get(path)
        if constraint_type == "minCount" and value is None:
            return False
        if constraint_type == "nodeKind" and value is not None:
            expected = constraint.get("kind")
            if expected == "IRI" and not isinstance(value, str):
                return False
        return True
