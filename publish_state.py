import json
from datetime import datetime, timezone
from pathlib import Path

from config import PROJECT_ROOT
from story_loader import Story


STATE_DIR = PROJECT_ROOT / "state"
PUBLISHED_STORIES_FILE = STATE_DIR / "published_stories.json"


def load_published_story_ids(path: Path = PUBLISHED_STORIES_FILE) -> set[str]:
    if not path.exists():
        return set()

    data = json.loads(path.read_text(encoding="utf-8"))
    return {item["story_id"] for item in data.get("stories", []) if item.get("story_id")}


def record_published_story(
    story: Story,
    youtube_url: str | None = None,
    instagram_url: str | None = None,
    path: Path = PUBLISHED_STORIES_FILE,
) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    data = {"stories": []}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))

    stories = [item for item in data.get("stories", []) if item.get("story_id") != story.story_id]
    stories.append(
        {
            "story_id": story.story_id,
            "title": story.title,
            "mood": story.mood,
            "youtube_url": youtube_url,
            "instagram_url": instagram_url,
            "published_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    stories.sort(key=lambda item: item["published_at"])
    path.write_text(json.dumps({"stories": stories}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
