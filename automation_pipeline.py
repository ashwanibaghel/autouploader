import argparse
import json
import logging
import shutil
from pathlib import Path

from cloudinary_uploader import upload_video_to_cloudinary
from config import APPROVED_STORIES_DIR, LOGS_DIR, OUTPUT_DIR, UPLOADS_DIR
from instagram_publisher import publish_instagram_reel
from premium_renderer import calculate_screen_timings, get_media_duration_seconds, render_premium_story, split_into_story_screens
from publish_state import record_published_story
from publishing_metadata import build_instagram_caption, build_youtube_metadata
from story_loader import find_pending_approved_story, load_story
from uploader import upload_video
from voiceover import generate_story_voiceover


def configure_logging() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOGS_DIR / "automation_pipeline.log", encoding="utf-8"),
        ],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one automated The Ashy Notes story job.")
    parser.add_argument("--story", type=Path, help="Specific story file. Defaults to next pending approved story.")
    parser.add_argument("--stories-dir", type=Path, default=APPROVED_STORIES_DIR)
    parser.add_argument("--selection", choices=["sequential", "random"], default="sequential")
    parser.add_argument("--no-voiceover", action="store_true", help="Render without Gemini voice-over.")
    parser.add_argument("--prepare-youtube", action="store_true", help="Copy final MP4 and metadata to uploads/.")
    parser.add_argument("--upload-youtube", action="store_true", help="Upload the rendered video to YouTube.")
    parser.add_argument("--upload-instagram", action="store_true", help="Publish the rendered video as an Instagram Reel.")
    parser.add_argument(
        "--cloudinary",
        action="store_true",
        help="Upload the rendered video to Cloudinary and use that public URL for Instagram.",
    )
    parser.add_argument(
        "--instagram-video-url",
        help="Public HTTPS direct MP4 URL for Instagram. Overrides INSTAGRAM_PUBLIC_VIDEO_BASE_URL.",
    )
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()

    story = (
        load_story(args.story)
        if args.story
        else find_pending_approved_story(args.stories_dir, selection=args.selection)
    )
    voiceover_path = None
    if not args.no_voiceover:
        cached_voiceover = OUTPUT_DIR / f"{story.story_id}_voiceover.wav"
        voiceover_path = cached_voiceover if cached_voiceover.exists() else generate_story_voiceover(story)
        validate_voiceover_duration(story, voiceover_path)

    result = render_premium_story(story, voiceover_path=voiceover_path)
    logging.info("Rendered video: %s", result.output_path)

    upload_video_path = None
    if args.prepare_youtube or args.upload_youtube:
        upload_video_path = prepare_youtube_upload(result.output_path, story)
        logging.info("Prepared YouTube upload package: %s", upload_video_path)

    if args.upload_youtube:
        metadata = build_youtube_metadata(story)
        uploaded = upload_video(
            video_path=upload_video_path or result.output_path,
            title=metadata.title,
            description=metadata.description,
            tags=metadata.tags,
            privacy_status=metadata.privacy_status,
        )
        logging.info("YouTube uploaded: %s", uploaded["video_url"])
        youtube_url = uploaded["video_url"]
    else:
        youtube_url = None

    if args.upload_instagram:
        instagram_video_url = args.instagram_video_url
        if args.cloudinary or not instagram_video_url:
            instagram_video_url = upload_video_to_cloudinary(result.output_path, public_id=story.story_id)

        instagram = publish_instagram_reel(
            video_path=result.output_path,
            caption=build_instagram_caption(story),
            video_url=instagram_video_url,
        )
        logging.info("Instagram Reel published: %s", instagram.get("permalink") or instagram["media_id"])
        instagram_url = instagram.get("permalink") or instagram["media_id"]
    else:
        instagram_url = None

    if args.upload_youtube or args.upload_instagram:
        record_published_story(story, youtube_url=youtube_url, instagram_url=instagram_url)
        logging.info("Recorded published story: %s", story.story_id)


def prepare_youtube_upload(video_path: Path, story) -> Path:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    target_video = UPLOADS_DIR / video_path.name
    shutil.copy2(video_path, target_video)

    metadata = build_youtube_metadata(story)
    metadata_path = target_video.with_suffix(".json")
    metadata_path.write_text(
        json.dumps(
            {
                "title": metadata.title,
                "description": metadata.description,
                "tags": metadata.tags,
                "privacy_status": metadata.privacy_status,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return target_video


def validate_voiceover_duration(story, voiceover_path: Path) -> None:
    screens = split_into_story_screens(story.body)
    expected_duration = sum(duration for _, duration in calculate_screen_timings(screens))
    actual_duration = get_media_duration_seconds(voiceover_path)
    min_duration = max(8.0, expected_duration * 0.55)
    max_duration = min(58.0, max(expected_duration * 1.55, expected_duration + 10.0))

    if actual_duration < min_duration or actual_duration > max_duration:
        voiceover_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"Voice-over duration looks wrong for {story.story_id}: "
            f"{actual_duration:.1f}s generated, expected around {expected_duration:.1f}s. "
            "Deleted the bad voice-over so the next run can regenerate it."
        )


if __name__ == "__main__":
    main()
