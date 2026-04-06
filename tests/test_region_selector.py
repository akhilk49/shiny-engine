"""Tests for RegionSelector — transparent full-screen drag-select overlay."""

from __future__ import annotations

import pytest

from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtWidgets import QApplication
from PyQt5.QtTest import QTest

from src.models import Region
from src.region_selector import RegionSelector


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    """Module-scoped QApplication (only one allowed per process)."""
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def selector(qapp):
    """Create a RegionSelector without showing it."""
    widget = RegionSelector()
    yield widget
    # Ensure cleanup even if test fails mid-way
    if not widget._loop.isRunning():
        widget.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simulate_drag(selector: RegionSelector, x1: int, y1: int, x2: int, y2: int) -> None:
    """Simulate a mouse press → move → release drag on the selector widget."""
    press = QPoint(x1, y1)
    release = QPoint(x2, y2)

    # Simulate press
    QTest.mousePress(selector, Qt.LeftButton, Qt.NoModifier, press)
    # Simulate move
    selector.mouseMoveEvent(_make_mouse_event(Qt.LeftButton, QPoint((x1 + x2) // 2, (y1 + y2) // 2)))
    # Simulate release — this calls _finish() and quits the loop
    QTest.mouseRelease(selector, Qt.LeftButton, Qt.NoModifier, release)


def _make_mouse_event(button, pos: QPoint):
    """Create a minimal mouse event object for mouseMoveEvent."""
    from PyQt5.QtGui import QMouseEvent
    from PyQt5.QtCore import QEvent
    return QMouseEvent(QEvent.MouseMove, pos, Qt.NoButton, button, Qt.NoModifier)


# ---------------------------------------------------------------------------
# Core behaviour: correct Region from simulated drag
# ---------------------------------------------------------------------------

def test_select_returns_region_with_correct_dimensions(qapp, selector):
    """select() should return a Region matching the drag rectangle."""
    # We drive the event loop manually instead of calling select() (which blocks)
    selector.show()
    qapp.processEvents()

    _simulate_drag(selector, x1=10, y1=20, x2=110, y2=70)
    qapp.processEvents()

    region = selector._selected_region
    assert region is not None
    assert region.width == 100
    assert region.height == 50


def test_select_returns_region_type(qapp, selector):
    """The returned object must be a Region instance."""
    selector.show()
    qapp.processEvents()

    _simulate_drag(selector, x1=0, y1=0, x2=50, y2=50)
    qapp.processEvents()

    assert isinstance(selector._selected_region, Region)


def test_select_region_has_correct_x_y(qapp, selector):
    """Region x, y should correspond to the top-left of the drag rectangle."""
    selector.show()
    qapp.processEvents()

    _simulate_drag(selector, x1=30, y1=40, x2=130, y2=140)
    qapp.processEvents()

    region = selector._selected_region
    assert region is not None
    # The widget is positioned at (0,0) in tests so local == global
    assert region.x == 30
    assert region.y == 40


# ---------------------------------------------------------------------------
# Reversed drag: width and height must always be positive
# ---------------------------------------------------------------------------

def test_reversed_drag_right_to_left(qapp, selector):
    """Dragging right-to-left should still produce positive width."""
    selector.show()
    qapp.processEvents()

    _simulate_drag(selector, x1=200, y1=50, x2=100, y2=150)
    qapp.processEvents()

    region = selector._selected_region
    assert region is not None
    assert region.width > 0
    assert region.height > 0


def test_reversed_drag_bottom_to_top(qapp, selector):
    """Dragging bottom-to-top should still produce positive height."""
    selector.show()
    qapp.processEvents()

    _simulate_drag(selector, x1=50, y1=200, x2=150, y2=100)
    qapp.processEvents()

    region = selector._selected_region
    assert region is not None
    assert region.width > 0
    assert region.height > 0


def test_reversed_drag_diagonal(qapp, selector):
    """Dragging in any diagonal direction should produce positive dimensions."""
    selector.show()
    qapp.processEvents()

    _simulate_drag(selector, x1=300, y1=300, x2=100, y2=100)
    qapp.processEvents()

    region = selector._selected_region
    assert region is not None
    assert region.width > 0
    assert region.height > 0
    assert region.width == 200
    assert region.height == 200


# ---------------------------------------------------------------------------
# Overlay closes after selection
# ---------------------------------------------------------------------------

def test_overlay_loop_exits_after_drag(qapp, selector):
    """The internal event loop should have exited after a drag completes."""
    selector.show()
    qapp.processEvents()

    _simulate_drag(selector, x1=10, y1=10, x2=60, y2=60)
    qapp.processEvents()

    # After _finish() is called, the loop should not be running
    assert not selector._loop.isRunning()


def test_overlay_region_set_after_drag(qapp, selector):
    """_selected_region must be set (not None) after a completed drag."""
    selector.show()
    qapp.processEvents()

    _simulate_drag(selector, x1=5, y1=5, x2=55, y2=55)
    qapp.processEvents()

    assert selector._selected_region is not None


# ---------------------------------------------------------------------------
# Escape key cancels selection
# ---------------------------------------------------------------------------

def test_escape_key_cancels_selection(qapp, selector):
    """Pressing Escape should set a zero-size region and exit the loop."""
    selector.show()
    qapp.processEvents()

    QTest.keyPress(selector, Qt.Key_Escape)
    qapp.processEvents()

    region = selector._selected_region
    assert region is not None
    assert region.width == 0
    assert region.height == 0
    assert not selector._loop.isRunning()
