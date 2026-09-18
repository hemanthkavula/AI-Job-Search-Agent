from __future__ import annotations
import json, os, re
from urllib import request, error

SYSTEM_PROMPT = """You are an expert ATS resume writer for senior data engineering roles.
Your FIRST draft must be submission-ready. Perform the JD analysis and quality review internally before returning the resume.
Create a genuinely JD-specific resume, not a reordered or mechanically spun master resume.
Preserve all employers, titles, dates, locations, education, and certifications exactly.
Domain lock: Fidelity=financial services; Cigna=healthcare; Target=retail.
Use exactly 8 Fidelity bullets, 7 Cigna bullets, and 6 Target bullets.
Treat the complete job description as the primary tailoring target.
Before writing, internally identify the target title, REQUIRED technologies/responsibilities, then preferred technologies, architecture, orchestration, streaming/batch, modeling, governance/data quality and DevOps. Do not output this analysis.
The confirmed extended technology inventory is PERMISSION TO USE a technology when the JD specifically calls for it; it is NOT a checklist and is NOT a reason to expand the resume stack.
STRICT EXTENDED-TECH RULE: use an extended technology only when it is explicitly named in the JD or an unmistakable direct variant/brand reference is named. Never add an extended technology merely because it is adjacent, complementary, inferable, modern, or useful.
Do not maximize the number of technologies in the resume. Prefer the smallest coherent set that covers the JD strongly.
If the JD names alternatives such as Beam OR Flink OR Spark Streaming, do not automatically include every alternative. Prefer the candidate's established/base technology when it satisfies the requirement; add a confirmed extended technology only when its exact evidence materially improves alignment.
An extended technology included in Technical Skills must also have natural Professional Experience evidence. If the JD explicitly requests a technology that is in the confirmed extended inventory, treat the candidate confirmation as valid hands-on evidence and place it naturally in a technically coherent employer/domain bullet; do not invent metrics, project names, migrations, architectures, or business outcomes merely to place it. If a credible employer-context placement cannot be made, omit it rather than manufacturing a project story.
Never invent a specific architecture, migration, deployment path, tool combination, or project solely to place a keyword. In particular, do not construct chains such as Beam→BigQuery→Dagster or Kubernetes→Helm→ArgoCD→Istio unless the JD specifically requires those technologies and the candidate evidence supports that coherent use.
Prioritize established employer baseline technologies from candidate_evidence whenever they already satisfy the JD. For every technology in extended_technologies_explicitly_requested_by_jd, deliberately decide whether it materially strengthens alignment; when it does and a coherent employer context exists, include it in both Technical Skills and Professional Experience on V1 rather than waiting for audit feedback.
Distribute JD technologies only where technically coherent and supported. Fidelity stays financial/trading, Cigna stays healthcare, Target stays retail/e-commerce.
Do not fabricate certifications, team sizes, project names, numerical outcomes, or business results. Never invent a metric merely to strengthen a bullet. Treat qualitative latency/scale claims such as sub-minute, sub-second, low-latency with a specific bound, millions/billions, or other numeric/near-numeric performance claims as metrics unless they are explicitly present in candidate evidence.
STRICT METRIC RULE: Fidelity may have at most 2 metric-bearing bullets, Cigna at most 2, and Target must contain ZERO numeric scale, percentage, volume, latency, count, or performance metrics.
Never stack boilerplate clauses, create keyword-dump bullets, or repeat the same phrases. Each bullet should communicate one coherent engineering accomplishment or responsibility.
Optimize for truthful JD alignment, evidence, title relevance, recruiter readability and concise impact. Keyword coverage must never override credibility.
If audit feedback is supplied, correct failed gates without introducing technologies that violate the extended-tech rule. A missing audit keyword is not permission to fabricate experience.
Before returning JSON, silently self-check: exact 8/7/6 bullet counts; required JD concepts covered where truthfully supported; every extended technology actually appears in the JD; no inventory dumping; no invented tool chains; skills have experience evidence; metric limits satisfied; employer domains and chronology preserved.
Return valid JSON only with keys summary, skills, experience, and education."""

