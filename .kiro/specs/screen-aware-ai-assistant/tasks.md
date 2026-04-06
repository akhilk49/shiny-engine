# Implementation Plan: Local Screen-Aware AI Assistant

## Overview

Phased Python implementation of the screen-aware AI assistant pipeline. Each task builds incrementally toward a fully wired application: config → data models → individual components → pipeline orchestration → security hardening. Property-based tests (hypothesis) are placed immediately after the component they validate.

## Tasks

- [x] 1. Project setup and configuration
  - [x] 1.1 Create project directory structure and `requirements.txt`
    - Create `src/` package with `__init__.py` files for each module
    - Add `requirements.txt` with all pinned dependencies: mss, pyautogui, easyocr, paddleocr, pytesseract, Pillow, PyQt5, keyboard, pynput, ollama, openai, pyyaml, keyring, hypothesis, pytest
    - Create `config.yaml` with all default values matching the dataclass defaults in the design
    - _Requirements: 8.1, 8.4_

  - [x] 1.2 Implement `ConfigManager` class
    - Write `src/config_manager.py` with `ConfigManager` class implementing `load()` and `save(config)`
    - `load()` reads `config.yaml`, applies defaults for missing optional fields, and returns a valid `AppConfig`
    - `save()` serialises `AppConfig` back to `config.yaml` (excluding `api_key` — handled by keyring)
    - Raise a descriptive `ConfigError` when the file is missing or malformed
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [ ]* 1.3 Write property test for ConfigManager save/load round-trip
    - **Property 15: ConfigManager save/load round-trip**
    - **Validates: Requirements 8.2**
    - Use `hypothesis` to generate arbitrary valid `AppConfig` objects and assert `load(save(cfg)) == cfg`

- [x] 2. Core data models
  - [x] 2.1 Implement all dataclasses and enums in `src/models.py`
    - Define `Region`, `MonitorInfo`, `OCRResult`, `ProcessedText` dataclasses
    - Define `TextClass`, `StatusIndicator` enums
    - Define `AppConfig`, `HotkeyConfig`, `CaptureConfig`, `OCRConfig`, `LLMConfig`, `UIConfig` dataclasses with default values
    - Define `CaptureError` and `LLMUnavailableError` exception classes
    - _Requirements: 2.7, 3.2, 4.4, 6.7, 9.5, 9.6_

- [x] 3. ScreenCapture module
  - [x] 3.1 Implement `ScreenCapture` class in `src/screen_capture.py`
    - Implement `capture(region=None)` using `mss` as primary backend
    - Implement `pyautogui` fallback: if `mss` raises, catch and retry with `pyautogui.screenshot()`
    - Raise `CaptureError` if both backends fail
    - Implement `set_region(region)` and `list_monitors()`
    - Validate `region.width > 0` and `region.height > 0` before capturing; raise `ValueError` otherwise
    - Support `monitor_index` from `CaptureConfig` for multi-monitor setups
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [ ]* 3.2 Write property test for capture dimensions
    - **Property 1: Capture dimensions match requested region**
    - **Validates: Requirements 2.2**
    - Use `hypothesis` to generate valid `Region` objects (positive width/height) and assert returned image dimensions match

- [x] 4. OCREngine module
  - [x] 4.1 Implement `OCREngine` class in `src/ocr_engine.py`
    - Implement `extract(image)` and `extract_with_confidence(image)` methods
    - Support `easyocr` (default), `paddleocr`, and `tesseract` backends selected by `OCRConfig.backend`
    - Filter results by `confidence_threshold`; return empty string when no results pass the threshold
    - Fall back to Tesseract if the configured primary backend is unavailable
    - If all backends fail, raise an exception that the pipeline catches to set overlay status to ERROR
    - Do not mutate the input image at any point
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [ ]* 4.2 Write property test for OCR confidence filtering
    - **Property 2: OCR confidence filtering**
    - **Validates: Requirements 3.2**
    - Use `hypothesis` to generate lists of mock `OCRResult` objects with random confidence scores and assert only results meeting the threshold appear in the output

  - [ ]* 4.3 Write property test for OCR image immutability
    - **Property 3: OCR does not mutate input image**
    - **Validates: Requirements 3.3**
    - Use `hypothesis` to generate synthetic PIL images and assert pixel data, size, and mode are unchanged after `extract()`

