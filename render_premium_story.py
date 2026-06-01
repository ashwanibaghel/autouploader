import argparse
import logging
from pathlib import Path

from config import LOGS_DIR
from premium_renderer import render_premium_story
from story_loader import find_unused_story, load_story
from voiceover import generate_story_voiceover


def configure_logging() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOGS_DIR / "premium_render.log", encoding="utf-8"),
        ],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a premium animated story video.")
    parser.add_argument("--story", type=Path, help="Path to a specific story .txt file.")
    parser.add_argument(
        "--voiceover",
        action="store_true",
        help="Generate Gemini TTS voice-over and mix it into the rendered video.",
    )
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    story = load_story(args.story) if args.story else find_unused_story()
    voiceover_path = generate_story_voiceover(story) if args.voiceover else None
    result = render_premium_story(story, voiceover_path=voiceover_path)
    logging.info("Rendered: %s", result.output_path)
    logging.info("Duration: %.1f seconds", result.duration_seconds)
    logging.info("Screens: %s", len(result.screens))
    if result.voiceover_path:
        logging.info("Voice-over: %s", result.voiceover_path)
    if result.audio_path:
        logging.info("Music: %s", result.audio_path)
    else:
        logging.warning("No music found in audio/. Rendered without music.")


if __name__ == "__main__":
    main()
