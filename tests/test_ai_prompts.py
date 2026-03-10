"""Tests for LLM prompt-to-ffmpeg-command generation.

Each test feeds a hardcoded media summary + user prompt to AIEngine.generate_command()
and asserts that the returned command matches expected regex patterns.

The model is loaded once per session via the ai_engine fixture in conftest.py.
"""

import re

import pytest

# ---------------------------------------------------------------------------
# Canonical media summaries (match get_media_summary() output format)
# ---------------------------------------------------------------------------
VIDEO_MOV = "Format: QuickTime / MOV, Duration: 00:00:05, Audio: aac 48000Hz 2ch, Video: h264 1920x1080"
VIDEO_MKV = "Format: Matroska, Duration: 01:45:00, Video: hevc 3840x2160, Audio: opus 48000Hz 6ch"
VIDEO_MP4 = "Format: MPEG-4, Duration: 00:10:00, Video: h264 1920x1080, Audio: aac 48000Hz 2ch"
AUDIO_WAV = "Format: WAV / WAVE (Waveform Audio), Duration: 00:00:09, Audio: pcm_s16le 8000Hz 1ch"
AUDIO_OPUS = "Format: Ogg, Duration: 00:03:35, Audio: opus 48000Hz 2ch"
AUDIO_FLAC = "Format: FLAC (Free Lossless Audio Codec), Duration: 00:04:12, Audio: flac 44100Hz 2ch"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _check_result(result, must_contain, must_not_contain, expect_ambiguous):
    """Validate an AIEngine result dict against pattern expectations."""
    assert isinstance(result, dict)
    assert {"command", "is_ambiguous", "clarification_question"} <= set(result)

    if expect_ambiguous:
        assert result["is_ambiguous"] is True, (
            f"Expected ambiguous but got command: {result['command']}"
        )
        assert result["command"].strip() == "", (
            f"Ambiguous result should have empty command, got: {result['command']}"
        )
        assert result["clarification_question"].strip() != "", (
            "Ambiguous result should have a clarification question"
        )
        return

    # Non-ambiguous assertions
    assert result["is_ambiguous"] is False, (
        f"Expected valid command, got clarification: {result['clarification_question']}"
    )
    cmd = result["command"]
    assert cmd.strip().startswith("ffmpeg"), f"Command must start with ffmpeg: {cmd}"
    assert "-y" not in cmd.split(), f"Must not contain -y flag: {cmd}"

    for pattern in must_contain:
        assert re.search(pattern, cmd, re.IGNORECASE), (
            f"Required pattern '{pattern}' not found in: {cmd}"
        )
    for pattern in must_not_contain:
        assert not re.search(pattern, cmd, re.IGNORECASE), (
            f"Forbidden pattern '{pattern}' found in: {cmd}"
        )


# ===================================================================
# CATEGORY A: Standard / Happy Path
# ===================================================================
STANDARD_CASES = [
    pytest.param(
        VIDEO_MOV, "<INPUT_1>.mov",
        "Extract the audio as mp3",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.mp3", r"-map\s+a"],
        [r"-y"],
        False,
        id="standard-extract-audio-mp3",
    ),
    pytest.param(
        VIDEO_MKV, "<INPUT_1>.mkv",
        "Convert this to mp4",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.mp4"],
        [r"-y"],
        False,
        id="standard-mkv-to-mp4",
    ),
    pytest.param(
        AUDIO_WAV, "<INPUT_1>.wav",
        "Convert to mp3",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.mp3", r"-map\s+a"],
        [r"-y", r"-c:v", r"-vf"],
        False,
        id="standard-wav-to-mp3",
    ),
    pytest.param(
        VIDEO_MOV, "<INPUT_1>.mov",
        "Resize to 720p",
        [r"-i\s+<INPUT_1>", r"scale.*720", r"<OUTPUT_1>"],
        [r"-y"],
        False,
        id="standard-resize-720p",
    ),
    pytest.param(
        VIDEO_MP4, "<INPUT_1>.mp4",
        "Compress this video to reduce file size",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.mp4", r"-crf\s+\d+"],
        [r"-y"],
        False,
        id="standard-compress-video",
    ),
]

# ===================================================================
# CATEGORY B: Slang / Informal Language
# ===================================================================
SLANG_CASES = [
    pytest.param(
        VIDEO_MOV, "<INPUT_1>.mov",
        "yo gimme the audio from this vid as an mp3 plz",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.mp3", r"-map\s+a"],
        [r"-y", r"-c:v"],
        False,
        id="slang-gimme-audio-mp3",
    ),
    pytest.param(
        VIDEO_MP4, "<INPUT_1>.mp4",
        "mp4 2 mkv pls",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.mkv"],
        [r"-y"],
        False,
        id="slang-mp4-to-mkv-abbrev",
    ),
    pytest.param(
        VIDEO_MOV, "<INPUT_1>.mov",
        "just rip the sound out",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.\w+", r"-map\s+a"],
        [r"-y"],
        False,
        id="slang-rip-sound-out",
    ),
    pytest.param(
        AUDIO_WAV, "<INPUT_1>.wav",
        "flac",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.flac"],
        [r"-y"],
        False,
        id="slang-single-word-flac",
    ),
]