- [x] 5. TextProcessor module
  - [x] 5.1 Implement `TextProcessor` class in `src/text_processor.py`
    - Implement `process(raw_text)` following the pseudocode algorithm in the design
    - Normalize whitespace: collapse multiple spaces → single space, multiple newlines → single newline
    - Deduplicate lines using case-insensitive comparison, preserving first occurrence
    - Filter out lines with two or fewer characters
    - Implement `classify(text)` returning the appropriate `TextClass` enum value
    - Return `ProcessedText(content="", classification=TextClass.EMPTY, word_count=0, is_empty=True)` for whitespace-only input
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ]* 5.2 Write property test for TextProcessor idempotency
    - **Property 4: TextProcessor deduplication is idempotent**
    - **Validates: Requirements 4.6**
    - Use `hypothesis` `st.text()` and assert `process(process(raw).content).content == process(raw).content`

  - [ ]* 5.3 Write property test for whitespace-only input
    - **Property 5: Whitespace-only input yields empty ProcessedText**
    - **Validates: Requirements 4.5**
    - Use `hypothesis` to generate strings composed entirely of whitespace and assert `is_empty=True` and `content=""`

- [x] 6. StateManager module
  - [x] 6.1 Implement `StateManager` class in `src/state_manager.py`
    - Implement `has_changed(text)`, `update(text)`, `get_cached()`, and `clear()` methods
    - Use `hashlib.sha256` on UTF-8 encoded text for comparison
    - Return `True` from `has_changed` when cache is empty
    - Protect `_cached_hash` and `_cached_text` with `threading.Lock` for thread safety
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 6.2 Write property test for StateManager change detection
    - **Property 6: StateManager change detection correctness**
    - **Validates: Requirements 5.1, 5.2**
    - Use `hypothesis` `st.text(min_size=1)` and assert `has_changed` returns `False` after `update(text)` and `True` for any different text

  - [ ]* 6.3 Write property test for StateManager cache round-trip
    - **Property 7: StateManager cache round-trip**
    - **Validates: Requirements 5.4**
    - Use `hypothesis` `st.text()` and assert `get_cached()` returns the exact text passed to `update(text)`

- [x] 7. Checkpoint — core components complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. LLMEngine module
  - [x] 8.1 Implement `LLMEngine` class in `src/llm_engine.py`
    - Implement `query(prompt)` and `query_stream(prompt)` for both `ollama` and `openai` backends
    - Implement `build_prompt(processed)` substituting `processed.content` into `config.llm.prompt_template` at `{text}`
    - Implement `health_check()` returning `True` when backend is reachable
    - Implement retry loop with exponential backoff starting at 1 second; double delay each attempt
    - Raise `LLMUnavailableError` after `retry_attempts` are exhausted
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

  - [ ]* 8.2 Write property test for streaming token reconstruction
    - **Property 8: Streaming tokens reconstruct full response**
    - **Validates: Requirements 6.2**
    - Mock the backend and assert `"".join(query_stream(prompt)) == query(prompt)` for arbitrary prompts

  - [ ]* 8.3 Write property test for retry count bound
    - **Property 9: Retry count is bounded**
    - **Validates: Requirements 6.6**
    - Use `hypothesis` `st.integers(min_value=1, max_value=5)` for `retry_attempts`; mock all backend calls to fail and assert attempt count never exceeds the configured value

- [x] 9. OverlayUI module
  - [x] 9.1 Implement `OverlayUI` class in `src/overlay_ui.py`
    - Create a frameless `QWidget` with `Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint` flags
    - Implement `show()`, `hide()`, `set_text(text)`, `append_text(chunk)`, `set_status(status)`
    - Route `set_text` and `append_text` through `pyqtSignal` so background threads can call them safely
    - Implement mouse-press drag on the title bar area using `mousePressEvent` and `mouseMoveEvent`
    - Display a `StatusIndicator` label that updates on `set_status()` calls
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [ ]* 9.2 Write property test for always-on-top flag persistence
    - **Property 13: OverlayUI always-on-top flag is never cleared**
    - **Validates: Requirements 7.1**
    - Use `hypothesis` to generate sequences of `set_text`, `append_text`, and `set_status` calls and assert `Qt.WindowStaysOnTopHint` remains set after each operation

- [x] 10. HotkeyListener module
  - [x] 10.1 Implement `HotkeyListener` class in `src/hotkey_listener.py`
    - Implement `start()`, `stop()`, and `register(hotkey, callback)` methods
    - Register all hotkeys from `HotkeyConfig` at startup using the `keyboard` library
    - Invoke callbacks in a non-blocking manner (dispatch to a thread pool or queue)
    - Run the listener loop in a dedicated daemon thread
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [x] 11. RegionSelector module
  - [x] 11.1 Implement `RegionSelector` class in `src/region_selector.py`
    - Create a transparent, full-screen `QWidget` overlay for drag-select
    - Track mouse press and release coordinates to compute `Region(x, y, width, height)`
    - Return the selected `Region` from `select()` (blocking call)
    - Close the overlay after selection completes
    - _Requirements: 10.1, 10.2, 10.4_

