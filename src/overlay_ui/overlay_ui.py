"""Overlay UI — floating tooltip style."""

from __future__ import annotations

import ctypes
import re

from PyQt5.QtCore import Qt, QPoint, QPropertyAnimation, QEasingCurve, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea,
    QSizePolicy, QMessageBox, QFrame, QGraphicsOpacityEffect
)
from PyQt5.QtGui import QPainter, QColor, QPainterPath, QFont

from src.models import UIConfig, StatusIndicator

WDA_EXCLUDEFROMCAPTURE = 0x00000011


def _exclude_from_capture(hwnd: int) -> None:
    try:
        ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
    except Exception:
        pass


class OverlayUI(QWidget):
    _set_text_signal: pyqtSignal = pyqtSignal(str)
    _append_text_signal: pyqtSignal = pyqtSignal(str)
    _set_status_signal: pyqtSignal = pyqtSignal(object)

    def __init__(self, config: UIConfig) -> None:
        super().__init__(
            None,
            Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint
        )
        self._config = config
        self._drag_pos: QPoint | None = None
        self._api_warning_shown = False
        self._full_text = ""

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_DeleteOnClose, False)  # prevent premature deletion
        self.setWindowOpacity(config.opacity)
        self.resize(config.width, config.height)
        self.move(config.position_x, config.position_y)

        self._build_ui()

        self._set_text_signal.connect(self._do_set_text)
        self._append_text_signal.connect(self._do_append_text)
        self._set_status_signal.connect(self._do_set_status)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)  # shadow space
        outer.setSpacing(0)

        # Inner card
        self._card = QWidget(self)
        self._card.setObjectName("Card")
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)
        outer.addWidget(self._card)

        # Top row: dot indicator + status text
        top = QWidget()
        top.setObjectName("Top")
        top.setFixedHeight(28)
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(12, 0, 12, 0)
        top_layout.setAlignment(Qt.AlignVCenter)

        self._status_label = QLabel("●  ready")
        self._status_label.setObjectName("Status")
        top_layout.addWidget(self._status_label)
        card_layout.addWidget(top)

        # Thin divider
        div = QFrame()
        div.setObjectName("Div")
        div.setFrameShape(QFrame.HLine)
        div.setFixedHeight(1)
        card_layout.addWidget(div)

        # Answer — large, prominent
        self._answer_label = QLabel("")
        self._answer_label.setObjectName("Answer")
        self._answer_label.setWordWrap(True)
        self._answer_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._answer_label.setContentsMargins(12, 10, 12, 8)
        card_layout.addWidget(self._answer_label)

        # Reasoning — smaller, dimmer, scrollable
        self._reason_label = QLabel("")
        self._reason_label.setObjectName("Reason")
        self._reason_label.setWordWrap(True)
        self._reason_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._reason_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._reason_label.setContentsMargins(12, 0, 12, 10)

        self._scroll = QScrollArea()
        self._scroll.setWidget(self._reason_label)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setObjectName("Scroll")
        card_layout.addWidget(self._scroll)

        self._content_label = self._reason_label  # compat

        self._apply_styles()

    def _apply_styles(self) -> None:
        self._card.setStyleSheet("""
            QWidget#Card {
                background-color: rgba(18, 18, 20, 245);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
            QWidget#Top {
                background: transparent;
                border-radius: 12px 12px 0 0;
            }
            QLabel#Status {
                color: rgba(255,255,255,0.35);
                font-size: 10px;
                font-family: 'Segoe UI', sans-serif;
                background: transparent;
            }
            QFrame#Div {
                background-color: rgba(255,255,255,0.06);
                border: none;
            }
            QLabel#Answer {
                color: rgba(255,255,255,0.92);
                font-size: 13px;
                font-weight: 600;
                font-family: 'Segoe UI', sans-serif;
                background: transparent;
                line-height: 1.5;
            }
            QLabel#Reason {
                color: rgba(255,255,255,0.40);
                font-size: 11px;
                font-family: 'Segoe UI', sans-serif;
                background: transparent;
                line-height: 1.5;
            }
            QScrollArea#Scroll {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.15);
                border-radius: 1px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

    def _parse_and_display(self, text: str) -> None:
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
        if not text:
            return

        answer = ""
        reasoning = ""

        m = re.search(r'(?:^|\n)\s*(?:\*\*)?[Aa]nswer(?:\*\*)?[:\s]+(.+?)(?:\n|$)', text)
        if m:
            answer = m.group(1).strip().strip('*')
            before = text[:m.start()].strip()
            after = text[m.end():].strip()
            reasoning = (before + "\n" + after).strip()
        elif len(text) <= 160:
            answer = text
        else:
            parts = re.split(r'(?<=[.!?])\s+', text, maxsplit=1)
            answer = parts[0].strip()
            reasoning = parts[1].strip() if len(parts) > 1 else ""

        self._answer_label.setText(answer or text)
        self._reason_label.setText(reasoning)
        self._scroll.setVisible(bool(reasoning))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show(self) -> None:
        super().show()
        _exclude_from_capture(int(self.winId()))

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
        msg.setWindowTitle("API Mode")
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
            self._scroll.setVisible(False)
        else:
            self._parse_and_display(text)

    @pyqtSlot(str)
    def _do_append_text(self, chunk: str) -> None:
        self._full_text += chunk
        self._parse_and_display(self._full_text)

    @pyqtSlot(object)
    def _do_set_status(self, status: StatusIndicator) -> None:
        labels = {
            StatusIndicator.IDLE:       ("●  ready",       "rgba(255,255,255,0.25)"),
            StatusIndicator.CAPTURING:  ("●  capturing",   "rgba(255,255,255,0.45)"),
            StatusIndicator.PROCESSING: ("●  thinking",    "rgba(255,255,255,0.55)"),
            StatusIndicator.ERROR:      ("●  error",       "rgba(239,68,68,0.8)"),
        }
        text, color = labels.get(status, ("●  ready", "rgba(255,255,255,0.25)"))
        self._status_label.setText(text)
        self._status_label.setStyleSheet(
            f"color: {color}; font-size: 10px; font-family: 'Segoe UI'; background: transparent;"
        )
        if status == StatusIndicator.ERROR:
            self._answer_label.setStyleSheet(
                "color: rgba(239,68,68,0.9); font-size: 13px; font-weight: 600; "
                "font-family: 'Segoe UI'; background: transparent;"
            )
        else:
            self._answer_label.setStyleSheet(
                "color: rgba(255,255,255,0.92); font-size: 13px; font-weight: 600; "
                "font-family: 'Segoe UI'; background: transparent;"
            )

    # ------------------------------------------------------------------
    # Drag (whole window)
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
