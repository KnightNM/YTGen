"""Generate structured stories through the locally authenticated Codex CLI."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from script_engine import ENDING_STYLES, STORY_SCHEMA, Story, load_validated_story


def _codex_prompt(topic: str) -> str:
    ending = ENDING_STYLES[sum(topic.encode("utf-8")) % len(ENDING_STYLES)]
    return f"""Write one original 55-60 second first-person horror account about: {topic}

The story must be believable, conversational, restrained, and genuinely frightening. Use 6-12
complete narration sentences totaling 105-175 words. Ground it in mundane specific details,
maintain clear cause and effect, and describe only what the narrator could know. Avoid lore dumps,
gore, melodrama, dream reveals, recycled internet stories, and cheap final-message/knock/CCTV
cliffhangers. The central event must conclude. Ending approach: {ending}.

Return a short curiosity-driven title, an SEO description ending in 3-6 horror hashtags, and one
visual prompt per narration sentence. Each visual prompt must literally depict that sentence and
repeat stable character/location details for continuity. Ask for a vertical 9:16 dark animated
horror-cartoon frame with cinematic lighting, no text, logo, watermark, copyrighted character, or
living artist imitation.

Your final response must contain only the JSON object required by the supplied output schema.
Do not create files, run commands, browse, or explain the response."""


def generate_story_with_codex(topic: str, project_root: Path, output_path: Path) -> Story:
    """Run ``codex exec`` with subscription auth, then apply existing quality safeguards."""
    topic = topic.strip()
    if not topic:
        raise ValueError("topic cannot be empty")
    executable = shutil.which("codex")
    if not executable:
        raise RuntimeError(
            "Codex CLI is not installed. Install it, run `codex login`, and retry."
        )

    work_dir = output_path.parent / ".codex_generation"
    work_dir.mkdir(parents=True, exist_ok=True)
    schema_path = work_dir / "story_schema.json"
    candidate_path = work_dir / "candidate.json"
    schema_path.write_text(json.dumps(STORY_SCHEMA, indent=2), encoding="utf-8")
    prompt = _codex_prompt(topic)
    last_error: Exception | None = None
    for attempt in range(1, 4):
        candidate_path.unlink(missing_ok=True)
        command = [
            executable,
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--sandbox",
            "read-only",
            "--color",
            "never",
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(candidate_path),
            "--cd",
            str(project_root),
            prompt,
        ]
        result = subprocess.run(
            command,
            text=True,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            tail = "\n".join(detail[-8:])
            last_error = RuntimeError(
                "Codex CLI failed. Confirm `codex login status` succeeds."
                + (f"\n{tail}" if tail else "")
            )
        elif not candidate_path.exists() or not candidate_path.read_text(encoding="utf-8").strip():
            last_error = RuntimeError("Codex completed without returning story JSON")
        else:
            try:
                return load_validated_story(candidate_path, output_path)
            except (ValueError, json.JSONDecodeError) as exc:
                last_error = exc

        if attempt < 3:
            print(f"Codex story attempt {attempt} was rejected: {last_error}. Retrying...")
            prompt = _codex_prompt(topic) + (
                f"\n\nA prior candidate failed validation for this reason: {last_error}. "
                "Produce a substantially revised candidate that fixes it."
            )
    raise RuntimeError("Codex could not produce a validated story after 3 attempts") from last_error
