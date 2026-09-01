from pathlib import Path
import subprocess
import shutil
import math
import os
import random
import cv2
import numpy as np
import json
import wave
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ==============================================================================
# 🎛️ FONT SIZES & SPACING CONFIGURATION
# ==============================================================================

FONT_SIZES = {
    "main_title": 72,
    "sub_title": 34,
    "sanskrit_verse": 44,
    "sanskrit_badges": 28,
    "meaning_header": 26,
    "meaning_text": 34,
    "moment_header": 26,
    "moment_text": 32
}

LAYOUT = {
    "sanskrit_line_spacing": 20,
    "meaning_line_spacing": 14,
    "moment_line_spacing": 12,
    "box_gap": 22,
    "side_margin": 60,
    "corner_radius": 20,
    "box_padding_x": 32,
    "box_padding_y": 22,
    "bottom_safe_area": 140
}

SHINE_DURATION = 0.22
GOLD_SHINE = (255, 245, 160, 255)
GOLD_GLOW_BACK = (255, 215, 0, 180)

def ffmpeg():
    return shutil.which("ffmpeg") or r"C:\ffmpeg\bin\ffmpeg.exe"

def encoder():
    try:
        p = subprocess.run([ffmpeg(), "-hide_banner", "-encoders"], capture_output=True, text=True)
        s = p.stdout
        for e in ("h264_mf", "h264_nvenc", "h264_qsv", "h264_amf"):
            if e in s:
                return e
    except Exception:
        pass
    return "libx264"

def get_audio_duration(wav_path):
    if not Path(wav_path).exists():
        return 0.0
    with wave.open(str(wav_path), 'rb') as wav_file:
        frames = wav_file.getnframes()
        rate = wav_file.getframerate()
        return frames / float(rate)

def load_font(preferred_names, size, root_dir=None):
    if isinstance(preferred_names, str):
        preferred_names = [preferred_names]
    
    dirs_to_check = []
    if root_dir:
        root_path = Path(root_dir)
        dirs_to_check.append(root_path / "assets" / "fonts")
        dirs_to_check.append(root_path / "fonts")
        dirs_to_check.append(root_path / "assets")

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
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()

def wrap_text_to_width(text, font, max_width, draw):
    if isinstance(text, list):
        wrapped_lines = []
        for line in text:
            wrapped_lines.extend(wrap_text_to_width(line, font, max_width, draw))
        return wrapped_lines

    words = str(text).split()
    lines = []
    current_line = []

    for word in words:
        current_line.append(word)
        test_line = " ".join(current_line)
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if (bbox[2] - bbox[0]) > max_width:
            if len(current_line) > 1:
                current_line.pop()
                lines.append(" ".join(current_line))
                current_line = [word]
            else:
                lines.append(test_line)
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

def compute_char_layout(lines, start_y, heights, line_spacing, font, draw, canvas_width=1080):
    chars_info = []
    cur_y = start_y
    for i, line in enumerate(lines):
        if not line:
            cur_y += heights[i] + line_spacing
            continue
        
        line_bbox = draw.textbbox((0, 0), line, font=font)
        line_w = line_bbox[2] - line_bbox[0]
        start_x = (canvas_width - line_w) // 2
        
        running_text = ""
        for ch in line:
            prefix_bbox = draw.textbbox((0, 0), running_text, font=font) if running_text else (0, 0, 0, 0)
            prefix_w = prefix_bbox[2] - prefix_bbox[0]
            
            chars_info.append({
                "char": ch,
                "pos": (start_x + prefix_w, cur_y)
            })
            running_text += ch
            
        cur_y += heights[i] + line_spacing
    return chars_info

