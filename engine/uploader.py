import os
import sys
import json
import time
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl"
]


def is_headless() -> bool:
    """Returns True if executing inside CI or without an active graphical display."""
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        return True
    if sys.platform != "win32" and not os.environ.get("DISPLAY"):
        return True
    return False


def get_authenticated_service(project_root: Path = Path(".")):
    project_root = Path(project_root)
    token_file = project_root / "token.json"
    client_secrets_file = project_root / "client_secrets.json"

    # Inject from environment if provided
    env_token = os.environ.get("YOUTUBE_TOKEN_JSON")
    if env_token and env_token.strip():
        token_file.write_text(env_token.strip(), encoding="utf-8")

    env_secrets = os.environ.get("CLIENT_SECRETS_JSON")
    if env_secrets and env_secrets.strip():
        client_secrets_file.write_text(env_secrets.strip(), encoding="utf-8")

    creds = None

    if token_file.exists():
        try:
            token_data = json.loads(token_file.read_text(encoding="utf-8"))
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
        except Exception as e:
            print(f"  [AUTH WARNING] Failed reading token.json: {e}")
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("  [AUTH] Refreshing expired OAuth access token via Google Cloud...")
            try:
                creds.refresh(Request())
                token_file.write_text(creds.to_json(), encoding="utf-8")
                print("  ✓ Access token refreshed successfully.")
            except Exception as e:
                print(f"  [AUTH ERROR] Token refresh failed: {e}")
                creds = None

    if not creds or not creds.valid:
        if is_headless():
            raise RuntimeError(
                "[CRITICAL AUTH FAILURE] Running in headless CI (GitHub Actions). "
                "Interactive browser login is disabled. "
                "Please ensure the 'YOUTUBE_TOKEN_JSON' repository secret contains a valid OAuth refresh token."
            )
        
        if not client_secrets_file.exists():
            raise FileNotFoundError(
                f"Missing {client_secrets_file}. Please download it from Google Cloud Console "
                "and place it in your root directory."
            )

        print("  [AUTH] Initiating one-time local OAuth browser login...")
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_file), SCOPES)
        creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json(), encoding="utf-8")
        print("  ✓ New token.json generated and saved successfully.")

    return build("youtube", "v3", credentials=creds)


def get_or_create_playlist(youtube, title: str) -> str:
    try:
        req = youtube.playlists().list(part="snippet", mine=True, maxResults=50)
        resp = req.execute()
        for pl in resp.get("items", []):
            if pl["snippet"]["title"].strip().lower() == title.strip().lower():
                return pl["id"]

        create_req = youtube.playlists().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": title,
                    "description": "Daily Sacred Bhagavad Gita Verses • Original Sanskrit Chants & Studio Narration."
                },
                "status": {"privacyStatus": "public"}
            }
        )
        res = create_req.execute()
        return res["id"]
    except Exception as e:
        print(f"  [PLAYLIST WARNING] Could not manage playlist: {e}")
        return ""


def add_video_to_playlist(youtube, video_id: str, playlist_id: str):
    if not playlist_id:
        return
    try:
        youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {
                        "kind": "youtube#video",
                        "videoId": video_id
                    }
                }
            }
        ).execute()
        print(f"  ✓ Video added to playlist: {playlist_id}")
    except Exception as e:
        print(f"  [PLAYLIST ERROR] Failed adding video to playlist: {e}")


def upload_to_youtube(
    video_path: Path,
    title: str,
    description: str,
    tags: list = None,
    category_id: str = "27",  # Education
    privacy_status: str = "public",
    playlist_name: str = "Bhagavad Gita • English Edition",
    project_root: Path = Path(".")
) -> str:
    youtube = get_authenticated_service(project_root)
    tags = tags or ["BhagavadGita", "Krishna", "Spirituality", "Shorts", "DailyWisdom"]

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags,
            "categoryId": category_id
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        chunksize=1024 * 1024 * 4,
        resumable=True
    )

    print(f"  [UPLOADER] Initiating upload for: {video_path.name}")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    retry_count = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"  [UPLOAD PROGRESS] {int(status.progress() * 100)}% uploaded...")
        except HttpError as e:
            if e.resp.status in [500, 502, 503, 504]:
                retry_count += 1
                if retry_count > 5:
                    raise
                time.sleep(retry_count * 2)
            else:
                raise

    video_id = response.get("id")
    video_url = f"https://youtu.be/{video_id}"
    print(f"  ✓ Video published successfully: {video_url}")

    if playlist_name:
        playlist_id = get_or_create_playlist(youtube, playlist_name)
        if playlist_id:
            add_video_to_playlist(youtube, video_id, playlist_id)

    return video_url
