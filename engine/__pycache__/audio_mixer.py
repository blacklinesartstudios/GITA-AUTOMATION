import os
import json
import random
import shutil
import subprocess
import asyncio
import wave
from pathlib import Path

# Unified single voice for the entire video
UNIFIED_VOICE = "hi-IN-MadhurNeural"

def ffmpeg_bin():
    return shutil.which("ffmpeg") or r"C:\ffmpeg\bin\ffmpeg.exe"

def get_audio_duration_sec(wav_path: Path) -> float:
    if not wav_path.exists():
        return 0.0
    try:
        with wave.open(str(wav_path), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 0.0

async def generate_edge_tts(text: str, voice: str, out_wav: Path, rate: str = "-10%", pitch: str = "-5Hz"):
    """Generates speech using edge-tts with gTTS fallback."""
    temp_mp3 = out_wav.with_suffix(".temp.mp3")
    try:
        import edge_tts
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        await communicate.save(str(temp_mp3))
        
        subprocess.run([
            ffmpeg_bin(), "-y", "-i", str(temp_mp3),
            "-ac", "2", "-ar", "44100", str(out_wav)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if temp_mp3.exists():
            temp_mp3.unlink()
        return True
    except Exception as e:
        print(f"  [TTS Fallback] edge-tts error: {e}. Attempting gTTS...")
        try:
            from gtts import gTTS
            tts = gTTS(text=text, lang="hi", slow=False)
            tts.save(str(temp_mp3))
            subprocess.run([
                ffmpeg_bin(), "-y", "-i", str(temp_mp3),
                "-ac", "2", "-ar", "44100", str(out_wav)
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if temp_mp3.exists():
                temp_mp3.unlink()
            return True
        except Exception:
            return False

def apply_temple_reverb(in_wav: Path, out_wav: Path):
    """Applies deep spiritual temple reverb to the Sanskrit chant."""
    filter_chain = "aecho=0.8:0.88:60|120:0.4|0.25,volume=1.2"
    subprocess.run([
        ffmpeg_bin(), "-y", "-i", str(in_wav),
        "-af", filter_chain,
        str(out_wav)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

def generate_voices(render_cfg_path: str, project_root: Path):
    cache = project_root / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    
    cfg = json.loads(Path(render_cfg_path).read_text(encoding="utf-8"))
    verse = cfg.get("verse", {})
    
    sanskrit_txt = verse.get("sanskrit", "").replace("\\n", " ").strip()
    meaning_txt = verse.get("meaning", "").strip()
    insight_txt = verse.get("insight", "").strip()

    full_narration = f"Meaning. {meaning_txt} ... The Moment. {insight_txt}"

    sans_raw_wav = cache / "sanskrit_raw.wav"
    sans_proc_wav = cache / "sanskrit_processed.wav"
    narr_proc_wav = cache / "narration_processed.wav"

    # 1. Sanskrit Chanting (hi-IN-MadhurNeural + Spiritual Reverb)
    print(f"  [VOICE] Synthesizing Sanskrit Chanting with {UNIFIED_VOICE}...")
    asyncio.run(generate_edge_tts(sanskrit_txt, UNIFIED_VOICE, sans_raw_wav, rate="-15%", pitch="-8Hz"))
    
    if sans_raw_wav.exists() and get_audio_duration_sec(sans_raw_wav) > 0.5:
        apply_temple_reverb(sans_raw_wav, sans_proc_wav)
    else:
        subprocess.run([
            ffmpeg_bin(), "-y", "-f", "lavfi", "-i", "sine=frequency=136.1:duration=6",
            "-af", "volume=0.3", str(sans_proc_wav)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 2. English Meaning & Insight Narration (Same Voice: hi-IN-MadhurNeural)
    print(f"  [VOICE] Synthesizing Narration with {UNIFIED_VOICE}...")
    asyncio.run(generate_edge_tts(full_narration, UNIFIED_VOICE, narr_proc_wav, rate="-8%", pitch="-4Hz"))
    
    if not narr_proc_wav.exists() or get_audio_duration_sec(narr_proc_wav) < 1.0:
        subprocess.run([
            ffmpeg_bin(), "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", "40", str(narr_proc_wav)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def mix_full_soundtrack(render_cfg_path: str, project_root: Path) -> tuple[Path, str]:
    assets = project_root / "assets"
    music_dir = assets / "music"
    cache = project_root / "cache"
    cache.mkdir(parents=True, exist_ok=True)

    generate_voices(render_cfg_path, project_root)

    valid_exts = {".mp3", ".wav", ".aac", ".flac", ".ogg"}
    music_tracks = [p for p in music_dir.iterdir() if p.suffix.lower() in valid_exts]
    if not music_tracks:
        raise FileNotFoundError(f"No background music files found in {music_dir}")
    
    selected_music = random.choice(music_tracks)
    print(f"[AUDIO] Selected Background Track: {selected_music.name}")

    attribution_str = ""
    meta_path = music_dir / "music_library.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            track_info = meta.get(selected_music.name, {})
            attribution_str = track_info.get("attribution", "").strip()
        except Exception:
            pass

    sans_wav = cache / "sanskrit_processed.wav"
    eng_wav = cache / "narration_processed.wav"

    sans_dur = get_audio_duration_sec(sans_wav)
    eng_dur = get_audio_duration_sec(eng_wav)

    # Timeline spacing: Intro + Sanskrit + Pause + Narration + Outro
    sans_delay_sec = 2.4
    narr_delay_sec = sans_delay_sec + sans_dur + 1.8
    natural_timeline_sec = narr_delay_sec + eng_dur + 4.0
    total_timeline_sec = max(62.0, natural_timeline_sec)

    sans_delay_ms = int(sans_delay_sec * 1000)
    narr_delay_ms = int(narr_delay_sec * 1000)

    master_out = cache / "master_soundtrack.wav"

    filter_complex = (
        f"[0:a]adelay={sans_delay_ms}|{sans_delay_ms},volume=1.35[sans];"
        f"[1:a]adelay={narr_delay_ms}|{narr_delay_ms},volume=1.45[narr];"
        f"[2:a]aloop=loop=-1:size=2e+09,atrim=0:{total_timeline_sec},"
        f"volume=0.18,afade=t=in:st=0:d=2.5,afade=t=out:st={total_timeline_sec-3.5}:d=3.5[bg];"
        f"[sans][narr][bg]amix=inputs=3:duration=longest:dropout_transition=3[out]"
    )

    cmd = [
        ffmpeg_bin(), "-y",
        "-i", str(sans_wav),
        "-i", str(eng_wav),
        "-i", str(selected_music),
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-ac", "2",
        "-ar", "44100",
        str(master_out)
    ]

    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return master_out, attribution_str