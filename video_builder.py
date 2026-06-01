import logging
import random
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg

from config import (
    AUDIO_DIR,
    LOGO_FILE,
    MIN_SHORT_DURATION_SECONDS,
    OUTPUT_DIR,
    SUPPORTED_AUDIO_EXTENSIONS,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
)
from mood_analyzer import MoodProfile
from story_loader import Story


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RenderResult:
    output_path: Path
    duration_seconds: float
    segments: list[str]
    background_videos: list[Path]
    audio_path: Path | None


def render_story_video(
    story: Story,
    mood_profile: MoodProfile,
    background_videos: list[Path],
    output_dir: Path = OUTPUT_DIR,
    logo_path: Path = LOGO_FILE,
) -> RenderResult:
    if not background_videos:
        raise ValueError("At least one background video is required.")
    if not logo_path.exists():
        raise FileNotFoundError(f"Logo file not found: {logo_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{story.story_id}.mp4"
    subtitles_path = output_dir / f"{story.story_id}.ass"

    segments = split_story_into_segments(story.body)
    duration = calculate_duration(len(segments))
    audio_path = pick_audio_track(mood_profile)
    write_ass_subtitles(subtitles_path, segments, duration)

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    filter_complex = _build_filter_complex(
        clip_count=len(background_videos),
        duration=duration,
        subtitles_path=subtitles_path,
    )

    command = [ffmpeg, "-y"]
    for video_path in background_videos:
        command.extend(["-stream_loop", "-1", "-t", str(duration), "-i", str(video_path)])
    command.extend(["-i", str(logo_path)])
    if audio_path:
        command.extend(["-stream_loop", "-1", "-t", str(duration), "-i", str(audio_path)])

    video_output_label = f"[vout]"
    command.extend(["-filter_complex", filter_complex, "-map", video_output_label])

    if audio_path:
        command.extend(["-map", f"{len(background_videos) + 1}:a", "-af", "volume=0.55,afade=t=out:st={:.2f}:d=2".format(max(duration - 2, 0))])
    else:
        command.extend(["-an"])

    command.extend(
        [
            "-t",
            str(duration),
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-shortest",
            str(output_path),
        ]
    )

    logger.info("Rendering video: %s", output_path)
    subprocess.run(command, check=True)
    subtitles_path.unlink(missing_ok=True)

    return RenderResult(
        output_path=output_path,
        duration_seconds=duration,
        segments=segments,
        background_videos=background_videos,
        audio_path=audio_path,
    )


def split_story_into_segments(text: str, max_chars: int = 64) -> list[str]:
    if not text.strip():
        raise ValueError("Story text is empty.")

    lines = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line.strip())
        if not line:
            continue
        sentence_parts = re.split(r"(?<=[.!?।])\s+", line)
        for part in sentence_parts:
            part = part.strip()
            if part:
                lines.extend(_split_long_part(part, max_chars=max_chars))

    screens = []
    index = 0
    while index < len(lines):
        current = lines[index]
        next_line = lines[index + 1] if index + 1 < len(lines) else None
        if next_line and len(current) <= max_chars and len(next_line) <= max_chars:
            screens.append(f"{current}\n{next_line}")
            index += 2
        else:
            screens.append(current)
            index += 1

    return screens


def calculate_duration(segment_count: int) -> float:
    if segment_count <= 0:
        raise ValueError("Segment count must be greater than zero.")
    target = segment_count * 5.2
    return float(max(MIN_SHORT_DURATION_SECONDS, target))


def pick_audio_track(mood_profile: MoodProfile, audio_dir: Path = AUDIO_DIR) -> Path | None:
    if not audio_dir.exists():
        logger.warning("Audio folder not found. Rendering without music: %s", audio_dir)
        return None

    tracks = [
        path
        for path in audio_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
    ]
    if not tracks:
        logger.warning("No music files found in %s. Rendering without music.", audio_dir)
        return None

    preferred = [
        path
        for path in tracks
        if any(keyword in path.stem.lower() for keyword in mood_profile.audio_keywords)
    ]
    return random.choice(preferred or tracks)


