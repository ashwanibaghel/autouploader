import logging
import mimetypes
import os
import re
import struct
from pathlib import Path

from google import genai
from google.genai import types

from config import GEMINI_API_KEY_ENV, GEMINI_TTS_MODEL, GEMINI_TTS_VOICE, OUTPUT_DIR, PROJECT_ROOT
from story_loader import Story


logger = logging.getLogger(__name__)


def generate_story_voiceover(
    story: Story,
    output_dir: Path = OUTPUT_DIR,
    model: str = GEMINI_TTS_MODEL,
    voice_name: str = GEMINI_TTS_VOICE,
) -> Path:
    """Generate a soft emotional Hindi/Hinglish voice-over for a story."""
    output_dir.mkdir(parents=True, exist_ok=True)
    load_dotenv_if_present()

    api_key = os.environ.get(GEMINI_API_KEY_ENV)
    if not api_key:
        raise RuntimeError(
            f"Missing {GEMINI_API_KEY_ENV}. Add it to .env before generating voice-over."
        )

    output_path = output_dir / f"{story.story_id}_voiceover.wav"
    prompt = build_voiceover_prompt(story)
    client = genai.Client(api_key=api_key)

    config = types.GenerateContentConfig(
        temperature=0.75,
        response_modalities=["audio"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
            )
        ),
    )

    audio_chunks: list[bytes] = []
    mime_type = ""

    logger.info("Generating Gemini voice-over with model %s", model)
    for chunk in client.models.generate_content_stream(
        model=model,
        contents=[prompt],
        config=config,
    ):
        for part in iter_response_parts(chunk):
            inline_data = getattr(part, "inline_data", None)
            if inline_data and inline_data.data:
                mime_type = inline_data.mime_type or mime_type
                audio_chunks.append(inline_data.data)

        text = getattr(chunk, "text", None)
        if text:
            logger.info("Gemini TTS text response: %s", text.strip())

    if not audio_chunks:
        raise RuntimeError("Gemini did not return audio data.")

    audio_data = b"".join(audio_chunks)
    output_path.write_bytes(normalize_audio_bytes(audio_data, mime_type))
    logger.info("Saved voice-over: %s", output_path)
    return output_path


def build_voiceover_prompt(story: Story) -> str:
    transcript = normalize_transcript_for_tts(story.body)
    return f"""Read the following Hindi/Hinglish emotional story as a premium voice-over.

# Brand
THE ASHY NOTES

# Voice Direction
Tone: warm, soft, emotional, restrained.
Feeling: late-night diary, personal memory, quiet family emotion.
Pace: natural spoken pace, not too slow.
Style: human storyteller, not news, not corporate, not motivational speech.
Delivery: keep it intimate and sincere. Do not overact.
Pauses: keep pauses short. Never add long silence between lines.

# Important
Read the complete transcript from start to end.
Read only the transcript. Do not add, remove, translate, summarize, or explain anything.
Do not stop early.

# Story Title
{story.title}

# Transcript
{transcript}
"""


def normalize_transcript_for_tts(text: str) -> str:
    lines = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line.strip())
        if line:
            lines.append(line)
    return "\n".join(lines)


def iter_response_parts(chunk) -> list:
    parts = getattr(chunk, "parts", None)
    if parts:
        return parts

    collected = []
    for candidate in getattr(chunk, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        candidate_parts = getattr(content, "parts", None) if content else None
        if candidate_parts:
            collected.extend(candidate_parts)
    return collected


def normalize_audio_bytes(audio_data: bytes, mime_type: str) -> bytes:
    extension = mimetypes.guess_extension(mime_type or "")
    if extension == ".wav" or (mime_type or "").lower().startswith("audio/wav"):
        return audio_data
    return convert_to_wav(audio_data, mime_type)


def convert_to_wav(audio_data: bytes, mime_type: str) -> bytes:
    parameters = parse_audio_mime_type(mime_type)
    bits_per_sample = parameters["bits_per_sample"]
    sample_rate = parameters["rate"]
    num_channels = 1
    data_size = len(audio_data)
    bytes_per_sample = bits_per_sample // 8
    block_align = num_channels * bytes_per_sample
    byte_rate = sample_rate * block_align
    chunk_size = 36 + data_size

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        chunk_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return header + audio_data


def parse_audio_mime_type(mime_type: str) -> dict[str, int]:
    bits_per_sample = 16
    rate = 24000

    for param in (mime_type or "").split(";"):
        param = param.strip()
        if param.lower().startswith("rate="):
            try:
                rate = int(param.split("=", 1)[1])
            except (ValueError, IndexError):
                pass
        else:
            match = re.search(r"L(\d+)", param, flags=re.IGNORECASE)
            if match:
                bits_per_sample = int(match.group(1))

    return {"bits_per_sample": bits_per_sample, "rate": rate}


def load_dotenv_if_present(path: Path = PROJECT_ROOT / ".env") -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
