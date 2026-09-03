import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables (.env file for API keys and tokens)
load_dotenv()

# Ensure repository root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.pipeline import run_pipeline

def main():
    print("=" * 60)
    print("   BLACKLINES ART STUDIO: GITA AUTOMATION v20   ")
    print("=" * 60)
    
    fast_render = "--fast" in sys.argv
    
    try:
        run_pipeline(root=PROJECT_ROOT, fast_mode=fast_render)
        print("\n[MASTER] Execution finished successfully.")
    except KeyboardInterrupt:
        print("\n[MASTER] Process interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print(f"\n[CRITICAL ERROR] Pipeline execution halted: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
