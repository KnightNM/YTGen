"""Procedural audio assets for a self-contained horror soundtrack."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt


SUPPORTED_AUDIO = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"}
GENERATED_FILENAME = "procedural_drone.wav"


def find_custom_background(assets_dir: Path) -> Path | None:
    """Return the first user-provided background track, if one exists."""
    candidates = sorted(
        path
        for path in assets_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_AUDIO
        and path.name != GENERATED_FILENAME
    )
    return candidates[0] if candidates else None


def generate_procedural_drone(
    output_path: Path,
    duration_seconds: float = 60.0,
    sample_rate: int = 44_100,
    seed: int = 7331,
) -> Path:
    """Generate a normalized stereo drone from oscillators and filtered noise."""
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sample_count = int(duration_seconds * sample_rate)
    time = np.arange(sample_count, dtype=np.float64) / sample_rate
    rng = np.random.default_rng(seed)

    slow_pulse = 0.72 + 0.28 * np.sin(2 * np.pi * 0.085 * time)
    fundamental = np.sin(2 * np.pi * 43.0 * time)
    undertone = np.sin(2 * np.pi * 28.5 * time + 0.45 * np.sin(2 * np.pi * 0.03 * time))
    dissonance = np.sin(2 * np.pi * 65.8 * time + 0.25 * np.sin(2 * np.pi * 0.11 * time))

    noise = rng.normal(0.0, 1.0, sample_count)
    # An efficient low-pass filter removes hiss while keeping ominous rumble.
    lowpass = butter(3, 95.0, btype="lowpass", fs=sample_rate, output="sos")
    low_noise = sosfilt(lowpass, noise)
    mono = slow_pulse * (0.52 * fundamental + 0.32 * undertone + 0.16 * dissonance)
    mono += 0.32 * low_noise

    fade_samples = min(int(sample_rate * 2.5), sample_count // 2)
    envelope = np.ones(sample_count, dtype=np.float64)
    envelope[:fade_samples] = np.linspace(0.0, 1.0, fade_samples)
    envelope[-fade_samples:] = np.linspace(1.0, 0.0, fade_samples)
    mono *= envelope
    mono /= max(float(np.max(np.abs(mono))), 1e-9)
    mono *= 0.72

    # Slight channel offset makes the drone feel spacious without phase inversion.
    right = np.roll(mono, int(sample_rate * 0.013)) * 0.96
    stereo = np.column_stack((mono, right))
    pcm = np.int16(np.clip(stereo, -1.0, 1.0) * 32767)
    wavfile.write(output_path, sample_rate, pcm)
    return output_path


def get_or_create_background(assets_dir: Path, seed: int = 7331) -> Path:
    """Prefer a custom track; otherwise idempotently create the default drone."""
    assets_dir.mkdir(parents=True, exist_ok=True)
    custom = find_custom_background(assets_dir)
    if custom:
        return custom
    generated = assets_dir / GENERATED_FILENAME
    if not generated.exists() or generated.stat().st_size == 0:
        print("No custom background track found; generating a 60-second creepy drone.")
        generate_procedural_drone(generated, seed=seed)
    return generated