# ===================================================================
# CATEGORY C: Typos / Misspellings
# ===================================================================
TYPO_CASES = [
    pytest.param(
        VIDEO_MOV, "<INPUT_1>.mov",
        "exract the aduio as an mp3",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.mp3", r"-map\s+a"],
        [r"-y"],
        False,
        id="typo-extract-audio-mp3",
    ),
    pytest.param(
        VIDEO_MP4, "<INPUT_1>.mp4",
        "convrt to mkv format",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.mkv"],
        [r"-y"],
        False,
        id="typo-convert-mkv",
    ),
    pytest.param(
        AUDIO_WAV, "<INPUT_1>.wav",
        "chnage this wav too a mp3 file",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.mp3"],
        [r"-y"],
        False,
        id="typo-wav-to-mp3-heavy",
    ),
    pytest.param(
        VIDEO_MOV, "<INPUT_1>.mov",
        "make it a empeethree",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.mp3"],
        [r"-y"],
        False,
        id="typo-phonetic-mp3",
    ),
]

# ===================================================================
# CATEGORY D: Mixed Case / Formatting
# ===================================================================
CASE_CASES = [
    pytest.param(
        VIDEO_MOV, "<INPUT_1>.mov",
        "EXTRACT THE AUDIO AS MP3",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.mp3", r"-map\s+a"],
        [r"-y"],
        False,
        id="case-all-caps-extract-mp3",
    ),
    pytest.param(
        AUDIO_WAV, "<INPUT_1>.wav",
        "cOnVeRt To FlAc",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.flac"],
        [r"-y"],
        False,
        id="case-alternating-flac",
    ),
    pytest.param(
        VIDEO_MP4, "<INPUT_1>.mp4",
        "   convert   this   to    mkv!!!   ",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.mkv"],
        [r"-y"],
        False,
        id="format-extra-whitespace-punct",
    ),
]

# ===================================================================
# CATEGORY E: Quality-Related Prompts
# ===================================================================
QUALITY_CASES = [
    pytest.param(
        VIDEO_MOV, "<INPUT_1>.mov",
        "highest quality mp3",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.mp3", r"-b:a\s+320k"],
        [r"-y"],
        False,
        id="quality-highest-mp3-320k",
    ),
    pytest.param(
        AUDIO_WAV, "<INPUT_1>.wav",
        "make a really low quality mp3, I don't care about fidelity",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.mp3", r"-q:a\s+[7-9]"],
        [r"-y", r"-b:a\s+320k"],
        False,
        id="quality-low-mp3",
    ),
    pytest.param(
        AUDIO_OPUS, "<INPUT_1>.opus",
        "make an mp3 but low quality and mono",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.mp3", r"-ac\s+1"],
        [r"-y", r"-b:a\s+320k"],
        False,
        id="quality-low-mp3-mono",
    ),
    pytest.param(
        AUDIO_WAV, "<INPUT_1>.wav",
        "convert to lossless flac",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.flac"],
        [r"-y"],
        False,
        id="quality-lossless-flac",
    ),
]

# ===================================================================
# CATEGORY F: Multi-Instruction Prompts
# ===================================================================
MULTI_CASES = [
    pytest.param(
        VIDEO_MOV, "<INPUT_1>.mov",
        "make a 192kbps mp3 at 44.1k sample rate and stereo",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.mp3", r"-b:a\s+192k", r"-ar\s+44100", r"-ac\s+2"],
        [r"-y", r"-stereo"],
        False,
        marks=pytest.mark.xfail(reason="0.5B model may omit -ar or use wrong syntax; few-shot example added but model is non-deterministic"),
        id="multi-192k-stereo-mp3",
    ),
    pytest.param(
        VIDEO_MOV, "<INPUT_1>.mov",
        "resize to 480p and convert to mp4",
        [r"-i\s+<INPUT_1>", r"scale.*480", r"<OUTPUT_1>\.mp4"],
        [r"-y"],
        False,
        id="multi-resize-and-convert-mp4",
    ),
    pytest.param(
        VIDEO_MP4, "<INPUT_1>.mp4",
        "get the audio, make it mono, and save as wav",
        [r"-i\s+<INPUT_1>", r"-ac\s+1", r"<OUTPUT_1>\.wav"],
        [r"-y"],
        False,
        marks=pytest.mark.xfail(reason="0.5B model may not handle 'mono' correctly"),
        id="multi-audio-mono-wav",
    ),
    pytest.param(
        VIDEO_MP4, "<INPUT_1>.mp4",
        "scale down to 720p and compress it more, like crf 30",
        [r"-i\s+<INPUT_1>", r"scale.*720", r"-crf\s+30", r"<OUTPUT_1>"],
        [r"-y"],
        False,
        id="multi-scale-and-crf30",
    ),
]

