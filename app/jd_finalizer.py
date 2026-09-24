from __future__ import annotations
import html,json,re
from pathlib import Path
from urllib import request,parse
from app.config import load_profile
from app.eligibility import two_category_filter
from app.filters import passes_hard_filters
from app.ats_resolver import resolve_original_ats
from app.sources.workday import job_detail_is_live
from urllib.error import HTTPError, URLError

MIN_COMPLETE_JD_CHARS=1200
MIN_JD_SIGNAL_SCORE=3
MIN_USABLE_JD_CHARS=250
DICE_BOILERPLATE_MARKERS=("Search all similar jobs","Jobs Directory","Career Advice","Employers and Recruiters","Get the Dice app","Copyright ©","Apply Now To see how well you match")
JD_SECTION_SIGNALS=("responsibilities","requirements","qualifications","what you'll do","what you will do","skills","experience","preferred","minimum qualifications","basic qualifications")

def _jd_signal_score(text):
    low=(text or "").lower()
    return sum(1 for s in JD_SECTION_SIGNALS if s in low)

def _looks_like_complete_jd(text,source=""):
    value=(text or "").strip()
    if len(value)<MIN_COMPLETE_JD_CHARS:return False
    if (source or "").lower()=="dice" and sum(m.lower() in value.lower() for m in DICE_BOILERPLATE_MARKERS)>=2:return False
    return _jd_signal_score(value)>=MIN_JD_SIGNAL_SCORE

def _looks_like_usable_jd(text,source=""):
    value=(text or "").strip()
    if len(value)<MIN_USABLE_JD_CHARS:return False
    if (source or "").lower()=="dice" and sum(m.lower() in value.lower() for m in DICE_BOILERPLATE_MARKERS)>=2:return False
    # Short provider excerpts are allowed for conservative base-resume tailoring
    # when they contain at least one meaningful JD section signal.
    return _jd_signal_score(value)>=1

def _clean_html(text):
    text=re.sub(r"(?is)<(script|style).*?>.*?</\1>"," ",text or "")
    text=re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h[1-6]>","\n",text)
    text=re.sub(r"(?s)<[^>]+>"," ",text)
    text=html.unescape(text).replace("\xa0"," ")
    return re.sub(r"[ \t]+"," ",re.sub(r"\n\s*\n+","\n",text)).strip()

DEAD_PAGE_MARKERS=("job is no longer available","job no longer available","position is no longer available","position has been filled","job has been filled","job has expired","posting has expired","requisition has been closed","this job is closed","page not found","job not found","no longer accepting applications")

