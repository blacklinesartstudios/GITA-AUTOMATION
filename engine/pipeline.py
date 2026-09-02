import math
from pathlib import Path
from PIL import ImageDraw, ImageFont

def get_font(project_root: Path, font_name: str, size: int):
    """Robust font loader utilizing project assets."""
    project_root = Path(project_root).resolve()
    font_path = project_root / "assets" / "fonts" / font_name
    if font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception:
            pass
    for fallback in ["Cinzel-Bold.ttf", "NotoSerifDevanagari-Bold.ttf", "gita_font.ttf"]:
        alt_path = project_root / "assets" / "fonts" / fallback
        if alt_path.exists():
            try:
                return ImageFont.truetype(str(alt_path), size)
            except Exception:
                continue
    return ImageFont.load_default()

def prepare_timed_captions(narration_text: str, total_audio_duration: float, words_per_chunk: int = 4):
    """
    Splits narration into rhythmic chunks and assigns precise start/end time windows 
    proportional to the total audio duration.
    """
    words = narration_text.split()
    if not words:
        return []

    chunks = []
    for i in range(0, len(words), words_per_chunk):
        chunk_words = words[i:i + words_per_chunk]
        chunks.append(" ".join(chunk_words))

    # Calculate time per chunk evenly across the total audio duration
    time_per_chunk = total_audio_duration / max(len(chunks), 1)

    timed_captions = []
    for idx, chunk in enumerate(chunks):
        start_time = idx * time_per_chunk
        end_time = (idx + 1) * time_per_chunk
        timed_captions.append({
            "text": chunk,
            "start": start_time,
            "end": end_time
        })

    return timed_captions

def render_synced_caption_frame(
    draw: ImageDraw.ImageDraw,
    project_root: Path,
    current_time: float,
    timed_captions: list,
    width: int,
    height: int
):
    """
    Identifies which caption chunk matches the current video timestamp 
    and renders it with a glowing active highlight effect.
    """
    font_caption = get_font(project_root, "Cinzel-Bold.ttf", 32)
    
    active_text = ""
    for cap in timed_captions:
        if cap["start"] <= current_time <= cap["end"]:
            active_text = cap["text"]
            break

    if not active_text:
        # Fallback to last caption if slightly over time
        if timed_captions and current_time > timed_captions[-1]["end"]:
            active_text = timed_captions[-1]["text"]
        else:
            return

    # Position captions near the lower third of the vertical short screen
    x = width // 2
    y = int(height * 0.75)

    # Draw subtle background shadow/stroke for high readability
    offset = 2
    for dx, dy in [(-offset, 0), (offset, 0), (0, -offset), (0, offset)]:
        draw.text((x + dx, y + dy), active_text, font=font_caption, fill=(0, 0, 0), anchor="mm")

    # Draw main active glowing text (Gold/White highlight matching Gita aesthetic)
    draw.text((x, y), active_text, font=font_caption, fill=(255, 215, 0), anchor="mm")
