"""Celery worker configuration for background task processing.

Provides async task execution for ingestion, OCR, compression,
and other long-running operations.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from celery import Celery

from awren_core.database import create_session
from awren_core.settings import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()
celery_app = Celery(
    "awren_core",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["awren_core.celery_app"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    task_soft_time_limit=3000,
    worker_prefetch_multiplier=1,
)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def process_import_job(self, job_id: str) -> dict[str, Any]:
    """Process an import job in the background.

    Extracts text, runs LLM entity extraction, creates entities/relationships.
    Called asynchronously after file upload.
    """
    from sqlalchemy import select
    from awren_core.orm_models import ImportJobModel
    from awren_ingestion.processors import DocumentProcessor

    session = create_session()
    try:
        stmt = select(ImportJobModel).where(ImportJobModel.id == UUID(job_id))
        job = session.execute(stmt).scalar_one_or_none()
        if not job:
            raise ValueError(f"Import job {job_id} not found")

        job.status = "processing"
        session.flush()

        processor = DocumentProcessor(session)
        result = processor.process(
            job_id=job.id,
            file_path=job.file_path,
            original_filename=job.original_filename,
        )

        job.status = "completed" if not result["errors"] else "completed_with_errors"
        job.total_entities = result["entities_created"]
        job.total_relationships = result["relationships_created"]
        job.error_messages = result["errors"]
        job.result_summary = result
        job.completed_at = datetime.now(timezone.utc)
        session.commit()

        logger.info(
            "Import job %s completed: %d entities, %d relationships",
            job_id, result["entities_created"], result["relationships_created"],
        )
        return result
    except Exception as exc:
        session.rollback()
        logger.error("Import job %s failed: %s", job_id, exc)
        # Update job status to failed
        try:
            stmt = select(ImportJobModel).where(ImportJobModel.id == UUID(job_id))
            job = session.execute(stmt).scalar_one_or_none()
            if job:
                job.status = "failed"
                job.error_messages = job.error_messages or []
                job.error_messages.append(str(exc))
                session.commit()
        except Exception:
            pass
        raise self.retry(exc=exc)
    finally:
        session.close()


@celery_app.task(bind=True, max_retries=2)
def process_ocr_job(self, file_path: str, file_name: str) -> dict[str, Any]:
    """Extract text from an image or scanned PDF in background."""
    from awren_ingestion.ocr import ocr_image, is_image_file
    from pathlib import Path

    try:
        if not is_image_file(file_path):
            return {"error": "Not a supported image file", "text": ""}

        session = create_session()
        try:
            text = ocr_image(file_path, session)
            return {"text": text, "file": file_name, "status": "completed"}
        finally:
            session.close()
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=2)
def generate_summary(self, text: str, max_length: int = 500) -> str:
    """Generate a summary of text in the background."""
    from awren_ingestion.compression import summarize_text
    session = create_session()
    try:
        summary = summarize_text(text=text, session=session, max_length=max_length)
        return summary
    finally:
        session.close()