def write_ass_subtitles(path: Path, segments: list[str], total_duration: float) -> None:
    font_name = "Nirmala UI"
    safe_segments = [segment.replace("{", "(").replace("}", ")") for segment in segments]
    segment_duration = total_duration / len(safe_segments)

    events = []
    for index, segment in enumerate(safe_segments):
        start = index * segment_duration
        end = min(total_duration, (index + 1) * segment_duration)
        screen_parts = [part.strip() for part in segment.splitlines() if part.strip()]
        top_text = _ass_escape(wrap_text(screen_parts[0], max_chars=24))
        events.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},TopText,,0,0,0,,{top_text}"
        )
        if len(screen_parts) > 1:
            bottom_text = _ass_escape(wrap_text(screen_parts[1], max_chars=24))
            events.append(
                f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},BottomText,,0,0,0,,{bottom_text}"
            )

    content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {VIDEO_WIDTH}
PlayResY: {VIDEO_HEIGHT}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TopText,{font_name},54,&H00FFFFFF,&H000000FF,&HD9000000,&H99000000,-1,0,0,0,100,100,0,0,1,4,2,8,92,92,650,1
Style: BottomText,{font_name},54,&H00FFFFFF,&H000000FF,&HD9000000,&H99000000,-1,0,0,0,100,100,0,0,1,4,2,2,92,92,575,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{chr(10).join(events)}
"""
    path.write_text(content, encoding="utf-8")


def wrap_text(text: str, max_chars: int) -> str:
    words = text.split()
    lines = []
    current = []

    for word in words:
        candidate = " ".join([*current, word])
        if len(candidate) <= max_chars:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]

    if current:
        lines.append(" ".join(current))

    return r"\N".join(lines[:3])


def _split_long_part(part: str, max_chars: int) -> list[str]:
    if len(part) <= max_chars:
        return [part]

    chunks = []
    words = part.split()
    current = []
    for word in words:
        candidate = " ".join([*current, word])
        if len(candidate) <= max_chars:
            current.append(word)
        else:
            if current:
                chunks.append(" ".join(current))
            current = [word]
    if current:
        chunks.append(" ".join(current))
    return chunks


def _build_filter_complex(clip_count: int, duration: float, subtitles_path: Path) -> str:
    clip_filters = []
    concat_inputs = []

    clip_duration = duration / clip_count
    for index in range(clip_count):
        clip_filters.append(
            f"[{index}:v]trim=duration={clip_duration},setpts=PTS-STARTPTS,"
            f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},setsar=1[v{index}]"
        )
        concat_inputs.append(f"[v{index}]")

    subtitle_file = _ffmpeg_path(subtitles_path)
    logo_input_index = clip_count
    center_logo_width = int(VIDEO_WIDTH * 0.38)
    corner_logo_width = 82
    font_file = _ffmpeg_path(Path("C:/Windows/Fonts/segoeuib.ttf"))

    filters = [
        *clip_filters,
        f"{''.join(concat_inputs)}concat=n={clip_count}:v=1:a=0[base]",
        "[base]eq=brightness=-0.07:contrast=1.08[dimmed]",
        f"[{logo_input_index}:v]scale={center_logo_width}:-1,format=rgba,colorchannelmixer=aa=0.09[centerlogo]",
        "[dimmed][centerlogo]overlay=(W-w)/2:(H-h)/2:format=auto[centered]",
        f"[{logo_input_index}:v]scale={corner_logo_width}:-1,format=rgba,colorchannelmixer=aa=0.92[cornerlogo]",
        "[centered][cornerlogo]overlay=58:74:format=auto[brandedlogo]",
        "[brandedlogo]drawtext="
        f"fontfile='{font_file}':"
        "text='The Ashy Notes':"
        "x=154:y=90:"
        "fontsize=38:"
        "fontcolor=white@0.90:"
        "shadowcolor=black@0.70:"
        "shadowx=2:shadowy=2[branded]",
        f"[branded]subtitles='{subtitle_file}'[vout]",
    ]
    return ";".join(filters)


def _ass_escape(text: str) -> str:
    return text.replace("{", "(").replace("}", ")")


def _ass_time(seconds: float) -> str:
    centiseconds = int(round(seconds * 100))
    cs = centiseconds % 100
    total_seconds = centiseconds // 100
    s = total_seconds % 60
    total_minutes = total_seconds // 60
    m = total_minutes % 60
    h = total_minutes // 60
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ffmpeg_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace(":", r"\:")
