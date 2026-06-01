import logging
import random
import re
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg

from config import (
    AUDIO_DIR,
    LOGO_FILE,
    OUTPUT_DIR,
    SUPPORTED_AUDIO_EXTENSIONS,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
)
from story_loader import Story


logger = logging.getLogger(__name__)

INTRO_SECONDS = 1.8
OUTRO_SECONDS = 4.0
MAX_DURATION_SECONDS = 60.0
STORY_BUDGET_SECONDS = MAX_DURATION_SECONDS - INTRO_SECONDS - OUTRO_SECONDS


@dataclass(frozen=True)
class PremiumRenderResult:
    output_path: Path
    duration_seconds: float
    screens: list[dict]
    audio_path: Path | None
    voiceover_path: Path | None = None


def render_premium_story(
    story: Story,
    output_dir: Path = OUTPUT_DIR,
    voiceover_path: Path | None = None,
) -> PremiumRenderResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{story.story_id}_v4.mp4"
    subtitles_path = output_dir / f"{story.story_id}_v4.ass"

    screens = split_into_story_screens(story.body)
    timings = calculate_screen_timings(screens)
    if voiceover_path:
        voiceover_duration = get_media_duration_seconds(voiceover_path)
        timings = align_timings_to_voiceover(timings, voiceover_duration)
    total_duration = INTRO_SECONDS + sum(duration for _, duration in timings) + OUTRO_SECONDS
    audio_path = pick_music_track(story.mood)

    write_premium_ass(subtitles_path, story.title, timings, total_duration)
    run_ffmpeg_render(output_path, subtitles_path, total_duration, audio_path, voiceover_path)
    subtitles_path.unlink(missing_ok=True)

    return PremiumRenderResult(output_path, total_duration, screens, audio_path, voiceover_path)


def split_into_story_screens(text: str, max_lines: int = 3, max_chars: int = 72) -> list[dict]:
    lines = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line.strip())
        if line:
            lines.extend(_split_long_line(line, max_chars=28))

    screens = []
    current = []
    current_chars = 0

    for line in lines:
        next_chars = current_chars + len(line)
        if current and (len(current) >= max_lines or next_chars > max_chars):
            screens.append(_build_screen(current))
            current = []
            current_chars = 0

        current.append(line)
        current_chars += len(line)

    if current:
        screens.append(_build_screen(current))

    return screens


def calculate_screen_timings(screens: list[dict]) -> list[tuple[dict, float]]:
    raw_durations = []
    for screen in screens:
        words = sum(len(line.split()) for line in screen["lines"])
        multiplier = 1.32 if screen["golden"] else 1.0
        raw_durations.append(max(2.5, min(5.6, (1.0 + words * 0.43) * multiplier)))

    total = sum(raw_durations)
    if total > STORY_BUDGET_SECONDS:
        scale = STORY_BUDGET_SECONDS / total
        durations = [max(1.75, duration * scale) for duration in raw_durations]
        overflow = sum(durations) - STORY_BUDGET_SECONDS
        if overflow > 0:
            durations = _trim_overflow(durations, overflow)
    else:
        durations = raw_durations

    return list(zip(screens, durations))


def align_timings_to_voiceover(
    timings: list[tuple[dict, float]],
    target_story_seconds: float,
) -> list[tuple[dict, float]]:
    current = sum(duration for _, duration in timings)
    max_story_seconds = min(STORY_BUDGET_SECONDS, current * 1.35)
    if current <= 0 or target_story_seconds <= current:
        return timings

    if target_story_seconds > max_story_seconds:
        logger.warning(
            "Voice-over duration %.1fs is too long for %.1fs story timing. "
            "Capping text timing at %.1fs to avoid slow page turns.",
            target_story_seconds,
            current,
            max_story_seconds,
        )
        target_story_seconds = max_story_seconds

    scale = target_story_seconds / current
    return [(screen, duration * scale) for screen, duration in timings]


def stretch_timings_to_budget(
    timings: list[tuple[dict, float]],
    target_story_seconds: float,
) -> list[tuple[dict, float]]:
    return align_timings_to_voiceover(timings, target_story_seconds)


def pick_music_track(mood: str | None = None, audio_dir: Path = AUDIO_DIR) -> Path | None:
    mood_tracks = []
    if mood:
        mood_dir = audio_dir / mood.lower()
        mood_tracks = _audio_files_in(mood_dir)
        if mood_tracks:
            return random.choice(mood_tracks)

    tracks = _audio_files_in(audio_dir)
    return random.choice(tracks) if tracks else None


def _audio_files_in(audio_dir: Path) -> list[Path]:
    if not audio_dir.exists():
        return []

    return [
        path
        for path in audio_dir.glob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
    ]


def _build_screen(lines: list[str]) -> dict:
    joined = " ".join(lines).lower()
    golden_terms = [
        "majboori",
        "mohabbat",
        "kami mat samajhna",
        "neend tak bech",
        "keemti",
        "yaad rakhna",
    ]
    return {"lines": lines, "golden": any(term in joined for term in golden_terms)}


