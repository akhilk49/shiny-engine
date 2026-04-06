"""Tests for OverlayUI — frameless always-on-top floating window."""

from __future__ import annotations

import threading
import time

import pytest

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
from unittest.mock import MagicMock

from src.models import UIConfig, StatusIndicator
from src.overlay_ui import OverlayUI


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    """Module-scoped QApplication (only one allowed per process)."""
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def config():
    return UIConfig(
        width=420,
        height=300,
        opacity=0.92,
        position_x=100,
        position_y=100,
        font_size=13,
        theme="dark",
        always_on_top=True,
    )


@pytest.fixture
def overlay(qapp, config):
    widget = OverlayUI(config)
    yield widget
    widget.close()


# ---------------------------------------------------------------------------
# Window flag tests
# ---------------------------------------------------------------------------

def test_window_stays_on_top_flag(overlay):
    """Window must have WindowStaysOnTopHint set."""
    assert overlay.windowFlags() & Qt.WindowStaysOnTopHint


def test_frameless_hint_flag(overlay):
    """Window must have FramelessWindowHint set."""
    assert overlay.windowFlags() & Qt.FramelessWindowHint


# ---------------------------------------------------------------------------
# set_text / append_text
# ---------------------------------------------------------------------------

def test_set_text_updates_content(qapp, overlay):
    """set_text should replace the content label text."""
    overlay.set_text("Hello world")
    qapp.processEvents()
    assert overlay._content_label.text() == "Hello world"


def test_set_text_replaces_existing(qapp, overlay):
    """set_text should replace, not append."""
    overlay.set_text("first")
    qapp.processEvents()
    overlay.set_text("second")
    qapp.processEvents()
    assert overlay._content_label.text() == "second"


def test_append_text_appends(qapp, overlay):
    """append_text should concatenate to existing content."""
    overlay.set_text("Hello")
    qapp.processEvents()
    overlay.append_text(" world")
    qapp.processEvents()
    assert overlay._content_label.text() == "Hello world"


def test_append_text_multiple_chunks(qapp, overlay):
    """Multiple append_text calls accumulate correctly."""
    overlay.set_text("")
    qapp.processEvents()
    for chunk in ["foo", " bar", " baz"]:
        overlay.append_text(chunk)
        qapp.processEvents()
    assert overlay._content_label.text() == "foo bar baz"


# ---------------------------------------------------------------------------
# set_status
# ---------------------------------------------------------------------------

def test_set_status_updates_label(overlay):
    """set_status should update the status label text."""
    overlay.set_status(StatusIndicator.PROCESSING)
    assert overlay._status_label.text() == StatusIndicator.PROCESSING.value


def test_set_status_all_values(overlay):
    """All StatusIndicator values should be accepted without error."""
    for status in StatusIndicator:
        overlay.set_status(status)
        assert overlay._status_label.text() == status.value


# ---------------------------------------------------------------------------
# Always-on-top flag persistence
# ---------------------------------------------------------------------------

def test_always_on_top_after_set_text(qapp, overlay):
    """WindowStaysOnTopHint must remain set after set_text."""
    overlay.set_text("some text")
    qapp.processEvents()
    assert overlay.windowFlags() & Qt.WindowStaysOnTopHint


def test_always_on_top_after_append_text(qapp, overlay):
    """WindowStaysOnTopHint must remain set after append_text."""
    overlay.append_text("chunk")
    qapp.processEvents()
    assert overlay.windowFlags() & Qt.WindowStaysOnTopHint


def test_always_on_top_after_set_status(overlay):
    """WindowStaysOnTopHint must remain set after set_status."""
    overlay.set_status(StatusIndicator.ERROR)
    assert overlay.windowFlags() & Qt.WindowStaysOnTopHint


def test_always_on_top_after_sequence(qapp, overlay):
    """WindowStaysOnTopHint must remain set after a sequence of UI operations."""
    overlay.set_status(StatusIndicator.CAPTURING)
    overlay.set_text("capturing…")
    qapp.processEvents()
    overlay.set_status(StatusIndicator.PROCESSING)
    overlay.append_text(" done")
    qapp.processEvents()
    overlay.set_status(StatusIndicator.IDLE)
    assert overlay.windowFlags() & Qt.WindowStaysOnTopHint


