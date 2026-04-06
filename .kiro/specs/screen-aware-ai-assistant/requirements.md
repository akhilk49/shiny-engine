# Requirements Document

## Introduction

This document defines the requirements for the Local Screen-Aware AI Assistant — a Windows desktop application that runs continuously in the background, captures user-selected screen regions on hotkey trigger, extracts visible text via OCR, and processes it through a local or remote LLM. Responses are displayed in a floating, always-on-top overlay. The system is designed for fully local, privacy-first operation with an optional hybrid API mode.

The architecture follows a linear pipeline: hotkey trigger → screen capture → OCR → text processing → change detection → LLM inference → overlay rendering. All eight components (HotkeyListener, ScreenCapture, OCREngine, TextProcessor, StateManager, LLMEngine, OverlayUI, ConfigManager) are decoupled and communicate asynchronously to meet the end-to-end latency target of under 4 seconds.

---

## Glossary

- **System**: The Local Screen-Aware AI Assistant application as a whole
- **HotkeyListener**: The component that registers and listens for global keyboard shortcuts
- **ScreenCapture**: The component that captures the screen or a user-defined region and returns a PIL Image
- **OCREngine**: The component that extracts text from a PIL Image using a configured OCR backend
- **TextProcessor**: The component that cleans, deduplicates, and classifies raw OCR output
- **StateManager**: The component that tracks the last processed text to avoid redundant LLM calls
- **LLMEngine**: The component that sends prompts to the configured LLM backend and returns responses
- **OverlayUI**: The always-on-top floating window that renders LLM responses and status indicators
- **ConfigManager**: The component that loads and validates configuration from `config.yaml`
- **Pipeline**: The end-to-end sequence from hotkey trigger through to overlay display
- **Region**: A bounding box defined by x, y, width, and height coordinates on the screen
- **ProcessedText**: The output of TextProcessor containing cleaned content, classification, word count, and empty flag
- **TextClass**: An enumeration of content types: QUESTION, CODE, PARAGRAPH, MIXED, EMPTY
- **StatusIndicator**: An enumeration of pipeline states: IDLE, CAPTURING, PROCESSING, ERROR
- **LLMUnavailableError**: The error raised when the LLM backend cannot be reached after all retries
- **CaptureError**: The error raised when all screen capture backends fail
- **AppConfig**: The top-level configuration dataclass containing all component configurations
- **OCRResult**: A structured result containing extracted text, confidence score, and bounding box
- **API mode**: Operation mode where the LLM backend is a remote OpenAI-compatible API
- **Local mode**: Operation mode where the LLM backend is Ollama running entirely on the local machine

---

## Requirements

### Requirement 1: Hotkey Listener

**User Story:** As a user, I want to trigger the assistant using global keyboard shortcuts, so that I can activate screen capture and other functions without switching focus away from my current application.

#### Acceptance Criteria

1. THE HotkeyListener SHALL register all hotkeys defined in HotkeyConfig at application startup
2. WHEN a registered hotkey is pressed, THE HotkeyListener SHALL invoke the associated callback function
3. WHEN a hotkey callback is invoked, THE HotkeyListener SHALL invoke it without blocking the main application thread
4. WHILE the application is running, THE HotkeyListener SHALL run in a dedicated daemon thread
5. THE HotkeyListener SHALL support the following default hotkey bindings: capture trigger (Ctrl+Shift+A), region select (Ctrl+Shift+R), overlay toggle (Ctrl+Shift+H), and quit (Ctrl+Shift+Q)
6. THE HotkeyListener SHALL allow hotkey bindings to be overridden via HotkeyConfig

---

### Requirement 2: Screen Capture

**User Story:** As a user, I want the assistant to capture my screen or a selected region, so that it can read the content currently visible on my display.

#### Acceptance Criteria

1. WHEN capture is triggered with no region specified, THE ScreenCapture SHALL return a PIL Image with dimensions matching the full monitor
2. WHEN capture is triggered with a Region specified, THE ScreenCapture SHALL return a PIL Image with width equal to Region.width and height equal to Region.height
3. THE ScreenCapture SHALL use `mss` as the primary capture backend and `pyautogui` as the fallback backend
4. IF the primary capture backend raises an exception, THEN THE ScreenCapture SHALL attempt capture using the fallback backend
5. IF both capture backends fail, THEN THE ScreenCapture SHALL raise a CaptureError
6. THE ScreenCapture SHALL support selecting a capture target by monitor index to enable multi-monitor setups
7. WHEN a Region is provided, THE ScreenCapture SHALL validate that Region.width and Region.height are both greater than zero before capturing

