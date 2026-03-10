# PLAN.md — AI-ncoder

Full implementation plan broken into distinct, testable phases. Each phase produces a working milestone that can be verified before moving on.

### Test Files (do not overwrite)

| File | Details |
|------|---------|
| `test-files/testvidmov.mov`          | 5s, 1920x1080, h264 video + aac audio (48kHz stereo), ~10MB |
| `test-files/testwave.wav`            | 9s, pcm_s16le audio (8kHz mono), ~156KB                     |
| `test-files/my video (1).mov`        | Copy of testvidmov.mov — tests spaces and parentheses       |
| `test-files/tëst wäve [final].wav`   | Copy of testwave.wav — tests unicode and brackets            |

---

## Phase 0: Project Scaffolding & Asset Acquisition ✅ COMPLETE

**Goal:** A fully configured dev environment with all external assets in place.

### Steps

1. Create the directory structure:
   ```
   AI-ncoder/
   ├── bin/              # ffmpeg + ffprobe static binaries
   ├── models/           # GGUF model file
   ├── main.py           # Entry point (will grow through phases)
   └── requirements.txt
   ```

2. Create `requirements.txt`:
   ```
   PySide6==6.10.2
   llama-cpp-python==0.3.16
   ```

3. Install dependencies into the existing `.venv`:
   ```bash
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

4. Download and place external assets:
   - **Model:** Download `Qwen2.5-Coder-0.5B-Instruct-Q8_0.gguf` from Hugging Face → `models/`
   - **ffmpeg/ffprobe:** Download latest macOS static builds → `bin/`, make executable with `chmod +x`

5. Initialize git repository and add `.gitignore` (exclude `.venv/`, `models/*.gguf`, `bin/ffmpeg`, `bin/ffprobe`, `.idea/`, `__pycache__/`, `*.spec`, `build/`, `dist/`).

### How to Verify

- `python -c "from llama_cpp import Llama; print('OK')"` succeeds
- `python -c "from PySide6.QtWidgets import QApplication; print('OK')"` succeeds
- `./bin/ffmpeg -version` prints version info
- `./bin/ffprobe -version` prints version info
- `ls models/*.gguf` shows the model file

---

## Phase 1: ffprobe Wrapper ✅ COMPLETE

**Goal:** A Python module that runs the bundled `ffprobe` on any media file and returns structured metadata.

### Steps

1. Create `media_utils.py` with a function `probe_file(file_path: str) -> dict`:
   - Resolves the path to `bin/ffprobe` relative to the project root
   - Runs: `ffprobe -v quiet -print_format json -show_format -show_streams <file>`
   - Parses the JSON output and returns it as a Python dict
   - Raises a clear exception on failure (file not found, invalid media, ffprobe error)

2. Create a helper `get_media_summary(probe_data: dict) -> str`:
   - Extracts key info from the probe output: container format, duration, video codec + resolution (if present), audio codec + sample rate + channels (if present)
   - Returns a concise human-readable summary string (this is what gets injected into the LLM prompt)

### How to Verify

- Run against the video test file:
  ```bash
  python -c "from media_utils import probe_file, get_media_summary; d = probe_file('test-files/testvidmov.mov'); print(get_media_summary(d))"
  ```
  Expected: `Format: QuickTime / MOV, Duration: 00:00:05, Audio: aac 48000Hz 2ch, Video: h264 1920x1080`
- Run against the audio test file:
  ```bash
  python -c "from media_utils import probe_file, get_media_summary; d = probe_file('test-files/testwave.wav'); print(get_media_summary(d))"
  ```
  Expected: `Format: WAV / WAVE (Waveform Audio), Duration: 00:00:09, Audio: pcm_s16le 8000Hz 1ch`
- Test with a non-media file (e.g., `requirements.txt`) and confirm a clear error

---

## Phase 2: LLM Integration & Prompt Engineering ✅ COMPLETE

**Goal:** A Python module that loads the Qwen model, accepts a media summary + user prompt, and returns a validated JSON response with an ffmpeg command.

### Steps

1. Create `ai_engine.py` with class `AIEngine`:
   - `__init__(self, model_path: str)`: Loads the GGUF model via `llama-cpp-python`. Configures model parameters (context size, temperature, etc.).
   - `generate_command(self, media_summary: str, input_token: str, user_prompt: str) -> dict`: Builds the full prompt, calls the model with JSON grammar constraint, parses and returns the result.

2. Build the **system prompt** with few-shot examples:
   - Define a system message explaining the model's role: "You are an ffmpeg command generator. Given media file metadata and a user request, output the correct ffmpeg command using the provided input/output tokens."
   - Include 3–5 few-shot examples covering common scenarios:
     - Extract audio from video as MP3
     - Convert video to different format (e.g., MKV → MP4)
     - Resize/scale a video
     - Compress a video to reduce file size
     - An ambiguous request that should set `is_ambiguous: true`

3. Define the **JSON grammar/schema** for constrained output:
   ```json
   {
     "command": "string — the ffmpeg command using <INPUT_N> and <OUTPUT_N> tokens",
     "is_ambiguous": "boolean — true if the request cannot be fulfilled",
     "clarification_question": "string — question to ask user if ambiguous, empty string otherwise"
   }
   ```

4. Implement the **token convention**:
   - Input files are referenced as `<INPUT_1>`, `<INPUT_2>`, etc.
   - Output files are referenced as `<OUTPUT_1>`, `<OUTPUT_2>`, etc.
   - The model receives the token along with its file extension (e.g., `<INPUT_1>.mkv`)

### How to Verify

- Test with the video file's real metadata:
  ```bash
  python -c "
  from ai_engine import AIEngine
  from media_utils import probe_file, get_media_summary
  engine = AIEngine('models/qwen2.5-coder-0.5b-instruct-q8_0.gguf')
  summary = get_media_summary(probe_file('test-files/testvidmov.mov'))
  result = engine.generate_command(
      media_summary=summary,
      input_token='<INPUT_1>.mov',
      user_prompt='Extract the audio as a high-quality mp3'
  )
  print(result)
  "
  ```
- Test with the audio file:
  ```bash
  python -c "
  from ai_engine import AIEngine
  from media_utils import probe_file, get_media_summary
  engine = AIEngine('models/qwen2.5-coder-0.5b-instruct-q8_0.gguf')
  summary = get_media_summary(probe_file('test-files/testwave.wav'))
  result = engine.generate_command(
      media_summary=summary,
      input_token='<INPUT_1>.wav',
      user_prompt='Convert to mp3'
  )
  print(result)
  "
  ```
- Confirm the output is valid JSON with the correct schema
- Confirm the command uses `<INPUT_1>` and `<OUTPUT_1>` tokens (not real paths)
- Confirm the command is a plausible ffmpeg invocation
- Test an ambiguous prompt (e.g., "make it better") and confirm `is_ambiguous` is true

---

## Phase 3: Command Reassembly & ffmpeg Execution ✅ COMPLETE

**Goal:** A module that takes the AI's JSON output, replaces tokens with real paths, and executes the ffmpeg command with progress reporting.

### Steps

1. Create `command_runner.py` with:

   **`reassemble_command(ai_output: dict, input_files: dict, output_dir: str) -> str`**
   - Takes the AI's JSON output and a mapping of tokens to real file paths (e.g., `{"<INPUT_1>": "/path/to/video.mkv"}`)
   - Generates a safe output file path in `output_dir`, using the output token's extension from the command
   - Handles file overwrite conflicts by auto-renaming: `output.mp3` → `output(1).mp3` → `output(2).mp3`
   - Replaces all tokens in the command string with the real, properly quoted paths
   - Returns the fully resolved command string

   **`run_ffmpeg(command: str, ffmpeg_path: str, progress_callback=None) -> bool`**
   - Resolves the `ffmpeg` token in the command to the actual `bin/ffmpeg` path
   - Executes the command as a subprocess
   - Parses ffmpeg's stderr output to extract progress (time-based, compared against known duration)
   - Calls `progress_callback(percent: float)` if provided
   - Returns True on success, raises on failure with stderr details

2. Create the **end-to-end headless pipeline** function in `main.py`:

   **`process_file(file_path: str, user_prompt: str) -> str`**
   - Calls `probe_file()` → `get_media_summary()`
   - Assigns `<INPUT_1>` token to the file
   - Calls `engine.generate_command()`
   - If `is_ambiguous`, prints the clarification question and exits
   - Calls `reassemble_command()` then `run_ffmpeg()`
   - Returns the output file path

### How to Verify

- Run the full headless pipeline with the video file:
  ```bash
  python main.py --file test-files/testvidmov.mov --prompt "Extract the audio as mp3"
  ```
- Run with the audio file:
  ```bash
  python main.py --file test-files/testwave.wav --prompt "Convert to mp3"
  ```
- Confirm the output files are created and playable
- Test file overwrite: run the same command twice, confirm the second output is auto-renamed
- Test with tricky filenames (spaces, parens, unicode, brackets):
  ```bash
  python main.py --file "test-files/my video (1).mov" --prompt "Extract the audio as mp3"
  python main.py --file "test-files/tëst wäve [final].wav" --prompt "Convert to mp3"
  ```
- Test with a prompt that triggers `is_ambiguous: true` and confirm the clarification question is printed
- Test progress callback prints percentage updates

---

## Phase 4: PySide6 UI — Core Window & Drag-and-Drop ✅ COMPLETE

**Goal:** A functional GUI window with drag-and-drop file ingestion and a text input field, connected to the Phase 3 backend.

### Steps

1. Create `ui.py` (or expand `main.py`) with the PySide6 application:

   **Main Window layout:**
   - A large **drop zone** area with a visual indicator (dashed border, icon, "Drag files here" label)
   - Accepts file drops via Qt's drag-and-drop API (`dragEnterEvent`, `dropEvent`)
   - Displays the dropped file name(s) after drop
   - A **text input field** (QLineEdit or QTextEdit) for the user's natural language prompt
   - A **"Convert" / "Go" button** to trigger processing

2. Wire up the drop zone:
   - On file drop: store the file path(s), assign `<INPUT_N>` tokens, run `ffprobe` in a background thread (QThread or QRunnable) so the UI doesn't freeze
   - Display file info (name, size, format summary) in the UI after probe completes

3. Wire up the convert button:
   - On click: take the user prompt text, call the full pipeline from Phase 3 in a **background thread**
   - Disable the button during processing to prevent double-submission

4. Handle the `is_ambiguous` case in the UI:
   - If the AI returns `is_ambiguous: true`, display the `clarification_question` in a dialog or inline message instead of running ffmpeg

### How to Verify

- Launch the app: `python main.py`
- Drag `test-files/testvidmov.mov` onto the window — file name and metadata appear
- Type a prompt and click Convert — the output file is created
- Drag `test-files/testwave.wav` and convert — audio conversion works
- Try an ambiguous prompt — clarification question is displayed
- Verify the UI does not freeze during processing (interact with the window while conversion runs)

---

## Phase 5: PySide6 UI — Progress, Advanced View & Polish ✅ COMPLETE

**Goal:** A polished user experience with progress feedback, command transparency, and completion notifications.

### Steps

1. **Progress bar:**
   - Add a QProgressBar to the main window
   - Connect it to the `progress_callback` from `run_ffmpeg()`
   - Show indeterminate progress (pulsing bar) during AI inference, determinate progress during ffmpeg execution

2. **Advanced View:**
   - Add a collapsible/toggleable section (QTextEdit, read-only) below the main UI
   - When the AI generates a command, display the final resolved ffmpeg command here
   - Toggle via a checkbox or button labeled "Show Command" / "Advanced View"

3. **Completion handling:**
   - On success: show a notification (status label or dialog) with the output file name
   - Add an "Open Folder" button that opens the output directory in the OS file manager (`QDesktopServices.openUrl()`)
   - Reset the UI to accept a new file/prompt

4. **Error handling in the UI:**
   - If ffmpeg fails: display stderr in the Advanced View and show a user-friendly error message
   - If model loading fails: show an error on startup pointing to the missing model path
   - If ffprobe fails on a dropped file: show "Unsupported file format" message

5. **UX polish:**
   - Keyboard shortcut: Enter/Return submits the prompt (same as clicking Convert)
   - Clear/reset button to start over
   - Window title, minimum size, and sensible defaults

### How to Verify

- Progress bar advances during conversion
- Advanced View shows the exact ffmpeg command being run
- "Open Folder" button opens the correct directory
- Error states display helpful messages (try dropping a non-media file like `requirements.txt`, try a prompt that fails)
- Enter key submits the prompt
- Full end-to-end workflow: drag `test-files/testvidmov.mov` → type prompt → see progress → get output → open folder

---

## Phase 6: Packaging with PyInstaller ✅ COMPLETE

**Goal:** A single distributable executable that bundles Python, PySide6, the model, and the ffmpeg binaries.

### Steps

1. Install PyInstaller: `pip install pyinstaller`

2. Create a PyInstaller `.spec` file (or use command-line flags) that bundles:
   - All Python source modules
   - The `models/` directory (the .gguf file)
   - The `bin/` directory (ffmpeg + ffprobe)
   - PySide6 and llama-cpp-python shared libraries

3. Update all file path resolution in the code to work in both development and bundled modes:
   - Use a helper that checks `sys._MEIPASS` (PyInstaller's temp directory) vs. the script's directory
   - Apply this to: model path, ffmpeg/ffprobe path

4. Build:
   ```bash
   pyinstaller AI-ncoder.spec
   ```

5. Test the built executable on a clean environment (no Python installed, no dev dependencies).

### How to Verify

- The built executable launches without errors
- Drag-and-drop, AI inference, and ffmpeg execution all work from the bundled app
- The executable size is reasonable (model is ~800MB, so expect ~900MB–1GB total)
- Test on a machine without Python or ffmpeg installed

---

## Module Dependency Map

```
main.py  (entry point — CLI in Phase 3, GUI from Phase 4+)
  ├── media_utils.py   (ffprobe wrapper, media summary)
  ├── ai_engine.py     (model loading, prompt building, JSON grammar, inference)
  └── command_runner.py (token reassembly, safe paths, ffmpeg execution, progress)

ui.py  (PySide6 window — Phase 4+, may be merged into main.py)
  └── uses all three modules above via main.py's pipeline function
```

---

## Phase Checkpoint Summary

| Phase | Milestone | Test Method |
|-------|-----------|-------------|
| 0 | Dev environment ready, all assets in place | Import checks, binary version commands |
| 1 | ffprobe wrapper returns structured metadata | CLI one-liner against a test file |
| 2 | LLM generates valid ffmpeg JSON from prompt | CLI one-liner with hardcoded summary |
| 3 | Full headless pipeline: file + prompt → output file | `python main.py --file X --prompt Y` |
| 4 | GUI with drag-and-drop triggers conversion | Launch app, drag file, type prompt |
| 5 | Polished UI with progress, command view, notifications | Full end-to-end UX walkthrough |
| 6 | Single bundled executable | Run on clean machine |
