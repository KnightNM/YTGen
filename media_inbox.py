"""Prepare and monitor a human-in-the-loop scene media inbox."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path

from script_engine import Story


SUPPORTED_EXTENSIONS = (".mp4", ".mov", ".m4v", ".webm", ".png", ".jpg", ".jpeg", ".webp")


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:48] or "horror-short"


def prepare_media_inbox(story: Story, root: Path) -> Path:
    """Create a unique folder containing numbered prompts and an asset manifest."""
    job_name = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{_slug(story.title)}"
    inbox = root / "output" / "media_inbox" / job_name
    inbox.mkdir(parents=True, exist_ok=False)
    scenes = []
    for index, (narration, prompt) in enumerate(
        zip(story.narration_segments, story.image_prompts), start=1
    ):
        stem = f"scene_{index:03d}"
        (inbox / f"{stem}.txt").write_text(
            f"NARRATION\n{narration}\n\nGENERATION PROMPT\n{prompt}\n", encoding="utf-8"
        )
        scenes.append({"index": index, "stem": stem, "narration": narration, "prompt": prompt})

    (inbox / "manifest.json").write_text(
        json.dumps({"title": story.title, "scenes": scenes}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (inbox / "README.txt").write_text(
        "Generate or download one image or video per prompt.\n"
        "Save each asset beside its prompt as scene_001.png, scene_002.mp4, etc.\n"
        "Use vertical 9:16 output where available. Files are scaled and center-cropped, never stretched.\n"
        "Supported formats: " + ", ".join(SUPPORTED_EXTENSIONS) + "\n",
        encoding="utf-8",
    )
    state_path = root / "output" / "scripts" / "hybrid_job.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"media_dir": str(inbox), "story_file": str(root / "output/scripts/story.json")}, indent=2),
        encoding="utf-8",
    )
    return inbox


def load_current_media_dir(root: Path) -> Path:
    state_path = root / "output" / "scripts" / "hybrid_job.json"
    if not state_path.exists():
        raise FileNotFoundError("No prepared hybrid job exists; run the prepare phase first")
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    return Path(payload["media_dir"]).expanduser().resolve()


def collect_scene_media(inbox: Path, count: int) -> tuple[list[Path], list[str]]:
    found: list[Path] = []
    missing: list[str] = []
    for index in range(1, count + 1):
        stem = f"scene_{index:03d}"
        matches = [inbox / f"{stem}{extension}" for extension in SUPPORTED_EXTENSIONS]
        matches = [path for path in matches if path.is_file() and path.stat().st_size > 0]
        if len(matches) == 1:
            found.append(matches[0])
        elif not matches:
            missing.append(stem)
        else:
            raise ValueError(f"Multiple media files found for {stem}: {', '.join(map(str, matches))}")
    return found, missing


def wait_for_scene_media(inbox: Path, count: int, timeout_seconds: int) -> list[Path]:
    """Poll a local directory until every numbered scene asset is present and stable."""
    deadline = time.monotonic() + timeout_seconds
    last_missing: tuple[str, ...] | None = None
    while True:
        media, missing = collect_scene_media(inbox, count)
        if not missing:
            sizes = [path.stat().st_size for path in media]
            time.sleep(1)
            if sizes == [path.stat().st_size for path in media]:
                return media
        marker = tuple(missing)
        if marker != last_missing:
            print(f"Waiting for {len(missing)} scene asset(s): {', '.join(missing)}")
            last_missing = marker
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Timed out waiting for scene media in {inbox}")
        time.sleep(2)
