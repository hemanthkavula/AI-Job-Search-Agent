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
    reasons=s.get("filter_reason_counts") or {}
    lines=[f"# Production Source Report — {s.get('cycle_id','unknown')}","",
      "## Cycle funnel","",
      f"- Discovered jobs: **{s.get('discovered',0)}**",
      f"- Fresh inside production window: **{s.get('fresh_verified_within_window',0)}**",
      f"- Older / unverified: **{s.get('older_or_unverified',0)}**",
      f"- Filtered before final JD verification: **{s.get('filtered_out',0)}**",
      f"- Preliminary eligible: **{s.get('preliminary_eligible',0)}**",
      f"- Final JD verified: **{s.get('final_jd_verified',0)}**",
      f"- Held / rejected at final gate: **{s.get('held_or_rejected',0)}**",
      f"- READY_TO_APPLY: **{s.get('ready_to_apply',0)}**","",
      "## Eligibility rejection counts","",
      f"- Wrong job family: **{reasons.get('wrong_job_family',0)}**",
      f"- Experience mismatch: **{reasons.get('experience_mismatch',0)}**",
      f"- Other hard filter: **{reasons.get('other_hard_filter',0)}**",
      f"- Already processed: **{reasons.get('already_processed_ledger',0)}**",
      f"- Duplicates removed: **{reasons.get('duplicates_removed',0)}**","",
      "## Coverage",""]
    cov=s.get("coverage") or {}
    for k,v in cov.items():
        if k!="configured_units_by_provider": lines.append(f"- {k.replace('_',' ').title()}: **{v}**")
    lines+=["","## ATS, career-site and job-board execution","",
      "| Provider | Attempted units | OK | Failed | Hard-skipped | Jobs returned |",
      "|---|---:|---:|---:|---:|---:|"]
    for p,rows in sorted(by_provider.items()):
        hard_skipped=sum(x.get('status') in {'SKIPPED_UNHEALTHY','SKIPPED_HARD_FAILURE'} for x in rows)
        lines.append(f"| {p} | {len(rows)} | {sum(x.get('status')=='OK' for x in rows)} | {sum(x.get('status')=='ERROR' for x in rows)} | {hard_skipped} | {sum(int(x.get('jobs_returned') or 0) for x in rows)} |")
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

    # Make disabled broad-discovery boards explicit so "zero jobs" is never
    # confused with "the board was searched successfully and found none".
    source_cfg=_json(ROOT/"data"/"job_sources.json",{})
    disabled=[]
    for row in source_cfg.get("discovery_portal",[]) or []:
        if isinstance(row,dict) and not row.get("enabled",True):
            disabled.append((row.get("provider") or "unknown",row.get("disabled_reason") or "disabled"))
    monster=source_cfg.get("monster") or {}
    if isinstance(monster,dict) and not monster.get("enabled",False):
        disabled.append(("monster",monster.get("disabled_reason") or "disabled"))
    if disabled:
        lines+=["","## Disabled broad-discovery sources","",
          "| Provider | Reason |","|---|---|"]
        for provider,reason in sorted(disabled):
            lines.append(f"| {provider} | {str(reason).replace('|','\\|')} |")
    text="\n".join(lines)+"\n"
    out=path.with_name(path.name.replace("_summary.json","_source_report.md"))
    out.write_text(text,encoding="utf-8")
    return out

if __name__=="__main__":
    print(build())