# ===================================================================
# CATEGORY G: Ambiguous / Vague (expect is_ambiguous=True)
# ===================================================================
AMBIGUOUS_CASES = [
    pytest.param(
        AUDIO_WAV, "<INPUT_1>.wav",
        "make it better",
        [], [], True,
        marks=pytest.mark.xfail(reason="0.5B model generates commands for vague prompts; post-processing clears is_ambiguous"),
        id="ambiguous-make-it-better",
    ),
    pytest.param(
        VIDEO_MP4, "<INPUT_1>.mp4",
        "improve this",
        [], [], True,
        marks=pytest.mark.xfail(reason="0.5B model generates commands for vague prompts; post-processing clears is_ambiguous"),
        id="ambiguous-improve-this",
    ),
    pytest.param(
        VIDEO_MOV, "<INPUT_1>.mov",
        "fix it",
        [], [], True,
        marks=pytest.mark.xfail(reason="0.5B model generates commands for vague prompts; post-processing clears is_ambiguous"),
        id="ambiguous-fix-it",
    ),
    pytest.param(
        VIDEO_MP4, "<INPUT_1>.mp4",
        "make it more purple and taste like strawberries",
        [], [], True,
        marks=pytest.mark.xfail(reason="0.5B model may try to generate a command for nonsense"),
        id="ambiguous-nonsensical-purple",
    ),
    pytest.param(
        AUDIO_WAV, "<INPUT_1>.wav",
        "do something with this",
        [], [], True,
        marks=pytest.mark.xfail(reason="0.5B model generates commands for vague prompts; post-processing clears is_ambiguous"),
        id="ambiguous-do-something",
    ),
]

# ===================================================================
# CATEGORY H: Unusual / Edge Case Format Requests
# ===================================================================
UNUSUAL_CASES = [
    pytest.param(
        VIDEO_MOV, "<INPUT_1>.mov",
        "convert to ogg vorbis audio",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.ogg"],
        [r"-y"],
        False,
        id="unusual-ogg-vorbis",
    ),
    pytest.param(
        VIDEO_MP4, "<INPUT_1>.mp4",
        "transcode video to h265 in an mkv container",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.mkv", r"(libx265|hevc)"],
        [r"-y"],
        False,
        id="unusual-explicit-h265-mkv",
    ),
    pytest.param(
        VIDEO_MOV, "<INPUT_1>.mov",
        "grab the audio as 22050hz mono wav",
        [r"-i\s+<INPUT_1>", r"-ar\s+22050", r"-ac\s+1", r"<OUTPUT_1>\.wav"],
        [r"-y"],
        False,
        marks=pytest.mark.xfail(reason="0.5B model may confuse -ar with -b:a or miss mono; few-shot example added but model is non-deterministic"),
        id="unusual-wav-22050-mono",
    ),
    pytest.param(
        VIDEO_MKV, "<INPUT_1>.mkv",
        "extract audio to opus format",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.opus"],
        [r"-y"],
        False,
        id="unusual-extract-opus",
    ),
]

# ===================================================================
# CATEGORY I: Contradictory / Impossible
# ===================================================================
CONTRADICTORY_CASES = [
    pytest.param(
        VIDEO_MOV, "<INPUT_1>.mov",
        "upscale this 1080p video to 8k",
        [r"-i\s+<INPUT_1>", r"scale", r"<OUTPUT_1>"],
        [r"-y"],
        False,
        id="contradictory-upscale-8k",
    ),
    pytest.param(
        AUDIO_WAV, "<INPUT_1>.wav",
        "increase the audio quality to maximum",
        [], [], True,
        marks=pytest.mark.xfail(reason="0.5B model may generate a command instead of flagging ambiguous"),
        id="contradictory-increase-lossless-quality",
    ),
    pytest.param(
        VIDEO_MP4, "<INPUT_1>.mp4",
        "make the file smaller but also increase the quality",
        [], [], True,
        marks=pytest.mark.xfail(reason="0.5B model generates commands for contradictory prompts"),
        id="contradictory-smaller-higher-quality",
    ),
]