---

### Requirement 3: OCR Engine

**User Story:** As a developer, I want the system to extract text from captured images, so that the content visible on screen can be passed to the language model.

#### Acceptance Criteria

1. WHEN a PIL Image is provided, THE OCREngine SHALL extract text using the configured OCR backend
2. WHEN extracting text, THE OCREngine SHALL only include results whose confidence score meets or exceeds the configured confidence threshold
3. WHEN extraction completes, THE OCREngine SHALL return the extracted text as a string without modifying the input image
4. THE OCREngine SHALL support EasyOCR as the default backend, PaddleOCR as a high-accuracy alternative, and Tesseract as a fallback backend
5. IF the configured primary OCR backend is unavailable, THEN THE OCREngine SHALL fall back to Tesseract
6. IF all OCR backends are unavailable, THEN THE OCREngine SHALL set the OverlayUI status to ERROR and display "OCR unavailable"
7. WHEN no text is detected above the confidence threshold, THE OCREngine SHALL return an empty string

---

### Requirement 4: Text Processor

**User Story:** As a developer, I want raw OCR output to be cleaned and classified before reaching the LLM, so that the model receives well-formed, deduplicated input.

#### Acceptance Criteria

1. WHEN processing raw text, THE TextProcessor SHALL normalize whitespace by collapsing multiple consecutive spaces into a single space and multiple consecutive newlines into a single newline
2. WHEN processing raw text, THE TextProcessor SHALL remove duplicate lines, preserving only the first occurrence of each unique line using case-insensitive comparison
3. WHEN processing raw text, THE TextProcessor SHALL filter out lines containing two or fewer characters
4. WHEN processing raw text, THE TextProcessor SHALL classify the content and return one of the TextClass values: QUESTION, CODE, PARAGRAPH, MIXED, or EMPTY
5. WHEN the input text is empty or contains only whitespace characters, THE TextProcessor SHALL return a ProcessedText with is_empty set to True and content set to an empty string
6. THE TextProcessor deduplication SHALL be idempotent: processing the output of a previous processing call SHALL produce the same content as the previous output

---

### Requirement 5: State Manager

**User Story:** As a developer, I want the system to detect whether screen content has changed since the last capture, so that redundant LLM calls are avoided when the screen has not changed.

#### Acceptance Criteria

1. WHEN has_changed is called with text that matches the cached text, THE StateManager SHALL return False
2. WHEN has_changed is called with text that differs from the cached text, THE StateManager SHALL return True
3. WHEN the cache is empty, THE StateManager SHALL return True from has_changed for any input text
4. WHEN update is called with a text value, THE StateManager SHALL store that value such that get_cached returns it
5. THE StateManager SHALL use SHA-256 hashing of the UTF-8 encoded text for change comparison
6. THE StateManager cache access SHALL be thread-safe

---

### Requirement 6: LLM Engine

**User Story:** As a user, I want the assistant to send captured screen text to a language model and receive a response, so that I can get AI-powered assistance based on what is currently on my screen.

#### Acceptance Criteria

1. WHEN a prompt is submitted, THE LLMEngine SHALL return a non-empty response string from the configured backend
2. WHEN query_stream is called, THE LLMEngine SHALL yield response tokens such that concatenating all yielded tokens produces the complete response
3. THE LLMEngine SHALL support Ollama as the local backend and OpenAI-compatible APIs as the remote backend
4. THE LLMEngine SHALL build the prompt by substituting the processed text into the configured prompt template at the `{text}` placeholder
5. IF the LLM backend is unreachable, THEN THE LLMEngine SHALL retry the request using exponential backoff starting at a 1-second delay
6. THE LLMEngine retry attempt count SHALL never exceed the value of retry_attempts in LLMConfig
7. IF all retry attempts are exhausted, THEN THE LLMEngine SHALL raise LLMUnavailableError
8. THE LLMEngine SHALL expose a health_check method that returns True when the backend is reachable and False otherwise

---

