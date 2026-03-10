"""Tests for the deterministic _sanitize_audio_command() guardrail.

No AI model needed — these run instantly.
"""

import pytest

from command_runner import _normalize_ext, _sanitize_audio_command


SANITIZE_CASES = [
    # --- Strip individual video flags ---
    pytest.param(
        "ffmpeg -i <INPUT_1>.mov -c:v copy -c:a libmp3lame -q:a 2 -map a <OUTPUT_1>.mp3",
        ".mp3",
        ["-map a", "-q:a 2", "-c:a libmp3lame"],
        ["-c:v"],
        id="strip-video-codec",
    ),
    pytest.param(
        "ffmpeg -i <INPUT_1>.mp4 -c:v libx264 -crf 23 -c:a libmp3lame -map a <OUTPUT_1>.mp3",
        ".mp3",
        ["-map a"],
        ["-c:v", "-crf"],
        id="strip-crf",
    ),
    pytest.param(
        "ffmpeg -i <INPUT_1>.mov -vf scale=-2:720 -c:a libmp3lame -q:a 0 -map a <OUTPUT_1>.mp3",
        ".mp3",
        ["-map a", "-q:a 0"],
        ["-vf"],
        id="strip-video-filter",
    ),
    pytest.param(
        "ffmpeg -i <INPUT_1>.mp4 -preset medium -c:a libmp3lame -map a <OUTPUT_1>.mp3",
        ".mp3",
        ["-map a"],
        ["-preset"],
        id="strip-preset",
    ),
    pytest.param(
        "ffmpeg -i <INPUT_1>.mp4 -b:v 2M -map a -c:a libmp3lame <OUTPUT_1>.mp3",
        ".mp3",
        ["-map a"],
        ["-b:v"],
        id="strip-video-bitrate",
    ),
    pytest.param(
        "ffmpeg -i <INPUT_1>.mp4 -r 30 -map a <OUTPUT_1>.mp3",
        ".mp3",
        ["-map a"],
        ["-r 30"],
        id="strip-framerate",
    ),
    pytest.param(
        "ffmpeg -i <INPUT_1>.mp4 -s 1920x1080 -map a <OUTPUT_1>.mp3",
        ".mp3",
        ["-map a"],
        ["-s 1920x1080"],
        id="strip-resolution",
    ),

    # --- Strip ALL video flags at once ---
    pytest.param(
        "ffmpeg -i <INPUT_1>.mp4 -c:v libx264 -crf 28 -preset medium -vf scale=-2:720 -b:v 2M -r 30 -s 1920x1080 -c:a libmp3lame -q:a 2 <OUTPUT_1>.mp3",
        ".mp3",
        ["-map a", "-c:a libmp3lame", "-q:a 2"],
        ["-c:v", "-crf", "-preset", "-vf", "-b:v"],
        id="strip-all-video-flags",
    ),

    # --- -map a insertion ---
    pytest.param(
        "ffmpeg -i <INPUT_1>.mov -c:a libmp3lame -q:a 2 <OUTPUT_1>.mp3",
        ".mp3",
        ["-map a", "-q:a 2"],
        [],
        id="add-map-a-when-missing",
    ),
    pytest.param(
        "ffmpeg -i <INPUT_1>.wav -map a -c:a libmp3lame -q:a 2 <OUTPUT_1>.mp3",
        ".mp3",
        ["-map a"],
        [],
        id="keep-map-a-when-present",
    ),

    # --- Codec compatibility ---
    pytest.param(
        "ffmpeg -i <INPUT_1>.mov -map a -c:a aac <OUTPUT_1>.mp3",
        ".mp3",
        ["-map a"],
        ["-c:a"],
        id="strip-incompatible-codec-aac-for-mp3",
    ),
    pytest.param(
        "ffmpeg -i <INPUT_1>.wav -map a -c:a libmp3lame -q:a 2 <OUTPUT_1>.mp3",
        ".mp3",
        ["-map a", "-c:a libmp3lame"],
        [],
        id="keep-compatible-codec-libmp3lame-for-mp3",
    ),
    pytest.param(
        "ffmpeg -i <INPUT_1>.wav -map a -c:a libmp3lame <OUTPUT_1>.flac",
        ".flac",
        ["-map a"],
        ["-c:a"],
        id="strip-incompatible-codec-mp3lame-for-flac",
    ),
    pytest.param(
        "ffmpeg -i <INPUT_1>.mov -map a -c:a pcm_s16le <OUTPUT_1>.wav",
        ".wav",
        ["-map a", "-c:a pcm_s16le"],
        [],
        id="keep-compatible-codec-pcm-for-wav",
    ),

    # --- Fix -stereo/-mono → -ac 2/-ac 1 ---
    pytest.param(
        "ffmpeg -i <INPUT_1>.opus -map a -b:a 192k -ar 44100 -stereo <OUTPUT_1>.mp3",
        ".mp3",
        ["-map a", "-ac 2", "-b:a 192k"],
        ["-stereo"],
        id="fix-stereo-to-ac-2",
    ),
    pytest.param(
        "ffmpeg -i <INPUT_1>.wav -map a -mono <OUTPUT_1>.mp3",
        ".mp3",
        ["-map a", "-ac 1"],
        ["-mono"],
        id="fix-mono-to-ac-1",
    ),

    # --- Audio-only source (no video flags to strip) ---
    pytest.param(
        "ffmpeg -i <INPUT_1>.wav -c:a libmp3lame -q:a 2 <OUTPUT_1>.mp3",
        ".mp3",
        ["-map a", "-c:a libmp3lame", "-q:a 2"],
        [],
        id="audio-only-source-just-add-map-a",
    ),

    # --- Fix -ar with "k" suffix → numeric Hz ---
    pytest.param(
        "ffmpeg -i <INPUT_1>.mov -map a -b:a 192k -ar 44.1k -ac 2 <OUTPUT_1>.mp3",
        ".mp3",
        ["-map a", "-ar 44100", "-b:a 192k", "-ac 2"],
        ["-ar 44.1k"],
        id="fix-ar-44.1k-to-44100",
    ),
    pytest.param(
        "ffmpeg -i <INPUT_1>.mov -map a -ar 48k <OUTPUT_1>.mp3",
        ".mp3",
        ["-map a", "-ar 48000"],
        ["-ar 48k"],
        id="fix-ar-48k-to-48000",
    ),
    pytest.param(
        "ffmpeg -i <INPUT_1>.mov -map a -ar 22.05k -ac 1 <OUTPUT_1>.wav",
        ".wav",
        ["-map a", "-ar 22050", "-ac 1"],
        ["-ar 22.05k"],
        id="fix-ar-22.05k-to-22050",
    ),
    pytest.param(
        "ffmpeg -i <INPUT_1>.mov -map a -ar 44100 -ac 2 <OUTPUT_1>.mp3",
        ".mp3",
        ["-map a", "-ar 44100", "-ac 2"],
        [],
        id="keep-ar-44100-unchanged",
    ),
]