def draw_golden_lotus(draw, center_x, center_y, scale=1.0, gold_bright=(255, 230, 140, 255), gold_main=(212, 175, 86, 255), gold_dark=(140, 105, 45, 255)):
    cx, cy = center_x, center_y
    r_aura = int(22 * scale)
    draw.ellipse([cx - r_aura, cy - r_aura, cx + r_aura, cy + r_aura], outline=(gold_main[0], gold_main[1], gold_main[2], 120), width=1)
    
    petals = 8
    for i in range(petals):
        angle = i * (2 * math.pi / petals)
        p_dist = 13 * scale
        px = cx + math.cos(angle) * p_dist
        py = cy + math.sin(angle) * p_dist
        r_p = int(4.5 * scale)
        draw.ellipse([px - r_p, py - r_p, px + r_p, py + r_p], fill=gold_main, outline=gold_dark, width=1)

    for i in range(petals):
        angle = (i * (2 * math.pi / petals)) + (math.pi / petals)
        p_dist = 7 * scale
        px = cx + math.cos(angle) * p_dist
        py = cy + math.sin(angle) * p_dist
        r_p = int(3.0 * scale)
        draw.ellipse([px - r_p, py - r_p, px + r_p, py + r_p], fill=gold_bright, outline=gold_dark, width=1)

    draw.ellipse([cx - int(3.5*scale), cy - int(3.5*scale), cx + int(3.5*scale), cy + int(3.5*scale)], fill=gold_bright, outline=gold_dark)
    d_size = int(2.5 * scale)
    diamond = [(cx, cy - d_size), (cx + d_size, cy), (cx, cy + d_size), (cx - d_size, cy)]
    draw.polygon(diamond, fill=(255, 255, 255, 255))

def draw_programmatic_gold_frame(w, h, gold_main=(212, 175, 86, 240), gold_bright=(255, 230, 140, 255), gold_dark=(140, 105, 45, 240)):
    border_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(border_layer)

    m1 = 28
    m2 = 38
    d.rectangle([m1, m1, w - m1, h - m1], outline=gold_main, width=2)
    d.rectangle([m2, m2, w - m2, h - m2], outline=(gold_main[0], gold_main[1], gold_main[2], 120), width=1)

    corners = [
        (m1, m1, 1, 1),
        (w - m1, m1, -1, 1),
        (m1, h - m1, 1, -1),
        (w - m1, h - m1, -1, -1)
    ]

    for cx, cy, sx, sy in corners:
        x_start, x_end = sorted([cx, cx + (74 * sx)])
        y_start, y_end = sorted([cy, cy + (74 * sy)])
        d.arc([x_start, y_start, x_end, y_end], 0, 360, fill=gold_main, width=2)

        x_inner_st, x_inner_en = sorted([cx + (14 * sx), cx + (54 * sx)])
        y_inner_st, y_inner_en = sorted([cy + (14 * sy), cy + (54 * sy)])
        d.arc([x_inner_st, y_inner_st, x_inner_en, y_inner_en], 0, 360, fill=gold_dark, width=1)

        d.ellipse([cx + (16*sx) - 4, cy - 4, cx + (16*sx) + 4, cy + 4], fill=gold_main)
        d.ellipse([cx - 4, cy + (16*sy) - 4, cx + 4, cy + (16*sy) + 4], fill=gold_main)

        flower_center_x = cx + (32 * sx)
        flower_center_y = cy + (32 * sy)
        draw_golden_lotus(d, flower_center_x, flower_center_y, scale=1.0, gold_bright=gold_bright, gold_main=gold_main, gold_dark=gold_dark)

    mid_x, mid_y = w // 2, h // 2
    draw_golden_lotus(d, mid_x, m1, scale=0.7, gold_bright=gold_bright, gold_main=gold_main, gold_dark=gold_dark)
    draw_golden_lotus(d, mid_x, h - m1, scale=0.7, gold_bright=gold_bright, gold_main=gold_main, gold_dark=gold_dark)
    draw_golden_lotus(d, m1, mid_y, scale=0.7, gold_bright=gold_bright, gold_main=gold_main, gold_dark=gold_dark)
    draw_golden_lotus(d, w - m1, mid_y, scale=0.7, gold_bright=gold_bright, gold_main=gold_main, gold_dark=gold_dark)

    return border_layer

