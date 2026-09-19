from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

from app.job_ledger import compact_ledger, load_ledger, save_ledger

ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/"generated"/"job_ledger.json"

def main():
    ap=argparse.ArgumentParser(description="Compact the job ledger without changing deduplication or application state.")
    ap.add_argument("--ledger",default=str(DEFAULT))
    ap.add_argument("--apply",action="store_true",help="Write the compacted ledger after creating a timestamped backup.")
    args=ap.parse_args()
    path=Path(args.ledger)
    ledger=load_ledger(path)
    compacted,stats=compact_ledger(ledger)
    before=len(json.dumps(ledger,indent=2).encode("utf-8"))
    after=len(json.dumps(compacted,indent=2).encode("utf-8"))
    result={**stats,"before_bytes":before,"after_bytes":after,"saved_bytes":before-after,"applied":False}
    if args.apply:
        stamp=datetime.now().strftime("%Y%m%dT%H%M%S")
        backup=path.with_name(f"{path.stem}.backup-{stamp}{path.suffix}")
        shutil.copy2(path,backup)
        save_ledger(compacted,path)
        result["applied"]=True
        result["backup"]=str(backup)
    print(json.dumps(result,indent=2))

if __name__=="__main__":
    main()
