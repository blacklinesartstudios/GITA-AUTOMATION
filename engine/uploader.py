import os
import sys
import time
import random
import datetime
from pathlib import Path
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

# Full upload permission scope
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube"
]

def get_authenticated_service(project_root: Path):
    """
    Handles OAuth 2.0 authentication with persistent token caching and auto-refresh.
    Fails safely with a descriptive error if running in headless CI without valid tokens.
    """
    project_root = Path(project_root).resolve()
    token_path = project_root / "token.json"
    client_secrets_path = project_root / "client_secrets.json"

    if not client_secrets_path.exists():
        alt_secret = project_root / "client_secret.json"
        if alt_secret.exists():
            client_secrets_path = alt_secret
        else:
            raise FileNotFoundError(
                f"Missing OAuth client secret file at {client_secrets_path}. "
                "Download your OAuth client JSON from Google Cloud Console."
            )

    creds = None

    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception as e:
            print(f"  [AUTH] Could not parse existing token.json ({e}).")
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("  [AUTH] Access token expired. Refreshing token via OAuth refresh flow...")
            try:
                creds.refresh(Request())
                print("  [AUTH] Token successfully refreshed!")
            except Exception as e:
                print(f"  [AUTH] Token refresh failed ({e}).")
                creds = None

        if not creds:
            if os.getenv("CI") or os.getenv("GITHUB_ACTIONS"):
                raise RuntimeError(
                    "  [AUTH ERROR] Interactive browser authentication cannot run in headless CI. "
                    "Your YOUTUBE_TOKEN_JSON secret is missing, invalid, or lacks a refresh_token."
                )
            
            print("  [AUTH] Launching local browser server for one-time YouTube OAuth authorization...")
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_path), SCOPES)
            creds = flow.run_local_server(port=0)

        token_path.write_text(creds.to_json(), encoding="utf-8")
        print(f"  [AUTH] Credentials cached successfully to {token_path.name}")

    return build("youtube", "v3", credentials=creds)

def format_shorts_metadata(chapter: int, verse: int, sanskrit: str, meaning: str, insight: str, music_attribution: str = "") -> dict:
    title = f"Gita Wisdom: Ch {chapter}, Verse {verse} | Divine Message #Shorts"
    if len(title) > 100:
        title = title[:97] + "..."

    description_lines = [
        f"॥ श्रीमद्भगवद्गीता ॥",
        f"Chapter {chapter}, Verse {verse}\n",
        f"📜 SANSKRIT VERSE:",
        f"{sanskrit}\n",
        f"📖 MEANING:",
        f"{meaning}\n",
        f"💡 THE MOMENT (PRACTICAL INSIGHT):",
        f"{insight}\n",
        f"--------------------------------------------------",
        f"Studio Master: BLACKLINES ART STUDIO",
        f"Creator & Sound Design: Venkatesh Marturu",
        f"Copyright: © 2026 BLACKLINES ART STUDIO. All rights reserved.",
        f"Audio License: {music_attribution if music_attribution else 'Original Composition / FlowMusic AI'}",
        f"--------------------------------------------------\n",
        f"#BhagavadGita #Krishna #Shorts #DailyWisdom #Spirituality #Hinduism #Geeta #Mindfulness"
    ]
    description = "\n".join(description_lines)

    tags = [
        "Bhagavad Gita",
        f"Bhagavad Gita Chapter {chapter}",
        f"Gita Sloka {chapter}.{verse}",
        "Lord Krishna",
        "Spiritual Wisdom",
        "Shorts",
        "Daily Motivation",
        "Blacklines Art Studio",
        "Hindu Philosophy",
        "Sanatan Dharma"
    ]

    return {
        "title": title,
        "description": description,
        "tags": tags,
        "categoryId": "27"
    }

def add_video_to_playlist(youtube, video_id: str, playlist_id: str):
    """
    Automatically adds a successfully uploaded YouTube video to a designated playlist ID.
    """
    if not playlist_id:
        return
        
    try:
        print(f"  [PLAYLIST] Adding video {video_id} to playlist {playlist_id}...")
        request = youtube.playlistItems().insert(
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
        )
        response = request.execute()
        print(f"  ✓ Successfully added video to playlist!")
        return response
    except Exception as e:
        print(f"  [PLAYLIST WARN] Could not add video to playlist: {e}")

def upload_short_to_youtube(
    video_path: Path,
    chapter: int,
    verse: int,
    sanskrit: str,
    meaning: str,
    insight: str,
    project_root: Path,
    music_attribution: str = "",
    schedule: bool = False,
    playlist_id: str = "PL_ENGLISH_VERSION_ID_HERE"
):
    video_path = Path(video_path).resolve()
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found at: {video_path}")

    youtube = get_authenticated_service(project_root)
    meta = format_shorts_metadata(chapter, verse, sanskrit, meaning, insight, music_attribution)

    status_body = {
        "selfDeclaredMadeForKids": False
    }

    if schedule:
        publish_time = (
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
        ).replace(hour=4, minute=0, second=0, microsecond=0).isoformat()
        
        status_body["privacyStatus"] = "private"
        status_body["publishAt"] = publish_time
        print(f"  [UPLOAD] Video scheduled for release at: {publish_time} (UTC)")
    else:
        status_body["privacyStatus"] = "public"

    body = {
        "snippet": meta,
        "status": status_body
    }

    print(f"  [UPLOAD] Initializing resumable upload: {video_path.name}...")
    media = MediaFileUpload(
        str(video_path),
        chunksize=1024 * 1024 * 8,
        resumable=True,
        mimetype="video/mp4"
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    response = None
    retry_count = 0
    max_retries = 5

    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                progress_pct = int(status.progress() * 100)
                sys.stdout.write(f"\r  [UPLOAD PROGRESS] Uploading: {progress_pct}% complete...")
                sys.stdout.flush()
        except HttpError as e:
            if e.resp.status in [500, 502, 503, 504]:
                retry_count += 1
                if retry_count > max_retries:
                    raise e
                sleep_time = random.uniform(2, 6) * retry_count
                print(f"\n  [UPLOAD WARN] Temporary network error ({e.resp.status}). Retrying in {sleep_time:.1f}s...")
                time.sleep(sleep_time)
            else:
                raise e
        except Exception as ex:
            retry_count += 1
            if retry_count > max_retries:
                raise ex
            sleep_time = random.uniform(2, 5) * retry_count
            print(f"\n  [UPLOAD WARN] Connection dropped. Retrying chunk in {sleep_time:.1f}s...")
            time.sleep(sleep_time)

    video_id = response.get("id")
    print(f"\n  ✓ YouTube Upload Complete! Video ID: {video_id}")
    print(f"  ✓ Watch URL: https://youtube.com/shorts/{video_id}")

    # Automatically add to the specified English version playlist
    if playlist_id and playlist_id != "PL_ENGLISH_VERSION_ID_HERE":
        add_video_to_playlist(youtube, video_id, playlist_id)

    return video_id
