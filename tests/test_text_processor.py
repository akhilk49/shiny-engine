"""Unit tests for TextProcessor (task 5.1).

Covers:
- Empty / whitespace input → is_empty=True
- Whitespace normalization (multiple spaces, multiple newlines)
- Duplicate line removal (case-insensitive)
- Lines with <= 2 chars filtered out
- classify: QUESTION, CODE, PARAGRAPH, EMPTY
- process returns correct word_count
- Idempotency: process(process(raw).content).content == process(raw).content
"""

import pytest

from src.text_processor import TextProcessor
from src.models import ProcessedText, TextClass


@pytest.fixture
def processor() -> TextProcessor:
    return TextProcessor()


# ---------------------------------------------------------------------------
# Empty / whitespace input
# ---------------------------------------------------------------------------

class TestEmptyInput:
    def test_empty_string_is_empty(self, processor):
        result = processor.process("")
        assert result.is_empty is True
        assert result.content == ""
        assert result.word_count == 0
        assert result.classification == TextClass.EMPTY

    def test_whitespace_only_is_empty(self, processor):
        result = processor.process("   \n\t\n  ")
        assert result.is_empty is True
        assert result.content == ""

    def test_single_space_is_empty(self, processor):
        result = processor.process(" ")
        assert result.is_empty is True

    def test_newlines_only_is_empty(self, processor):
        result = processor.process("\n\n\n")
        assert result.is_empty is True


# ---------------------------------------------------------------------------
# Whitespace normalization
# ---------------------------------------------------------------------------

class TestWhitespaceNormalization:
    def test_multiple_spaces_collapsed(self, processor):
        result = processor.process("hello   world")
        assert "  " not in result.content

    def test_multiple_spaces_become_single(self, processor):
        result = processor.process("foo    bar    baz")
        assert result.content == "foo bar baz"

    def test_multiple_newlines_collapsed(self, processor):
        result = processor.process("line one\n\n\nline two")
        assert "\n\n" not in result.content

    def test_multiple_newlines_become_single(self, processor):
        result = processor.process("first\n\n\nsecond")
        assert result.content == "first\nsecond"

    def test_leading_trailing_whitespace_stripped(self, processor):
        result = processor.process("  hello world  ")
        assert result.content == "hello world"


# ---------------------------------------------------------------------------
# Duplicate line removal
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_exact_duplicate_removed(self, processor):
        result = processor.process("hello world\nhello world")
        lines = result.content.split("\n")
        assert lines.count("hello world") == 1

    def test_case_insensitive_duplicate_removed(self, processor):
        result = processor.process("Hello World\nhello world\nHELLO WORLD")
        lines = result.content.split("\n")
        # Only the first occurrence should remain
        assert len(lines) == 1

    def test_first_occurrence_preserved(self, processor):
        result = processor.process("First Line\nfirst line")
        assert result.content == "First Line"

    def test_distinct_lines_all_kept(self, processor):
        result = processor.process("alpha beta\ngamma delta\nepsilon zeta")
        lines = result.content.split("\n")
        assert len(lines) == 3


# ---------------------------------------------------------------------------
# Short line filtering
# ---------------------------------------------------------------------------

class TestShortLineFiltering:
    def test_single_char_line_filtered(self, processor):
        result = processor.process("a\nhello world")
        assert "a" not in result.content.split("\n")

    def test_two_char_line_filtered(self, processor):
        result = processor.process("ab\nhello world")
        lines = result.content.split("\n")
        assert "ab" not in lines

    def test_three_char_line_kept(self, processor):
        result = processor.process("abc\nhello world")
        lines = result.content.split("\n")
        assert "abc" in lines

    def test_all_short_lines_yields_empty(self, processor):
        result = processor.process("a\nb\nc")
        assert result.is_empty is True


# ---------------------------------------------------------------------------
# classify
# ---------------------------------------------------------------------------

class TestClassify:
    def test_classify_empty_string(self, processor):
        assert processor.classify("") == TextClass.EMPTY

    def test_classify_whitespace_only(self, processor):
        assert processor.classify("   ") == TextClass.EMPTY

    def test_classify_question_mark(self, processor):
        assert processor.classify("What time is it?") == TextClass.QUESTION

    def test_classify_question_word_what(self, processor):
        assert processor.classify("What is the capital of France") == TextClass.QUESTION

    def test_classify_question_word_how(self, processor):
        assert processor.classify("How does this work") == TextClass.QUESTION

    def test_classify_question_word_why(self, processor):
        assert processor.classify("Why is the sky blue") == TextClass.QUESTION

    def test_classify_code_def(self, processor):
        assert processor.classify("def my_function():") == TextClass.CODE

    def test_classify_code_class(self, processor):
        assert processor.classify("class MyClass:") == TextClass.CODE

    def test_classify_code_import(self, processor):
        assert processor.classify("import os") == TextClass.CODE

    def test_classify_code_const(self, processor):
        assert processor.classify("const x = 42;") == TextClass.CODE

    def test_classify_code_arrow(self, processor):
        assert processor.classify("const fn = () => {}") == TextClass.CODE

    def test_classify_paragraph(self, processor):
        result = processor.classify("The quick brown fox jumps over the lazy dog.")
        assert result == TextClass.PARAGRAPH

    def test_classify_mixed_question_and_code(self, processor):
        result = processor.classify("How does def work in Python?")
        assert result == TextClass.MIXED


# ---------------------------------------------------------------------------
# word_count
# ---------------------------------------------------------------------------

class TestWordCount:
    def test_word_count_simple(self, processor):
        result = processor.process("hello world foo bar")
        assert result.word_count == 4

    def test_word_count_multiline(self, processor):
        result = processor.process("hello world\nfoo bar baz")
        assert result.word_count == 5

    def test_word_count_zero_for_empty(self, processor):
        result = processor.process("")
        assert result.word_count == 0


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_idempotent_simple(self, processor):
        raw = "Hello World\nhello world\nsome other line"
        first = processor.process(raw)
        second = processor.process(first.content)
        assert first.content == second.content

    def test_idempotent_with_extra_spaces(self, processor):
        raw = "foo   bar\n\n\nbaz qux"
        first = processor.process(raw)
        second = processor.process(first.content)
        assert first.content == second.content

    def test_idempotent_empty(self, processor):
        raw = ""
        first = processor.process(raw)
        second = processor.process(first.content)
        assert first.content == second.content

    def test_idempotent_code(self, processor):
        raw = "def foo():\n    pass\ndef foo():\n    pass"
        first = processor.process(raw)
        second = processor.process(first.content)
        assert first.content == second.content
