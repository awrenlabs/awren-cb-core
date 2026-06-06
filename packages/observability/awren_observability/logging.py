"""Structured logging for the Awren Cognitive OS."""
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

class StructuredLogger:
    """Provides structured JSON logging."""
    def __init__(self, name: str):
        self._logger = logging.getLogger(name)
        self._context: Dict[str, Any] = {}

    def bind(self, **kwargs) -> None:
        self._context.update(kwargs)

    def _log(self, level: str, message: str, **kwargs) -> None:
        record = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "message": message,
            "context": self._context,
            **kwargs,
        }
        log_fn = getattr(self._logger, level.lower(), self._logger.info)
        log_fn(json.dumps(record))

    def info(self, msg: str, **kwargs) -> None:
        self._log("info", msg, **kwargs)

    def error(self, msg: str, **kwargs) -> None:
        self._log("error", msg, **kwargs)

    def warn(self, msg: str, **kwargs) -> None:
        self._log("warn", msg, **kwargs)

    def debug(self, msg: str, **kwargs) -> None:
        self._log("debug", msg, **kwargs)
