from pathlib import Path
import subprocess, shutil, math, os, random, sys, time, urllib.request, re
import cv2
import numpy as np
import json
import wave
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from engine.audio_analyzer import extract_music_wave_average_profile

try:
    import torch
except ImportError:
    torch = None

_MIDAS_MODEL = None
_MIDAS_TRANSFORMS = None
_TORCH_DEVICE = None

def get_midas_model(model_type="MiDaS_small"):
    global _MIDAS_MODEL, _MIDAS_TRANSFORMS, _TORCH_DEVICE
    if torch is None:
        return None, None, None
    if _MIDAS_MODEL is None:
        _TORCH_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"  [MIDAS] Initializing PyTorch MiDaS model on device: {_TORCH_DEVICE}...")
        _MIDAS_MODEL = torch.hub.load("intel-isl/MiDaS", model_type, trust_repo=True)
        _MIDAS_MODEL.to(_TORCH_DEVICE)
        _MIDAS_MODEL.eval()

        midas_transforms = torch.hub.load("intel-isl/MiDaS", "transforms", trust_repo=True)
        _MIDAS_TRANSFORMS = midas_transforms.small_transform if model_type == "MiDaS_small" else midas_transforms.dpt_transform

    return _MIDAS_MODEL, _MIDAS_TRANSFORMS, _TORCH_DEVICE

def generate_and_save_depth_map(img_input, target_depth_path: Path) -> np.ndarray:
    target_depth_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from engine.depth import make_depth
        if isinstance(img_input, (str, Path)) and Path(img_input).exists():
            make_depth(Path(img_input), target_depth_path)
        else:
            temp_in = target_depth_path.parent / f"temp_{target_depth_path.stem}.png"
            cv2.imwrite(str(temp_in), img_input)
            make_depth(temp_in, target_depth_path)
            if temp_in.exists():
                temp_in.unlink()

        if target_depth_path.exists():
            depth_u8 = cv2.imread(str(target_depth_path), cv2.IMREAD_GRAYSCALE)
            if depth_u8 is not None:
                return depth_u8
    except Exception as e:
        print(f"  [DEPTH] ONNX Depth-Anything fallback to MiDaS: {e}")

    img_bgr = img_input if isinstance(img_input, np.ndarray) else cv2.imread(str(img_input))
    if img_bgr is None:
        fallback_map = np.full((1920, 1080), 128, dtype=np.uint8)
        cv2.imwrite(str(target_depth_path), fallback_map)
        return fallback_map

    model, transform, device = get_midas_model("MiDaS_small")
    if model is not None:
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        input_batch = transform(img_rgb).to(device)

        with torch.no_grad():
            prediction = model(input_batch)
            prediction = torch.nn.functional.interpolate(
                prediction.unsqueeze(1),
                size=img_bgr.shape[:2],
                mode="bicubic",
                align_corners=False,
            ).squeeze()

        depth_map = prediction.cpu().numpy()
        d_min, d_max = depth_map.min(), depth_map.max()
        depth_norm = (depth_map - d_min) / (d_max - d_min) if d_max - d_min > 0 else np.zeros_like(depth_map)
        depth_norm = np.power(depth_norm, 1.4)
        depth_u8 = (depth_norm * 255.0).astype(np.uint8)
        cv2.imwrite(str(target_depth_path), depth_u8)
        return depth_u8

    fallback_map = np.full(img_bgr.shape[:2], 128, dtype=np.uint8)
    cv2.imwrite(str(target_depth_path), fallback_map)
    return fallback_map

def convert_to_devanagari_num(text_str: str) -> str:
    devanagari_map = {
        '0': '०', '1': '१', '2': '२', '3': '३', '4': '४',
        '5': '५', '6': '६', '7': '७', '8': '८', '9': '९'
    }
    return "".join(devanagari_map.get(ch, ch) for ch in str(text_str))

FONT_SIZES = {
    "main_title": 76,
    "sub_title": 36,
    "sanskrit_verse": 44,
    "sanskrit_badges": 30,
    "meaning_header": 28,
    "meaning_text": 34,
    "moment_header": 28,
    "moment_text": 32
}

LAYOUT = {
    "sanskrit_line_spacing": 20,
    "meaning_line_spacing": 16,
    "moment_line_spacing": 14,
    "box_gap": 22,
    "side_margin": 64,
    "corner_radius": 22,
    "box_padding_x": 36,
    "box_padding_y": 24,
    "bottom_safe_area": 140
}

SHINE_DURATION = 0.22
GOLD_SHINE = (255, 245, 160, 255)
GOLD_GLOW_BACK = (255, 215, 0, 180)

def ffmpeg():
    return shutil.which("ffmpeg") or r"C:\ffmpeg\bin\ffmpeg.exe"

def test_encoder_works(encoder_name: str) -> bool:
    cmd = [
        ffmpeg(), '-y', '-nostdin',
        '-f', 'lavfi', '-i', 'nullsrc=s=128x128:d=0.1',
        '-c:v', encoder_name,
        '-f', 'null', '-'
    ]
    try:
        p = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        return p.returncode == 0
    except Exception:
        return False

def detect_best_encoder():
    for enc in ("h264_nvenc", "h264_qsv", "h264_amf", "h264_mf"):
        if test_encoder_works(enc):
            return enc
    return "libx264"

