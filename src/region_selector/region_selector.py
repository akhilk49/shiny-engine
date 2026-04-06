"""Region Selector module — transparent full-screen drag-select overlay."""

from __future__ import annotations

from PyQt5.QtCore import Qt, QRect, QPoint, QEventLoop
from PyQt5.QtWidgets import QWidget, QApplication
from PyQt5.QtGui import QPainter, QColor, QPen

from src.models import Region


class RegionSelector(QWidget):
    """Transparent full-screen overlay that lets the user drag-select a region.

    Usage::

        region = RegionSelector().select()  # blocks until drag completes
    """

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint,
        )

        # Semi-transparent background
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowOpacity(1.0)
        self.setCursor(Qt.CrossCursor)

        # Cover the full virtual desktop (all monitors)
        screen = QApplication.primaryScreen()
        if screen is not None:
            geometry = screen.virtualGeometry()
            self.setGeometry(geometry)
        else:
            # Fallback: cover primary screen
            self.resize(1920, 1080)

        self._start: QPoint | None = None
        self._end: QPoint | None = None
        self._selected_region: Region | None = None
        self._loop: QEventLoop = QEventLoop()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def select(self) -> Region:
        """Show the overlay and block until the user completes a drag.

        Returns the selected :class:`~src.models.Region` with positive
        width and height regardless of drag direction.
        """
        self.showFullScreen()
        self._loop.exec_()  # blocks here until _finish() calls quit()
        self.close()
        assert self._selected_region is not None, "No region was selected"
        return self._selected_region

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._start = event.pos()
            self._end = event.pos()
            self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.LeftButton and self._start is not None:
            self._end = event.pos()
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._start is not None:
            self._end = event.pos()
            self._finish()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        """Allow Escape to cancel selection (returns a zero-size region)."""
        if event.key() == Qt.Key_Escape:
            self._selected_region = Region(x=0, y=0, width=0, height=0)
            self._loop.quit()
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        # Dim the whole screen slightly
        painter.fillRect(self.rect(), QColor(0, 0, 0, 60))

        if self._start is not None and self._end is not None:
            rect = self._selection_rect()

            # Semi-transparent fill
            painter.fillRect(rect, QColor(100, 149, 237, 80))  # cornflower blue

            # Visible border
            pen = QPen(QColor(255, 255, 255, 220), 2, Qt.SolidLine)
            painter.setPen(pen)
            painter.drawRect(rect)

        painter.end()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _selection_rect(self) -> QRect:
        """Return a normalised QRect from start/end points."""
        assert self._start is not None and self._end is not None
        return QRect(self._start, self._end).normalized()

    def _finish(self) -> None:
        """Compute the Region and exit the event loop."""
        rect = self._selection_rect()
        # Map widget-local coordinates to global screen coordinates
        global_origin = self.mapToGlobal(rect.topLeft())
        # QRect width/height are inclusive (+1), so use coordinate subtraction
        # for the actual pixel span.
        width = rect.right() - rect.left()
        height = rect.bottom() - rect.top()
        self._selected_region = Region(
            x=global_origin.x(),
            y=global_origin.y(),
            width=max(1, width),
            height=max(1, height),
        )
        self._loop.quit()
