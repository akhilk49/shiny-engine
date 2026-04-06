"""LLM Engine — sends prompts to Ollama or OpenAI backends with retry logic."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Iterator

from src.models import LLMConfig, LLMUnavailableError, ProcessedText

if TYPE_CHECKING:
    pass


class LLMEngine:
    """Sends a prompt to the configured LLM backend and returns the response."""

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        # Lazy-loaded backend clients
        self._ollama = None
        self._openai_client = None

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def build_prompt(self, processed: ProcessedText) -> str:
        """Substitute processed.content into the configured prompt template."""
        return self._config.prompt_template.replace("{text}", processed.content)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        """Return True when the configured backend is reachable."""
        try:
            if self._config.backend == "ollama":
                ollama = self._get_ollama()
                ollama.list()
            else:
                client = self._get_openai_client()
                client.models.list()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Query (blocking)
    # ------------------------------------------------------------------

    def query(self, prompt: str) -> str:
        """Send prompt to the backend and return the full response string."""
        return self._with_retry(self._query_once, prompt)

    def _query_once(self, prompt: str) -> str:
        if self._config.backend == "ollama":
            return self._ollama_query(prompt)
        return self._openai_query(prompt)

    # ------------------------------------------------------------------
    # Streaming query
    # ------------------------------------------------------------------

    def query_stream(self, prompt: str) -> Iterator[str]:
        """Yield response tokens; concatenating them equals the full response."""
        # Collect via retry, then yield tokens.
        # We buffer the full response so retry logic applies uniformly.
        response = self._with_retry(self._query_once, prompt)
        yield response

    # ------------------------------------------------------------------
    # Backend implementations
    # ------------------------------------------------------------------

    def _ollama_query(self, prompt: str) -> str:
        ollama = self._get_ollama()
        response = ollama.chat(
            model=self._config.model,
            messages=[{"role": "user", "content": prompt}],
            options={
                "num_predict": self._config.max_tokens,
                "temperature": self._config.temperature,
            },
        )
        # ollama.chat returns an object; handle both attribute and dict access
        if hasattr(response, "message"):
            return response.message.content
        return response["message"]["content"]

    def _openai_query(self, prompt: str) -> str:
        client = self._get_openai_client()
        completion = client.chat.completions.create(
            model=self._config.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=self._config.max_tokens,
            temperature=self._config.temperature,
            timeout=self._config.timeout_seconds,
        )
        return completion.choices[0].message.content

    # ------------------------------------------------------------------
    # Retry with exponential backoff
    # ------------------------------------------------------------------

    def _with_retry(self, fn, *args):
        """Call fn(*args), retrying with exponential backoff on connection errors."""
        delay = 1.0
        last_exc: Exception | None = None

        for attempt in range(self._config.retry_attempts):
            try:
                return fn(*args)
            except (TimeoutError, ConnectionError, OSError) as exc:
                last_exc = exc
                if attempt + 1 < self._config.retry_attempts:
                    time.sleep(delay)
                    delay *= 2
            except Exception:
                # Non-connection errors should propagate immediately
                raise

        raise LLMUnavailableError(
            f"LLM backend '{self._config.backend}' unreachable after "
            f"{self._config.retry_attempts} attempt(s): {last_exc}"
        ) from last_exc

    # ------------------------------------------------------------------
    # API key management
    # ------------------------------------------------------------------

    @staticmethod
    def store_api_key(key: str) -> None:
        """Store the OpenAI API key in the OS keychain."""
        import keyring as _keyring  # noqa: PLC0415
        _keyring.set_password("screen-ai-assistant", "openai_api_key", key)

    # ------------------------------------------------------------------
    # Lazy backend loaders
    # ------------------------------------------------------------------

    def _get_ollama(self):
        if self._ollama is None:
            import ollama as _ollama  # noqa: PLC0415
            self._ollama = _ollama
        return self._ollama

    def _get_openai_client(self):
        if self._openai_client is None:
            import keyring as _keyring  # noqa: PLC0415
            import openai as _openai  # noqa: PLC0415
            api_key = _keyring.get_password("screen-ai-assistant", "openai_api_key")
            if api_key is None:
                api_key = self._config.api_key
            self._openai_client = _openai.OpenAI(
                api_key=api_key,
                base_url=self._config.base_url,
                timeout=self._config.timeout_seconds,
            )
        return self._openai_client
