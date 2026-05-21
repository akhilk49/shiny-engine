# Agentic AI Assistant

A context-aware AI agent that understands what you're working on and assists intelligently — without you having to copy, paste, or switch context.

---

## Capabilities

- **Context understanding** — reads and reasons about context
- **Code analysis** — explains what code does or identifies bugs
- **Intelligent responses** — adapts response style to content type
- **Flexible AI backends** — HuggingFace Inference API, Ollama (local), or OpenAI
- **Privacy-first** — fully local operation supported; API keys stored in OS keychain
- **Fully configurable** — hotkeys, model, OCR backend, UI appearance all in `config.yaml`

---

## Tech Stack

Python · PyQt5 · Tesseract OCR · HuggingFace Inference API · mss · keyboard · PyYAML · keyring

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Install Tesseract OCR

Download and install from: https://github.com/UB-Mannheim/tesseract/wiki

Default install path: `C:\Program Files\Tesseract-OCR\`

### 3. Configure your AI backend

**Option A — HuggingFace (recommended, no local GPU needed)**

Get a free token at https://huggingface.co/settings/tokens, then run:

```bash
python -c "
import sys; sys.path.insert(0, '.')
from src.llm_engine.llm_engine import LLMEngine
LLMEngine.store_api_key('hf_your_token_here', 'hf_api_key')
"
```

**Option B — Ollama (fully local)**

```bash
ollama serve
ollama pull phi3:mini
```

Then set `backend: "ollama"` and `model: "phi3:mini"` in `config.yaml`.

### 4. Run

```bash
python main.py
```

---

## Configuration

ocr:
  backend: "tesseract"
  confidence_threshold: 0.3

llm:
  backend: "huggingface"
  model: "Qwen/Qwen2.5-72B-Instruct"
  max_tokens: 350
  temperature: 0.1

ui:
  width: 340
  height: 200
  opacity: 0.95
  theme: "dark"
```

---

## Project Structure

```
├── main.py                    # Entry point
├── config.yaml                # Configuration
├── requirements.txt
└── src/
    ├── models.py              # Dataclasses, enums, exceptions
    ├── config_manager/        # YAML config loader
    ├── screen_capture/        # Screen region capture
    ├── ocr_engine/            # Text extraction (Tesseract / EasyOCR)
    ├── text_processor/        # Clean, classify, structure
    ├── state_manager/         # Change detection
    ├── llm_engine/            # HuggingFace / Ollama / OpenAI
    ├── overlay_ui/            # Floating overlay (PyQt5)
    ├── hotkey_listener/       # Global hotkeys
    ├── region_selector/       # Drag-select UI
    └── controller/            # Agent pipeline orchestration
```

---

## Privacy & Security

- **Local mode**: nothing leaves your machine
- **API mode**: one-time consent prompt before first remote call; API keys stored in OS keychain, never in config files
- **Read-only**: the agent only observes — no keyboard or mouse injection

---

## Requirements

- Windows 10 (build 19041+) or Windows 11
- Python 3.10+
- Tesseract OCR 5.x
- 4 GB RAM minimum
