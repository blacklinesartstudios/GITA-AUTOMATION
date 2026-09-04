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
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        return True
    if sys.platform != "win32" and not os.environ.get("DISPLAY"):
        return True
    return False

def get_authenticated_service(project_root: Path = Path(".")):
    project_root = Path(project_root)
    token_file = project_root / "token.json"
    client_secrets_file = project_root / "client_secrets.json"

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
            creds = Credentials.from_authorized_user_info(token_data)
        except Exception as e:
            print(f"  [AUTH WARNING] Failed reading token.json: {e}")
            creds = None

    if not creds or not creds.valid:
        if creds and creds.refresh_token:
            print("  [AUTH] Refreshing expired OAuth token via Google Cloud...")
            try:
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
            raise FileNotFoundError(f"Missing {client_secrets_file} in root directory.")

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
                print(f"  ✓ Found existing playlist: '{title}' ({pl['id']})")
                return pl["id"]

        print(f"  [PLAYLIST] Creating public playlist: '{title}'...")
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
        print(f"  ✓ Playlist created successfully: {res['id']}")
        return res["id"]
    except Exception as e:
        print(f"  [PLAYLIST ERROR] Failed to query/create playlist: {e}")
        return ""

def add_video_to_playlist(youtube, video_id: str, playlist_id: str):
    if not playlist_id or not video_id:
        print("  [PLAYLIST WARNING] Missing playlist_id or video_id. Skipping link.")
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
        print(f"  ✓ Successfully added video {video_id} to playlist ID: {playlist_id}")
    except Exception as e:
        print(f"  [PLAYLIST ERROR] Could not add video to playlist: {e}")

def upload_short_to_youtube(*args, **kwargs) -> str:
    project_root = Path(".")
    video_path = kwargs.get("video_path")
    json_path = kwargs.get("json_path") or kwargs.get("config_path")
    
    title = kwargs.get("title")
    description = kwargs.get("description")
    tags = kwargs.get("tags")
    category_id = kwargs.get("category_id", "27")
    privacy_status = kwargs.get("privacy_status", "public")
    playlist_name = kwargs.get("playlist_name", "Bhagavad Gita • English Edition")

    # 1. Exhaustive scan of positional arguments
    for arg in args:
        if isinstance(arg, (str, Path)):
            p = Path(arg)
            if p.suffix.lower() == ".json":
                if p.exists():
                    json_path = p
                elif (project_root / p).exists():
                    json_path = project_root / p
            elif p.suffix.lower() in [".mp4", ".mov", ".mkv"]:
                if p.exists():
                    video_path = p
                elif (project_root / p).exists():
                    video_path = project_root / p

    # 2. Auto-discover JSON config if still missing
    if not json_path or not Path(json_path).exists():
        json_candidates = sorted(list(project_root.glob("cache/**/*.json")) + list(project_root.glob("*.json")), key=os.path.getmtime, reverse=True)
        if json_candidates:
            json_path = json_candidates[0]
            print(f"  [UPLOADER] Auto-discovered config JSON: {json_path}")

    # 3. Parse JSON config for accurate chapter, verse, and multi-line SEO description
    if json_path and Path(json_path).exists():
        try:
            cfg_data = json.loads(Path(json_path).read_text(encoding="utf-8"))
            verse = cfg_data.get("verse", {})
            ch = verse.get("chapter", 1)
            vs = verse.get("verse_number", verse.get("verse", 1))
            sanskrit_text = verse.get("sanskrit", "").replace("\\n", "\n")
            meaning_text = verse.get("meaning", "")
            insight_text = verse.get("insight", "")
            
            title = f"Bhagavad Gita | Chapter {ch} Verse {vs} #Shorts"
            
            description = (
                f"॥ श्रीमद्भगवद्गीता ॥\n"
                f"Chapter {ch}, Verse {vs}\n\n"
                f"📜 SANSKRIT VERSE:\n"
                f"{sanskrit_text}\n\n"
                f"📖 MEANING:\n"
                f"{meaning_text}\n\n"
                f"💡 THE MOMENT (PRACTICAL INSIGHT):\n"
                f"{insight_text}\n\n"
                f"--------------------------------------------------\n"
                f"Studio Master: @BhagavadGita-slokha\n"
                f"Creator & Sound Design: Venkatesh Marturu\n"
                f"Copyright: © 2026 @BhagavadGita-slokha. All rights reserved.\n"
                f"Audio License: Music composition arranged via FlowMusic AI.\n"
                f"--------------------------------------------------\n\n"
                f"#BhagavadGita #Krishna #Shorts #DailyWisdom #Spirituality #Hinduism #Geeta #mindfulnessforsleep"
            )
            print(f"  ✓ Successfully locked metadata for Chapter {ch} Verse {vs}")
        except Exception as e:
            print(f"  [DESC ERROR] Failed parsing JSON file {json_path}: {e}")

    # 4. Auto-discover video path if still missing
    if not video_path or not Path(video_path).exists():
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
            raise FileNotFoundError("Could not locate final rendered .mp4 file for upload.")

    print(f"  [UPLOADER] Target video file verified: {video_path}")

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

    print(f"  [UPLOADER] Commencing YouTube Shorts publication: {Path(video_path).name}")
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
        if playlist_id and video_id:
            add_video_to_playlist(youtube, video_id, playlist_id)

    return video_url

upload_to_youtube = upload_short_to_youtube
upload_video = upload_short_to_youtube