# ===================================================================
# CATEGORY J: Off-the-Wall (clear intent, weird phrasing)
# ===================================================================
OFFTHEWALL_CASES = [
    pytest.param(
        VIDEO_MOV, "<INPUT_1>.mov",
        "make it a ringtone",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.(mp3|m4a|m4r|aac)", r"-map\s+a"],
        [r"-y", r"-c:v"],
        False,
        marks=pytest.mark.xfail(reason="0.5B model may not map 'ringtone' to audio extraction"),
        id="offthewall-make-ringtone",
    ),
    pytest.param(
        VIDEO_MOV, "<INPUT_1>.mov",
        "I need this for my Instagram story",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.mp4"],
        [r"-y"],
        False,
        id="offthewall-instagram-story",
    ),
    pytest.param(
        VIDEO_MOV, "<INPUT_1>.mov",
        "strip everything except the voice",
        [r"-i\s+<INPUT_1>", r"<OUTPUT_1>\.\w+", r"-map\s+a"],
        [r"-y"],
        False,
        marks=pytest.mark.xfail(reason="0.5B model generates broken command for metaphorical phrasing"),
        id="offthewall-strip-except-voice",
    ),
]


# ===================================================================
# All cases combined
# ===================================================================
ALL_PROMPT_CASES = (
    STANDARD_CASES
    + SLANG_CASES
    + TYPO_CASES
    + CASE_CASES
    + QUALITY_CASES
    + MULTI_CASES
    + AMBIGUOUS_CASES
    + UNUSUAL_CASES
    + CONTRADICTORY_CASES
    + OFFTHEWALL_CASES
)


@pytest.mark.parametrize(
    "media_summary, input_token, user_prompt, must_contain, must_not_contain, expect_ambiguous",
    ALL_PROMPT_CASES,
)
def test_ai_prompt(ai_engine, media_summary, input_token, user_prompt,
                   must_contain, must_not_contain, expect_ambiguous):
    """Test that the LLM generates correct commands for various prompts."""
    result = ai_engine.generate_command(media_summary, input_token, user_prompt)
    _check_result(result, must_contain, must_not_contain, expect_ambiguous)


# ===================================================================
# Post-sanitize pipeline tests
# ===================================================================
from command_runner import _sanitize_audio_command

PIPELINE_CASES = [
    pytest.param(
        VIDEO_MOV, "<INPUT_1>.mov",
        "extract audio as mp3", ".mp3",
        [r"-map\s+a"],
        [r"-c:v", r"-vf", r"-crf", r"-preset"],
        id="pipeline-extract-mp3-sanitized",
    ),
    pytest.param(
        VIDEO_MP4, "<INPUT_1>.mp4",
        "save just the audio as a wav file", ".wav",
        [r"-map\s+a"],
        [r"-c:v", r"-vf", r"-crf", r"-preset"],
        id="pipeline-extract-wav-sanitized",
    ),
    pytest.param(
        VIDEO_MOV, "<INPUT_1>.mov",
        "highest quality mp3 please", ".mp3",
        [r"-map\s+a"],
        [r"-c:v", r"-vf"],
        id="pipeline-highest-quality-mp3-sanitized",
    ),
    pytest.param(
        VIDEO_MOV, "<INPUT_1>.mov",
        "192kbps stereo mp3 at 44.1k", ".mp3",
        [r"-map\s+a"],
        [r"-stereo"],  # guardrail must remove -stereo if model generates it
        id="pipeline-stereo-mp3-sanitized",
    ),
    pytest.param(
        VIDEO_MOV, "<INPUT_1>.mov",
        "make a 192kbps mp3 at 44.1k sample rate", ".mp3",
        [r"-map\s+a", r"-ar\s+44100"],
        [r"-ar\s+44\.1k"],  # sanitizer must fix "44.1k" if model outputs it
        id="pipeline-sample-rate-44100-sanitized",
    ),
]


@pytest.mark.parametrize(
    "media_summary, input_token, user_prompt, output_ext, must_contain_after, must_not_contain_after",
    PIPELINE_CASES,
)
def test_post_sanitize_pipeline(ai_engine, media_summary, input_token, user_prompt,
                                output_ext, must_contain_after, must_not_contain_after):
    """Test that LLM output, after sanitization, meets audio safety requirements."""
    result = ai_engine.generate_command(media_summary, input_token, user_prompt)
    assert not result["is_ambiguous"], f"Expected command, got ambiguous: {result}"

    sanitized = _sanitize_audio_command(result["command"], output_ext)

    for pattern in must_contain_after:
        assert re.search(pattern, sanitized, re.IGNORECASE), (
            f"Pattern '{pattern}' not found after sanitize: {sanitized}"
        )
    for pattern in must_not_contain_after:
        assert not re.search(pattern, sanitized, re.IGNORECASE), (
            f"Forbidden pattern '{pattern}' found after sanitize: {sanitized}"
        )
