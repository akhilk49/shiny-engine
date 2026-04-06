"""OCR Engine: extracts text from PIL Images using configurable backends."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PIL import Image

from src.models import OCRConfig, OCRResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class OCRError(Exception):
    """Raised when all OCR backends are unavailable."""


class OCREngine:
    """Extracts text from PIL Images using EasyOCR, PaddleOCR, or Tesseract."""

    def __init__(self, config: OCRConfig) -> None:
        self._config = config
        # Lazy-loaded backend instances
        self._easyocr_reader = None
        self._paddleocr_instance = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, image: Image.Image) -> str:
        """Run OCR on image and return extracted text as a plain string.

        Returns an empty string when no text is detected above the threshold.
        Does not modify the input image.
        """
        results = self.extract_with_confidence(image)
        lines = [r.text for r in results]
        return "\n".join(lines)

    def extract_with_confidence(self, image: Image.Image) -> list[OCRResult]:
        """Run OCR and return structured results filtered by confidence threshold.

        Does not modify the input image.
        """
        # Work on a copy so the original is never mutated
        image_copy = image.copy()

        backend = self._config.backend.lower()

        # Try the configured primary backend first, then fall back to tesseract
        if backend == "easyocr":
            try:
                return self._run_easyocr(image_copy)
            except (ImportError, OSError) as exc:
                raise OCRError(f"EasyOCR failed to load: {exc}") from exc

        if backend == "paddleocr":
            try:
                return self._run_paddleocr(image_copy)
            except (ImportError, OSError) as exc:
                raise OCRError(f"PaddleOCR failed to load: {exc}") from exc

        if backend == "tesseract":
            return self._run_tesseract_with_fallback(image_copy)

        # Unknown backend — treat like easyocr (default)
        logger.warning("Unknown OCR backend '%s', defaulting to EasyOCR", backend)
        try:
            return self._run_easyocr(image_copy)
        except (ImportError, OSError) as exc:
            raise OCRError(f"EasyOCR failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Backend implementations (lazy-loaded)
    # ------------------------------------------------------------------

    def _run_easyocr(self, image: Image.Image) -> list[OCRResult]:
        """Run EasyOCR backend (lazy import)."""
        import easyocr  # noqa: PLC0415 — intentional lazy import

        if self._easyocr_reader is None:
            self._easyocr_reader = easyocr.Reader(
                self._config.languages,
                gpu=False,  # force CPU — avoids CUDA DLL issues on Windows
            )

        raw = self._easyocr_reader.readtext(image)
        # EasyOCR returns: [(bbox, text, confidence), ...]
        return self._filter_results(
            [
                OCRResult(text=str(text), confidence=float(conf), bbox=self._bbox_to_tuple(bbox))
                for bbox, text, conf in raw
            ]
        )

    def _run_paddleocr(self, image: Image.Image) -> list[OCRResult]:
        """Run PaddleOCR backend (lazy import)."""
        from paddleocr import PaddleOCR  # noqa: PLC0415 — intentional lazy import

        if self._paddleocr_instance is None:
            lang = self._config.languages[0] if self._config.languages else "en"
            self._paddleocr_instance = PaddleOCR(use_angle_cls=True, lang=lang)

        raw = self._paddleocr_instance.ocr(image, cls=True)
        results: list[OCRResult] = []
        if raw:
            for line in raw:
                if line is None:
                    continue
                for item in line:
                    # PaddleOCR returns: [[bbox_points], (text, confidence)]
                    bbox_points, (text, conf) = item
                    results.append(
                        OCRResult(
                            text=str(text),
                            confidence=float(conf),
                            bbox=self._paddle_bbox_to_tuple(bbox_points),
                        )
                    )
        return self._filter_results(results)

    def _run_tesseract(self, image: Image.Image) -> list[OCRResult]:
        """Run Tesseract backend via pytesseract (lazy import)."""
        import pytesseract  # noqa: PLC0415 — intentional lazy import

        # Common Windows install path — set if not already on PATH
        import os
        if os.name == "nt":
            for candidate in [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            ]:
                if os.path.exists(candidate):
                    pytesseract.pytesseract.tesseract_cmd = candidate
                    # Set tessdata prefix so language files are found
                    tessdata = os.path.join(os.path.dirname(candidate), "tessdata")
                    os.environ["TESSDATA_PREFIX"] = tessdata
                    break

        lang = "+".join(
            "eng" if l == "en" else l
            for l in self._config.languages
        ) if self._config.languages else "eng"
        data = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)

        results: list[OCRResult] = []
        n = len(data["text"])
        for i in range(n):
            text = data["text"][i].strip()
            if not text:
                continue
            raw_conf = data["conf"][i]
            # pytesseract returns -1 for non-word entries; treat as 0
            conf = max(0.0, float(raw_conf) / 100.0)
            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            results.append(OCRResult(text=text, confidence=conf, bbox=(x, y, w, h)))

        return self._filter_results(results)

    def _run_tesseract_with_fallback(self, image: Image.Image) -> list[OCRResult]:
        """Attempt Tesseract; raise OCRError if unavailable."""
        try:
            return self._run_tesseract(image)
        except ImportError as exc:
            raise OCRError(
                "All OCR backends are unavailable. "
                "Install easyocr, paddleocr, or pytesseract."
            ) from exc

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _filter_results(self, results: list[OCRResult]) -> list[OCRResult]:
        """Return only results whose confidence meets the configured threshold."""
        threshold = self._config.confidence_threshold
        return [r for r in results if r.confidence >= threshold]

    @staticmethod
    def _bbox_to_tuple(bbox: object) -> tuple[int, int, int, int]:
        """Convert EasyOCR bbox (list of 4 corner points) to (x, y, w, h)."""
        try:
            xs = [pt[0] for pt in bbox]
            ys = [pt[1] for pt in bbox]
            x, y = int(min(xs)), int(min(ys))
            w, h = int(max(xs) - x), int(max(ys) - y)
            return (x, y, w, h)
        except Exception:
            return (0, 0, 0, 0)

    @staticmethod
    def _paddle_bbox_to_tuple(bbox_points: object) -> tuple[int, int, int, int]:
        """Convert PaddleOCR bbox (4 corner points) to (x, y, w, h)."""
        try:
            xs = [pt[0] for pt in bbox_points]
            ys = [pt[1] for pt in bbox_points]
            x, y = int(min(xs)), int(min(ys))
            w, h = int(max(xs) - x), int(max(ys) - y)
            return (x, y, w, h)
        except Exception:
            return (0, 0, 0, 0)
