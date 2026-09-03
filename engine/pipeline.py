import json
import random
import sys
from pathlib import Path

from engine.audio_mixer import mix_full_soundtrack
from engine.uploader import upload_short_to_youtube
from engine.video import get_audio_duration, mux, render_master_video

BHAGAVAD_GITA_CHAPTERS = {
    1: 47,  2: 72,  3: 43,  4: 42,  5: 29,  6: 47,
    7: 30,  8: 28,  9: 34, 10: 42, 11: 55, 12: 20,
    13: 35, 14: 27, 15: 20, 16: 24, 17: 28, 18: 78
}

GLOBAL_LANGUAGES = [
    {"code": "en", "name": "English", "voice": "en-IN-PrabhatNeural", "playlist_id": "PL_ENGLISH_VERSION_ID_HERE"},
    {"code": "hi", "name": "Hindi", "voice": "hi-IN-MadhurNeural", "playlist_id": "PL_HINDI_VERSION_ID_HERE"},
    {"code": "te", "name": "Telugu", "voice": "te-IN-MohanNeural", "playlist_id": "PL_TELUGU_VERSION_ID_HERE"},
    {"code": "ta", "name": "Tamil", "voice": "ta-IN-ValluvarNeural", "playlist_id": "PL_TAMIL_VERSION_ID_HERE"},
    {"code": "ml", "name": "Malayalam", "voice": "ml-IN-MidhunNeural", "playlist_id": "PL_MALAYALAM_VERSION_ID_HERE"},
    {"code": "kn", "name": "Kannada", "voice": "kn-IN-GaganNeural", "playlist_id": "PL_KANNADA_VERSION_ID_HERE"},
    {"code": "es", "name": "Spanish", "voice": "es-ES-AlvaroNeural", "playlist_id": "PL_SPANISH_VERSION_ID_HERE"},
    {"code": "fr", "name": "French", "voice": "fr-FR-HenriNeural", "playlist_id": "PL_FRENCH_VERSION_ID_HERE"},
    {"code": "de", "name": "German", "voice": "de-DE-ConradNeural", "playlist_id": "PL_GERMAN_VERSION_ID_HERE"},
    {"code": "ja", "name": "Japanese", "voice": "ja-JP-KeitaNeural", "playlist_id": "PL_JAPANESE_VERSION_ID_HERE"},
]

