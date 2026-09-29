from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from urllib import error, request

CACHE_DIR = Path("generated") / "llm_job_analysis_cache"

SYSTEM_PROMPT = """You extract factual eligibility requirements from an official job description.
Return JSON only. Do not recommend, score, rank, or infer unstated requirements.
Every non-null restrictive fact must include a short verbatim evidence fragment from the supplied JD.
If wording is ambiguous, return null/unknown rather than guessing."""

def _output_text(payload: dict) -> str:
    if payload.get("output_text"):
        return str(payload["output_text"])
    chunks=[]
    for item in payload.get("output",[]) or []:
        for part in item.get("content",[]) or []:
            if part.get("type")=="output_text" and part.get("text"):
                chunks.append(str(part["text"]))
    return "".join(chunks)

def _cache_key(model: str, job: dict) -> str:
    material={
        "model":model,
        "title":job.get("title"),
        "company":job.get("company_key") or job.get("company"),
        "description":job.get("description"),
        "url":job.get("original_url") or job.get("url"),
    }
    return hashlib.sha256(json.dumps(material,sort_keys=True,ensure_ascii=False).encode("utf-8")).hexdigest()

def _evidence_is_in_jd(evidence, description: str) -> bool:
    if not evidence or not isinstance(evidence,str):
        return False
    norm=lambda s: re.sub(r"\s+"," ",str(s or "")).strip().lower()
    return bool(norm(evidence)) and norm(evidence) in norm(description)

def _validated(result: dict, description: str) -> dict:
    if not isinstance(result,dict):
        raise RuntimeError("OpenAI job analysis payload is not a JSON object")
    out={
        "required_experience_years":None,
        "required_experience_evidence":None,
        "employment_type":str(result.get("employment_type") or "unknown").lower(),
        "employment_evidence":None,
        "sponsorship":"unknown",
        "sponsorship_evidence":None,
        "us_citizenship_required":None,
        "citizenship_evidence":None,
        "clearance_required":None,
        "clearance_evidence":None,
        "role_family":str(result.get("role_family") or "unknown").lower(),
        "role_family_evidence":None,
    }
    pairs=(
        ("required_experience_evidence","required_experience_evidence"),
        ("employment_evidence","employment_evidence"),
        ("sponsorship_evidence","sponsorship_evidence"),
        ("citizenship_evidence","citizenship_evidence"),
        ("clearance_evidence","clearance_evidence"),
        ("role_family_evidence","role_family_evidence"),
    )
    for source,target in pairs:
        value=result.get(source)
        if _evidence_is_in_jd(value,description):
            out[target]=value

    years=result.get("required_experience_years")
    try:
        years=int(years) if years is not None else None
    except (TypeError,ValueError):
        years=None
    if years is not None and 0 < years <= 20 and out["required_experience_evidence"]:
        out["required_experience_years"]=years

    sponsorship=str(result.get("sponsorship") or "unknown").lower()
    if sponsorship in {"available","unavailable","unknown"}:
        if sponsorship=="unknown" or out["sponsorship_evidence"]:
            out["sponsorship"]=sponsorship

    for source,target,evidence_key in (
        ("us_citizenship_required","us_citizenship_required","citizenship_evidence"),
        ("clearance_required","clearance_required","clearance_evidence"),
    ):
        value=result.get(source)
        if isinstance(value,bool) and (value is False or out[evidence_key]):
            out[target]=value
    return out

