from pathlib import Path
import subprocess, shutil, wave, random

def ffmpeg_bin():
    return shutil.which("ffmpeg") or r"C:\ffmpeg\bin\ffmpeg.exe"

def get_audio_duration(wav_path):
    p = Path(wav_path)
    if not p.exists():
        return 0.0
    try:
        with wave.open(str(p), 'rb') as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        cmd = [ffmpeg_bin(), "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(p)]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            return float(res.stdout.strip())
        except Exception:
            return 45.0

def mix_master_audio(
    sanskrit_path: Path,
    narration_path: Path,
    bg_music_path: Path,
    output_path: Path
) -> dict:
    """
    Sequences voice tracks with accurate delays, adds dynamic pauses, and appends a randomized outro
    so every video exceeds 60s without matching previous video runtimes.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sans_dur = get_audio_duration(sanskrit_path)
    narr_dur = get_audio_duration(narration_path)

    intro_lead = 1.8         # Sacred chime intro before Sanskrit begins
    inter_card_pause = 1.4   # Rest between Sanskrit and English narration
    outro_tail = random.uniform(5.0, 9.5)  # Randomized tail avoids identical durations

    sanskrit_start = intro_lead
    sanskrit_end = sanskrit_start + sans_dur
    narration_start = sanskrit_end + inter_card_pause
    narration_end = narration_start + narr_dur

    raw_total = narration_end + outro_tail
    total_duration = max(63.5, raw_total)  # Enforce 1-minute+ floor

    sk_delay_ms = int(sanskrit_start * 1000)
    na_delay_ms = int(narration_start * 1000)
    fade_start = max(1.0, total_duration - 3.5)

    has_bg = bg_music_path and Path(bg_music_path).exists()

    if has_bg:
        filter_complex = (
            f"[0:a]volume=1.15,adelay={sk_delay_ms}|{sk_delay_ms}[sk];"
            f"[1:a]volume=1.05,adelay={na_delay_ms}|{na_delay_ms}[na];"
            f"[sk][na]amix=inputs=2:dropout_transition=0:weights=1 1[voice];"
            f"[2:a]volume=0.18,afade=t=out:st={fade_start:.2f}:d=3.0[bg];"
            f"[voice][bg]amix=inputs=2:duration=first:dropout_transition=0[outa]"
        )
        inputs = ["-i", str(sanskrit_path), "-i", str(narration_path), "-i", str(bg_music_path)]
    else:
        filter_complex = (
            f"[0:a]volume=1.15,adelay={sk_delay_ms}|{sk_delay_ms}[sk];"
            f"[1:a]volume=1.05,adelay={na_delay_ms}|{na_delay_ms}[na];"
            f"[sk][na]amix=inputs=2:dropout_transition=0:weights=1 1,afade=t=out:st={fade_start:.2f}:d=3.0[outa]"
        )
        inputs = ["-i", str(sanskrit_path), "-i", str(narration_path)]

    cmd = [
        ffmpeg_bin(), "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[outa]",
        "-c:a", "pcm_s16le",
        "-t", f"{total_duration:.2f}",
        str(output_path)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return {
        "output_path": output_path,
        "sanskrit_voice_start": sanskrit_start,
        "sanskrit_voice_end": sanskrit_end,
        "narration_voice_start": narration_start,
        "narration_voice_end": narration_end,
        "total_duration": total_duration,
        "sanskrit_duration": sans_dur,
        "narration_duration": narr_dur
    }