### Requirement 7: Overlay UI

**User Story:** As a user, I want to see the AI response in a floating window that stays on top of all other windows, so that I can read the response without losing context of my current work.

#### Acceptance Criteria

1. WHILE the application is running, THE OverlayUI SHALL maintain the always-on-top window flag so that the overlay remains above all other windows
2. WHEN set_text or append_text is called from a background thread, THE OverlayUI SHALL route the update through Qt signals and slots to ensure thread safety
3. WHEN the pipeline completes, THE OverlayUI SHALL display either the LLM response or a descriptive status message
4. WHEN set_status is called, THE OverlayUI SHALL update the displayed StatusIndicator to reflect the new pipeline state
5. THE OverlayUI SHALL be frameless and draggable by mouse press on the title bar area
6. THE OverlayUI SHALL display a status indicator that transitions through IDLE, CAPTURING, PROCESSING, and ERROR states as the pipeline progresses

---

### Requirement 8: Config Manager

**User Story:** As a developer, I want application settings to be loaded from a YAML configuration file, so that the system can be configured without modifying source code.

#### Acceptance Criteria

1. WHEN load is called, THE ConfigManager SHALL parse `config.yaml` and return a valid AppConfig object
2. WHEN save is called with an AppConfig, THE ConfigManager SHALL write the configuration to `config.yaml` such that a subsequent load returns an equivalent AppConfig
3. IF `config.yaml` is missing or malformed, THEN THE ConfigManager SHALL raise a descriptive error identifying the problem
4. THE ConfigManager SHALL apply default values for any optional configuration fields not present in the file

---

### Requirement 9: Pipeline Orchestration

**User Story:** As a user, I want the system to coordinate all components in the correct sequence when I press the capture hotkey, so that I receive a relevant AI response with minimal latency.

#### Acceptance Criteria

1. WHEN the capture hotkey is pressed, THE System SHALL execute the pipeline in the following order: screen capture, OCR extraction, text processing, change detection, LLM query, overlay display
2. WHEN the pipeline produces empty OCR output, THE System SHALL short-circuit and not invoke the LLMEngine
3. WHEN the pipeline detects no change in screen content, THE System SHALL short-circuit and not invoke the LLMEngine
4. WHEN the pipeline completes successfully, THE System SHALL update the StateManager cache with the latest processed text
5. WHEN the pipeline short-circuits due to empty text, THE System SHALL display "No readable text found" in the OverlayUI
6. WHEN the pipeline short-circuits due to unchanged text, THE System SHALL display "No change detected" in the OverlayUI
7. THE System SHALL set the OverlayUI status to CAPTURING before screen capture, PROCESSING before LLM query, and IDLE after pipeline completion
8. THE System end-to-end latency from hotkey press to first token displayed SHALL be under 4 seconds under normal operating conditions

---

### Requirement 10: Region Selection

**User Story:** As a user, I want to define a specific screen region for capture, so that the assistant focuses only on the relevant portion of my screen.

#### Acceptance Criteria

1. WHEN the region select hotkey is pressed, THE System SHALL display a transparent overlay that allows the user to drag-select a screen region
2. WHEN the user completes a drag selection, THE System SHALL pass the selected Region to ScreenCapture via set_region
3. WHEN a region is set, THE System SHALL use that region for all subsequent capture operations until a new region is selected
4. WHEN a region is set, THE System SHALL confirm the selection to the user

---

### Requirement 11: Security and Privacy

**User Story:** As a user, I want my screen data to remain private and never leave my machine without my explicit consent, so that sensitive information visible on my screen is not exposed.

#### Acceptance Criteria

1. WHILE operating in local mode, THE System SHALL not transmit screen capture data, OCR text, or prompts to any external network endpoint
2. WHERE API mode is configured, THE System SHALL display a one-time warning dialog to the user before the first API call is made
3. WHERE API mode is configured, THE System SHALL store the API key using the OS keychain via the `keyring` library and SHALL NOT store it in plaintext in `config.yaml`
4. WHILE save_debug_images is set to False, THE System SHALL not write screenshot data to disk
5. THE System SHALL perform read-only screen observation and SHALL NOT inject keyboard or mouse input into other applications

---

### Requirement 12: Error Handling and Recovery

