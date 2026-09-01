import shutil
from pathlib import Path

def ffmpeg_path():
    return shutil.which("ffmpeg") or r"C:\ffmpeg\bin\ffmpeg.exe"

def run_preflight(root: Path, cfg: dict = None) -> tuple[bool, str]:
    assets = root / "assets"
    fonts_dir = assets / "fonts"
    images_dir = assets / "images"
    music_dir = assets / "music"
    voices_dir = assets / "voices"

    checks = []
    
    # 1. FFmpeg Validation
    ff = ffmpeg_path()
    ff_ok = Path(ff).exists() or shutil.which("ffmpeg") is not None
    checks.append((ff_ok, f"FFmpeg Binary: {ff}"))

    # 2. Segregated Directory Checks
    checks.append((assets.exists() and assets.is_dir(), f"Base Assets Folder: {assets}"))
    checks.append((fonts_dir.exists() and fonts_dir.is_dir(), f"Fonts Folder: {fonts_dir}"))
    checks.append((images_dir.exists() and images_dir.is_dir(), f"Images Folder: {images_dir}"))
    checks.append((music_dir.exists() and music_dir.is_dir(), f"Music Folder: {music_dir}"))
    checks.append((voices_dir.exists() and voices_dir.is_dir(), f"Voices Folder: {voices_dir}"))

    # 3. Asset Content Validation
    valid_img_exts = {".jpg", ".jpeg", ".png", ".webp"}
    images = [p for p in images_dir.iterdir() if p.suffix.lower() in valid_img_exts] if images_dir.exists() else []
    checks.append((len(images) > 0, f"Background Images Found: {len(images)}"))

    fonts = list(fonts_dir.glob("*.ttf")) if fonts_dir.exists() else []
    checks.append((len(fonts) > 0, f"Devanagari/Latin Fonts Found: {len(fonts)}"))

    valid_audio_exts = {".mp3", ".wav", ".aac", ".flac", ".ogg"}
    music = [p for p in music_dir.iterdir() if p.suffix.lower() in valid_audio_exts] if music_dir.exists() else []
    checks.append((len(music) > 0, f"Music Tracks Found: {len(music)}"))

    # 4. Google OAuth Secrets
    secrets = root / "client_secrets.json"
    checks.append((secrets.exists(), f"OAuth client_secrets.json: {secrets}"))

    lines = ["\n=== PREFLIGHT VERIFICATION ==="]
    all_ok = True
    for ok, msg in checks:
        status = "[OK]  " if ok else "[FAIL]"
        lines.append(f"{status} {msg}")
        if not ok:
            all_ok = False
            
    lines.append("==============================\n")
    report = "\n".join(lines)
    print(report)
    return all_ok, report