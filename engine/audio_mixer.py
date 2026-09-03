import os
import subprocess
from pathlib import Path

def ffmpeg_bin():
    return "ffmpeg"

def get_audio_duration(file_path: Path) -> float:
    """Returns duration in seconds using ffprobe."""
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

def mix_full_soundtrack(
    sanskrit_audio: Path,
    narration_audio: Path,
    bgm_audio: Path,
    output_path: Path,
    target_lufs: float = -14.0,
    **kwargs
) -> Path:
    """
    Main entry point expected by pipeline.py.
    Mixes Sanskrit chant, English narration, and sacred background drone/music
    with ducking and broadcast volume leveling.
    """
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sanskrit_path = Path(sanskrit_audio).resolve()
    narration_path = Path(narration_audio).resolve()
    bgm_path = Path(bgm_audio).resolve() if bgm_audio and Path(bgm_audio).exists() else None

    # Determine speech durations
    sanskrit_dur = get_audio_duration(sanskrit_path)
    narration_dur = get_audio_duration(narration_path)

    # Delay narration until after Sanskrit verse + 1.2s breathing gap
    narration_delay_ms = int((sanskrit_dur + 1.2) * 1000)

    # Calculate total sequence length (ensuring > 60s for YouTube Shorts requirements)
    speech_total = (narration_delay_ms / 1000.0) + narration_dur
    total_duration = max(speech_total + 4.0, 64.0)

    # Build FFmpeg filter chain
    inputs = ["-i", str(sanskrit_path), "-i", str(narration_path)]
    
    if bgm_path:
        inputs += ["-stream_loop", "-1", "-i", str(bgm_path)]
        filter_complex = (
            f"[0:a]volume=1.0,apad=whole_dur={total_duration}[sanskrit];"
            f"[1:a]volume=1.1,adelay={narration_delay_ms}|{narration_delay_ms},"
            f"apad=whole_dur={total_duration}[narration];"
            f"[sanskrit][narration]amix=inputs=2:dropout_transition=0:weights=1 1[voice];"
            f"[2:a]volume=0.22,aloop=loop=-1:size=2e+09,atrim=0:{total_duration},"
            f"afade=t=in:st=0:d=2.0,afade=t=out:st={total_duration - 3.0}:d=3.0[bgm];"
            f"[voice][bgm]amix=inputs=2:dropout_transition=0:weights=1 1,"
            f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11[out]"
        )
    else:
        filter_complex = (
            f"[0:a]volume=1.0,apad=whole_dur={total_duration}[sanskrit];"
            f"[1:a]volume=1.1,adelay={narration_delay_ms}|{narration_delay_ms},"
            f"apad=whole_dur={total_duration}[narration];"
            f"[sanskrit][narration]amix=inputs=2:dropout_transition=0:weights=1 1,"
            f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11[out]"
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

    subprocess.run(
        cmd,
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    print(f"  ✓ Full soundtrack mixed: {output_path.name} (Duration: {total_duration:.1f}s)")
    return output_path

# Alias in case other modules call it under different names
mix_soundtrack = mix_full_soundtrack
mix_audio = mix_full_soundtrack
