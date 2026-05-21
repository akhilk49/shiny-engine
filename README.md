# Agentic AI Assistant

A local, privacy-first agentic AI assistant for Windows that runs continuously in the background. It autonomously captures any region of your screen, extracts text via OCR, and delivers instant AI-powered answers through a minimal floating overlay — invisible to screen sharing tools.

---

## What it does

Press a hotkey → draw a region → get an answer. That's it.

The assistant reads whatever is on your screen — questions, code, paragraphs — and responds intelligently through a compact floating popup that only you can see.

---

## Features

- **Agentic pipeline** — hotkey → capture → OCR → LLM → overlay, fully automated
- **Region selection** — drag to select exactly what you want analyzed
- **Always-on-top overlay** — minimal floating UI, invisible to screen capture and screen sharing
- **MCQ support** — identifies questions and options, picks the correct answer
- **Flexible LLM backends** — HuggingFace Inference API, Ollama (local), or OpenAI
- **Privacy-first** — all processing can run fully local; API keys stored in OS keychain
- **Configurable** — hotkeys, model, OCR backend, UI size/position all in `config.yaml`

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

### 3. Configure your LLM

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
ollama pull phi3:mini   # or any model that fits your RAM
```

Then set `backend: "ollama"` and `model: "phi3:mini"` in `config.yaml`.

### 4. Run

```bash
python main.py
```

---

## Hotkeys

| Hotkey | Action |
|--------|--------|
| `Ctrl+Alt+A` | Capture screen and get AI response |
| `Ctrl+Alt+R` | Select a screen region (auto-captures after selection) |
| `Ctrl+Alt+H` | Toggle overlay visibility |
| `Ctrl+Alt+Q` | Quit |

All hotkeys are configurable in `config.yaml`.

---

## Configuration

Edit `config.yaml` to customize:

```yaml
hotkeys:
  capture_trigger: "ctrl+alt+a"
  region_select: "ctrl+alt+r"

ocr:
  backend: "tesseract"          # tesseract | easyocr
  confidence_threshold: 0.3

llm:
  backend: "huggingface"        # huggingface | ollama | openai
  model: "Qwen/Qwen2.5-72B-Instruct"
  max_tokens: 350
  temperature: 0.1

ui:
  width: 340
  height: 200
  opacity: 0.95
  theme: "dark"                 # dark | light
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
    ├── screen_capture/        # mss + pyautogui capture
    ├── ocr_engine/            # Tesseract / EasyOCR
    ├── text_processor/        # Clean, deduplicate, classify
    ├── state_manager/         # Change detection cache
    ├── llm_engine/            # HuggingFace / Ollama / OpenAI
    ├── overlay_ui/            # PyQt5 floating overlay
    ├── hotkey_listener/       # Global hotkeys
    ├── region_selector/       # Drag-select overlay
    └── controller/            # Pipeline orchestration
```

---

## Privacy & Security

- **Local mode**: nothing leaves your machine
- **API mode**: one-time warning before first remote call; API keys stored in OS keychain, never in config files
- **Screen capture exclusion**: overlay is hidden from screen recording tools (OBS, Zoom, Teams, etc.) via Windows `SetWindowDisplayAffinity`
- **Read-only**: the assistant only observes your screen — no keyboard/mouse injection

---

## Requirements

- Windows 10 (build 19041+) or Windows 11
- Python 3.10+
- Tesseract OCR 5.x
- 4 GB RAM minimum (8 GB recommended for local models)
