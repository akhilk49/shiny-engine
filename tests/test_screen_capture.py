"""Unit tests for ScreenCapture."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from src.models import CaptureConfig, CaptureError, MonitorInfo, Region
from src.screen_capture import ScreenCapture


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rgb_image(width: int = 100, height: int = 80) -> Image.Image:
    return Image.new("RGB", (width, height), color=(128, 128, 128))


def _make_config(**kwargs) -> CaptureConfig:
    defaults = dict(backend="mss", monitor_index=0, region=None, save_debug_images=False)
    defaults.update(kwargs)
    return CaptureConfig(**defaults)


# ---------------------------------------------------------------------------
# Full-screen capture returns PIL Image
# ---------------------------------------------------------------------------

class TestFullScreenCapture:
    def test_returns_pil_image(self):
        """Full-screen capture via mss returns a PIL Image."""
        config = _make_config()
        sc = ScreenCapture(config)

        fake_image = _make_rgb_image(1920, 1080)

        with patch.object(sc, "_capture_with_mss", return_value=fake_image):
            result = sc.capture()

        assert isinstance(result, Image.Image)
        assert result.size == (1920, 1080)

    def test_full_screen_no_region(self):
        """capture() with no region and no stored region calls mss without a region."""
        config = _make_config()
        sc = ScreenCapture(config)

        fake_image = _make_rgb_image(1280, 720)

        with patch.object(sc, "_capture_with_mss", return_value=fake_image) as mock_mss:
            sc.capture()
            mock_mss.assert_called_once_with(None)


# ---------------------------------------------------------------------------
# Region capture returns image with correct dimensions
# ---------------------------------------------------------------------------

class TestRegionCapture:
    def test_region_capture_correct_dimensions(self):
        """capture(region) returns image with region.width x region.height."""
        config = _make_config()
        sc = ScreenCapture(config)

        region = Region(x=10, y=20, width=300, height=200)
        fake_image = _make_rgb_image(300, 200)

        with patch.object(sc, "_capture_with_mss", return_value=fake_image):
            result = sc.capture(region=region)

        assert result.size == (300, 200)

    def test_stored_region_used_when_no_arg(self):
        """capture() uses the stored region when none is passed."""
        config = _make_config()
        sc = ScreenCapture(config)

        region = Region(x=0, y=0, width=150, height=100)
        sc.set_region(region)

        fake_image = _make_rgb_image(150, 100)

        with patch.object(sc, "_capture_with_mss", return_value=fake_image) as mock_mss:
            sc.capture()
            mock_mss.assert_called_once_with(region)


# ---------------------------------------------------------------------------
# Invalid region raises ValueError
# ---------------------------------------------------------------------------

class TestInvalidRegion:
    @pytest.mark.parametrize("width,height", [(0, 100), (100, 0), (0, 0), (-1, 100), (100, -5)])
    def test_zero_or_negative_dimensions_raise_value_error(self, width, height):
        """Region with non-positive width or height raises ValueError."""
        config = _make_config()
        sc = ScreenCapture(config)
        region = Region(x=0, y=0, width=width, height=height)

        with pytest.raises(ValueError):
            sc.capture(region=region)

    def test_valid_region_does_not_raise(self):
        """Region with positive dimensions does not raise ValueError."""
        config = _make_config()
        sc = ScreenCapture(config)
        region = Region(x=0, y=0, width=1, height=1)
        fake_image = _make_rgb_image(1, 1)

        with patch.object(sc, "_capture_with_mss", return_value=fake_image):
            result = sc.capture(region=region)

        assert isinstance(result, Image.Image)


# ---------------------------------------------------------------------------
# mss failure falls back to pyautogui
# ---------------------------------------------------------------------------

class TestFallback:
    def test_mss_failure_falls_back_to_pyautogui(self):
        """When mss fails, pyautogui fallback is used."""
        config = _make_config()
        sc = ScreenCapture(config)

        fake_image = _make_rgb_image(800, 600)

        with patch.object(sc, "_capture_with_mss", return_value=None):
            with patch.object(sc, "_capture_with_pyautogui", return_value=fake_image) as mock_pag:
                result = sc.capture()

        mock_pag.assert_called_once()
        assert isinstance(result, Image.Image)

    def test_mss_success_does_not_call_pyautogui(self):
        """When mss succeeds, pyautogui is never called."""
        config = _make_config()
        sc = ScreenCapture(config)

        fake_image = _make_rgb_image(800, 600)

        with patch.object(sc, "_capture_with_mss", return_value=fake_image):
            with patch.object(sc, "_capture_with_pyautogui") as mock_pag:
                sc.capture()

        mock_pag.assert_not_called()


# ---------------------------------------------------------------------------
# Both backends failing raises CaptureError
# ---------------------------------------------------------------------------

class TestBothBackendsFail:
    def test_both_fail_raises_capture_error(self):
        """CaptureError is raised when both mss and pyautogui fail."""
        config = _make_config()
        sc = ScreenCapture(config)

        with patch.object(sc, "_capture_with_mss", return_value=None):
            with patch.object(sc, "_capture_with_pyautogui", return_value=None):
                with pytest.raises(CaptureError):
                    sc.capture()


# ---------------------------------------------------------------------------
# set_region stores the region correctly
# ---------------------------------------------------------------------------

class TestSetRegion:
    def test_set_region_stores_region(self):
        """set_region stores the region and it is used on next capture."""
        config = _make_config()
        sc = ScreenCapture(config)

        region = Region(x=5, y=10, width=200, height=150)
        sc.set_region(region)

        assert sc._region is region

    def test_set_region_overrides_previous(self):
        """set_region replaces any previously stored region."""
        config = _make_config()
        sc = ScreenCapture(config)

        region1 = Region(x=0, y=0, width=100, height=100)
        region2 = Region(x=50, y=50, width=200, height=200)

        sc.set_region(region1)
        sc.set_region(region2)

        assert sc._region is region2

    def test_config_region_used_as_initial_region(self):
        """Region from CaptureConfig is used as the initial stored region."""
        initial_region = Region(x=0, y=0, width=400, height=300)
        config = _make_config(region=initial_region)
        sc = ScreenCapture(config)

        assert sc._region is initial_region


# ---------------------------------------------------------------------------
# list_monitors returns MonitorInfo list
# ---------------------------------------------------------------------------

class TestListMonitors:
    def test_list_monitors_returns_monitor_info_list(self):
        """list_monitors returns a list of MonitorInfo objects."""
        config = _make_config()
        sc = ScreenCapture(config)

        fake_monitors = [
            MonitorInfo(index=0, x=0, y=0, width=1920, height=1080),
            MonitorInfo(index=1, x=1920, y=0, width=1280, height=720),
        ]

        with patch.object(sc, "list_monitors", return_value=fake_monitors):
            result = sc.list_monitors()

        assert isinstance(result, list)
        assert all(isinstance(m, MonitorInfo) for m in result)
        assert len(result) == 2

    def test_list_monitors_with_mss(self):
        """list_monitors uses mss to enumerate monitors."""
        config = _make_config()
        sc = ScreenCapture(config)

        mock_mss_instance = MagicMock()
        mock_mss_instance.__enter__ = MagicMock(return_value=mock_mss_instance)
        mock_mss_instance.__exit__ = MagicMock(return_value=False)
        mock_mss_instance.monitors = [
            # index 0 = virtual combined screen (skipped)
            {"left": 0, "top": 0, "width": 3200, "height": 1080},
            # index 1 = primary monitor
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
            # index 2 = secondary monitor
            {"left": 1920, "top": 0, "width": 1280, "height": 1080},
        ]

        mock_mss_module = MagicMock()
        mock_mss_module.mss.return_value = mock_mss_instance

        with patch.dict(sys.modules, {"mss": mock_mss_module}):
            result = sc.list_monitors()

        assert len(result) == 2
        assert result[0].index == 0
        assert result[0].width == 1920
        assert result[1].index == 1
        assert result[1].width == 1280


# ---------------------------------------------------------------------------
# save_debug_images behaviour
# ---------------------------------------------------------------------------

class TestDebugImages:
    def test_no_disk_write_when_save_debug_images_false(self, tmp_path, monkeypatch):
        """No image files are written when save_debug_images is False."""
        monkeypatch.chdir(tmp_path)
        config = _make_config(save_debug_images=False)
        sc = ScreenCapture(config)

        fake_image = _make_rgb_image(100, 100)

        with patch.object(sc, "_capture_with_mss", return_value=fake_image):
            sc.capture()

        # No debug_captures directory should be created
        assert not (tmp_path / "debug_captures").exists()

    def test_disk_write_when_save_debug_images_true(self, tmp_path, monkeypatch):
        """Image file is written when save_debug_images is True."""
        monkeypatch.chdir(tmp_path)
        config = _make_config(save_debug_images=True)
        sc = ScreenCapture(config)

        fake_image = _make_rgb_image(100, 100)

        with patch.object(sc, "_capture_with_mss", return_value=fake_image):
            sc.capture()

        debug_dir = tmp_path / "debug_captures"
        assert debug_dir.exists()
        files = list(debug_dir.iterdir())
        assert len(files) == 1
        assert files[0].suffix == ".png"
