"""StateManager: tracks last processed text to avoid redundant LLM calls."""

from __future__ import annotations

import hashlib
import threading


class StateManager:
    """Hash-based change detection with thread-safe cache access."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cached_hash: str | None = None
        self._cached_text: str | None = None

    def has_changed(self, text: str) -> bool:
        """Return True if *text* differs from the cached text, or cache is empty."""
        new_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        with self._lock:
            if self._cached_hash is None:
                return True
            return new_hash != self._cached_hash

    def update(self, text: str) -> None:
        """Store *text* and its hash in the cache."""
        new_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        with self._lock:
            self._cached_hash = new_hash
            self._cached_text = text

    def get_cached(self) -> str | None:
        """Return the last cached text, or None if cache is empty."""
        with self._lock:
            return self._cached_text

    def clear(self) -> None:
        """Reset the cache so the next has_changed call returns True."""
        with self._lock:
            self._cached_hash = None
            self._cached_text = None
