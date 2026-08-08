"""Gemini-backed story generation with a strict, validated data contract."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types


# Google's versioned models can be retired for new API users. The stable alias
# follows the current Flash generation model; GEMINI_MODEL can pin a version.
DEFAULT_MODEL_NAME = "gemini-flash-latest"
ENDING_STYLES = (
    "a fully resolved survival account with a concrete aftermath",
    "a plausible explanation that resolves the danger but leaves one small uncanny detail",
    "a witness or physical record corroborates the narrator and the incident is conclusively over",
    "a quiet personal realization that closes the event without introducing a new threat",
    "a costly but complete escape in which the narrator makes a believable practical decision",
    "a grounded reveal that recontextualizes earlier details and ends the central mystery",
)
HISTORY_LIMIT = 50
UNIQUENESS_LOOKBACK = 12
SIMILARITY_LIMIT = 0.52
COMMON_WORDS = {
    "about", "after", "again", "been", "before", "could", "didn", "from", "have",
    "into", "just", "like", "never", "only", "other", "some", "still", "that", "their",
    "them", "then", "there", "they", "this", "through", "very", "what", "when", "where",
    "which", "while", "with", "would", "your",
}
CLICHE_PHRASES = (
    "blood ran cold",
    "little did i know",
    "it was all a dream",
    "i was never seen again",
)
CLIFFHANGER_ENDING = re.compile(
    r"\b(scheduled for|tonight|tomorrow|at midnight|new message|notification|"
    r"phone (?:buzzed|lit up|rang)|knock(?:ed|ing)? again|behind me|"
    r"still (?:there|watching|waiting|following)|it followed me|entry read)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Story:
    title: str
    description: str
    narration_segments: list[str]
    image_prompts: list[str]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Story":
        required = {"title", "description", "narration_segments", "image_prompts"}
        missing = required.difference(payload)
        if missing:
            raise ValueError(f"Gemini response is missing: {', '.join(sorted(missing))}")

        title = payload["title"]
        description = payload["description"]
        narration = payload["narration_segments"]
        prompts = payload["image_prompts"]
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Story title must be a non-empty string")
        if not isinstance(description, str) or not description.strip():
            raise ValueError("Story description must be a non-empty string")
        if not isinstance(narration, list) or not all(
            isinstance(item, str) and item.strip() for item in narration
        ):
            raise ValueError("narration_segments must contain non-empty strings")
        if not isinstance(prompts, list) or not all(
            isinstance(item, str) and item.strip() for item in prompts
        ):
            raise ValueError("image_prompts must contain non-empty strings")
        if not narration or len(narration) != len(prompts):
            raise ValueError("Narration and image prompt arrays must be non-empty and aligned")
        if len(narration) > 14:
            raise ValueError("Too many segments for a 60-second short (maximum: 14)")

        return cls(
            title.strip(),
            description.strip(),
            [item.strip() for item in narration],
            [item.strip() for item in prompts],
        )

    def save(self, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return output_path


STORY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "narration_segments": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 6,
            "maxItems": 12,
        },
        "image_prompts": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 6,
            "maxItems": 12,
        },
    },
    "required": ["title", "description", "narration_segments", "image_prompts"],
}


def _load_story_history(output_path: Path) -> list[dict[str, Any]]:
    history_path = output_path.parent / "story_history.json"
    history: list[dict[str, Any]] = []
    if history_path.exists():
        try:
            payload = json.loads(history_path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                history = [item for item in payload if isinstance(item, dict)]
        except (json.JSONDecodeError, OSError):
            print("Story history is unreadable; starting a fresh uniqueness history.")

    # Preserve the most recent story from installations created before history tracking.
    if output_path.exists():
        try:
            current = Story.from_dict(json.loads(output_path.read_text(encoding="utf-8")))
            if not any(item.get("title") == current.title for item in history):
                history.append({
                    "title": current.title,
                    "topic": "previous generated story",
                    "narration_segments": current.narration_segments,
                    "ending_style": "legacy",
                })
        except (ValueError, json.JSONDecodeError, OSError):
            pass
    return history[-HISTORY_LIMIT:]


def _fingerprint(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {word for word in words if len(word) > 3 and word not in COMMON_WORDS}


def _assert_unique(story: Story, history: list[dict[str, Any]]) -> None:
    new_text = " ".join([story.title, *story.narration_segments])
    new_words = _fingerprint(new_text)
    for previous in history[-UNIQUENESS_LOOKBACK:]:
        old_segments = previous.get("narration_segments", [])
        if not isinstance(old_segments, list):
            old_segments = []
        old_text = " ".join([str(previous.get("title", "")), *map(str, old_segments)])
        old_words = _fingerprint(old_text)
        union = new_words | old_words
        similarity = len(new_words & old_words) / len(union) if union else 0.0
        if similarity >= SIMILARITY_LIMIT:
            raise ValueError(
                f"Generated story is too similar to {previous.get('title', 'a recent story')!r} "
                f"(similarity {similarity:.0%})"
            )


def _assert_story_quality(story: Story) -> None:
    """Reject structurally weak, robotic, or cheap-cliffhanger stories."""
    if not 6 <= len(story.narration_segments) <= 12:
        raise ValueError("Story must contain 6-12 aligned narration and image segments")
    narration = " ".join(story.narration_segments)
    word_count = len(re.findall(r"\b[\w’'-]+\b", narration))
    if not 105 <= word_count <= 175:
        raise ValueError(f"Narration must be 105-175 words; received {word_count}")
    first_person_markers = len(
        re.findall(r"\b(?:i|i'm|i've|i'd|my|me|mine)\b", narration, re.IGNORECASE)
    )
    if first_person_markers < 5:
        raise ValueError("Narration does not sound like a first-person personal account")
    lowered = narration.lower().replace("’", "'")
    used_cliches = [phrase for phrase in CLICHE_PHRASES if phrase in lowered]
    if used_cliches:
        raise ValueError(f"Narration uses banned cliché: {used_cliches[0]}")
    ending = story.narration_segments[-1].strip()
    if ending.endswith(("?", "...", "…")) or CLIFFHANGER_ENDING.search(ending):
        raise ValueError(f"Narration ends with a cheap cliffhanger: {ending}")
    if any(len(segment.split()) > 38 for segment in story.narration_segments):
        raise ValueError("A narration segment is too long for natural speech and readable subtitles")
    if any(len(prompt.split()) < 10 for prompt in story.image_prompts):
        raise ValueError("Each image prompt must contain concrete continuity and scene details")


def _record_story(
    output_path: Path,
    history: list[dict[str, Any]],
    story: Story,
    topic: str,
    ending_style: str,
) -> None:
    history_path = output_path.parent / "story_history.json"
    history.append({
        "created_at": datetime.now(timezone.utc).isoformat(),
        "topic": topic,
        "title": story.title,
        "ending_style": ending_style,
        "narration_segments": story.narration_segments,
    })
    temporary = history_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(history[-HISTORY_LIMIT:], indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(history_path)


def _recent_story_brief(history: list[dict[str, Any]]) -> str:
    if not history:
        return "- No previous stories are recorded."
    lines = []
    for item in history[-8:]:
        segments = item.get("narration_segments", [])
        opening = str(segments[0]) if isinstance(segments, list) and segments else ""
        ending = str(segments[-1]) if isinstance(segments, list) and segments else ""
        lines.append(
            f"- Title: {item.get('title', '')} | Opening: {opening[:120]} | Ending: {ending[:120]}"
        )
    return "\n".join(lines)


def _prompt(topic: str, ending_style: str, history: list[dict[str, Any]]) -> str:
    return f"""Create an original creepypasta for a YouTube Short about: {topic}

