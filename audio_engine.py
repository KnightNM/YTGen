"""Edge TTS narration synthesis and timestamp-aware audio assembly."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import edge_tts
from pydub import AudioSegment
from pydub.effects import compress_dynamic_range, normalize


DEFAULT_VOICE = "en-US-BrianMultilingualNeural"
SUPPORTED_VOICES = {
    DEFAULT_VOICE,
    "en-US-AndrewMultilingualNeural",
    "en-US-GuyNeural",
    "en-US-ChristopherNeural",
    "en-US-EricNeural",
}


@dataclass(frozen=True)
class VoiceDirection:
    rate: str
    pitch: str
    volume: str


@dataclass(frozen=True)
class SegmentTiming:
    index: int
    text: str
    start: float
    end: float
    audio_path: str


@dataclass(frozen=True)
class NarrationResult:
    audio_path: Path
    timings: list[SegmentTiming]
    duration: float


def _voice_direction(index: int, total: int) -> VoiceDirection:
    """Shape delivery from uneasy recollection through panic to final dread."""
    progress = index / max(total - 1, 1)
    if index == total - 1:
        return VoiceDirection(rate="-14%", pitch="-5Hz", volume="-2%")
    if progress < 0.30:
        return VoiceDirection(rate="-8%", pitch="-2Hz", volume="-3%")
    if progress < 0.72:
        return VoiceDirection(rate="-3%", pitch="+2Hz", volume="+0%")
    return VoiceDirection(rate="+3%", pitch="+7Hz", volume="+2%")


async def _synthesize_one(
    text: str,
    output_path: Path,
    voice: str,
    direction: VoiceDirection,
) -> None:
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            communicator = edge_tts.Communicate(
                text=text,
                voice=voice,
                rate=direction.rate,
                pitch=direction.pitch,
                volume=direction.volume,
            )
            await communicator.save(str(output_path))
            if not output_path.exists() or output_path.stat().st_size == 0:
                raise RuntimeError(f"TTS produced no audio for {output_path.name}")
            return
        except Exception as exc:
            last_error = exc
            output_path.unlink(missing_ok=True)
            if attempt < 3:
                await asyncio.sleep(2**attempt)
    raise RuntimeError(f"TTS failed three times for {output_path.name}") from last_error


async def _synthesize_all(
    segments: list[str], segment_dir: Path, voice: str
) -> list[Path]:
    paths = [segment_dir / f"segment_{index:03d}.mp3" for index in range(len(segments))]
    # Keep a small concurrency limit to avoid throttling the free public service.
    semaphore = asyncio.Semaphore(3)

    async def guarded(index: int, text: str, path: Path) -> None:
        async with semaphore:
            await _synthesize_one(text, path, voice, _voice_direction(index, len(segments)))

    await asyncio.gather(
        *(guarded(index, text, path) for index, (text, path) in enumerate(zip(segments, paths)))
    )
    return paths


def _pause_after(text: str, index: int, base_ms: int) -> int:
    """Use varied conversational pauses instead of a mechanical fixed gap."""
    stripped = text.rstrip()
    if stripped.endswith(("...", "…")):
        return base_ms + 260
    if stripped.endswith("?"):
        return base_ms + 130
    if stripped.endswith("!"):
        return base_ms + 70
    return base_ms + (20, 65, 40)[index % 3]


def synthesize_narration(
    segments: list[str],
    output_dir: Path,
    voice: str = DEFAULT_VOICE,
    gap_ms: int = 120,
) -> NarrationResult:
    """Synthesize every line, merge it, and persist exact subtitle timings."""
    if voice not in SUPPORTED_VOICES:
        raise ValueError(f"Unsupported voice {voice!r}; choose one of {sorted(SUPPORTED_VOICES)}")
    if not segments or not all(isinstance(text, str) and text.strip() for text in segments):
        raise ValueError("segments must contain non-empty strings")

    output_dir.mkdir(parents=True, exist_ok=True)
    segment_dir = output_dir / "segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    paths = asyncio.run(_synthesize_all(segments, segment_dir, voice))

    master = AudioSegment.silent(duration=0)
    timings: list[SegmentTiming] = []
    cursor_ms = 0
    for index, (text, path) in enumerate(zip(segments, paths)):
        clip = AudioSegment.from_file(path)
        start_ms = cursor_ms
        master += clip
        cursor_ms += len(clip)
        timings.append(
            SegmentTiming(index, text.strip(), start_ms / 1000.0, cursor_ms / 1000.0, str(path))
        )
        if index < len(paths) - 1:
            pause_ms = _pause_after(text, index, gap_ms)
            master += AudioSegment.silent(duration=pause_ms)
            cursor_ms += pause_ms

    audio_path = output_dir / "master_narration.wav"
    master = compress_dynamic_range(
        master, threshold=-23.0, ratio=2.2, attack=8.0, release=90.0
    )
    master = normalize(master, headroom=1.5)
    master.export(audio_path, format="wav")
    timing_path = output_dir / "narration_timings.json"
    timing_path.write_text(
        json.dumps([asdict(item) for item in timings], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return NarrationResult(audio_path, timings, len(master) / 1000.0)
