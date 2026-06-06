"""Document and data ingestion pipeline."""

from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4


class IngestionPipeline:
    """Pipeline for ingesting documents and data into the knowledge graph."""

    def __init__(self):
        self._processors: List[Any] = []

    def add_processor(self, processor: Any) -> None:
        self._processors.append(processor)

    async def ingest(self, source: str, data: Any) -> Dict[str, Any]:
        result = {"source": source, "entities_created": 0, "entities_updated": 0, "errors": []}
        for processor in self._processors:
            try:
                await processor.process(data, result)
            except Exception as e:
                result["errors"].append(str(e))
        return result