@pytest.mark.parametrize(
    "input_command, output_ext, must_contain, must_not_contain",
    SANITIZE_CASES,
)
def test_sanitize_audio_command(input_command, output_ext, must_contain, must_not_contain):
    """Test that _sanitize_audio_command correctly strips video flags and fixes codecs."""
    result = _sanitize_audio_command(input_command, output_ext)

    for expected in must_contain:
        assert expected in result, f"Expected '{expected}' in: {result}"
    for forbidden in must_not_contain:
        assert forbidden not in result, f"Forbidden '{forbidden}' in: {result}"

    # Structural checks
    assert "  " not in result, f"Double spaces in: {result}"
    assert result.startswith("ffmpeg"), f"Must start with ffmpeg: {result}"


def test_sanitize_preserves_tokens():
    """Input and output tokens must survive sanitization."""
    cmd = "ffmpeg -i <INPUT_1>.mov -c:v copy -map a -q:a 2 <OUTPUT_1>.mp3"
    result = _sanitize_audio_command(cmd, ".mp3")
    assert "<INPUT_1>" in result
    assert "<OUTPUT_1>" in result


def test_sanitize_idempotent():
    """Running sanitize twice should produce the same result as running it once."""
    cmd = "ffmpeg -i <INPUT_1>.mp4 -c:v libx264 -crf 28 -preset medium -map a -c:a libmp3lame <OUTPUT_1>.mp3"
    once = _sanitize_audio_command(cmd, ".mp3")
    twice = _sanitize_audio_command(once, ".mp3")
    assert once == twice


# ===================================================================
# Extension normalization tests
# ===================================================================
@pytest.mark.parametrize(
    "ext, expected",
    [
        (".mp3s", ".mp3"),
        (".mp4s", ".mp4"),
        (".wavs", ".wav"),
        (".mkvs", ".mkv"),
        (".flac", ".flac"),
        (".mp3", ".mp3"),
        (".MP3S", ".mp3"),
        (".xyz", ".xyz"),  # unknown ext passes through unchanged
        (".wave", ".wav"),
        (".waves", ".wav"),
        (".WAVE", ".wav"),
    ],
    ids=[
        "plural-mp3s", "plural-mp4s", "plural-wavs", "plural-mkvs",
        "valid-flac", "valid-mp3", "uppercase-plural-mp3s", "unknown-ext",
        "alias-wave", "alias-waves-plural", "alias-wave-uppercase",
    ],
)
def test_normalize_ext(ext, expected):
    """Test that _normalize_ext fixes plural and case issues."""
    assert _normalize_ext(ext) == expected
