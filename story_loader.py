import re
import random
import json
from dataclasses import dataclass
from pathlib import Path

from config import APPROVED_STORIES_DIR, OUTPUT_DIR, PROJECT_ROOT, STORIES_DIR


@dataclass(frozen=True)
class Story:
    story_id: str
    path: Path
    title: str
    mood: str | None
    body: str


def find_unused_story(stories_dir: Path = STORIES_DIR, output_dir: Path = OUTPUT_DIR) -> Story:
    stories = list_story_paths(stories_dir)
    if not stories:
        raise FileNotFoundError(f"No .txt stories found in {stories_dir}")

    for story_path in stories:
        output_path = output_dir / f"{story_path.stem}_v4.mp4"
        if not output_path.exists():
            return load_story(story_path)

    raise RuntimeError("All stories already have rendered videos in the output folder.")


def find_pending_approved_story(
    stories_dir: Path = APPROVED_STORIES_DIR,
    output_dir: Path = OUTPUT_DIR,
    selection: str = "sequential",
) -> Story:
    published_ids = _load_published_story_ids()
    stories = [
        path
        for path in list_story_paths(stories_dir)
        if path.stem not in published_ids and not (output_dir / f"{path.stem}_v4.mp4").exists()
    ]
    if not stories:
        raise RuntimeError("All approved stories already have rendered videos in the output folder.")
    if selection == "random":
        return load_story(random.choice(stories))
    return load_story(stories[0])


def _load_published_story_ids() -> set[str]:
    path = PROJECT_ROOT / "state" / "published_stories.json"
    if not path.exists():
        return set()

    data = json.loads(path.read_text(encoding="utf-8"))
    return {item["story_id"] for item in data.get("stories", []) if item.get("story_id")}


def list_story_paths(stories_dir: Path = STORIES_DIR) -> list[Path]:
    if not stories_dir.exists():
        return []

    return sorted(
        path
        for path in stories_dir.rglob("*.txt")
        if path.is_file() and not path.name.startswith(".")
    )


def load_story(story_path: str | Path) -> Story:
    path = Path(story_path)
    if not path.exists():
        raise FileNotFoundError(f"Story file does not exist: {path}")

    raw_text = path.read_text(encoding="utf-8").strip()
    if not raw_text:
        raise ValueError(f"Story file is empty: {path}")

    title, mood, body = _parse_story_text(raw_text, path.stem)
    return Story(story_id=path.stem, path=path, title=title, mood=mood, body=body)


def _parse_story_text(raw_text: str, fallback_title: str) -> tuple[str, str | None, str]:
    title = fallback_title.replace("_", " ").title()
    mood = None
    body_lines = []

    for line in raw_text.splitlines():
        stripped = line.strip()
        title_match = re.match(r"^TITLE\s*:\s*(.+)$", stripped, flags=re.IGNORECASE)
        mood_match = re.match(r"^MOOD\s*:\s*(.+)$", stripped, flags=re.IGNORECASE)

        if title_match:
            title = title_match.group(1).strip()
            continue
        if mood_match:
            mood = mood_match.group(1).strip().lower().replace(" ", "_")
            continue

        body_lines.append(line)

    body = "\n".join(body_lines).strip()
    if not body:
        raise ValueError("Story body is empty after TITLE/MOOD metadata.")

    return title, mood, body