def analyze_job_with_llm(job: dict) -> dict | None:
    """Semantic second verifier for an already-resolved official JD.

    Disabled unless JOB_ANALYSIS_LLM_ENABLED=true. Results are cached by exact
    official JD/model. Restrictive facts are trusted only when their evidence is
    literally present in the JD; deterministic eligibility remains authoritative.
    """
    if os.getenv("JOB_ANALYSIS_LLM_ENABLED","false").lower() not in {"1","true","yes"}:
        return None
    key=os.getenv("OPENAI_API_KEY") or os.getenv("RESUME_LLM_API_KEY")
    if not key:
        raise RuntimeError("JOB_ANALYSIS_LLM_ENABLED but OPENAI_API_KEY is unavailable")
    description=str(job.get("description") or "").strip()
    if not description:
        raise RuntimeError("Cannot semantically verify an empty job description")
    model=os.getenv("JOB_ANALYSIS_LLM_MODEL","gpt-5.6-luna")
    cache_key=_cache_key(model,job)
    path=CACHE_DIR/f"{cache_key}.json"
    if path.exists():
        try:
            cached=json.loads(path.read_text(encoding="utf-8"))
            return _validated(cached,description)
        except Exception:
            pass

    prompt={
        "title":job.get("title"),
        "company":job.get("company_key") or job.get("company"),
        "official_job_description":description,
        "extract":{
            "required_experience_years":"Highest explicit minimum years of professional/relevant/role experience required overall. Do not use company age or preferred-only years.",
            "required_experience_evidence":"Short exact JD fragment supporting required_experience_years.",
            "employment_type":"One of full_time, contract, part_time, temporary, internship, unknown.",
            "employment_evidence":"Short exact JD fragment when employment_type is known.",
            "sponsorship":"One of available, unavailable, unknown. unavailable only for explicit current/future employment visa or immigration sponsorship/support restrictions.",
            "sponsorship_evidence":"Short exact JD fragment when sponsorship is not unknown.",
            "us_citizenship_required":"true only when explicitly required; false only when explicitly not required; otherwise null.",
            "citizenship_evidence":"Short exact JD fragment when non-null.",
            "clearance_required":"true only when an applicant must hold/obtain/maintain a security or public-trust clearance; false only when explicitly not required; otherwise null.",
            "clearance_evidence":"Short exact JD fragment when non-null.",
            "role_family":"One of data_engineering, analytics_engineering, data_platform, software_engineering, data_science, management, architecture, consulting, other, unknown.",
            "role_family_evidence":"Short exact JD fragment supporting the role family."
        }
    }
    endpoint=os.getenv("JOB_ANALYSIS_LLM_ENDPOINT","https://api.openai.com/v1/responses")
    body=json.dumps({
        "model":model,
        "instructions":SYSTEM_PROMPT,
        "input":json.dumps(prompt,ensure_ascii=False),
        "max_output_tokens":1800,
    }).encode("utf-8")
    req=request.Request(endpoint,data=body,headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},method="POST")
    try:
        with request.urlopen(req,timeout=90) as resp:
            payload=json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail=exc.read().decode("utf-8",errors="replace")
        raise RuntimeError(f"OpenAI job analysis HTTP {exc.code}: {detail[:1000]}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"OpenAI job analysis connection error: {exc.reason}") from exc
    text=_output_text(payload)
    if not text:
        raise RuntimeError("OpenAI job analysis returned no output text")
    try:
        result=json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"OpenAI job analysis returned non-JSON output: {text[:1000]}") from exc
    CACHE_DIR.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result,ensure_ascii=False),encoding="utf-8")
    tmp.replace(path)
    return _validated(result,description)

def semantic_rejection_reasons(analysis: dict | None, profile: dict) -> list[str]:
    if not analysis:
        return []
    reasons=[]
    max_years=int(profile.get("preferences",{}).get("max_required_years",7))
    min_years=int(profile.get("preferences",{}).get("min_required_years",4))
    years=analysis.get("required_experience_years")
    if isinstance(years,int) and years>max_years:
        reasons.append(f"OpenAI-verified official JD requires {years}+ years, above configured maximum {max_years}")
    elif isinstance(years,int) and years<min_years:
        reasons.append(f"OpenAI-verified official JD requires {years} years, below configured minimum {min_years}")
    if analysis.get("employment_type") in {"contract","part_time","temporary","internship"} and analysis.get("employment_evidence"):
        reasons.append(f"OpenAI-verified non-target employment type: {analysis['employment_type']}")
    if analysis.get("sponsorship")=="unavailable" and analysis.get("sponsorship_evidence"):
        reasons.append("OpenAI-verified official JD explicitly disallows required future sponsorship/support")
    if analysis.get("us_citizenship_required") is True and analysis.get("citizenship_evidence"):
        reasons.append("OpenAI-verified official JD explicitly requires U.S. citizenship")
    if analysis.get("clearance_required") is True and analysis.get("clearance_evidence"):
        reasons.append("OpenAI-verified official JD explicitly requires security/public-trust clearance")
    if analysis.get("role_family") in {"data_science","management","architecture","consulting"} and analysis.get("role_family_evidence"):
        reasons.append(f"OpenAI-verified role family is outside target Data Engineering scope: {analysis['role_family']}")
    return reasons