def draw_3d_header(canvas_img, y_title, y_sub, title_text, sub_text, f_title, f_sub, gold_color, white_color):
    shadow_layer = Image.new("RGBA", canvas_img.size, (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow_layer)

    t_bbox = s_draw.textbbox((0, 0), title_text, font=f_title)
    t_w = t_bbox[2] - t_bbox[0]
    t_x = (canvas_img.width - t_w) // 2

    s_bbox = s_draw.textbbox((0, 0), sub_text, font=f_sub)
    s_w = s_bbox[2] - s_bbox[0]
    s_x = (canvas_img.width - s_w) // 2

    s_draw.text((t_x, y_title + 5), title_text, font=f_title, fill=(0, 0, 0, 240), stroke_width=4, stroke_fill=(0, 0, 0, 240))
    s_draw.text((s_x, y_sub + 3), sub_text, font=f_sub, fill=(0, 0, 0, 220), stroke_width=3, stroke_fill=(0, 0, 0, 220))
    s_draw.line([(s_x - 90, y_sub + 18), (s_x - 16, y_sub + 18)], fill=(0, 0, 0, 220), width=3)
    s_draw.line([(s_x + s_w + 16, y_sub + 18), (s_x + s_w + 90, y_sub + 18)], fill=(0, 0, 0, 220), width=3)

    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=5))
    canvas_img.alpha_composite(shadow_layer)

    main_draw = ImageDraw.Draw(canvas_img)
    main_draw.text((t_x, y_title), title_text, font=f_title, fill=white_color, stroke_width=2, stroke_fill=(20, 20, 20, 230))
    main_draw.text((s_x, y_sub), sub_text, font=f_sub, fill=gold_color, stroke_width=1, stroke_fill=(20, 20, 20, 230))
    main_draw.line([(s_x - 90, y_sub + 16), (s_x - 16, y_sub + 16)], fill=gold_color, width=2)
    main_draw.line([(s_x + s_w + 16, y_sub + 16), (s_x + s_w + 90, y_sub + 16)], fill=gold_color, width=2)

def calculate_char_times(chars, start_t, end_t):
    if not chars:
        return []
    
    weights = []
    for item in chars:
        ch = item["char"]
        if ch in ("।", "॥", ".", "\n"):
            weights.append(4.5)
        elif ch in (",", ";", ":", "-"):
            weights.append(2.5)
        elif ch == " ":
            weights.append(1.5)
        else:
            weights.append(1.0)
            
    total_weight = sum(weights)
    total_duration = max(0.1, end_t - start_t)
    
    timed = []
    current_time = start_t
    for idx, item in enumerate(chars):
        timed.append({
            "char": item["char"],
            "pos": item["pos"],
            "appear_t": current_time
        })
        current_time += (weights[idx] / total_weight) * total_duration
    return timed

def render_karaoke_chars(draw_ctx, timed_chars, current_t, font, normal_color):
    for item in timed_chars:
        if current_t >= item["appear_t"]:
            time_alive = current_t - item["appear_t"]
            x, y = item["pos"]
            
            if time_alive < SHINE_DURATION:
                for dx, dy in ((-1,0), (1,0), (0,-1), (0,1)):
                    draw_ctx.text((x + dx, y + dy), item["char"], font=font, fill=GOLD_GLOW_BACK)
                draw_ctx.text((x, y), item["char"], font=font, fill=GOLD_SHINE)
            else:
                draw_ctx.text((x, y), item["char"], font=font, fill=normal_color)

