"""Unit tests for ConfigManager (task 1.2)."""

from __future__ import annotations

import os
import textwrap

import pytest
import yaml

from src.config_manager import ConfigManager
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_yaml(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(textwrap.dedent(content))


# ---------------------------------------------------------------------------
# load() — happy path
# ---------------------------------------------------------------------------

class TestLoad:
    def test_load_full_config(self, tmp_path):
        cfg_path = str(tmp_path / "config.yaml")
        write_yaml(cfg_path, """
            hotkeys:
              capture_trigger: "ctrl+shift+a"
              region_select: "ctrl+shift+r"
              toggle_overlay: "ctrl+shift+h"
              quit: "ctrl+shift+q"
            capture:
              backend: "mss"
              monitor_index: 1
              region: null
              save_debug_images: false
            ocr:
              backend: "easyocr"
              languages: ["en"]
              gpu: false
              confidence_threshold: 0.6
            llm:
              backend: "ollama"
              model: "llama3"
              base_url: "http://localhost:11434"
              max_tokens: 256
              temperature: 0.5
              timeout_seconds: 15
              retry_attempts: 2
              prompt_template: "Answer: {text}"
            ui:
              width: 500
              height: 400
              opacity: 0.8
              position_x: 50
              position_y: 50
              font_size: 14
              theme: "light"
              always_on_top: true
        """)
        config = ConfigManager(cfg_path).load()
        assert isinstance(config, AppConfig)
        assert config.hotkeys.capture_trigger == "ctrl+shift+a"
        assert config.capture.monitor_index == 1
        assert config.ocr.confidence_threshold == pytest.approx(0.6)
        assert config.llm.model == "llama3"
        assert config.llm.max_tokens == 256
        assert config.ui.theme == "light"

    def test_load_applies_defaults_for_missing_fields(self, tmp_path):
        cfg_path = str(tmp_path / "config.yaml")
        write_yaml(cfg_path, "hotkeys:\n  capture_trigger: 'ctrl+a'\n")
        config = ConfigManager(cfg_path).load()
        # Defaults applied for everything not specified
        assert config.hotkeys.capture_trigger == "ctrl+a"
        assert config.hotkeys.region_select == HotkeyConfig().region_select
        assert config.capture.backend == CaptureConfig().backend
        assert config.ocr.backend == OCRConfig().backend
        assert config.llm.backend == LLMConfig().backend
        assert config.ui.width == UIConfig().width

    def test_load_empty_file_uses_all_defaults(self, tmp_path):
        cfg_path = str(tmp_path / "config.yaml")
        write_yaml(cfg_path, "")
        config = ConfigManager(cfg_path).load()
        assert config == AppConfig()

    def test_load_region_parsed_correctly(self, tmp_path):
        cfg_path = str(tmp_path / "config.yaml")
        write_yaml(cfg_path, """
            capture:
              region:
                x: 10
                y: 20
                width: 300
                height: 200
        """)
        config = ConfigManager(cfg_path).load()
        assert config.capture.region == Region(x=10, y=20, width=300, height=200)

    def test_load_api_key_never_read_from_disk(self, tmp_path):
        cfg_path = str(tmp_path / "config.yaml")
        write_yaml(cfg_path, "llm:\n  api_key: 'super-secret'\n")
        config = ConfigManager(cfg_path).load()
        assert config.llm.api_key is None


# ---------------------------------------------------------------------------
# load() — error cases
# ---------------------------------------------------------------------------

class TestLoadErrors:
    def test_missing_file_raises_config_error(self, tmp_path):
        cfg_path = str(tmp_path / "nonexistent.yaml")
        with pytest.raises(ConfigError, match="not found"):
            ConfigManager(cfg_path).load()

    def test_malformed_yaml_raises_config_error(self, tmp_path):
        cfg_path = str(tmp_path / "config.yaml")
        with open(cfg_path, "w") as fh:
            fh.write("hotkeys: [\nunclosed bracket")
        with pytest.raises(ConfigError, match="Cannot parse"):
            ConfigManager(cfg_path).load()

    def test_non_mapping_top_level_raises_config_error(self, tmp_path):
        cfg_path = str(tmp_path / "config.yaml")
        write_yaml(cfg_path, "- item1\n- item2\n")
        with pytest.raises(ConfigError, match="mapping"):
            ConfigManager(cfg_path).load()

    def test_invalid_languages_type_raises_config_error(self, tmp_path):
        cfg_path = str(tmp_path / "config.yaml")
        write_yaml(cfg_path, "ocr:\n  languages: 'en'\n")
        with pytest.raises(ConfigError):
            ConfigManager(cfg_path).load()


# ---------------------------------------------------------------------------
# save() — happy path
# ---------------------------------------------------------------------------

class TestSave:
    def test_save_writes_yaml_file(self, tmp_path):
        cfg_path = str(tmp_path / "out.yaml")
        config = AppConfig()
        ConfigManager(cfg_path).save(config)
        assert os.path.exists(cfg_path)

    def test_save_excludes_api_key(self, tmp_path):
        cfg_path = str(tmp_path / "out.yaml")
        config = AppConfig()
        config.llm.api_key = "my-secret-key"
        ConfigManager(cfg_path).save(config)
        with open(cfg_path, "r") as fh:
            raw = fh.read()
        assert "my-secret-key" not in raw
        assert "api_key" not in raw

    def test_save_then_load_round_trip(self, tmp_path):
        cfg_path = str(tmp_path / "config.yaml")
        original = AppConfig(
            hotkeys=HotkeyConfig(capture_trigger="ctrl+alt+s"),
            capture=CaptureConfig(monitor_index=2, save_debug_images=True),
            ocr=OCRConfig(backend="tesseract", confidence_threshold=0.7),
            llm=LLMConfig(model="mistral", max_tokens=1024, temperature=0.1),
            ui=UIConfig(width=600, theme="light"),
        )
        mgr = ConfigManager(cfg_path)
        mgr.save(original)
        loaded = mgr.load()

        assert loaded.hotkeys.capture_trigger == "ctrl+alt+s"
        assert loaded.capture.monitor_index == 2
        assert loaded.capture.save_debug_images is True
        assert loaded.ocr.backend == "tesseract"
        assert loaded.ocr.confidence_threshold == pytest.approx(0.7)
        assert loaded.llm.model == "mistral"
        assert loaded.llm.max_tokens == 1024
        assert loaded.ui.width == 600
        assert loaded.ui.theme == "light"
        # api_key must remain None after round-trip
        assert loaded.llm.api_key is None

    def test_save_region_round_trip(self, tmp_path):
        cfg_path = str(tmp_path / "config.yaml")
        original = AppConfig()
        original.capture.region = Region(x=5, y=10, width=640, height=480)
        mgr = ConfigManager(cfg_path)
        mgr.save(original)
        loaded = mgr.load()
        assert loaded.capture.region == Region(x=5, y=10, width=640, height=480)

    def test_save_null_region_round_trip(self, tmp_path):
        cfg_path = str(tmp_path / "config.yaml")
        original = AppConfig()
        original.capture.region = None
        mgr = ConfigManager(cfg_path)
        mgr.save(original)
        loaded = mgr.load()
        assert loaded.capture.region is None