def get_audio_duration(wav_path):
    if not Path(wav_path).exists():
        return 0.0
    try:
        with wave.open(str(wav_path), 'rb') as wav_file:
            return wav_file.getnframes() / float(wav_file.getframerate())
    except Exception:
        cmd = [
            ffmpeg(), "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(wav_path)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            return float(res.stdout.strip())
        except Exception:
            return 64.0

FONT_DOWNLOAD_URLS = {
    "NotoSerifDevanagari-Bold.ttf": "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSerifDevanagari/NotoSerifDevanagari-Bold.ttf",
    "Cinzel-Bold.ttf": "https://github.com/google/fonts/raw/main/ofl/cinzel/Cinzel-Bold.ttf",
    "EBGaramond-Medium.ttf": "https://github.com/google/fonts/raw/main/ofl/ebgaramond/EBGaramond-Medium.ttf",
    "NotoSansTelugu-Bold.ttf": "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansTelugu/NotoSansTelugu-Bold.ttf",
    "NotoSansTamil-Bold.ttf": "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansTamil/NotoSansTamil-Bold.ttf",
    "NotoSansMalayalam-Bold.ttf": "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansMalayalam/NotoSansMalayalam-Bold.ttf",
    "NotoSansKannada-Bold.ttf": "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansKannada/NotoSansKannada-Bold.ttf",
}

def load_font(preferred_names, size, assets_dir=None, root_dir=None):
    if isinstance(preferred_names, str):
        preferred_names = [preferred_names]
    dirs_to_check = []
    if assets_dir:
        dirs_to_check.extend([Path(assets_dir) / "fonts", Path(assets_dir)])
    if root_dir:
        dirs_to_check.extend([Path(root_dir) / "assets" / "fonts", Path(root_dir) / "fonts", Path(root_dir) / "assets"])

    dirs_to_check.extend([
        Path("/usr/share/fonts/truetype/dejavu"),
        Path("/usr/share/fonts/truetype/freefont"),
        Path("/usr/share/fonts"),
        Path(r"C:\Windows\Fonts")
    ])

    for name in preferred_names:
        for d in dirs_to_check:
            p = d / name
            if p.exists():
                try:
                    return ImageFont.truetype(str(p), size)
                except OSError:
                    pass
        if os.path.exists(name):
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                pass

        if name in FONT_DOWNLOAD_URLS and root_dir:
            target_p = Path(root_dir) / "assets" / "fonts" / name
            target_p.parent.mkdir(parents=True, exist_ok=True)
            try:
                urllib.request.urlretrieve(FONT_DOWNLOAD_URLS[name], str(target_p))
                return ImageFont.truetype(str(target_p), size)
            except Exception:
                pass

    return ImageFont.load_default()

def wrap_text_to_width(text, font, max_width, draw):
    if isinstance(text, list):
        out = []
        for line in text:
            out.extend(wrap_text_to_width(line, font, max_width, draw))
        return out

    words = str(text).split()
    lines = []
    current_line = []

    for word in words:
        current_line.append(word)
        test_str = " ".join(current_line)
        bbox = draw.textbbox((0, 0), test_str, font=font)
        if (bbox[2] - bbox[0]) > max_width:
            if len(current_line) > 1:
                current_line.pop()
                lines.append(" ".join(current_line))
                current_line = [word]
            else:
                lines.append(word)
                current_line = []
    if current_line:
        lines.append(" ".join(current_line))
    return lines

def draw_centered_text(draw, y, text, font, fill, canvas_width=1080, stroke_w=0, stroke_fill=(0,0,0)):
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_w)
    w = bbox[2] - bbox[0]
    x = (canvas_width - w) // 2
    draw.text((x, y), text, font=font, fill=fill, stroke_width=stroke_w, stroke_fill=stroke_fill)
    return bbox[3] - bbox[1]

def measure_lines_height(draw, lines, font, line_spacing):
    heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        heights.append(bbox[3] - bbox[1])
    total_h = sum(heights) + line_spacing * max(0, len(lines) - 1)
    return total_h, heights

def compute_char_layout(lines, start_y, heights, line_spacing, font, draw, canvas_width=1080, is_english=False):
    chars_info = []
    cur_y = start_y
    
    # Decoupled layout rules: English preserves spaces cleanly; Devanagari groups atomic graphemes
    if is_english:
        token_pattern = re.compile(r'(\s+|.)')
    else:
        token_pattern = re.compile(r'(?:[\u0900-\u097F]\u094d)*[\u0900-\u097F][\u093e-\u094c\u0932\u0941\u0942\u0943\u0947\u0948\u094b\u094c\u0902\u0903\u0901\u093c]*|\s|.')

    for i, line in enumerate(lines):
        if not line:
            cur_y += heights[i] + line_spacing
            continue
            
        line_bbox = draw.textbbox((0, 0), line, font=font)
        line_w = line_bbox[2] - line_bbox[0]
        start_x = (canvas_width - line_w) // 2
        
        chunks = token_pattern.findall(line)
        chunks = [c for c in chunks if c is not None]
        
        running_text = ""
        for chunk in chunks:
            prefix_bbox = draw.textbbox((0, 0), running_text, font=font) if running_text else (0, 0, 0, 0)
            prefix_w = prefix_bbox[2] - prefix_bbox[0]
            chars_info.append({"char": chunk, "pos": (start_x + prefix_w, cur_y)})
            running_text += chunk
            
        cur_y += heights[i] + line_spacing
    return chars_info

