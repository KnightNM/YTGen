"""MoviePy composer accepting a mixture of locally downloaded images and clips."""

from __future__ import annotations

import math
from pathlib import Path

from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
)
from moviepy.audio.fx.AudioLoop import AudioLoop
from moviepy.video.fx.Loop import Loop

from audio_engine import SegmentTiming
from video_composer import (
    AMBIENT_GAIN,
    FRAME_SIZE,
    _subtitle_clip,
    _subtitle_shadow_clip,
)


VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}


def _cover(clip, duration: float):
    """Fill 9:16 by uniform scaling and center cropping; never alter aspect ratio."""
    scale = max(FRAME_SIZE[0] / clip.w, FRAME_SIZE[1] / clip.h)
    covered = clip.resized(scale)
    return (
        CompositeVideoClip([covered.with_position(("center", "center"))], size=FRAME_SIZE)
        .with_duration(duration)
    )


def _scene(path: Path, duration: float, index: int):
    if path.suffix.lower() in VIDEO_EXTENSIONS:
        source = VideoFileClip(str(path), audio=False)
        if source.duration < duration:
            source = source.with_effects([Loop(duration=duration)])
        else:
            source = source.subclipped(0, duration)
        return _cover(source, duration)

    source = ImageClip(str(path)).with_duration(duration)
    base_scale = max(FRAME_SIZE[0] / source.w, FRAME_SIZE[1] / source.h)
    progress_sign = 1 if index % 2 == 0 else -1

    def scale_at(t: float) -> float:
        progress = min(max(t / max(duration, 0.001), 0), 1)
        return base_scale * (1.04 + progress_sign * 0.025 * (progress - 0.5))

    moving = source.resized(scale_at).with_position(("center", "center"))
    return CompositeVideoClip([moving], size=FRAME_SIZE).with_duration(duration)


def compose_hybrid_video(
    media_paths: list[Path],
    narration_path: Path,
    timings: list[SegmentTiming],
    ambient_path: Path,
    output_path: Path,
    fps: int = 30,
) -> Path:
    if not timings or len(media_paths) != len(timings):
        raise ValueError("There must be exactly one local media asset per narration segment")
    for path in [*media_paths, narration_path, ambient_path]:
        if not path.exists():
            raise FileNotFoundError(path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    narration = AudioFileClip(str(narration_path))
    total_duration = narration.duration
    boundaries = [timing.start for timing in timings] + [total_duration]
    scenes = []
    subtitles: list[TextClip] = []
    ambient_source = ambient_loop = montage = final = None
    try:
        for index, (path, timing) in enumerate(zip(media_paths, timings)):
            duration = max(boundaries[index + 1] - timing.start, 0.05)
            scenes.append(_scene(path, duration, index))
        montage = concatenate_videoclips(scenes, method="compose").with_duration(total_duration)
        subtitles = [
            clip for timing in timings
            for clip in (_subtitle_shadow_clip(timing), _subtitle_clip(timing))
        ]
        visual = CompositeVideoClip([montage, *subtitles], size=FRAME_SIZE).with_duration(total_duration)
        ambient_source = AudioFileClip(str(ambient_path))
        ambient_loop = ambient_source.with_effects([AudioLoop(duration=total_duration)])
        mixed = CompositeAudioClip(
            [narration, ambient_loop.with_volume_scaled(AMBIENT_GAIN)]
        ).with_duration(total_duration)
        final = visual.with_audio(mixed)
        final.write_videofile(
            str(output_path), fps=fps, codec="libx264", audio_codec="aac",
            audio_bitrate="192k", preset="medium",
            threads=max(1, min(8, math.ceil((__import__("os").cpu_count() or 2) / 2))),
            ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"],
        )
    finally:
        if final is not None:
            final.close()
        if montage is not None:
            montage.close()
        for item in subtitles:
            item.close()
        for item in scenes:
            item.close()
        if ambient_loop is not None:
            ambient_loop.close()
        if ambient_source is not None:
            ambient_source.close()
        narration.close()
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("Hybrid render did not produce a video")
    return output_path