Required ending style for this story: {ending_style}.

Recent stories that MUST NOT be repeated, paraphrased, or structurally imitated:
{_recent_story_brief(history)}

Requirements:
- Narration should sound natural when spoken and last roughly 55-60 seconds (about 125-145 words total).
- Use 6-12 concise narration sentences. Each array item must be one complete spoken sentence.
- Write the entire narration as a believable first-person personal experience using "I" and "my".
- Make it sound like a real person reluctantly recounting something that happened to them, not an
  omniscient narrator or a polished novel. Use plain conversational language and natural uncertainty.
- Ground the account with one or two mundane, specific details such as a time, routine, job, relative,
  apartment feature, or familiar place. Only describe what the narrator personally saw, heard, or learned.
- Keep the event small-scale and internally consistent. Give the narrator a credible reason to be there,
  make them react sensibly, and maintain clear cause and effect. Use at most one unexplained element.
- Prefer ordinary settings and restrained details over impossible spectacle, lore dumps, or escalating monsters.
- Open with an immediate first-person memory or confession, not a generic introduction or channel greeting.
- Write for frightened spoken delivery: use contractions, varied sentence lengths, and occasional natural
  hesitation with an ellipsis or em dash. Never include stage directions or emotion labels in the narration.
- Build immediate tension, escalating dread, and a coherent payoff that follows from earlier details.
- Keep the supernatural element slightly ambiguous and avoid melodramatic cliches such as
  "little did I know," "blood ran cold," and "it was all a dream."
