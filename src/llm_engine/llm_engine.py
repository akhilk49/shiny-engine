"""LLM Engine — sends prompts to Ollama, OpenAI, or HuggingFace backends."""

from __future__ import annotations

import time
from typing import Iterator

from src.models import LLMConfig, LLMUnavailableError, ProcessedText


class LLMEngine:
    """Sends a prompt to the configured LLM backend and returns the response."""

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self._ollama = None
        self._openai_client = None
        self._hf_client = None

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def build_prompt(self, processed: ProcessedText) -> str:
        return self._config.prompt_template.replace("{text}", processed.content)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        try:
            if self._config.backend == "ollama":
                self._get_ollama().list()
            elif self._config.backend == "huggingface":
                # Just check the client can be created
                self._get_hf_client()
            else:
                self._get_openai_client().models.list()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(self, prompt: str) -> str:
        return self._with_retry(self._query_once, prompt)

    def _query_once(self, prompt: str) -> str:
        if self._config.backend == "ollama":
            return self._ollama_query(prompt)
        if self._config.backend == "huggingface":
            return self._hf_query(prompt)
        return self._openai_query(prompt)

    def query_stream(self, prompt: str) -> Iterator[str]:
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

    def _hf_query(self, prompt: str) -> str:
        """Query HuggingFace Inference API using chat completion."""
        client = self._get_hf_client()
        response = client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model=self._config.model,
            max_tokens=self._config.max_tokens,
            temperature=self._config.temperature,
        )
        return response.choices[0].message.content

    # ------------------------------------------------------------------
    # Retry
    # ------------------------------------------------------------------

    def _with_retry(self, fn, *args):
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
                raise
        raise LLMUnavailableError(
            f"LLM backend '{self._config.backend}' unreachable after "
            f"{self._config.retry_attempts} attempt(s): {last_exc}"
        ) from last_exc

    # ------------------------------------------------------------------
    # API key management
    # ------------------------------------------------------------------

    @staticmethod
    def store_api_key(key: str, service: str = "openai_api_key") -> None:
        import keyring as _keyring
        _keyring.set_password("screen-ai-assistant", service, key)

    def _get_hf_api_key(self) -> str | None:
        try:
            import keyring as _keyring
            key = _keyring.get_password("screen-ai-assistant", "hf_api_key")
            if key:
                return key
        except Exception:
            pass
        return self._config.api_key

    # ------------------------------------------------------------------
    # Lazy loaders
    # ------------------------------------------------------------------

    def _get_ollama(self):
        if self._ollama is None:
            import ollama as _ollama
            self._ollama = _ollama
        return self._ollama

    def _get_openai_client(self):
        if self._openai_client is None:
            import keyring as _keyring
            import openai as _openai
            api_key = _keyring.get_password("screen-ai-assistant", "openai_api_key")
            if api_key is None:
                api_key = self._config.api_key
            self._openai_client = _openai.OpenAI(
                api_key=api_key,
                base_url=self._config.base_url,
                timeout=self._config.timeout_seconds,
            )
        return self._openai_client

    def _get_hf_client(self):
        if self._hf_client is None:
            from huggingface_hub import InferenceClient
            api_key = self._get_hf_api_key()
            self._hf_client = InferenceClient(token=api_key)
        return self._hf_client
