import argparse
import os
import sys

from ai_engine import AIEngine
from command_runner import reassemble_command, run_ffmpeg
from media_utils import probe_file, get_media_summary
from paths import MODEL_PATH as _MODEL_PATH

# Lazy-loaded so the model isn't loaded unless needed
_engine: AIEngine | None = None


def get_engine() -> AIEngine:
    global _engine
    if _engine is None:
        print("Loading AI model...")
        _engine = AIEngine(_MODEL_PATH)
        print("Model loaded.")
    return _engine


def process_file(file_path: str, user_prompt: str, output_dir: str | None = None) -> str:
    """End-to-end headless pipeline: file + prompt -> output file.

    Returns the output file path on success, or raises on error.
    """
    file_path = os.path.abspath(file_path)

    if output_dir is None:
        output_dir = os.path.dirname(file_path)

    # 1. Probe the file
    probe_data = probe_file(file_path)
    summary = get_media_summary(probe_data)
    print(f"Media: {summary}")

    # 2. Assign input token
    ext = os.path.splitext(file_path)[1]  # e.g. ".mov"
    input_token = f"<INPUT_1>{ext}"
    input_files = {"<INPUT_1>": file_path}

    # 3. AI generates the command
    engine = get_engine()
    ai_output = engine.generate_command(summary, input_token, user_prompt)

    if ai_output["is_ambiguous"]:
        print(f"Clarification needed: {ai_output['clarification_question']}")
        return ""

    print(f"AI command: {ai_output['command']}")

    # 4. Reassemble with real paths
    resolved_cmd, output_path = reassemble_command(ai_output, input_files, output_dir)
    print(f"Resolved:   {resolved_cmd}")

    # 5. Get duration for progress reporting
    duration = None
    fmt = probe_data.get("format", {})
    if fmt.get("duration"):
        duration = float(fmt["duration"])

    # 6. Execute
    def on_progress(pct):
        print(f"\rProgress: {pct:5.1f}%", end="", flush=True)

    run_ffmpeg(resolved_cmd, duration=duration, progress_callback=on_progress)
    print()  # newline after progress

    print(f"Output: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="AI-ncoder")
    parser.add_argument("--file", nargs="+", default=None, help="Path(s) to input media file(s) (CLI mode)")
    parser.add_argument("--prompt", default=None, help="Natural language conversion prompt (CLI mode)")
    parser.add_argument("--output-dir", default=None, help="Output directory (defaults to input file's directory)")
    args = parser.parse_args()

    # CLI mode: both --file and --prompt provided
    if args.file and args.prompt:
        succeeded = 0
        failed = 0
        errors = []

        for file_path in args.file:
            try:
                output = process_file(file_path, args.prompt, args.output_dir)
                if output:
                    succeeded += 1
                else:
                    failed += 1  # ambiguous case
            except Exception as e:
                print(f"Error processing {file_path}: {e}", file=sys.stderr)
                errors.append((file_path, str(e)))
                failed += 1

        total = len(args.file)
        if total > 1:
            print(f"\nBatch complete: {succeeded}/{total} succeeded, {failed} failed.")
            if errors:
                print("Failed files:")
                for path, msg in errors:
                    print(f"  {path}: {msg}")

        if failed > 0 and succeeded == 0:
            sys.exit(1)
    else:
        # GUI mode
        from ui import run_gui
        run_gui()


if __name__ == "__main__":
    main()