def draw_golden_lotus(draw, center_x, center_y, scale=1.0, gold_bright=(255, 230, 140, 255), gold_main=(212, 175, 86, 255), gold_dark=(140, 105, 45, 255)):
    cx, cy = center_x, center_y
    r_aura = int(24 * scale)
    draw.ellipse([cx - r_aura, cy - r_aura, cx + r_aura, cy + r_aura], outline=(gold_main[0], gold_main[1], gold_main[2], 120), width=1)
    petals = 8
    for i in range(petals):
        angle = i * (2 * math.pi / petals)
        px = cx + math.cos(angle) * (14 * scale)
        py = cy + math.sin(angle) * (14 * scale)
        r_p = int(5 * scale)
        draw.ellipse([px - r_p, py - r_p, px + r_p, py + r_p], fill=gold_main, outline=gold_dark, width=1)
    for i in range(petals):
        angle = (i * (2 * math.pi / petals)) + (math.pi / petals)
        px = cx + math.cos(angle) * (8 * scale)
        py = cy + math.sin(angle) * (8 * scale)
        r_p = int(3.5 * scale)
        draw.ellipse([px - r_p, py - r_p, px + r_p, py + r_p], fill=gold_bright, outline=gold_dark, width=1)
    draw.ellipse([cx - int(4*scale), cy - int(4*scale), cx + int(4*scale), cy + int(4*scale)], fill=gold_bright, outline=gold_dark)

def draw_programmatic_gold_frame(w, h, gold_main=(212, 175, 86, 240), gold_bright=(255, 230, 140, 255), gold_dark=(140, 105, 45, 240)):
    border_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(border_layer)
    m1, m2 = 28, 38
    d.rectangle([m1, m1, w - m1, h - m1], outline=gold_main, width=2)
    d.rectangle([m2, m2, w - m2, h - m2], outline=(gold_main[0], gold_main[1], gold_main[2], 120), width=1)

    corners = [(m1, m1, 1, 1), (w - m1, m1, -1, 1), (m1, h - m1, 1, -1), (w - m1, h - m1, -1, -1)]
    for cx, cy, sx, sy in corners:
        x_st, x_en = sorted([cx, cx + (74 * sx)])
        y_st, y_en = sorted([cy, cy + (74 * sy)])
        d.arc([x_st, y_st, x_en, y_en], 0, 360, fill=gold_main, width=2)
        draw_golden_lotus(d, cx + (32 * sx), cy + (32 * sy), scale=1.1, gold_bright=gold_bright, gold_main=gold_main, gold_dark=gold_dark)
    return border_layer

def draw_3d_header(canvas_img, y_title, y_sub, title_text, sub_text, f_title, f_sub, gold_color, white_color):
    shadow_layer = Image.new("RGBA", canvas_img.size, (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow_layer)
    t_bbox = s_draw.textbbox((0, 0), title_text, font=f_title)
    t_x = (canvas_img.width - (t_bbox[2] - t_bbox[0])) // 2
    s_bbox = s_draw.textbbox((0, 0), sub_text, font=f_sub)
    s_w = s_bbox[2] - s_bbox[0]
    s_x = (canvas_img.width - s_w) // 2

    s_draw.text((t_x, y_title + 6), title_text, font=f_title, fill=(0, 0, 0, 240), stroke_width=4, stroke_fill=(0, 0, 0, 240))
    s_draw.text((s_x, y_sub + 4), sub_text, font=f_sub, fill=(0, 0, 0, 220), stroke_width=3, stroke_fill=(0, 0, 0, 220))
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=6))
    canvas_img.alpha_composite(shadow_layer)

    main_draw = ImageDraw.Draw(canvas_img)
    main_draw.text((t_x, y_title), title_text, font=f_title, fill=white_color, stroke_width=2, stroke_fill=(20, 20, 20, 230))
    main_draw.text((s_x, y_sub), sub_text, font=f_sub, fill=gold_color, stroke_width=1, stroke_fill=(20, 20, 20, 230))
    main_draw.line([(s_x - 110, y_sub + 16), (s_x - 16, y_sub + 16)], fill=gold_color, width=2)
    main_draw.line([(s_x + s_w + 16, y_sub + 16), (s_x + s_w + 110, y_sub + 16)], fill=gold_color, width=2)

def calculate_char_times(chars, start_t, end_t):
    if not chars:
        return []
    weights = [1.2 if item["char"] in ("।", "॥", ".", "\n") else (1.0 if item["char"] == " " else 1.0) for item in chars]
    total_w = sum(weights)
    total_d = max(0.1, end_t - start_t)
    timed, cur_t = [], start_t
    for idx, item in enumerate(chars):
        timed.append({"char": item["char"], "pos": item["pos"], "appear_t": cur_t})
        cur_t += (weights[idx] / total_w) * total_d
    return timed

def render_karaoke_chars(draw_ctx, timed_chars, current_t, font, normal_color):
    for item in timed_chars:
        if current_t >= item["appear_t"]:
            time_alive = current_t - item["appear_t"]
            x, y = item["pos"]
            if time_alive < SHINE_DURATION:
                draw_ctx.text((x, y), item["char"], font=font, fill=GOLD_SHINE)
            else:
                draw_ctx.text((x, y), item["char"], font=font, fill=normal_color)

