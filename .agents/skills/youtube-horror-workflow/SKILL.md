---
name: youtube-horror-workflow
description: Run the repository's gated hybrid workflow for creating first-person YouTube horror Shorts with Codex subscription story generation, Edge narration, consistent ImageGen scenes, local MoviePy/FFmpeg rendering, and approved YouTube uploads. Use when the user asks to create, continue, check, render, publish, post, or resume a horror-video workflow in YTGen.
---

# YouTube Horror Workflow

Operate from the YTGen project root. Treat `workflow.py status` as the source of truth.

## State machine

Follow stages in order:

1. `not_started` → prepare story, narration, and prompt inbox.
2. `awaiting_media` → generate and save every numbered ImageGen scene.
3. `ready_to_render` → render locally without uploading.
4. `awaiting_upload_approval` → show the local result and wait for explicit approval.
5. `uploaded` → report the YouTube URL and stop; never upload the same workflow twice.

Run this before and after each action:

```bash
.venv/bin/python workflow.py status
```

Surface its `Nudge` line to the user whenever a stage cannot advance.

## Start

For a new topic, request network access and permission for Codex CLI to update its existing
`~/.codex` state, then run:

```bash
.venv/bin/python workflow.py start --topic "<topic>"
```

This uses ChatGPT OAuth through `codex exec`; do not request an OpenAI API key. If authentication
is missing, nudge the user to run `codex login`. Edge TTS also needs network access.

## Generate scene media

Use the available `imagegen` skill and its built-in tool. Do not scrape Sora or other protected web
interfaces. Read all `scene_###.txt` files from the state's `media_dir`.

Generate scene 1 as a native portrait horror-cartoon frame. Copy its built-in output into the inbox
as `scene_001.png`. For every later scene, use scene 1 as a reference image and explicitly lock:

- protagonist identity, age, hair, clothing, and proportions;
- recurring vehicles and location details;
- dark 2D horror-cartoon rendering and palette;
- native 9:16 framing with no vertical stretching;
- no text, logo, watermark, gore, or living-artist imitation.

Issue one built-in ImageGen call per scene. Copy, do not delete, generated originals. Save exact
filenames `scene_001.png` through the final scene number. Run `workflow.py status`; do not render
until it reports `ready_to_render`.

## Render

Rendering is local and reversible, so proceed when the user says render, continue, or finish the
local video:

```bash
.venv/bin/python workflow.py render
```

Report the resulting MP4 and its dimensions/duration. This command must never upload.

## Upload approval gate

Uploading is an external side effect. Require an explicit current request such as “post it to
YouTube” or “upload it.” A request to render, finish, test, or continue is not upload approval.
Default to `private` unless the user explicitly chooses `unlisted` or `public`.

After approval, request network access and run exactly once:

```bash
.venv/bin/python workflow.py upload --confirm-upload --privacy private
```

If Google OAuth requires interaction, nudge the user to complete it in the opened browser. If
`client_secret.json` is missing, nudge them to add YouTube desktop OAuth credentials. Report the
URL returned by the command.

## Guardrails

- Do not expose or commit `.env`, `token.json`, or `client_secret.json`.
- Do not regenerate a story or overwrite a prepared job while resuming it.
- Do not silently substitute Gemini/Pollinations for Codex/ImageGen.
- Do not upload when the state is already `uploaded`.
- On failure, preserve completed artifacts, run `workflow.py status`, and give one concrete nudge.

Read [references/operations.md](references/operations.md) only when diagnosing a blocked stage.
