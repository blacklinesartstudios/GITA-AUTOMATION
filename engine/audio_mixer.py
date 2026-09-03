import os
import sys
import json
import asyncio
import subprocess
from pathlib import Path

def ffmpeg_bin():
    return "ffmpeg"

def get_audio_duration(file_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(file_path)
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(res.stdout.strip())
    except Exception:
        return 0.0

async def _synthesize_edge_tts(text: str, voice: str, rate: str, pitch: str, out_path: Path):
    import edge_tts
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(str(out_path))

def synthesize_voice(text: str, voice: str, rate: str, pitch: str, out_path: Path):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        asyncio.run(_synthesize_edge_tts(text, voice, rate, pitch, out_path))
    except Exception:
        cmd = [
            "edge-tts",
            "--voice", voice,
            f"--rate={rate}",
            f"--pitch={pitch}",
            "--text", text,
            f"--write-media={out_path}"
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

class AudioResult(str):
    """Compatible with code expecting a str, Path, or dict with metadata."""
    def __new__(cls, file_path, duration=65.0, sanskrit_dur=15.0, narration_dur=45.0):
        s = super().__new__(cls, str(file_path))
        s.path = Path(file_path)
        s.duration = float(duration)
        s.total_duration = float(duration)
        s.sanskrit_duration = float(sanskrit_dur)
        s.narration_duration = float(narration_dur)
        s._dict = {
            "audio_path": str(file_path),
            "path": str(file_path),
            "duration": float(duration),
            "total_duration": float(duration),
            "sanskrit_duration": float(sanskrit_dur),
            "narration_duration": float(narration_dur)
        }
        return s

    def __getitem__(self, item):
        if isinstance(item, int):
            return super().__getitem__(item)
        return self._dict.get(item, getattr(self, item, None))

    def get(self, key, default=None):
        return self._dict.get(key, default)

    def __fspath__(self):
        return str(self.path)

def mix_full_soundtrack(*args, **kwargs):
    cache_dir = Path("cache")
    cache_dir.mkdir(parents=True, exist_ok=True)

    if len(args) >= 4:
        sanskrit_path = Path(args[0])
        narration_path = Path(args[1])
        bgm_path = Path(args[2]) if args[2] and Path(args[2]).exists() else None
        output_path = Path(args[3])
    else:
        first_arg = args[0] if len(args) > 0 else kwargs.get("verse", {})
        
        verse = {}
        if isinstance(first_arg, dict):
            verse = first_arg.get("verse", first_arg)
        elif hasattr(first_arg, "verse"):
            verse = getattr(first_arg, "verse")

        sanskrit_text = verse.get("sanskrit", "धर्मक्षेत्रे कुरुक्षेत्रे समवेता युयुत्सवः")
        meaning_text = verse.get("meaning", "")
        insight_text = verse.get("insight", "")
        narration_text = f"{meaning_text} {insight_text}".strip()

        sanskrit_voice = "hi-IN-MadhurNeural"
        narration_voice = "en-US-ChristopherNeural"
        s_rate, s_pitch = "-15%", "-3Hz"
        n_rate, n_pitch = "-14%", "-2Hz"

        cfg_path = Path("config.json")
        if cfg_path.exists():
            try:
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                s_prof = cfg.get("audio", {}).get("sanskrit_audio_profile", {})
                n_prof = cfg.get("audio", {}).get("narration_audio_profile", {})
                sanskrit_voice = s_prof.get("voice_id", sanskrit_voice)
                s_rate = s_prof.get("rate", s_rate)
                s_pitch = s_prof.get("pitch", s_pitch)
                narration_voice = n_prof.get("voice_id", narration_voice)
                n_rate = n_prof.get("rate", n_rate)
                n_pitch = n_prof.get("pitch", n_pitch)
            except Exception:
                pass

        sanskrit_path = cache_dir / "sanskrit_speech.mp3"
        narration_path = cache_dir / "narration_speech.mp3"
        output_path = cache_dir / "master_audio.wav"

        print("  [AUDIO] Synthesizing sacred Sanskrit chant (Madhur Neural)...")
        synthesize_voice(sanskrit_text, sanskrit_voice, s_rate, s_pitch, sanskrit_path)

        print("  [AUDIO] Synthesizing philosophical narration (Christopher Neural)...")
        synthesize_voice(narration_text, narration_voice, n_rate, n_pitch, narration_path)

        bgm_path = None
        for candidate_dir in [Path("assets/music"), Path("assets"), Path("music")]:
            if candidate_dir.exists():
                audio_files = list(candidate_dir.glob("*.mp3")) + list(candidate_dir.glob("*.wav"))
                if audio_files:
                    bgm_path = audio_files[0]
                    break

    sanskrit_dur = get_audio_duration(sanskrit_path)
    narration_dur = get_audio_duration(narration_path)

    narration_delay_ms = int((sanskrit_dur + 1.2) * 1000)
    speech_total = (narration_delay_ms / 1000.0) + narration_dur
    total_duration = max(speech_total + 4.0, 64.0)

    fade_out_start = max(0.0, total_duration - 3.0)

    inputs = ["-i", str(sanskrit_path), "-i", str(narration_path)]
    if bgm_path and bgm_path.exists():
        inputs += ["-stream_loop", "-1", "-i", str(bgm_path)]
        filter_complex = (
            f"[0:a]volume=1.0,apad=whole_dur={total_duration}[sanskrit];"
            f"[1:a]volume=1.1,adelay={narration_delay_ms}|{narration_delay_ms},"
            f"apad=whole_dur={total_duration}[narration];"
            f"[sanskrit][narration]amix=inputs=2:dropout_transition=0[voice];"
            f"[2:a]volume=0.20,atrim=0:{total_duration},"
            f"afade=t=in:st=0:d=2.0,afade=t=out:st={fade_out_start}:d=3.0[bgm];"
            f"[voice][bgm]amix=inputs=2:dropout_transition=0,"
            f"loudnorm=I=-14.0:TP=-1.5:LRA=11[out]"
        )
    else:
        filter_complex = (
            f"[0:a]volume=1.0,apad=whole_dur={total_duration}[sanskrit];"
            f"[1:a]volume=1.1,adelay={narration_delay_ms}|{narration_delay_ms},"
            f"apad=whole_dur={total_duration}[narration];"
            f"[sanskrit][narration]amix=inputs=2:dropout_transition=0,"
            f"loudnorm=I=-14.0:TP=-1.5:LRA=11[out]"
        )

    cmd = [
        ffmpeg_bin(), "-y", "-nostdin",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-t", str(total_duration),
        "-c:a", "pcm_s16le",
        str(output_path)
    ]

    subprocess.run(cmd, check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"  ✓ Studio soundtrack ready: {output_path.name} ({total_duration:.1f}s)")

    return AudioResult(output_path, duration=total_duration, sanskrit_dur=sanskrit_dur, narration_dur=narration_dur)

mix_soundtrack = mix_full_soundtrack
mix_audio = mix_full_soundtrack
