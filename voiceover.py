import logging
import json
import mimetypes
import os
import random
import re
import struct
import time
import wave
from pathlib import Path

from google import genai
from google.genai import types

from config import GEMINI_API_KEY_ENV, GEMINI_TTS_MODEL, GEMINI_TTS_VOICE, OUTPUT_DIR, PROJECT_ROOT
from premium_renderer import get_media_duration_seconds, split_into_story_screens
from story_loader import Story


logger = logging.getLogger(__name__)


def generate_story_voiceover(
    story: Story,
    output_dir: Path = OUTPUT_DIR,
    model: str = GEMINI_TTS_MODEL,
    voice_name: str = GEMINI_TTS_VOICE,
    max_attempts: int = 4,
) -> Path:
    """Generate a reliable screen-by-screen voice-over for a story."""
    output_dir.mkdir(parents=True, exist_ok=True)
    load_dotenv_if_present()

    api_key = os.environ.get(GEMINI_API_KEY_ENV)
    if not api_key:
        raise RuntimeError(
            f"Missing {GEMINI_API_KEY_ENV}. Add it to .env before generating voice-over."
        )

    screens = split_into_story_screens(story.body)
    if len(screens) > 1:
        return generate_chunked_story_voiceover(
            story=story,
            screens=screens,
            output_dir=output_dir,
            model=model,
            voice_name=voice_name,
            max_attempts=max_attempts,
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
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        audio_chunks = []
        mime_type = ""
        try:
            logger.info(
                "Generating Gemini voice-over with model %s (attempt %s/%s)",
                model,
                attempt,
                max_attempts,
            )
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

            if audio_chunks:
                break
            last_error = RuntimeError("Gemini did not return audio data.")
        except Exception as error:
            last_error = error

        if attempt < max_attempts:
            sleep_seconds = min(45.0, (2**attempt) + random.uniform(1.0, 4.0))
            logger.warning(
                "Gemini voice-over attempt %s/%s failed: %s. Retrying in %.1fs.",
                attempt,
                max_attempts,
                last_error,
                sleep_seconds,
            )
            time.sleep(sleep_seconds)

    if not audio_chunks:
        raise RuntimeError("Gemini did not return audio data.") from last_error

    audio_data = b"".join(audio_chunks)
    output_path.write_bytes(normalize_audio_bytes(audio_data, mime_type))
    logger.info("Saved voice-over: %s", output_path)
    return output_path


def generate_chunked_story_voiceover(
    story: Story,
    screens: list[dict],
    output_dir: Path,
    model: str,
    voice_name: str,
    max_attempts: int,
) -> Path:
    output_path = output_dir / f"{story.story_id}_voiceover.wav"
    chunks_dir = output_dir / "_voice_chunks" / story.story_id
    chunks_dir.mkdir(parents=True, exist_ok=True)

    load_dotenv_if_present()
    api_key = os.environ.get(GEMINI_API_KEY_ENV)
    if not api_key:
        raise RuntimeError(f"Missing {GEMINI_API_KEY_ENV}. Add it to .env before generating voice-over.")

    client = genai.Client(api_key=api_key)
    config = build_tts_config(voice_name)
    chunk_paths = []
    screen_durations = []

    for index, screen in enumerate(screens, start=1):
        text = "\n".join(screen["lines"])
        chunk_path = chunks_dir / f"{index:03d}.wav"
        prompt = build_screen_voiceover_prompt(story, text, index, len(screens))
        audio_data, mime_type = generate_tts_audio(
            client=client,
            config=config,
            model=model,
            prompt=prompt,
            label=f"{story.story_id} screen {index}/{len(screens)}",
            max_attempts=max_attempts,
        )
        chunk_path.write_bytes(normalize_audio_bytes(audio_data, mime_type))
        chunk_duration = get_media_duration_seconds(chunk_path)
        if chunk_duration < 0.45:
            raise RuntimeError(f"Generated voice chunk is too short for {story.story_id} screen {index}.")
        chunk_paths.append(chunk_path)
        screen_durations.append(chunk_duration + 0.28)

    concatenate_wav_chunks(chunk_paths, output_path, pause_seconds=0.18)
    if screen_durations:
        screen_durations[-1] = max(0.45, screen_durations[-1] - 0.18)
    write_timing_sidecar(output_path, screen_durations)
    logger.info("Saved chunked voice-over: %s", output_path)
    return output_path


def build_tts_config(voice_name: str):
    return types.GenerateContentConfig(
        temperature=0.55,
        response_modalities=["audio"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
            )
        ),
    )


def generate_tts_audio(
    client,
    config,
    model: str,
    prompt: str,
    label: str,
    max_attempts: int,
) -> tuple[bytes, str]:
    audio_chunks: list[bytes] = []
    mime_type = ""
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        audio_chunks = []
        mime_type = ""
        try:
            logger.info("Generating Gemini voice-over for %s (attempt %s/%s)", label, attempt, max_attempts)
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

            if audio_chunks:
                return b"".join(audio_chunks), mime_type
            last_error = RuntimeError("Gemini did not return audio data.")
        except Exception as error:
            last_error = error

        if attempt < max_attempts:
            sleep_seconds = min(45.0, (2**attempt) + random.uniform(1.0, 4.0))
            logger.warning(
                "Gemini voice-over attempt %s/%s failed for %s: %s. Retrying in %.1fs.",
                attempt,
                max_attempts,
                label,
                last_error,
                sleep_seconds,
            )
            time.sleep(sleep_seconds)

    raise RuntimeError(f"Gemini did not return audio data for {label}.") from last_error


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


def build_screen_voiceover_prompt(story: Story, text: str, index: int, total: int) -> str:
    return f"""Read this exact Hindi/Hinglish story segment as a natural voice-over.

# Brand
THE ASHY NOTES

# Direction
Tone: warm, sincere, emotional, restrained.
Pace: natural spoken pace. No long pauses.
Read the full segment exactly once.
Do not add, remove, translate, summarize, or explain anything.

# Story
{story.title}

# Segment {index} of {total}
{text}
"""


def normalize_transcript_for_tts(text: str) -> str:
    lines = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line.strip())
        if line:
            lines.append(line)
    return "\n".join(lines)


def concatenate_wav_chunks(chunk_paths: list[Path], output_path: Path, pause_seconds: float) -> None:
    if not chunk_paths:
        raise ValueError("No voice chunks to concatenate.")

    with wave.open(str(chunk_paths[0]), "rb") as first:
        params = first.getparams()

    silence_frames = b"\x00" * int(params.framerate * pause_seconds) * params.nchannels * params.sampwidth

    with wave.open(str(output_path), "wb") as output:
        output.setparams(params)
        for index, chunk_path in enumerate(chunk_paths):
            with wave.open(str(chunk_path), "rb") as chunk:
                if chunk.getparams()[:3] != params[:3]:
                    raise RuntimeError(f"Voice chunk audio format mismatch: {chunk_path}")
                output.writeframes(chunk.readframes(chunk.getnframes()))
            if index < len(chunk_paths) - 1:
                output.writeframes(silence_frames)


def write_timing_sidecar(voiceover_path: Path, screen_durations: list[float]) -> None:
    sidecar_path = voiceover_path.with_suffix(".timings.json")
    sidecar_path.write_text(
        json.dumps({"screen_durations": screen_durations}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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
