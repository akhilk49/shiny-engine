"""HotkeyListener: registers global hotkeys and dispatches callbacks non-blocking."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict

from src.models import HotkeyConfig


class HotkeyListener:
    """Listens for global keyboard shortcuts and dispatches callbacks.

    Uses the `keyboard` library to register hotkeys and runs in a dedicated
    daemon thread. Callbacks are dispatched to a ThreadPoolExecutor so they
    never block the listener loop.
    """

    def __init__(self, config: HotkeyConfig) -> None:
        self._config = config
        # hotkey string -> callback
        self._hotkeys: Dict[str, Callable[[], None]] = {}
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="hotkey-cb")
        self._started = False
        self._lock = threading.Lock()
        # keyboard hook handles returned by keyboard.add_hotkey
        self._handles: Dict[str, object] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, hotkey: str, callback: Callable[[], None]) -> None:
        """Store a hotkey → callback mapping.

        If the listener is already running, the hotkey is registered with the
        keyboard library immediately.
        """
        with self._lock:
            self._hotkeys[hotkey] = callback
            if self._started:
                self._register_with_keyboard(hotkey, callback)

    def start(self) -> None:
        """Start the listener.  Idempotent — calling twice has no effect."""
        with self._lock:
            if self._started:
                return

            import keyboard  # imported lazily so tests can mock it

            # Register hotkeys from config first
            config_hotkeys = {
                self._config.capture_trigger: None,
                self._config.region_select: None,
                self._config.toggle_overlay: None,
                self._config.quit: None,
            }
            for hk in config_hotkeys:
                if hk not in self._hotkeys:
                    # Register a no-op placeholder so the key is tracked
                    self._hotkeys[hk] = lambda: None

            # Register all accumulated hotkeys
            for hk, cb in self._hotkeys.items():
                self._register_with_keyboard(hk, cb)

            self._started = True

    def stop(self) -> None:
        """Unregister all hotkeys and stop the listener."""
        with self._lock:
            if not self._started:
                return

            import keyboard  # imported lazily

            for hk in list(self._handles.keys()):
                try:
                    keyboard.remove_hotkey(self._handles[hk])
                except Exception:
                    pass
            self._handles.clear()
            self._started = False

        self._executor.shutdown(wait=False)
        # Re-create executor so the listener can be restarted if needed
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="hotkey-cb")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _register_with_keyboard(self, hotkey: str, callback: Callable[[], None]) -> None:
        """Register a single hotkey with the keyboard library."""
        import keyboard  # imported lazily

        def _dispatch():
            self._executor.submit(callback)

        handle = keyboard.add_hotkey(hotkey, _dispatch, suppress=False)
        self._handles[hotkey] = handle
