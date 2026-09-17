from __future__ import annotations
import json, os
from urllib import request, error

SYSTEM_PROMPT = """You are an expert ATS resume writer for senior data engineering roles.
Create a genuinely JD-specific resume, not a reordered or mechanically spun master resume.
Preserve all employers, titles, dates, locations, education, and certifications exactly.
Domain lock: Fidelity=financial services; Cigna=healthcare; Target=retail.
Use exactly 8 Fidelity bullets, 7 Cigna bullets, and 6 Target bullets.
Treat the job description as the primary tailoring target.
The candidate has confirmed broader hands-on exposure to these technologies even if they are absent from the base resume: BigQuery, Dagster, Apache Beam, Apache Flink, Kubernetes, ArgoCD, Helm, Istio.
When one of these confirmed technologies is relevant to the JD, include it in Technical Skills AND demonstrate it naturally in at least one relevant experience bullet. Integrate technologies into plausible engineering responsibilities rather than isolated keyword lists.
Distribute JD technologies across experience only where they make technical and domain sense. Keep Fidelity focused on financial/trading data, Cigna on healthcare data, and Target on retail/e-commerce data.
Do not force every keyword into every employer. Prefer coherent combinations such as streaming technologies with event pipelines, orchestration technologies with pipeline scheduling, warehouse technologies with ELT/analytics, and Kubernetes/Helm/ArgoCD/Istio with containerized data-platform deployment and operations.
Do not fabricate specific numerical results, certifications, team sizes, project names, or business outcomes. Do not claim an unsupported level of ownership. Use wording such as developed, implemented, integrated, deployed, supported, or worked with only when consistent with the candidate's confirmed technology exposure and surrounding evidence.
Every prominent JD technology placed in Technical Skills should have experience evidence somewhere in the resume when it is technically reasonable to demonstrate it.
Never stack boilerplate clauses, create keyword-dump bullets, or repeat the same phrases across bullets. Each bullet should communicate one coherent engineering accomplishment or responsibility and remain easy for a recruiter to read.
Preserve the meaning and strength of documented accomplishments.
Fidelity may contain at most 2 metric-bearing bullets; Cigna at most 2; Target must contain zero fabricated metrics.
Optimize simultaneously for ATS alignment and human readability; never improve keyword coverage by making bullets unnatural.
Return valid JSON only with keys summary, skills, experience, and education."""

CONFIRMED_EXTENDED_TECHNOLOGIES = [
    "BigQuery", "Dagster", "Apache Beam", "Apache Flink",
    "Kubernetes", "ArgoCD", "Helm", "Istio"
]

def build_prompt(job, profile, audit_feedback=None):
    return {
        "task":"Generate a fresh, human-readable, ATS-focused resume tailored directly to this JD.",
        "job":{"company":job.company,"title":job.title,"description":job.description},
        "candidate_evidence":profile,
        "confirmed_extended_technology_inventory":CONFIRMED_EXTENDED_TECHNOLOGIES,
        "audit_feedback":audit_feedback or {},
        "tailoring_policy":{
            "jd_is_primary_target":True,
            "include_relevant_jd_required_and_preferred_skills":True,
            "use_confirmed_extended_technologies_when_jd_relevant":True,
            "skills_need_experience_evidence":True,
            "integrate_jd_technologies_naturally_into_experience":True,
            "preserve_employer_domain_context":True,
            "do_not_invent_metrics_certifications_or_business_results":True
        },
        "quality_rules":{
            "target_internal_ats_score":95,
            "optimize_human_readability":True,
            "no_keyword_stuffing":True,
            "no_repeated_boilerplate":True,
            "one_coherent_idea_per_bullet":True,
            "preserve_fact_strength":True,
            "fidelity_bullets":8,"cigna_bullets":7,"target_bullets":6
        },
        "output_schema":{
            "summary":"3 concise recruiter-friendly sentences using the most important JD terminology naturally",
            "skills":{"category":["JD-relevant skill from base or confirmed extended technology inventory"]},
            "experience":[{"company":"exact employer","title":"exact title","dates":"exact dates","bullets":["fresh, coherent JD-specific bullet with natural evidence for relevant listed technologies"]}],
            "education":"preserve exactly"
        },
    }

def _extract_output_text(payload):
    if payload.get("output_text"): return payload["output_text"]
    chunks=[]
    for item in payload.get("output",[]):
        for part in item.get("content",[]):
            if part.get("type")=="output_text" and part.get("text"): chunks.append(part["text"])
    return "".join(chunks)

def generate_with_llm(job, profile, audit_feedback=None):
    key=os.getenv("OPENAI_API_KEY") or os.getenv("RESUME_LLM_API_KEY")
    if not key: return None
    endpoint=os.getenv("RESUME_LLM_ENDPOINT","https://api.openai.com/v1/responses")
    model=os.getenv("RESUME_LLM_MODEL","gpt-5.6")
    body=json.dumps({"model":model,"instructions":SYSTEM_PROMPT,"input":json.dumps(build_prompt(job,profile,audit_feedback)),"max_output_tokens":12000}).encode("utf-8")
    req=request.Request(endpoint,data=body,headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},method="POST")
    try:
        with request.urlopen(req,timeout=180) as resp:payload=json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail=exc.read().decode("utf-8",errors="replace");raise RuntimeError(f"OpenAI API HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:raise RuntimeError(f"OpenAI API connection error: {exc.reason}") from exc
    text=_extract_output_text(payload)
    if not text:raise RuntimeError(f"OpenAI Responses API returned no output text: {json.dumps(payload)[:1200]}")
    try:return json.loads(text)
    except json.JSONDecodeError as exc:raise RuntimeError(f"OpenAI returned non-JSON resume output: {text[:1200]}") from exc
