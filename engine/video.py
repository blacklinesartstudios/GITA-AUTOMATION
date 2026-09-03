import os
import sys
import json
import math
import shutil
import subprocess
import urllib.request
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from engine.depth import make_depth

def ffmpeg_bin():
    return shutil.which("ffmpeg") or r"C:\ffmpeg\bin\ffmpeg.exe"

def get_audio_duration(audio_path: str) -> float:
    cmd = [
        ffmpeg_bin(), "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(res.stdout.strip())
    except Exception:
        return 60.0

def ensure_font_library(fonts_dir: Path):
    fonts_dir.mkdir(parents=True, exist_ok=True)
    
    font_urls = {
        "DejaVuSans-Bold.ttf": "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans-Bold.ttf",
        "NotoSansDevanagari-Bold.ttf": "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Bold.ttf",
        "NotoSansTelugu-Bold.ttf": "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansTelugu/NotoSansTelugu-Bold.ttf",
        "NotoSansTamil-Bold.ttf": "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansTamil/NotoSansTamil-Bold.ttf",
        "NotoSansMalayalam-Bold.ttf": "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansMalayalam/NotoSansMalayalam-Bold.ttf",
        "NotoSansKannada-Bold.ttf": "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansKannada/NotoSansKannada-Bold.ttf",
    }
    
    for font_name, url in font_urls.items():
        dst = fonts_dir / font_name
        if not dst.exists() or dst.stat().st_size < 1000:
            try:
                urllib.request.urlretrieve(url, str(dst))
            except Exception:
                pass

def get_font(fonts_dir: Path, font_name: str, size: int):
    target = fonts_dir / font_name
    if target.exists():
        try:
            return ImageFont.truetype(str(target), size)
        except Exception:
            pass

    system_candidates = [
        Path(f"/usr/share/fonts/truetype/dejavu/{font_name}"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/freefont/FreeSansBold.ttf")
    ]
    for sys_font in system_candidates:
        if sys_font.exists():
            try:
                return ImageFont.truetype(str(sys_font), size)
            except Exception:
                pass

    for fb in ["DejaVuSans-Bold.ttf", "NotoSansDevanagari-Bold.ttf"]:
        alt = fonts_dir / fb
        if alt.exists():
            try:
                return ImageFont.truetype(str(alt), size)
            except Exception:
                pass
    return ImageFont.load_default()

def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int):
    lines = []
    for paragraph in text.split("\n"):
        words = paragraph.split(" ")
        curr_line = ""
        for word in words:
            test_line = f"{curr_line} {word}".strip()
            bbox = draw.textbbox((0, 0), test_line, font=font)
            w = bbox[2] - bbox[0]
            if w <= max_width:
                curr_line = test_line
            else:
                if curr_line:
                    lines.append(curr_line)
                curr_line = word
        if curr_line:
            lines.append(curr_line)
    return lines

def build_hud_card(w: int, h: int, cfg: dict, fonts_dir: Path) -> np.ndarray:
    ensure_font_library(fonts_dir)
    
    verse_info = cfg.get("verse", {})
    lang_info = cfg.get("language", {"code": "en", "name": "English"})
    
    ch = verse_info.get("chapter", 1)
    vs = verse_info.get("verse_number", 1)
    sanskrit_txt = verse_info.get("sanskrit", "")
    meaning_txt = verse_info.get("meaning", "")
    insight_txt = verse_info.get("insight", "")
    lang_name = lang_info.get("name", "English")

    img = Image.new("RGBA", (w, h), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    gold_main = (212, 175, 55, 240)
    gold_dim = (140, 110, 30, 180)
    draw.rectangle([40, 40, w - 40, h - 40], outline=gold_dim, width=2)
    draw.rectangle([54, 54, w - 54, h - 54], outline=gold_main, width=4)

    for cx, cy in [(54, 54), (w - 54, 54), (54, h - 54), (w - 54, h - 54)]:
        draw.polygon([(cx, cy - 12), (cx + 12, cy), (cx, cy + 12), (cx - 12, cy)], fill=gold_main)

    font_sanskrit_title = get_font(fonts_dir, "NotoSansDevanagari-Bold.ttf", 40)
    font_sanskrit_sloka = get_font(fonts_dir, "NotoSansDevanagari-Bold.ttf", 38)
    font_sanskrit_tag = get_font(fonts_dir, "NotoSansDevanagari-Bold.ttf", 26)

    regional_font_map = {
        "te": "NotoSansTelugu-Bold.ttf",
        "ta": "NotoSansTamil-Bold.ttf",
        "ml": "NotoSansMalayalam-Bold.ttf",
        "kn": "NotoSansKannada-Bold.ttf",
        "hi": "NotoSansDevanagari-Bold.ttf",
    }
    meaning_font_name = regional_font_map.get(lang_info.get("code", "en"), "DejaVuSans-Bold.ttf")
    font_latin_header = get_font(fonts_dir, "DejaVuSans-Bold.ttf", 26)
    font_body = get_font(fonts_dir, meaning_font_name, 32)
    font_latin_tag = get_font(fonts_dir, "DejaVuSans-Bold.ttf", 24)
    font_latin_foot = get_font(fonts_dir, "DejaVuSans-Bold.ttf", 20)

    draw.rounded_rectangle([180, 120, w - 180, 245], radius=14, fill=(18, 20, 32, 220), outline=gold_main, width=2)
    draw.text((w // 2, 162), "॥ श्रीमद्भगवद्गीता ॥", font=font_sanskrit_title, fill=gold_main, anchor="mm")
    draw.text((w // 2, 212), f"{lang_name.upper()} • CHAPTER {ch}, VERSE {vs}", font=font_latin_header, fill=(245, 245, 245, 255), anchor="mm")

    draw.rounded_rectangle([80, 340, w - 80, 820], radius=16, fill=(14, 16, 26, 225), outline=gold_dim, width=2)
    draw.text((w // 2, 385), "॥ श्लोक ॥", font=font_sanskrit_tag, fill=gold_main, anchor="mm")

    sloka_lines = wrap_text(draw, sanskrit_txt, font_sanskrit_sloka, max_width=840)
    y_sloka = 530 - (len(sloka_lines) * 30)
    for line in sloka_lines:
        draw.text((w // 2, y_sloka), line, font=font_sanskrit_sloka, fill=(255, 255, 255, 255), anchor="mm")
        y_sloka += 62

    draw.rounded_rectangle([80, 890, w - 80, 1680], radius=16, fill=(12, 14, 24, 230), outline=gold_main, width=2)
    draw.text((w // 2, 940), f"MEANING & WISDOM ({lang_name.upper()})", font=font_latin_tag, fill=gold_main, anchor="mm")

    meaning_lines = wrap_text(draw, f'"{meaning_txt}"', font_body, max_width=840)
    y_text = 1010
    for line in meaning_lines[:7]:
        draw.text((w // 2, y_text), line, font=font_body, fill=(235, 235, 235, 255), anchor="mm")
        y_text += 48

    draw.line([240, y_text + 35, w - 240, y_text + 35], fill=gold_dim, width=1)
    draw.text((w // 2, y_text + 75), "PRACTICAL TAKEAWAY", font=font_latin_tag, fill=gold_main, anchor="mm")

    insight_lines = wrap_text(draw, insight_txt, font_body, max_width=840)
    y_ins = y_text + 125
    for line in insight_lines[:5]:
        draw.text((w // 2, y_ins), line, font=font_body, fill=(255, 220, 130, 255), anchor="mm")
        y_ins += 46

    draw.text((w // 2, 1780), "BLACKLINES ART STUDIO • TIMELESS WISDOM", font=font_latin_foot, fill=(180, 180, 180, 230), anchor="mm")

    return cv2.cvtColor(np.array(img), cv2.COLOR_RGBA2BGRA)

def render_3d_parallax_frame(
    img_bgr: np.ndarray,
    depth_gray: np.ndarray,
    progress: float,
    pan_amp_x: float = 24.0,
    pan_amp_y: float = 14.0,
    zoom_max: float = 1.06
) -> np.ndarray:
    h, w = img_bgr.shape[:2]
    norm_depth = depth_gray.astype(np.float32) / 255.0

    current_zoom = 1.0 + (zoom_max - 1.0) * progress
    shift_x = math.sin(progress * math.pi) * pan_amp_x
    shift_y = math.cos(progress * math.pi * 0.5) * pan_amp_y

    x = np.linspace(0, w - 1, w, dtype=np.float32)
    y = np.linspace(0, h - 1, h, dtype=np.float32)
    base_x, base_y = np.meshgrid(x, y)

    center_x = (w - 1) * 0.5
    center_y = (h - 1) * 0.5
    zx = (base_x - center_x) / current_zoom + center_x
    zy = (base_y - center_y) / current_zoom + center_y

    map_x = zx + (shift_x * (norm_depth - 0.5))
    map_y = zy + (shift_y * (norm_depth - 0.5))

    return cv2.remap(img_bgr, map_x.astype(np.float32), map_y.astype(np.float32), interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

def render_master_video(
    images: list[Path],
    out: str,
    master_audio_path: str,
    bg_music_path: str,
    w: int,
    h: int,
    fps: int,
    cfg_path: str,
    sans_dur: float,
    eng_dur: float,
    fast_mode: bool = False
):
    project_root = Path(cfg_path).resolve().parent.parent
    cache_dir = project_root / "cache"
    depth_dir = cache_dir / "depths"
    depth_dir.mkdir(parents=True, exist_ok=True)
    fonts_dir = project_root / "assets" / "fonts"

    cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
    total_sec = get_audio_duration(master_audio_path)
    total_frames = int(total_sec * fps)

    print(f"  [RENDER] Synthesizing ONNX 3D Depth Maps for {len(images)} scenes...")
    preloaded = []
    for img_path in images:
        raw_bgr = cv2.imread(str(img_path))
        if raw_bgr is None:
            continue
        raw_bgr = cv2.resize(raw_bgr, (w, h), interpolation=cv2.INTER_CUBIC)

        depth_file = depth_dir / f"{img_path.stem}_depth.png"
        if not depth_file.exists():
            make_depth(img_path, depth_file)
        
        depth_raw = cv2.imread(str(depth_file), cv2.IMREAD_GRAYSCALE)
        if depth_raw is None:
            depth_raw = np.full((h, w), 128, dtype=np.uint8)
        else:
            depth_raw = cv2.resize(depth_raw, (w, h), interpolation=cv2.INTER_CUBIC)

        preloaded.append((raw_bgr, depth_raw))

    if not preloaded:
        raise RuntimeError("No valid visual scenes could be loaded.")

    hud_card_bgra = build_hud_card(w, h, cfg, fonts_dir)
    card_rgb = hud_card_bgra[:, :, :3].astype(np.float32)
    card_alpha = (hud_card_bgra[:, :, 3].astype(np.float32) / 255.0)[:, :, None]

    cmd = [
        ffmpeg_bin(), "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{w}x{h}", "-pix_fmt", "bgr24", "-r", str(fps),
        "-i", "-",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", str(out)
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    sec_per_cut = total_sec / len(preloaded)
    frames_per_cut = int(sec_per_cut * fps)
    fade_out_start_frame = max(0, total_frames - int(2.5 * fps))

    print(f"  [RENDER] Streaming {total_frames} 3D parallax frames with overlay...")
    frame_idx = 0
    try:
        while frame_idx < total_frames:
            scene_idx = min(int(frame_idx / frames_per_cut), len(preloaded) - 1)
            scene_bgr, scene_depth = preloaded[scene_idx]
            progress = (frame_idx % frames_per_cut) / float(frames_per_cut)

            bg_3d = render_3d_parallax_frame(scene_bgr, scene_depth, progress)
            composed = (bg_3d.astype(np.float32) * (1.0 - card_alpha) + card_rgb * card_alpha).astype(np.uint8)

            if frame_idx >= fade_out_start_frame:
                decay = 1.0 - ((frame_idx - fade_out_start_frame) / float(total_frames - fade_out_start_frame))
                composed = (composed.astype(np.float32) * decay).astype(np.uint8)

            proc.stdin.write(composed.tobytes())
            frame_idx += 1
    finally:
        if proc.stdin:
            proc.stdin.close()
        proc.wait()

    print(f"  ✓ 3D Master Parallax Video Rendered: {Path(out).name}")

def mux(visuals_path: Path, audio_path: Path, output_path: Path, chapter: int, verse: int):
    author_str = "Venkatesh Marturu"
    studio_str = "BLACKLINES ART STUDIO"
    cmd = [
        ffmpeg_bin(), "-y",
        "-i", str(visuals_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-metadata", f"title=Bhagavad Gita - Chapter {chapter} Verse {verse}",
        "-metadata", f"artist={author_str}",
        "-metadata", f"album_artist={author_str}",
        "-metadata", f"publisher={studio_str}",
        "-metadata", "copyright=© 2026 BLACKLINES ART STUDIO",
        str(output_path)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
