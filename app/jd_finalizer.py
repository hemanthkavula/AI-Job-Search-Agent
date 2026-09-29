from __future__ import annotations
import html,json,re
from http.client import InvalidURL
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib import request,parse
from app.config import load_profile
from app.eligibility import two_category_filter
from app.llm_job_analyzer import analyze_job_with_llm, semantic_rejection_reasons
from app.filters import passes_hard_filters, location_is_us
from app.ats_resolver import resolve_original_ats
from app.sources.workday import job_detail_is_live
from app.discovery import ALL_ATS_PROVIDERS
from app.company_domain_resolver import resolve_company
from urllib.error import HTTPError, URLError

MIN_COMPLETE_JD_CHARS=1200
MIN_JD_SIGNAL_SCORE=3
MIN_USABLE_JD_CHARS=250
DICE_BOILERPLATE_MARKERS=("Search all similar jobs","Jobs Directory","Career Advice","Employers and Recruiters","Get the Dice app","Copyright ©","Apply Now To see how well you match")
AGGREGATOR_HOSTS=("dice.com","indeed.com","linkedin.com","ziprecruiter.com","monster.com")

def _is_aggregator_url(url):
    host=(parse.urlsplit(url or "").netloc or "").lower()
    return any(host==name or host.endswith("."+name) for name in AGGREGATOR_HOSTS)
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
    except (URLError,TimeoutError,OSError,ValueError,InvalidURL):
        # Network/anti-bot failures and malformed URLs are not allowed to crash
        # the whole production cycle. Hold this one job for later verification.
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

def _jsonld_jobpostings(page):
    """Return schema.org JobPosting nodes for identity-aware employer resolution."""
    found=[]
    for block in re.findall(r"(?is)<script[^>]+type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>",page or ""):
        try: payload=json.loads(html.unescape(block).strip())
        except Exception: continue
        stack=payload if isinstance(payload,list) else [payload]
        for item in stack:
            if not isinstance(item,dict):continue
            nodes=item.get("@graph") if isinstance(item.get("@graph"),list) else [item]
            for node in nodes:
                if not isinstance(node,dict):continue
                kinds=node.get("@type");kinds=kinds if isinstance(kinds,list) else [kinds]
                if "JobPosting" in kinds:found.append(node)
    return found

def _extract_jsonld_job_description(page):
    for node in _jsonld_jobpostings(page):
        if node.get("description"):return _clean_html(str(node["description"]))
    return ""

def _jsonld_job_location(node):
    """Return authoritative physical or telecommute eligibility from JobPosting."""
    locations=node.get("jobLocation") or []
    if not isinstance(locations,list):locations=[locations]
    values=[]
    for location in locations:
        if not isinstance(location,dict):continue
        address=location.get("address") or {}
        if not isinstance(address,dict):continue
        parts=[address.get("streetAddress"),address.get("addressLocality"),address.get("addressRegion"),address.get("postalCode"),address.get("addressCountry")]
        value=", ".join(str(x).strip() for x in parts if x not in (None,"") and str(x).strip())
        if value:values.append(value)
    if values:
        return " | ".join(dict.fromkeys(values))

    # Fully remote schema.org postings commonly omit jobLocation and instead
    # express the legal work geography through applicantLocationRequirements.
    # That field is more authoritative than an upstream board's generic "Remote".
    location_type=str(node.get("jobLocationType") or "").upper()
    if "TELECOMMUTE" in location_type:
        requirements=node.get("applicantLocationRequirements") or []
        if not isinstance(requirements,list):requirements=[requirements]
        allowed=[]
        for requirement in requirements:
            if isinstance(requirement,str):
                value=requirement.strip()
            elif isinstance(requirement,dict):
                value=str(
                    requirement.get("name")
                    or requirement.get("addressCountry")
                    or (requirement.get("address") or {}).get("addressCountry")
                    or ""
                ).strip()
            else:
                value=""
            if value:allowed.append(value)
        if allowed:
            return "Remote - " + " | ".join(dict.fromkeys(allowed))
        return "Remote"
    return ""

