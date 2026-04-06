"""ConfigManager — loads and saves application configuration from config.yaml."""

from __future__ import annotations

import os
from typing import Any, Dict

import yaml

from src.models import (
    AppConfig,
    CaptureConfig,
    ConfigError,
    HotkeyConfig,
    LLMConfig,
    OCRConfig,
    Region,
    UIConfig,
)


class ConfigManager:
    """Loads and saves :class:`AppConfig` to/from a YAML file.

    The ``api_key`` field of :class:`LLMConfig` is intentionally excluded from
    the saved file — it must be stored in the OS keychain via ``keyring``.
    """

    def __init__(self, path: str = "config.yaml") -> None:
        self._path = path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> AppConfig:
        """Read *config.yaml* and return a fully-populated :class:`AppConfig`.

        Raises:
            ConfigError: If the file is missing, cannot be parsed, or contains
                         values of the wrong type.
        """
        raw = self._read_yaml()
        try:
            return self._parse(raw)
        except (TypeError, ValueError, KeyError) as exc:
            raise ConfigError(f"Malformed configuration in '{self._path}': {exc}") from exc

    def save(self, config: AppConfig) -> None:
        """Serialise *config* to *config.yaml*.

        The ``api_key`` field is **never** written to disk.

        Raises:
            ConfigError: If the file cannot be written.
        """
        data = self._serialise(config)
        try:
            with open(self._path, "w", encoding="utf-8") as fh:
                yaml.dump(data, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)
        except OSError as exc:
            raise ConfigError(f"Cannot write configuration to '{self._path}': {exc}") from exc

    # ------------------------------------------------------------------
    # Private helpers — reading
    # ------------------------------------------------------------------

    def _read_yaml(self) -> Dict[str, Any]:
        if not os.path.exists(self._path):
            raise ConfigError(
                f"Configuration file '{self._path}' not found. "
                "Create it or copy the default config.yaml."
            )
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise ConfigError(f"Cannot parse '{self._path}': {exc}") from exc

        if data is None:
            # Empty file — treat as empty dict so defaults apply
            return {}
        if not isinstance(data, dict):
            raise ConfigError(
                f"'{self._path}' must contain a YAML mapping at the top level, "
                f"got {type(data).__name__}."
            )
        return data

    def _parse(self, raw: Dict[str, Any]) -> AppConfig:
        hotkeys = self._parse_hotkeys(raw.get("hotkeys") or {})
        capture = self._parse_capture(raw.get("capture") or {})
        ocr = self._parse_ocr(raw.get("ocr") or {})
        llm = self._parse_llm(raw.get("llm") or {})
        ui = self._parse_ui(raw.get("ui") or {})
        return AppConfig(hotkeys=hotkeys, capture=capture, ocr=ocr, llm=llm, ui=ui)

    @staticmethod
    def _parse_hotkeys(d: Dict[str, Any]) -> HotkeyConfig:
        defaults = HotkeyConfig()
        return HotkeyConfig(
            capture_trigger=str(d.get("capture_trigger", defaults.capture_trigger)),
            region_select=str(d.get("region_select", defaults.region_select)),
            toggle_overlay=str(d.get("toggle_overlay", defaults.toggle_overlay)),
            quit=str(d.get("quit", defaults.quit)),
        )

    @staticmethod
    def _parse_capture(d: Dict[str, Any]) -> CaptureConfig:
        defaults = CaptureConfig()
        region_raw = d.get("region")
        region: Region | None = None
        if isinstance(region_raw, dict):
            region = Region(
                x=int(region_raw["x"]),
                y=int(region_raw["y"]),
                width=int(region_raw["width"]),
                height=int(region_raw["height"]),
            )
        return CaptureConfig(
            backend=str(d.get("backend", defaults.backend)),
            monitor_index=int(d.get("monitor_index", defaults.monitor_index)),
            region=region,
            save_debug_images=bool(d.get("save_debug_images", defaults.save_debug_images)),
        )

    @staticmethod
    def _parse_ocr(d: Dict[str, Any]) -> OCRConfig:
        defaults = OCRConfig()
        languages = d.get("languages", defaults.languages)
        if not isinstance(languages, list):
            raise ValueError(f"ocr.languages must be a list, got {type(languages).__name__}")
        return OCRConfig(
            backend=str(d.get("backend", defaults.backend)),
            languages=[str(lang) for lang in languages],
            gpu=bool(d.get("gpu", defaults.gpu)),
            confidence_threshold=float(d.get("confidence_threshold", defaults.confidence_threshold)),
        )

    @staticmethod
    def _parse_llm(d: Dict[str, Any]) -> LLMConfig:
        defaults = LLMConfig()
        return LLMConfig(
            backend=str(d.get("backend", defaults.backend)),
            model=str(d.get("model", defaults.model)),
            base_url=str(d.get("base_url", defaults.base_url)),
            # api_key is intentionally NOT read from disk — use keyring
            api_key=None,
            max_tokens=int(d.get("max_tokens", defaults.max_tokens)),
            temperature=float(d.get("temperature", defaults.temperature)),
            timeout_seconds=int(d.get("timeout_seconds", defaults.timeout_seconds)),
            retry_attempts=int(d.get("retry_attempts", defaults.retry_attempts)),
            prompt_template=str(d.get("prompt_template", defaults.prompt_template)),
        )

    @staticmethod
    def _parse_ui(d: Dict[str, Any]) -> UIConfig:
        defaults = UIConfig()
        return UIConfig(
            width=int(d.get("width", defaults.width)),
            height=int(d.get("height", defaults.height)),
            opacity=float(d.get("opacity", defaults.opacity)),
            position_x=int(d.get("position_x", defaults.position_x)),
            position_y=int(d.get("position_y", defaults.position_y)),
            font_size=int(d.get("font_size", defaults.font_size)),
            theme=str(d.get("theme", defaults.theme)),
            always_on_top=bool(d.get("always_on_top", defaults.always_on_top)),
        )

    # ------------------------------------------------------------------
    # Private helpers — writing
    # ------------------------------------------------------------------

    @staticmethod
    def _serialise(config: AppConfig) -> Dict[str, Any]:
        hk = config.hotkeys
        cap = config.capture
        ocr = config.ocr
        llm = config.llm
        ui = config.ui

        region_data = None
        if cap.region is not None:
            region_data = {
                "x": cap.region.x,
                "y": cap.region.y,
                "width": cap.region.width,
                "height": cap.region.height,
            }

        return {
            "hotkeys": {
                "capture_trigger": hk.capture_trigger,
                "region_select": hk.region_select,
                "toggle_overlay": hk.toggle_overlay,
                "quit": hk.quit,
            },
            "capture": {
                "backend": cap.backend,
                "monitor_index": cap.monitor_index,
                "region": region_data,
                "save_debug_images": cap.save_debug_images,
            },
            "ocr": {
                "backend": ocr.backend,
                "languages": ocr.languages,
                "gpu": ocr.gpu,
                "confidence_threshold": ocr.confidence_threshold,
            },
            "llm": {
                # api_key is deliberately excluded — stored in keyring
                "backend": llm.backend,
                "model": llm.model,
                "base_url": llm.base_url,
                "max_tokens": llm.max_tokens,
                "temperature": llm.temperature,
                "timeout_seconds": llm.timeout_seconds,
                "retry_attempts": llm.retry_attempts,
                "prompt_template": llm.prompt_template,
            },
            "ui": {
                "width": ui.width,
                "height": ui.height,
                "opacity": ui.opacity,
                "position_x": ui.position_x,
                "position_y": ui.position_y,
                "font_size": ui.font_size,
                "theme": ui.theme,
                "always_on_top": ui.always_on_top,
            },
        }
