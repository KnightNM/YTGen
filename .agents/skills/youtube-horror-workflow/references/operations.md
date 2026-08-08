# Blocked-stage operations

## Preflight

- Python environment: `.venv/bin/python`
- FFmpeg verification: `ffmpeg -version` and `ffprobe -version`
- Codex authentication: `codex login status`
- Workflow state: `output/scripts/workflow_state.json`
- Current prompt inbox: `output/scripts/hybrid_job.json`
- YouTube credentials: ignored `client_secret.json` and `token.json` in the project root

## Expected files

After `start`:

- `output/scripts/story.json`
- `output/audio/master_narration.wav`
- `output/audio/narration_timings.json`
- `output/media_inbox/<job>/scene_###.txt`

After ImageGen:

- exactly one supported image or clip for each `scene_###` stem

After `render`:

- `output/video/hybrid_short.mp4`

## Recovery

- Codex login failure: ask the user to run `codex login`; rerun `start` only after login succeeds.
- Story quality rejection: allow the built-in three retries; preserve the final error if all fail.
- Partial media generation: keep completed numbered files and generate only missing stems.
- Interrupted render: rerun `workflow.py render`; it reuses existing story, audio, and scene media.
- YouTube OAuth prompt: let the user complete browser authentication, then allow the uploader to
  resume. Never request passwords or OAuth codes in chat.
- Upload uncertainty: run `workflow.py status`. If stage is `uploaded`, never retry. If the API call
  failed before returning a URL, report uncertainty instead of automatically creating a duplicate.
