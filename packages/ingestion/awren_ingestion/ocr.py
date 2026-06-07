"""OCR Engine — text extraction from images and scanned PDFs using LLM Vision API."""

import base64
import logging
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image

from awren_core.llm import create_llm_client

logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_FORMATS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}


def is_image_file(file_path: str) -> bool:
    """Check if file is a supported image format."""
    ext = Path(file_path).suffix.lower()
    return ext in SUPPORTED_IMAGE_FORMATS


def is_scanned_pdf(file_path: str) -> bool:
    """Heuristic: check if a PDF has extractable text or is scanned.
    Returns True if the PDF has no extractable text (likely scanned).
    """
    try:
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        for page in reader.pages:
            text = page.extract_text()
            if text and text.strip():
                return False  # Has extractable text
        return True  # No text found → likely scanned
    except Exception:
        return False


async def ocr_image(file_path: str, session) -> str:
    """Extract text from an image using LLM Vision API (GPT-4o or compatible).
    
    Falls back to a descriptive prompt when the model can't do OCR.
    """
    # Read and compress image
    img = Image.open(file_path)
    
    # Resize if too large (max 2048px on longest side)
    max_dim = 2048
    if max(img.size) > max_dim:
        ratio = max_dim / max(img.size)
        img = img.resize((int(img.size[0] * ratio), int(img.size[1] * ratio)), Image.LANCZOS)
    
    # Save as compressed JPEG
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        img.save(tmp, format="JPEG", quality=85)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")

        llm = create_llm_client(db_session=session)
        if not llm:
            return "[OCR unavailable: no LLM configured]"

        prompt = (
            "You are an OCR engine. Extract ALL text visible in this image exactly as written. "
            "Preserve the original formatting, line breaks, and structure. "
            "If the image contains a table, format it as markdown table. "
            "Return ONLY the extracted text, no explanations."
        )

        # Try to use vision API
        try:
            raw = llm.chat_vision(
                system_prompt="You are an OCR engine. Return ONLY the extracted text.",
                user_prompt=prompt,
                image_base64=b64_data,
                temperature=0.1,
                max_tokens=4096,
            )
            return raw or "[No text detected in image]"
        except AttributeError:
            # chat_vision not available, use regular chat with description
            raw = llm.chat(
                system_prompt="You are an OCR engine.",
                user_prompt=f"Describe all text visible in this image (base64 JPEG, ~{len(b64_data)} bytes): {prompt}",
                temperature=0.1,
                max_tokens=4096,
            )
            return raw or "[No text detected]"
    finally:
        Path(tmp_path).unlink(missing_ok=True)


async def ocr_pdf_as_images(file_path: str, session) -> list[str]:
    """Extract text from a scanned PDF by rendering pages as images and OCR-ing each.
    
    Requires: pdf2image (poppler) or PyMuPDF for PDF→image conversion.
    Falls back to a warning if neither is available.
    """
    try:
        import fitz  # PyMuPDF
        pages_text = []
        doc = fitz.open(file_path)
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=200)
            img_data = pix.tobytes("png")
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(img_data)
                tmp_path = tmp.name
            try:
                text = await ocr_image(tmp_path, session)
                pages_text.append(f"--- Page {page_num + 1} ---\n{text}")
            finally:
                Path(tmp_path).unlink(missing_ok=True)
        doc.close()
        return pages_text
    except ImportError:
        logger.warning("PyMuPDF not installed. Install with: pip install pymupdf")
        return ["[OCR requires PyMuPDF (pymupdf) for PDF page rendering. Install with: pip install pymupdf]"]
    except Exception as e:
        logger.error("PDF OCR failed: %s", e)
        return [f"[PDF OCR error: {e}]"]
