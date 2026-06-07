"""Text extraction from various file formats."""

import csv
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


def extract_text(file_path: str, mime_type: Optional[str] = None) -> str:
    """Extract text content from a file. Supports PDF, DOCX, CSV, JSON, TXT, MD."""
    ext = Path(file_path).suffix.lower()
    mime = mime_type or ""

    try:
        if ext == ".pdf" or "pdf" in mime:
            return _extract_pdf(file_path)
        elif ext == ".docx" or "word" in mime:
            return _extract_docx(file_path)
        elif ext == ".csv" or "csv" in mime:
            return _extract_csv(file_path)
        elif ext == ".json" or "json" in mime:
            return _extract_json(file_path)
        else:
            # Fallback: read as text
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
    except Exception as e:
        raise RuntimeError(f"Failed to extract text from {file_path}: {e}")


def _extract_pdf(file_path: str) -> str:
    """Extract text from PDF using pypdf."""
    from pypdf import PdfReader
    reader = PdfReader(file_path)
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n\n".join(pages)


def _extract_docx(file_path: str) -> str:
    """Extract text from DOCX using python-docx."""
    from docx import Document
    doc = Document(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def _extract_csv(file_path: str) -> str:
    """Extract text from CSV as structured text."""
    rows = []
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            rows.append(f"Row {i}: " + ", ".join(row))
    return "\n".join(rows)


def _extract_json(file_path: str) -> str:
    """Extract text from JSON as formatted text."""
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        data = json.load(f)
    return json.dumps(data, indent=2, ensure_ascii=False)