def prepare_sequential_ui(w, h, cfg_path, sans_dur, eng_dur, total_audio_duration):
    root_dir = Path(cfg_path).resolve().parent
    if root_dir.name.lower() == "cache":
        root_dir = root_dir.parent

    cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
    verse_data = cfg.get("verse", {})

    sloka_raw = verse_data.get("sanskrit", "").replace("\\n", "\n").strip()
    sanskrit_lines_raw = [l.strip() for l in sloka_raw.split("\n") if l.strip()]
    meaning = verse_data.get("meaning", "").strip()
    insight = verse_data.get("insight", "").strip()
    ch = str(verse_data.get("chapter", "1"))
    v = str(verse_data.get("verse_number", "1"))

    CREAM_WHITE = (245, 242, 235, 255)
    BODY_WHITE  = (230, 232, 236, 255)
    GOLD_ACCENT = (212, 175, 86, 255)
    CARD_BG     = (10, 14, 20, 220)
    CARD_BORDER = (212, 175, 86, 210)

    sanskrit_font_list = ["NotoSerifDevanagari-Bold.ttf", "NirmalaB.ttf", "mangal.ttf", "YatraOne-Regular.ttf"]
    title_font_list    = ["Cinzel-Bold.ttf", "TrajanPro-Bold.ttf", "timesbd.ttf", "georgiab.ttf"]
    body_font_list     = ["EBGaramond-Medium.ttf", "georgia.ttf", "calibri.ttf"]

    f_title      = load_font(title_font_list, FONT_SIZES["main_title"], root_dir)
    f_sub        = load_font(title_font_list, FONT_SIZES["sub_title"], root_dir)
    f_sanskrit   = load_font(sanskrit_font_list, FONT_SIZES["sanskrit_verse"], root_dir)
    f_sk_badge   = load_font(sanskrit_font_list, FONT_SIZES["sanskrit_badges"], root_dir)
    f_meaning_hd = load_font(title_font_list, FONT_SIZES["meaning_header"], root_dir)
    f_meaning    = load_font(body_font_list, FONT_SIZES["meaning_text"], root_dir)
    f_moment_hd  = load_font(title_font_list, FONT_SIZES["moment_header"], root_dir)
    f_moment     = load_font(body_font_list, FONT_SIZES["moment_text"], root_dir)

    PAD_Y = LAYOUT["box_padding_y"]
    PAD_X = LAYOUT["box_padding_x"]
    GAP   = LAYOUT["box_gap"]
    RAD   = LAYOUT["corner_radius"]
    CARD_L = LAYOUT["side_margin"]
    CARD_R = w - LAYOUT["side_margin"]
    MAX_TEXT_WIDTH = (CARD_R - CARD_L) - (PAD_X * 2)

    measure_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d_m = ImageDraw.Draw(measure_img)

    sanskrit_lines = wrap_text_to_width(sanskrit_lines_raw, f_sanskrit, MAX_TEXT_WIDTH, d_m)
    meaning_lines  = wrap_text_to_width(meaning, f_meaning, MAX_TEXT_WIDTH, d_m)
    moment_lines   = wrap_text_to_width(insight, f_moment, MAX_TEXT_WIDTH, d_m) if insight else []

    sanskrit_top_badge = "॥ श्रीमद्भगवद्गीता ॥"
    sanskrit_bottom_badge = f"अध्याय {ch} । श्लोक {v}"

    sk_total_h, sk_heights = measure_lines_height(d_m, sanskrit_lines, f_sanskrit, LAYOUT["sanskrit_line_spacing"])
    badge_top_h = d_m.textbbox((0, 0), sanskrit_top_badge, font=f_sk_badge)[3] - d_m.textbbox((0, 0), sanskrit_top_badge, font=f_sk_badge)[1]
    badge_bot_h = d_m.textbbox((0, 0), sanskrit_bottom_badge, font=f_sk_badge)[3] - d_m.textbbox((0, 0), sanskrit_bottom_badge, font=f_sk_badge)[1]
    b1_inner_gap = 20
    box1_h = PAD_Y + badge_top_h + b1_inner_gap + sk_total_h + b1_inner_gap + badge_bot_h + PAD_Y

    mean_total_h, mean_heights = measure_lines_height(d_m, meaning_lines, f_meaning, LAYOUT["meaning_line_spacing"])
    m_hd_h = d_m.textbbox((0, 0), "MEANING", font=f_meaning_hd)[3] - d_m.textbbox((0, 0), "MEANING", font=f_meaning_hd)[1]
    b2_inner_gap = 16
    box2_h = PAD_Y + m_hd_h + b2_inner_gap + mean_total_h + PAD_Y

    if moment_lines:
        mom_total_h, mom_heights = measure_lines_height(d_m, moment_lines, f_moment, LAYOUT["moment_line_spacing"])
        mom_hd_h = d_m.textbbox((0, 0), "THE MOMENT", font=f_moment_hd)[3] - d_m.textbbox((0, 0), "THE MOMENT", font=f_moment_hd)[1]
        b3_inner_gap = 16
        box3_h = PAD_Y + mom_hd_h + b3_inner_gap + mom_total_h + PAD_Y
    else:
        box3_h = 0

    box3_bot = h - LAYOUT["bottom_safe_area"]
    box3_top = box3_bot - box3_h

    box2_bot = (box3_top - GAP) if moment_lines else box3_bot
    box2_top = box2_bot - box2_h

    box1_bot = box2_top - GAP
    box1_top = box1_bot - box1_h

    min_top_allowed = 250
    if box1_top < min_top_allowed:
        shift_down = min_top_allowed - box1_top
        box1_top += shift_down
        box1_bot += shift_down
        box2_top += shift_down
        box2_bot += shift_down
        box3_top += shift_down
        box3_bot += shift_down

    sk_start_y = box1_top + PAD_Y + badge_top_h + b1_inner_gap
    sanskrit_chars_layout = compute_char_layout(sanskrit_lines, sk_start_y, sk_heights, LAYOUT["sanskrit_line_spacing"], f_sanskrit, d_m, canvas_width=w)

    mean_start_y = box2_top + PAD_Y + m_hd_h + b2_inner_gap
    meaning_chars_layout = compute_char_layout(meaning_lines, mean_start_y, mean_heights, LAYOUT["meaning_line_spacing"], f_meaning, d_m, canvas_width=w)

    if moment_lines:
        mom_start_y = box3_top + PAD_Y + mom_hd_h + b3_inner_gap
        moment_chars_layout = compute_char_layout(moment_lines, mom_start_y, mom_heights, LAYOUT["moment_line_spacing"], f_moment, d_m, canvas_width=w)
    else:
        moment_chars_layout = []

    t_border_fade_in = (0.5, 1.5)
    t_title_fade_in = (0.8, 1.8)
    t_box1_fade_in = (1.2, 2.0)
    
    sanskrit_voice_start = 2.0
    actual_sans_dur = max(2.5, sans_dur)
    sanskrit_voice_end = sanskrit_voice_start + actual_sans_dur
    
    t_box2_fade_in = (sanskrit_voice_end + 0.2, sanskrit_voice_end + 0.9)
    narration_voice_start = sanskrit_voice_end + 0.9
    actual_eng_dur = max(4.0, eng_dur)
    
    len_meaning = max(1, len(meaning_chars_layout))
    len_moment = len(moment_chars_layout)
    total_chars = len_meaning + len_moment

    if len_moment > 0:
        meaning_ratio = len_meaning / float(total_chars)
        meaning_audio_dur = actual_eng_dur * meaning_ratio
        moment_audio_dur = actual_eng_dur * (1.0 - meaning_ratio)
    else:
        meaning_audio_dur = actual_eng_dur
        moment_audio_dur = 0.0

    meaning_voice_end = narration_voice_start + meaning_audio_dur
    
    t_box3_fade_in = (meaning_voice_end + 0.1, meaning_voice_end + 0.8)
    moment_voice_start = meaning_voice_end + 0.8
    moment_voice_end = moment_voice_start + moment_audio_dur

    global_ui_fade_out_start = max(moment_voice_end + 1.0, total_audio_duration - 2.8)
    global_ui_fade_out_end = max(global_ui_fade_out_start + 1.2, total_audio_duration - 1.5)

    timed_sanskrit_chars = calculate_char_times(sanskrit_chars_layout, sanskrit_voice_start, sanskrit_voice_end)
    timed_meaning_chars  = calculate_char_times(meaning_chars_layout, narration_voice_start, meaning_voice_end)
    timed_moment_chars   = calculate_char_times(moment_chars_layout, moment_voice_start, moment_voice_end)

    border_img = draw_programmatic_gold_frame(w, h)

    header_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_3d_header(header_img, y_title=75, y_sub=165,
                   title_text="BHAGAVAD GITA", sub_text=f"CHAPTER {ch} • VERSE {v}",
                   f_title=f_title, f_sub=f_sub,
                   gold_color=GOLD_ACCENT, white_color=CREAM_WHITE)

    box1_container = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d_b1 = ImageDraw.Draw(box1_container)
    d_b1.rounded_rectangle([CARD_L, box1_top, CARD_R, box1_bot], radius=RAD, fill=CARD_BG, outline=CARD_BORDER, width=2)
    draw_centered_text(d_b1, box1_top + PAD_Y, sanskrit_top_badge, f_sk_badge, GOLD_ACCENT, canvas_width=w)
    draw_centered_text(d_b1, box1_bot - PAD_Y - badge_bot_h, sanskrit_bottom_badge, f_sk_badge, GOLD_ACCENT, canvas_width=w)

    box2_container = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d_b2 = ImageDraw.Draw(box2_container)
    d_b2.rounded_rectangle([CARD_L, box2_top, CARD_R, box2_bot], radius=RAD, fill=CARD_BG, outline=CARD_BORDER, width=2)
    draw_centered_text(d_b2, box2_top + PAD_Y, "MEANING", f_meaning_hd, GOLD_ACCENT, canvas_width=w)

    box3_container = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if moment_lines:
        d_b3 = ImageDraw.Draw(box3_container)
        d_b3.rounded_rectangle([CARD_L, box3_top, CARD_R, box3_bot], radius=RAD, fill=CARD_BG, outline=CARD_BORDER, width=2)
        draw_centered_text(d_b3, box3_top + PAD_Y, "THE MOMENT", f_moment_hd, GOLD_ACCENT, canvas_width=w)

    return {
        "w": w, "h": h,
        "f_sanskrit": f_sanskrit,
        "f_meaning": f_meaning,
        "f_moment": f_moment,
        "CREAM_WHITE": CREAM_WHITE,
        "BODY_WHITE": BODY_WHITE,
        "border_img": border_img,
        "header_img": header_img,
        "box1_container": box1_container,
        "box2_container": box2_container,
        "box3_container": box3_container,
        "t_border_fade_in": t_border_fade_in,
        "t_title_fade_in": t_title_fade_in,
        "t_box1_fade_in": t_box1_fade_in,
        "t_box2_fade_in": t_box2_fade_in,
        "t_box3_fade_in": t_box3_fade_in,
        "global_ui_fade_out": (global_ui_fade_out_start, global_ui_fade_out_end),
        "timed_sanskrit_chars": timed_sanskrit_chars,
        "timed_meaning_chars": timed_meaning_chars,
        "timed_moment_chars": timed_moment_chars
    }

