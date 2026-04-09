"""TextProcessor: cleans, deduplicates, and classifies raw OCR output."""

from __future__ import annotations

import re

from src.models import ProcessedText, TextClass

# Question words used for classification
_QUESTION_WORDS = {
    "what", "why", "how", "when", "where", "who",
    "is", "are", "can", "does", "do", "should", "would", "could", "will",
}

# Code indicator substrings / patterns
_CODE_INDICATORS = [
    "def ", "class ", "import ", "function", "=>",
    "{", "}", "if (", "for (", "while (", "#include", "var ", "const ", "let ",
]


class TextProcessor:
    """Cleans and classifies raw OCR output before sending to the LLM."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, raw_text: str) -> ProcessedText:
        """Clean, deduplicate, and classify *raw_text*.

        Returns a :class:`ProcessedText` with ``is_empty=True`` when the
        input is empty or whitespace-only.
        """
        if not raw_text or raw_text.strip() == "":
            return ProcessedText(
                content="",
                classification=TextClass.EMPTY,
                word_count=0,
                is_empty=True,
            )

        # --- Normalize whitespace ---
        text = raw_text.strip()
        # Collapse multiple consecutive spaces into one
        text = re.sub(r"[ \t]+", " ", text)
        # Collapse multiple consecutive newlines into one
        text = re.sub(r"\n{2,}", "\n", text)

        # --- Deduplicate lines but preserve MCQ option lines ---
        # --- Filter out lines with <= 2 characters UNLESS they look like option labels ---
        seen: set[str] = set()
        unique_lines: list[str] = []
        for line in text.split("\n"):
            stripped = line.strip()
            normalized = stripped.lower()
            # Keep option labels (1., 2., A., B., (1), (A), etc.) even if short
            is_option_label = bool(re.match(r'^[\(\[]?[a-dA-D1-4][\)\].]?\s', stripped))
            if normalized not in seen and (len(normalized) > 2 or is_option_label):
                seen.add(normalized)
                unique_lines.append(stripped)

        content = "\n".join(unique_lines)

        if not content:
            return ProcessedText(
                content="",
                classification=TextClass.EMPTY,
                word_count=0,
                is_empty=True,
            )

        classification = self.classify(content)
        word_count = len(content.split())

        return ProcessedText(
            content=content,
            classification=classification,
            word_count=word_count,
            is_empty=False,
        )

    def classify(self, text: str) -> TextClass:
        """Return the :class:`TextClass` that best describes *text*."""
        if not text or text.strip() == "":
            return TextClass.EMPTY

        is_question = self._is_question(text)
        is_code = self._is_code(text)

        if is_question and is_code:
            return TextClass.MIXED
        if is_question:
            return TextClass.QUESTION
        if is_code:
            return TextClass.CODE

        # Multi-line text that doesn't match question or code → PARAGRAPH
        return TextClass.PARAGRAPH

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_question(text: str) -> bool:
        """Return True if *text* looks like a question."""
        stripped = text.strip()
        if stripped.endswith("?"):
            return True
        # Check for question words (whole-word match, case-insensitive)
        words = re.findall(r"\b\w+\b", stripped.lower())
        return any(w in _QUESTION_WORDS for w in words)

    @staticmethod
    def _is_code(text: str) -> bool:
        """Return True if *text* contains code indicators."""
        return any(indicator in text for indicator in _CODE_INDICATORS)
