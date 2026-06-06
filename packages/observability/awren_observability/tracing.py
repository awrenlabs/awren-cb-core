"""Distributed tracing for the Awren Cognitive OS."""
from typing import Any, Dict, Optional
from uuid import UUID, uuid4
from datetime import datetime

class Tracer:
    """Simple distributed tracer for request tracking."""
    def __init__(self):
        self._spans: Dict[str, Dict[str, Any]] = {}

    def start_span(self, name: str, parent_id: Optional[str] = None) -> str:
        span_id = str(uuid4())
        self._spans[span_id] = {
            "name": name,
            "span_id": span_id,
            "parent_id": parent_id,
            "start_time": datetime.utcnow().isoformat(),
            "end_time": None,
            "attributes": {},
        }
        return span_id

    def end_span(self, span_id: str) -> None:
        if span_id in self._spans:
            self._spans[span_id]["end_time"] = datetime.utcnow().isoformat()

    def add_attribute(self, span_id: str, key: str, value: Any) -> None:
        if span_id in self._spans:
            self._spans[span_id]["attributes"][key] = value
