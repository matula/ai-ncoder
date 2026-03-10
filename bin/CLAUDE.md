# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-ncoder — a desktop app that translates natural language prompts into executable `ffmpeg` commands using a local Small Language Model (SLM). Runs entirely offline with no external API dependencies. 
Target deliverable is a single bundled executable via PyInstaller.

### Look at PLAN.md for the phased plan. When a phase is complete, mark it as complete.

## Tech Stack

- **UI:** PySide6 (Qt for Python) — cross-platform drag-and-drop support
- **AI Engine:** llama-cpp-python — runs GGUF models on CPU with JSON grammar constraints
- **Language Model:** Qwen 2.5 Coder 0.5B (Q8_0 GGUF, ~800MB)
- **Media:** Bundled static ffmpeg & ffprobe binaries
- **Packaging:** PyInstaller (single executable)
- **Python:** 3.14+ (venv at `.venv/`)

## Project Structure

```
AI-ncoder/
├── models/          # Qwen2.5-Coder-0.5B-Instruct Q8_0 GGUF model file
├── bin/             # Static ffmpeg and ffprobe binaries
├── main.py          # Application entry point (UI + logic)
└── requirements.txt # PySide6==6.10.2, llama-cpp-python==0.3.16
```

## Commands

```bash
# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

## Architecture

The application follows a pipeline architecture with four layers:

1. **UI Layer (PySide6):** Handles drag-and-drop file ingestion and text prompt input. Assigns generic tokens (`<INPUT_1>`) to files so the LLM never sees raw file paths.

2. **AI Pipeline Layer:** Runs `ffprobe` on input files to extract codec/format metadata, injects that context into the prompt alongside file tokens and the user's natural language request, then calls the Qwen model via llama-cpp-python with a strict JSON grammar constraint.

3. **Reassembly Layer:** Parses the model's constrained JSON output, replaces `<INPUT_1>`/`<OUTPUT_1>` tokens with real sanitized file paths, and generates safe output paths (with auto-rename on conflicts).

4. **Execution Layer:** Runs the ffmpeg command as a subprocess, pipes output to a progress bar, and notifies on completion.

### AI Guardrails (Critical Design Decisions)

These constraints prevent the tiny 0.5B model from hallucinating:

- **File path decoupling:** LLM only sees generic tokens, never real paths
- **Context injection:** ffprobe metadata is silently prepended to every prompt
- **Constrained JSON output:** llama.cpp grammar forces output into `{"command": "...", "is_ambiguous": bool, "clarification_question": "..."}`
- **Few-shot system prompt:** 3-5 hardcoded input→output examples prime the model

### Key Conventions

- ffmpeg/ffprobe binaries are referenced from `bin/`, not system PATH
- The model file is loaded from `models/`
- File tokens use the pattern `<INPUT_N>` and `<OUTPUT_N>` where N is an integer
- Output file conflicts are resolved by auto-renaming (e.g., `output(1).mp3`)

## Development Phases

The project follows three phases as defined in the README:
1. **Phase 1:** Headless AI + ffmpeg integration (no UI) — script takes file path + text → outputs converted file
2. **Phase 2:** PySide6 UI with drag-and-drop, text input, advanced view, progress bar
3. **Phase 3:** PyInstaller packaging, edge case handling
