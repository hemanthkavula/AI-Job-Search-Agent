from __future__ import annotations
import argparse,json
from pathlib import Path
from datetime import datetime

def build(manifest_path="generated/application_manifest.json", output="generated/evening_report.md"):
    p=Path(manifest_path); rows=json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    applied=[r for r in rows if r.get("application_status")=="SUBMITTED"]
    ready=[r for r in rows if r.get("next_action")=="READY_TO_APPLY"]
    held=[r for r in rows if r.get("next_action")=="HOLD_ATS_REVIEW"]
    lines=[f"# Job Automation Report — {datetime.now().strftime('%Y-%m-%d')}","",f"- Prepared: {len(rows)}",f"- Submitted: {len(applied)}",f"- Ready to apply: {len(ready)}",f"- Held for ATS review: {len(held)}","",
           "| Company | Role | ATS | Sponsorship | Status | Resume |","|---|---|---:|---|---|---|"]
    for r in rows:
        a=r.get("ats_audit",{}); s=r.get("sponsorship",{}).get("category","")
        lines.append(f"| {r.get('company','')} | {r.get('title','')} | {a.get('internal_ats_score','')} | {s} | {r.get('application_status') or r.get('next_action','')} | {r.get('pdf_path') or r.get('resume_path','')} |")
    out=Path(output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text("\n".join(lines),encoding="utf-8");return out
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--manifest",default="generated/application_manifest.json");ap.add_argument("--output",default="generated/evening_report.md");a=ap.parse_args();print(build(a.manifest,a.output))
