from __future__ import annotations
import argparse, json
from pathlib import Path
from app.sources.career_site import validate_source

ROOT=Path(__file__).resolve().parents[1]

def run(path: str="data/job_sources.json", timeout: int=12) -> dict:
    cfg=json.loads((ROOT/path).read_text(encoding="utf-8"))
    rows=[validate_source(x["company"],x["search_url"],x["job_url_pattern"],timeout)
          for x in cfg.get("career_site",[])]
    counts={}
    for row in rows: counts[row["status"]]=counts.get(row["status"],0)+1
    return {"counts":counts,"sources":rows}

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--sources",default="data/job_sources.json")
    p.add_argument("--timeout",type=int,default=12)
    p.add_argument("--output",default="generated/source_health.json")
    a=p.parse_args()
    report=run(a.sources,a.timeout)
    out=ROOT/a.output; out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report["counts"],indent=2))
    for r in report["sources"]:
        if r["status"]!="ok" or r.get("matching_job_links",0)==0:
            print(f'{r["status"]:22} {r["company"]}: {r["search_url"]} links={r.get("matching_job_links","?")} http={r.get("http_status")}')
    print(f"Saved report to {out}")
