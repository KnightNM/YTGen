"""MoviePy/FFmpeg composition for a vertical narrated horror short."""

from __future__ import annotations

import math
from pathlib import Path

from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    concatenate_videoclips,
)
from moviepy.audio.fx.AudioLoop import AudioLoop

from audio_engine import SegmentTiming


FRAME_SIZE = (1080, 1920)
AMBIENT_GAIN = 10 ** (-18 / 20)
SUBTITLE_BOX_WIDTH = 860
SUBTITLE_TOP = 1050
SUBTITLE_SHADOW_OFFSET = 7
SUBTITLE_FONT_CANDIDATES = (
    Path("/System/Library/Fonts/Supplemental/Georgia Bold.ttf"),
    Path("C:/Windows/Fonts/georgiab.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"),
)


def _subtitle_font() -> str | None:
    """Select the reference-style bold serif font with portable fallbacks."""
    configured = __import__("os").getenv("SUBTITLE_FONT")
    if configured:
        path = Path(configured).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"SUBTITLE_FONT does not exist: {path}")
        return str(path)
    return next((str(path) for path in SUBTITLE_FONT_CANDIDATES if path.exists()), None)


def _cover_vertical(image_path: Path, duration: float, zoom_in: bool) -> CompositeVideoClip:
    """Scale to cover the canvas and apply a slow alternating Ken Burns zoom."""
    source = ImageClip(str(image_path)).with_duration(duration)
    scale_to_cover = max(FRAME_SIZE[0] / source.w, FRAME_SIZE[1] / source.h)
    covered = source.resized(scale_to_cover)
    direction = 1.0 if zoom_in else -1.0

    def scale_at_time(t: float) -> float:
        progress = min(max(t / max(duration, 0.001), 0.0), 1.0)
        return 1.04 + direction * 0.035 * (progress - (0.0 if zoom_in else 1.0))

    moving = covered.resized(scale_at_time).with_position(("center", "center"))
    return CompositeVideoClip([moving], size=FRAME_SIZE).with_duration(duration)


def _subtitle_clip(timing: SegmentTiming) -> TextClip:
    duration = max(timing.end - timing.start, 0.05)
    return (
        TextClip(
            text=timing.text,
            font=_subtitle_font(),
            font_size=70,
            color="white",
            stroke_color="#262626",
            stroke_width=3,
            method="caption",
            size=(SUBTITLE_BOX_WIDTH, None),
            text_align="center",
            margin=(24, 18),
        )
        .with_start(timing.start)
        .with_duration(duration)
        .with_position(("center", SUBTITLE_TOP))
    )


def _subtitle_shadow_clip(timing: SegmentTiming) -> TextClip:
    """Create the soft, low offset shadow visible in the reference treatment."""
    duration = max(timing.end - timing.start, 0.05)
    return (
        TextClip(
            text=timing.text,
            font=_subtitle_font(),
            font_size=70,
            color="#202020",
            stroke_color="#202020",
            stroke_width=3,
            method="caption",
            size=(SUBTITLE_BOX_WIDTH, None),
            text_align="center",
            margin=(24, 18),
        )
        .with_opacity(0.68)
        .with_start(timing.start)
        .with_duration(duration)
        .with_position(("center", SUBTITLE_TOP + SUBTITLE_SHADOW_OFFSET))
    )


def compose_video(
    image_paths: list[Path],
    narration_path: Path,
    timings: list[SegmentTiming],
    ambient_path: Path,
    output_path: Path,
    fps: int = 30,
) -> Path:
    """Compose images, mixed audio, and burned-in subtitles into an MP4."""
    if not timings or len(image_paths) != len(timings):
        raise ValueError("There must be exactly one image for each subtitle timing")
    for path in [*image_paths, narration_path, ambient_path]:
        if not path.exists():
            raise FileNotFoundError(path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    narration = AudioFileClip(str(narration_path))
    total_duration = narration.duration
    if total_duration <= 0:
        narration.close()
        raise ValueError("Narration audio has zero duration")

    scenes: list[CompositeVideoClip] = []
    subtitles: list[TextClip] = []
    ambient_source: AudioFileClip | None = None
    ambient_loop = None
    final = None
    montage = None
    try:
        boundaries = [item.start for item in timings] + [total_duration]
        for index, (image_path, timing) in enumerate(zip(image_paths, timings)):
            scene_duration = max(boundaries[index + 1] - timing.start, 0.05)
            scenes.append(_cover_vertical(image_path, scene_duration, zoom_in=index % 2 == 0))

        montage = concatenate_videoclips(scenes, method="compose").with_duration(total_duration)
        subtitles = [
            clip
            for timing in timings
            for clip in (_subtitle_shadow_clip(timing), _subtitle_clip(timing))
        ]
        visual = CompositeVideoClip([montage, *subtitles], size=FRAME_SIZE).with_duration(total_duration)

        ambient_source = AudioFileClip(str(ambient_path))
        ambient_loop = ambient_source.with_effects([AudioLoop(duration=total_duration)])
        ambient_loop = ambient_loop.with_volume_scaled(AMBIENT_GAIN)
        mixed_audio = CompositeAudioClip([narration, ambient_loop]).with_duration(total_duration)
        final = visual.with_audio(mixed_audio)
        final.write_videofile(
            str(output_path),
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            audio_bitrate="192k",
            preset="medium",
            threads=max(1, min(8, math.ceil((__import__("os").cpu_count() or 2) / 2))),
            ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"],
        )
    finally:
        if final is not None:
            final.close()
        if montage is not None:
            montage.close()
        for subtitle in subtitles:
            subtitle.close()
        for scene in scenes:
            scene.close()
        if ambient_loop is not None:
            ambient_loop.close()
        if ambient_source is not None:
            ambient_source.close()
        narration.close()

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("Video rendering completed without producing a file")
    return output_path
