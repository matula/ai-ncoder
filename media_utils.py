import json
import os
import subprocess

from paths import FFPROBE_PATH as _FFPROBE_PATH


def probe_file(file_path: str) -> dict:
    """Run ffprobe on a media file and return the parsed JSON output."""
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    cmd = [
        _FFPROBE_PATH,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        file_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed (exit {result.returncode}): {result.stderr.strip()}"
        )

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"ffprobe returned invalid JSON: {e}")

    if not data.get("streams"):
        raise RuntimeError(f"ffprobe found no streams in: {file_path}")

    return data


def get_media_summary(probe_data: dict) -> str:
    """Extract a concise summary string from ffprobe data for LLM context injection."""
    parts = []

    # Container format and duration
    fmt = probe_data.get("format", {})
    format_name = fmt.get("format_long_name") or fmt.get("format_name", "unknown")
    parts.append(f"Format: {format_name}")

    duration = fmt.get("duration")
    if duration:
        secs = float(duration)
        h, remainder = divmod(int(secs), 3600)
        m, s = divmod(remainder, 60)
        parts.append(f"Duration: {h:02d}:{m:02d}:{s:02d}")

    # Per-stream info
    for stream in probe_data.get("streams", []):
        codec_type = stream.get("codec_type")
        codec_name = stream.get("codec_name", "unknown")

        if codec_type == "video":
            w = stream.get("width", "?")
            h = stream.get("height", "?")
            parts.append(f"Video: {codec_name} {w}x{h}")

        elif codec_type == "audio":
            sample_rate = stream.get("sample_rate", "?")
            channels = stream.get("channels", "?")
            parts.append(f"Audio: {codec_name} {sample_rate}Hz {channels}ch")

        elif codec_type == "subtitle":
            parts.append(f"Subtitle: {codec_name}")

    return ", ".join(parts)
