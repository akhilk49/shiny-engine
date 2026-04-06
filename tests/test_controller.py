"""Unit tests for Controller — pipeline orchestration."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest
from PIL import Image

from src.controller.controller import Controller
from src.models import (
    AppConfig,
    CaptureError,
    LLMUnavailableError,
    OCRError,
    ProcessedText,
    StatusIndicator,
    TextClass,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_processed(content: str = "Hello world", is_empty: bool = False) -> ProcessedText:
    return ProcessedText(
        content=content,
        classification=TextClass.PARAGRAPH,
        word_count=len(content.split()) if content else 0,
        is_empty=is_empty,
    )


def _make_controller(
    *,
    capture_return=None,
    ocr_return: str = "Hello world",
    processed: ProcessedText | None = None,
    has_changed: bool = True,
    llm_tokens: list[str] | None = None,
    capture_side_effect=None,
    llm_side_effect=None,
    ocr_side_effect=None,
):
    """Build a Controller with fully mocked components."""
    config = AppConfig()

    capture = MagicMock()
    if capture_side_effect:
        capture.capture.side_effect = capture_side_effect
    else:
        capture.capture.return_value = capture_return or Image.new("RGB", (100, 100))

    ocr = MagicMock()
    if ocr_side_effect:
        ocr.extract.side_effect = ocr_side_effect
    else:
        ocr.extract.return_value = ocr_return

    processor = MagicMock()
    processor.process.return_value = processed or _make_processed(ocr_return)

    state = MagicMock()
    state.has_changed.return_value = has_changed

    llm = MagicMock()
    if llm_side_effect:
        llm.query_stream.side_effect = llm_side_effect
    else:
        llm.query_stream.return_value = iter(llm_tokens or ["response text"])
    llm.build_prompt.return_value = "built prompt"

    overlay = MagicMock()

    return Controller(config, capture, ocr, processor, state, llm, overlay)


# ---------------------------------------------------------------------------
# Full pipeline success
# ---------------------------------------------------------------------------

class TestFullPipelineSuccess:
    def test_capture_ocr_process_llm_overlay_updated(self):
        """Full pipeline: capture → OCR → process → LLM → overlay updated."""
        tokens = ["Hello", " ", "world"]
        ctrl = _make_controller(llm_tokens=tokens)

        ctrl.run_pipeline()

        ctrl._capture.capture.assert_called_once()
        ctrl._ocr.extract.assert_called_once()
        ctrl._processor.process.assert_called_once()
        ctrl._llm.build_prompt.assert_called_once()
        ctrl._llm.query_stream.assert_called_once_with("built prompt")

        # overlay should have received each token
        append_calls = ctrl._overlay.append_text.call_args_list
        assert append_calls == [call("Hello"), call(" "), call("world")]

    def test_overlay_set_text_cleared_before_streaming(self):
        """Overlay text is cleared before streaming begins."""
        ctrl = _make_controller(llm_tokens=["token"])
        ctrl.run_pipeline()
        # set_text("") should be called before append_text
        ctrl._overlay.set_text.assert_called_with("")

    def test_state_cache_updated_after_successful_run(self):
        """StateManager.update is called with processed content after success."""
        processed = _make_processed("some text")
        ctrl = _make_controller(processed=processed)
        ctrl.run_pipeline()
        ctrl._state.update.assert_called_once_with("some text")


# ---------------------------------------------------------------------------
# Short-circuit: empty OCR output
# ---------------------------------------------------------------------------

class TestEmptyOCRShortCircuit:
    def test_llm_not_called_when_empty(self):
        """LLM is never called when processed text is empty."""
        ctrl = _make_controller(processed=_make_processed("", is_empty=True))
        ctrl.run_pipeline()
        ctrl._llm.query_stream.assert_not_called()
        ctrl._llm.query.assert_not_called()

    def test_overlay_shows_no_readable_text(self):
        """Overlay displays 'No readable text found.' on empty OCR."""
        ctrl = _make_controller(processed=_make_processed("", is_empty=True))
        ctrl.run_pipeline()
        ctrl._overlay.set_text.assert_called_with("No readable text found.")

    def test_overlay_status_idle_after_empty(self):
        """Overlay status is IDLE after empty-text short-circuit."""
        ctrl = _make_controller(processed=_make_processed("", is_empty=True))
        ctrl.run_pipeline()
        ctrl._overlay.set_status.assert_called_with(StatusIndicator.IDLE)


# ---------------------------------------------------------------------------
# Short-circuit: unchanged text
# ---------------------------------------------------------------------------

class TestUnchangedTextShortCircuit:
    def test_llm_not_called_when_unchanged(self):
        """LLM is never called when state has not changed."""
        ctrl = _make_controller(has_changed=False)
        ctrl.run_pipeline()
        ctrl._llm.query_stream.assert_not_called()
        ctrl._llm.query.assert_not_called()

    def test_overlay_shows_no_change_detected(self):
        """Overlay displays 'No change detected.' when text unchanged."""
        ctrl = _make_controller(has_changed=False)
        ctrl.run_pipeline()
        ctrl._overlay.set_text.assert_called_with("No change detected.")

    def test_state_not_updated_when_unchanged(self):
        """StateManager.update is NOT called when text is unchanged."""
        ctrl = _make_controller(has_changed=False)
        ctrl.run_pipeline()
        ctrl._state.update.assert_not_called()


# ---------------------------------------------------------------------------
# Error handling: CaptureError
# ---------------------------------------------------------------------------

class TestCaptureError:
    def test_capture_error_sets_overlay_error_status(self):
        """CaptureError sets overlay status to ERROR."""
        ctrl = _make_controller(capture_side_effect=CaptureError("backend failed"))
        ctrl.run_pipeline()
        ctrl._overlay.set_status.assert_called_with(StatusIndicator.ERROR)

    def test_capture_error_sets_correct_message(self):
        """CaptureError sets overlay text to 'Capture failed'."""
        ctrl = _make_controller(capture_side_effect=CaptureError("backend failed"))
        ctrl.run_pipeline()
        ctrl._overlay.set_text.assert_called_with("Capture failed")

    def test_capture_error_does_not_call_llm(self):
        """LLM is not called when capture fails."""
        ctrl = _make_controller(capture_side_effect=CaptureError("backend failed"))
        ctrl.run_pipeline()
        ctrl._llm.query_stream.assert_not_called()


# ---------------------------------------------------------------------------
# Error handling: LLMUnavailableError
# ---------------------------------------------------------------------------

class TestLLMUnavailableError:
    def test_llm_unavailable_sets_error_status(self):
        """LLMUnavailableError sets overlay status to ERROR."""
        ctrl = _make_controller(llm_side_effect=LLMUnavailableError("no llm"))
        ctrl.run_pipeline()
        ctrl._overlay.set_status.assert_called_with(StatusIndicator.ERROR)

    def test_llm_unavailable_sets_correct_message(self):
        """LLMUnavailableError sets the correct overlay message."""
        ctrl = _make_controller(llm_side_effect=LLMUnavailableError("no llm"))
        ctrl.run_pipeline()
        ctrl._overlay.set_text.assert_called_with(
            "LLM unavailable — check Ollama or API config"
        )

    def test_llm_unavailable_state_not_updated(self):
        """StateManager.update is NOT called when LLM fails."""
        ctrl = _make_controller(llm_side_effect=LLMUnavailableError("no llm"))
        ctrl.run_pipeline()
        ctrl._state.update.assert_not_called()


# ---------------------------------------------------------------------------
# Error handling: OCRError
# ---------------------------------------------------------------------------

class TestOCRError:
    def test_ocr_error_sets_error_status(self):
        """OCRError sets overlay status to ERROR."""
        ctrl = _make_controller(ocr_side_effect=OCRError("no ocr backend"))
        ctrl.run_pipeline()
        ctrl._overlay.set_status.assert_called_with(StatusIndicator.ERROR)

    def test_ocr_error_sets_correct_message(self):
        """OCRError sets overlay text to 'OCR unavailable'."""
        ctrl = _make_controller(ocr_side_effect=OCRError("no ocr backend"))
        ctrl.run_pipeline()
        ctrl._overlay.set_text.assert_called_with("OCR unavailable")


# ---------------------------------------------------------------------------
# Overlay status transitions
# ---------------------------------------------------------------------------

class TestOverlayStatusTransitions:
    def test_capturing_then_processing_then_idle(self):
        """Overlay transitions: CAPTURING → PROCESSING → IDLE on success."""
        ctrl = _make_controller()
        ctrl.run_pipeline()

        status_calls = [c.args[0] for c in ctrl._overlay.set_status.call_args_list]
        assert StatusIndicator.CAPTURING in status_calls
        assert StatusIndicator.PROCESSING in status_calls
        assert StatusIndicator.IDLE in status_calls

        # Order matters
        capturing_idx = status_calls.index(StatusIndicator.CAPTURING)
        processing_idx = status_calls.index(StatusIndicator.PROCESSING)
        idle_idx = status_calls.index(StatusIndicator.IDLE)
        assert capturing_idx < processing_idx < idle_idx

    def test_capturing_set_before_capture_call(self):
        """CAPTURING status is set before capture.capture() is called."""
        call_order: list[str] = []

        ctrl = _make_controller()
        ctrl._overlay.set_status.side_effect = lambda s: call_order.append(f"status:{s.value}")
        ctrl._capture.capture.side_effect = lambda **kw: call_order.append("capture") or Image.new("RGB", (10, 10))

        ctrl.run_pipeline()

        assert call_order.index("status:capturing") < call_order.index("capture")

    def test_error_status_on_unexpected_exception(self):
        """Any unexpected exception sets overlay status to ERROR."""
        ctrl = _make_controller(capture_side_effect=RuntimeError("unexpected"))
        ctrl.run_pipeline()
        ctrl._overlay.set_status.assert_called_with(StatusIndicator.ERROR)


# ---------------------------------------------------------------------------
# from_config factory (smoke test — no real config.yaml needed via mock)
# ---------------------------------------------------------------------------

class TestFromConfigFactory:
    def test_from_config_creates_controller(self, tmp_path):
        """from_config returns a Controller instance."""
        import yaml

        cfg = {
            "hotkeys": {},
            "capture": {},
            "ocr": {},
            "llm": {},
            "ui": {},
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(cfg))

        # OverlayUI requires a QApplication — patch it out
        with patch("src.controller.controller.OverlayUI") as mock_ui:
            mock_ui.return_value = MagicMock()
            ctrl = Controller.from_config(str(config_file))

        assert isinstance(ctrl, Controller)


# ---------------------------------------------------------------------------
# Hotkey wiring
# ---------------------------------------------------------------------------

class TestHotkeyWiring:
    def _make_ctrl_with_hotkeys(self):
        """Build a Controller with a mock HotkeyListener."""
        from src.models import HotkeyConfig
        ctrl = _make_controller()
        hotkeys = MagicMock()
        ctrl._config.hotkeys = HotkeyConfig()
        return ctrl, hotkeys

    def test_setup_hotkeys_registers_capture_trigger(self):
        ctrl, hotkeys = self._make_ctrl_with_hotkeys()
        ctrl.setup_hotkeys(hotkeys)
        registered = {call.args[0]: call.args[1] for call in hotkeys.register.call_args_list}
        assert ctrl._config.hotkeys.capture_trigger in registered
        assert registered[ctrl._config.hotkeys.capture_trigger] == ctrl.run_pipeline_async

    def test_setup_hotkeys_registers_region_select(self):
        ctrl, hotkeys = self._make_ctrl_with_hotkeys()
        ctrl.setup_hotkeys(hotkeys)
        registered = {call.args[0]: call.args[1] for call in hotkeys.register.call_args_list}
        assert ctrl._config.hotkeys.region_select in registered
        assert registered[ctrl._config.hotkeys.region_select] == ctrl._on_region_select

    def test_setup_hotkeys_registers_toggle_overlay(self):
        ctrl, hotkeys = self._make_ctrl_with_hotkeys()
        ctrl.setup_hotkeys(hotkeys)
        registered = {call.args[0]: call.args[1] for call in hotkeys.register.call_args_list}
        assert ctrl._config.hotkeys.toggle_overlay in registered
        assert registered[ctrl._config.hotkeys.toggle_overlay] == ctrl._on_toggle_overlay

    def test_setup_hotkeys_registers_quit(self):
        ctrl, hotkeys = self._make_ctrl_with_hotkeys()
        ctrl.setup_hotkeys(hotkeys)
        registered = {call.args[0]: call.args[1] for call in hotkeys.register.call_args_list}
        assert ctrl._config.hotkeys.quit in registered
        assert registered[ctrl._config.hotkeys.quit] == ctrl._on_quit

    def test_hotkeys_param_in_init_calls_setup(self):
        """Passing hotkeys to __init__ automatically calls setup_hotkeys."""
        from src.models import HotkeyConfig
        config = AppConfig()
        hotkeys = MagicMock()
        ctrl = Controller(
            config,
            MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(),
            hotkeys=hotkeys,
        )
        assert hotkeys.register.call_count == 4

    def test_no_hotkeys_param_does_not_raise(self):
        """Controller without hotkeys param works fine."""
        ctrl = _make_controller()
        assert ctrl._hotkeys is None


class TestOnToggleOverlay:
    def test_hides_when_visible(self):
        ctrl = _make_controller()
        ctrl._overlay.isVisible.return_value = True
        ctrl._on_toggle_overlay()
        ctrl._overlay.hide.assert_called_once()
        ctrl._overlay.show.assert_not_called()

    def test_shows_when_hidden(self):
        ctrl = _make_controller()
        ctrl._overlay.isVisible.return_value = False
        ctrl._on_toggle_overlay()
        ctrl._overlay.show.assert_called_once()
        ctrl._overlay.hide.assert_not_called()


class TestOnQuit:
    def test_calls_qapplication_quit(self):
        ctrl = _make_controller()
        with patch("src.controller.controller.QApplication") as mock_app:
            ctrl._on_quit()
            mock_app.quit.assert_called_once()


class TestOnRegionSelect:
    def test_sets_region_and_confirms_on_valid_selection(self):
        """Valid region is applied to capture and confirmed in overlay."""
        from src.models import Region
        ctrl = _make_controller()
        region = Region(x=10, y=20, width=300, height=200)

        with patch("src.controller.controller.RegionSelector") as MockSelector:
            MockSelector.return_value.select.return_value = region
            ctrl._on_region_select()
            # Wait for the background thread to finish
            import time; time.sleep(0.1)

        ctrl._capture.set_region.assert_called_once_with(region)
        ctrl._overlay.set_text.assert_called_with("Region set: 300x200")

    def test_shows_cancelled_message_on_zero_region(self):
        """Zero-size region (Escape) shows cancellation message."""
        from src.models import Region
        ctrl = _make_controller()
        region = Region(x=0, y=0, width=0, height=0)

        with patch("src.controller.controller.RegionSelector") as MockSelector:
            MockSelector.return_value.select.return_value = region
            ctrl._on_region_select()
            import time; time.sleep(0.1)

        ctrl._capture.set_region.assert_not_called()
        ctrl._overlay.set_text.assert_called_with("Region selection cancelled")


class TestFromConfigWithHotkeys:
    def test_from_config_creates_hotkey_listener(self, tmp_path):
        """from_config creates a HotkeyListener and wires it up."""
        import yaml

        cfg = {"hotkeys": {}, "capture": {}, "ocr": {}, "llm": {}, "ui": {}}
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(cfg))

        with patch("src.controller.controller.OverlayUI") as mock_ui, \
             patch("src.controller.controller.HotkeyListener") as mock_hl:
            mock_ui.return_value = MagicMock()
            mock_hl_instance = MagicMock()
            mock_hl.return_value = mock_hl_instance

            ctrl = Controller.from_config(str(config_file))

        assert ctrl._hotkeys is mock_hl_instance
        assert mock_hl_instance.register.call_count == 4


# ---------------------------------------------------------------------------
# API mode warning (Requirement 11.2)
# ---------------------------------------------------------------------------

class TestApiModeWarning:
    def _make_openai_controller(self, warn_result: bool):
        """Build a Controller configured for the openai backend."""
        from src.models import LLMConfig
        ctrl = _make_controller()
        ctrl._config.llm = LLMConfig(backend="openai")
        ctrl._overlay.warn_api_mode_once.return_value = warn_result
        return ctrl

    def test_pipeline_aborts_when_user_declines_api_warning(self):
        """Pipeline does not call LLM when warn_api_mode_once returns False."""
        ctrl = self._make_openai_controller(warn_result=False)
        ctrl.run_pipeline()
        ctrl._llm.query_stream.assert_not_called()

    def test_pipeline_sets_idle_status_when_user_declines_api_warning(self):
        """Overlay status is IDLE when user declines the API warning."""
        ctrl = self._make_openai_controller(warn_result=False)
        ctrl.run_pipeline()
        ctrl._overlay.set_status.assert_called_with(StatusIndicator.IDLE)

    def test_pipeline_proceeds_when_user_accepts_api_warning(self):
        """Pipeline calls LLM when warn_api_mode_once returns True."""
        ctrl = self._make_openai_controller(warn_result=True)
        ctrl.run_pipeline()
        ctrl._llm.query_stream.assert_called_once()

    def test_warn_api_mode_once_not_called_for_ollama_backend(self):
        """warn_api_mode_once is NOT called when backend is ollama."""
        ctrl = _make_controller()
        ctrl._config.llm.backend = "ollama"
        ctrl.run_pipeline()
        ctrl._overlay.warn_api_mode_once.assert_not_called()
