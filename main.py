"""CLI orchestrator for the autonomous horror short pipeline."""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from setup import initialize_project


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate and optionally upload a vertical YouTube horror short."
    )
    story_source = parser.add_mutually_exclusive_group(required=True)
    story_source.add_argument("--topic", help="Story premise or horror topic for Gemini")
    story_source.add_argument(
        "--story-file",
        help="Validated JSON story authored externally (used by the Codex automation)",
    )
    parser.add_argument(
        "--voice",
        choices=(
            "en-US-BrianMultilingualNeural",
            "en-US-AndrewMultilingualNeural",
            "en-US-GuyNeural",
            "en-US-ChristopherNeural",
            "en-US-EricNeural",
        ),
        default="en-US-BrianMultilingualNeural",
        help="Edge neural narration voice (default: casual, sincere Brian)",
    )
    parser.add_argument(
        "--privacy",
        choices=("private", "unlisted", "public"),
        default="private",
        help="YouTube privacy status when auto-upload is configured",
    )
    parser.add_argument("--seed", type=int, default=7331, help="Visual and drone seed")
    parser.add_argument("--skip-upload", action="store_true", help="Always keep the result local")
    parser.add_argument("--debug", action="store_true", help="Print a traceback after an error")
    return parser


def run(args: argparse.Namespace) -> int:
    initialization = initialize_project(require_gemini=not bool(args.story_file))
    root = initialization.project_root

    # Import after first-run initialization so missing credentials fail clearly.
    from assets_engine import get_or_create_background
    from audio_engine import synthesize_narration
    from script_engine import generate_story, load_validated_story
    from video_composer import compose_video
    from visual_engine import download_images
    from youtube_uploader import upload_video

    story_output = root / "output" / "scripts" / "story.json"
    if args.story_file:
        print("[1/6] Loading and validating Codex-authored story...")
        story = load_validated_story(Path(args.story_file).expanduser().resolve(), story_output)
    else:
        print("[1/6] Generating and validating story with Gemini...")
        story = generate_story(args.topic, story_output)

    print("[2/6] Synthesizing narration with Edge TTS...")
    narration = synthesize_narration(
        story.narration_segments, root / "output" / "audio", voice=args.voice
    )

    print("[3/6] Acquiring vertical horror visuals from Pollinations.ai...")
    images = download_images(
        story.image_prompts,
        root / "output" / "images",
        narration_segments=story.narration_segments,
        seed=args.seed,
    )

    print("[4/6] Preparing ambient soundtrack...")
    ambient = get_or_create_background(root / "assets", seed=args.seed)

    print("[5/6] Rendering 1080x1920 video with subtitles...")
    final_path = compose_video(
        images,
        narration.audio_path,
        narration.timings,
        ambient,
        root / "output" / "video" / "final_short.mp4",
    )

    print("[6/6] Handling YouTube upload...")
    if args.skip_upload:
        print(f"Upload skipped by request. Video saved at {final_path}")
    else:
        upload_video(final_path, story, root, privacy_status=args.privacy)

    print(f"Done: {final_path}")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    try:
        return run(args)
    except KeyboardInterrupt:
        print("\nCancelled by user.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"\nPipeline failed: {exc}", file=sys.stderr)
        if args.debug or __import__("os").getenv("DEBUG") == "1":
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
