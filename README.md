# Free YouTube Horror Video Generator

A local-first Python CLI that creates a short creepypasta, narrates it, downloads
matching vertical artwork, generates its own ambient drone, burns synchronized
subtitles into a 1080x1920 video, and optionally uploads it to YouTube.

Visuals use a dark hand-drawn cartoon brief and are normalized to an exact 9:16
phone canvas. Generated stories are checked for length, first-person delivery,
recent-story similarity, cliché endings, and aligned scene prompts.

The software uses free services/libraries, but Gemini, Edge TTS, Pollinations.ai,
and YouTube require internet access and remain subject to their providers' quotas
and terms.

## Install

Python 3.11+ is recommended. FFmpeg must be available on `PATH`.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py --topic "The noise behind the basement walls"
```

Codex or another trusted author can bypass Gemini by supplying the same strict
story JSON contract directly:

```bash
python main.py --story-file output/scripts/codex_story_candidate.json
```

On the first run the CLI securely prompts for `GEMINI_API_KEY` and writes `.env`.
It creates all output folders automatically. To use your own music, place one
supported audio file in `assets/`; otherwise `assets/procedural_drone.wav` is made.

## YouTube upload (optional)

Create OAuth desktop credentials for YouTube Data API v3 and save the downloaded
file as `client_secret.json` in this directory. The first upload opens Google's
OAuth consent flow and stores the refreshable credentials in ignored `token.json`.
Uploads default to private:

```bash
python main.py --topic "The last train had no driver" --privacy unlisted
```

Use `--skip-upload` to guarantee a local-only run. The finished file is written to
`output/video/final_short.mp4`.
