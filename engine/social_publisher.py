import os
import requests
import time
from pathlib import Path
from engine.uploader import upload_short_to_youtube

def publish_to_instagram_reels(
    video_public_url: str,
    caption: str,
    access_token: str,
    ig_user_id: str
):
    """
    Publishes a Reel to Instagram via the Meta Graph API.
    """
    if not access_token or not ig_user_id or not video_public_url:
        print("  [IG WARN] Skipping Instagram publish: Missing credentials or public video URL.")
        return None

    print(f"  [IG] Creating Instagram media container...")
    creation_url = f"https://graph.facebook.com/v18.0/{ig_user_id}/media"
    payload = {
        "media_type": "REELS",
        "video_url": video_public_url,
        "caption": caption,
        "access_token": access_token
    }

    try:
        response = requests.post(creation_url, data=payload)
        res_data = response.json()
        
        if "id" not in res_data:
            print(f"  [IG ERROR] Failed to create container: {res_data}")
            return None

        creation_id = res_data["id"]
        print(f"  [IG] Container created ({creation_id}). Waiting for processing...")

        # Poll status until processing is complete
        status_url = f"https://graph.facebook.com/v18.0/{creation_id}"
        for _ in range(15):
            status_res = requests.get(status_url, params={"fields": "status_code", "access_token": access_token}).json()
            status = status_res.get("status_code")
            print(f"  [IG STATUS] {status}")
            
            if status == "FINISHED":
                break
            elif status == "ERROR":
                print(f"  [IG ERROR] Video processing failed on Instagram.")
                return None
            time.sleep(10)

        # Publish the container
        publish_url = f"https://graph.facebook.com/v18.0/{ig_user_id}/media_publish"
        pub_response = requests.post(publish_url, data={"creation_id": creation_id, "access_token": access_token}).json()
        
        if "id" in pub_response:
            media_id = pub_response["id"]
            print(f"  ✓ Instagram Reel Published Successfully! Media ID: {media_id}")
            return media_id
        else:
            print(f"  [IG ERROR] Publish failed: {pub_response}")
            return None

    except Exception as e:
        print(f"  [IG EXCEPTION] {e}")
        return None

def run_multi_platform_distribution(
    video_path: Path,
    chapter: int,
    verse: int,
    sanskrit: str,
    meaning: str,
    insight: str,
    project_root: Path,
    music_attribution: str = "",
    schedule: bool = False,
    playlist_id: str = "",
    public_video_url: str = ""
):
    """
    Orchestrates automated publishing across YouTube Shorts and Instagram/Facebook Reels.
    """
    print(f"\n==============================================")
    print(f"      STARTING MULTI-PLATFORM DISTRIBUTION      ")
    print(f"==============================================")

    # 1. Publish to YouTube
    youtube_video_id = None
    try:
        youtube_video_id = upload_short_to_youtube(
            video_path=video_path,
            chapter=chapter,
            verse=verse,
            sanskrit=sanskrit,
            meaning=meaning,
            insight=insight,
            project_root=project_root,
            music_attribution=music_attribution,
            schedule=schedule,
            playlist_id=playlist_id
        )
    except Exception as e:
        print(f"  [YOUTUBE ERROR] {e}")

    # 2. Publish to Instagram Reels (if credentials are provided in environment variables)
    ig_token = os.getenv("IG_ACCESS_TOKEN")
    ig_user_id = os.getenv("IG_USER_ID")
    
    if ig_token and ig_user_id and public_video_url:
        caption = f"Gita Ch {chapter}, Verse {verse} | Divine Wisdom 📜\n\n{meaning}\n\n#BhagavadGita #Krishna #Shorts #Spirituality"
        publish_to_instagram_reels(public_video_url, caption, ig_token, ig_user_id)
    else:
        print("  [INFO] Instagram distribution skipped (IG_ACCESS_TOKEN, IG_USER_ID, or public_video_url not set).")

    print(f"==============================================")
    print(f"        DISTRIBUTION PIPELINE FINISHED        ")
    print(f"==============================================")
    return youtube_video_id