# ---------------------------------------------------------------------------
# Thread-safety: set_text and append_text from non-Qt thread
# ---------------------------------------------------------------------------

def test_set_text_from_background_thread(qapp, overlay):
    """set_text called from a non-Qt thread must not crash."""
    errors: list[Exception] = []

    def worker():
        try:
            overlay.set_text("from thread")
        except Exception as exc:
            errors.append(exc)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout=2)

    # Process any queued Qt events
    qapp.processEvents()

    assert not errors, f"Exception in background thread: {errors}"
    assert overlay._content_label.text() == "from thread"


def test_append_text_from_background_thread(qapp, overlay):
    """append_text called from a non-Qt thread must not crash."""
    overlay.set_text("base")
    qapp.processEvents()

    errors: list[Exception] = []

    def worker():
        try:
            overlay.append_text(" appended")
        except Exception as exc:
            errors.append(exc)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout=2)

    qapp.processEvents()

    assert not errors, f"Exception in background thread: {errors}"
    assert overlay._content_label.text() == "base appended"


# ---------------------------------------------------------------------------
# Theme and config
# ---------------------------------------------------------------------------

def test_light_theme_applied(qapp):
    """Light theme config should produce a different stylesheet."""
    light_config = UIConfig(theme="light")
    widget = OverlayUI(light_config)
    assert "f5f5f5" in widget.styleSheet()
    widget.close()


def test_dark_theme_applied(qapp, overlay):
    """Dark theme config should produce a dark stylesheet."""
    assert "1e1e2e" in overlay.styleSheet()


def test_opacity_set(qapp, config):
    """Window opacity should match UIConfig.opacity."""
    widget = OverlayUI(config)
    assert abs(widget.windowOpacity() - config.opacity) < 0.01
    widget.close()


def test_initial_position(qapp, config):
    """Window should be positioned at UIConfig.position_x/y."""
    widget = OverlayUI(config)
    pos = widget.pos()
    assert pos.x() == config.position_x
    assert pos.y() == config.position_y
    widget.close()


# ---------------------------------------------------------------------------
# API warning dialog
# ---------------------------------------------------------------------------

def test_warn_api_mode_once_shows_dialog_on_first_call(qapp, overlay):
    """warn_api_mode_once calls show_api_warning on the first invocation."""
    overlay.show_api_warning = MagicMock(return_value=True)
    result = overlay.warn_api_mode_once()
    overlay.show_api_warning.assert_called_once()
    assert result is True


def test_warn_api_mode_once_returns_true_on_second_call_without_dialog(qapp, overlay):
    """warn_api_mode_once skips the dialog on subsequent calls and returns True."""
    overlay.show_api_warning = MagicMock(return_value=True)
    overlay.warn_api_mode_once()  # first call — shows dialog
    overlay.show_api_warning.reset_mock()

    result = overlay.warn_api_mode_once()  # second call — no dialog
    overlay.show_api_warning.assert_not_called()
    assert result is True


def test_warn_api_mode_once_returns_false_when_user_cancels(qapp, overlay):
    """warn_api_mode_once returns False when show_api_warning returns False."""
    overlay.show_api_warning = MagicMock(return_value=False)
    result = overlay.warn_api_mode_once()
    assert result is False


def test_warn_api_mode_once_sets_flag_after_first_call(qapp, overlay):
    """_api_warning_shown is True after the first warn_api_mode_once call."""
    overlay.show_api_warning = MagicMock(return_value=True)
    assert overlay._api_warning_shown is False
    overlay.warn_api_mode_once()
    assert overlay._api_warning_shown is True


def test_api_warning_shown_flag_initialised_false(qapp, overlay):
    """_api_warning_shown starts as False on a fresh OverlayUI instance."""
    assert overlay._api_warning_shown is False
