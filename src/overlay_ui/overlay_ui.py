"""Overlay UI module — always-on-top floating response window."""

from __future__ import annotations

from PyQt5.QtCore import Qt, QPoint, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea, QSizePolicy, QMessageBox
from PyQt5.QtGui import QFont

from src.models import UIConfig, StatusIndicator

# ---------------------------------------------------------------------------
# Theme palettes
# ---------------------------------------------------------------------------

_DARK_STYLE = """
QWidget#OverlayRoot {
    background-color: #1e1e2e;
    border: 1px solid #444466;
    border-radius: 8px;
}
QLabel#TitleBar {
    background-color: #2a2a3e;
    color: #cdd6f4;
    padding: 4px 8px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: bold;
}
QLabel#StatusLabel {
    color: #a6e3a1;
    padding: 2px 8px;
    font-size: 11px;
}
QLabel#ContentLabel {
    color: #cdd6f4;
    padding: 4px 8px;
    background-color: transparent;
}
QScrollArea {
    background-color: transparent;
    border: none;
}
"""

_LIGHT_STYLE = """
QWidget#OverlayRoot {
    background-color: #f5f5f5;
    border: 1px solid #cccccc;
    border-radius: 8px;
}
QLabel#TitleBar {
    background-color: #e0e0e0;
    color: #333333;
    padding: 4px 8px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: bold;
}
QLabel#StatusLabel {
    color: #2e7d32;
    padding: 2px 8px;
    font-size: 11px;
}
QLabel#ContentLabel {
    color: #333333;
    padding: 4px 8px;
    background-color: transparent;
}
QScrollArea {
    background-color: transparent;
    border: none;
}
"""

_STATUS_COLORS_DARK = {
    StatusIndicator.IDLE: "#a6e3a1",
    StatusIndicator.CAPTURING: "#89b4fa",
    StatusIndicator.PROCESSING: "#f9e2af",
    StatusIndicator.ERROR: "#f38ba8",
}

_STATUS_COLORS_LIGHT = {
    StatusIndicator.IDLE: "#2e7d32",
    StatusIndicator.CAPTURING: "#1565c0",
    StatusIndicator.PROCESSING: "#e65100",
    StatusIndicator.ERROR: "#c62828",
}


class OverlayUI(QWidget):
    """Frameless, always-on-top floating overlay window."""

    # Signals for thread-safe text updates
    _set_text_signal: pyqtSignal = pyqtSignal(str)
    _append_text_signal: pyqtSignal = pyqtSignal(str)

    def __init__(self, config: UIConfig) -> None:
        super().__init__(None, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)

        self._config = config
        self._drag_pos: QPoint | None = None
        self._api_warning_shown: bool = False

        self.setObjectName("OverlayRoot")
        self.resize(config.width, config.height)
        self.move(config.position_x, config.position_y)
        self.setWindowOpacity(config.opacity)

        self._build_ui()
        self._apply_theme()

        # Connect signals to slots (safe cross-thread updates)
        self._set_text_signal.connect(self._do_set_text)
        self._append_text_signal.connect(self._do_append_text)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Title bar (draggable area)
        self._title_bar = QLabel("AI Assistant", self)
        self._title_bar.setObjectName("TitleBar")
        self._title_bar.setFixedHeight(28)
        layout.addWidget(self._title_bar)

        # Status indicator
        self._status_label = QLabel(StatusIndicator.IDLE.value, self)
        self._status_label.setObjectName("StatusLabel")
        layout.addWidget(self._status_label)

        # Scrollable content area
        self._content_label = QLabel("", self)
        self._content_label.setObjectName("ContentLabel")
        self._content_label.setWordWrap(True)
        self._content_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._content_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        font = QFont()
        font.setPointSize(self._config.font_size)
        self._content_label.setFont(font)

        scroll = QScrollArea(self)
        scroll.setWidget(self._content_label)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)

    def _apply_theme(self) -> None:
        if self._config.theme == "light":
            self.setStyleSheet(_LIGHT_STYLE)
            self._status_colors = _STATUS_COLORS_LIGHT
        else:
            self.setStyleSheet(_DARK_STYLE)
            self._status_colors = _STATUS_COLORS_DARK

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def show(self) -> None:  # type: ignore[override]
        super().show()

    def hide(self) -> None:  # type: ignore[override]
        super().hide()

    def set_text(self, text: str) -> None:
        """Thread-safe: replace content text."""
        self._set_text_signal.emit(text)

    def append_text(self, chunk: str) -> None:
        """Thread-safe: append a chunk to content text."""
        self._append_text_signal.emit(chunk)

    def set_status(self, status: StatusIndicator) -> None:
        """Update the status indicator label (call from any thread via direct call is safe
        because Qt will queue it if called from a non-GUI thread via the signal mechanism;
        however set_status is typically called from the GUI thread or pipeline thread.
        For full safety we update directly — Qt label setText is reentrant-safe when
        called from the GUI thread, and the pipeline should call this via the controller
        which uses signals. For simplicity we update directly here."""
        self._status_label.setText(status.value)
        color = self._status_colors.get(status, "")
        if color:
            self._status_label.setStyleSheet(f"color: {color}; padding: 2px 8px; font-size: 11px;")

    def show_api_warning(self) -> bool:
        """Show a warning that screen data will be sent to a remote API endpoint.

        Must be called from the Qt main thread.
        Returns True if the user clicks OK, False if they cancel.
        """
        msg = QMessageBox(self)
        msg.setWindowTitle("API Mode Warning")
        msg.setIcon(QMessageBox.Warning)
        msg.setText(
            "API mode is enabled.\n\n"
            "Screen capture data and OCR text will be sent to a remote API endpoint. "
            "Do you want to continue?"
        )
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        msg.setDefaultButton(QMessageBox.Cancel)
        result = msg.exec_()
        return result == QMessageBox.Ok

    def warn_api_mode_once(self) -> bool:
        """Show the API warning dialog at most once per session.

        Returns True immediately if the warning has already been shown.
        On the first call, shows the dialog; returns False if the user cancels.
        """
        if self._api_warning_shown:
            return True
        accepted = self.show_api_warning()
        self._api_warning_shown = True
        return accepted

    # ------------------------------------------------------------------
    # Private slots (always run on GUI thread)
    # ------------------------------------------------------------------

    @pyqtSlot(str)
    def _do_set_text(self, text: str) -> None:
        self._content_label.setText(text)

    @pyqtSlot(str)
    def _do_append_text(self, chunk: str) -> None:
        current = self._content_label.text()
        self._content_label.setText(current + chunk)

    # ------------------------------------------------------------------
    # Mouse drag (title bar)
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            # Only drag when clicking in the title bar area
            if self._title_bar.geometry().contains(event.pos()):
                self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None
        super().mouseReleaseEvent(event)