def rgba_to_bgr_and_alpha(pil_img):
    arr = np.array(pil_img)
    bgr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
    alpha = arr[:, :, 3:4].astype(np.float32) / 255.0
    return bgr, alpha

def prepare_sequential_ui(w, h, cfg_path, font_path, sans_dur, eng_dur, total_audio_duration):
    root_dir = Path(cfg_path).resolve().parent.parent if Path(cfg_path).resolve().parent.name == "cache" else Path(cfg_path).resolve().parent
    assets_dir = root_dir / "assets"
    cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
    verse_data = cfg.get("verse", {})
    lang_info = cfg.get("language", {"code": "en", "name": "English"})

    raw_sanskrit = convert_to_devanagari_num(verse_data.get("sanskrit", "").replace("\\n", "\n").strip())
    sanskrit_lines_raw = [l.strip() for l in raw_sanskrit.split("\n") if l.strip()]
    meaning = verse_data.get("meaning", "").strip()
    insight = verse_data.get("insight", "").strip()

    ch_num = convert_to_devanagari_num(verse_data.get("chapter", 1))
    v_num = convert_to_devanagari_num(verse_data.get("verse_number", 1))

    CREAM_WHITE = (245, 242, 235, 255)
    BODY_WHITE  = (228, 230, 235, 255)
    GOLD_ACCENT = (212, 175, 86, 255)
    CARD_BG     = (10, 14, 20, 220)
    CARD_BORDER = (212, 175, 86, 210)

    regional_meaning_fonts = {
        "te": ["NotoSansTelugu-Bold.ttf"],
        "ta": ["NotoSansTamil-Bold.ttf"],
        "ml": ["NotoSansMalayalam-Bold.ttf"],
        "kn": ["NotoSansKannada-Bold.ttf"],
        "hi": ["NotoSerifDevanagari-Bold.ttf", "mangal.ttf"],
    }
    preferred_body_fonts = regional_meaning_fonts.get(
        lang_info.get("code", "en"), 
        ["EBGaramond-Medium.ttf", "georgia.ttf", "DejaVuSerif.ttf"]
    )

    f_title      = load_font(["Cinzel-Bold.ttf", "timesbd.ttf", "DejaVuSans-Bold.ttf"], FONT_SIZES["main_title"], assets_dir, root_dir)
    f_sub        = load_font(["Cinzel-Bold.ttf", "timesbd.ttf", "DejaVuSans-Bold.ttf"], FONT_SIZES["sub_title"], assets_dir, root_dir)
    f_sanskrit   = load_font(["NotoSerifDevanagari-Bold.ttf", "mangal.ttf"], FONT_SIZES["sanskrit_verse"], assets_dir, root_dir)
    f_sk_badge   = load_font(["NotoSerifDevanagari-Bold.ttf", "mangal.ttf"], FONT_SIZES["sanskrit_badges"], assets_dir, root_dir)
    f_meaning_hd = load_font(["Cinzel-Bold.ttf", "timesbd.ttf", "DejaVuSans-Bold.ttf"], FONT_SIZES["meaning_header"], assets_dir, root_dir)
    f_meaning    = load_font(preferred_body_fonts, FONT_SIZES["meaning_text"], assets_dir, root_dir)
    f_moment_hd  = load_font(["Cinzel-Bold.ttf", "timesbd.ttf", "DejaVuSans-Bold.ttf"], FONT_SIZES["moment_header"], assets_dir, root_dir)
    f_moment     = load_font(preferred_body_fonts, FONT_SIZES["moment_text"], assets_dir, root_dir)

    PAD_Y, PAD_X = LAYOUT["box_padding_y"], LAYOUT["box_padding_x"]
    GAP, RAD = LAYOUT["box_gap"], LAYOUT["corner_radius"]
    CARD_L, CARD_R = LAYOUT["side_margin"], w - LAYOUT["side_margin"]
    MAX_TEXT_WIDTH = (CARD_R - CARD_L) - (PAD_X * 2)

    measure_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d_m = ImageDraw.Draw(measure_img)

    sanskrit_lines = wrap_text_to_width(sanskrit_lines_raw, f_sanskrit, MAX_TEXT_WIDTH, d_m)
    meaning_lines  = wrap_text_to_width(meaning, f_meaning, MAX_TEXT_WIDTH, d_m)
    moment_lines   = wrap_text_to_width(insight, f_moment, MAX_TEXT_WIDTH, d_m) if insight else []

    sanskrit_top_badge = "॥ श्रीमद्भगवद्गीता ॥"
    sanskrit_bottom_badge = f"अध्याय {ch_num} । श्लोक {v_num}"

    sk_total_h, sk_heights = measure_lines_height(d_m, sanskrit_lines, f_sanskrit, LAYOUT["sanskrit_line_spacing"])
    badge_top_h = d_m.textbbox((0, 0), sanskrit_top_badge, font=f_sk_badge)[3] - d_m.textbbox((0, 0), sanskrit_top_badge, font=f_sk_badge)[1]
    badge_bot_h = d_m.textbbox((0, 0), sanskrit_bottom_badge, font=f_sk_badge)[3] - d_m.textbbox((0, 0), sanskrit_bottom_badge, font=f_sk_badge)[1]
    box1_h = PAD_Y + badge_top_h + 22 + sk_total_h + 22 + badge_bot_h + PAD_Y

    mean_total_h, mean_heights = measure_lines_height(d_m, meaning_lines, f_meaning, LAYOUT["meaning_line_spacing"])
    m_hd_h = d_m.textbbox((0, 0), "MEANING", font=f_meaning_hd)[3] - d_m.textbbox((0, 0), "MEANING", font=f_meaning_hd)[1]
    box2_h = PAD_Y + m_hd_h + 18 + mean_total_h + PAD_Y

    if moment_lines:
        mom_total_h, mom_heights = measure_lines_height(d_m, moment_lines, f_moment, LAYOUT["moment_line_spacing"])
        mom_hd_h = d_m.textbbox((0, 0), "THE MOMENT", font=f_moment_hd)[3] - d_m.textbbox((0, 0), "THE MOMENT", font=f_moment_hd)[1]
        box3_h = PAD_Y + mom_hd_h + 18 + mom_total_h + PAD_Y
    else:
        box3_h = 0

    box3_bot = h - LAYOUT["bottom_safe_area"]
    box3_top = box3_bot - box3_h
    box2_bot = (box3_top - GAP) if moment_lines else box3_bot
    box2_top = box2_bot - box2_h
    box1_bot = box2_top - GAP
    box1_top = box1_bot - box1_h

    if box1_top < 270:
        shift = 270 - box1_top
        box1_top += shift; box1_bot += shift; box2_top += shift; box2_bot += shift; box3_top += shift; box3_bot += shift

    sk_start_y = box1_top + PAD_Y + badge_top_h + 22
    sanskrit_chars_layout = compute_char_layout(sanskrit_lines, sk_start_y, sk_heights, LAYOUT["sanskrit_line_spacing"], f_sanskrit, d_m, canvas_width=w, is_english=False)
    
    mean_start_y = box2_top + PAD_Y + m_hd_h + 18
    meaning_chars_layout = compute_char_layout(meaning_lines, mean_start_y, mean_heights, LAYOUT["meaning_line_spacing"], f_meaning, d_m, canvas_width=w, is_english=True)
    
    moment_chars_layout = compute_char_layout(moment_lines, box3_top + PAD_Y + mom_hd_h + 18, mom_heights, LAYOUT["moment_line_spacing"], f_moment, d_m, canvas_width=w, is_english=True) if moment_lines else []

    avail_time = max(8.0, total_audio_duration - 3.0)
    
    sanskrit_voice_start = 1.0
    sanskrit_voice_end = sanskrit_voice_start + max(2.5, avail_time * 0.22)
    
    narration_voice_start = sanskrit_voice_end + 0.4
    
    len_mean = max(1, len(meaning_chars_layout))
    len_mom = len(moment_chars_layout)
    tot_c = len_mean + (len_mom if len_mom > 0 else 0)
    
    remaining_time = max(3.0, total_audio_duration - narration_voice_start - 1.5)
    mean_allotted = remaining_time * (len_mean / float(tot_c)) if tot_c > 0 else remaining_time
    
    meaning_voice_end = narration_voice_start + mean_allotted
    moment_voice_start = meaning_voice_end + 0.4
    moment_voice_end = total_audio_duration - 1.0 if len_mom > 0 else moment_voice_start

    border_img = draw_programmatic_gold_frame(w, h)
    border_bgr, border_alpha = rgba_to_bgr_and_alpha(border_img)

    header_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_3d_header(
        header_img, 80, 170, "BHAGAVAD GITA",
        f"CHAPTER {verse_data.get('chapter', 1)} • VERSE {verse_data.get('verse_number', 1)}",
        f_title, f_sub, GOLD_ACCENT, CREAM_WHITE
    )
    header_bgr, header_alpha = rgba_to_bgr_and_alpha(header_img)

    box1_container = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d_b1 = ImageDraw.Draw(box1_container)
    d_b1.rounded_rectangle([CARD_L, box1_top, CARD_R, box1_bot], radius=RAD, fill=CARD_BG, outline=CARD_BORDER, width=2)
    draw_centered_text(d_b1, box1_top + PAD_Y, sanskrit_top_badge, f_sk_badge, GOLD_ACCENT, canvas_width=w)
    draw_centered_text(d_b1, box1_bot - PAD_Y - badge_bot_h, sanskrit_bottom_badge, f_sk_badge, GOLD_ACCENT, canvas_width=w)
    box1_bgr, box1_alpha = rgba_to_bgr_and_alpha(box1_container)

    box2_container = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d_b2 = ImageDraw.Draw(box2_container)
    d_b2.rounded_rectangle([CARD_L, box2_top, CARD_R, box2_bot], radius=RAD, fill=CARD_BG, outline=CARD_BORDER, width=2)
    draw_centered_text(d_b2, box2_top + PAD_Y, "MEANING", f_meaning_hd, GOLD_ACCENT, canvas_width=w)
    box2_bgr, box2_alpha = rgba_to_bgr_and_alpha(box2_container)

    if moment_lines:
        box3_container = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d_b3 = ImageDraw.Draw(box3_container)
        d_b3.rounded_rectangle([CARD_L, box3_top, CARD_R, box3_bot], radius=RAD, fill=CARD_BG, outline=CARD_BORDER, width=2)
        draw_centered_text(d_b3, box3_top + PAD_Y, "THE MOMENT", f_moment_hd, GOLD_ACCENT, canvas_width=w)
        box3_bgr, box3_alpha = rgba_to_bgr_and_alpha(box3_container)
    else:
        box3_bgr, box3_alpha = None, None

    return {
        "w": w, "h": h,
        "f_sanskrit": f_sanskrit, "f_meaning": f_meaning, "f_moment": f_moment,
        "CREAM_WHITE": CREAM_WHITE, "BODY_WHITE": BODY_WHITE,
        "border_bgr": border_bgr, "border_alpha": border_alpha,
        "header_bgr": header_bgr, "header_alpha": header_alpha,
        "box1_bgr": box1_bgr, "box1_alpha": box1_alpha,
        "box2_bgr": box2_bgr, "box2_alpha": box2_alpha,
        "box3_bgr": box3_bgr, "box3_alpha": box3_alpha,
        "t_border_fade_in": (0.3, 1.2),
        "t_title_fade_in": (0.5, 1.5),
        "t_box1_fade_in": (1.2, 2.0),
        "t_box2_fade_in": (sanskrit_voice_end + 0.2, sanskrit_voice_end + 0.8),
        "t_box3_fade_in": (meaning_voice_end + 0.2, meaning_voice_end + 0.8),
        "global_ui_fade_out": (max(total_audio_duration - 2.5, total_audio_duration - 3.5), total_audio_duration - 0.5),
        "timed_sanskrit_chars": calculate_char_times(sanskrit_chars_layout, sanskrit_voice_start, sanskrit_voice_end),
        "timed_meaning_chars": calculate_char_times(meaning_chars_layout, narration_voice_start, meaning_voice_end),
        "timed_moment_chars": calculate_char_times(moment_chars_layout, moment_voice_start, moment_voice_end)
    }

