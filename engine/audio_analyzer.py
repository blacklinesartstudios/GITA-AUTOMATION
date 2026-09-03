from pathlib import Path
import shutil
import subprocess
import numpy as np

def ffmpeg_bin():
    return shutil.which("ffmpeg") or r"C:\ffmpeg\bin\ffmpeg.exe"

def extract_music_wave_average_profile(audio_path: Path, fps: int = 30, smoothing_window_sec: float = 0.5) -> np.ndarray:
    """
    Decodes audio to mono PCM via FFmpeg and extracts a moving-average RMS envelope.
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        return np.ones(3000, dtype=np.float32)

    try:
        sample_rate = 16000
        cmd = [
            ffmpeg_bin(), "-y", "-i", str(audio_path),
            "-f", "s16le", "-ac", "1", "-ar", str(sample_rate), "-"
        ]
        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        raw_bytes = proc.stdout

        samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if len(samples) == 0:
            return np.ones(3000, dtype=np.float32)

        samples_per_frame = int(sample_rate / fps)
        total_frames = max(1, int(len(samples) / samples_per_frame))

        rms_profile = np.zeros(total_frames, dtype=np.float32)
        for i in range(total_frames):
            st = i * samples_per_frame
            en = min(st + samples_per_frame, len(samples))
            chunk = samples[st:en]
            if len(chunk) > 0:
                rms_profile[i] = np.sqrt(np.mean(chunk**2))

        win_frames = max(3, int(fps * smoothing_window_sec))
        kernel = np.ones(win_frames, dtype=np.float32) / float(win_frames)
        smoothed = np.convolve(rms_profile, kernel, mode='same')

        min_e = np.percentile(smoothed, 5)
        max_e = np.percentile(smoothed, 95)

        if max_e > min_e:
            norm = (smoothed - min_e) / (max_e - min_e)
            velocity = 0.8 + (0.45 * np.clip(norm, 0.0, 1.0))
        else:
            velocity = np.ones_like(smoothed)

        return velocity

    except Exception as e:
        print(f"  [AUDIO-ANALYZER] Fallback wave profile ({e})")
        return np.ones(3000, dtype=np.float32)

extract_audio_energy_profile = extract_music_wave_average_profile