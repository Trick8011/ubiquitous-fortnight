"""Upload finished videos to YouTube via the YouTube Data API v3.

Uses OAuth installed-app credentials (a client_secret.json downloaded from
Google Cloud Console with the YouTube Data API enabled). The first upload
opens a browser consent flow; the resulting token is cached and refreshed
automatically after that.

The Google client libraries are an optional dependency:

    pip install google-api-python-client google-auth-oauthlib

Standalone usage:

    python -m videopipeline.upload out.mp4 --title "My Video" --privacy unlisted
"""

from __future__ import annotations

import argparse
import http.client
import os
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
CAPTIONS_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"

DEFAULT_CONFIG_DIR = Path.home() / ".videopipeline"
DEFAULT_CATEGORY = "22"  # People & Blogs
CHUNK_SIZE = 8 * 1024 * 1024
MAX_RETRIES = 5
RETRIABLE_STATUS = {500, 502, 503, 504}
RETRIABLE_EXCEPTIONS = (
    OSError,
    http.client.HTTPException,
)


@dataclass
class UploadOptions:
    title: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    category: str = DEFAULT_CATEGORY
    privacy: str = "private"  # private | unlisted | public
    made_for_kids: bool = False
    captions_srt: Path | None = None  # uploaded as an English caption track
    client_secrets: Path | None = None
    token_file: Path | None = None
    verbose: bool = True

    def __post_init__(self) -> None:
        if self.privacy not in ("private", "unlisted", "public"):
            raise ValueError(f"privacy must be private, unlisted, or public, got {self.privacy!r}")
        if not self.title.strip():
            raise ValueError("upload title must not be empty")


def _import_google():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload
    except ImportError as e:
        raise RuntimeError(
            "YouTube upload needs the Google API client libraries:\n"
            "  pip install google-api-python-client google-auth-oauthlib"
        ) from e
    return Request, Credentials, InstalledAppFlow, build, HttpError, MediaFileUpload


def _resolve_paths(options: UploadOptions) -> tuple[Path, Path]:
    secrets = options.client_secrets or Path(
        os.environ.get("YT_CLIENT_SECRETS", DEFAULT_CONFIG_DIR / "client_secret.json")
    )
    token = options.token_file or Path(
        os.environ.get("YT_TOKEN_FILE", DEFAULT_CONFIG_DIR / "token.json")
    )
    return secrets, token


def get_youtube_service(options: UploadOptions):
    """Authenticate and return a YouTube API client, caching the OAuth token."""
    Request, Credentials, InstalledAppFlow, build, _, _ = _import_google()
    secrets, token = _resolve_paths(options)
    scopes = [UPLOAD_SCOPE] + ([CAPTIONS_SCOPE] if options.captions_srt else [])

    creds = None
    if token.exists():
        creds = Credentials.from_authorized_user_file(str(token), scopes)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        if not secrets.exists():
            raise RuntimeError(
                f"no OAuth client secrets at {secrets}.\n"
                "Create an OAuth client ID (Desktop app) in Google Cloud Console with the\n"
                "YouTube Data API v3 enabled, download client_secret.json there, or point\n"
                "--client-secrets / YT_CLIENT_SECRETS at it."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(secrets), scopes)
        creds = flow.run_local_server(port=0, open_browser=False)
        token.parent.mkdir(parents=True, exist_ok=True)
        token.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def upload_video(video: Path, options: UploadOptions) -> str:
    """Upload the MP4 with resumable chunks; returns the new video's URL."""
    _, _, _, _, HttpError, MediaFileUpload = _import_google()
    if not video.exists():
        raise RuntimeError(f"video not found: {video}")
    say = print if options.verbose else (lambda *a, **k: None)

    youtube = get_youtube_service(options)
    body = {
        "snippet": {
            "title": options.title,
            "description": options.description,
            "tags": options.tags,
            "categoryId": options.category,
        },
        "status": {
            "privacyStatus": options.privacy,
            "selfDeclaredMadeForKids": options.made_for_kids,
        },
    }
    media = MediaFileUpload(str(video), chunksize=CHUNK_SIZE, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    say(f"Uploading {video.name} ({video.stat().st_size / 1e6:.1f} MB, privacy={options.privacy})...")
    response = None
    retries = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                say(f"  {int(status.progress() * 100)}%")
            retries = 0
        except HttpError as e:
            if e.resp.status not in RETRIABLE_STATUS:
                raise RuntimeError(f"upload failed: {e}") from e
            retries = _backoff(retries, say, f"HTTP {e.resp.status}")
        except RETRIABLE_EXCEPTIONS as e:
            retries = _backoff(retries, say, str(e))

    video_id = response["id"]
    say(f"  100% — video id {video_id}")

    if options.captions_srt and options.captions_srt.exists():
        _upload_captions(youtube, video_id, options.captions_srt, say)

    return f"https://www.youtube.com/watch?v={video_id}"


def _backoff(retries: int, say, reason: str) -> int:
    retries += 1
    if retries > MAX_RETRIES:
        raise RuntimeError(f"upload failed after {MAX_RETRIES} retries: {reason}")
    delay = random.uniform(1, 2 ** retries)
    say(f"  retriable error ({reason}), retrying in {delay:.0f}s...")
    time.sleep(delay)
    return retries


def _upload_captions(youtube, video_id: str, srt: Path, say) -> None:
    _, _, _, _, HttpError, MediaFileUpload = _import_google()
    say(f"Uploading captions from {srt.name}...")
    try:
        youtube.captions().insert(
            part="snippet",
            body={"snippet": {"videoId": video_id, "language": "en", "name": ""}},
            media_body=MediaFileUpload(str(srt)),
        ).execute()
        say("  captions attached")
    except HttpError as e:
        # The video is already up — a caption failure shouldn't fail the run.
        say(f"  warning: caption upload failed ({e}); video is still uploaded")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="videopipeline.upload",
        description="Upload an MP4 to YouTube (Data API v3, resumable).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("video", type=Path, help="MP4 file to upload")
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument("--tags", default="", help="comma-separated tag list")
    parser.add_argument("--category", default=DEFAULT_CATEGORY, help="YouTube category id")
    parser.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private")
    parser.add_argument("--made-for-kids", action="store_true")
    parser.add_argument("--srt", type=Path, help="SRT file to attach as an English caption track")
    parser.add_argument("--client-secrets", type=Path, help="OAuth client_secret.json path")
    parser.add_argument("--token-file", type=Path, help="cached OAuth token path")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args(argv)

    try:
        options = UploadOptions(
            title=args.title,
            description=args.description,
            tags=[t.strip() for t in args.tags.split(",") if t.strip()],
            category=args.category,
            privacy=args.privacy,
            made_for_kids=args.made_for_kids,
            captions_srt=args.srt,
            client_secrets=args.client_secrets,
            token_file=args.token_file,
            verbose=not args.quiet,
        )
        url = upload_video(args.video, options)
        print(url)
        return 0
    except (RuntimeError, ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
