import json
import os

from llama_cpp import Llama

from paths import get_base_dir

_PROJECT_ROOT = get_base_dir()

SYSTEM_PROMPT = """\
You are an ffmpeg command generator. Given media file metadata and a user request, \
output the correct ffmpeg command using the provided input/output placeholder tokens.

Rules:
- Use ONLY the placeholder tokens (e.g. <INPUT_1>, <OUTPUT_1>) for file paths. Never invent filenames.
- The command must start with "ffmpeg".
- Do NOT include "-y" or any overwrite flags.
- When the output is an audio-only format (mp3, wav, flac, aac, ogg, opus), always include "-map a" to select only audio streams and exclude cover art or video.
- For MP3 quality: `-b:a 320k` is highest CBR quality, `-q:a 0` is highest VBR quality, `-q:a 9` is lowest quality. When the user asks for "highest quality" or "best quality" mp3, use `-b:a 320k`.
- For channel layout: use `-ac 2` for stereo, `-ac 1` for mono. Never use `-stereo` or `-mono` flags.
- For sample rate: use `-ar` followed by the numeric Hz value (not "k" suffix). Common rates: 44100 (44.1kHz), 48000 (48kHz), 22050 (22.05kHz).
- If the user's request is vague (e.g. "make it better", "improve this", "fix it"), impossible, \
or you cannot determine the correct ffmpeg flags, you MUST set "is_ambiguous" to true, \
set "command" to an empty string, and ask a clarification question.

Examples:

Input: Format: QuickTime / MOV, Duration: 00:02:30, Video: h264 1920x1080, Audio: aac 48000Hz 2ch
File: <INPUT_1>.mov
User: "Extract the audio as a high-quality mp3"
Output: {"command": "ffmpeg -i <INPUT_1>.mov -q:a 0 -map a <OUTPUT_1>.mp3", "is_ambiguous": false, "clarification_question": ""}

Input: Format: QuickTime / MOV, Duration: 00:01:00, Video: h264 1920x1080, Audio: aac 48000Hz 2ch
File: <INPUT_1>.mov
User: "highest quality mp3"
Output: {"command": "ffmpeg -i <INPUT_1>.mov -map a -b:a 320k <OUTPUT_1>.mp3", "is_ambiguous": false, "clarification_question": ""}

Input: Format: Matroska, Duration: 01:45:00, Video: hevc 3840x2160, Audio: opus 48000Hz 6ch
File: <INPUT_1>.mkv
User: "Convert this to mp4"
Output: {"command": "ffmpeg -i <INPUT_1>.mkv -c:v copy -c:a aac <OUTPUT_1>.mp4", "is_ambiguous": false, "clarification_question": ""}

Input: Format: QuickTime / MOV, Duration: 00:00:30, Video: h264 1920x1080, Audio: aac 44100Hz 2ch
File: <INPUT_1>.mov
User: "Resize to 720p"
Output: {"command": "ffmpeg -i <INPUT_1>.mov -vf scale=-2:720 -c:a copy <OUTPUT_1>.mov", "is_ambiguous": false, "clarification_question": ""}

Input: Format: MPEG-4, Duration: 00:10:00, Video: h264 1920x1080, Audio: aac 48000Hz 2ch
File: <INPUT_1>.mp4
User: "Compress this video to reduce file size"
Output: {"command": "ffmpeg -i <INPUT_1>.mp4 -c:v libx264 -crf 28 -preset medium -c:a aac -b:a 128k <OUTPUT_1>.mp4", "is_ambiguous": false, "clarification_question": ""}

Input: Format: WAV / WAVE (Waveform Audio), Duration: 00:03:00, Audio: pcm_s16le 44100Hz 2ch
File: <INPUT_1>.wav
User: "Convert to mp3"
Output: {"command": "ffmpeg -i <INPUT_1>.wav -map a -c:a libmp3lame -q:a 2 <OUTPUT_1>.mp3", "is_ambiguous": false, "clarification_question": ""}

Input: Format: Ogg, Duration: 00:03:35, Audio: opus 48000Hz 2ch, Video: mjpeg 480x360
File: <INPUT_1>.opus
User: "make an mp3 but low quality and mono"
Output: {"command": "ffmpeg -i <INPUT_1>.opus -map a -c:a libmp3lame -q:a 9 -ac 1 <OUTPUT_1>.mp3", "is_ambiguous": false, "clarification_question": ""}

Input: Format: QuickTime / MOV, Duration: 00:02:30, Video: h264 1920x1080, Audio: aac 48000Hz 2ch
File: <INPUT_1>.mov
User: "make a 192kbps mp3 at 44.1k sample rate and stereo"
Output: {"command": "ffmpeg -i <INPUT_1>.mov -map a -b:a 192k -ar 44100 -ac 2 <OUTPUT_1>.mp3", "is_ambiguous": false, "clarification_question": ""}

Input: Format: QuickTime / MOV, Duration: 00:00:30, Video: h264 1920x1080, Audio: aac 48000Hz 2ch
File: <INPUT_1>.mov
User: "grab the audio as 22050hz mono wav"
Output: {"command": "ffmpeg -i <INPUT_1>.mov -map a -ar 22050 -ac 1 <OUTPUT_1>.wav", "is_ambiguous": false, "clarification_question": ""}

Input: Format: WAV, Duration: 00:05:00, Audio: pcm_s16le 44100Hz 2ch
File: <INPUT_1>.wav
User: "Make it better"
Output: {"command": "", "is_ambiguous": true, "clarification_question": "Could you be more specific? For example, do you want to convert to a different format, adjust the volume, trim the audio, or change the sample rate?"}

Input: Format: MPEG-4, Duration: 00:03:00, Video: h264 1280x720, Audio: aac 44100Hz 2ch
File: <INPUT_1>.mp4
User: "Improve this"
Output: {"command": "", "is_ambiguous": true, "clarification_question": "What would you like to improve? For example, increase resolution, reduce file size, change format, or extract audio?"}\
"""

