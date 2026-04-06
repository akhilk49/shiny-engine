"""Data models for the Screen-Aware AI Assistant."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class TextClass(Enum):
    QUESTION = "question"
    CODE = "code"
    PARAGRAPH = "paragraph"
    MIXED = "mixed"
    EMPTY = "empty"


class StatusIndicator(Enum):
    IDLE = "idle"
    CAPTURING = "capturing"
    PROCESSING = "processing"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Simple value objects
# ---------------------------------------------------------------------------

@dataclass
class Region:
    x: int
    y: int
    width: int
    height: int


@dataclass
class MonitorInfo:
    index: int
    x: int
    y: int
    width: int
    height: int


@dataclass
class OCRResult:
    text: str
    confidence: float
    bbox: tuple  # (x, y, w, h)


@dataclass
class ProcessedText:
    content: str
    classification: TextClass
    word_count: int
    is_empty: bool


# ---------------------------------------------------------------------------
# Configuration dataclasses
# ---------------------------------------------------------------------------

@dataclass
class HotkeyConfig:
    capture_trigger: str = "ctrl+shift+a"
    region_select: str = "ctrl+shift+r"
    toggle_overlay: str = "ctrl+shift+h"
    quit: str = "ctrl+shift+q"


@dataclass
class CaptureConfig:
    backend: str = "mss"
    monitor_index: int = 0
    region: Optional[Region] = None
    save_debug_images: bool = False


@dataclass
class OCRConfig:
    backend: str = "easyocr"
    languages: list = field(default_factory=lambda: ["en"])
    gpu: bool = False
    confidence_threshold: float = 0.5


@dataclass
class LLMConfig:
    backend: str = "ollama"
    model: str = "llama3"
    base_url: str = "http://localhost:11434"
    api_key: Optional[str] = None
    max_tokens: int = 512
    temperature: float = 0.3
    timeout_seconds: int = 10
    retry_attempts: int = 3
    prompt_template: str = (
        "You are an intelligent assistant.\n"
        "If the input is:\n"
        "- A question → answer clearly\n"
        "- Code → explain or debug\n"
        "- Text → summarize concisely\n\n"
        "Input: {text}"
    )


@dataclass
class UIConfig:
    width: int = 420
    height: int = 300
    opacity: float = 0.92
    position_x: int = 100
    position_y: int = 100
    font_size: int = 13
    theme: str = "dark"
    always_on_top: bool = True


@dataclass
class AppConfig:
    hotkeys: HotkeyConfig = field(default_factory=HotkeyConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    ocr: OCRConfig = field(default_factory=OCRConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    ui: UIConfig = field(default_factory=UIConfig)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class CaptureError(Exception):
    """Raised when all screen capture backends fail."""


class LLMUnavailableError(Exception):
    """Raised when the LLM backend cannot be reached after all retries."""


class ConfigError(Exception):
    """Raised when config.yaml is missing, malformed, or invalid."""


class OCRError(Exception):
    """Raised when all OCR backends are unavailable."""