def start_ffmpeg_process(out_path, w, h, fps, encoder_name, fast_mode=False):
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg(), '-y', '-nostdin',
        '-f', 'rawvideo',
        '-vcodec', 'rawvideo',
        '-s', f'{w}x{h}',
        '-pix_fmt', 'bgr24',
        '-r', str(fps),
        '-i', '-'
    ]
    if fast_mode:
        cmd += ['-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'fastdecode', '-crf', '30']
    elif encoder_name == "h264_nvenc":
        cmd += ['-c:v', 'h264_nvenc', '-preset', 'fast', '-b:v', '8M']
    elif encoder_name == "h264_qsv":
        cmd += ['-c:v', 'h264_qsv', '-preset', 'fast', '-b:v', '8M']
    elif encoder_name == "h264_amf":
        cmd += ['-c:v', 'h264_amf', '-usage', 'transcoding', '-b:v', '8M']
    elif encoder_name == "h264_mf":
        cmd += ['-c:v', 'h264_mf', '-b:v', '8M']
    else:
        cmd += ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-threads', '0']

    cmd += ['-pix_fmt', 'yuv420p', str(out_path)]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def render_master_video(images, out, master_audio_path, bg_music_path=None, w=1080, h=1920, fps=30, cfg_path=None, sans_dur=0.0, eng_dur=0.0, fast_mode=False):
    w, h = 1080, 1920
    fps = 24 if fast_mode else 30

    best_encoder = detect_best_encoder() if not fast_mode else "libx264"
    audio_duration = get_audio_duration(master_audio_path) or 64.0
    total_frames = int(audio_duration * fps)

    target_track = bg_music_path if (bg_music_path and Path(bg_music_path).exists()) else master_audio_path
    wave_profile = extract_music_wave_average_profile(Path(target_track), fps=fps)

    ui = prepare_sequential_ui(w, h, cfg_path, None, sans_dur, eng_dur, audio_duration)

    frames_per_img = total_frames // len(images)
    rem_frames = total_frames % len(images)
    camera_motions = [random.choice(["dolly_in", "pan_left", "pan_right", "tilt_float"]) for _ in range(len(images))]

    grid_y, grid_x = np.indices((h, w), dtype=np.float32)
    cx, cy = w / 2.0, h / 2.0

    overscan = 1.12
    ow, oh = int(w * overscan), int(h * overscan)
    ox_offset = (ow - w) // 2
    oy_offset = (oh - h) // 2

    process = start_ffmpeg_process(out, w, h, fps, best_encoder, fast_mode=fast_mode)

    global_frame = 0
    start_time = time.time()
    
    print("\n  [RENDER PROGRESS]")
    try:
        for img_idx, image_path in enumerate(images):
            img_path = Path(image_path).resolve()
            project_root = img_path.parent.parent.parent if img_path.parent.name == "images" else img_path.parent.parent
            depth_path = project_root / "depth" / f"{img_path.stem}.png"

            img = cv2.imread(str(img_path))
            if img is None:
                continue  

            h_img, w_img = img.shape[:2]
            img[int(h_img * 0.94):h_img, int(w_img * 0.82):w_img] = (15, 15, 15)

            orig_h, orig_w = img.shape[:2]
            aspect_target = w / float(h)
            if (orig_w / float(orig_h)) > aspect_target:
                new_w = int(orig_h * aspect_target)
                offset = (orig_w - new_w) // 2
                img_cropped = img[:, offset:offset+new_w]
                depth_slice = (slice(None), slice(offset, offset+new_w))
            else:
                new_h = int(orig_w / aspect_target)
                offset = (orig_h - new_h) // 2
                img_cropped = img[offset:offset+new_h, :]
                depth_slice = (slice(offset, offset+new_h), slice(None))

            img_overscanned = cv2.resize(img_cropped, (ow, oh), interpolation=cv2.INTER_CUBIC)

            if not depth_path.exists():
                generate_and_save_depth_map(img_path, depth_path)
            depth_raw = cv2.imread(str(depth_path), cv2.IMREAD_GRAYSCALE)
            if depth_raw is None:
                depth_raw = generate_and_save_depth_map(img_path, depth_path)

            depth_cropped = depth_raw[depth_slice]
            depth_overscanned = cv2.resize(depth_cropped, (ow, oh), interpolation=cv2.INTER_CUBIC)

            depth_smooth = cv2.bilateralFilter(depth_overscanned, 9, 75, 75)
            depth_smooth = cv2.GaussianBlur(depth_smooth, (7, 7), 1.5)
            depth_norm = depth_smooth.astype(np.float32) / 255.0

            motion_style = camera_motions[img_idx]
            current_frames = frames_per_img + (rem_frames if img_idx == len(images) - 1 else 0)

            for f_i in range(current_frames):
                energy = wave_profile[global_frame] if global_frame < len(wave_profile) else 1.0
                t = f_i / float(current_frames)
                ease = 0.5 * (1.0 - math.cos(math.pi * t))

                max_disp = 28.0 * energy
                if motion_style == "pan_left":
                    cam_dx = -math.sin(math.pi * ease) * max_disp
                    cam_dy = math.cos(math.pi * ease) * (max_disp * 0.2)
                    zoom_factor = 1.0 + (0.035 * ease * energy)
                elif motion_style == "pan_right":
                    cam_dx = math.sin(math.pi * ease) * max_disp
                    cam_dy = -math.cos(math.pi * ease) * (max_disp * 0.2)
                    zoom_factor = 1.0 + (0.035 * ease * energy)
                elif motion_style == "tilt_float":
                    cam_dx = math.cos(math.pi * ease) * (max_disp * 0.25)
                    cam_dy = math.sin(math.pi * ease) * (max_disp * 0.6)
                    zoom_factor = 1.0 + (0.04 * ease * energy)
                else:
                    cam_dx = 0.0
                    cam_dy = math.sin(math.pi * ease) * (max_disp * 0.15)
                    zoom_factor = 1.0 + (0.06 * ease * energy)

                sample_depth = depth_norm[oy_offset:oy_offset+h, ox_offset:ox_offset+w]
                depth_weight = 0.20 + (0.80 * sample_depth)

                map_x = (grid_x - cx) / zoom_factor + cx + ox_offset + (cam_dx * (depth_weight - 0.5))
                map_y = (grid_y - cy) / zoom_factor + cy + oy_offset + (cam_dy * (depth_weight - 0.5))

                warped_bg = cv2.remap(
                    img_overscanned,
                    map_x.astype(np.float32),
                    map_y.astype(np.float32),
                    interpolation=cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_REFLECT_101
                )

                comp = warped_bg.astype(np.float32)

                current_time_sec = global_frame / fps
                fo_st, fo_end = ui["global_ui_fade_out"]
                global_fade = 0.0 if current_time_sec >= fo_end else (1.0 - ((current_time_sec - fo_st) / (fo_end - fo_st)) if current_time_sec >= fo_st else 1.0)

                if global_fade > 0.0:
                    b_st, b_en = ui["t_border_fade_in"]
                    if current_time_sec >= b_st:
                        a_b = min(1.0, (current_time_sec - b_st) / (b_en - b_st)) * global_fade
                        eff_a = ui["border_alpha"] * a_b
                        comp = comp * (1.0 - eff_a) + (ui["border_bgr"].astype(np.float32) * eff_a)

                    t_st, t_en = ui["t_title_fade_in"]
                    if current_time_sec >= t_st:
                        a_t = min(1.0, (current_time_sec - t_st) / (t_en - t_st)) * global_fade
                        eff_a = ui["header_alpha"] * a_t
                        comp = comp * (1.0 - eff_a) + (ui["header_bgr"].astype(np.float32) * eff_a)

                    b1_st, b1_en = ui["t_box1_fade_in"]
                    if current_time_sec >= b1_st:
                        a_b1 = min(1.0, (current_time_sec - b1_st) / (b1_en - b1_st)) * global_fade
                        eff_a = ui["box1_alpha"] * a_b1
                        comp = comp * (1.0 - eff_a) + (ui["box1_bgr"].astype(np.float32) * eff_a)

                    b2_st, b2_en = ui["t_box2_fade_in"]
                    if current_time_sec >= b2_st:
                        a_b2 = min(1.0, (current_time_sec - b2_st) / (b2_en - b2_st)) * global_fade
                        eff_a = ui["box2_alpha"] * a_b2
                        comp = comp * (1.0 - eff_a) + (ui["box2_bgr"].astype(np.float32) * eff_a)

                    if ui["box3_alpha"] is not None:
                        b3_st, b3_en = ui["t_box3_fade_in"]
                        if current_time_sec >= b3_st:
                            a_b3 = min(1.0, (current_time_sec - b3_st) / (b3_en - b3_st)) * global_fade
                            eff_a = ui["box3_alpha"] * a_b3
                            comp = comp * (1.0 - eff_a) + (ui["box3_bgr"].astype(np.float32) * eff_a)

                    text_overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                    d_txt = ImageDraw.Draw(text_overlay)
                    render_karaoke_chars(d_txt, ui["timed_sanskrit_chars"], current_time_sec, ui["f_sanskrit"], ui["CREAM_WHITE"])
                    render_karaoke_chars(d_txt, ui["timed_meaning_chars"], current_time_sec, ui["f_meaning"], ui["BODY_WHITE"])
                    render_karaoke_chars(d_txt, ui["timed_moment_chars"], current_time_sec, ui["f_moment"], ui["BODY_WHITE"])

                    txt_np = np.array(text_overlay)
                    txt_bgr = cv2.cvtColor(txt_np, cv2.COLOR_RGBA2BGR).astype(np.float32)
                    txt_alpha = (txt_np[:, :, 3:4].astype(np.float32) / 255.0) * global_fade
                    comp = comp * (1.0 - txt_alpha) + (txt_bgr * txt_alpha)

                frame = np.ascontiguousarray(np.clip(comp, 0, 255).astype(np.uint8))

                if process.poll() is not None:
                    _, err = process.communicate()
                    err_msg = err.decode('utf-8', errors='ignore') if err else "Unknown FFmpeg termination"
                    raise RuntimeError(f"FFmpeg exited prematurely:\n{err_msg}")

                try:
                    process.stdin.write(frame.tobytes())
                except (OSError, BrokenPipeError):
                    _, err = process.communicate()
                    err_msg = err.decode('utf-8', errors='ignore') if err else "Pipe closed unexpectedly"
                    raise RuntimeError(f"FFmpeg write error:\n{err_msg}")

                global_frame += 1

                if global_frame % 10 == 0 or global_frame == total_frames:
                    pct = (global_frame / float(total_frames)) * 100.0
                    elapsed = max(0.001, time.time() - start_time)
                    cur_fps = global_frame / elapsed
                    bar_len = 25
                    filled = int(bar_len * global_frame // total_frames)
                    bar = '█' * filled + '-' * (bar_len - filled)
                    sys.stdout.write(f"\r  Rendering: [{bar}] {pct:5.1f}% | {global_frame}/{total_frames} frames ({cur_fps:.1f} fps)")
                    sys.stdout.flush()

        process.stdin.close()
        _, stderr_data = process.communicate()
        if process.returncode != 0:
            err_msg = stderr_data.decode('utf-8', errors='ignore') if stderr_data else "Unknown error"
            raise RuntimeError(f"FFmpeg encoding failed with returncode {process.returncode}:\n{err_msg}")

        print("\n  ✓ 3D Parallax Video stream rendered successfully.")
    except Exception as e:
        if process.poll() is None:
            process.kill()
        raise e

def mux(video, audio, out, chapter=1, verse=1):
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    
    title_str = f"Srimad Bhagavad Gita - Chapter {chapter} Verse {verse}"
    author_str = "Venkatesh Marturu"
    studio_str = "@BhagavadGita-slokha"
    copyright_str = "© 2026 @BhagavadGita-slokha. All rights reserved."
    desc_str = f"Official studio master for Srimad Bhagavad Gita Chapter {chapter} Verse {verse}. Produced, designed, and mastered by Venkatesh Marturu at @BhagavadGita-slokha."

    cmd = [
        ffmpeg(), "-y",
        "-nostdin",
        "-i", str(video),
        "-i", str(audio),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "256k",
        "-shortest",
        "-metadata", f"title={title_str}",
        "-metadata", f"artist={author_str}",
        "-metadata", f"author={author_str}",
        "-metadata", f"director={author_str}",
        "-metadata", f"composer={author_str}",
        "-metadata", f"album_artist={author_str}",
        "-metadata", f"publisher={studio_str}",
        "-metadata", f"album=Srimad Bhagavad Gita Cinematic Master Series",
        "-metadata", f"copyright={copyright_str}",
        "-metadata", "year=2026",
        "-metadata", "date=2026",
        "-metadata", "genre=Ancient Philosophy / Devotional / Sacred Music",
        "-metadata", f"comment={desc_str}",
        "-metadata", f"description={desc_str}",
        "-metadata", f"synopsis={desc_str}",
        "-metadata", "rating=5",
        "-metadata", "rating_percent=99",
        "-metadata", "service_name=@BhagavadGita-slokha",
        "-metadata", "service_provider=@BhagavadGita-slokha",
        "-metadata", "encoder=Adobe Premiere Pro 2026 (Windows)",
        "-metadata:s:v:0", "handler_name=Blacklines Studio Video Renderer",
        "-metadata:s:a:0", "handler_name=Blacklines High Fidelity Master Audio",
        "-metadata:s:v:0", "encoder=MainConcept H.264 Video Encoder",
        "-metadata:s:a:0", "encoder=Dolby Digital Professional AAC Master",
        str(out)
    ]
    subprocess.run(
        cmd,
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
