"""First-run initialization for the horror video generator.

This file intentionally contains runtime setup rather than package metadata.  The
orchestrator imports :func:`initialize_project` before importing API-dependent
pipeline modules.
"""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
REQUIRED_DIRECTORIES = (
    PROJECT_ROOT / "output" / "scripts",
    PROJECT_ROOT / "output" / "audio",
    PROJECT_ROOT / "output" / "images",
    PROJECT_ROOT / "output" / "video",
    PROJECT_ROOT / "assets",
)


@dataclass(frozen=True)
class InitializationResult:
    project_root: Path
    ffmpeg_path: str


def _write_env(api_key: str) -> None:
    """Create a minimal private .env file without logging the secret."""
    env_path = PROJECT_ROOT / ".env"
    env_path.write_text(f"GEMINI_API_KEY={api_key.strip()}\n", encoding="utf-8")
    try:
        env_path.chmod(0o600)
    except OSError:
        # chmod is best-effort on filesystems that do not expose POSIX modes.
        pass


def ensure_environment(required: bool = True) -> None:
    """Load .env, interactively creating it on the first run."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists() and required:
        print("First run: a Gemini API key is required to generate the story.")
        while True:
            api_key = getpass("Enter GEMINI_API_KEY (input is hidden): ").strip()
            if api_key:
                _write_env(api_key)
                print(f"Saved API key to {env_path}")
                break
            print("The API key cannot be empty. Please try again.")
    if env_path.exists():
        load_dotenv(env_path, override=False)
    if required and not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError(f"GEMINI_API_KEY is missing or empty in {env_path}")


def ensure_directories() -> None:
    for directory in REQUIRED_DIRECTORIES:
        directory.mkdir(parents=True, exist_ok=True)


def _ffmpeg_install_hint() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "brew install ffmpeg"
    if system == "windows":
        return "winget install --id Gyan.FFmpeg -e"
    return "sudo apt update && sudo apt install -y ffmpeg"


def ensure_ffmpeg() -> str:
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    if not ffmpeg_path or not ffprobe_path:
        raise RuntimeError(
            "FFmpeg (including ffprobe) was not found on PATH. Install it with:\n"
            f"  {_ffmpeg_install_hint()}\n"
            "Then open a new terminal and run this command again."
        )
    return ffmpeg_path


def initialize_project(require_gemini: bool = True) -> InitializationResult:
    """Perform every idempotent preflight check needed by the pipeline."""
    ensure_directories()
    ensure_environment(required=require_gemini)
    ffmpeg_path = ensure_ffmpeg()
    return InitializationResult(PROJECT_ROOT, ffmpeg_path)


if __name__ == "__main__":
    result = initialize_project()
    print(f"Initialization complete. FFmpeg: {result.ffmpeg_path}")
