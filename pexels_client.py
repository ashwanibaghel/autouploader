import logging
import os
import random
from pathlib import Path
from urllib.parse import urlparse

import requests

from config import DOWNLOADS_DIR, PEXELS_API_KEY_ENV


logger = logging.getLogger(__name__)
PEXELS_VIDEO_SEARCH_URL = "https://api.pexels.com/videos/search"


def download_stock_videos(
    keywords: list[str],
    story_id: str,
    target_count: int = 4,
    downloads_dir: Path = DOWNLOADS_DIR,
) -> list[Path]:
    api_key = os.getenv(PEXELS_API_KEY_ENV)
    if not api_key:
        raise RuntimeError(
            f"Missing Pexels API key. Set it first: $env:{PEXELS_API_KEY_ENV}='your_api_key'"
        )

    story_download_dir = downloads_dir / story_id
    story_download_dir.mkdir(parents=True, exist_ok=True)

    downloaded = list(story_download_dir.glob("*.mp4"))
    if len(downloaded) >= target_count:
        return downloaded[:target_count]

    headers = {"Authorization": api_key}
    candidates = []

    for keyword in keywords:
        params = {
            "query": keyword,
            "orientation": "portrait",
            "size": "large",
            "per_page": 8,
        }
        logger.info("Searching Pexels videos for: %s", keyword)
        response = requests.get(PEXELS_VIDEO_SEARCH_URL, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        videos = response.json().get("videos", [])
        candidates.extend(_extract_video_files(videos))

    random.shuffle(candidates)

    for index, candidate in enumerate(candidates, start=1):
        if len(downloaded) >= target_count:
            break
        target = story_download_dir / f"clip_{len(downloaded) + 1:02d}.mp4"
        logger.info("Downloading Pexels clip: %s", target.name)
        _download_file(candidate["link"], target)
        downloaded.append(target)

    if not downloaded:
        raise RuntimeError("No Pexels videos could be downloaded for this story.")

    return downloaded


def _extract_video_files(videos: list[dict]) -> list[dict]:
    candidates = []
    for video in videos:
        duration = video.get("duration", 0)
        for file_info in video.get("video_files", []):
            width = file_info.get("width") or 0
            height = file_info.get("height") or 0
            link = file_info.get("link")
            quality = file_info.get("quality")
            if not link or width <= 0 or height <= 0:
                continue
            if height < width:
                continue
            if height < 1280:
                continue
            candidates.append(
                {
                    "link": link,
                    "width": width,
                    "height": height,
                    "quality": quality,
                    "duration": duration,
                }
            )

    return sorted(candidates, key=lambda item: (item["height"], item["width"]), reverse=True)


def _download_file(url: str, target: Path) -> None:
    suffix = Path(urlparse(url).path).suffix
    if suffix and target.suffix != suffix:
        target = target.with_suffix(suffix)

    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with target.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file.write(chunk)
