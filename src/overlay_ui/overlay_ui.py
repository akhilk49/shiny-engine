"""Overlay UI — minimal professional dark card."""

from __future__ import annotations

import ctypes
import re

from PyQt5.QtCore import Qt, QPoint, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QSizePolicy, QMessageBox, QFrame
)
from PyQt5.QtGui import QFont

from src.models import UIConfig, StatusIndicator

# Windows constant — excludes window from screen capture
WDA_EXCLUDEFROMCAPTURE = 0x00000011


def _set_capture_excluded(hwnd: int) -> bool:
    """Make window invisible to screen capture on Windows 10 2004+."""
    try:
        return bool(ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE))
    except Exception:
        return False


class OverlayUI(QWidget):
    _set_text_signal: pyqtSignal = pyqtSignal(str)
    _append_text_signal: pyqtSignal = pyqtSignal(str)
    _set_status_signal: pyqtSignal = pyqtSignal(object)

    def __init__(self, config: UIConfig) -> None:
        super().__init__(None, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self._config = config
        self._drag_pos: QPoint | None = None
        self._api_warning_shown: bool = False
        self._full_text: str = ""

        self.setObjectName("OverlayRoot")
        self.resize(config.width, config.height)
        self.move(config.position_x, config.position_y)
        self.setWindowOpacity(config.opacity)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._build_ui()

        self._set_text_signal.connect(self._do_set_text)
        self._append_text_signal.connect(self._do_append_text)
        self._set_status_signal.connect(self._do_set_status)

        # Exclude from screen capture immediately
        _set_capture_excluded(int(self.winId()))

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Card container
        self._card = QWidget(self)
        self._card.setObjectName("Card")
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)
        root.addWidget(self._card)

        # Header bar
        header = QWidget()
        header.setObjectName("Header")
        header.setFixedHeight(36)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(14, 0, 14, 0)

        self._title_label = QLabel("AI Assistant")
        self._title_label.setObjectName("Title")

        self._status_label = QLabel("idle")
        self._status_label.setObjectName("Status")
        self._status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        h_layout.addWidget(self._title_label)
        h_layout.addWidget(self._status_label)
        card_layout.addWidget(header)

        # Divider
        div = QFrame()
        div.setObjectName("Divider")
        div.setFrameShape(QFrame.HLine)
        div.setFixedHeight(1)
        card_layout.addWidget(div)

        # Answer section
        ans_widget = QWidget()
        ans_widget.setObjectName("AnswerSection")
        ans_layout = QVBoxLayout(ans_widget)
        ans_layout.setContentsMargins(14, 10, 14, 10)
        ans_layout.setSpacing(4)

        self._answer_label = QLabel("")
        self._answer_label.setObjectName("Answer")
        self._answer_label.setWordWrap(True)
        self._answer_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        ans_layout.addWidget(self._answer_label)
        card_layout.addWidget(ans_widget)

        # Divider 2
        div2 = QFrame()
        div2.setObjectName("Divider")
        div2.setFrameShape(QFrame.HLine)
        div2.setFixedHeight(1)
        card_layout.addWidget(div2)
        self._div2 = div2

        # Reasoning section
        self._reason_section = QWidget()
        reason_layout = QVBoxLayout(self._reason_section)
        reason_layout.setContentsMargins(14, 8, 14, 10)
        reason_layout.setSpacing(0)

        self._reason_label = QLabel("")
        self._reason_label.setObjectName("Reason")
        self._reason_label.setWordWrap(True)
        self._reason_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._reason_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        reason_layout.addWidget(self._reason_label)

        scroll = QScrollArea()
        scroll.setWidget(self._reason_section)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setObjectName("Scroll")
        card_layout.addWidget(scroll)

        self._content_label = self._reason_label  # compat alias
        self._apply_styles()

    def _apply_styles(self) -> None:
        self._card.setStyleSheet("""
            QWidget#Card {
                background-color: #111113;
                border: 1px solid #2a2a2e;
                border-radius: 10px;
            }
            QWidget#Header {
                background-color: #111113;
                border-radius: 10px 10px 0 0;
            }
            QLabel#Title {
                color: #ffffff;
                font-size: 12px;
                font-weight: 600;
                background: transparent;
            }
            QLabel#Status {
                color: #555560;
                font-size: 10px;
                background: transparent;
            }
            QFrame#Divider {
                background-color: #1e1e22;
                border: none;
            }
            QWidget#AnswerSection {
                background-color: #111113;
            }
            QLabel#Answer {
                color: #f0f0f0;
                font-size: 14px;
                font-weight: 600;
                background: transparent;
                line-height: 1.4;
            }
            QWidget {
                background-color: #111113;
            }
            QLabel#Reason {
                color: #888896;
                font-size: 11px;
                background: transparent;
                line-height: 1.5;
            }
            QScrollArea#Scroll {
                background-color: #111113;
                border: none;
            }
            QScrollBar:vertical {
                background: #111113;
                width: 4px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical {
                background: #2a2a2e;
                border-radius: 2px;
            }
        """)

    def _parse_and_display(self, text: str) -> None:
        text = text.strip()
        # Strip DeepSeek <think> blocks
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

        answer = ""
        reasoning = ""

        match = re.search(
            r'(?:^|\n)\s*(?:\*\*)?[Aa]nswer(?:\*\*)?[:\s]+(.+?)(?:\n|$)',
            text
        )
        if match:
            answer = match.group(1).strip().strip('*').strip()
            before = text[:match.start()].strip()
            after = text[match.end():].strip()
            reasoning = (before + "\n" + after).strip()
        elif len(text) <= 150:
            answer = text
        else:
            parts = re.split(r'(?<=[.!?])\s+', text, maxsplit=1)
            answer = parts[0].strip()
            reasoning = parts[1].strip() if len(parts) > 1 else ""

        self._answer_label.setText(answer or text)
        self._reason_label.setText(reasoning)
        self._div2.setVisible(bool(reasoning))
        self._reason_section.setVisible(bool(reasoning))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show(self) -> None:
        super().show()
        # Exclude from screen capture (invisible to OBS, Teams, Zoom, etc.)
        hwnd = int(self.winId())
        _set_capture_excluded(hwnd)

    def hide(self) -> None:
        super().hide()

    def set_text(self, text: str) -> None:
        self._set_text_signal.emit(text)

    def append_text(self, chunk: str) -> None:
        self._append_text_signal.emit(chunk)

    def set_status(self, status: StatusIndicator) -> None:
        self._set_status_signal.emit(status)

    def show_api_warning(self) -> bool:
        msg = QMessageBox(self)
        msg.setWindowTitle("API Mode Warning")
        msg.setIcon(QMessageBox.Warning)
        msg.setText("Screen data will be sent to a remote API. Continue?")
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        msg.setDefaultButton(QMessageBox.Cancel)
        return msg.exec_() == QMessageBox.Ok

    def warn_api_mode_once(self) -> bool:
        if self._api_warning_shown:
            return True
        accepted = self.show_api_warning()
        self._api_warning_shown = True
        return accepted

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @pyqtSlot(str)
    def _do_set_text(self, text: str) -> None:
        self._full_text = text
        if not text:
            self._answer_label.setText("")
            self._reason_label.setText("")
            self._div2.setVisible(False)
            self._reason_section.setVisible(False)
        else:
            self._parse_and_display(text)

    @pyqtSlot(str)
    def _do_append_text(self, chunk: str) -> None:
        self._full_text += chunk
        self._parse_and_display(self._full_text)

    @pyqtSlot(object)
    def _do_set_status(self, status: StatusIndicator) -> None:
        status_map = {
            StatusIndicator.IDLE: ("idle", "#555560"),
            StatusIndicator.CAPTURING: ("capturing", "#6b7280"),
            StatusIndicator.PROCESSING: ("processing", "#6b7280"),
            StatusIndicator.ERROR: ("error", "#ef4444"),
        }
        text, color = status_map.get(status, ("idle", "#555560"))
        self._status_label.setText(text)
        self._status_label.setStyleSheet(
            f"color: {color}; font-size: 10px; background: transparent;"
        )
        if status == StatusIndicator.ERROR:
            self._answer_label.setStyleSheet(
                "color: #ef4444; font-size: 14px; font-weight: 600; background: transparent;"
            )
        else:
            self._answer_label.setStyleSheet(
                "color: #f0f0f0; font-size: 14px; font-weight: 600; background: transparent;"
            )

    # ------------------------------------------------------------------
    # Drag
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None
