import argparse
import logging
import shutil
from pathlib import Path

from auth import get_credentials
from config import SUPPORTED_VIDEO_EXTENSIONS, UPLOADED_DIR, UPLOADS_DIR
from uploader import load_metadata_for_video, upload_video


logger = logging.getLogger(__name__)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def find_videos(upload_dir: Path = UPLOADS_DIR) -> list[Path]:
    if not upload_dir.exists():
        upload_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Created uploads folder: %s", upload_dir)
        return []

    return sorted(
        path
        for path in upload_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS
    )


def upload_pending_videos(
    upload_dir: Path = UPLOADS_DIR,
    move_uploaded: bool = False,
    limit: int | None = None,
) -> list[dict[str, str]]:
    videos = find_videos(upload_dir)
    if limit is not None:
        videos = videos[:limit]

    if not videos:
        logger.info("No videos found in %s", upload_dir)
        return []

    results = []
    for video_path in videos:
        metadata = load_metadata_for_video(video_path)
        result = upload_video(
            video_path=video_path,
            title=metadata.title,
            description=metadata.description,
            tags=metadata.tags,
            privacy_status=metadata.privacy_status,
            category_id=metadata.category_id,
            made_for_kids=metadata.made_for_kids,
        )
        results.append(result)

        if move_uploaded:
            move_to_uploaded(video_path)

    return results


def move_to_uploaded(video_path: Path) -> None:
    UPLOADED_DIR.mkdir(parents=True, exist_ok=True)
    target = UPLOADED_DIR / video_path.name
    shutil.move(str(video_path), str(target))

    metadata_path = video_path.with_suffix(".json")
    if metadata_path.exists():
        shutil.move(str(metadata_path), str(UPLOADED_DIR / metadata_path.name))

    logger.info("Moved uploaded file to %s", target)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload YouTube Shorts from the uploads folder.")
    parser.add_argument("--uploads-dir", type=Path, default=UPLOADS_DIR)
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of videos to upload.")
    parser.add_argument(
        "--auth-only",
        action="store_true",
        help="Authenticate with YouTube and create or refresh token.json without uploading videos.",
    )
    parser.add_argument(
        "--move-uploaded",
        action="store_true",
        help="Move uploaded videos and metadata files to the uploaded folder.",
    )
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()

    if args.auth_only:
        get_credentials()
        logger.info("YouTube authentication is ready.")
        return

    results = upload_pending_videos(
        upload_dir=args.uploads_dir,
        move_uploaded=args.move_uploaded,
        limit=args.limit,
    )

    for result in results:
        logger.info("Uploaded video: %s", result["video_url"])


if __name__ == "__main__":
    main()
