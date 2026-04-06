"""Unit tests for HotkeyListener."""

from __future__ import annotations

import sys
import threading
import time
import types
from typing import Callable
from unittest.mock import MagicMock, patch, call

import pytest

from src.models import HotkeyConfig


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_keyboard_mock():
    """Return a minimal mock of the `keyboard` module."""
    kb = MagicMock()
    # add_hotkey returns a unique handle object each time
    kb.add_hotkey.side_effect = lambda hotkey, fn, **kw: object()
    return kb


def _make_listener(config: HotkeyConfig | None = None):
    """Import HotkeyListener with a mocked keyboard module."""
    from src.hotkey_listener.hotkey_listener import HotkeyListener
    cfg = config or HotkeyConfig()
    return HotkeyListener(cfg)


# ---------------------------------------------------------------------------
# 1. register stores the hotkey-callback mapping
# ---------------------------------------------------------------------------

class TestRegister:
    def test_register_stores_mapping(self):
        listener = _make_listener()
        cb = MagicMock()
        listener.register("ctrl+a", cb)
        assert listener._hotkeys["ctrl+a"] is cb

    def test_register_multiple_hotkeys(self):
        listener = _make_listener()
        cb1, cb2 = MagicMock(), MagicMock()
        listener.register("ctrl+a", cb1)
        listener.register("ctrl+b", cb2)
        assert listener._hotkeys["ctrl+a"] is cb1
        assert listener._hotkeys["ctrl+b"] is cb2

    def test_register_overwrites_existing(self):
        listener = _make_listener()
        cb1, cb2 = MagicMock(), MagicMock()
        listener.register("ctrl+a", cb1)
        listener.register("ctrl+a", cb2)
        assert listener._hotkeys["ctrl+a"] is cb2


# ---------------------------------------------------------------------------
# 2. start registers hotkeys with the keyboard library
# ---------------------------------------------------------------------------

class TestStart:
    def test_start_calls_add_hotkey_for_config_hotkeys(self):
        kb = _make_keyboard_mock()
        with patch.dict(sys.modules, {"keyboard": kb}):
            listener = _make_listener()
            listener.start()

        registered = {c.args[0] for c in kb.add_hotkey.call_args_list}
        cfg = HotkeyConfig()
        assert cfg.capture_trigger in registered
        assert cfg.region_select in registered
        assert cfg.toggle_overlay in registered
        assert cfg.quit in registered

    def test_start_registers_pre_registered_hotkeys(self):
        kb = _make_keyboard_mock()
        cb = MagicMock()
        with patch.dict(sys.modules, {"keyboard": kb}):
            listener = _make_listener()
            listener.register("ctrl+z", cb)
            listener.start()

        registered = {c.args[0] for c in kb.add_hotkey.call_args_list}
        assert "ctrl+z" in registered

    def test_register_after_start_calls_add_hotkey_immediately(self):
        kb = _make_keyboard_mock()
        cb = MagicMock()
        with patch.dict(sys.modules, {"keyboard": kb}):
            listener = _make_listener()
            listener.start()
            kb.add_hotkey.reset_mock()
            listener.register("ctrl+x", cb)

        kb.add_hotkey.assert_called_once()
        assert kb.add_hotkey.call_args.args[0] == "ctrl+x"


# ---------------------------------------------------------------------------
# 3. stop unregisters hotkeys
# ---------------------------------------------------------------------------

class TestStop:
    def test_stop_calls_remove_hotkey_for_each_registered(self):
        handles = {}
        kb = MagicMock()

        def _add(hotkey, fn, **kw):
            h = object()
            handles[hotkey] = h
            return h

        kb.add_hotkey.side_effect = _add

        with patch.dict(sys.modules, {"keyboard": kb}):
            listener = _make_listener()
            listener.start()
            listener.stop()

        assert kb.remove_hotkey.call_count == len(handles)
        removed = {c.args[0] for c in kb.remove_hotkey.call_args_list}
        assert removed == set(handles.values())

    def test_stop_clears_started_flag(self):
        kb = _make_keyboard_mock()
        with patch.dict(sys.modules, {"keyboard": kb}):
            listener = _make_listener()
            listener.start()
            listener.stop()
        assert not listener._started

    def test_stop_before_start_is_safe(self):
        kb = _make_keyboard_mock()
        with patch.dict(sys.modules, {"keyboard": kb}):
            listener = _make_listener()
            listener.stop()  # should not raise
        kb.remove_hotkey.assert_not_called()


# ---------------------------------------------------------------------------
# 4. callback is invoked non-blocking when hotkey fires
# ---------------------------------------------------------------------------

class TestNonBlockingCallback:
    def test_callback_dispatched_to_thread_pool(self):
        """The dispatch wrapper submits the callback to the executor."""
        kb = MagicMock()
        dispatch_fn_holder = {}

        def _add(hotkey, fn, **kw):
            dispatch_fn_holder[hotkey] = fn
            return object()

        kb.add_hotkey.side_effect = _add

        cb = MagicMock()
        with patch.dict(sys.modules, {"keyboard": kb}):
            listener = _make_listener()
            listener.register("ctrl+a", cb)
            listener.start()

        # Simulate the keyboard library firing the hotkey
        dispatch_fn = dispatch_fn_holder.get("ctrl+a")
        assert dispatch_fn is not None, "dispatch fn not captured"

        # Call the dispatch function and wait briefly for the thread pool
        dispatch_fn()
        time.sleep(0.1)

        cb.assert_called_once()

    def test_slow_callback_does_not_block_caller(self):
        """A slow callback must not block the dispatch call."""
        kb = MagicMock()
        dispatch_fn_holder = {}

        def _add(hotkey, fn, **kw):
            dispatch_fn_holder[hotkey] = fn
            return object()

        kb.add_hotkey.side_effect = _add

        started = threading.Event()
        finished = threading.Event()

        def slow_cb():
            started.set()
            time.sleep(0.5)
            finished.set()

        with patch.dict(sys.modules, {"keyboard": kb}):
            listener = _make_listener()
            listener.register("ctrl+a", slow_cb)
            listener.start()

        dispatch_fn = dispatch_fn_holder["ctrl+a"]
        t0 = time.monotonic()
        dispatch_fn()
        elapsed = time.monotonic() - t0

        # dispatch should return almost immediately (well under 0.5 s)
        assert elapsed < 0.2, f"dispatch blocked for {elapsed:.3f}s"
        # callback eventually finishes
        assert finished.wait(timeout=2.0)


# ---------------------------------------------------------------------------
# 5. start is idempotent
# ---------------------------------------------------------------------------

class TestIdempotentStart:
    def test_start_twice_does_not_duplicate_registrations(self):
        kb = _make_keyboard_mock()
        with patch.dict(sys.modules, {"keyboard": kb}):
            listener = _make_listener()
            listener.start()
            first_count = kb.add_hotkey.call_count
            listener.start()  # second call — should be a no-op
            second_count = kb.add_hotkey.call_count

        assert first_count == second_count, (
            f"add_hotkey called {second_count - first_count} extra times on second start()"
        )

    def test_started_flag_set_after_first_start(self):
        kb = _make_keyboard_mock()
        with patch.dict(sys.modules, {"keyboard": kb}):
            listener = _make_listener()
            listener.start()
        assert listener._started

    def test_started_flag_remains_true_after_second_start(self):
        kb = _make_keyboard_mock()
        with patch.dict(sys.modules, {"keyboard": kb}):
            listener = _make_listener()
            listener.start()
            listener.start()
        assert listener._started
