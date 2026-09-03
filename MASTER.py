import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables (for local runs or GitHub Secrets)
load_dotenv()

# Ensure project root is in python path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(PROJECT_ROOT))

from engine.pipeline import run_pipeline

def main():
    print("==================================================")
    print("   BLACKLINES ART STUDIO: GITA AUTOMATION v20   ")
    print("==================================================")
    
    # Configuration dictionary for the studio pipeline
    config = {
        "youtube_playlist_id": os.getenv("YOUTUBE_PLAYLIST_ID", "PL_ENGLISH_VERSION_ID_HERE"),
        "fast_mode": False
    }

    try:
        # Execute the main sequential rollout pipeline
        run_pipeline(root=PROJECT_ROOT, cfg=config)
        print("\n[MASTER] Pipeline execution completed successfully!")
    except Exception as e:
        print(f"\n[MASTER ERROR] Pipeline failed with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
