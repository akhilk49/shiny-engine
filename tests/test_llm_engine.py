"""Unit tests for LLMEngine."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch, call
import pytest

from src.models import LLMConfig, LLMUnavailableError, ProcessedText, TextClass
from src.llm_engine.llm_engine import LLMEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_config(**kwargs) -> LLMConfig:
    defaults = dict(
        backend="ollama",
        model="llama3",
        base_url="http://localhost:11434",
        api_key=None,
        max_tokens=512,
        temperature=0.3,
        timeout_seconds=10,
        retry_attempts=3,
        prompt_template="You are an assistant.\n\nInput: {text}",
    )
    defaults.update(kwargs)
    return LLMConfig(**defaults)


def make_processed(content: str = "Hello world") -> ProcessedText:
    return ProcessedText(
        content=content,
        classification=TextClass.PARAGRAPH,
        word_count=len(content.split()),
        is_empty=False,
    )


def _make_ollama_response(content: str) -> dict:
    """Simulate the dict-like response from ollama.chat()."""
    return {"message": {"content": content}}


# ---------------------------------------------------------------------------
# build_prompt
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    def test_substitutes_text_placeholder(self):
        engine = LLMEngine(make_config(prompt_template="Answer: {text}"))
        result = engine.build_prompt(make_processed("What is 2+2?"))
        assert result == "Answer: What is 2+2?"

    def test_template_without_placeholder_unchanged(self):
        engine = LLMEngine(make_config(prompt_template="No placeholder here"))
        result = engine.build_prompt(make_processed("ignored"))
        assert result == "No placeholder here"

    def test_multiline_template(self):
        template = "System: helpful\n\nUser: {text}\n"
        engine = LLMEngine(make_config(prompt_template=template))
        result = engine.build_prompt(make_processed("hi"))
        assert result == "System: helpful\n\nUser: hi\n"


# ---------------------------------------------------------------------------
# query — ollama backend
# ---------------------------------------------------------------------------

class TestQueryOllama:
    def _make_engine_with_mock_ollama(self, response_content: str) -> tuple[LLMEngine, MagicMock]:
        config = make_config(backend="ollama", retry_attempts=1)
        engine = LLMEngine(config)
        mock_ollama = MagicMock()
        mock_ollama.chat.return_value = _make_ollama_response(response_content)
        engine._ollama = mock_ollama
        return engine, mock_ollama

    def test_query_returns_non_empty_string(self):
        engine, _ = self._make_engine_with_mock_ollama("The answer is 42.")
        result = engine.query("What is the answer?")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_query_returns_backend_response(self):
        engine, _ = self._make_engine_with_mock_ollama("Hello from Ollama!")
        result = engine.query("Say hello")
        assert result == "Hello from Ollama!"

    def test_query_passes_prompt_to_backend(self):
        engine, mock_ollama = self._make_engine_with_mock_ollama("ok")
        engine.query("my prompt")
        mock_ollama.chat.assert_called_once()
        call_kwargs = mock_ollama.chat.call_args
        messages = call_kwargs[1]["messages"] if call_kwargs[1] else call_kwargs[0][1]
        # Check the prompt appears in the messages
        assert any("my prompt" in str(m) for m in mock_ollama.chat.call_args_list)


# ---------------------------------------------------------------------------
# query — openai backend
# ---------------------------------------------------------------------------

class TestQueryOpenAI:
    def _make_engine_with_mock_openai(self, response_content: str) -> tuple[LLMEngine, MagicMock]:
        config = make_config(backend="openai", api_key="test-key", retry_attempts=1)
        engine = LLMEngine(config)
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = response_content
        mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
        engine._openai_client = mock_client
        return engine, mock_client

    def test_query_returns_non_empty_string(self):
        engine, _ = self._make_engine_with_mock_openai("OpenAI response here.")
        result = engine.query("Tell me something")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_query_returns_backend_response(self):
        engine, _ = self._make_engine_with_mock_openai("GPT says hi")
        result = engine.query("Say hi")
        assert result == "GPT says hi"


# ---------------------------------------------------------------------------
# query_stream
# ---------------------------------------------------------------------------

class TestQueryStream:
    def test_stream_yields_tokens(self):
        config = make_config(backend="ollama", retry_attempts=1)
        engine = LLMEngine(config)
        mock_ollama = MagicMock()
        mock_ollama.chat.return_value = _make_ollama_response("token1 token2 token3")
        engine._ollama = mock_ollama

        tokens = list(engine.query_stream("prompt"))
        assert len(tokens) > 0

    def test_stream_concatenates_to_full_response(self):
        full_response = "The full response text."
        config = make_config(backend="ollama", retry_attempts=1)
        engine = LLMEngine(config)
        mock_ollama = MagicMock()
        mock_ollama.chat.return_value = _make_ollama_response(full_response)
        engine._ollama = mock_ollama

        streamed = "".join(engine.query_stream("prompt"))
        direct = engine.query("prompt")
        assert streamed == direct
        assert streamed == full_response


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_health_check_returns_true_when_reachable_ollama(self):
        config = make_config(backend="ollama")
        engine = LLMEngine(config)
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = []
        engine._ollama = mock_ollama

        assert engine.health_check() is True

    def test_health_check_returns_false_when_unreachable_ollama(self):
        config = make_config(backend="ollama")
        engine = LLMEngine(config)
        mock_ollama = MagicMock()
        mock_ollama.list.side_effect = ConnectionError("refused")
        engine._ollama = mock_ollama

        assert engine.health_check() is False

    def test_health_check_returns_true_when_reachable_openai(self):
        config = make_config(backend="openai", api_key="key")
        engine = LLMEngine(config)
        mock_client = MagicMock()
        mock_client.models.list.return_value = []
        engine._openai_client = mock_client

        assert engine.health_check() is True

    def test_health_check_returns_false_when_unreachable_openai(self):
        config = make_config(backend="openai", api_key="key")
        engine = LLMEngine(config)
        mock_client = MagicMock()
        mock_client.models.list.side_effect = ConnectionError("refused")
        engine._openai_client = mock_client

        assert engine.health_check() is False


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------

class TestRetryLogic:
    def test_retries_on_connection_error(self):
        config = make_config(backend="ollama", retry_attempts=3)
        engine = LLMEngine(config)
        mock_ollama = MagicMock()
        # Fail twice, succeed on third
        mock_ollama.chat.side_effect = [
            ConnectionError("fail 1"),
            ConnectionError("fail 2"),
            _make_ollama_response("success"),
        ]
        engine._ollama = mock_ollama

        with patch("time.sleep"):
            result = engine.query("prompt")

        assert result == "success"
        assert mock_ollama.chat.call_count == 3

    def test_llm_unavailable_error_after_all_retries_exhausted(self):
        config = make_config(backend="ollama", retry_attempts=3)
        engine = LLMEngine(config)
        mock_ollama = MagicMock()
        mock_ollama.chat.side_effect = ConnectionError("always fails")
        engine._ollama = mock_ollama

        with patch("time.sleep"):
            with pytest.raises(LLMUnavailableError):
                engine.query("prompt")

    def test_retry_count_never_exceeds_retry_attempts(self):
        for max_retries in [1, 2, 3, 4, 5]:
            config = make_config(backend="ollama", retry_attempts=max_retries)
            engine = LLMEngine(config)
            mock_ollama = MagicMock()
            mock_ollama.chat.side_effect = ConnectionError("always fails")
            engine._ollama = mock_ollama

            with patch("time.sleep"):
                with pytest.raises(LLMUnavailableError):
                    engine.query("prompt")

            assert mock_ollama.chat.call_count <= max_retries, (
                f"Expected at most {max_retries} calls, got {mock_ollama.chat.call_count}"
            )

    def test_retry_count_equals_retry_attempts_on_total_failure(self):
        """Verify the engine makes exactly retry_attempts calls when all fail."""
        config = make_config(backend="ollama", retry_attempts=3)
        engine = LLMEngine(config)
        mock_ollama = MagicMock()
        mock_ollama.chat.side_effect = ConnectionError("always fails")
        engine._ollama = mock_ollama

        with patch("time.sleep"):
            with pytest.raises(LLMUnavailableError):
                engine.query("prompt")

        assert mock_ollama.chat.call_count == 3

    def test_exponential_backoff_delays(self):
        """Verify sleep is called with doubling delays."""
        config = make_config(backend="ollama", retry_attempts=3)
        engine = LLMEngine(config)
        mock_ollama = MagicMock()
        mock_ollama.chat.side_effect = ConnectionError("always fails")
        engine._ollama = mock_ollama

        sleep_calls = []
        with patch("time.sleep", side_effect=lambda d: sleep_calls.append(d)):
            with pytest.raises(LLMUnavailableError):
                engine.query("prompt")

        # With 3 attempts: sleep after attempt 0 (1s) and attempt 1 (2s); no sleep after last
        assert sleep_calls == [1.0, 2.0]

    def test_no_sleep_on_single_attempt_failure(self):
        """With retry_attempts=1, no sleep should occur."""
        config = make_config(backend="ollama", retry_attempts=1)
        engine = LLMEngine(config)
        mock_ollama = MagicMock()
        mock_ollama.chat.side_effect = ConnectionError("fail")
        engine._ollama = mock_ollama

        with patch("time.sleep") as mock_sleep:
            with pytest.raises(LLMUnavailableError):
                engine.query("prompt")

        mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# Keyring / API key storage (Requirement 11.3)
# ---------------------------------------------------------------------------

def _make_mock_keyring(get_password_return=None):
    """Return a mock keyring module."""
    mock_kr = MagicMock()
    mock_kr.get_password.return_value = get_password_return
    return mock_kr


class TestStoreApiKey:
    def test_store_api_key_calls_keyring_set_password(self):
        mock_kr = _make_mock_keyring()
        with patch.dict("sys.modules", {"keyring": mock_kr}):
            LLMEngine.store_api_key("sk-test-123")
        mock_kr.set_password.assert_called_once_with(
            "screen-ai-assistant", "openai_api_key", "sk-test-123"
        )


class TestGetOpenAIClientKeyring:
    def test_uses_keyring_key_when_available(self):
        """_get_openai_client should use the keyring key when keyring returns one."""
        config = make_config(backend="openai", api_key="config-key", retry_attempts=1)
        engine = LLMEngine(config)

        mock_kr = _make_mock_keyring(get_password_return="keyring-key")
        mock_openai_module = MagicMock()
        mock_client_instance = MagicMock()
        mock_openai_module.OpenAI.return_value = mock_client_instance

        with patch.dict("sys.modules", {"keyring": mock_kr, "openai": mock_openai_module}):
            client = engine._get_openai_client()

        mock_kr.get_password.assert_called_once_with("screen-ai-assistant", "openai_api_key")
        mock_openai_module.OpenAI.assert_called_once()
        _, kwargs = mock_openai_module.OpenAI.call_args
        assert kwargs["api_key"] == "keyring-key"
        assert client is mock_client_instance

    def test_falls_back_to_config_api_key_when_keyring_returns_none(self):
        """_get_openai_client should fall back to config.api_key when keyring returns None."""
        config = make_config(backend="openai", api_key="config-key", retry_attempts=1)
        engine = LLMEngine(config)

        mock_kr = _make_mock_keyring(get_password_return=None)
        mock_openai_module = MagicMock()
        mock_client_instance = MagicMock()
        mock_openai_module.OpenAI.return_value = mock_client_instance

        with patch.dict("sys.modules", {"keyring": mock_kr, "openai": mock_openai_module}):
            client = engine._get_openai_client()

        mock_kr.get_password.assert_called_once_with("screen-ai-assistant", "openai_api_key")
        mock_openai_module.OpenAI.assert_called_once()
        _, kwargs = mock_openai_module.OpenAI.call_args
        assert kwargs["api_key"] == "config-key"
        assert client is mock_client_instance

    def test_keyring_key_takes_precedence_over_config_key(self):
        """When both keyring and config have keys, keyring wins."""
        config = make_config(backend="openai", api_key="config-key", retry_attempts=1)
        engine = LLMEngine(config)

        mock_kr = _make_mock_keyring(get_password_return="keyring-key")
        mock_openai_module = MagicMock()
        mock_openai_module.OpenAI.return_value = MagicMock()

        with patch.dict("sys.modules", {"keyring": mock_kr, "openai": mock_openai_module}):
            engine._get_openai_client()

        _, kwargs = mock_openai_module.OpenAI.call_args
        assert kwargs["api_key"] == "keyring-key"
        assert kwargs["api_key"] != "config-key"
