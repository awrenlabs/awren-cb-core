"""Flexible LLM provider abstraction for multi-model AI integration.

Supports:
- OpenAI (GPT-4, GPT-4o-mini, etc.)
- Anthropic (Claude)
- OpenRouter (multi-model gateway)
- Any OpenAI-compatible API (Together, Groq, etc.)

Usage:
    client = create_llm_client()  # Reads config from env/settings
    response = client.chat(
        system_prompt="You are a helpful assistant",
        user_prompt="Hello!",
    )
"""

import json
import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Optional, cast
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    """Supported LLM provider types."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OPENROUTER = "openrouter"
    CUSTOM_OPENAI = "custom_openai"


class LLMClient(ABC):
    """Abstract base for all LLM providers."""

    def __init__(self, model: str) -> None:
        self.model = model

    @abstractmethod
    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        response_format: Optional[dict[str, Any]] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> Optional[str]:
        """Send a chat completion and return the response content string."""
        ...

    @abstractmethod
    def chat_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ):
        """Stream a chat completion, yielding content chunks."""
        ...


class OpenAIClient(LLMClient):
    """Client for OpenAI and any OpenAI-compatible API.

    Works with:
    - OpenAI (api.openai.com)
    - OpenRouter (openrouter.ai/api/v1)
    - Together (api.together.xyz)
    - Groq (api.groq.com)
    - Any OpenAI-compatible endpoint
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: Optional[str] = None,
    ) -> None:
        super().__init__(model)
        from openai import OpenAI

        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        response_format: Optional[dict[str, Any]] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> Optional[str]:
        try:
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if response_format:
                kwargs["response_format"] = response_format
            response = self._client.chat.completions.create(**kwargs)
            return response.choices[0].message.content
        except Exception as e:
            logger.warning("OpenAI API call failed: %s", e)
            return None

    def chat_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ):
        try:
            stream = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
        except Exception as e:
            logger.warning("OpenAI stream failed: %s", e)
            yield f"\n\n[Error: {str(e)}]"


class AnthropicClient(LLMClient):
    """Client for Anthropic Claude models."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
    ) -> None:
        super().__init__(model)
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        response_format: Optional[dict[str, Any]] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> Optional[str]:
        try:
            response = self._client.messages.create(
                model=self.model,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.content[0].text
        except Exception as e:
            logger.warning("Anthropic API call failed: %s", e)
            return None

    def chat_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ):
        try:
            with self._client.messages.stream(
                model=self.model,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            ) as stream:
                for text in stream.text_stream:
                    yield text
        except Exception as e:
            logger.warning("Anthropic stream failed: %s", e)
            yield f"\n\n[Error: {str(e)}]"


def _read_db_cfg(db_session: Session) -> Optional[dict[str, str]]:
    """Read LLM settings from DB. Returns None if no row exists."""
    try:
        from awren_core.orm_models import LlmSettingsModel
        from sqlalchemy import select
        stmt = select(LlmSettingsModel).where(LlmSettingsModel.id == 1)
        result = db_session.execute(stmt)
        cfg = result.scalar_one_or_none()
        if cfg is not None:
            return {
                "provider": cfg.provider,
                "model": cfg.model,
                "openai_api_key": cfg.openai_api_key or "",
                "anthropic_api_key": cfg.anthropic_api_key or "",
            }
    except Exception:
        logger.warning("Failed to read LLM settings from DB", exc_info=True)
    return None


def create_llm_client(db_session: Optional[Session] = None) -> Optional[LLMClient]:
    """Factory: create the appropriate LLM client based on settings.

    Priority:
        1. DB-persisted settings (provider/model/api keys) if ``db_session`` is given
        2. Environment/.env settings as fallback

    Returns ``None`` if no API key is configured for the selected provider.
    """
    from awren_core.settings import get_settings

    settings = get_settings()
    provider = settings.llm_provider
    model: Optional[str] = None
    db_openai_key: Optional[str] = None
    db_anthropic_key: Optional[str] = None

    db_cfg = _read_db_cfg(db_session) if db_session is not None else None
    if db_cfg is not None:
        provider = db_cfg["provider"]
        model = db_cfg["model"]
        db_openai_key = db_cfg["openai_api_key"] or None
        db_anthropic_key = db_cfg["anthropic_api_key"] or None

    # Resolve API key: DB > .env
    openai_api_key = db_openai_key or settings.openai_api_key or None
    anthropic_api_key = db_anthropic_key or settings.anthropic_api_key or None

    # --- Anthropic ---
    if provider == LLMProvider.ANTHROPIC:
        if not anthropic_api_key:
            logger.info("Anthropic API key not configured; LLM disabled")
            return None
        return AnthropicClient(api_key=anthropic_api_key, model=model or settings.anthropic_model)

    # --- OpenAI-compatible (OpenAI, OpenRouter, Custom) ---
    if not openai_api_key:
        logger.info("OpenAI API key not configured; LLM disabled")
        return None

    base_url: Optional[str] = None
    if provider == LLMProvider.OPENROUTER:
        base_url = "https://openrouter.ai/api/v1"
    elif provider == LLMProvider.CUSTOM_OPENAI:
        base_url = settings.openai_base_url or None

    return OpenAIClient(
        api_key=openai_api_key,
        model=model or settings.openai_model,
        base_url=base_url,
    )
