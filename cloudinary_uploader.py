import logging
import os
from pathlib import Path

import cloudinary
import cloudinary.uploader

from config import (
    CLOUDINARY_API_KEY_ENV,
    CLOUDINARY_API_SECRET_ENV,
    CLOUDINARY_CLOUD_NAME_ENV,
    CLOUDINARY_FOLDER_ENV,
    DEFAULT_CLOUDINARY_FOLDER,
    PROJECT_ROOT,
)


logger = logging.getLogger(__name__)


def upload_video_to_cloudinary(video_path: str | Path, public_id: str | None = None) -> str:
    """Upload a rendered MP4 to Cloudinary and return its public HTTPS URL."""
    load_dotenv_if_present()
    cloud_name = require_env(CLOUDINARY_CLOUD_NAME_ENV)
    api_key = require_env(CLOUDINARY_API_KEY_ENV)
    api_secret = require_env(CLOUDINARY_API_SECRET_ENV)
    folder = os.environ.get(CLOUDINARY_FOLDER_ENV, DEFAULT_CLOUDINARY_FOLDER).strip("/")

    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"Video file does not exist: {path}")

    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True,
    )

    logger.info("Uploading video to Cloudinary: %s", path.name)
    result = cloudinary.uploader.upload_large(
        str(path),
        resource_type="video",
        folder=folder,
        public_id=public_id or path.stem,
        overwrite=True,
        unique_filename=False,
        use_filename=True,
    )

    secure_url = result.get("secure_url")
    if not secure_url:
        raise RuntimeError(f"Cloudinary upload did not return secure_url: {result}")

    logger.info("Cloudinary video URL ready: %s", secure_url)
    return secure_url


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
