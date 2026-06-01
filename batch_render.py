import argparse
import logging
from pathlib import Path

from config import APPROVED_STORIES_DIR, LOGS_DIR, OUTPUT_DIR
from premium_renderer import render_premium_story
from story_loader import load_story
from voiceover import generate_story_voiceover


def configure_logging() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOGS_DIR / "batch_render.log", encoding="utf-8"),
        ],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch render The Ashy Notes story videos.")
    parser.add_argument("--stories-dir", type=Path, default=APPROVED_STORIES_DIR)
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of stories to render.")
    parser.add_argument("--voiceover", action="store_true", help="Generate/reuse Gemini voice-over.")
    parser.add_argument("--overwrite", action="store_true", help="Re-render videos that already exist.")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()

    story_paths = sorted(args.stories_dir.rglob("*.txt"))
    if args.limit:
        story_paths = story_paths[: args.limit]

    if not story_paths:
        raise FileNotFoundError(f"No .txt stories found in {args.stories_dir}")

    rendered = 0
    skipped = 0
    failed = 0

    for story_path in story_paths:
        output_path = OUTPUT_DIR / f"{story_path.stem}_v4.mp4"
        if output_path.exists() and not args.overwrite:
            logging.info("Skipping existing video: %s", output_path)
            skipped += 1
            continue

        try:
            story = load_story(story_path)
            voiceover_path = None
            if args.voiceover:
                cached_voiceover = OUTPUT_DIR / f"{story.story_id}_voiceover.wav"
                voiceover_path = (
                    cached_voiceover if cached_voiceover.exists() else generate_story_voiceover(story)
                )

            result = render_premium_story(story, voiceover_path=voiceover_path)
            logging.info("Rendered %s -> %s", story_path.name, result.output_path)
            rendered += 1
        except Exception:
            logging.exception("Failed to render story: %s", story_path)
            failed += 1

    logging.info("Batch complete. Rendered=%s Skipped=%s Failed=%s", rendered, skipped, failed)


if __name__ == "__main__":
    main()