def load_verified_verse(root: Path, chapter: int, verse: int, lang_code: str) -> dict:
    try:
        from engine.gita_store import get_verse_from_dataset
        raw = get_verse_from_dataset(chapter, verse, root)
        if raw and "sloka" in raw:
            translations = raw.get("authentic_translation", {})
            dialogue = raw.get("viewer_dialogue", {})
            return {
                "sanskrit": raw["sloka"].get("sanskrit", ""),
                "meaning": translations.get(lang_code, translations.get("english", "")),
                "insight": f"{dialogue.get('explanation', '')} {dialogue.get('practical_takeaway', '')}".strip()
            }
    except Exception:
        pass

    for candidate in [root / "data" / "verses.json", root / "verses.json", root / "data" / "gita.json"]:
        if candidate.exists():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                for c_k in [str(chapter), chapter]:
                    if isinstance(data, dict) and c_k in data and isinstance(data[c_k], dict):
                        for v_k in [str(verse), verse]:
                            if v_k in data[c_k]:
                                item = data[c_k][v_k]
                                return {
                                    "sanskrit": item.get("sanskrit", ""),
                                    "meaning": item.get(lang_code, item.get("meaning", item.get("english", ""))),
                                    "insight": item.get("insight", item.get("explanation", ""))
                                }
            except Exception:
                continue

    if chapter == 1 and verse == 9:
        return {
            "sanskrit": "अन्ये च बहवः शूरा मदर्थे त्यक्तजीविताः ।\nनानाशस्त्रप्रहरणाः सर्वे युद्धविशारदाः ॥",
            "meaning": "There are many other heroes who are prepared to lay down their lives for my sake. All of them are well-equipped with diverse weapons and experienced in the art of warfare.",
            "insight": "True leadership demands evaluating all inner challenges and recognizing unwavering commitment when stepping onto the battlefield of life."
        }

    return {
        "sanskrit": "धर्मक्षेत्रे कुरुक्षेत्रे समवेता युयुत्सवः।",
        "meaning": f"Bhagavad Gita Chapter {chapter}, Verse {verse}: Timeless wisdom illuminating the path of righteous duty.",
        "insight": "Every verse serves as a beacon for self-discipline, mental mastery, and decisive clarity."
    }

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
            json.dumps({"language_index": 0, "chapter": 1, "verse": 9}, indent=2), encoding="utf-8"
        )

    tracker = json.loads(tracker_file.read_text(encoding="utf-8"))
    lang_idx = int(tracker.get("language_index", 0))
    ch = int(tracker.get("chapter", 1))
    v = int(tracker.get("verse", 9))

    if lang_idx >= len(GLOBAL_LANGUAGES):
        print("  [ROLLOUT] Full global sequence complete! Cycling language queue...")
        lang_idx = 0

    current_lang = GLOBAL_LANGUAGES[lang_idx]
    print(f"\n[1/6] Loading Chapter {ch}, Verse {v} in [{current_lang['name'].upper()}]...")

    verse_record = load_verified_verse(root, ch, v, current_lang["code"])
    sanskrit_txt = verse_record["sanskrit"]
    meaning_txt = verse_record["meaning"]
    insight_txt = verse_record["insight"]

    render_cfg = {
        "verse": {
            "chapter": ch,
            "verse_number": v,
            "sanskrit": sanskrit_txt,
            "meaning": meaning_txt,
            "insight": insight_txt,
        },
        "language": current_lang,
        "narration_voice": current_lang["voice"]
    }
    cfg_path = cache_dir / "render_config.json"
    cfg_path.write_text(json.dumps(render_cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n[2/6] Mixing Soundtrack & Applying Studio Vocal DSP...")
    mastered, bg_music_track, music_attribution = mix_full_soundtrack(str(cfg_path), project_root=root)

    sans_wav = cache_dir / "sanskrit_processed.wav"
    eng_wav = cache_dir / "narration_processed.wav"
    sans_dur = get_audio_duration(str(sans_wav))
    eng_dur = get_audio_duration(str(eng_wav))
    total_audio_dur = get_audio_duration(str(mastered))

    print(f"  ✓ Sanskrit Chanting Duration: {sans_dur:.1f}s")
    print(f"  ✓ {current_lang['name']} Narration Duration: {eng_dur:.1f}s")
    print(f"  ✓ Total Master Audio Duration: {total_audio_dur:.1f}s (Dynamic timeline)")

    print("\n[3/6] Selecting & Distributing Visual Assets...")
    img_dir = root / "assets" / "images"
    valid_exts = {".png", ".jpg", ".jpeg", ".webp"}
    all_imgs = [p for p in img_dir.iterdir() if p.suffix.lower() in valid_exts] if img_dir.exists() else []

    if not all_imgs:
        fallback_img = cache_dir / "fallback_bg.png"
        if not fallback_img.exists():
            Image.new("RGB", (1080, 1920), color=(14, 16, 26)).save(str(fallback_img))
        all_imgs = [fallback_img]

    images_needed = max(6, int(total_audio_dur / 6.0))
    selected_images = []
    while len(selected_images) < images_needed:
        random.shuffle(all_imgs)
        selected_images.extend(all_imgs)
    selected_images = selected_images[:images_needed]

    print(f"  ✓ Selected {len(selected_images)} scenes across timeline (~6.0s/cut)")

    print("\n[4/6] Executing 3D Parallax Video Render...")
    visuals_mp4 = cache_dir / "visuals_temp.mp4"
    final_output = output_dir / f"GITA_{current_lang['code'].upper()}_CH{ch:02d}_VS{v:02d}.mp4"

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
    upload_succeeded = False

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
                schedule=False,
                playlist_id=current_lang.get("playlist_id")
            )
            print(f"  ✓ Video uploaded to {current_lang['name']} playlist!")
            upload_succeeded = True
        except Exception as e:
            print(f"  [WARN] YouTube upload skipped/error: {e}")

    next_v = v + 1
    next_ch = ch
    next_lang_idx = lang_idx

    max_verses = BHAGAVAD_GITA_CHAPTERS.get(ch, 47)
    if next_v > max_verses:
        next_ch += 1
        next_v = 1
        print(f"  ✓ Completed Chapter {ch}! Moving to Chapter {next_ch}...")

    if next_ch > 18:
        print(f"  ✓ Completed all 18 Chapters in {current_lang['name']}! Advancing to next language...")
        next_lang_idx += 1
        next_ch = 1
        next_v = 1

    tracker["language_index"] = next_lang_idx
    tracker["chapter"] = next_ch
    tracker["verse"] = next_v
    tracker_file.write_text(json.dumps(tracker, indent=2), encoding="utf-8")

    upcoming = GLOBAL_LANGUAGES[next_lang_idx % len(GLOBAL_LANGUAGES)]
    print(f"  ✓ Tracker advanced. Next target: {upcoming['name']} (Chapter {next_ch}, Verse {next_v})")
    print("\n" + "=" * 60)
    print("               PIPELINE EXECUTION COMPLETE             ")
    print("=" * 60)

if __name__ == "__main__":
    fast_render = "--fast" in sys.argv
    project_root_dir = Path(__file__).resolve().parent.parent
    run_pipeline(project_root_dir, fast_mode=fast_render)