CONFIRMED_EXTENDED_TECHNOLOGIES=["BigQuery","Dagster","Apache Beam","Apache Flink","Kubernetes","ArgoCD","Helm","Istio"]
EXTENDED_ALIASES={
 "BigQuery":("bigquery","google bigquery"),
 "Dagster":("dagster",),
 "Apache Beam":("apache beam","beam"),
 "Apache Flink":("apache flink","flink"),
 "Kubernetes":("kubernetes","k8s"),
 "ArgoCD":("argocd","argo cd"),
 "Helm":("helm",),
 "Istio":("istio",),
}

def _jd_requested_extended(description):
    text=(description or "").lower()
    selected=[]
    for tech,aliases in EXTENDED_ALIASES.items():
        if any(re.search(r"(?<![a-z0-9])"+re.escape(alias)+r"(?![a-z0-9])",text) for alias in aliases):
            selected.append(tech)
    return selected

def build_prompt(job,profile,audit_feedback=None,coverage_plan=None):
    jd_extended=_jd_requested_extended(job.description)
    prompt={
      "task":"Produce one submission-ready, human-readable, strongly ATS-aligned resume for this complete JD. Use the smallest credible technology set that covers the JD.",
      "job":{"company":job.company,"title":job.title,"description":job.description},
      "candidate_evidence":profile,
      "pre_generation_coverage_plan":coverage_plan or {},
      "confirmed_extended_technology_inventory":CONFIRMED_EXTENDED_TECHNOLOGIES,
      "extended_technologies_explicitly_requested_by_jd":jd_extended,
      "extended_technology_policy":{
        "allowed_for_this_resume":jd_extended,
        "all_other_extended_technologies_must_be_omitted":True,
        "inventory_is_permission_not_checklist":True,
        "prefer_base_evidence_when_it_satisfies_jd":True,
        "do_not_create_projects_or_tool_chains_to_place_keywords":True
      },
      "tailoring_policy":{
        "jd_is_primary_target":True,"first_draft_must_be_final_quality":True,
        "prioritize_required_before_preferred":True,"use_exact_jd_terminology_when_truthful":True,
        "skills_need_experience_evidence":True,"preserve_employer_domain_context":True,
        "do_not_invent_metrics_certifications_business_results_or_architectures":True
      },
      "quality_rules":{
        "optimize_human_readability":True,"no_keyword_stuffing":True,"no_inventory_dumping":True,
        "no_repeated_boilerplate":True,"one_coherent_idea_per_bullet":True,"self_check_before_output":True,
        "fidelity_metric_bullets_max":2,"cigna_metric_bullets_max":2,"target_metric_bullets_max":0,
        "fidelity_bullets":8,"cigna_bullets":7,"target_bullets":6
      },
      "output_schema":{
        "summary":"3 concise recruiter-friendly sentences aligned to the target title and strongest supported JD requirements",
        "skills":{"category":["only JD-relevant, truthfully supported skills"]},
        "experience":[{"company":"exact employer","title":"exact title","dates":"exact dates","bullets":["credible JD-specific bullet grounded in candidate evidence"]}],
        "education":"preserve exactly"
      }
    }
    if audit_feedback:
        prompt["revision_mode"]=True;prompt["audit_feedback"]=audit_feedback
        prompt["task"]="Regenerate for the same JD, fixing legitimate audit gaps while preserving credibility. Do not add an extended technology unless it is in extended_technologies_explicitly_requested_by_jd."
    return prompt

def _extract_output_text(payload):
    if payload.get("output_text"):return payload["output_text"]
    chunks=[]
    for item in payload.get("output",[]):
        for part in item.get("content",[]):
            if part.get("type")=="output_text" and part.get("text"):chunks.append(part["text"])
    return "".join(chunks)

def generate_with_llm(job,profile,audit_feedback=None,coverage_plan=None):
    key=os.getenv("OPENAI_API_KEY") or os.getenv("RESUME_LLM_API_KEY")
    if not key:return None
    endpoint=os.getenv("RESUME_LLM_ENDPOINT","https://api.openai.com/v1/responses");model=os.getenv("RESUME_LLM_MODEL","gpt-5.6")
    body=json.dumps({"model":model,"instructions":SYSTEM_PROMPT,"input":json.dumps(build_prompt(job,profile,audit_feedback,coverage_plan)),"max_output_tokens":12000}).encode("utf-8")
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