**User Story:** As a user, I want the assistant to recover gracefully from component failures, so that a single error does not crash the application or leave it in an unresponsive state.

#### Acceptance Criteria

1. IF the LLMEngine raises LLMUnavailableError, THEN THE System SHALL display "LLM unavailable — check Ollama or API config" in the OverlayUI and set status to ERROR
2. IF the ScreenCapture raises CaptureError, THEN THE System SHALL log the error, skip the current pipeline run, and display "Capture failed" in the OverlayUI
3. IF the OCREngine returns an empty string, THEN THE System SHALL display "No readable text found" in the OverlayUI without invoking the LLMEngine
4. WHEN any pipeline stage raises an unhandled exception, THE System SHALL set the OverlayUI status to ERROR and log the exception with a stack trace
5. WHEN the OverlayUI status is set to ERROR, THE System SHALL return to IDLE status after the next successful pipeline run

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Capture dimensions match requested region

*For any* valid Region with positive width and height, the PIL Image returned by ScreenCapture.capture(region) shall have width equal to region.width and height equal to region.height.

**Validates: Requirements 2.2**

### Property 2: OCR confidence filtering

*For any* image and any set of OCR results, the text returned by OCREngine.extract shall contain only text from results whose confidence score is greater than or equal to the configured confidence threshold.

**Validates: Requirements 3.2**

### Property 3: OCR does not mutate input image

*For any* PIL Image, calling OCREngine.extract shall not modify the image's pixel data, size, or mode.

**Validates: Requirements 3.3**

### Property 4: TextProcessor deduplication is idempotent

*For any* raw text string, processing the output of TextProcessor.process shall produce the same content field as the original processing call: process(process(raw).content).content == process(raw).content.

**Validates: Requirements 4.6**

### Property 5: Whitespace-only input yields empty ProcessedText

*For any* string composed entirely of whitespace characters (including the empty string), TextProcessor.process shall return a ProcessedText with is_empty set to True and content equal to the empty string.

**Validates: Requirements 4.5**

### Property 6: StateManager change detection correctness

*For any* non-empty text string, after calling StateManager.update(text), calling StateManager.has_changed(text) shall return False; and for any different text string, has_changed shall return True.

**Validates: Requirements 5.1, 5.2**

### Property 7: StateManager cache round-trip

*For any* text string, after calling StateManager.update(text), StateManager.get_cached() shall return that same text string.

**Validates: Requirements 5.4**

### Property 8: Streaming tokens reconstruct full response

*For any* prompt submitted to LLMEngine.query_stream, concatenating all yielded token strings shall produce a string equal to the response returned by LLMEngine.query for the same prompt.

**Validates: Requirements 6.2**

### Property 9: Retry count is bounded

*For any* configured retry_attempts value, the number of LLM backend call attempts made by LLMEngine during a single query shall never exceed retry_attempts.

**Validates: Requirements 6.6**

### Property 10: Empty OCR output never reaches LLMEngine

*For any* pipeline run where TextProcessor returns a ProcessedText with is_empty equal to True, the LLMEngine.query or LLMEngine.query_stream method shall not be called.

**Validates: Requirements 9.2**

### Property 11: Unchanged text never triggers LLMEngine

*For any* pipeline run where StateManager.has_changed returns False, the LLMEngine.query or LLMEngine.query_stream method shall not be called.

**Validates: Requirements 9.3**

### Property 12: State cache reflects last processed text

*For any* successful pipeline run, after the pipeline completes, StateManager.get_cached() shall return the content field of the ProcessedText that was passed to the LLMEngine in that run.

**Validates: Requirements 9.4**

### Property 13: OverlayUI always-on-top flag is never cleared

*For any* sequence of pipeline runs and UI updates during an active session, the OverlayUI window shall retain the Qt.WindowStaysOnTopHint flag throughout.

**Validates: Requirements 7.1**

### Property 14: Screenshot data not written to disk in default mode

*For any* pipeline run where save_debug_images is False, no image file shall be created or modified on the filesystem as a result of the capture or OCR steps.

**Validates: Requirements 11.4**

### Property 15: ConfigManager save/load round-trip

*For any* valid AppConfig object, saving it with ConfigManager.save and then loading it with ConfigManager.load shall produce an AppConfig that is equivalent to the original.

**Validates: Requirements 8.2**
