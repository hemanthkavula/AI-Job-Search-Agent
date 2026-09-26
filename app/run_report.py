from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent

def latest_summary():
    rows=sorted((ROOT/"generated/cycles").glob("*_summary.json"))
    if not rows: raise SystemExit("No production summary found")
    return rows[-1]

def build(summary_path=None):
    path=Path(summary_path) if summary_path else latest_summary()
    s=json.loads(path.read_text(encoding="utf-8"))
    units=s.get("source_unit_status") or {}
    by_provider={}
    for _,row in units.items():
        if isinstance(row,str):
            provider,_,company=_.partition(":")
            row={"source":provider,"company":company,"status":row,"jobs_returned":0}
        p=row.get("source") or "unknown"
        by_provider.setdefault(p,[]).append(row)
    lines=[f"# Production Source Report — {s.get('cycle_id','unknown')}","",
      "## Cycle totals","",
      f"- Discovered jobs: **{s.get('discovered',0)}**",
      f"- Preliminary eligible: **{s.get('preliminary_eligible',0)}**",
      f"- Final JD verified: **{s.get('final_jd_verified',0)}**",
      f"- READY_TO_APPLY: **{s.get('ready_to_apply',0)}**","",
      "## Coverage",""]
    cov=s.get("coverage") or {}
    for k,v in cov.items():
        if k!="configured_units_by_provider": lines.append(f"- {k.replace('_',' ').title()}: **{v}**")
    lines+=["","## ATS, career-site and job-board execution","",
      "| Provider | Attempted units | OK | Failed | Skipped | Jobs returned |",
      "|---|---:|---:|---:|---:|---:|"]
    for p,rows in sorted(by_provider.items()):
        lines.append(f"| {p} | {len(rows)} | {sum(x.get('status')=='OK' for x in rows)} | {sum(x.get('status')=='ERROR' for x in rows)} | {sum(x.get('status')=='SKIPPED_UNHEALTHY' for x in rows)} | {sum(int(x.get('jobs_returned') or 0) for x in rows)} |")
    lines+=["","## Every company / tenant / board attempted","",
      "| Provider | Company / tenant | Status | Jobs returned | Failure / note |",
      "|---|---|---|---:|---|"]
    for p,rows in sorted(by_provider.items()):
        for x in sorted(rows,key=lambda z:str(z.get("company") or "").lower()):
            err=str(x.get("error") or "").replace("|","\\|").replace("\n"," ")
            lines.append(f"| {p} | {x.get('company') or ''} | {x.get('status') or ''} | {x.get('jobs_returned',0)} | {err} |")
    configured=cov.get("configured_units_by_provider") or {}
    lines+=["","## Configured provider universe","",
      "| Provider | Configured units | Cycle status |",
      "|---|---:|---|"]
    statuses=s.get("source_status") or {}
    for p,n in sorted(configured.items()):
        lines.append(f"| {p} | {n} | {statuses.get(p,'NOT_ATTEMPTED_OR_DISABLED')} |")
    text="\n".join(lines)+"\n"
    out=path.with_name(path.name.replace("_summary.json","_source_report.md"))
    out.write_text(text,encoding="utf-8")
    return out

if __name__=="__main__":
    print(build())
