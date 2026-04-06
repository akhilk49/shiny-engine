"""Unit tests for StateManager."""

from __future__ import annotations

import threading

import pytest

from src.state_manager import StateManager


@pytest.fixture
def state() -> StateManager:
    return StateManager()


# ---------------------------------------------------------------------------
# has_changed
# ---------------------------------------------------------------------------

def test_has_changed_returns_true_when_cache_empty(state: StateManager) -> None:
    assert state.has_changed("any text") is True


def test_has_changed_returns_false_after_update_same_text(state: StateManager) -> None:
    state.update("hello world")
    assert state.has_changed("hello world") is False


def test_has_changed_returns_true_for_different_text(state: StateManager) -> None:
    state.update("original text")
    assert state.has_changed("different text") is True


def test_has_changed_does_not_mutate_cache(state: StateManager) -> None:
    state.update("cached")
    state.has_changed("other")
    assert state.get_cached() == "cached"


# ---------------------------------------------------------------------------
# update / get_cached
# ---------------------------------------------------------------------------

def test_update_stores_text_retrievable_via_get_cached(state: StateManager) -> None:
    state.update("stored text")
    assert state.get_cached() == "stored text"


def test_get_cached_returns_none_initially(state: StateManager) -> None:
    assert state.get_cached() is None


def test_update_overwrites_previous_cache(state: StateManager) -> None:
    state.update("first")
    state.update("second")
    assert state.get_cached() == "second"


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------

def test_clear_resets_cache_so_has_changed_returns_true(state: StateManager) -> None:
    state.update("some text")
    state.clear()
    assert state.has_changed("some text") is True


def test_clear_makes_get_cached_return_none(state: StateManager) -> None:
    state.update("data")
    state.clear()
    assert state.get_cached() is None


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

def test_concurrent_updates_do_not_corrupt_state(state: StateManager) -> None:
    """Multiple threads updating simultaneously should not corrupt the cache."""
    errors: list[Exception] = []

    def worker(text: str) -> None:
        try:
            for _ in range(50):
                state.update(text)
                cached = state.get_cached()
                # cached must be a string (not None) after update
                assert isinstance(cached, str)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(f"thread-{i}",)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Thread errors: {errors}"
    # Final cached value must be one of the valid thread strings
    final = state.get_cached()
    assert final is not None
    assert final.startswith("thread-")
