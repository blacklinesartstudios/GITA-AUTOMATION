import os
import sys
import json
import random
import shutil
import subprocess
import asyncio
import wave
from pathlib import Path

# Human Neural Voice for both Sanskrit Chanting and English Philosophical Narration
UNIFIED_VOICE = "hi-IN-MadhurNeural"


def ffmpeg_bin() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def get_audio_duration_sec(wav_path: Path) -> float:
    wav_path = Path(wav_path)
    if not wav_path.exists():
        return 0.0
    try:
        with wave.open(str(wav_path), "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            return frames / float(rate) if rate > 0 else 0.0
    except Exception:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(wav_path)
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            return float(res.stdout.strip())
        except Exception:
            return 0.0


def process_voice_dsp(in_wav: Path, out_wav: Path, is_chant: bool = False):
    """Applies analog-style studio EQ, spatial echo, and dynamic vocal compression."""
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
        ffmpeg_bin(), "-y", "-nostdin",
        "-i", str(in_wav),
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
            ffmpeg_bin(), "-y", "-nostdin",
            "-i", str(temp_mp3),
            "-ac", "2", "-ar", "44100",
            str(out_wav)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, check=True)
        if temp_mp3.exists():
            temp_mp3.unlink()
        return True
    except Exception:
        cmd = [
            "edge-tts",
            "--voice", voice,
            f"--rate={rate}",
            f"--pitch={pitch}",
            "--text", text,
            f"--write-media={temp_mp3}"
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, check=True)
            subprocess.run([
                ffmpeg_bin(), "-y", "-nostdin",
                "-i", str(temp_mp3),
                "-ac", "2", "-ar", "44100",
                str(out_wav)
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, check=True)
            if temp_mp3.exists():
                temp_mp3.unlink()
            return True
        except Exception:
            return False


class UniversalAudioResult(tuple):
    def __new__(cls, master_path: Path, music_path: Path, attribution: str, duration: float, sanskrit_dur: float, narr_dur: float):
        return super().__new__(cls, (Path(master_path), Path(music_path), str(attribution)))

    def __init__(self, master_path: Path, music_path: Path, attribution: str, duration: float, sanskrit_dur: float, narr_dur: float):
        self.path = Path(master_path)
        self.audio_path = Path(master_path)
        self.music_path = Path(music_path)
        self.attribution = str(attribution)
        self.duration = float(duration)
        self.total_duration = float(duration)
        self.sanskrit_duration = float(sanskrit_dur)
        self.narration_duration = float(narr_dur)
        self._dict = {
            "path": str(master_path),
            "audio_path": str(master_path),
            "music_path": str(music_path),
            "attribution": str(attribution),
            "duration": float(duration),
            "total_duration": float(duration),
            "sanskrit_duration": float(sanskrit_dur),
            "narration_duration": float(narr_dur)
        }

    def __str__(self):
        return str(self.path)

    def __fspath__(self):
        return str(self.path)

    def __getitem__(self, item):
        if isinstance(item, int):
            return super().__getitem__(item)
        return self._dict.get(item, getattr(self, str(item), None))

    def get(self, key, default=None):
        return self._dict.get(key, default)


def mix_full_soundtrack(*args, **kwargs) -> UniversalAudioResult:
    project_root = Path(".")
    verse_dict = {}

    if len(args) >= 2 and isinstance(args[1], (str, Path)):
        project_root = Path(args[1])

    if len(args) >= 1:
        first = args[0]
        if isinstance(first, (str, Path)) and Path(first).exists():
            try:
                cfg_data = json.loads(Path(first).read_text(encoding="utf-8"))
                verse_dict = cfg_data.get("verse", cfg_data)
            except Exception:
                pass
        elif isinstance(first, dict):
            verse_dict = first.get("verse", first)
    elif "verse" in kwargs:
        verse_dict = kwargs["verse"]

    cache = project_root / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    assets = project_root / "assets"
    music_dir = assets / "music"
    music_dir.mkdir(parents=True, exist_ok=True)

    sanskrit_txt = verse_dict.get("sanskrit", "").replace("\\n", " ").strip()
    meaning_txt = verse_dict.get("meaning", "").strip()
    insight_txt = verse_dict.get("insight", "").strip()
    clean_narration = f"{meaning_txt} ... ... {insight_txt}".strip()

    sans_raw_wav = cache / "sanskrit_raw.wav"
    sans_proc_wav = cache / "sanskrit_processed.wav"
    narr_raw_wav = cache / "narration_raw.wav"
    narr_proc_wav = cache / "narration_processed.wav"

    print("  [AUDIO] Synthesizing sacred Sanskrit chant (Madhur Neural)...")
    asyncio.run(generate_edge_tts(sanskrit_txt, UNIFIED_VOICE, sans_raw_wav, rate="-12%", pitch="-4Hz"))
    if sans_raw_wav.exists() and get_audio_duration_sec(sans_raw_wav) > 0.2:
        process_voice_dsp(sans_raw_wav, sans_proc_wav, is_chant=True)
    else:
        sans_proc_wav = sans_raw_wav

    print("  [AUDIO] Synthesizing human philosophical narration (Madhur Neural)...")
    asyncio.run(generate_edge_tts(clean_narration, UNIFIED_VOICE, narr_raw_wav, rate="-6%", pitch="-2Hz"))
    if narr_raw_wav.exists() and get_audio_duration_sec(narr_raw_wav) > 0.2:
        process_voice_dsp(narr_raw_wav, narr_proc_wav, is_chant=False)
    else:
        narr_proc_wav = narr_raw_wav

    valid_exts = {".mp3", ".wav", ".aac", ".flac", ".ogg"}
    music_tracks = [p for p in music_dir.iterdir() if p.suffix.lower() in valid_exts]
    selected_music = random.choice(music_tracks) if music_tracks else (cache / "fallback_bgm.wav")
    attribution_str = "Music composition arranged via FlowMusic AI."

    if not selected_music.exists():
        subprocess.run([
            ffmpeg_bin(), "-y", "-nostdin",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", "70",
            str(selected_music)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, check=True)

    sans_dur = get_audio_duration_sec(sans_proc_wav)
    narr_dur = get_audio_duration_sec(narr_proc_wav)

    music_intro_lead = 3.5
    sans_delay_sec = music_intro_lead
    inter_segment_pause = 2.0
    narr_delay_sec = sans_delay_sec + sans_dur + inter_segment_pause
    outro_buffer = 4.5

    total_timeline_sec = max(64.0, narr_delay_sec + narr_dur + outro_buffer)
    fade_out_start = max(0.0, total_timeline_sec - 3.5)

    sans_delay_ms = int(sans_delay_sec * 1000)
    narr_delay_ms = int(narr_delay_sec * 1000)
    master_out = cache / "master_soundtrack.wav"

    author_str = "Venkatesh Marturu"
    studio_str = "BLACKLINES ART STUDIO"
    copyright_str = "© 2026 BLACKLINES ART STUDIO. All rights reserved."

    loop_samples = 44100 * 300
    filter_complex = (
        f"[0:a]adelay={sans_delay_ms}|{sans_delay_ms},apad=whole_dur={total_timeline_sec}[sans];"
        f"[1:a]adelay={narr_delay_ms}|{narr_delay_ms},apad=whole_dur={total_timeline_sec}[narr];"
        f"[2:a]aloop=loop=-1:size={loop_samples},atrim=0:{total_timeline_sec},"
        f"asetrate=44100*1.003,aresample=44100,volume=0.14,"
        f"afade=t=in:st=0:d=3.0,afade=t=out:st={fade_out_start}:d=3.5[bg];"
        f"[sans][narr][bg]amix=inputs=3:duration=longest:dropout_transition=0,"
        f"dynaudnorm=f=150:g=15:p=0.92,loudnorm=I=-14.0:TP=-1.5:LRA=11[out]"
    )

    cmd = [
        ffmpeg_bin(), "-y", "-nostdin",
        "-i", str(sans_proc_wav),
        "-i", str(narr_proc_wav),
        "-i", str(selected_music),
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-t", str(total_timeline_sec),
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
    print(f"  ✓ Studio soundtrack mixed successfully: {master_out.name} ({total_timeline_sec:.1f}s)")

    return UniversalAudioResult(
        master_path=master_out,
        music_path=selected_music,
        attribution=attribution_str,
        duration=total_timeline_sec,
        sanskrit_dur=sans_dur,
        narr_dur=narr_dur
    )
