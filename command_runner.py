import os
import re
import shlex
import subprocess

from paths import FFMPEG_PATH as _FFMPEG_PATH
_AUDIO_ONLY_EXTS = {
    ".mp3", ".wav", ".flac", ".aac", ".ogg", ".opus", ".wma", ".m4a",
    ".mka", ".ac3", ".dts", ".mp2", ".wv", ".ape", ".amr",
}
_KNOWN_EXTS = _AUDIO_ONLY_EXTS | {
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".wmv", ".ts", ".m4v",
    ".mpg", ".3gp", ".m2ts", ".vob", ".gif", ".mxf", ".ogv",
}
_EXT_ALIASES = {
    ".wave": ".wav",
    ".mpeg": ".mpg",
    ".tiff": ".tif",
}


def _normalize_ext(ext: str) -> str:
    """Fix common LLM extension mistakes like .mp3s (plural) or .wave → .wav."""
    ext = ext.lower()
    if ext in _KNOWN_EXTS:
        return ext
    # Check aliases (e.g. .wave → .wav)
    if ext in _EXT_ALIASES:
        return _EXT_ALIASES[ext]
    # Strip trailing 's' (plural) and recheck
    if ext.endswith("s") and ext[:-1] in _KNOWN_EXTS:
        return ext[:-1]
    # Plural of an alias (e.g. .waves → .wave → .wav)
    if ext.endswith("s") and ext[:-1] in _EXT_ALIASES:
        return _EXT_ALIASES[ext[:-1]]
    return ext


def reassemble_command(ai_output: dict, input_files: dict, output_dir: str) -> tuple[str, str]:
    """Replace placeholder tokens with real file paths.

    Args:
        ai_output: The dict from AIEngine.generate_command()
        input_files: Mapping of tokens to real paths, e.g. {"<INPUT_1>": "/path/to/video.mkv"}
        output_dir: Directory where output files will be written

    Returns:
        Tuple of (resolved_command_string, output_file_path)
    """
    command = ai_output["command"]

    # Replace input tokens — match token-with-extension first (e.g. <INPUT_1>.mov),
    # then bare token, to avoid double extensions. Quote paths for shell safety.
    for token, real_path in input_files.items():
        quoted = shlex.quote(real_path)
        # Pattern: <INPUT_1>.ext — replace the whole thing with the quoted real path
        token_with_ext = re.compile(re.escape(token) + r"\.\w+")
        command = token_with_ext.sub(quoted, command)
        # Also replace any bare token (without extension) just in case
        command = command.replace(token, quoted)

    # Find output tokens and their extensions, e.g. <OUTPUT_1>.mp3
    output_match = re.search(r"<OUTPUT_(\d+)>(\.\w+)", command)
    if not output_match:
        raise RuntimeError(f"No output token found in command: {command}")

    output_ext = output_match.group(2)  # e.g. ".mp3" or ".mp3s"

    # Normalize mangled extensions (e.g. ".mp3s" from plural user input → ".mp3")
    normalized_ext = _normalize_ext(output_ext)
    if normalized_ext != output_ext.lower():
        old_out = output_match.group(0)
        new_out = old_out[: old_out.rfind(".")] + normalized_ext
        command = command.replace(old_out, new_out)
        output_ext = normalized_ext
        output_match = re.search(r"<OUTPUT_(\d+)>(\.\w+)", command)

    # Guardrail: for audio-only output formats, clean up the command to prevent
    # common 0.5B model mistakes (including video flags, wrong audio codec, etc.)
    if output_ext.lower() in _AUDIO_ONLY_EXTS:
        command = _sanitize_audio_command(command, output_ext)

    # Derive output filename from first input file's basename
    first_input = next(iter(input_files.values()))
    base_name = os.path.splitext(os.path.basename(first_input))[0]

    output_path = _safe_output_path(output_dir, base_name, output_ext)

    # Replace all output tokens
    full_token = output_match.group(0)  # e.g. "<OUTPUT_1>.mp3"
    command = command.replace(full_token, shlex.quote(output_path))

    # Replace the leading "ffmpeg" with the real binary path
    if command.startswith("ffmpeg "):
        command = shlex.quote(_FFMPEG_PATH) + command[6:]

    return command, output_path


