import json
import logging
import mimetypes
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from auth import get_credentials
from config import DEFAULT_CATEGORY_ID, DEFAULT_PRIVACY_STATUS


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UploadMetadata:
    title: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    privacy_status: str = DEFAULT_PRIVACY_STATUS
    category_id: str = DEFAULT_CATEGORY_ID
    made_for_kids: bool = False


def get_youtube_service():
    """Create an authenticated YouTube Data API client."""
    credentials = get_credentials()
    return build("youtube", "v3", credentials=credentials)


def upload_video(
    video_path: str | Path,
    title: str,
    description: str = "",
    tags: Iterable[str] | None = None,
    privacy_status: str = DEFAULT_PRIVACY_STATUS,
    category_id: str = DEFAULT_CATEGORY_ID,
    made_for_kids: bool = False,
) -> dict[str, str]:
    """Upload a video to YouTube and return its ID and URL."""
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"Video file does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"Video path is not a file: {path}")

    youtube = get_youtube_service()
    media_type = mimetypes.guess_type(path.name)[0] or "video/mp4"
    media = MediaFileUpload(str(path), mimetype=media_type, chunksize=-1, resumable=True)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": list(tags or []),
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": made_for_kids,
        },
    }

    logger.info("Starting upload: %s", path.name)
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = _execute_resumable_upload(request)
    video_id = response["id"]
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    logger.info("Upload complete: %s", video_url)
    return {"video_id": video_id, "video_url": video_url}


def load_metadata_for_video(video_path: Path) -> UploadMetadata:
    """Load optional metadata from video_name.json, otherwise derive safe defaults."""
    metadata_path = video_path.with_suffix(".json")
    if not metadata_path.exists():
        return UploadMetadata(
            title=f"{video_path.stem} #Shorts",
            description="A short emotional story from The Ashy Notes.\n\n#Shorts #TheAshyNotes",
            tags=["Shorts", "The Ashy Notes", "emotional story", "life lesson"],
        )

    with metadata_path.open("r", encoding="utf-8") as file:
        raw = json.load(file)

    return UploadMetadata(
        title=raw["title"],
        description=raw.get("description", ""),
        tags=raw.get("tags", []),
        privacy_status=raw.get("privacy_status", DEFAULT_PRIVACY_STATUS),
        category_id=str(raw.get("category_id", DEFAULT_CATEGORY_ID)),
        made_for_kids=bool(raw.get("made_for_kids", False)),
    )


def _execute_resumable_upload(request, max_retries: int = 5) -> dict:
    response = None
    retry = 0

    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                logger.info("Upload progress: %.1f%%", status.progress() * 100)
        except HttpError as error:
            if error.resp.status not in {500, 502, 503, 504} or retry >= max_retries:
                raise
            retry += 1
            sleep_seconds = min(2**retry, 60)
            logger.warning(
                "Temporary YouTube API error %s. Retrying in %s seconds.",
                error.resp.status,
                sleep_seconds,
            )
            time.sleep(sleep_seconds)

    if "id" not in response:
        raise RuntimeError(f"YouTube upload failed. API response: {response}")

    return response