def _live_public_job_page(url):
    """Provider-agnostic final existence check before paid resume generation."""
    if not url:return False,"missing_url"
    req=request.Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; AI-Job-Search-Agent/1.0)","Accept":"text/html,application/json,*/*"})
    try:
        with request.urlopen(req,timeout=30) as resp:
            status=getattr(resp,"status",200)
            if status in (404,410):return False,f"http_{status}"
            if status>=400:return False,f"http_{status}"
            body=resp.read(500000).decode("utf-8",errors="replace")
    except HTTPError as exc:
        if exc.code in (404,410):
            return False,f"http_{exc.code}"
        # Access blocks, rate limits, and transient server errors do not prove
        # that the requisition is dead. Hold until it can be verified.
        return None,f"http_{exc.code}"
    except (URLError,TimeoutError,OSError):
        # Network/anti-bot failures are not proof that a job is dead; hold it
        # rather than falsely treating it as a valid application.
        return None,"unverifiable"
    plain=_clean_html(body).lower()
    if any(marker in plain for marker in DEAD_PAGE_MARKERS):
        return False,"closed_marker"
    return True,"reachable"

def _fetch_public_page(url):
    if not url:return ""
    req=request.Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; AI-Job-Search-Agent/1.0)"})
    try:
        with request.urlopen(req,timeout=30) as resp:return resp.read().decode("utf-8",errors="replace")
    except Exception:return ""

def _extract_jsonld_job_description(page):
    """Extract a full JobPosting description embedded as schema.org JSON-LD."""
    for block in re.findall(r"(?is)<script[^>]+type=['\"]application/ld\\+json['\"][^>]*>(.*?)</script>",page or ""):
        try:
            payload=json.loads(html.unescape(block).strip())
        except Exception:
            continue
        stack=payload if isinstance(payload,list) else [payload]
        for item in stack:
            if not isinstance(item,dict):continue
            candidates=item.get("@graph") if isinstance(item.get("@graph"),list) else [item]
            for node in candidates:
                if not isinstance(node,dict):continue
                kind=node.get("@type")
                kinds=kind if isinstance(kind,list) else [kind]
                if "JobPosting" in kinds and node.get("description"):
                    return _clean_html(str(node["description"]))
    return ""

def _best_resolved_description(page,source=""):
    jsonld=_extract_jsonld_job_description(page)
    extracted=_extract_dice(page) if (source or "").lower()=="dice" else _clean_html(page)
    candidates=[x.strip() for x in (jsonld,extracted) if x and x.strip()]
    if not candidates:return ""
    # Prefer meaningful JD structure first, then length. This avoids replacing a
    # clean JSON-LD JobPosting with a much longer navigation-heavy HTML dump.
    return max(candidates,key=lambda x:(_jd_signal_score(x),len(x)))

def _extract_dice(page):
    plain=_clean_html(page)
    start=re.search(r"(?i)\bJob Description\b",plain)
    if start:plain=plain[start.start():]
    end=re.search(r"(?i)\b(?:Search all similar jobs|Similar Jobs|More jobs at|Search for Jobs|Jobs Directory|Career Advice|Employers and Recruiters|Create a job alert|Dice Id:)\b",plain)
    if end:plain=plain[:end.start()]
    return plain

def _resolve_employer_career_page(job):
    """Fallback for aggregator excerpts: locate the same role on the employer's public careers site."""
    company=(job.get("company_key") or job.get("company") or "").strip()
    title=(job.get("title") or "").strip()
    if not company or not title:return ("","")
    # Search-engine fallback is intentionally limited to public employer career pages.
    # It is used only after the aggregator page itself fails to expose an ATS link.
    q=parse.quote(f'{company} {title} careers')
    page=_fetch_public_page("https://www.google.com/search?q="+q)
    urls=re.findall(r'https?://[^&"<> ]+',page or "")
    company_tokens=[x for x in re.findall(r"[a-z0-9]+",company.lower()) if len(x)>=4]
    title_tokens=set(x for x in re.findall(r"[a-z0-9]+",title.lower()) if len(x)>=3)
    ranked=[]
    for u in urls:
        u=html.unescape(u)
        if any(x in u.lower() for x in ("dice.com","indeed.com","linkedin.com","ziprecruiter.com","google.com")):continue
        host=re.sub(r"[^a-z0-9]","",parse.urlsplit(u).netloc.lower())
        company_score=sum(t in host for t in company_tokens)
        if not company_score:continue
        p=_fetch_public_page(u)
        desc=_best_resolved_description(p,"")
        words=set(re.findall(r"[a-z0-9]+",desc.lower()))
        overlap=len(title_tokens & words)
        if _looks_like_usable_jd(desc,"") and overlap>=max(2,min(4,len(title_tokens))):
            ranked.append((company_score,overlap,_jd_signal_score(desc),len(desc),u,desc))
    if not ranked:return ("","")
    _,_,_,_,u,desc=max(ranked)
    return u,desc

def resolve_full_jd(job):
    """Resolve full JD only after lightweight eligibility. Never calls an LLM."""
    job=resolve_original_ats(job)
    current=(job.get("description") or "").strip()
    source=(job.get("source") or "").lower()
    if job.get("description_complete") and _looks_like_complete_jd(current,source):return job
    fetch_url=job.get("original_url") or job.get("url")
    page=_fetch_public_page(fetch_url)
    resolved=_best_resolved_description(page,source)
    out=dict(job)
    employer_url=""
    # Aggregators can expose only a teaser and omit the employer ATS link. In
    # that case, resolve the same company/title on the employer's public career
    # site rather than weakening JD quality requirements.
    if not _looks_like_usable_jd(resolved or current,source):
        employer_url,employer_desc=_resolve_employer_career_page(out)
        if len(employer_desc)>len(resolved):resolved=employer_desc
        if employer_url:
            out["original_url"]=employer_url
            out["ats_resolution"]="employer_career_page_fallback"
    if len(resolved)>len(current):out["description"]=resolved
    final=(out.get("description") or "").strip()
    out["description_length"]=len(final)
    out["description_complete"]=_looks_like_complete_jd(final,source)
    out["description_usable"]=_looks_like_usable_jd(final,source)
    out["jd_signal_score"]=_jd_signal_score(final)
    out["jd_resolution_source"]="employer_career_page_fallback" if employer_url else ("jsonld_or_original_ats_public_job_detail_page" if len(resolved)>len(current) else "source_payload")
    return out

def finalize_report(report_path,output_path="generated/finalized_jobs.json"):
    report=json.loads(Path(report_path).read_text(encoding="utf-8"));profile=load_profile()
    finalized=[];held=[]
    for item in report.get("results",[]):
        if item.get("action")!="ELIGIBLE_FOR_RESUME":continue
        raw=resolve_full_jd(item["job"])
        # Workday search results can contain a requisition that closes between
        # discovery and resume generation. Re-check the CXS detail endpoint here.
        if (raw.get("source") or "").lower()=="workday":
            url=raw.get("url") or raw.get("original_url") or ""
            m=re.search(r"https?://([^/]+)/(?:(?:[a-z]{2}-[A-Z]{2})/)?([^/]+)(/job/.+)",url)
            if m:
                host,site,external_path=m.groups()
                tenant=host.split(".",1)[0]
                live,_=job_detail_is_live(host,tenant,site,external_path)
                if not live:
                    held.append({"job":raw,"action":"REJECT_DEAD_JOB","reason":"Workday requisition no longer exists at the live detail endpoint.","diagnostics":{"url":url}})
                    continue
        # Every provider gets a final live-page check. Never spend resume
        # generation on a URL known to be dead, and never assume an unverifiable
        # application is live.
        live_status,live_reason=_live_public_job_page(raw.get("original_url") or raw.get("url"))
        if live_status is False:
            held.append({"job":raw,"action":"REJECT_DEAD_JOB","reason":"Application page no longer exists or is explicitly closed.","diagnostics":{"url":raw.get("original_url") or raw.get("url"),"live_check":live_reason}})
            continue
        if live_status is None:
            held.append({"job":raw,"action":"HOLD_LIVE_STATUS_UNVERIFIED","reason":"Application page could not be verified as live before resume generation.","diagnostics":{"url":raw.get("original_url") or raw.get("url"),"live_check":live_reason}})
            continue
        if not (raw.get("description_complete") or raw.get("description_usable") or _looks_like_usable_jd(raw.get("description"),raw.get("source"))):
            held.append({"job":raw,"action":"HOLD_UNUSABLE_JD","reason":"Job description is too limited to identify meaningful tailoring targets safely.","diagnostics":{"description_length":raw.get("description_length",len(raw.get("description") or "")),"jd_signal_score":raw.get("jd_signal_score"),"jd_resolution_source":raw.get("jd_resolution_source"),"url":raw.get("original_url") or raw.get("url")}});continue
        raw["tailoring_mode"]="FULL_JD" if raw.get("description_complete") else "BASE_RESUME_CONSERVATIVE"
        eligibility=two_category_filter(raw,profile);ok,reasons=passes_hard_filters(raw,profile)
        if not eligibility.get("eligible") or not ok:
            held.append({"job":raw,"eligibility":eligibility,"action":"SKIP_FINAL_ELIGIBILITY","reasons":reasons,"diagnostics":{"description_length":raw.get("description_length",len(raw.get("description") or "")),"jd_signal_score":raw.get("jd_signal_score"),"jd_resolution_source":raw.get("jd_resolution_source")}});continue
        # Paid resume generation requires a known application route. A verified
        # external ATS is preferred. Dice-hosted jobs remain eligible for a
        # controlled Dice adapter; the adapter must inspect the Apply flow and
        # stop on redirects, CAPTCHA/MFA, or unknown questions.
        supported={"greenhouse","lever","ashby","workday","smartrecruiters","icims","jobvite"}
        if raw.get("ats_provider") in supported:
            raw["application_route"]="EXTERNAL_ATS"
        elif (raw.get("source") or "").lower()=="dice" and "dice.com" in (raw.get("original_url") or raw.get("url") or "").lower():
            raw["application_route"]="DICE"
            raw["ats_provider"]="dice"
        else:
            held.append({"job":raw,"eligibility":eligibility,"action":"HOLD_ATS_UNRESOLVED","reason":"Application route could not be determined safely before paid resume generation.","diagnostics":{"description_length":raw.get("description_length",len(raw.get("description") or "")),"jd_signal_score":raw.get("jd_signal_score"),"jd_resolution_source":raw.get("jd_resolution_source"),"ats_resolution":raw.get("ats_resolution"),"url":raw.get("original_url") or raw.get("url")}})
            continue
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
    for x in result["rejections"]:
        j=x["job"];d=x.get("diagnostics",{})
        reason=x.get("reason") or "; ".join(x.get("reasons") or [])
        print(f"HOLD/SKIP: {j.get('company_key')} | {j.get('title')} | {x['action']} | JD chars={d.get('description_length')} | signals={d.get('jd_signal_score')} | source={d.get('jd_resolution_source')} | reason={reason}")
    print(f"Saved finalized jobs to {a.output}")