def _official_job_location(page,job):
    """Extract location only from the identity-matched official JobPosting node."""
    for node in _jsonld_jobpostings(page):
        if _jobposting_identity_matches(job,node,job.get("original_url") or job.get("url") or ""):
            location=_jsonld_job_location(node)
            if location:return location
    # Direct ATS pages can omit enough organization identity metadata to prevent
    # strict identity matching. If the page exposes exactly one JobPosting, it is
    # the authoritative posting already selected by this job URL.
    nodes=_jsonld_jobpostings(page)
    if len(nodes)==1:return _jsonld_job_location(nodes[0])
    return ""

def _official_posted_at(page,now=None):
    """Extract the employer/ATS JobPosting publication date; aggregator dates are never authoritative."""
    now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    for node in _jsonld_jobpostings(page):
        value=node.get("datePosted") or node.get("datePublished")
        if not value:continue
        try:return datetime.fromisoformat(str(value).replace("Z","+00:00")).astimezone(timezone.utc),str(value)
        except Exception:continue
    plain=_clean_html(page)
    m=re.search(r"(?i)\bposted\s+(today|just now|(?:an?|\d+)\s+hours?\s+ago|(?:a|\d+)\s+days?\s+ago)\b",plain)
    if not m:return None,None
    label="Posted "+m.group(1)
    from app.freshness import _parse_posting_value
    return _parse_posting_value(label,now),label

def _norm_identity(value):
    return re.sub(r"[^a-z0-9]+"," ",(value or "").lower()).strip()

def _jobposting_identity_matches(job,node,url):
    """Require a candidate page to identify the same employer and role, not merely mention them."""
    expected_title=_norm_identity(job.get("title"))
    actual_title=_norm_identity(str(node.get("title") or ""))
    if not expected_title or not actual_title:return False
    et=set(expected_title.split());at=set(actual_title.split())
    title_ratio=len(et & at)/max(1,len(et))
    if title_ratio<0.70:return False
    org=node.get("hiringOrganization") or {}
    org_name=_norm_identity(org.get("name") if isinstance(org,dict) else str(org))
    company=_norm_identity(job.get("company_key") or job.get("company"))
    company_tokens={x for x in company.split() if len(x)>=4 and x not in {"company","corporation","inc","llc","ltd"}}
    org_tokens=set(org_name.split())
    host=_norm_identity(parse.urlsplit(url).netloc).replace(" ","")
    company_ok=bool(company_tokens & org_tokens) if org_name else any(x in host for x in company_tokens)
    if not company_ok:return False
    expected_id=_norm_identity(str(job.get("requisition_id") or job.get("job_id") or job.get("external_id") or ""))
    ident=node.get("identifier") or {}
    actual_id=_norm_identity(str(ident.get("value") if isinstance(ident,dict) else ident))
    # When both sides expose a useful requisition identifier, disagreement is a hard mismatch.
    if expected_id and actual_id and len(expected_id)>=4 and len(actual_id)>=4 and expected_id not in actual_id and actual_id not in expected_id:
        # Aggregator external IDs are often unrelated UUIDs; only enforce recognizable requisition-like IDs.
        if any(ch.isdigit() for ch in expected_id) and len(expected_id)<80:return False
    return True

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
    """Resolve an aggregator lead only to a strongly identity-matched employer/ATS JobPosting."""
    company=(job.get("company_key") or job.get("company") or "").strip()
    title=(job.get("title") or "").strip()
    if not company or not title:return ("","")
    # Build several identity-rich lookup routes instead of relying on only
    # company+title. Aggregator leads often expose a requisition ID, location, or
    # hiringOrganization URL that is more discriminating than the title alone.
    req_id=str(job.get("requisition_id") or job.get("job_id") or "").strip()
    location=str(job.get("location") or "").strip()
    domain_hit=resolve_company({
        "company":company,
        "organization_url_evidence":job.get("organization_url_evidence"),
        "official_domain":job.get("official_domain"),
        "official_url":job.get("official_url"),
    },allow_name_search=True) or {}
    official_domain=(domain_hit.get("official_domain") or "").strip()
    queries=[f'"{title}" "{company}" careers',f'"{title}" "{company}" jobs']
    if req_id:queries.insert(0,f'"{req_id}" "{company}" jobs')
    if location:queries.append(f'"{title}" "{company}" "{location}"')
    if official_domain:
        queries.insert(0,f'site:{official_domain} "{title}"')
        if req_id:queries.insert(0,f'site:{official_domain} "{req_id}"')
    seen=set();ranked=[]
    for query in queries:
        page=_fetch_public_page("https://www.google.com/search?q="+parse.quote(query))
        urls=re.findall(r'https?://[^&"<> ]+',page or "")
        for u in urls:
            u=html.unescape(u)
            if u in seen:continue
            seen.add(u)
            low=u.lower()
            if any(x in low for x in ("dice.com","indeed.com","linkedin.com","ziprecruiter.com","google.com")):continue
            p=_fetch_public_page(u)
            for node in _jsonld_jobpostings(p):
                if not _jobposting_identity_matches(job,node,u):continue
                desc=_clean_html(str(node.get("description") or ""))
                if not _looks_like_usable_jd(desc,""):continue
                provider_bonus=1 if any(x in low for x in ("greenhouse","lever.co","ashbyhq","myworkdayjobs","smartrecruiters","icims","jobvite","oraclecloud")) else 0
                ranked.append((provider_bonus,_jd_signal_score(desc),len(desc),u,desc))
    if not ranked:return ("","")
    _,_,_,u,desc=max(ranked)
    return u,desc

