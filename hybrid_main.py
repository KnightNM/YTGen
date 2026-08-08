"""Hybrid subscription-authenticated story, local media, render, and upload CLI."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

from audio_engine import DEFAULT_VOICE, SUPPORTED_VOICES, SegmentTiming, synthesize_narration
from setup import initialize_project


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare prompts with Codex, then assemble manually downloaded scene media locally."
    )
    parser.add_argument("--phase", choices=("prepare", "render", "all"), default="prepare")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--topic", help="Premise sent to the locally authenticated Codex CLI")
    source.add_argument("--story-file", help="Pre-authored story JSON using the documented schema")
    parser.add_argument("--media-dir", help="Folder containing scene_001.png/mp4, scene_002, etc.")
    parser.add_argument(
        "--wait-seconds", type=int, default=3600,
        help="How long --phase all waits for media files (default: 3600)",
    )
    parser.add_argument("--voice", choices=sorted(SUPPORTED_VOICES), default=DEFAULT_VOICE)
    parser.add_argument("--privacy", choices=("private", "unlisted", "public"), default="private")
    parser.add_argument("--seed", type=int, default=7331)
    parser.add_argument("--skip-upload", action="store_true")
    parser.add_argument("--debug", action="store_true")
    return parser


def _load_story(path: Path):
    from script_engine import Story

    if not path.exists():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Story JSON must contain one object")
    return Story.from_dict(payload)


def _load_timings(path: Path) -> list[SegmentTiming]:
    if not path.exists():
        raise FileNotFoundError(f"Narration timings are missing; run prepare first: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [SegmentTiming(**item) for item in payload]


def _prepare(args: argparse.Namespace, root: Path):
    from codex_story_engine import generate_story_with_codex
    from media_inbox import prepare_media_inbox
    from script_engine import load_validated_story

    story_output = root / "output" / "scripts" / "story.json"
    if args.story_file:
        story = load_validated_story(Path(args.story_file).expanduser().resolve(), story_output)
    elif args.topic:
        print("[1/3] Generating structured story through Codex subscription auth...")
        story = generate_story_with_codex(args.topic, root, story_output)
    else:
        raise ValueError("prepare/all requires either --topic or --story-file")

    print("[2/3] Synthesizing narration and exact subtitle timings...")
    synthesize_narration(story.narration_segments, root / "output" / "audio", args.voice)
    print("[3/3] Creating numbered local media inbox...")
    inbox = prepare_media_inbox(story, root)
    print(f"Prepared: {inbox}")
    print("Add one scene_### image or video for every .txt prompt, then run:")
    print(f'  python hybrid_main.py --phase render --media-dir "{inbox}"')
    return story, inbox


def _render(args: argparse.Namespace, root: Path, story=None, inbox: Path | None = None) -> Path:
    from assets_engine import get_or_create_background
    from hybrid_composer import compose_hybrid_video
    from media_inbox import collect_scene_media, load_current_media_dir, wait_for_scene_media
    from youtube_uploader import upload_video

    story = story or _load_story(root / "output" / "scripts" / "story.json")
    inbox = inbox or (
        Path(args.media_dir).expanduser().resolve() if args.media_dir else load_current_media_dir(root)
    )
    if args.phase == "all":
        media = wait_for_scene_media(inbox, len(story.narration_segments), args.wait_seconds)
    else:
        media, missing = collect_scene_media(inbox, len(story.narration_segments))
        if missing:
            raise FileNotFoundError(
                f"Missing {len(missing)} scene asset(s) in {inbox}: {', '.join(missing)}"
            )

    timings = _load_timings(root / "output" / "audio" / "narration_timings.json")
    narration = root / "output" / "audio" / "master_narration.wav"
    ambient = get_or_create_background(root / "assets", seed=args.seed)
    print("Rendering local images/clips, narration, ambience, and burn-in subtitles...")
    result = compose_hybrid_video(
        media, narration, timings, ambient, root / "output" / "video" / "hybrid_short.mp4"
    )
    if args.skip_upload:
        print(f"Upload skipped. Video saved at {result}")
    else:
        upload_video(result, story, root, privacy_status=args.privacy)
    return result


def run(args: argparse.Namespace) -> int:
    root = initialize_project(require_gemini=False).project_root
    if args.wait_seconds < 1:
        raise ValueError("--wait-seconds must be positive")
    if args.phase in {"prepare", "all"}:
        story, inbox = _prepare(args, root)
        if args.phase == "prepare":
            return 0
        result = _render(args, root, story, inbox)
    else:
        result = _render(args, root)
    print(f"Done: {result}")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    try:
        return run(args)
    except KeyboardInterrupt:
        print("\nCancelled by user.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"\nHybrid pipeline failed: {exc}", file=sys.stderr)
        if args.debug:
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
