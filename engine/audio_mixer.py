import os
import json
import random
import shutil
import subprocess
import asyncio
import wave
from pathlib import Path

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

def process_voice_dsp(in_wav: Path, out_wav: Path, is_chant: bool = False):
    if is_chant:
        audio_filter = (
            "equalizer=f=110:width_type=o:w=1.2:g=5.5,"
            "equalizer=f=240:width_type=o:w=1.0:g=3.0,"
            "equalizer=f=3200:width_type=o:w=1.0:g=-2.0,"
            "aecho=0.8:0.88:40|80|140:0.4|0.3|0.2,"
            "acompressor=threshold=-18dB:ratio=3:attack=15:release=120,"
            "loudnorm=I=-16:TP=-1.5:LRA=11"
        )
    else:
        audio_filter = (
            "equalizer=f=140:width_type=o:w=1.0:g=4.5,"
            "equalizer=f=260:width_type=o:w=1.2:g=2.5,"
            "equalizer=f=4500:width_type=o:w=1.5:g=-3.0,"
            "aecho=0.85:0.7:25:0.12,"
            "acompressor=threshold=-16dB:ratio=2.5:attack=10:release=100,"
            "loudnorm=I=-16:TP=-1.5:LRA=9"
        )

    subprocess.run([
        ffmpeg_bin(), "-y", "-nostdin", "-i", str(in_wav),
        "-af", audio_filter,
        "-ar", "44100", "-ac", "2",
        str(out_wav)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, check=True)

async def generate_edge_tts(text: str, voice: str, out_wav: Path, rate: str = "-6%", pitch: str = "-2Hz"):
    temp_mp3 = out_wav.with_suffix(".temp.mp3")
    try:
        import edge_tts
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        await communicate.save(str(temp_mp3))
        subprocess.run([
            ffmpeg_bin(), "-y", "-nostdin", "-i", str(temp_mp3),
            "-ac", "2", "-ar", "44100", str(out_wav)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, check=True)
        if temp_mp3.exists():
            temp_mp3.unlink()
        return True
    except Exception:
        return False

def generate_voices(render_cfg_path: str, project_root: Path):
    cache = project_root / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    
    cfg = json.loads(Path(render_cfg_path).read_text(encoding="utf-8"))
    verse = cfg.get("verse", {})
    
    sanskrit_txt = verse.get("sanskrit", "").replace("\\n", " ").strip()
    meaning_txt = verse.get("meaning", "").strip()
    insight_txt = verse.get("insight", "").strip()
    clean_narration = f"{meaning_txt} ... ... {insight_txt}"

    sans_raw_wav = cache / "sanskrit_raw.wav"
    sans_proc_wav = cache / "sanskrit_processed.wav"
    narr_raw_wav = cache / "narration_raw.wav"
    narr_proc_wav = cache / "narration_processed.wav"

    asyncio.run(generate_edge_tts(sanskrit_txt, UNIFIED_VOICE, sans_raw_wav, rate="-12%", pitch="-4Hz"))
    if sans_raw_wav.exists() and get_audio_duration_sec(sans_raw_wav) > 0.5:
        process_voice_dsp(sans_raw_wav, sans_proc_wav, is_chant=True)

    asyncio.run(generate_edge_tts(clean_narration, UNIFIED_VOICE, narr_raw_wav, rate="-6%", pitch="-2Hz"))
    if narr_raw_wav.exists() and get_audio_duration_sec(narr_raw_wav) > 1.0:
        process_voice_dsp(narr_raw_wav, narr_proc_wav, is_chant=False)

def mix_full_soundtrack(render_cfg_path: str, project_root: Path) -> tuple[Path, Path, str]:
    assets = project_root / "assets"
    music_dir = assets / "music"
    music_dir.mkdir(parents=True, exist_ok=True)
    cache = project_root / "cache"
    cache.mkdir(parents=True, exist_ok=True)

    generate_voices(render_cfg_path, project_root)

    valid_exts = {".mp3", ".wav", ".aac", ".flac", ".ogg"}
    music_tracks = [p for p in music_dir.iterdir() if p.suffix.lower() in valid_exts]
    selected_music = random.choice(music_tracks) if music_tracks else (cache / "fallback_bgm.wav")

    attribution_str = "Music composition arranged via FlowMusic AI."

    sans_wav = cache / "sanskrit_processed.wav"
    eng_wav = cache / "narration_processed.wav"

    sans_dur = get_audio_duration_sec(sans_wav)
    eng_dur = get_audio_duration_sec(eng_wav)

    music_intro_lead = 3.5
    sans_delay_sec = music_intro_lead
    inter_segment_pause = 2.0
    narr_delay_sec = sans_delay_sec + sans_dur + inter_segment_pause
    outro_buffer = 4.5

    total_timeline_sec = max(60.0, narr_delay_sec + eng_dur + outro_buffer)

    sans_delay_ms = int(sans_delay_sec * 1000)
    narr_delay_ms = int(narr_delay_sec * 1000)
    master_out = cache / "master_soundtrack.wav"

    author_str = "Venkatesh Marturu"
    studio_str = "BLACKLINES ART STUDIO"
    copyright_str = "© 2026 BLACKLINES ART STUDIO. All rights reserved."

    # Loop buffer capped at 5 minutes of samples (44100 * 300) to prevent OS memory exhaustion
    loop_samples = 44100 * 300
    filter_complex = (
        f"[0:a]adelay={sans_delay_ms}|{sans_delay_ms}[sans];"
        f"[1:a]adelay={narr_delay_ms}|{narr_delay_ms}[narr];"
        f"[2:a]aloop=loop=-1:size={loop_samples},atrim=0:{total_timeline_sec},"
        f"asetrate=44100*1.003,aresample=44100,volume=0.14,"
        f"afade=t=in:st=0:d=3.0,afade=t=out:st={total_timeline_sec-3.5}:d=3.5[bg];"
        f"[sans][narr][bg]amix=inputs=3:duration=longest:dropout_transition=3,"
        f"dynaudnorm=f=150:g=15:p=0.92[out]"
    )

    cmd = [
        ffmpeg_bin(), "-y", "-nostdin",
        "-i", str(sans_wav),
        "-i", str(eng_wav),
        "-i", str(selected_music),
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-ac", "2",
        "-ar", "44100",
        "-metadata", "title=Bhagavad Gita Sacred Soundscape & Chants",
        "-metadata", f"artist={author_str}",
        "-metadata", f"composer={author_str}",
        "-metadata", f"album_artist={author_str}",
        "-metadata", "album=Srimad Bhagavad Gita Studio Soundtracks",
        "-metadata", f"publisher={studio_str}",
        "-metadata", f"copyright={copyright_str}",
        "-metadata", "year=2026",
        "-metadata", "date=2026",
        "-metadata", "genre=Devotional Meditation / Sacred Indian Classical",
        "-metadata", "rating=5",
        "-metadata", "encoder=Pro Tools Ultimate HD (Windows)",
        str(master_out)
    ]

    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    return master_out, selected_music, attribution_str
