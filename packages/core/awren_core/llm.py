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
        """Send a chat completion and return the response content string.

        Args:
            system_prompt: System-level instruction for the model.
            user_prompt: The user message content.
            response_format: Optional format constraint (e.g. {"type": "json_object"}).
                Only supported by OpenAI-compatible APIs; ignored by Anthropic.
            temperature: Sampling temperature (0-1).
            max_tokens: Maximum tokens in the response.

        Returns:
            The response text, or None if the call failed.
        """
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


class AnthropicClient(LLMClient):
    """Client for Anthropic Claude models.

    Uses the Anthropic Messages API. Note that Anthropic does not support
    ``response_format`` natively — JSON mode is achieved via prompting.
    """

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
        response_format: Optional[dict[str, Any]] = None,  # noqa: ARG002 — ignored, Anthropic doesn't support native JSON mode
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


def create_llm_client() -> Optional[LLMClient]:
    """Factory: create the appropriate LLM client based on settings.

    Reads the current ``Settings`` to determine which provider and
    credentials to use. Returns ``None`` if no API key is configured
    for the selected provider — this allows graceful fallback in
    environments where LLM access is optional.

    Provider resolution:
        - ``anthropic`` → AnthropicClient (requires ``anthropic_api_key``)
        - ``openrouter`` → OpenAIClient with OpenRouter base URL
        - ``custom_openai`` → OpenAIClient with custom ``openai_base_url``
        - ``openai`` (default) → OpenAIClient with default OpenAI endpoint
    """
    from awren_core.settings import get_settings

    settings = get_settings()
    provider = settings.llm_provider

    # --- Anthropic ---
    if provider == LLMProvider.ANTHROPIC:
        api_key = settings.anthropic_api_key
        if not api_key:
            logger.info("Anthropic API key not configured; LLM disabled")
            return None
        return AnthropicClient(api_key=api_key, model=settings.anthropic_model)

    # --- OpenAI-compatible (OpenAI, OpenRouter, Custom) ---
    api_key = settings.openai_api_key
    if not api_key:
        logger.info("OpenAI API key not configured; LLM disabled")
        return None

    base_url: Optional[str] = None
    if provider == LLMProvider.OPENROUTER:
        base_url = "https://openrouter.ai/api/v1"
    elif provider == LLMProvider.CUSTOM_OPENAI:
        base_url = settings.openai_base_url or None

    return OpenAIClient(
        api_key=api_key,
        model=settings.openai_model,
        base_url=base_url,
    )
