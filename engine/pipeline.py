import json
import random
import sys
from pathlib import Path

from engine.audio_mixer import mix_full_soundtrack
from engine.gita_store import get_verse_from_dataset
from engine.uploader import upload_short_to_youtube
from engine.video import get_audio_duration, mux, render_master_video

def run_pipeline(root: Path, cfg: dict | None = None, fast_mode: bool = False):
    root = Path(root).resolve()
    tracker_file = root / "tracker.json"
    cache_dir = root / "cache"
    output_dir = root / "output"

    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("      SHRIMAD BHAGAVAD GITA — AUTOMATION PIPELINE      ")
    print("=" * 60)

    if not tracker_file.exists():
        tracker_file.write_text(
            json.dumps({"chapter": 1, "verse": 1}, indent=2), encoding="utf-8"
        )

    tracker = json.loads(tracker_file.read_text(encoding="utf-8"))
    ch = int(tracker.get("chapter", 1))
    v = int(tracker.get("verse", 1))

    print(f"\n[1/6] Loading Chapter {ch}, Verse {v} from Offline Gita Master...")
    verse_record = get_verse_from_dataset(ch, v, root)

    sanskrit_txt = verse_record["sloka"]["sanskrit"]
    meaning_txt = verse_record["authentic_translation"]["english"]
    dialogue = verse_record.get("viewer_dialogue", {})
    insight_txt = f"{dialogue.get('explanation', '')} {dialogue.get('practical_takeaway', '')}".strip()

    render_cfg = {
        "verse": {
            "chapter": ch,
            "verse_number": v,
            "sanskrit": sanskrit_txt,
            "meaning": meaning_txt,
            "insight": insight_txt,
        }
    }
    cfg_path = cache_dir / "render_config.json"
    cfg_path.write_text(json.dumps(render_cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n[2/6] Mixing Soundtrack & Applying Vocal DSP...")
    mastered, bg_music_track, music_attribution = mix_full_soundtrack(str(cfg_path), project_root=root)

    sans_wav = cache_dir / "sanskrit_processed.wav"
    eng_wav = cache_dir / "narration_processed.wav"
    sans_dur = get_audio_duration(str(sans_wav))
    eng_dur = get_audio_duration(str(eng_wav))
    total_audio_dur = get_audio_duration(str(mastered))

    print(f"  ✓ Sanskrit Chanting Duration: {sans_dur:.1f}s")
    print(f"  ✓ English Narration Duration: {eng_dur:.1f}s")
    print(f"  ✓ Total Video Timeline Duration: {total_audio_dur:.1f}s (Min 60s+ Floor)")

    print("\n[3/6] Selecting & Distributing Visual Assets...")
    img_dir = root / "assets" / "images"
    valid_exts = {".png", ".jpg", ".jpeg", ".webp"}
    all_imgs = [p for p in img_dir.iterdir() if p.suffix.lower() in valid_exts]

    if not all_imgs:
        raise FileNotFoundError(f"No background images found in {img_dir}")

    images_needed = max(6, int(total_audio_dur / 6.0))
    selected_images = []
    while len(selected_images) < images_needed:
        random.shuffle(all_imgs)
        selected_images.extend(all_imgs)
    selected_images = selected_images[:images_needed]

    print(f"  ✓ Selected {len(selected_images)} scenes across timeline (~6.0s/cut)")

    print("\n[4/6] Executing 3D Parallax Video Render...")
    visuals_mp4 = cache_dir / "visuals_temp.mp4"
    final_output = output_dir / f"GITA_CHAPTER_{ch:02d}_VERSE_{v:02d}.mp4"

    render_master_video(
        images=selected_images,
        out=str(visuals_mp4),
        master_audio_path=str(mastered),
        bg_music_path=str(bg_music_track),
        w=1080,
        h=1920,
        fps=30,
        cfg_path=str(cfg_path),
        sans_dur=sans_dur,
        eng_dur=eng_dur,
        fast_mode=fast_mode,
    )

    print("\n[5/6] Muxing Video and Audio with Studio Master Metadata...")
    mux(visuals_mp4, mastered, final_output, chapter=ch, verse=v)
    print(f"  ✓ Master Video Exported: {final_output.resolve()}")

    print("\n[6/6] Finalizing Distribution & Auto-Upload...")
    auto_upload = True
    if auto_upload and not fast_mode:
        try:
            upload_short_to_youtube(
                video_path=final_output,
                chapter=ch,
                verse=v,
                sanskrit=sanskrit_txt,
                meaning=meaning_txt,
                insight=insight_txt,
                project_root=root,
                music_attribution=music_attribution,
                schedule=True,
            )
            print("  ✓ Video successfully uploaded & scheduled to YouTube!")
        except Exception as e:
            print(f"  [WARN] YouTube upload error: {e}")

    tracker["verse"] = v + 1
    tracker_file.write_text(json.dumps(tracker, indent=2), encoding="utf-8")
    print(f"  ✓ Tracker advanced to Chapter {ch}, Verse {v + 1}")

    print("\n" + "=" * 60)
    print("               PIPELINE EXECUTION COMPLETE             ")
    print("=" * 60)

if __name__ == "__main__":
    fast_render = "--fast" in sys.argv
    project_root_dir = Path(__file__).resolve().parent.parent
    run_pipeline(project_root_dir, fast_mode=fast_render)