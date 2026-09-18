from __future__ import annotations
import argparse,json
from pathlib import Path
from app.jd_finalizer import resolve_full_jd

def _jobs(payload):
    if isinstance(payload,list): return payload
    if not isinstance(payload,dict): return []
    rows=[]
    for key in ("results","rejections","hard_filter_rejections"):
        for item in payload.get(key,[]) or []:
            job=item.get("job") if isinstance(item,dict) else None
            if isinstance(job,dict): rows.append(job)
    return rows

def _match(job,external_id=None,title=None,company=None):
    if external_id and job.get("external_id")!=external_id:return False
    if title and title.lower() not in (job.get("title") or "").lower():return False
    if company and company.lower() not in (job.get("company_key") or job.get("company") or "").lower():return False
    return True

def main():
    p=argparse.ArgumentParser(description="Free targeted full-JD/ATS resolver test; never calls the resume LLM.")
    p.add_argument("--report",required=True)
    p.add_argument("--external-id")
    p.add_argument("--title")
    p.add_argument("--company")
    p.add_argument("--output")
    a=p.parse_args()
    payload=json.loads(Path(a.report).read_text(encoding="utf-8"))
    matches=[j for j in _jobs(payload) if _match(j,a.external_id,a.title,a.company)]
    if not matches:
        print("No matching job found in report.");return 2
    if len(matches)>1 and not a.external_id:
        print(f"{len(matches)} jobs matched. Narrow with --external-id or a more specific --title/--company.")
        for j in matches[:20]:print(f"  {j.get('external_id')} | {j.get('company_key')} | {j.get('title')}")
        return 2
    original=matches[0];resolved=resolve_full_jd(original)
    result={
      "external_id":resolved.get("external_id"),"company":resolved.get("company_key") or resolved.get("company"),
      "title":resolved.get("title"),"source":resolved.get("source"),
      "discovery_url":original.get("url"),"original_url":resolved.get("original_url"),
      "ats_provider":resolved.get("ats_provider"),"ats_identifier":resolved.get("ats_identifier"),
      "ats_resolution":resolved.get("ats_resolution"),"description_length":resolved.get("description_length",len(resolved.get("description") or "")),
      "description_complete":bool(resolved.get("description_complete")),"jd_signal_score":resolved.get("jd_signal_score"),
      "jd_resolution_source":resolved.get("jd_resolution_source"),
    }
    print(json.dumps(result,indent=2))
    if a.output:
        out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(resolved,indent=2),encoding="utf-8");print(f"Saved resolved job to {out}")
    return 0 if result["description_complete"] else 1

if __name__=="__main__":
    raise SystemExit(main())