# ==============================================================================
# 🌌 CONTINUOUS 3D DEPTH DISPLACEMENT ENGINE
# ==============================================================================

def render_master_video(images, out, master_audio_path, w=1080, h=1920, fps=30, cfg_path=None, font_path=None, sans_dur=0.0, eng_dur=0.0):
    audio_duration = get_audio_duration(master_audio_path)
    if audio_duration <= 0.0:
        audio_duration = 38.0
        
    total_video_frames = int(audio_duration * fps)
    
    if not images:
        raise ValueError("No images provided for rendering.")
        
    frames_per_image = total_video_frames // len(images)
    remainder_frames = total_video_frames % len(images)

    ui = prepare_sequential_ui(w, h, cfg_path, sans_dur, eng_dur, audio_duration)

    camera_trajectories = [
        {"name": "orbit_right", "dx": 28.0, "dy": -12.0, "zoom_st": 1.04, "zoom_en": 1.14},
        {"name": "orbit_left",  "dx": -28.0, "dy": 12.0, "zoom_st": 1.05, "zoom_en": 1.15},
        {"name": "dolly_deep",  "dx": 0.0,   "dy": -18.0, "zoom_st": 1.02, "zoom_en": 1.18},
        {"name": "ascend_flow", "dx": 16.0,  "dy": 22.0,  "zoom_st": 1.06, "zoom_en": 1.16}
    ]

    # Precompute 2D coordinate grid for instant GPU/CPU continuous mesh remapping
    grid_x, grid_y = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))

    def run_render_loop(selected_encoder):
        fade_out_start = max(0.0, audio_duration - 2.5)
        vf_filter = f"fade=t=in:st=0:d=1.5,fade=t=out:st={fade_out_start}:d=2.5"

        cmd = [
            ffmpeg(), '-y', '-f', 'rawvideo', '-vcodec', 'rawvideo',
            '-s', f'{w}x{h}', '-pix_fmt', 'bgr24', '-r', str(fps),
            '-i', '-', '-c:v', selected_encoder,
            '-vf', vf_filter
        ]
        
        if selected_encoder == "libx264":
            cmd += ["-preset", "veryfast", "-crf", "18", "-threads", "0"]
        elif selected_encoder == "h264_mf":
            cmd += ["-b:v", "8M"]
        elif selected_encoder == "h264_nvenc":
            cmd += ["-preset", "p4", "-b:v", "8M"]
        elif selected_encoder == "h264_qsv":
            cmd += ["-preset", "fast", "-global_quality", "20"]
        else:
            cmd += ["-b:v", "6M"]
            
        cmd += ["-pix_fmt", "yuv420p", str(out)]
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        
        try:
            global_frame = 0
            for img_idx, image_path in enumerate(images):
                img_path = Path(image_path).resolve()
                
                project_root = img_path.parent.parent.parent if img_path.parent.name == "images" else img_path.parent.parent
                depth_path = project_root / "depth" / f"{img_path.stem}.png"
                
                img = cv2.imread(str(img_path))
                if img is None: 
                    continue

                orig_h, orig_w = img.shape[:2]
                aspect_img = orig_w / float(orig_h)
                aspect_target = w / float(h)
                
                if aspect_img > aspect_target:
                    new_w = int(orig_h * aspect_target)
                    offset = (orig_w - new_w) // 2
                    img_cropped = img[:, offset:offset+new_w]
                    depth_slice = (slice(None), slice(offset, offset+new_w))
                else:
                    new_h = int(orig_w / aspect_target)
                    offset = (orig_h - new_h) // 2
                    img_cropped = img[offset:offset+new_h, :]
                    depth_slice = (slice(offset, offset+new_h), slice(None))
                    
                img_resized = cv2.resize(img_cropped, (w, h), interpolation=cv2.INTER_CUBIC)

                # Continuous Depth Field Normalization
                has_continuous_depth = False
                depth_norm = None
                if depth_path.exists():
                    depth_raw = cv2.imread(str(depth_path), cv2.IMREAD_GRAYSCALE)
                    if depth_raw is not None:
                        depth_cropped = depth_raw[depth_slice]
                        depth_u8 = cv2.resize(depth_cropped, (w, h), interpolation=cv2.INTER_CUBIC)
                        
                        # Continuous normalized 3D displacement field [-0.5 to +0.5]
                        depth_norm = (cv2.GaussianBlur(depth_u8, (7, 7), 0).astype(np.float32) / 255.0) - 0.5
                        has_continuous_depth = True

                cx, cy = w / 2.0, h / 2.0
                traj = camera_trajectories[img_idx % len(camera_trajectories)]
                
                current_frames = frames_per_image
                if img_idx == len(images) - 1:
                    current_frames += remainder_frames 
                    
                for i in range(current_frames):
                    t = i / float(current_frames)
                    # Smooth sinusoidal kinematics
                    smooth_t = 0.5 * (1.0 - math.cos(math.pi * t))
                    
                    if has_continuous_depth:
                        # Vector displacement along trajectory
                        cam_x = traj["dx"] * math.sin(math.pi * smooth_t)
                        cam_y = traj["dy"] * math.sin(math.pi * smooth_t)
                        current_zoom = traj["zoom_st"] + (traj["zoom_en"] - traj["zoom_st"]) * smooth_t

                        # 3D Coordinate Ray Displacement Remap
                        map_x = ((grid_x - cx) / current_zoom + cx) + (depth_norm * cam_x)
                        map_y = ((grid_y - cy) / current_zoom + cy) + (depth_norm * cam_y)

                        comp = cv2.remap(img_resized, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101).astype(np.float32)
                    else:
                        zoom = 1.02 + (0.08 * t)
                        M = cv2.getRotationMatrix2D((cx, cy), 0, zoom)
                        comp = cv2.warpAffine(img_resized, M, (w, h), borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
                    
                    current_time_sec = global_frame / fps
                    
                    fo_st, fo_end = ui["global_ui_fade_out"]
                    if current_time_sec >= fo_end:
                        global_fade = 0.0
                    elif current_time_sec >= fo_st:
                        global_fade = 1.0 - ((current_time_sec - fo_st) / (fo_end - fo_st))
                    else:
                        global_fade = 1.0

                    if global_fade > 0.0:
                        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                        d_over = ImageDraw.Draw(overlay)

                        b_st, b_en = ui["t_border_fade_in"]
                        if current_time_sec >= b_st:
                            alpha_border = min(1.0, (current_time_sec - b_st) / (b_en - b_st))
                            if alpha_border > 0:
                                b_arr = np.array(ui["border_img"]).copy()
                                b_arr[:, :, 3] = (b_arr[:, :, 3].astype(np.float32) * alpha_border).astype(np.uint8)
                                overlay.alpha_composite(Image.fromarray(b_arr))

                        t_st, t_en = ui["t_title_fade_in"]
                        if current_time_sec >= t_st:
                            alpha_title = min(1.0, (current_time_sec - t_st) / (t_en - t_st))
                            if alpha_title > 0:
                                head_arr = np.array(ui["header_img"]).copy()
                                head_arr[:, :, 3] = (head_arr[:, :, 3].astype(np.float32) * alpha_title).astype(np.uint8)
                                overlay.alpha_composite(Image.fromarray(head_arr))

                        b1_st, b1_en = ui["t_box1_fade_in"]
                        if current_time_sec >= b1_st:
                            alpha_b1 = min(1.0, (current_time_sec - b1_st) / (b1_en - b1_st))
                            if alpha_b1 > 0:
                                b1_arr = np.array(ui["box1_container"]).copy()
                                b1_arr[:, :, 3] = (b1_arr[:, :, 3].astype(np.float32) * alpha_b1).astype(np.uint8)
                                overlay.alpha_composite(Image.fromarray(b1_arr))

                        render_karaoke_chars(d_over, ui["timed_sanskrit_chars"], current_time_sec, ui["f_sanskrit"], ui["CREAM_WHITE"])

                        b2_st, b2_en = ui["t_box2_fade_in"]
                        if current_time_sec >= b2_st:
                            alpha_b2 = min(1.0, (current_time_sec - b2_st) / (b2_en - b2_st))
                            if alpha_b2 > 0:
                                b2_arr = np.array(ui["box2_container"]).copy()
                                b2_arr[:, :, 3] = (b2_arr[:, :, 3].astype(np.float32) * alpha_b2).astype(np.uint8)
                                overlay.alpha_composite(Image.fromarray(b2_arr))

                        render_karaoke_chars(d_over, ui["timed_meaning_chars"], current_time_sec, ui["f_meaning"], ui["BODY_WHITE"])

                        b3_st, b3_en = ui["t_box3_fade_in"]
                        if current_time_sec >= b3_st:
                            alpha_b3 = min(1.0, (current_time_sec - b3_st) / (b3_en - b3_st))
                            if alpha_b3 > 0:
                                b3_arr = np.array(ui["box3_container"]).copy()
                                b3_arr[:, :, 3] = (b3_arr[:, :, 3].astype(np.float32) * alpha_b3).astype(np.uint8)
                                overlay.alpha_composite(Image.fromarray(b3_arr))

                        render_karaoke_chars(d_over, ui["timed_moment_chars"], current_time_sec, ui["f_moment"], ui["BODY_WHITE"])

                        over_arr = np.array(overlay)
                        over_bgr = cv2.cvtColor(over_arr, cv2.COLOR_RGBA2BGR).astype(np.float32)
                        over_alpha = (over_arr[:, :, 3:4].astype(np.float32) / 255.0) * global_fade
                        comp = (comp * (1.0 - over_alpha)) + (over_bgr * over_alpha)

                    frame = np.clip(comp, 0, 255).astype(np.uint8)
                    process.stdin.write(frame.tobytes())
                    global_frame += 1

            process.stdin.close()
            process.communicate()
            if process.returncode != 0:
                raise RuntimeError(f"FFmpeg exit code {process.returncode}")
                
        except Exception as e:
            process.kill()
            process.communicate()
            if Path(out).exists(): 
                Path(out).unlink()
            raise RuntimeError(str(e))

    pref_enc = encoder()
    try:
        print(f"  [VIDEO] Executing fast 3D render with {pref_enc} (Continuous 3D Parallax Warp)...")
        run_render_loop(pref_enc)
    except Exception:
        if pref_enc != "libx264":
            print(f"  [WARNING] Hardware encoder busy. Engaging CPU multi-thread fallback (libx264)...")
            if Path(out).exists(): 
                Path(out).unlink()
            run_render_loop("libx264")
        else:
            raise

def mux(video, audio, out):
    subprocess.run([
        ffmpeg(), "-y",
        "-i", str(video),
        "-i", str(audio),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "256k",
        str(out)
    ], check=True)