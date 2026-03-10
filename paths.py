"""Centralized path resolution for both development and PyInstaller-bundled modes.

When running from source, paths resolve relative to the project root.
When running from a PyInstaller bundle, data files live in sys._MEIPASS.
"""

import os
import sys


def get_base_dir() -> str:
    """Return the base directory where bundled data files live."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


_BASE_DIR = get_base_dir()

MODEL_PATH = os.path.join(
    _BASE_DIR, "models", "qwen2.5-coder-0.5b-instruct-q8_0.gguf"
)
FFMPEG_PATH = os.path.join(_BASE_DIR, "bin", "ffmpeg")
FFPROBE_PATH = os.path.join(_BASE_DIR, "bin", "ffprobe")
