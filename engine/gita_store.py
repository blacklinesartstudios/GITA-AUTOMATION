import json
from pathlib import Path

def get_verse_from_dataset(chapter: int, verse: int, project_root: Path) -> dict:
    """
    Fetches the canonical Sanskrit shloka, translation, and structured
    dialogue directly from the local offline master JSON.
    """
    gita_file = project_root / "assets" / "gita" / "bhagavad_gita.json"
    if not gita_file.exists():
        raise FileNotFoundError(f"Missing master Gita dataset at {gita_file}")

    data = json.loads(gita_file.read_text(encoding="utf-8"))
    target_id = f"BG_{chapter:02d}_{verse:02d}"

    for item in data:
        if item.get("id") == target_id:
            return item

    # Fallback search by chapter & verse integers
    for item in data:
        if item.get("chapter") == chapter and item.get("verse") == verse:
            return item

    raise KeyError(f"Verse not found: Chapter {chapter}, Verse {verse}")