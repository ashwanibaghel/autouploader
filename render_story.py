import argparse
import logging
import os
from pathlib import Path

from config import AUDIO_DIR, DOWNLOADS_DIR, LOGS_DIR, OUTPUT_DIR, STORIES_DIR, VIDEOS_DIR
from mood_analyzer import analyze_mood
from pexels_client import download_stock_videos
from story_loader import find_unused_story, load_story
from video_builder import render_story_video


logger = logging.getLogger(__name__)


def configure_logging() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOGS_DIR / "render.log", encoding="utf-8"),
        ],
    )


def ensure_project_folders() -> None:
    for folder in [STORIES_DIR, AUDIO_DIR, VIDEOS_DIR, DOWNLOADS_DIR, OUTPUT_DIR, LOGS_DIR]:
        folder.mkdir(parents=True, exist_ok=True)


def load_env_file(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render one The Ashy Notes story video.")
    parser.add_argument("--story", type=Path, help="Path to a specific story .txt file.")
    parser.add_argument(
        "--use-local-videos",
        action="store_true",
        help="Use videos from videos/ instead of downloading from Pexels.",
    )
    parser.add_argument("--clip-count", type=int, default=4, help="Number of background clips to use.")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    load_env_file()
    ensure_project_folders()
    args = parse_args()

    story = load_story(args.story) if args.story else find_unused_story()
    mood_profile = analyze_mood(story.title, story.body, story.mood)

    if args.use_local_videos:
        background_videos = _local_background_videos(args.clip_count)
    else:
        background_videos = download_stock_videos(
            keywords=mood_profile.pexels_keywords,
            story_id=story.story_id,
            target_count=args.clip_count,
        )

    result = render_story_video(
        story=story,
        mood_profile=mood_profile,
        background_videos=background_videos,
    )

    logger.info("Rendered: %s", result.output_path)
    logger.info("Duration: %.1f seconds", result.duration_seconds)
    logger.info("Text segments: %s", len(result.segments))
    if result.audio_path:
        logger.info("Music: %s", result.audio_path)


def _local_background_videos(limit: int) -> list[Path]:
    candidates = sorted(
        path
        for path in VIDEOS_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in {".mp4", ".mov", ".m4v", ".mkv"}
    )
    if not candidates:
        raise FileNotFoundError(
            f"No local background videos found in {VIDEOS_DIR}. "
            "Add clips there or run without --use-local-videos to use Pexels."
        )
    return candidates[:limit]


if __name__ == "__main__":
    main()
