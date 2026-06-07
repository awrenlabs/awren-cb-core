"""Information Compression — smart chunking, summarization, deduplication."""

import hashlib
import logging
import re
from typing import Any, Optional
from uuid import UUID

from awren_core.llm import create_llm_client
from awren_core.models import BaseEntity

logger = logging.getLogger(__name__)


def chunk_text(text: str, chunk_size: int = 2000, overlap: int = 200) -> list[dict]:
    """Split text into overlapping chunks for embedding/processing.
    
    Args:
        text: Input text to chunk
        chunk_size: Target characters per chunk
        overlap: Number of overlapping characters between chunks
    
    Returns:
        List of dicts with 'text', 'index', 'start_char', 'end_char'
    """
    if len(text) <= chunk_size:
        return [{"text": text, "index": 0, "start_char": 0, "end_char": len(text)}]

    chunks = []
    start = 0
    index = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))
        
        # Try to break at sentence boundary
        if end < len(text):
            # Look for sentence end within the last 20% of the chunk
            search_start = max(start, end - int(chunk_size * 0.2))
            segment = text[search_start:end]
            # Find last sentence boundary (.!? followed by space or newline)
            for sep in ["\n\n", "\n", ". ", "! ", "? "]:
                pos = segment.rfind(sep)
                if pos != -1:
                    end = search_start + pos + len(sep)
                    break

        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append({
                "text": chunk_text,
                "index": index,
                "start_char": start,
                "end_char": end,
                "fingerprint": hashlib.md5(chunk_text.encode()).hexdigest()[:12],
            })
            index += 1

        # Move start, accounting for overlap
        start = end - overlap if end < len(text) else len(text)

    return chunks


async def summarize_text(text: str, session, max_length: int = 500) -> str:
    """Summarize a text using the LLM."""
    llm = create_llm_client(db_session=session)
    if not llm:
        return text[:max_length] + "..." if len(text) > max_length else text

    prompt = (
        f"Summarize the following text in {max_length} characters or less. "
        f"Capture only the key facts, entities, and relationships. Be concise.\n\n{text[:6000]}"
    )
    try:
        result = llm.chat(
            system_prompt="You are an information compression engine. Be concise and factual.",
            user_prompt=prompt,
            temperature=0.3,
            max_tokens=1000,
        )
        return result or text[:max_length]
    except Exception as e:
        logger.warning("Summarization failed: %s", e)
        return text[:max_length]


async def deduplicate_entities(
    entities: list[BaseEntity], session
) -> tuple[list[BaseEntity], list[dict]]:
    """Detect and merge duplicate entities based on label similarity.
    
    Returns (unique_entities, merge_log).
    """
    merge_log = []
    seen: dict[str, BaseEntity] = {}
    unique: list[BaseEntity] = []

    for entity in entities:
        key = _entity_dedup_key(entity)
        existing = seen.get(key)
        if existing:
            merge_log.append({
                "kept": existing.label,
                "removed": entity.label,
                "reason": "Label similarity",
            })
        else:
            seen[key] = entity
            unique.append(entity)

    return unique, merge_log


def _entity_dedup_key(entity: BaseEntity) -> str:
    """Generate a deduplication key for an entity.
    Normalizes the label for comparison.
    """
    label = entity.label.lower().strip()
    # Remove common prefixes/suffixes
    label = re.sub(r"^(the|a|an|corp|inc|ltd|llc|s.a.)\s+", "", label)
    label = re.sub(r"\s+(corp|inc|ltd|llc|s\.a\.)$", "", label)
    # Normalize whitespace
    label = re.sub(r"\s+", " ", label)
    # Use label + type as key
    return f"{entity.type}:{label}"


def compress_entity_for_storage(entity: BaseEntity) -> dict:
    """Compress an entity into a minimal storage representation.
    Strips unnecessary metadata while preserving semantic value.
    """
    minimal_props = {}
    for k, v in entity.properties.items():
        if v is not None and v != "" and v != 0 and v != "0":
            minimal_props[k] = v

    return {
        "id": str(entity.id),
        "t": entity.type.split(":")[-1],  # Compress type (core:Person → Person)
        "l": entity.label[:100],          # Truncate long labels
        "p": minimal_props,
        "s": entity.state or "active",
    }
