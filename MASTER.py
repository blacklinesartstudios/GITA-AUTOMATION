from pathlib import Path
import sys, json, traceback

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine.preflight import run_preflight
from engine.pipeline import run_pipeline

def main():
    print("\n=== GITA YOUTUBE AUTO V6 ===\n")
    fast_mode = "--fast" in sys.argv
    if fast_mode:
        print("[MODE] >>> Running Fast Test Render (1080p @ 24fps ultrafast) <<<\n")

    try:
        cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        
        ok, report = run_preflight(ROOT, cfg)
        print(report)
        if not ok:
            print("\nPREFLIGHT FAILED. Fix the items above and run again.")
            return 2
        
        run_pipeline(ROOT, cfg, fast_mode=fast_mode)
        
        print("\nDONE.")
        return 0
    except KeyboardInterrupt:
        print("\nStopped.")
        return 130
    except Exception:
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    raise SystemExit(main())