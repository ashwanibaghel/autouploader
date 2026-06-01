import logging
import os
import time
from pathlib import Path
from urllib.parse import quote

import requests

from config import (
    DEFAULT_INSTAGRAM_GRAPH_BASE_URL,
    DEFAULT_INSTAGRAM_GRAPH_API_VERSION,
    INSTAGRAM_ACCESS_TOKEN_ENV,
    INSTAGRAM_GRAPH_BASE_URL_ENV,
    INSTAGRAM_GRAPH_API_VERSION_ENV,
    INSTAGRAM_PUBLIC_VIDEO_BASE_URL_ENV,
    INSTAGRAM_USER_ID_ENV,
    PROJECT_ROOT,
)


logger = logging.getLogger(__name__)


def publish_instagram_reel(
    video_path: str | Path,
    caption: str,
    video_url: str | None = None,
    share_to_feed: bool = True,
    poll_interval_seconds: int = 10,
    max_wait_seconds: int = 600,
) -> dict[str, str]:
    """Publish a video as an Instagram Reel using the Instagram Graph API."""
    load_dotenv_if_present()
    access_token = require_env(INSTAGRAM_ACCESS_TOKEN_ENV)
    ig_user_id = require_env(INSTAGRAM_USER_ID_ENV)
    graph_version = os.environ.get(
        INSTAGRAM_GRAPH_API_VERSION_ENV,
        DEFAULT_INSTAGRAM_GRAPH_API_VERSION,
    )
    graph_base_url = get_graph_base_url()

    path = Path(video_path)
    final_video_url = video_url or build_public_video_url(path)

    container_id = create_reel_container(
        ig_user_id=ig_user_id,
        graph_base_url=graph_base_url,
        graph_version=graph_version,
        access_token=access_token,
        video_url=final_video_url,
        caption=caption,
        share_to_feed=share_to_feed,
    )
    wait_for_container_ready(
        container_id=container_id,
        graph_base_url=graph_base_url,
        graph_version=graph_version,
        access_token=access_token,
        poll_interval_seconds=poll_interval_seconds,
        max_wait_seconds=max_wait_seconds,
    )
    media_id = publish_container(
        ig_user_id=ig_user_id,
        graph_base_url=graph_base_url,
        graph_version=graph_version,
        access_token=access_token,
        container_id=container_id,
    )
    permalink = get_media_permalink(media_id, graph_base_url, graph_version, access_token)
    return {"media_id": media_id, "permalink": permalink or "", "video_url": final_video_url}


def create_reel_container(
    ig_user_id: str,
    graph_base_url: str,
    graph_version: str,
    access_token: str,
    video_url: str,
    caption: str,
    share_to_feed: bool,
) -> str:
    response = requests.post(
        f"{graph_base_url}/{graph_version}/{ig_user_id}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": str(share_to_feed).lower(),
            "access_token": access_token,
        },
        timeout=60,
    )
    payload = parse_graph_response(response)
    container_id = payload.get("id")
    if not container_id:
        raise RuntimeError(f"Instagram did not return a container id: {payload}")
    logger.info("Instagram container created: %s", container_id)
    return container_id


def wait_for_container_ready(
    container_id: str,
    graph_base_url: str,
    graph_version: str,
    access_token: str,
    poll_interval_seconds: int,
    max_wait_seconds: int,
) -> None:
    deadline = time.monotonic() + max_wait_seconds
    while time.monotonic() < deadline:
        response = requests.get(
            f"{graph_base_url}/{graph_version}/{container_id}",
            params={"fields": "status_code,status", "access_token": access_token},
            timeout=30,
        )
        payload = parse_graph_response(response)
        status_code = payload.get("status_code")
        status = payload.get("status")
        logger.info("Instagram container status: %s %s", status_code, status or "")

        if status_code == "FINISHED":
            return
        if status_code in {"ERROR", "EXPIRED"}:
            raise RuntimeError(f"Instagram container failed: {payload}")
        time.sleep(poll_interval_seconds)

    raise TimeoutError(f"Instagram container was not ready after {max_wait_seconds} seconds.")


def publish_container(
    ig_user_id: str,
    graph_base_url: str,
    graph_version: str,
    access_token: str,
    container_id: str,
) -> str:
    response = requests.post(
        f"{graph_base_url}/{graph_version}/{ig_user_id}/media_publish",
        data={"creation_id": container_id, "access_token": access_token},
        timeout=60,
    )
    payload = parse_graph_response(response)
    media_id = payload.get("id")
    if not media_id:
        raise RuntimeError(f"Instagram did not return a media id: {payload}")
    logger.info("Instagram Reel published: %s", media_id)
    return media_id


def get_media_permalink(
    media_id: str,
    graph_base_url: str,
    graph_version: str,
    access_token: str,
) -> str | None:
    response = requests.get(
        f"{graph_base_url}/{graph_version}/{media_id}",
        params={"fields": "permalink", "access_token": access_token},
        timeout=30,
    )
    payload = parse_graph_response(response)
    return payload.get("permalink")


def build_public_video_url(video_path: Path) -> str:
    base_url = os.environ.get(INSTAGRAM_PUBLIC_VIDEO_BASE_URL_ENV, "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError(
            f"Missing {INSTAGRAM_PUBLIC_VIDEO_BASE_URL_ENV}. Instagram needs a public HTTPS "
            "direct MP4 URL, not a local file path."
        )
    return f"{base_url}/{quote(video_path.name)}"


def get_graph_base_url() -> str:
    value = os.environ.get(INSTAGRAM_GRAPH_BASE_URL_ENV, DEFAULT_INSTAGRAM_GRAPH_BASE_URL)
    return value.strip().rstrip("/")


def parse_graph_response(response: requests.Response) -> dict:
    try:
        payload = response.json()
    except ValueError as error:
        raise RuntimeError(f"Instagram returned non-JSON response: {response.text}") from error

    if not response.ok or "error" in payload:
        raise RuntimeError(f"Instagram API error: {payload}")
    return payload


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing {name}. Add it to .env.")
    return value


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
