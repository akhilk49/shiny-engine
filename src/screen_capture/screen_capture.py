"""ScreenCapture: captures the full screen or a user-defined region.

Primary backend: mss
Fallback backend: pyautogui
"""

from __future__ import annotations

import os
from typing import Optional

from PIL import Image

from src.models import CaptureConfig, CaptureError, MonitorInfo, Region


class ScreenCapture:
    """Captures screen content and returns a PIL Image."""

    def __init__(self, config: CaptureConfig) -> None:
        self._config = config
        self._region: Optional[Region] = config.region

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def capture(self, region: Optional[Region] = None) -> Image.Image:
        """Capture the screen (or a region) and return a PIL Image.

        Args:
            region: Optional bounding box to capture. Falls back to the
                    region stored via ``set_region``, then full monitor.

        Returns:
            PIL Image of the captured area.

        Raises:
            ValueError: If the resolved region has non-positive dimensions.
            CaptureError: If all capture backends fail.
        """
        effective_region = region if region is not None else self._region

        if effective_region is not None:
            if effective_region.width <= 0 or effective_region.height <= 0:
                raise ValueError(
                    f"Region dimensions must be positive, got "
                    f"width={effective_region.width}, height={effective_region.height}"
                )

        image = self._capture_with_mss(effective_region)
        if image is None:
            image = self._capture_with_pyautogui(effective_region)
        if image is None:
            raise CaptureError("All screen capture backends failed.")

        if self._config.save_debug_images:
            self._save_debug_image(image)

        return image

    def set_region(self, region: Region) -> None:
        """Store the active capture region for subsequent captures."""
        self._region = region

    def list_monitors(self) -> list[MonitorInfo]:
        """Return a list of available monitors.

        Returns:
            List of MonitorInfo objects, one per detected monitor.
        """
        try:
            import mss  # type: ignore

            with mss.mss() as sct:
                monitors: list[MonitorInfo] = []
                # mss.monitors[0] is the combined virtual screen; skip it
                for idx, mon in enumerate(sct.monitors[1:], start=0):
                    monitors.append(
                        MonitorInfo(
                            index=idx,
                            x=mon["left"],
                            y=mon["top"],
                            width=mon["width"],
                            height=mon["height"],
                        )
                    )
                return monitors
        except Exception:
            # Fallback: return a single monitor based on pyautogui screen size
            try:
                import pyautogui  # type: ignore

                w, h = pyautogui.size()
                return [MonitorInfo(index=0, x=0, y=0, width=w, height=h)]
            except Exception:
                return []

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _capture_with_mss(self, region: Optional[Region]) -> Optional[Image.Image]:
        """Attempt capture using mss. Returns None on failure."""
        try:
            import mss  # type: ignore
            import mss.tools  # type: ignore

            with mss.mss() as sct:
                monitor_index = self._config.monitor_index
                # mss.monitors[0] is the virtual combined screen;
                # monitor_index 0 → monitors[1] (primary), etc.
                monitors = sct.monitors
                if monitor_index + 1 < len(monitors):
                    mon = monitors[monitor_index + 1]
                else:
                    mon = monitors[1] if len(monitors) > 1 else monitors[0]

                if region is not None:
                    capture_box = {
                        "left": mon["left"] + region.x,
                        "top": mon["top"] + region.y,
                        "width": region.width,
                        "height": region.height,
                    }
                else:
                    capture_box = mon

                screenshot = sct.grab(capture_box)
                return Image.frombytes(
                    "RGB",
                    (screenshot.width, screenshot.height),
                    screenshot.rgb,
                )
        except Exception:
            return None

    def _capture_with_pyautogui(self, region: Optional[Region]) -> Optional[Image.Image]:
        """Attempt capture using pyautogui. Returns None on failure."""
        try:
            import pyautogui  # type: ignore

            if region is not None:
                screenshot = pyautogui.screenshot(
                    region=(region.x, region.y, region.width, region.height)
                )
            else:
                screenshot = pyautogui.screenshot()

            return screenshot.convert("RGB")
        except Exception:
            return None

    def _save_debug_image(self, image: Image.Image) -> None:
        """Save image to disk for debugging (only when save_debug_images is True)."""
        import datetime

        debug_dir = "debug_captures"
        os.makedirs(debug_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = os.path.join(debug_dir, f"capture_{timestamp}.png")
        image.save(path)
