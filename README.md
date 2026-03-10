# AI-ncoder

A desktop app that converts media files using plain English. Powered by a local SLM (Small Language Model) — runs entirely offline, no API keys or internet required.

<!-- TODO: Add a screenshot here -->
<!-- ![AI-ncoder screenshot](screenshot.png) -->

## Features

- **Natural language prompts** — type "extract the audio as mp3" instead of memorizing ffmpeg flags
- **Drag and drop** — drop files onto the window to get started
- **Completely offline** — the AI model runs locally on your CPU
- **Batch processing** — drop multiple files and convert them all with one prompt
- **Progress tracking** — real-time progress bar during conversion
- **Command transparency** — toggle "Show Command" to see the exact ffmpeg command being run
- **Cross-platform** — built with Qt (PySide6), works on macOS, Windows, and Linux

## Quick Start

### Prerequisites

- Python 3.12+ ([python.org](https://www.python.org/downloads/))
- Git

### 1. Clone and install

```bash
git clone https://github.com/matula/AI-ncoder.git
cd AI-ncoder
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows
pip install -r requirements.txt
```

### 2. Download the AI model

Download **Qwen2.5-Coder-0.5B-Instruct** (Q8_0 GGUF format, ~506 MB) and place it in `models/`:

```bash
mkdir -p models
# Download from Hugging Face:
# https://huggingface.co/Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF
# Get the file: qwen2.5-coder-0.5b-instruct-q8_0.gguf
# Place it at: models/qwen2.5-coder-0.5b-instruct-q8_0.gguf
```

### 3. Download ffmpeg and ffprobe

Download static builds for your platform and place them in `bin/`:

| Platform | Download |
|----------|----------|
| **macOS** | [evermeet.cx/ffmpeg](https://evermeet.cx/ffmpeg/) (download both ffmpeg and ffprobe) |
| **Linux** | [johnvansickle.com/ffmpeg](https://johnvansickle.com/ffmpeg/) (static builds) |
| **Windows** | [gyan.dev/ffmpeg](https://www.gyan.dev/ffmpeg/builds/) (get the "essentials" build) |

```bash
mkdir -p bin
# Place the binaries in bin/
# macOS/Linux: make them executable
chmod +x bin/ffmpeg bin/ffprobe
```

On Windows, the files should be named `ffmpeg.exe` and `ffprobe.exe`.

### 4. Run

```bash
python main.py
```

## Usage

### GUI Mode (default)

1. Launch with `python main.py`
2. Drag media files onto the drop zone
3. Type what you want in plain English
4. Click **Convert**

**Example prompts:**
- "Extract the audio as a high-quality mp3"
- "Convert to mp4"
- "Resize to 720p"
- "Make a 192kbps mp3 at 44.1khz stereo"
- "Compress this video to reduce file size"
- "Start at 30 seconds and cut to 60 seconds"

### CLI Mode

```bash
python main.py --file input.mov --prompt "Extract audio as mp3"
python main.py --file video1.mp4 video2.mkv --prompt "Convert to mp4"
```

## Building the Executable

The project includes a PyInstaller spec file for building a standalone app.

```bash
pip install pyinstaller
pyinstaller AI-ncoder.spec
```

### macOS

The spec file produces a `.app` bundle at `dist/AI-ncoder.app`. If macOS blocks it:

```bash
xattr -cr dist/AI-ncoder.app
```

### Windows

The current `AI-ncoder.spec` is configured for macOS. To build on Windows:

1. Use `ffmpeg.exe` and `ffprobe.exe` in `bin/`
2. In `AI-ncoder.spec`:
   - Change the `binaries` paths to use `.exe` extensions
   - Change `llama_binaries` glob from `*.dylib` to `*.dll`
   - Remove the `BUNDLE` block at the bottom (that's macOS-only)
3. Run `pyinstaller AI-ncoder.spec`
4. Output: `dist/AI-ncoder/AI-ncoder.exe`

### Linux

1. Use static ffmpeg/ffprobe binaries in `bin/`
2. In `AI-ncoder.spec`:
   - Change `llama_binaries` glob from `*.dylib` to `*.so`
   - Remove the `BUNDLE` block at the bottom (that's macOS-only)
3. Run `pyinstaller AI-ncoder.spec`
4. Output: `dist/AI-ncoder/AI-ncoder`

## How It Works

The app uses a 4-layer pipeline:

1. **UI Layer** — PySide6 handles drag-and-drop and text input. Files are assigned generic tokens (`<INPUT_1>`) so the AI never sees real file paths.

2. **AI Layer** — ffprobe extracts media metadata (codec, resolution, sample rate). This metadata plus the user's prompt is sent to a local Qwen 0.5B model, constrained to output valid JSON with an ffmpeg command.

3. **Reassembly Layer** — The AI's output tokens are replaced with real, shell-safe file paths. A sanitizer fixes common small-model mistakes (wrong codecs, malformed flags).

4. **Execution Layer** — ffmpeg runs as a subprocess with progress piped back to the UI.

## Project Structure

```
AI-ncoder/
├── main.py              # Entry point (CLI + GUI routing)
├── ui.py                # PySide6 GUI (dark theme, drag-and-drop)
├── ai_engine.py         # LLM inference with constrained JSON output
├── command_runner.py    # Token replacement, ffmpeg execution, progress
├── media_utils.py       # ffprobe wrapper, metadata extraction
├── paths.py             # Path resolution (dev vs. bundled mode)
├── requirements.txt     # PySide6, llama-cpp-python
├── AI-ncoder.spec       # PyInstaller build configuration
├── hooks/               # PyInstaller runtime hooks
├── models/              # AI model file (.gitignored)
├── bin/                 # ffmpeg + ffprobe binaries (.gitignored)
└── tests/               # Automated test suite
```

## System Requirements

- **RAM:** 2-4 GB free (for AI model inference)
- **Disk:** ~700 MB for the model + binaries
- **CPU:** Any modern x86_64 or ARM64 processor
- **OS:** macOS 12+, Windows 10+, or Linux (with glibc 2.31+)

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
