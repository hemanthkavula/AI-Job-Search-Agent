import argparse,json
from pathlib import Path
from app.orchestrator import process_job

ap=argparse.ArgumentParser()
ap.add_argument("--job",required=True,help="Path to normalized job JSON")
ap.add_argument("--min-score",type=int,default=70)
args=ap.parse_args()
raw=json.loads(Path(args.job).read_text(encoding="utf-8"))
print(json.dumps(process_job(raw,args.min_score),indent=2))