def resolve_full_jd(job):
    """Resolve full JD only after lightweight eligibility. Never calls an LLM."""
    job=resolve_original_ats(job)
    current=(job.get("description") or "").strip()
    source=(job.get("source") or "").lower()
    lead_before_resolution=job.get("original_url") or job.get("url") or ""
    aggregator_origin=bool(job.get("discovery_only")) or source in {"dice","ziprecruiter","indeed","linkedin","monster"} or _is_aggregator_url(lead_before_resolution)
    if job.get("description_complete") and _looks_like_complete_jd(current,source) and not aggregator_origin:return job
    fetch_url=job.get("original_url") or job.get("url")
    page=_fetch_public_page(fetch_url)
    resolved=_best_resolved_description(page,source)
    out=dict(job)
    employer_url=""
    # Aggregators can expose only a teaser and omit the employer ATS link. In
    # that case, resolve the same company/title on the employer's public career
    # site rather than weakening JD quality requirements.
    # Aggregator URLs are discovery leads, not preferred application targets.
    # Always try to canonicalize Dice to the employer's own careers/ATS page,
    # even when Dice already supplied a usable/full JD.
    lead_url=out.get("original_url") or out.get("url") or ""
    # Any aggregator-origin lead is discovery-only. It must resolve to the
    # employer/ATS job page before it can become eligible for paid resume work.
    should_resolve_employer=(bool(out.get("discovery_only")) or source in {"dice","ziprecruiter"} or _is_aggregator_url(lead_url))
    if should_resolve_employer or not _looks_like_usable_jd(resolved or current,source):
        employer_url,employer_desc=_resolve_employer_career_page(out)
        if len(employer_desc)>len(resolved):resolved=employer_desc
        if employer_url:
            out["aggregator_url"]=out.get("original_url") or out.get("url")
            out["original_url"]=employer_url
            out["ats_resolution"]="employer_career_page_canonical" if should_resolve_employer else "employer_career_page_fallback"
    if len(resolved)>len(current):out["description"]=resolved
    final=(out.get("description") or "").strip()
    out["description_length"]=len(final)
    out["description_complete"]=_looks_like_complete_jd(final,source)
    out["description_usable"]=_looks_like_usable_jd(final,source)
    out["jd_signal_score"]=_jd_signal_score(final)
    out["jd_resolution_source"]="employer_career_page_canonical" if employer_url and should_resolve_employer else ("employer_career_page_fallback" if employer_url else ("jsonld_or_original_ats_public_job_detail_page" if len(resolved)>len(current) else "source_payload"))
    return out

