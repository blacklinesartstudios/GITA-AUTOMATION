from pathlib import Path
from PIL import ImageFont, ImageDraw, Image

def get_font(project_root: Path, font_name: str, size: int):
    """
    Robust font loader with fallback safety for Devanagari and Title typography.
    """
    project_root = Path(project_root).resolve()
    font_path = project_root / "assets" / "fonts" / font_name
    
    if font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception:
            pass
            
    # Fallback options
    for fallback in ["NotoSerifDevanagari-Bold.ttf", "Cinzel-Bold.ttf", "gita_font.ttf"]:
        alt_path = project_root / "assets" / "fonts" / fallback
        if alt_path.exists():
            try:
                return ImageFont.truetype(str(alt_path), size)
            except Exception:
                continue
                
    return ImageFont.load_default()

def render_verse_text(draw: ImageDraw.ImageDraw, project_root: Path, sanskrit_text: str, title_text: str, width: int, height: int):
    """
    Renders Sanskrit and title text using proper Devanagari and serif fonts.
    """
    # Load fonts using your robust utility
    font_sanskrit = get_font(project_root, "NotoSerifDevanagari-Bold.ttf", 40)
    font_title = get_font(project_root, "Cinzel-Bold.ttf", 36)

    # Example layout rendering position (adjust coordinates as per your vertical short layout)
    # Drawing Title
    draw.text((width // 2, 150), title_text, font=font_title, fill=(255, 215, 0), anchor="mm")

    # Drawing Sanskrit Verse with Devanagari support
    # Note: Pillow handles Unicode Devanagari strings directly when paired with NotoSerifDevanagari
    draw.text((width // 2, 350), sanskrit_text, font=font_sanskrit, fill=(255, 255, 255), anchor="mm")
