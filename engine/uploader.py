import os
import sys
import json
import time
from pathlib import Path

def get_authenticated_service(project_root: Path):
    """
    Authenticates with YouTube Data API v3 using token.json or client_secrets.json.
    Guards against headless browser hangs on GitHub Actions.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        print("  [UPLOAD ERROR] Google API client libraries not installed.")
        print("  Run: pip install google-api-python-client google-auth-oauthlib google-auth-httplib2")
        return None

    scopes = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube"
    ]

    project_root = Path(project_root).resolve()
    token_path = project_root / "token.json"
    client_secrets_path = project_root / "client_secrets.json"

    creds = None
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), scopes)
        except Exception as e:
            print(f"  [UPLOAD WARNING] Error reading token.json: {e}")

    is_ci = os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("CI") == "true"

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                print("  [UPLOAD] Refreshing expired OAuth access token...")
                creds.refresh(Request())
                token_path.write_text(creds.to_json(), encoding="utf-8")
                print("  ✓ Access token refreshed successfully.")
            except Exception as e:
                print(f"  [UPLOAD ERROR] Could not refresh token: {e}")
                creds = None

        if not creds and client_secrets_path.exists():
            if is_ci:
                print("  [UPLOAD ERROR] Running in headless CI (GitHub Actions). Interactive browser login unavailable.")
                print("  Please ensure YOUTUBE_TOKEN_JSON secret contains a valid refresh_token.")
                return None
            try:
                print("  [UPLOAD] Starting local browser OAuth login...")
                flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_path), scopes)
                creds = flow.run_local_server(port=0)
                token_path.write_text(creds.to_json(), encoding="utf-8")
                print("  ✓ New token.json generated and saved.")
            except Exception as e:
                print(f"  [UPLOAD ERROR] OAuth flow failed: {e}")
                return None

    if not creds:
        print("  [UPLOAD ERROR] No valid YouTube credentials found on system.")
        return None

    return build("youtube", "v3", credentials=creds)

def add_video_to_playlist(youtube, video_id: str, playlist_id: str):
    """Inserts uploaded Short into the designated language playlist."""
    if not playlist_id or playlist_id.startswith("PL_"):
        return
    try:
        request_body = {
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {
                    "kind": "youtube#video",
                    "videoId": video_id
                }
            }
        }
        youtube.playlistItems().insert(
            part="snippet",
            body=request_body
        ).execute()
        print(f"  ✓ Video added to playlist: {playlist_id}")
    except Exception as e:
        print(f"  [UPLOAD WARNING] Could not add video to playlist {playlist_id}: {e}")

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
    playlist_id: str = None,
    **kwargs
) -> str | None:
    """
    Uploads the master 9:16 Short to YouTube, assigns metadata, and links to playlists.
    """
    video_path = Path(video_path).resolve()
    if not video_path.exists():
        print(f"  [UPLOAD ERROR] Target video not found at: {video_path}")
        return None

    youtube = get_authenticated_service(project_root)
    if not youtube:
        print(f"  [UPLOAD FAILED] Authentication failed. Video remains saved locally at: {video_path.name}")
        return None

    try:
        from googleapiclient.http import MediaFileUpload

        title = f"Bhagavad Gita | Chapter {chapter}, Verse {verse} #Shorts #Gita"
        if len(title) > 100:
            title = title[:97] + "..."

        description = (
            f"॥ श्रीमद्भगवद्गीता ॥\n"
            f"Chapter {chapter}, Verse {verse}\n\n"
            f"श्लोक:\n{sanskrit}\n\n"
            f"Meaning:\n{meaning}\n\n"
            f"Practical Insight:\n{insight}\n\n"
            f"---\n"
            f"{music_attribution}\n"
            f"Produced by BLACKLINES ART STUDIO\n"
            f"#Shorts #BhagavadGita #Krishna #SpiritualWisdom #AncientWisdom #Mindset"
        )

        tags = [
            "Bhagavad Gita",
            f"Chapter {chapter}",
            f"Verse {verse}",
            "Krishna",
            "Spiritual Wisdom",
            "Shorts",
            "Motivation",
            "Philosophy"
        ]

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": "27"  # Education
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False
            }
        }

        media = MediaFileUpload(
            str(video_path),
            chunksize=-1,
            resumable=True,
            mimetype="video/mp4"
        )

        print(f"  [UPLOAD] Uploading {video_path.name} to YouTube...")
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"    Uploaded {int(status.progress() * 100)}%...")

        video_id = response.get("id")
        print(f"  ✓ Video successfully uploaded: https://youtu.be/{video_id}")

        if playlist_id:
            add_video_to_playlist(youtube, video_id, playlist_id)

        return video_id

    except Exception as e:
        print(f"  [UPLOAD ERROR] API upload failed: {e}")
        return None
