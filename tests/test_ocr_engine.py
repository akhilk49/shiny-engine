"""Unit tests for OCREngine.

All OCR backends are mocked — no real easyocr/paddleocr/tesseract required.
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from src.models import OCRConfig, OCRResult
from src.ocr_engine import OCREngine, OCRError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_image(width: int = 100, height: int = 50) -> Image.Image:
    return Image.new("RGB", (width, height), color=(255, 255, 255))


def _make_config(backend: str = "easyocr", threshold: float = 0.5) -> OCRConfig:
    return OCRConfig(backend=backend, languages=["en"], gpu=False, confidence_threshold=threshold)


def _easyocr_raw(items: list[tuple[str, float]]) -> list:
    """Build fake EasyOCR readtext output: [(bbox, text, conf), ...]"""
    bbox = [[0, 0], [10, 0], [10, 10], [0, 10]]
    return [(bbox, text, conf) for text, conf in items]


def _tesseract_dict(items: list[tuple[str, float]]) -> dict:
    """Build fake pytesseract image_to_data output dict."""
    texts, confs, lefts, tops, widths, heights = [], [], [], [], [], []
    for text, conf in items:
        texts.append(text)
        confs.append(int(conf * 100))
        lefts.append(0)
        tops.append(0)
        widths.append(10)
        heights.append(10)
    return {
        "text": texts,
        "conf": confs,
        "left": lefts,
        "top": tops,
        "width": widths,
        "height": heights,
    }


# ---------------------------------------------------------------------------
# Tests: extract returns string
# ---------------------------------------------------------------------------

class TestExtractReturnsString:
    def test_returns_str_type(self):
        engine = OCREngine(_make_config())
        image = _make_image()

        mock_reader = MagicMock()
        mock_reader.readtext.return_value = _easyocr_raw([("Hello", 0.9)])
        engine._easyocr_reader = mock_reader

        with patch.dict(sys.modules, {"easyocr": MagicMock()}):
            result = engine.extract(image)

        assert isinstance(result, str)

    def test_returns_text_content(self):
        engine = OCREngine(_make_config())
        image = _make_image()

        mock_reader = MagicMock()
        mock_reader.readtext.return_value = _easyocr_raw([("Hello", 0.9), ("World", 0.8)])
        engine._easyocr_reader = mock_reader

        with patch.dict(sys.modules, {"easyocr": MagicMock()}):
            result = engine.extract(image)

        assert "Hello" in result
        assert "World" in result


# ---------------------------------------------------------------------------
# Tests: confidence filtering
# ---------------------------------------------------------------------------

class TestConfidenceFiltering:
    def test_results_above_threshold_included(self):
        engine = OCREngine(_make_config(threshold=0.5))
        image = _make_image()

        mock_reader = MagicMock()
        mock_reader.readtext.return_value = _easyocr_raw([("Above", 0.9), ("AtThreshold", 0.5)])
        engine._easyocr_reader = mock_reader

        with patch.dict(sys.modules, {"easyocr": MagicMock()}):
            results = engine.extract_with_confidence(image)

        texts = [r.text for r in results]
        assert "Above" in texts
        assert "AtThreshold" in texts

    def test_results_below_threshold_excluded(self):
        engine = OCREngine(_make_config(threshold=0.5))
        image = _make_image()

        mock_reader = MagicMock()
        mock_reader.readtext.return_value = _easyocr_raw([("Good", 0.9), ("Bad", 0.3)])
        engine._easyocr_reader = mock_reader

        with patch.dict(sys.modules, {"easyocr": MagicMock()}):
            results = engine.extract_with_confidence(image)

        texts = [r.text for r in results]
        assert "Good" in texts
        assert "Bad" not in texts

    def test_empty_string_when_no_results_pass_threshold(self):
        engine = OCREngine(_make_config(threshold=0.9))
        image = _make_image()

        mock_reader = MagicMock()
        mock_reader.readtext.return_value = _easyocr_raw([("Low", 0.1), ("AlsoLow", 0.4)])
        engine._easyocr_reader = mock_reader

        with patch.dict(sys.modules, {"easyocr": MagicMock()}):
            result = engine.extract(image)

        assert result == ""

    def test_exact_threshold_boundary_included(self):
        """Confidence exactly equal to threshold should be included."""
        engine = OCREngine(_make_config(threshold=0.7))
        image = _make_image()

        mock_reader = MagicMock()
        mock_reader.readtext.return_value = _easyocr_raw([("Exact", 0.7)])
        engine._easyocr_reader = mock_reader

        with patch.dict(sys.modules, {"easyocr": MagicMock()}):
            results = engine.extract_with_confidence(image)

        assert len(results) == 1
        assert results[0].text == "Exact"


# ---------------------------------------------------------------------------
# Tests: input image not mutated
# ---------------------------------------------------------------------------

class TestImageNotMutated:
    def test_extract_does_not_mutate_image(self):
        engine = OCREngine(_make_config())
        image = _make_image()

        original_size = image.size
        original_mode = image.mode
        original_pixels = list(image.getdata())

        mock_reader = MagicMock()
        mock_reader.readtext.return_value = _easyocr_raw([("Text", 0.9)])
        engine._easyocr_reader = mock_reader

        with patch.dict(sys.modules, {"easyocr": MagicMock()}):
            engine.extract(image)

        assert image.size == original_size
        assert image.mode == original_mode
        assert list(image.getdata()) == original_pixels

    def test_extract_with_confidence_does_not_mutate_image(self):
        engine = OCREngine(_make_config())
        image = _make_image()

        original_size = image.size
        original_mode = image.mode
        original_pixels = list(image.getdata())

        mock_reader = MagicMock()
        mock_reader.readtext.return_value = _easyocr_raw([("Text", 0.9)])
        engine._easyocr_reader = mock_reader

        with patch.dict(sys.modules, {"easyocr": MagicMock()}):
            engine.extract_with_confidence(image)

        assert image.size == original_size
        assert image.mode == original_mode
        assert list(image.getdata()) == original_pixels


# ---------------------------------------------------------------------------
# Tests: backend fallback to tesseract
# ---------------------------------------------------------------------------

class TestBackendFallback:
    def test_easyocr_unavailable_falls_back_to_tesseract(self):
        """When easyocr import fails, should fall back to tesseract."""
        engine = OCREngine(_make_config(backend="easyocr"))
        image = _make_image()

        mock_pytesseract = MagicMock()
        mock_pytesseract.Output.DICT = "dict"
        mock_pytesseract.image_to_data.return_value = _tesseract_dict([("Fallback", 0.9)])

        # Remove easyocr from sys.modules to simulate ImportError
        with patch.dict(sys.modules, {"easyocr": None}):
            with patch.dict(sys.modules, {"pytesseract": mock_pytesseract}):
                result = engine.extract(image)

        assert "Fallback" in result

    def test_paddleocr_unavailable_falls_back_to_tesseract(self):
        """When paddleocr import fails, should fall back to tesseract."""
        engine = OCREngine(_make_config(backend="paddleocr"))
        image = _make_image()

        mock_pytesseract = MagicMock()
        mock_pytesseract.Output.DICT = "dict"
        mock_pytesseract.image_to_data.return_value = _tesseract_dict([("PaddleFallback", 0.8)])

        with patch.dict(sys.modules, {"paddleocr": None}):
            with patch.dict(sys.modules, {"pytesseract": mock_pytesseract}):
                result = engine.extract(image)

        assert "PaddleFallback" in result

    def test_tesseract_backend_uses_tesseract_directly(self):
        """When backend is 'tesseract', use tesseract without trying others."""
        engine = OCREngine(_make_config(backend="tesseract"))
        image = _make_image()

        mock_pytesseract = MagicMock()
        mock_pytesseract.Output.DICT = "dict"
        mock_pytesseract.image_to_data.return_value = _tesseract_dict([("TesseractDirect", 0.95)])

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract}):
            result = engine.extract(image)

        assert "TesseractDirect" in result


# ---------------------------------------------------------------------------
# Tests: all backends fail raises OCRError
# ---------------------------------------------------------------------------

class TestAllBackendsFail:
    def test_raises_ocr_error_when_all_backends_unavailable(self):
        """When primary and tesseract both unavailable, OCRError is raised."""
        engine = OCREngine(_make_config(backend="easyocr"))
        image = _make_image()

        with patch.dict(sys.modules, {"easyocr": None, "pytesseract": None}):
            with pytest.raises(OCRError):
                engine.extract(image)

    def test_raises_ocr_error_for_tesseract_backend_when_unavailable(self):
        """When tesseract backend configured and pytesseract missing, OCRError raised."""
        engine = OCREngine(_make_config(backend="tesseract"))
        image = _make_image()

        with patch.dict(sys.modules, {"pytesseract": None}):
            with pytest.raises(OCRError):
                engine.extract(image)

    def test_raises_ocr_error_for_paddleocr_when_all_unavailable(self):
        """When paddleocr and tesseract both unavailable, OCRError is raised."""
        engine = OCREngine(_make_config(backend="paddleocr"))
        image = _make_image()

        with patch.dict(sys.modules, {"paddleocr": None, "pytesseract": None}):
            with pytest.raises(OCRError):
                engine.extract(image)


# ---------------------------------------------------------------------------
# Tests: OCRResult structure
# ---------------------------------------------------------------------------

class TestOCRResultStructure:
    def test_extract_with_confidence_returns_ocr_results(self):
        engine = OCREngine(_make_config())
        image = _make_image()

        mock_reader = MagicMock()
        mock_reader.readtext.return_value = _easyocr_raw([("Hello", 0.9)])
        engine._easyocr_reader = mock_reader

        with patch.dict(sys.modules, {"easyocr": MagicMock()}):
            results = engine.extract_with_confidence(image)

        assert len(results) == 1
        r = results[0]
        assert isinstance(r, OCRResult)
        assert r.text == "Hello"
        assert r.confidence == pytest.approx(0.9)
        assert isinstance(r.bbox, tuple)
        assert len(r.bbox) == 4