- Complete the central event and deliver the required ending style. Do not end mid-action, introduce a new
  threat in the last sentence, tease a sequel, or use a final knock, message, reflection, CCTV sighting,
  returning object, "it followed me," or "it is still out there" as a cliffhanger.
- Be genuinely different from every recent story listed above in setting, threat, sequence, reveal, and ending.
- Do not use gore, sexual content, copyrighted characters, or instructions for wrongdoing.
- Provide exactly one matching image prompt for every narration sentence, in the same order.
- Each image prompt must describe a dark animated horror-cartoon scene, vertical 9:16 composition,
  dramatic lighting, no text, no logos, no watermark, and no recognizable living artist's style.
- Every image prompt must literally depict its matching narration sentence. Restate the same protagonist's
  stable age range, clothing, setting, and time of day where visible so separate images retain continuity.
- The title must be short, curiosity-driven, and frame the story like a personal confession or warning.
- The description must be SEO-aware and end with 3-6 relevant horror hashtags.
Return only the JSON object matching the supplied schema."""


def generate_story(topic: str, output_path: Path) -> Story:
    """Generate, validate, and persist one story."""
    if not topic.strip():
        raise ValueError("topic cannot be empty")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    client = genai.Client(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", DEFAULT_MODEL_NAME).strip() or DEFAULT_MODEL_NAME
    history = _load_story_history(output_path)
    ending_style = ENDING_STYLES[len(history) % len(ENDING_STYLES)]
    config = types.GenerateContentConfig(
        temperature=0.9,
        response_mime_type="application/json",
        response_json_schema=STORY_SCHEMA,
    )
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=_prompt(topic.strip(), ending_style, history),
                config=config,
            )
            if not response.text:
                raise RuntimeError("Gemini returned an empty response")
            try:
                payload = json.loads(response.text)
            except json.JSONDecodeError as exc:
                raise ValueError("Gemini did not return valid JSON") from exc
            if not isinstance(payload, dict):
                raise ValueError("Gemini response must be a JSON object")
            story = Story.from_dict(payload)
            _assert_story_quality(story)
            _assert_unique(story, history)
            story.save(output_path)
            _record_story(output_path, history, story, topic.strip(), ending_style)
            return story
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                print(
                    f"Story generation attempt {attempt} with {model_name} failed: "
                    f"{type(exc).__name__}: {exc}. Retrying..."
                )
                time.sleep(2**attempt)
    print(
        f"Gemini could not produce a validated story after 3 attempts ({last_error}); "
        "using a curated offline story."
    )
    from fallback_story_engine import select_offline_story

    previous_titles = {str(item.get("title", "")) for item in history}
    story = Story.from_dict(select_offline_story(previous_titles))
    _assert_story_quality(story)
    _assert_unique(story, history)
    story.save(output_path)
    _record_story(output_path, history, story, topic.strip(), "curated offline resolution")
    return story


def load_validated_story(source_path: Path, output_path: Path) -> Story:
    """Load a Codex-authored story file and pass it through all pipeline safeguards."""
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Story file is not valid JSON: {source_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Story file must contain one JSON object")
    story = Story.from_dict(payload)
    history = _load_story_history(output_path)
    _assert_story_quality(story)
    _assert_unique(story, history)
    story.save(output_path)
    _record_story(
        output_path,
        history,
        story,
        f"Codex story file: {source_path.name}",
        "Codex-authored validated resolution",
    )
    return story
