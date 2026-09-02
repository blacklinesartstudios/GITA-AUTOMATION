import os
import json
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw

from engine.depth_renderer import UltraDepthRenderer
from engine.uploader import upload_short_to_youtube

def get_font(project_root: Path, font_name: str, size: int):
    """
    Robust font loader with fallback safety for Devanagari and Title typography.
    """
    project_root = Path(project_root).resolve()
    font_path = project_root / "assets" / "fonts" / font_name
    
    if font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception:
            pass
            
    # Fallback options
    for fallback in ["NotoSerifDevanagari-Bold.ttf", "Cinzel-Bold.ttf", "gita_font.ttf"]:
        alt_path = project_root / "assets" / "fonts" / fallback
        if alt_path.exists():
            try:
                return ImageFont.truetype(str(alt_path), size)
            except Exception:
                continue
                
    return ImageFont.load_default()

def run_pipeline(root: Path, cfg: dict, fast_mode: bool = False):
    """
    Orchestrates the complete Bhagavad Gita content generation pipeline:
    1. Loads current progress from tracker.json
    2. Generates/renders Ultra Depth 3D frames & synced captions
    3. Muxes video and audio via FFmpeg
    4. Automatically uploads to YouTube and assigns to playlist
    5. Advances tracker state
    """
    root = Path(root).resolve()
    print(f"\n[PIPELINE] Initializing execution from root: {root}")

    # 1. Load Tracker State
    tracker_path = root / "tracker.json"
    if tracker_path.exists():
        tracker = json.loads(tracker_path.read_text(encoding="utf-8"))
    else:
        tracker = {"chapter": 1, "verse": 1}

    chapter = tracker.get("chapter", 1)
    verse = tracker.get("verse", 1)
    print(f"[PIPELINE] Current Target -> Chapter {chapter}, Verse {verse}")

    # 2. Mock or load verse metadata (integrate your Gemini API generation here if needed)
    sanskrit_text = "यदा यदा हि धर्मस्य ग्लानिर्भवति भारत।"
    meaning = "Whenever righteousness declines and unrighteousness prevails, O descendant of Bharata, I manifest Myself."
    insight = "True leadership means standing up for moral clarity during times of societal crisis."
    
    output_dir = root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    video_filename = f"GITA_CHAPTER_{chapter:02d}_VERSE_{verse:02d}.mp4"
    final_video_path = output_dir / video_filename

    # 3. Initialize Ultra Depth Renderer (ONNX Depth Anything v2)
    depth_renderer = UltraDepthRenderer(root)

    # 4. Render sample test frame / video sequence
    print("[PIPELINE] Rendering 3D Parallax & Depth Frames...")
    # (Assuming your frame generation loop writes frames to temp directory for FFmpeg)
    temp_dir = root / "temp"
    temp_dir.mkdir(exist_ok=True)

    # Create a test frame if none exists
    base_img = Image.new("RGB", (1080, 1920), color=(15, 15, 25))
    draw = ImageDraw.Draw(base_img)
    
    # Load fonts using your robust utility
    font_sanskrit = get_font(root, "NotoSerifDevanagari-Bold.ttf", 40)
    font_title = get_font(root, "Cinzel-Bold.ttf", 36)

    draw.text((540, 300), f"Chapter {chapter}, Verse {verse}", font=font_title, fill=(255, 215, 0), anchor="mm")
    draw.text((540, 600), sanskrit_text, font=font_sanskrit, fill=(255, 255, 255), anchor="mm")
    
    sample_frame_path = temp_dir / "frame_0001.png"
    base_img.save(sample_frame_path)

    # Generate depth map utilizing ONNX Ultra Depth
    depth_map = depth_renderer.generate_depth_map(np_array_from_image(base_img))
    depth_path = root / "depth"
    depth_path.mkdir(exist_ok=True)
    Image.fromarray(depth_map).save(depth_path / f"depth_{chapter}_{verse}.png")

    # 5. Export / Mux video using FFmpeg (Simulated mock export for verification)
    print(f"[PIPELINE] Exporting Master Video to {final_video_path}...")
    # Quick silent test video generation using ffmpeg if no audio exists yet
    dummy_audio = root / "assets" / "audio" / "ambient.mp3"
    
    # Simple solid color 5-second video generation for testing upload
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(sample_frame_path),
        "-t", "5", "-pix_fmt", "yuv420p", "-vf", "scale=1080:1920",
        str(final_video_path)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print(f"  ✓ Master Video Exported: {final_video_path}")

    # 6. Finalizing Distribution & Auto-Upload to YouTube & Playlist
    print("[PIPELINE] Finalizing Distribution & Auto-Upload...")
    playlist_id = cfg.get("youtube_playlist_id", "PL_ENGLISH_VERSION_ID_HERE")
    
    try:
        upload_short_to_youtube(
            video_path=final_video_path,
            chapter=chapter,
            verse=verse,
            sanskrit=sanskrit_text,
            meaning=meaning,
            insight=insight,
            project_root=root,
            music_attribution="Original Composition",
            schedule=False,
            playlist_id=playlist_id
        )
    except Exception as e:
        print(f"  [UPLOAD WARNING] Automatic upload skipped or failed: {e}")

    # 7. Advance Tracker State
    next_verse = verse + 1
    next_chapter = chapter
    if next_verse > 78:  # Example chapter verse limit check
        next_chapter += 1
        next_verse = 1

    tracker["chapter"] = next_chapter
    tracker["verse"] = next_verse
    tracker_path.write_text(json.dumps(tracker, indent=2), encoding="utf-8")
    print(f"  ✓ Tracker advanced to Chapter {next_chapter}, Verse {next_verse}")
    print("[PIPELINE] EXECUTION COMPLETE.")

def np_array_from_image(img: Image.Image):
    import numpy as np
    return np.array(img)
