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
    "https://www.googleapis.com/auth/youtube"
]


def is_headless() -> bool:
    """Detects if running inside headless CI without a GUI display."""
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        return True
    if sys.platform != "win32" and not os.environ.get("DISPLAY"):
        return True
    return False


def get_authenticated_service(project_root: Path = Path(".")):
    project_root = Path(project_root)
    token_file = project_root / "token.json"
    client_secrets_file = project_root / "client_secrets.json"

    # Hydrate credentials from GitHub Secrets if running in Actions
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
            # Omit explicit SCOPES parameter so it defaults to the token's original granted scopes
            creds = Credentials.from_authorized_user_info(token_data)
        except Exception as e:
            print(f"  [AUTH WARNING] Failed reading token.json: {e}")
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("  [AUTH] Refreshing expired OAuth token via Google Cloud...")
            try:
                # Clear explicit scopes so Google refreshes against originally granted scopes
                creds._scopes = None
                creds.refresh(Request())
                token_file.write_text(creds.to_json(), encoding="utf-8")
                print("  ✓ OAuth token refreshed successfully.")
            except Exception as e:
                print(f"  [AUTH ERROR] Automatic token refresh failed: {e}")
                creds = None

    if not creds or not creds.valid:
        if is_headless():
            raise RuntimeError(
                "\n[CRITICAL AUTH FAILURE] Running in headless CI (GitHub Actions).\n"
                "Interactive browser authorization is impossible.\n"
                "Ensure repository secret 'YOUTUBE_TOKEN_JSON' contains a valid token with a refresh_token."
            )

        if not client_secrets_file.exists():
            raise FileNotFoundError(
                f"Missing {client_secrets_file}. Download OAuth Client JSON from Google Cloud Console "
                "and save it to the project root."
            )

        print("  [AUTH] Opening browser for one-time local OAuth authorization...")
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_file), SCOPES)
        creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json(), encoding="utf-8")
        print("  ✓ Fresh token.json created.")

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
        print(f"  [PLAYLIST WARNING] Failed to query or create playlist: {e}")
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
        print(f"  ✓ Video linked to playlist: {playlist_id}")
    except Exception as e:
        print(f"  [PLAYLIST ERROR] Could not add video to playlist: {e}")


def upload_short_to_youtube(*args, **kwargs) -> str:
    """
    Polymorphic upload interface. Handles:
    - upload_short_to_youtube(video_path, title, description, ...)
    - upload_short_to_youtube(render_cfg_path, project_root)
    - upload_short_to_youtube(video_path, metadata_dict)
    - upload_short_to_youtube(video_path=..., title=..., ...)
    """
    project_root = Path(".")
    video_path = None
    title = kwargs.get("title")
    description = kwargs.get("description")
    tags = kwargs.get("tags")
    category_id = kwargs.get("category_id", "27")  # Education
    privacy_status = kwargs.get("privacy_status", "public")
    playlist_name = kwargs.get("playlist_name", "Bhagavad Gita • English Edition")

    # Parse positional arguments
    if len(args) >= 1:
        first = args[0]
        if isinstance(first, (str, Path)):
            p = Path(first)
            if p.suffix.lower() == ".json" and p.exists():
                try:
                    cfg_data = json.loads(p.read_text(encoding="utf-8"))
                    verse = cfg_data.get("verse", {})
                    ch = verse.get("chapter", 1)
                    vs = verse.get("verse", 1)
                    title = f"Bhagavad Gita | Ch {ch} Verse {vs} #Shorts"
                    description = f"Chapter {ch}, Verse {vs}\n\n{verse.get('meaning', '')}\n\n#BhagavadGita #Krishna #Shorts"
                except Exception:
                    pass
                if len(args) >= 2 and isinstance(args[1], (str, Path)):
                    project_root = Path(args[1])
            elif p.suffix.lower() in [".mp4", ".mov", ".mkv"]:
                video_path = p
        elif isinstance(first, dict):
            ch = first.get("chapter", 1)
            vs = first.get("verse", 1)
            title = f"Bhagavad Gita | Ch {ch} Verse {vs} #Shorts"
            description = f"Chapter {ch}, Verse {vs}\n\n{first.get('meaning', '')}\n\n#BhagavadGita #Krishna #Shorts"

    if len(args) >= 2:
        second = args[1]
        if isinstance(second, str) and not title:
            title = second
        elif isinstance(second, dict):
            if not title and "title" in second:
                title = second["title"]
            if not description and "description" in second:
                description = second.get("description")

    if len(args) >= 3 and isinstance(args[2], str) and not description:
        description = args[2]

    if "video_path" in kwargs:
        video_path = Path(kwargs["video_path"])

    # Locate rendered video if not passed explicitly
    if not video_path or not video_path.exists():
        candidates = [
            project_root / "output" / "final_master.mp4",
            project_root / "output" / "final_short.mp4",
            project_root / "output" / "render.mp4",
            project_root / "cache" / "final_master.mp4",
        ]
        found = False
        for c in candidates:
            if c.exists():
                video_path = c
                found = True
                break
        if not found:
            out_dir = project_root / "output"
            if out_dir.exists():
                mp4s = sorted(out_dir.glob("*.mp4"), key=os.path.getmtime, reverse=True)
                if mp4s:
                    video_path = mp4s[0]
                    found = True
        if not found:
            raise FileNotFoundError("Could not locate final rendered .mp4 file in output/ or cache/.")

    if not title:
        title = "Bhagavad Gita Divine Verse #Shorts"
    if not description:
        description = "Daily sacred Bhagavad Gita wisdom, Sanskrit chanting, and philosophical insight.\n\n#BhagavadGita #Krishna #Wisdom #Shorts"
    if not tags:
        tags = ["BhagavadGita", "Krishna", "Spirituality", "Shorts", "DailyWisdom", "Meditation"]

    youtube = get_authenticated_service(project_root)

    body = {
        "snippet": {
            "title": str(title)[:100],
            "description": str(description)[:5000],
            "tags": tags,
            "categoryId": str(category_id)
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

    print(f"  [UPLOADER] Commencing YouTube Shorts publication: {video_path.name}")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    retry_count = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"  [UPLOAD PROGRESS] {int(status.progress() * 100)}% transferred...")
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
    print(f"  ✓ Video published live: {video_url}")

    if playlist_name:
        playlist_id = get_or_create_playlist(youtube, playlist_name)
        if playlist_id:
            add_video_to_playlist(youtube, video_id, playlist_id)

    return video_url


upload_to_youtube = upload_short_to_youtube
upload_video = upload_short_to_youtube
