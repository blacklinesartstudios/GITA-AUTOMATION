import subprocess
from pathlib import Path

def get_audio_duration(audio_path: Path) -> float:
    """
    Extracts the exact natural duration of the voiceover audio file using ffprobe,
    ensuring zero artificial padding or fixed time limits.
    """
    audio_path = Path(audio_path).resolve()
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path)
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        duration = float(result.stdout.strip())
        return duration
    except ValueError:
        return 60.0

def build_dynamic_video_sequence(
    video_frames_dir: Path,
    voiceover_audio_path: Path,
    background_music_path: Path,
    output_video_path: Path,
    fps: int = 30
):
    """
    Assembles the final video matching the natural length of the voiceover audio,
    triggering a synchronized sequential fade-out for visuals and music at the end.
    """
    video_frames_dir = Path(video_frames_dir).resolve()
    voiceover_audio_path = Path(voiceover_audio_path).resolve()
    background_music_path = Path(background_music_path).resolve()
    output_video_path = Path(output_video_path).resolve()

    audio_duration = get_audio_duration(voiceover_audio_path)
    # Add a clean 1.5-second trailing buffer for the final cinematic fade out
    total_duration = audio_duration + 1.5

    print(f"  [PACING] Natural voiceover duration detected: {audio_duration:.2f}s")
    print(f"  [PACING] Total video timeline set to: {total_duration:.2f}s (Audio-synced)")

    fade_start = audio_duration
    fade_duration = 1.5

    # FFmpeg complex filter for smooth visual fade-out and background audio ducking/fade
    filter_complex = (
        f"[0:v]fade=t=out:st={fade_start}:d={fade_duration}[v_out];"
        f"[1:a]volume=1.0[voice];"
        f"[2:a]volume=0.2,afade=t=out:st={fade_start}:d={fade_duration}[music];"
        f"[voice][music]amix=inputs=2:duration=first[a_out]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-pattern_type", "glob",
        "-i", f"{video_frames_dir}/frame_%04d.png",
        "-i", str(voiceover_audio_path),
        "-i", str(background_music_path),
        "-filter_complex", filter_complex,
        "-map", "[v_out]",
        "-map", "[a_out]",
        "-t", str(total_duration),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        str(output_video_path)
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        print(f"  [ERROR] Video assembly failed: {result.stderr.decode()}")
        raise RuntimeError("FFmpeg video assembly failed.")

    print(f"  ✓ Master Video Assembled Successfully: {output_video_path.name}")
    return output_video_path
