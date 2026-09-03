def extract_audio_profile(audio_path: Path, num_frames: int = 1953) -> list:
    """Safely extracts RMS waveform curve without NoneType crashes."""
    import wave
    import numpy as np

    p = Path(audio_path)
    if not p.exists():
        for candidate in [p.parent / "master_soundtrack.wav", p.parent / "master_audio.wav"]:
            if candidate.exists():
                p = candidate
                break

    if not p.exists():
        return [0.15] * num_frames

    try:
        with wave.open(str(p), "rb") as wav_file:
            n_channels = wav_file.getnchannels()
            sampwidth = wav_file.getsampwidth()
            n_frames = wav_file.getnframes()
            
            if n_frames <= 0 or sampwidth not in (1, 2, 4):
                return [0.15] * num_frames

            raw_bytes = wav_file.readframes(n_frames)
            if not raw_bytes:
                return [0.15] * num_frames

            dtype = np.int16 if sampwidth == 2 else (np.int32 if sampwidth == 4 else np.uint8)
            audio_data = np.frombuffer(raw_bytes, dtype=dtype)

            if n_channels > 1:
                audio_data = audio_data[::n_channels]

            step = max(1, len(audio_data) // max(1, num_frames))
            profile = []
            for i in range(num_frames):
                chunk = audio_data[i * step : (i + 1) * step]
                if len(chunk) > 0:
                    rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
                    profile.append(float(min(1.0, rms / 14000.0)))
                else:
                    profile.append(0.1)
            return profile
    except Exception:
        return [0.15] * num_frames


def mux(video, audio, out, chapter=1, verse=1):
    """Muxes audio and video without terminal blocking."""
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    author_str = "Venkatesh Marturu"
    studio_str = "BLACKLINES ART STUDIO"
    cmd = [
        shutil.which("ffmpeg") or "ffmpeg", "-y",
        "-nostdin",
        "-i", str(video),
        "-i", str(audio),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "256k",
        "-shortest",
        "-metadata", f"title=Srimad Bhagavad Gita - Chapter {chapter} Verse {verse}",
        "-metadata", f"artist={author_str}",
        "-metadata", f"album_artist={author_str}",
        "-metadata", f"publisher={studio_str}",
        str(out)
    ]
    subprocess.run(
        cmd,
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