_RESPONSE_SCHEMA = {
    "type": "json_object",
    "schema": {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "is_ambiguous": {"type": "boolean"},
            "clarification_question": {"type": "string"},
        },
        "required": ["command", "is_ambiguous", "clarification_question"],
    },
}


class AIEngine:
    def __init__(self, model_path: str):
        if not os.path.isabs(model_path):
            model_path = os.path.join(_PROJECT_ROOT, model_path)

        if not os.path.isfile(model_path):
            raise FileNotFoundError(f"Model not found: {model_path}")

        self._llm = Llama(
            model_path=model_path,
            n_ctx=2048,
            n_gpu_layers=0,  # CPU-only for portability
            verbose=False,
        )

    def generate_command(
        self, media_summary: str, input_token: str, user_prompt: str
    ) -> dict:
        """Generate an ffmpeg command from media metadata and a user prompt.

        Args:
            media_summary: Output of get_media_summary() (e.g. "Format: QuickTime / MOV, ...")
            input_token: The placeholder with extension (e.g. "<INPUT_1>.mov")
            user_prompt: The user's natural language request

        Returns:
            dict with keys: command, is_ambiguous, clarification_question
        """
        user_message = (
            f"Input: {media_summary}\n"
            f"File: {input_token}\n"
            f'User: "{user_prompt}"'
        )

        response = self._llm.create_chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            response_format=_RESPONSE_SCHEMA,
            temperature=0.1,
        )

        text = response["choices"][0]["message"]["content"]
        result = json.loads(text)

        # Post-processing guardrails for the 0.5B model:
        # - If there's a valid command, trust it even if clarification text leaked through
        # - If the command is empty/missing, treat as ambiguous
        has_command = bool(result.get("command", "").strip())
        has_clarification = bool(result.get("clarification_question", "").strip())

        if has_command:
            # Valid command — clear any spurious clarification text
            result["is_ambiguous"] = False
            result["clarification_question"] = ""
        elif has_clarification:
            # No command but has clarification — mark ambiguous
            result["is_ambiguous"] = True
            result["command"] = ""

        return result
