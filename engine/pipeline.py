import os
import json
import subprocess
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from engine.depth_renderer import UltraDepthRenderer
from engine.uploader import upload_short_to_youtube

# Custom Sequential Rollout: Indian Majority Languages first, followed by Global Languages
GLOBAL_LANGUAGES = [
    {"code": "en", "name": "English", "playlist_id": "PL_ENGLISH_VERSION_ID_HERE"},
    {"code": "hi", "name": "Hindi", "playlist_id": "PL_HINDI_VERSION_ID_HERE"},
    {"code": "te", "name": "Telugu", "playlist_id": "PL_TELUGU_VERSION_ID_HERE"},
    {"code": "ta", "name": "Tamil", "playlist_id": "PL_TAMIL_VERSION_ID_HERE"},
    {"code": "ml", "name": "Malayalam", "playlist_id": "PL_MALAYALAM_VERSION_ID_HERE"},
    {"code": "kn", "name": "Kannada", "playlist_id": "PL_KANNADA_VERSION_ID_HERE"},
    # Global expansion begins here after Indian languages are completed
    {"code": "es", "name": "Spanish", "playlist_id": "PL_SPANISH_VERSION_ID_HERE"},
    {"code": "fr", "name": "French", "playlist_id": "PL_FRENCH_VERSION_ID_HERE"},
    {"code": "de", "name": "German", "playlist_id": "PL_GERMAN_VERSION_ID_HERE"},
    {"code": "ja", "name": "Japanese", "playlist_id": "PL_JAPANESE_VERSION_ID_HERE"},
]

def get_font(project_root: Path, font_name: str, size: int):
    project_root = Path(project_root).resolve()
    font_path = project_root / "assets" / "fonts" / font_name
    
    if font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception:
            pass
            
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
    Orchestrates sequential language rotation following the Indian-to-Global rollout plan.
    """
    root = Path(root).resolve()
    print(f"\n[PIPELINE] Initializing Sequential Rollout Execution from root: {root}")

    # 1. Load Tracker State
    tracker_path = root / "tracker.json"
    if tracker_path.exists():
        tracker = json.loads(tracker_path.read_text(encoding="utf-8"))
    else:
        tracker = {"language_index": 0, "chapter": 1, "verse": 1}

    lang_idx = tracker.get("language_index", 0)
    chapter = tracker.get("chapter", 1)
    verse = tracker.get("verse", 1)

    if lang_idx >= len(GLOBAL_LANGUAGES):
        print("[PIPELINE] All scheduled languages in the rollout list have been completed!")
        lang_idx = 0

    current_lang = GLOBAL_LANGUAGES[lang_idx]
    print(f"[PIPELINE] Active Language Target: {current_lang['name']} ({current_lang['code'].upper()})")
    print(f"[PIPELINE] Current Target -> Chapter {chapter}, Verse {verse}")

    # 2. Localized Verse Metadata
    sanskrit_text = "यदा यदा हि धर्मस्य ग्लानिर्भवति भारत।"
    meaning = f"[{current_lang['name']}] Whenever righteousness declines and unrighteousness prevails, I manifest Myself."
    insight = "True leadership means standing up for moral clarity during times of societal crisis."
    
    output_dir = root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    video_filename = f"GITA_{current_lang['code'].upper()}_CH{chapter:02d}_VS{verse:02d}.mp4"
    final_video_path = output_dir / video_filename

    # 3. Initialize Ultra Depth Renderer (ONNX Depth Anything v2)
    depth_renderer = UltraDepthRenderer(root)

    # 4. Render sample frame and depth map
    print("[PIPELINE] Rendering 3D Parallax & Depth Frames...")
    temp_dir = root / "temp"
    temp_dir.mkdir(exist_ok=True)

    base_img = Image.new("RGB", (1080, 1920), color=(15, 15, 25))
    draw = ImageDraw.Draw(base_img)
    
    font_sanskrit = get_font(root, "NotoSerifDevanagari-Bold.ttf", 40)
    font_title = get_font(root, "Cinzel-Bold.ttf", 36)

    draw.text((540, 300), f"{current_lang['name']} | Ch {chapter}, V {verse}", font=font_title, fill=(255, 215, 0), anchor="mm")
    draw.text((540, 600), sanskrit_text, font=font_sanskrit, fill=(255, 255, 255), anchor="mm")
    
    sample_frame_path = temp_dir / "frame_0001.png"
    base_img.save(sample_frame_path)

    depth_map = depth_renderer.generate_depth_map(np.array(base_img))
    depth_path = root / "depth"
    depth_path.mkdir(exist_ok=True)
    Image.fromarray(depth_map).save(depth_path / f"depth_{current_lang['code']}_{chapter}_{verse}.png")

    # 5. Export Video via FFmpeg
    print(f"[PIPELINE] Exporting Master Video to {final_video_path}...")
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(sample_frame_path),
        "-t", "5", "-pix_fmt", "yuv420p", "-vf", "scale=1080:1920",
        str(final_video_path)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print(f"  ✓ Master Video Exported: {final_video_path}")

    # 6. Upload to YouTube & Assign to Language-Specific Playlist
    print("[PIPELINE] Finalizing Distribution & Auto-Upload...")
    playlist_id = current_lang["playlist_id"]
    
    try:
        upload_short_to_youtube(
            video_path=final_video_path,
            chapter=chapter,
            verse=verse,
            sanskrit=sanskrit_text,
            meaning=meaning,
            insight=insight,
            project_root=root,
            music_attribution=f"Original Composition ({current_lang['name']})",
            schedule=False,
            playlist_id=playlist_id
        )
    except Exception as e:
        print(f"  [UPLOAD WARNING] Automatic upload skipped or failed: {e}")

    # 7. Advance Tracker State & Language Progression
    next_verse = verse + 1
    next_chapter = chapter
    next_lang_idx = lang_idx

    if chapter > 18 or (chapter == 18 and next_verse > 78):
        print(f"  ✓ Completed all chapters in {current_lang['name']}! Rotating to next language...")
        next_lang_idx += 1
        next_chapter = 1
        next_verse = 1

    tracker["language_index"] = next_lang_idx
    tracker["chapter"] = next_chapter
    tracker["verse"] = next_verse
    tracker_path.write_text(json.dumps(tracker, indent=2), encoding="utf-8")
    
    upcoming_lang = GLOBAL_LANGUAGES[next_lang_idx % len(GLOBAL_LANGUAGES)]
    print(f"  ✓ Tracker advanced. Next Run Language: {upcoming_lang['name']} (Ch {next_chapter}, V {next_verse})")
    print("[PIPELINE] EXECUTION COMPLETE.")
