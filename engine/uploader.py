def add_video_to_playlist(youtube, video_id: str, playlist_id: str):
    """
    Adds a successfully uploaded YouTube video to a designated playlist ID.
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
        print(f"  ✓ Successfully added to playlist!")
        return response
    except Exception as e:
        print(f"  [PLAYLIST WARN] Could not add video to playlist: {e}")