def _sanitize_audio_command(command: str, output_ext: str) -> str:
    """Clean up an ffmpeg command for audio-only output.

    Strips video-related flags and ensures -map a is present so that
    non-audio streams (cover art, video) don't break audio containers.
    """
    # Strip video-related flags that are meaningless for audio-only output.
    # These patterns match the flag and its value argument.
    video_flag_patterns = [
        r"-c:v\s+\S+",
        r"-crf\s+\S+",
        r"-preset\s+\S+",
        r"-vf\s+\S+",
        r"-b:v\s+\S+",
        r"-r\s+\d+",
        r"-s\s+\d+x\d+",
    ]
    for pattern in video_flag_patterns:
        command = re.sub(pattern, "", command)

    # If the audio codec is incompatible with the output container, remove it
    # and let ffmpeg auto-select the correct codec for the format.
    _CODEC_FOR_EXT = {
        ".mp3": {"libmp3lame", "mp3"},
        ".flac": {"flac"},
        ".opus": {"libopus", "opus"},
        ".wav": {"pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le"},
    }
    allowed = _CODEC_FOR_EXT.get(output_ext.lower())
    if allowed:
        codec_match = re.search(r"-c:a\s+(\S+)", command)
        if codec_match and codec_match.group(1) not in allowed:
            command = re.sub(r"-c:a\s+\S+", "", command)

    # Fix common model mistakes: -stereo → -ac 2, -mono → -ac 1
    command = re.sub(r"-stereo\b", "-ac 2", command)
    command = re.sub(r"-mono\b", "-ac 1", command)

    # Fix common model mistakes: -ar with "k" suffix → numeric Hz
    # e.g., -ar 44.1k → -ar 44100, -ar 48k → -ar 48000
    def _normalize_sample_rate(m):
        val = m.group(1)
        if val.lower().endswith("k"):
            try:
                return f"-ar {int(float(val[:-1]) * 1000)}"
            except ValueError:
                pass
        return m.group(0)

    command = re.sub(r"-ar\s+(\S+)", _normalize_sample_rate, command)

    # Collapse any double spaces left behind
    command = re.sub(r"  +", " ", command).strip()

    # Ensure -map a is present
    if "-map a" not in command:
        # Insert after the -i <file> argument
        match = re.search(r"-i\s+('(?:[^']*)'|\S+)", command)
        if match:
            insert_pos = match.end()
            command = command[:insert_pos] + " -map a" + command[insert_pos:]

    return command


def _safe_output_path(output_dir: str, base_name: str, ext: str) -> str:
    """Generate a non-conflicting output path with auto-rename."""
    os.makedirs(output_dir, exist_ok=True)

    candidate = os.path.join(output_dir, f"{base_name}{ext}")
    if not os.path.exists(candidate):
        return candidate

    counter = 1
    while True:
        candidate = os.path.join(output_dir, f"{base_name}({counter}){ext}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def run_ffmpeg(
    command: str, duration: float | None = None, progress_callback=None
) -> bool:
    """Execute an ffmpeg command with optional progress reporting.

    Args:
        command: The fully resolved ffmpeg command string
        duration: Total duration in seconds (for progress calculation)
        progress_callback: Called with progress as a float 0.0–100.0

    Returns:
        True on success, raises RuntimeError on failure
    """
    # Split command respecting quoted paths
    args = _split_command(command)

    # Add -progress pipe:1 for machine-readable progress output
    # Insert after the ffmpeg binary path, before other args
    args = [args[0], "-progress", "pipe:1", "-nostats"] + args[1:]

    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stderr_lines = []
    if process.stdout:
        for line in process.stdout:
            line = line.strip()

            # Parse "out_time_ms=<microseconds>" for progress
            if line.startswith("out_time_ms=") and duration and progress_callback:
                try:
                    us = int(line.split("=", 1)[1])
                    elapsed_secs = us / 1_000_000
                    pct = min(100.0, (elapsed_secs / duration) * 100)
                    progress_callback(pct)
                except (ValueError, ZeroDivisionError):
                    pass

    process.wait()

    if process.stderr:
        stderr_lines = process.stderr.read().splitlines()

    if process.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed (exit {process.returncode}):\n" + "\n".join(stderr_lines[-10:])
        )

    if progress_callback:
        progress_callback(100.0)

    return True


def _split_command(command: str) -> list[str]:
    """Split a command string into args, respecting quoted paths with spaces."""
    return shlex.split(command)