def write_premium_ass(
    path: Path,
    title: str,
    timings: list[tuple[dict, float]],
    total_duration: float,
) -> None:
    font_regular = "Georgia"
    font_brand = "Georgia"
    events = []

    events.append(
        "Dialogue: 0,0:00:00.00,{end},Intro,,0,0,0,,{{\\fad(520,420)}}THE ASHY NOTES".format(
            end=_ass_time(INTRO_SECONDS)
        )
    )
    events.append(
        "Dialogue: 0,0:00:00.35,{end},IntroSub,,0,0,0,,{{\\fad(620,360)}}STORIES THAT STAY".format(
            end=_ass_time(INTRO_SECONDS)
        )
    )

    cursor = INTRO_SECONDS
    for screen, duration in timings:
        start = cursor
        end = cursor + duration
        text = r"\N".join(_ass_escape(line) for line in screen["lines"])
        style = "GoldenStory" if screen["golden"] else "Story"
        zoom = r"{\fad(420,420)\t(0,650,\fscx102\fscy102)}" if screen["golden"] else r"{\fad(360,420)}"
        events.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},{style},,0,0,0,,{zoom}{text}"
        )
        cursor = end

    outro_start = max(INTRO_SECONDS, total_duration - OUTRO_SECONDS)
    outro_text = r"Thank you for reading.\NIf this story touched your heart...\NFollow The Ashy Notes\NLike   Share   Follow"
    events.append(
        f"Dialogue: 0,{_ass_time(outro_start)},{_ass_time(total_duration)},Outro,,0,0,0,,{{\\fad(450,450)}}{outro_text}"
    )

    content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {VIDEO_WIDTH}
