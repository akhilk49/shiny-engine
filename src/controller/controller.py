"""Controller — orchestrates the full capture-to-response pipeline."""

from __future__ import annotations

import logging
import threading
from typing import Optional

from PyQt5.QtWidgets import QApplication

from src.config_manager import ConfigManager
from src.hotkey_listener.hotkey_listener import HotkeyListener
from src.llm_engine.llm_engine import LLMEngine
from src.models import (
    AppConfig,
    CaptureError,
    LLMUnavailableError,
    OCRError,
    StatusIndicator,
)
from src.ocr_engine.ocr_engine import OCREngine
from src.overlay_ui.overlay_ui import OverlayUI
from src.region_selector.region_selector import RegionSelector
from src.screen_capture.screen_capture import ScreenCapture
from src.state_manager.state_manager import StateManager
from src.text_processor.text_processor import TextProcessor

logger = logging.getLogger(__name__)


class Controller:
    """Wires all components together and runs the capture-to-response pipeline.

    Accepts pre-built component instances for testability.  Use the
    :meth:`from_config` factory to build a fully-wired instance from a
    ``config.yaml`` file.
    """

    def __init__(
        self,
        config: AppConfig,
        capture: ScreenCapture,
        ocr: OCREngine,
        processor: TextProcessor,
        state: StateManager,
        llm: LLMEngine,
        overlay: OverlayUI,
        hotkeys: Optional[HotkeyListener] = None,
    ) -> None:
        self._config = config
        self._capture = capture
        self._ocr = ocr
        self._processor = processor
        self._state = state
        self._llm = llm
        self._overlay = overlay
        self._hotkeys = hotkeys

        if hotkeys is not None:
            self.setup_hotkeys(hotkeys)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config_path: str = "config.yaml") -> "Controller":
        """Build a fully-wired :class:`Controller` from *config_path*."""
        config = ConfigManager(config_path).load()
        capture = ScreenCapture(config.capture)
        ocr = OCREngine(config.ocr)
        processor = TextProcessor()
        state = StateManager()
        llm = LLMEngine(config.llm)
        overlay = OverlayUI(config.ui)
        hotkeys = HotkeyListener(config.hotkeys)
        return cls(config, capture, ocr, processor, state, llm, overlay, hotkeys)

    # ------------------------------------------------------------------
    # Hotkey wiring
    # ------------------------------------------------------------------

    def setup_hotkeys(self, hotkeys: HotkeyListener) -> None:
        """Register all hotkey bindings on *hotkeys*."""
        self._hotkeys = hotkeys
        hotkeys.register(self._config.hotkeys.capture_trigger, self.run_pipeline_async)
        hotkeys.register(self._config.hotkeys.region_select, self._on_region_select)
        hotkeys.register(self._config.hotkeys.toggle_overlay, self._on_toggle_overlay)
        hotkeys.register(self._config.hotkeys.quit, self._on_quit)

    def _on_region_select(self) -> None:
        """Open RegionSelector, apply the result, then auto-capture."""

        def _select():
            region = RegionSelector().select()
            if region.width == 0 or region.height == 0:
                self._overlay.set_text("Region selection cancelled")
                return
            self._capture.set_region(region)
            # Also clear state cache so the new region always triggers LLM
            self._state.clear()
            # Auto-capture immediately after region is set
            self.run_pipeline()

        thread = threading.Thread(target=_select, daemon=True)
        thread.start()

    def _on_toggle_overlay(self) -> None:
        """Show the overlay if hidden, hide it if shown."""
        if self._overlay.isVisible():
            self._overlay.hide()
        else:
            self._overlay.show()

    def _on_quit(self) -> None:
        """Quit the Qt application."""
        QApplication.quit()

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    def run_pipeline(self) -> None:
        """Execute the full capture-to-response pipeline.

        Designed to be called from a background thread so the Qt event loop
        remains responsive.  All overlay updates are routed through Qt
        signals internally by :class:`OverlayUI`.
        """
        try:
            # Step 1: Capture — use the capture module's active region (set via Ctrl+Shift+R)
            self._overlay.set_status(StatusIndicator.CAPTURING)
            image = self._capture.capture()

            # Step 2: OCR
            self._overlay.set_status(StatusIndicator.PROCESSING)
            raw_text = self._ocr.extract(image)

            # Temporarily show OCR output so we can diagnose quality
            self._overlay.set_text(f"[OCR]\n{raw_text[:400]}")

            # Step 3: Text processing
            processed = self._processor.process(raw_text)

            # Step 4: Short-circuit — empty text
            if processed.is_empty:
                self._overlay.set_text("No readable text found.")
                self._overlay.set_status(StatusIndicator.IDLE)
                return

            # Step 5: Short-circuit — no change
            if not self._state.has_changed(processed.content):
                self._overlay.set_text("No change detected.")
                self._overlay.set_status(StatusIndicator.IDLE)
                return

            # Step 6: LLM query (streaming)
            prompt = self._llm.build_prompt(processed)

            # Warn user before first OpenAI API call (Requirement 11.2)
            if self._config.llm.backend == "openai":
                if not self._overlay.warn_api_mode_once():
                    self._overlay.set_status(StatusIndicator.IDLE)
                    return

            self._overlay.set_text("")
            for token in self._llm.query_stream(prompt):
                self._overlay.append_text(token)

            # Step 7: Update state cache
            self._state.update(processed.content)
            self._overlay.set_status(StatusIndicator.IDLE)

        except CaptureError as exc:
            logger.error("Screen capture failed: %s", exc)
            self._overlay.set_text("Capture failed")
            self._overlay.set_status(StatusIndicator.ERROR)

        except LLMUnavailableError as exc:
            logger.error("LLM unavailable: %s", exc)
            self._overlay.set_text("LLM unavailable — check Ollama or API config")
            self._overlay.set_status(StatusIndicator.ERROR)

        except OCRError as exc:
            logger.error("OCR unavailable: %s", exc)
            self._overlay.set_text("OCR unavailable")
            self._overlay.set_status(StatusIndicator.ERROR)

        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error in pipeline: %s", exc)
            self._overlay.set_text(f"Error: {type(exc).__name__}: {exc}")
            self._overlay.set_status(StatusIndicator.ERROR)

    def run_pipeline_async(self) -> threading.Thread:
        """Run :meth:`run_pipeline` in a background daemon thread.

        Returns the started :class:`threading.Thread` so callers can join
        it if needed.
        """
        thread = threading.Thread(target=self.run_pipeline, daemon=True)
        thread.start()
        return thread
