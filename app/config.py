from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = ROOT / "data" / "candidate_profile.json"

def load_profile() -> dict:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