- [x] 12. Pipeline orchestration and Controller
  - [x] 12.1 Implement `Controller` class in `src/controller.py`
    - Instantiate all components using `ConfigManager.load()`
    - Implement `run_pipeline()` following the main pipeline algorithm from the design
    - Set overlay status to `CAPTURING` before capture, `PROCESSING` before LLM query, `IDLE` after completion
    - Short-circuit with "No readable text found" when `processed.is_empty` is True
    - Short-circuit with "No change detected" when `state_manager.has_changed()` returns False
    - Update `StateManager` cache after a successful LLM response
    - Handle `CaptureError`, `LLMUnavailableError`, and unhandled exceptions: log with stack trace, set overlay to ERROR
    - Return overlay to IDLE after the next successful pipeline run following an ERROR
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 12.1, 12.2, 12.3, 12.4, 12.5_

  - [x] 12.2 Wire hotkeys to pipeline and region selector in `Controller`
    - Register `on_capture_trigger` → `run_pipeline()` for `config.hotkeys.capture_trigger`
    - Register `on_region_select` → `RegionSelector().select()` + `capture.set_region()` for `config.hotkeys.region_select`
    - Register overlay toggle and quit hotkeys
    - Confirm region selection to the user via overlay message
    - _Requirements: 1.5, 10.2, 10.3, 10.4_

  - [x] 12.3 Implement `main.py` entry point
    - Instantiate `Controller`, call `overlay.show()` and `hotkeys.start()`, then enter the Qt event loop
    - _Requirements: 9.1_

  - [ ]* 12.4 Write property test for empty OCR short-circuit
    - **Property 10: Empty OCR output never reaches LLMEngine**
    - **Validates: Requirements 9.2**
    - Use `hypothesis` to generate pipeline runs where `TextProcessor` returns `is_empty=True` and assert `LLMEngine.query` and `query_stream` are never called

  - [ ]* 12.5 Write property test for unchanged text short-circuit
    - **Property 11: Unchanged text never triggers LLMEngine**
    - **Validates: Requirements 9.3**
    - Use `hypothesis` to generate pipeline runs where `StateManager.has_changed` returns `False` and assert `LLMEngine.query` and `query_stream` are never called

  - [ ]* 12.6 Write property test for state cache after successful pipeline run
    - **Property 12: State cache reflects last processed text**
    - **Validates: Requirements 9.4**
    - Use `hypothesis` to generate arbitrary processed text values and assert `state_manager.get_cached()` equals the content passed to the LLM after a successful run

- [x] 13. Checkpoint — full pipeline wired
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. Security hardening
  - [x] 14.1 Implement API key storage via `keyring` in `LLMEngine`
    - When `LLMConfig.backend == "openai"`, retrieve the API key from the OS keychain using `keyring.get_password()`
    - Provide a helper to store the key: `keyring.set_password("screen-ai-assistant", "openai_api_key", key)`
    - Ensure `api_key` is never written to `config.yaml` by `ConfigManager.save()`
    - _Requirements: 11.3_

  - [x] 14.2 Implement one-time API mode warning dialog in `OverlayUI`
    - Before the first API call, display a `QMessageBox` warning the user that screen data will be sent to a remote endpoint
    - Persist a `api_warning_shown` flag (in memory for the session) so the dialog appears only once
    - _Requirements: 11.2_

  - [x] 14.3 Enforce no-disk-write policy for screenshot data
    - In `ScreenCapture`, only write image files when `config.capture.save_debug_images` is `True`
    - In `OCREngine`, ensure no intermediate image files are created during processing
    - _Requirements: 11.4_

  - [ ]* 14.4 Write property test for screenshot data not written to disk
    - **Property 14: Screenshot data not written to disk in default mode**
    - **Validates: Requirements 11.4**
    - Use `hypothesis` to generate pipeline runs with `save_debug_images=False` and assert no image files are created or modified on the filesystem

- [ ] 15. Integration tests
  - [ ]* 15.1 Write end-to-end pipeline integration test
    - Create a synthetic screenshot (PIL Image with known text rendered via `Pillow` `ImageDraw`)
    - Run the full pipeline with a mock LLM server (stub returning a fixed response)
    - Assert OCR extracts the expected text, `TextProcessor` cleans it, and the overlay receives the mock response tokens in order
    - _Requirements: 9.1, 9.7_

  - [ ]* 15.2 Write integration test for error recovery paths
    - Test `CaptureError` path: mock both backends to fail, assert overlay shows "Capture failed" and status is ERROR
    - Test `LLMUnavailableError` path: mock all retries to fail, assert overlay shows the correct error message
    - Test OCR fallback: mock primary backend unavailable, assert Tesseract fallback is used
    - _Requirements: 12.1, 12.2, 12.4_

- [x] 16. Final checkpoint — all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Property tests use the `hypothesis` library and map directly to the 15 correctness properties in the design and requirements documents
- Checkpoints at tasks 7, 13, and 16 ensure incremental validation before proceeding
- The `keyring` integration (task 14.1) requires the OS keychain to be available; on headless systems use the `keyrings.alt` fallback