def finalize_report(report_path,output_path="generated/finalized_jobs.json",hours=24,now=None):
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
        application_url=raw.get("original_url") or raw.get("url") or ""
        # Discovery metadata is not authoritative for geography. Re-read the
        # official ATS JobPosting before final eligibility and replace the
        # discovery location when the employer page provides one. This prevents
        # foreign jobs mislabeled as US/remote upstream from reaching resumes.
        official_page=_fetch_public_page(application_url)
        official_location=_official_job_location(official_page,raw)
        if official_location:
            raw["discovery_location"]=raw.get("location")
            raw["location"]=official_location
            raw["official_location"]=official_location
            raw["location_basis"]="official_employer_jobposting"
        if _is_aggregator_url(application_url):
            held.append({"job":raw,"action":"HOLD_ATS_UNRESOLVED","reason":"Aggregator listing could not be resolved to an authoritative employer/ATS application page before resume generation.","diagnostics":{"url":application_url,"source":raw.get("source"),"ats_resolution":raw.get("ats_resolution")}})
            continue
        aggregator_origin=bool(raw.get("aggregator_url")) or (raw.get("source") or "").lower() in {"dice","ziprecruiter","indeed","linkedin","monster"}
        check_now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        cutoff=check_now-timedelta(hours=hours)
        posting_fields=("posted_at","posted_on","date_posted","datePosted","published_at","publication_date")
        raw["discovery_posted_at"]=next((raw.get(field) for field in posting_fields if raw.get(field) not in (None,"")),None)
        official_posted=None;official_label=None
        if aggregator_origin:
            # Aggregator timestamps are discovery evidence only. Re-read the
            # resolved employer/ATS page and enforce its authoritative date.
            official_posted,official_label=_official_posted_at(official_page,now=check_now)
        else:
            # Direct ATS jobs can gain a more authoritative posting field during
            # detail resolution after the earlier freshness pass. Re-check that
            # final value here so e.g. Workday "Posted 4 Days Ago" cannot bypass
            # a ~61-hour production window. If no posting field was added, retain
            # the result of the earlier strict freshness gate.
            from app.freshness import _parse_posting_value
            for field in posting_fields:
                value=raw.get(field)
                if value in (None,""):continue
                official_posted=_parse_posting_value(value,check_now)
                if official_posted is not None:
                    official_label=str(value);break
        if official_posted is not None:
            raw["official_posted_at"]=official_posted.isoformat()
            raw["official_posted_label"]=official_label
            raw["freshness_basis"]="official_employer_posting_date"
        if aggregator_origin and official_posted is None:
            # The official employer/ATS page is always the primary freshness source.
            # For a Dice-origin lead only, once that lead has been identity-resolved
            # to an official employer/ATS application page, allow Dice's posting date
            # as a fallback when the official page exposes no usable date.
            # This never permits an unresolved Dice URL to become the application URL.
            from app.freshness import _parse_posting_value
            discovery_source=(raw.get("source") or "").lower()
            fallback_value=raw.get("discovery_posted_at")
            fallback_posted=_parse_posting_value(fallback_value,check_now) if discovery_source=="dice" and raw.get("aggregator_url") and fallback_value else None
            if fallback_posted is not None:
                official_posted=fallback_posted
                official_label=str(fallback_value)
                raw["official_posted_at"]=fallback_posted.isoformat()
                raw["official_posted_label"]=official_label
                raw["freshness_basis"]="dice_date_fallback_after_official_ats_resolution"
            else:
                held.append({"job":raw,"action":"HOLD_OFFICIAL_POST_DATE_UNVERIFIED","reason":"Official employer/ATS posting date could not be verified at finalization and no permitted Dice fallback date was available.","diagnostics":{"url":application_url,"discovery_source":raw.get("source"),"ats_resolution":raw.get("ats_resolution")}})
                continue
        if official_posted is not None and (official_posted<cutoff or official_posted>check_now+timedelta(minutes=10)):
            held.append({"job":raw,"action":"REJECT_STALE_OFFICIAL_POSTING","reason":"Official employer/ATS posting date is outside the requested freshness window; discovery/repost/refresh dates were ignored.","diagnostics":{"url":application_url,"official_posted_at":official_posted.isoformat(),"official_posted_label":official_label,"freshness_hours":hours,"discovery_source":raw.get("source")}})
            continue
        live_status,live_reason=_live_public_job_page(application_url)
        if live_status is False:
            held.append({"job":raw,"action":"REJECT_DEAD_JOB","reason":"Application page no longer exists or is explicitly closed.","diagnostics":{"url":raw.get("original_url") or raw.get("url"),"live_check":live_reason}})
            continue
        if live_status is None:
            held.append({"job":raw,"action":"HOLD_LIVE_STATUS_UNVERIFIED","reason":"Application page could not be verified as live before resume generation.","diagnostics":{"url":raw.get("original_url") or raw.get("url"),"live_check":live_reason}})
            continue
        if not raw.get("description_complete"):
            held.append({"job":raw,"action":"HOLD_COMPLETE_JD_REQUIRED","reason":"Resume generation requires a trustworthy complete current job description; short/partial excerpts are discovery evidence only.","diagnostics":{"description_length":raw.get("description_length",len(raw.get("description") or "")),"jd_signal_score":raw.get("jd_signal_score"),"jd_resolution_source":raw.get("jd_resolution_source"),"description_usable":raw.get("description_usable"),"url":raw.get("original_url") or raw.get("url")}});continue
        raw["tailoring_mode"]="FULL_JD"
        # Compute the governing eligibility record before any final-location hold so
        # every rejection preserves the same diagnostic schema (experience,
        # sponsorship, citizenship, clearance).
        eligibility=two_category_filter(raw,profile)
        # OpenAI is a semantic second verifier over the already-resolved official
        # JD. It can make eligibility stricter when it finds an explicit restriction
        # with evidence, but it can never override a deterministic rejection.
        try:
            semantic_analysis=analyze_job_with_llm(raw)
        except Exception as exc:
            held.append({"job":raw,"eligibility":eligibility,"action":"HOLD_LLM_ELIGIBILITY_UNVERIFIED","reason":"OpenAI semantic eligibility verification failed; fail closed before resume generation.","diagnostics":{"error":str(exc)[:1000],"url":application_url}})
            continue
        if semantic_analysis is not None:
            raw["llm_job_analysis"]=semantic_analysis
            semantic_reasons=semantic_rejection_reasons(semantic_analysis,profile)
            if semantic_reasons:
                held.append({"job":raw,"eligibility":eligibility,"action":"SKIP_FINAL_ELIGIBILITY","reason":"; ".join(semantic_reasons),"reasons":semantic_reasons,"diagnostics":{"llm_job_analysis":semantic_analysis,"url":application_url}})
                continue
        # Aggregator discovery geography is never authoritative after canonicalizing
        # to an employer/ATS page. If that official page exposes no structured
        # location, require explicit U.S. geography in the verified employer JD
        # instead of reusing the aggregator's old location value.
        final_location=raw.get("location")
        if aggregator_origin and not raw.get("official_location"):
            final_location=""
        # Discovery may defer blank/remote geography, but finalization must never do so.
        # Require explicit U.S. evidence from the official structured location or verified JD.
        final_location_verified = bool((final_location or "").strip()) and location_is_us(final_location,None,raw.get("description") or "")
        if not final_location_verified:
            held.append({"job":raw,"eligibility":eligibility,"action":"SKIP_FINAL_ELIGIBILITY","reason":"location outside United States target or U.S. geography unverified at official finalization","reasons":["location outside United States target or U.S. geography unverified at official finalization"],"diagnostics":{"official_location":raw.get("official_location"),"discovery_location":raw.get("discovery_location") or raw.get("location"),"location_basis":raw.get("location_basis"),"url":application_url}})
            continue
        ok,reasons=passes_hard_filters(raw,profile)
        if not eligibility.get("eligible") or not ok:
            held.append({"job":raw,"eligibility":eligibility,"action":"SKIP_FINAL_ELIGIBILITY","reasons":reasons,"diagnostics":{"description_length":raw.get("description_length",len(raw.get("description") or "")),"jd_signal_score":raw.get("jd_signal_score"),"jd_resolution_source":raw.get("jd_resolution_source")}});continue
        # Paid resume generation requires a known application route. A verified
        # external ATS is preferred. Dice-hosted jobs remain eligible for a
        # controlled Dice adapter; the adapter must inspect the Apply flow and
        # This pipeline verifies the job/application destination but does not
        # decide whether the separate Muse application system can automate it.
        source_supported=set(ALL_ATS_PROVIDERS)
        if raw.get("ats_provider") in source_supported:
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
