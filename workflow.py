"""Stateful controller for the gated hybrid horror-video workflow."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "output" / "scripts" / "workflow_state.json"


@dataclass
class WorkflowState:
    version: int
    stage: str
    topic: str
    title: str
    story_file: str
    media_dir: str
    video_file: str
    privacy: str
    uploaded_url: str | None
    updated_at: str

    @classmethod
    def load(cls) -> "WorkflowState":
        if not STATE_PATH.exists():
            raise FileNotFoundError("No workflow exists yet. Start one with `workflow.py start`.")
        return cls(**json.loads(STATE_PATH.read_text(encoding="utf-8")))

    def save(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = STATE_PATH.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        temporary.replace(STATE_PATH)


def _run(command: list[str]) -> None:
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode:
        raise RuntimeError(f"Workflow command failed with exit code {result.returncode}")


def _story(path: Path):
    from script_engine import Story

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Story file must contain one JSON object")
    return Story.from_dict(payload)


def _refresh(state: WorkflowState) -> tuple[int, list[str]]:
    from media_inbox import collect_scene_media

    story = _story(Path(state.story_file))
    media, missing = collect_scene_media(Path(state.media_dir), len(story.narration_segments))
    if not missing and state.stage == "awaiting_media":
        state.stage = "ready_to_render"
        state.save()
    return len(media), missing


def _nudge(state: WorkflowState, media_count: int, missing: list[str]) -> str:
    if state.stage == "awaiting_media":
        return (
            f"Generate {len(missing)} remaining ImageGen scene(s) in {state.media_dir}: "
            f"{', '.join(missing)}"
        )
    if state.stage == "ready_to_render":
        return "All scene media is ready. Ask Codex to render, or run `python workflow.py render`."
    if state.stage == "awaiting_upload_approval":
        return (
            "The local video is ready. Explicitly say `post it to YouTube` to approve a private "
            "upload, or specify unlisted/public."
        )
    if state.stage == "uploaded":
        return f"Workflow complete: {state.uploaded_url}"
    return f"Unknown workflow stage {state.stage!r}; inspect {STATE_PATH}."


def status_command(_args: argparse.Namespace) -> int:
    try:
        state = WorkflowState.load()
    except FileNotFoundError as exc:
        print(f"Stage: not_started\nNudge: {exc}")
        return 0
    count, missing = _refresh(state)
    print(f"Stage: {state.stage}")
    print(f"Title: {state.title}")
    print(f"Media: {count} ready, {len(missing)} missing")
    print(f"Video: {state.video_file}")
    if state.uploaded_url:
        print(f"YouTube: {state.uploaded_url}")
    print(f"Nudge: {_nudge(state, count, missing)}")
    return 0


def start_command(args: argparse.Namespace) -> int:
    command = [sys.executable, "hybrid_main.py", "--phase", "prepare", "--voice", args.voice]
    if args.topic:
        command.extend(["--topic", args.topic])
        topic = args.topic
    else:
        source = Path(args.story_file).expanduser().resolve()
        command.extend(["--story-file", str(source)])
        topic = f"Story file: {source.name}"
    _run(command)

    job = json.loads((ROOT / "output/scripts/hybrid_job.json").read_text(encoding="utf-8"))
    story_path = Path(job["story_file"])
    story = _story(story_path)
    state = WorkflowState(
        version=1,
        stage="awaiting_media",
        topic=topic,
        title=story.title,
        story_file=str(story_path),
        media_dir=str(Path(job["media_dir"])),
        video_file=str(ROOT / "output/video/hybrid_short.mp4"),
        privacy="private",
        uploaded_url=None,
        updated_at="",
    )
    state.save()
    return status_command(args)


def render_command(args: argparse.Namespace) -> int:
    state = WorkflowState.load()
    _, missing = _refresh(state)
    if missing:
        raise RuntimeError(f"Cannot render; missing scene media: {', '.join(missing)}")
    if state.stage == "uploaded":
        raise RuntimeError("This workflow is already uploaded; start a new workflow instead")
    _run([
        sys.executable,
        "hybrid_main.py",
        "--phase",
        "render",
        "--media-dir",
        state.media_dir,
        "--skip-upload",
    ])
    state.stage = "awaiting_upload_approval"
    state.save()
    return status_command(args)


def upload_command(args: argparse.Namespace) -> int:
    if not args.confirm_upload:
        raise PermissionError(
            "Upload requires explicit approval: add `--confirm-upload` only after the user asks to post"
        )
    state = WorkflowState.load()
    if state.stage == "uploaded":
        raise RuntimeError(f"Refusing a duplicate upload; already posted at {state.uploaded_url}")
    if state.stage != "awaiting_upload_approval":
        raise RuntimeError("Render the workflow successfully before uploading")
    video = Path(state.video_file)
    if not video.exists() or video.stat().st_size == 0:
        raise FileNotFoundError(video)

    from youtube_uploader import upload_video

    url = upload_video(video, _story(Path(state.story_file)), ROOT, privacy_status=args.privacy)
    if not url:
        raise RuntimeError("YouTube OAuth is not configured; the video remains local")
    state.stage = "uploaded"
    state.privacy = args.privacy
    state.uploaded_url = url
    state.save()
    return status_command(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run and inspect the gated horror-video workflow")
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start", help="Generate story, narration, and scene prompt inbox")
    source = start.add_mutually_exclusive_group(required=True)
    source.add_argument("--topic")
    source.add_argument("--story-file")
    start.add_argument("--voice", default="en-US-BrianMultilingualNeural")
    start.set_defaults(handler=start_command)
    for name in ("status", "nudge"):
        item = commands.add_parser(name, help="Show current stage and next required action")
        item.set_defaults(handler=status_command)
    render = commands.add_parser("render", help="Render locally after every scene asset exists")
    render.set_defaults(handler=render_command)
    upload = commands.add_parser("upload", help="Upload only after explicit user approval")
    upload.add_argument("--confirm-upload", action="store_true")
    upload.add_argument("--privacy", choices=("private", "unlisted", "public"), default="private")
    upload.set_defaults(handler=upload_command)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.handler(args)
    except (FileNotFoundError, PermissionError, RuntimeError, ValueError) as exc:
        print(f"Workflow blocked: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
