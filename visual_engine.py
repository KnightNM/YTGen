"""Pollinations.ai image acquisition with validation and retry handling."""

from __future__ import annotations

import time
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


BASE_URL = "https://image.pollinations.ai/prompt"


def _image_url(prompt: str, narration: str, story_context: str, seed: int) -> str:
    enhanced = (
        "2D CARTOON ILLUSTRATION ONLY — not a photograph, not live action, not 3D. "
        "Dark hand-drawn animated horror storyboard, bold clean ink outlines, visible cel shading, "
        "expressive but believable faces, textured shadows, muted blue-gray and sepia palette. "
        f"Draw this exact scene: {prompt}. The story action is: {narration}. "
        "Every named person, action, and important object must be clearly visible in the frame. "
        f"Continuity reference: {story_context}. Preserve the same protagonist design and location. "
        "Compose as a 4:5 storyboard panel with normal realistic human proportions, anatomically correct "
        "head and limbs, medium or waist-up shot, no elongated body, no extreme foreshortening, and safe "
        "empty space above and below for placement on a phone canvas. No generic monster or unrelated location, "
        "no text, no captions, no speech bubbles, no logo, no watermark"
    )
    return (
        f"{BASE_URL}/{quote(enhanced, safe='')}?width=1080&height=1350"
        f"&model=sana&nologo=true&seed={seed}"
    )


def _looks_like_image(data: bytes, content_type: str) -> bool:
    signatures = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"RIFF")
    return content_type.lower().startswith("image/") and any(data.startswith(sig) for sig in signatures)


def _compose_phone_canvas(source: Image.Image) -> Image.Image:
    """Extend a 4:5 illustration to 9:16 without changing its geometry."""
    source_rgb = source.convert("RGB")
    background = ImageOps.fit(
        source_rgb,
        (1080, 1920),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )
    background = background.filter(ImageFilter.GaussianBlur(radius=38))
    background = ImageEnhance.Brightness(background).enhance(0.38)

    foreground = ImageOps.contain(
        source_rgb,
        (1080, 1560),
        method=Image.Resampling.LANCZOS,
    )
    x = (1080 - foreground.width) // 2
    y = (1920 - foreground.height) // 2
    background.paste(foreground, (x, y))
    return background


def _save_vertical_frame(data: bytes, destination: Path) -> None:
    """Decode and place the source on an exact 9:16 canvas without stretching."""
    try:
        with Image.open(BytesIO(data)) as source:
            source.load()
            frame = _compose_phone_canvas(source)
            temporary = destination.with_suffix(".jpg.part")
            frame.save(temporary, format="JPEG", quality=94, optimize=True)
            temporary.replace(destination)
    except (OSError, ValueError) as exc:
        raise ValueError("Pollinations returned an unreadable image") from exc


def download_images(
    prompts: list[str],
    output_dir: Path,
    narration_segments: list[str] | None = None,
    seed: int = 7331,
    retries: int = 4,
    timeout: tuple[int, int] = (15, 180),
) -> list[Path]:
    """Download one deterministic vertical image per prompt."""
    if not prompts or not all(isinstance(prompt, str) and prompt.strip() for prompt in prompts):
        raise ValueError("prompts must contain non-empty strings")
    if narration_segments is None:
        narration_segments = prompts
    if len(narration_segments) != len(prompts) or not all(
        isinstance(segment, str) and segment.strip() for segment in narration_segments
    ):
        raise ValueError("narration_segments must contain one non-empty item per image prompt")
    # A compact setup supplies continuity without overwhelming the current visual beat.
    story_context = " ".join(narration_segments[:2])[:500]
    output_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "FreeHorrorVideoGenerator/1.0"})
    results: list[Path] = []

    for index, (prompt, narration) in enumerate(zip(prompts, narration_segments)):
        destination = output_dir / f"frame_{index:03d}.jpg"
        # A shared seed helps Pollinations retain visual identity across story beats.
        url = _image_url(prompt, narration, story_context, seed)
        error: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                response = session.get(url, timeout=timeout)
                response.raise_for_status()
                if not _looks_like_image(response.content, response.headers.get("Content-Type", "")):
                    raise ValueError("Pollinations returned a non-image response")
                _save_vertical_frame(response.content, destination)
                results.append(destination)
                print(f"Downloaded image {index + 1}/{len(prompts)}")
                break
            except (requests.RequestException, ValueError, OSError) as exc:
                error = exc
                if attempt < retries:
                    time.sleep(min(2 ** (attempt - 1), 8))
        else:
            raise RuntimeError(f"Failed to download image {index + 1} after {retries} attempts") from error
    return results
