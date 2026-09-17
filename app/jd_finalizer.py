from __future__ import annotations
import html,json,re
from pathlib import Path
from urllib import request
from app.config import load_profile
from app.eligibility import two_category_filter
from app.filters import passes_hard_filters

MIN_COMPLETE_JD_CHARS=1200

def _clean_html(text):
    text=re.sub(r"(?is)<(script|style).*?>.*?</\1>"," ",text or "")
    text=re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h[1-6]>","\n",text)
    text=re.sub(r"(?s)<[^>]+>"," ",text)
    text=html.unescape(text).replace("\xa0"," ")
    return re.sub(r"[ \t]+"," ",re.sub(r"\n\s*\n+","\n",text)).strip()

def _fetch_public_page(url):
    if not url:return ""
    req=request.Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; AI-Job-Search-Agent/1.0)"})
    try:
        with request.urlopen(req,timeout=30) as resp:return resp.read().decode("utf-8",errors="replace")
    except Exception:return ""

def _extract_dice(page):
    plain=_clean_html(page)
    start=re.search(r"(?i)\bJob Description\b",plain)
    if start:plain=plain[start.start():]
    end=re.search(r"(?i)\b(?:Similar Jobs|Create a job alert|Dice Id:)\b",plain)
    if end and end.start()>MIN_COMPLETE_JD_CHARS:plain=plain[:end.start()]
    return plain

def resolve_full_jd(job):
    """Resolve full JD only after lightweight eligibility. Never calls an LLM."""
    current=(job.get("description") or "").strip()
    if job.get("description_complete") and len(current)>=MIN_COMPLETE_JD_CHARS:return job
    source=(job.get("source") or "").lower()
    page=_fetch_public_page(job.get("url"))
    resolved=_extract_dice(page) if source=="dice" else _clean_html(page)
    out=dict(job)
    if len(resolved)>len(current):out["description"]=resolved
    final=(out.get("description") or "").strip()
    out["description_length"]=len(final)
    out["description_complete"]=len(final)>=MIN_COMPLETE_JD_CHARS
    out["jd_resolution_source"]="public_job_detail_page" if len(resolved)>len(current) else "source_payload"
    return out

def finalize_report(report_path,output_path="generated/finalized_jobs.json"):
    report=json.loads(Path(report_path).read_text(encoding="utf-8"));profile=load_profile()
    finalized=[];held=[]
    for item in report.get("results",[]):
        if item.get("action")!="ELIGIBLE_FOR_RESUME":continue
        raw=resolve_full_jd(item["job"])
        if not raw.get("description_complete"):
            held.append({"job":raw,"action":"HOLD_INCOMPLETE_JD","reason":"Complete JD could not be resolved; no resume will be generated."});continue
        eligibility=two_category_filter(raw,profile);ok,reasons=passes_hard_filters(raw,profile)
        if not eligibility.get("eligible") or not ok:
            held.append({"job":raw,"eligibility":eligibility,"action":"SKIP_FINAL_ELIGIBILITY","reasons":reasons});continue
        finalized.append({"job":raw,"eligibility":eligibility,"action":"FINAL_JD_VERIFIED"})
    result={"finalized":len(finalized),"held_or_rejected":len(held),"results":finalized,"rejections":held}
    out=Path(output_path);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2),encoding="utf-8")
    return result

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--report",default="generated/eligible_jobs.json");p.add_argument("--output",default="generated/finalized_jobs.json");a=p.parse_args()
    result=finalize_report(a.report,a.output);print(json.dumps({k:v for k,v in result.items() if k not in ("results","rejections")},indent=2))
    for i,x in enumerate(result["results"],1):
        j=x["job"];print(f"{i}. {j.get('company_key')} | {j.get('title')} | JD chars={j.get('description_length')} | {x['action']}")
    for x in result["rejections"]:print(f"HOLD/SKIP: {x['job'].get('company_key')} | {x['job'].get('title')} | {x['action']}")
    print(f"Saved finalized jobs to {a.output}")