PlayResY: {VIDEO_HEIGHT}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Intro,{font_brand},64,&H00F3D29A,&H000000FF,&H99000000,&H66000000,0,0,0,0,100,100,4,0,1,2,0,5,110,110,0,1
Style: IntroSub,{font_regular},28,&H66D8C09A,&H000000FF,&H66000000,&H44000000,0,0,0,0,100,100,4,0,1,1,0,5,110,110,170,1
Style: Story,{font_regular},76,&H00F7F0E5,&H000000FF,&HCC000000,&H66000000,0,0,0,0,100,112,0,0,1,4,1,5,70,70,0,1
Style: GoldenStory,{font_regular},79,&H0027D9FF,&H000000FF,&HAA211000,&H66000000,0,0,0,0,100,114,0,0,1,5,1,5,70,70,0,1
Style: Outro,{font_regular},52,&H00F7F0E5,&H000000FF,&HAA000000,&H66000000,0,0,0,0,100,112,0,0,1,3,1,5,90,90,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{chr(10).join(events)}
"""
    path.write_text(content, encoding="utf-8")


def run_ffmpeg_render(
    output_path: Path,
    subtitles_path: Path,
    duration: float,
    audio_path: Path | None,
    voiceover_path: Path | None = None,
) -> None:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subtitle_file = _ffmpeg_path(subtitles_path)
    font_file = _ffmpeg_path(Path("C:/Windows/Fonts/georgia.ttf"))

    command = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x070709:s=540x960:r=30:d={duration}",
        "-i",
        str(LOGO_FILE),
    ]
    audio_input_index = None
    voiceover_input_index = None
    if audio_path:
        audio_input_index = len(command_input_indexes(command))
        command.extend(["-stream_loop", "-1", "-t", str(duration), "-i", str(audio_path)])
    if voiceover_path:
        voiceover_input_index = len(command_input_indexes(command))
        command.extend(["-i", str(voiceover_path)])

    audio_filter = ""
    audio_map = None
    if voiceover_path and audio_path:
        voice_delay_ms = int(INTRO_SECONDS * 1000)
        audio_filter = (
            f";[{audio_input_index}:a]volume=0.135,"
            f"afade=t=in:st=0:d=1.2,"
            f"afade=t=out:st={max(duration - 3, 0):.2f}:d=3[music];"
            f"[{voiceover_input_index}:a]volume=1.00,"
            f"adelay={voice_delay_ms}|{voice_delay_ms}[voice];"
            "[music][voice]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )
        audio_map = "[aout]"
    elif voiceover_path:
        voice_delay_ms = int(INTRO_SECONDS * 1000)
        audio_filter = (
            f";[{voiceover_input_index}:a]volume=1.00,"
            f"adelay={voice_delay_ms}|{voice_delay_ms}[aout]"
        )
        audio_map = "[aout]"

    filter_complex = (
        "[0:v]format=rgba,"
        "noise=alls=26:allf=t+u,"
        "eq=contrast=1.18:brightness=0.012:saturation=0.82,"
        "drawbox=x=0:y=0:w=iw:h=ih:color=0x07172c@0.26:t=fill,"
        "drawbox=x=0:y=0:w=iw:h=ih:color=0x2b0b26@0.16:t=fill,"
        "drawbox=x=-30:y=0:w=340:h=385:color=0xd4b36b@0.130:t=fill,"
        "drawbox=x=-55:y=80:w=670:h=180:color=0xf0ca72@0.070:t=fill,"
        "drawbox=x=384:y=52:w=176:h=840:color=0xf0ca72@0.032:t=fill,"
        "drawbox=x=24:y=246:w=492:h=484:color=black@0.20:t=fill,"
        "drawbox=x=36:y=260:w=468:h=456:color=0xd4b36b@0.060:t=fill,"
        f"vignette=PI/2.12:eval=frame,scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:flags=bicubic[canvas];"
        "[canvas]"
        "drawbox=x=43:y=51:w=994:h=1818:color=0xd4b36b@0.58:t=2,"
        "drawbox=x=60:y=70:w=960:h=1780:color=0xd4b36b@0.13:t=1,"
        "drawbox=x=120:y=225:w=840:h=2:color=0xd4b36b@0.34:t=fill,"
        "drawbox=x=230:y=270:w=620:h=1:color=0xd4b36b@0.16:t=fill,"
        "drawbox=x=150:y=1485:w=780:h=1:color=0xd4b36b@0.20:t=fill,"
        "drawbox=x=285:y=1537:w=510:h=2:color=0xd4b36b@0.34:t=fill,"
        "drawbox=x=100:y=515:w=880:h=780:color=black@0.16:t=fill,"
        "drawbox=x=120:y=545:w=840:h=720:color=0xd4b36b@0.052:t=fill,"
        "drawtext=fontfile='{font_file}':text='THE ASHY NOTES':"
        "x=(W-tw)/2:y=145:fontsize=34:fontcolor=0xF3D29A@0.88:"
        "shadowcolor=black@0.45:shadowx=0:shadowy=2,"
        "drawtext=fontfile='{font_file}':text='STORIES THAT STAY':"
        "x=(W-tw)/2:y=1705:fontsize=18:fontcolor=0xF3D29A@0.50:"
        "shadowcolor=black@0.35:shadowx=0:shadowy=1,"
        "drawtext=fontfile='{font_file}':text='The Ashy Notes':"
        "x=(W-tw)/2:y=1630:fontsize=44:fontcolor=0xF3D29A@0.42:"
        "shadowcolor=black@0.40:shadowx=0:shadowy=2,"
        "drawtext=fontfile='{font_file}':text='\\\"':"
        "x=(W-tw)/2:y=520:fontsize=96:fontcolor=0xF3D29A@0.46:"
        "shadowcolor=black@0.35:shadowx=0:shadowy=2[atmos];"
        "[1:v]scale=72:-1,format=rgba,colorchannelmixer=aa=0.145[logo_top];"
        "[1:v]scale=58:-1,format=rgba,colorchannelmixer=aa=0.060[logo_wm];"
        "[atmos][logo_top]overlay=77:92:format=auto[with_top_logo];"
        "[with_top_logo][logo_wm]overlay=W-w-72:H-h-96:format=auto[wm];"
        "[wm]subtitles='{subtitle_file}'[vout]"
        "{audio_filter}"
    ).format(font_file=font_file, subtitle_file=subtitle_file, audio_filter=audio_filter)

    command.extend(["-filter_complex", filter_complex, "-map", "[vout]"])

    if audio_map:
        command.extend(["-map", audio_map])
    elif audio_path:
        command.extend(
            [
                "-map",
                f"{audio_input_index}:a",
                "-af",
                f"volume=0.30,afade=t=in:st=0:d=1.2,afade=t=out:st={max(duration - 3, 0):.2f}:d=3",
            ]
        )
    else:
        command.append("-an")

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
            str(output_path),
        ]
    )

    logger.info("Rendering premium template: %s", output_path)
    subprocess.run(command, check=True)


def command_input_indexes(command: list[str]) -> list[int]:
    return [index for index, value in enumerate(command) if value == "-i"]


def get_media_duration_seconds(path: Path) -> float:
    if path.suffix.lower() == ".wav":
        with wave.open(str(path), "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            return frames / float(rate)

    ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe())
    ffprobe = ffmpeg.with_name("ffprobe.exe")
    if not ffprobe.exists():
        return 0.0

    result = subprocess.run(
        [
            str(ffprobe),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def _split_long_line(line: str, max_chars: int) -> list[str]:
    if len(line) <= max_chars:
        return [line]

    words = line.split()
    chunks = []
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


def _trim_overflow(durations: list[float], overflow: float) -> list[float]:
    trimmed = durations[:]
    while overflow > 0.01:
        candidates = [index for index, duration in enumerate(trimmed) if duration > 1.75]
        if not candidates:
            break
        reduction = min(overflow / len(candidates), 0.08)
        for index in candidates:
            actual = min(reduction, trimmed[index] - 1.75)
            trimmed[index] -= actual
            overflow -= actual
            if overflow <= 0.01:
                break
    return trimmed


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
