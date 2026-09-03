import json
from pathlib import Path

# Canonical Gita verse counts per chapter
GITA_CHAPTER_VERSES = {
    1: 47, 2: 72, 3: 43, 4: 42, 5: 29, 6: 47,
    7: 30, 8: 28, 9: 34, 10: 42, 11: 55, 12: 20,
    13: 35, 14: 27, 15: 20, 16: 24, 17: 28, 18: 78
}

def get_tracker_file(root_dir: Path) -> Path:
    tracker_path = root_dir / "state.json"
    if not tracker_path.exists():
        tracker_path.write_text(json.dumps({"chapter": 1, "verse": 1}, indent=4), encoding="utf-8")
    return tracker_path

def get_current_state(root_dir: Path) -> dict:
    t_file = get_tracker_file(root_dir)
    try:
        data = json.loads(t_file.read_text(encoding="utf-8"))
        return {"chapter": int(data.get("chapter", 1)), "verse": int(data.get("verse", 1))}
    except Exception:
        return {"chapter": 1, "verse": 1}

def advance_tracker(root_dir: Path):
    """Advances sequentially: Ch 1 V 1 -> Ch 1 V 2 ... -> Ch 2 V 1."""
    t_file = get_tracker_file(root_dir)
    state = get_current_state(root_dir)
    ch = state["chapter"]
    v = state["verse"]

    max_v = GITA_CHAPTER_VERSES.get(ch, 47)
    if v < max_v:
        v += 1
    else:
        if ch < 18:
            ch += 1
            v = 1
        else:
            print("[INFO] Complete 700 verses finished! Resetting to Chapter 1, Verse 1.")
            ch = 1
            v = 1

    new_state = {"chapter": ch, "verse": v}
    t_file.write_text(json.dumps(new_state, indent=4), encoding="utf-8")
    print(f"[TRACKER] Advanced state to -> Chapter {ch}, Verse {v}")