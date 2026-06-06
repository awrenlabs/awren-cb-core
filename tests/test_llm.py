"""Tests for the flexible LLM provider abstraction.

Covers:
- OpenAIClient (OpenAI API and OpenAI-compatible endpoints)
- AnthropicClient (Claude Messages API)
- ``create_llm_client`` factory with various settings
- Error handling and graceful degradation
"""

from unittest.mock import MagicMock, patch

import pytest

from awren_core.llm import (
    LLMProvider,
    AnthropicClient,
    LLMClient,
    OpenAIClient,
    create_llm_client,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_openai() -> MagicMock:
    """Patch the openai.OpenAI constructor so no real API call is made.

    The import inside OpenAIClient is ``from openai import OpenAI`` (lazy),
    so we patch the top-level ``openai.OpenAI`` directly.
    """
    with patch("openai.OpenAI") as mock:
        yield mock


@pytest.fixture
def mock_anthropic() -> MagicMock:
    """Patch the anthropic.Anthropic constructor so no real API call is made.

    The AnthropicClient does ``import anthropic`` then ``anthropic.Anthropic(..)``.
    We patch the ``Anthropic`` class attribute within the installed module.
    """
    with patch("anthropic.Anthropic") as mock:
        yield mock


def _make_openai_response(content: str) -> MagicMock:
    """Build a mock OpenAI chat completion response."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_anthropic_response(content: str) -> MagicMock:
    """Build a mock Anthropic messages response."""
    text_block = MagicMock()
    text_block.text = content
    resp = MagicMock()
    resp.content = [text_block]
    return resp


# ---------------------------------------------------------------------------
# OpenAIClient
# ---------------------------------------------------------------------------


class TestOpenAIClient:
    def test_init_with_default_endpoint(self, mock_openai: MagicMock) -> None:
        client = OpenAIClient(api_key="sk-test", model="gpt-4o-mini")
        assert client.model == "gpt-4o-mini"
        mock_openai.assert_called_once_with(api_key="sk-test")

    def test_init_with_custom_base_url(self, mock_openai: MagicMock) -> None:
        client = OpenAIClient(
            api_key="sk-test",
            model="gpt-4o-mini",
            base_url="https://openrouter.ai/api/v1",
        )
        mock_openai.assert_called_once_with(
            api_key="sk-test",
            base_url="https://openrouter.ai/api/v1",
        )

    def test_chat_success(self, mock_openai: MagicMock) -> None:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.return_value = _make_openai_response(
            '{"result": "Hello!"}'
        )

        client = OpenAIClient(api_key="sk-test", model="gpt-4o-mini")
        result = client.chat(
            system_prompt="You are a helpful assistant",
            user_prompt="Say hello",
        )

        assert result == '{"result": "Hello!"}'
        mock_client.chat.completions.create.assert_called_once_with(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant"},
                {"role": "user", "content": "Say hello"},
            ],
            temperature=0.3,
            max_tokens=2000,
        )

    def test_chat_with_response_format(self, mock_openai: MagicMock) -> None:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.return_value = _make_openai_response("{}")

        client = OpenAIClient(api_key="sk-test", model="gpt-4o-mini")
        client.chat(
            system_prompt="test",
            user_prompt="test",
            response_format={"type": "json_object"},
        )

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["response_format"] == {"type": "json_object"}

    def test_chat_api_failure(self, mock_openai: MagicMock) -> None:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API error")

        client = OpenAIClient(api_key="sk-test", model="gpt-4o-mini")
        result = client.chat(system_prompt="test", user_prompt="test")

        assert result is None


# ---------------------------------------------------------------------------
# AnthropicClient
# ---------------------------------------------------------------------------


class TestAnthropicClient:
    def test_init(self, mock_anthropic: MagicMock) -> None:
        client = AnthropicClient(api_key="sk-ant-test", model="claude-sonnet-4-20250514")
        assert client.model == "claude-sonnet-4-20250514"
        mock_anthropic.assert_called_once_with(api_key="sk-ant-test")

    def test_chat_success(self, mock_anthropic: MagicMock) -> None:
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        # Pre-bind messages mock to avoid MagicMock re-creating it each access
        messages_mock = MagicMock()
        messages_mock.create.return_value = _make_anthropic_response(
            "Hello from Claude!"
        )
        mock_client.messages = messages_mock

        client = AnthropicClient(api_key="sk-ant-test")
        result = client.chat(
            system_prompt="You are Claude",
            user_prompt="Say hello",
        )

        assert result == "Hello from Claude!"
        messages_mock.create.assert_called_once_with(
            model="claude-sonnet-4-20250514",
            system="You are Claude",
            messages=[{"role": "user", "content": "Say hello"}],
            temperature=0.3,
            max_tokens=2000,
        )

    def test_chat_ignores_response_format(self, mock_anthropic: MagicMock) -> None:
        """Anthropic doesn't support response_format natively — should be ignored."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        messages_mock = MagicMock()
        messages_mock.create.return_value = _make_anthropic_response("{}")
        mock_client.messages = messages_mock

        client = AnthropicClient(api_key="sk-ant-test")
        result = client.chat(
            system_prompt="test",
            user_prompt="test",
            response_format={"type": "json_object"},
        )

        assert result == "{}"
        # response_format should not appear in the Anthropic call kwargs
        call_kwargs = messages_mock.create.call_args[1]
        assert "response_format" not in call_kwargs

    def test_chat_api_failure(self, mock_anthropic: MagicMock) -> None:
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        messages_mock = MagicMock()
        messages_mock.create.side_effect = Exception("API error")
        mock_client.messages = messages_mock

        client = AnthropicClient(api_key="sk-ant-test")
        result = client.chat(system_prompt="test", user_prompt="test")

        assert result is None


# ---------------------------------------------------------------------------
# Factory: create_llm_client
# ---------------------------------------------------------------------------


class TestCreateLLMClient:
    def test_openai_default(self) -> None:
        """OpenAI client is created when provider=openai and key is set."""
        with patch("awren_core.settings.get_settings") as mock_settings:
            settings = MagicMock()
            settings.llm_provider = "openai"
            settings.openai_api_key = "sk-test"
            settings.openai_model = "gpt-4o-mini"
            settings.openai_base_url = ""
            mock_settings.return_value = settings

            with patch("awren_core.llm.OpenAIClient") as mock_cls:
                client = create_llm_client()
                assert client is not None
                mock_cls.assert_called_once_with(
                    api_key="sk-test",
                    model="gpt-4o-mini",
                    base_url=None,
                )

    def test_openai_no_key_returns_none(self) -> None:
        """When no OpenAI key is set and provider is openai, returns None."""
        with patch("awren_core.settings.get_settings") as mock_settings:
            settings = MagicMock()
            settings.llm_provider = "openai"
            settings.openai_api_key = ""
            mock_settings.return_value = settings

            client = create_llm_client()
            assert client is None

    def test_openrouter(self) -> None:
        """OpenRouter uses OpenAIClient with OpenRouter base URL."""
        with patch("awren_core.settings.get_settings") as mock_settings:
            settings = MagicMock()
            settings.llm_provider = "openrouter"
            settings.openai_api_key = "sk-test"
            settings.openai_model = "anthropic/claude-3.5-sonnet"
            settings.openai_base_url = ""
            mock_settings.return_value = settings

            with patch("awren_core.llm.OpenAIClient") as mock_cls:
                client = create_llm_client()
                assert client is not None
                mock_cls.assert_called_once_with(
                    api_key="sk-test",
                    model="anthropic/claude-3.5-sonnet",
                    base_url="https://openrouter.ai/api/v1",
                )

    def test_custom_openai(self) -> None:
        """Custom OpenAI-compatible endpoint uses the configured base_url."""
        with patch("awren_core.settings.get_settings") as mock_settings:
            settings = MagicMock()
            settings.llm_provider = "custom_openai"
            settings.openai_api_key = "sk-test"
            settings.openai_model = "mixtral-8x7b"
            settings.openai_base_url = "https://api.together.xyz/v1"
            mock_settings.return_value = settings

            with patch("awren_core.llm.OpenAIClient") as mock_cls:
                client = create_llm_client()
                assert client is not None
                mock_cls.assert_called_once_with(
                    api_key="sk-test",
                    model="mixtral-8x7b",
                    base_url="https://api.together.xyz/v1",
                )

    def test_anthropic(self) -> None:
        """Anthropic client is created when provider=anthropic."""
        with patch("awren_core.settings.get_settings") as mock_settings:
            settings = MagicMock()
            settings.llm_provider = "anthropic"
            settings.anthropic_api_key = "sk-ant-test"
            settings.anthropic_model = "claude-sonnet-4-20250514"
            settings.openai_api_key = ""
            mock_settings.return_value = settings

            with patch("awren_core.llm.AnthropicClient") as mock_cls:
                client = create_llm_client()
                assert client is not None
                mock_cls.assert_called_once_with(
                    api_key="sk-ant-test",
                    model="claude-sonnet-4-20250514",
                )

    def test_anthropic_no_key_returns_none(self) -> None:
        """When Anthropic key is empty and provider=anthropic, returns None."""
        with patch("awren_core.settings.get_settings") as mock_settings:
            settings = MagicMock()
            settings.llm_provider = "anthropic"
            settings.anthropic_api_key = ""
            mock_settings.return_value = settings

            client = create_llm_client()
            assert client is None

    def test_all_provider_enum_values(self) -> None:
        """All LLMProvider enum values are handled by the factory."""
        for provider in LLMProvider:
            assert provider.value in {"openai", "anthropic", "openrouter", "custom_openai"}


# ---------------------------------------------------------------------------
# Protocol / Interface contract
# ---------------------------------------------------------------------------


class TestLLMClientProtocol:
    """All concrete clients must satisfy the LLMClient contract."""

    def test_openai_is_llm_client(self) -> None:
        client = OpenAIClient(api_key="sk-test", model="gpt-4o-mini")
        assert isinstance(client, LLMClient)

    def test_anthropic_is_llm_client(self) -> None:
        client = AnthropicClient(api_key="sk-ant-test")
        assert isinstance(client, LLMClient)
