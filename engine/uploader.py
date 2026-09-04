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

    # Scan all positional arguments for json config or video files anywhere in the list
    for arg in args:
        if isinstance(arg, (str, Path)):
            p = Path(arg)
            if p.suffix.lower() == ".json" and p.exists():
                json_path = p
            elif p.suffix.lower() in [".mp4", ".mov", ".mkv"] and p.exists():
                video_path = p

    # If we found a json config, parse it to lock in exact chapter, verse, and description
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
        except Exception as e:
            print(f"  [DESC ERROR] Failed parsing JSON file {json_path}: {e}")

    # Fallback to find video path if not explicitly provided
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
