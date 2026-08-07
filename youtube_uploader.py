"""Optional OAuth2 upload to YouTube Data API v3."""

from __future__ import annotations

import re
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from script_engine import Story


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _credentials(project_root: Path) -> Credentials:
    token_path = project_root / "token.json"
    client_secret_path = project_root / "client_secret.json"
    credentials: Credentials | None = None
    if token_path.exists():
        credentials = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
        credentials = flow.run_local_server(port=0, open_browser=True)
    token_path.write_text(credentials.to_json(), encoding="utf-8")
    return credentials


def _tags(story: Story) -> list[str]:
    hashtags = re.findall(r"#([A-Za-z0-9_]+)", story.description)
    return list(dict.fromkeys(["horror", "creepypasta", "shorts", *hashtags]))[:15]


def upload_video(
    video_path: Path,
    story: Story,
    project_root: Path,
    privacy_status: str = "private",
) -> str | None:
    """Upload when OAuth configuration exists; otherwise make local success explicit."""
    client_secret_path = project_root / "client_secret.json"
    if not client_secret_path.exists():
        print(
            "client_secret.json was not found; skipping YouTube upload. "
            f"Your finished video is saved locally at {video_path}"
        )
        return None
    if privacy_status not in {"private", "unlisted", "public"}:
        raise ValueError("privacy_status must be private, unlisted, or public")
    if not video_path.exists():
        raise FileNotFoundError(video_path)

    credentials = _credentials(project_root)
    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    body = {
        "snippet": {
            "title": story.title[:100],
            "description": story.description[:5000],
            "tags": _tags(story),
            "categoryId": "24",
        },
        "status": {"privacyStatus": privacy_status, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(
        str(video_path), mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024
    )
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Upload progress: {int(status.progress() * 100)}%")
    video_id = response.get("id")
    if not video_id:
        raise RuntimeError("YouTube upload response did not include a video ID")
    url = f"https://youtu.be/{video_id}"
    print(f"Uploaded successfully: {url}")
    return url
