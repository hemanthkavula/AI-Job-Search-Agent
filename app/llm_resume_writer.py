from __future__ import annotations
import hashlib, json, os, re
from pathlib import Path
from urllib import request, error

SYSTEM_PROMPT = """You are an expert ATS resume writer for senior data engineering roles.
Your FIRST draft must be submission-ready. Perform the JD analysis and quality review internally before returning the resume.
Create a genuinely JD-specific resume, not a reordered or mechanically spun master resume.
Preserve all employers, titles, dates, locations, education, and certifications exactly.
Domain lock: Fidelity=financial services; Cigna=healthcare; Target=retail.
CLOUD TAILORING POLICY: Cigna's cloud is fixed to Azure and Target's cloud is fixed to AWS. Fidelity is the cloud-adaptive employer: when the JD is predominantly AWS, write Fidelity using AWS; when predominantly Azure, write Fidelity using Azure; when predominantly GCP, write Fidelity using GCP. Never change Cigna away from Azure or Target away from AWS. If the JD is cloud-neutral or genuinely multi-cloud, Fidelity MUST default to AWS. Do not make Fidelity multi-cloud merely because the JD says multi-cloud; use AWS as Fidelity's primary cloud unless the JD is predominantly and specifically Azure or predominantly and specifically GCP.
The master resume is reference evidence for identity, chronology, domain, scale, responsibilities, and truthful accomplishments; its existing bullet wording and cloud/tool choices are not the template for every generated resume. Generate Professional Experience from the current JD's requirements and the candidate's supported background, preserving fixed facts and avoiding fabricated specific accomplishments.
Use exactly 8 Fidelity bullets, 7 Cigna bullets, and 6 Target bullets.
Treat the complete job description as the primary tailoring target.
Before writing, internally identify the target title, REQUIRED technologies/responsibilities, then preferred technologies, architecture, orchestration, streaming/batch, modeling, governance/data quality and DevOps. Do not output this analysis.
The COMPLETE JOB DESCRIPTION is the primary technical tailoring source. The master profile is primarily the source of fixed factual identity and chronology; it is NOT a technical-keyword whitelist.
Use the supplied pre-generation coverage plan as the authoritative checklist for V1. Cover every item marked include, including material/required JD technologies, responsibilities, and concepts. Use exact JD terminology or a clear semantic equivalent where appropriate. Relevant JD technologies may appear in Technical Skills even when the master profile does not already list them.
CRITICAL TAILORING RULE: Technical Skills is not sufficient evidence of fit. For every tailored resume, materially rewrite Professional Experience against the current JD. Do not simply preserve the master bullets while changing Summary/Skills. Across Fidelity, Cigna, and Target, at least 6 bullets total must be clearly JD-specific, and each material hands-on requirement that is truthfully supportable must appear in one or more coherent experience bullets. When a JD-required technology is listed in Technical Skills and is supportable from the candidate background/allowed inventory, connect it to a relevant responsibility in Professional Experience rather than leaving it as an isolated keyword. Preserve employer domain truth and fixed facts, but vary responsibilities, emphasis, terminology, and bullet construction for the actual JD.
Do not force every Technical Skills keyword into Professional Experience. However, distinguish keyword coverage from demonstrated experience: when the JD explicitly requires hands-on implementation, configuration, architecture, administration, leadership, mentoring, or operational ownership of a platform/capability, the strongest relevant requirements must be demonstrated in Professional Experience bullets rather than appearing only in Summary/Technical Skills. Experience bullets should emphasize the most important JD requirements in technically coherent employer/domain contexts without becoming keyword dumps.
Do not invent a specific project, architecture, migration, deployment path, certification, metric, or business outcome solely to place a keyword. Never claim a false specific accomplishment.
If the JD presents true alternatives (for example Beam OR Flink OR Spark Streaming), do not automatically include every alternative; cover the requirement with the most relevant option unless the JD materially expects multiple technologies.
Distribute technical content coherently. Fidelity stays financial/trading, Cigna stays healthcare, Target stays retail/e-commerce.
Do not fabricate certifications, team sizes, project names, numerical outcomes, or business results. Never invent a metric merely to strengthen a bullet. Treat qualitative latency/scale claims such as sub-minute, sub-second, low-latency with a specific bound, millions/billions, or other numeric/near-numeric performance claims as metrics unless they are explicitly present in candidate evidence. Do NOT generate unapproved bounded or near-numeric claims such as sub-minute, sub-second, under-N, less-than-N, N+, or similar latency/scale/count claims. If the JD asks for low latency but candidate evidence has no approved bound, use non-quantified wording such as low-latency, near-real-time, timely, scalable, or performance-optimized instead.
STRICT METRIC RULE: Fidelity may have at most 2 metric-bearing bullets, Cigna at most 2, and Target must contain ZERO numeric scale, percentage, volume, latency, count, or performance metrics.
Never stack boilerplate clauses, create keyword-dump bullets, or repeat the same phrases. Each bullet should communicate one coherent engineering accomplishment or responsibility.
Optimize for complete-JD alignment, title relevance, recruiter readability and concise impact while preserving fixed factual history and avoiding fabricated specific accomplishments. For specialized roles (for example MDM, CRM/Power Platform, governance, platform engineering, IAM, AI/ML), make the experience section read like credible experience for that specialty, not a generic cloud data-engineering resume with specialty keywords added only to Summary/Skills. If the JD requires leadership or mentoring, demonstrate that responsibility naturally in at least one relevant experience bullet when it can be stated without inventing a team size or outcome.
If audit feedback is supplied, correct the exact failed gates. Missing material JD terminology should be incorporated naturally, but never by inventing a false specific accomplishment, metric, certification, employer, date, education fact, or project.
Before returning JSON, silently self-check: exact 8/7/6 bullet counts; all material/required JD concepts covered; exact relevant JD terminology used naturally; no keyword dumping; no invented specific accomplishments or tool-chain stories; metric limits satisfied; employer domains and chronology preserved.
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
      "task":"Produce the strongest submission-ready, human-readable resume for this complete JD. Treat pre_generation_coverage_plan.requirements as the authoritative checklist: naturally cover every requirement whose resume_action is include, and use exact JD terminology or a clear semantic equivalent while preserving fixed factual history.",
      "job":{"company":job.company,"title":job.title,"description":job.description},
      "candidate_fixed_facts_and_background":profile,
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
        "prioritize_required_before_preferred":True,"coverage_plan_is_authoritative_checklist":True,"use_exact_jd_terminology_when_truthful":True,
        "technical_skills_should_include_jd_required_technologies_and_tools":True,"professional_experience_must_be_materially_rewritten_for_each_jd":True,"minimum_jd_specific_experience_bullets":6,"skills_only_tailoring_is_forbidden":True,"material_jd_technologies_should_be_demonstrated_in_experience":True,"jd_may_drive_new_experience_content_beyond_master_resume":True,"master_resume_is_identity_and_chronology_anchor_not_content_ceiling":True,"specialized_role_experience_must_not_be_skills_only":True,"preserve_employer_domain_context":True,"cloud_strategy":{"Fidelity Investments":"ADAPT_TO_JD_PRIMARY_CLOUD_AWS_AZURE_OR_GCP","Cigna Healthcare":"AZURE_FIXED","Target Corporation":"AWS_FIXED"},"master_resume_is_reference_not_bullet_template":True,
        "do_not_invent_metrics_certifications_business_results_or_architectures":True
      },
      "quality_rules":{
        "optimize_human_readability":True,"no_keyword_stuffing":True,"no_inventory_dumping":True,
        "no_repeated_boilerplate":True,"one_coherent_idea_per_bullet":True,"self_check_before_output":True,
        "fidelity_metric_bullets_max":2,"cigna_metric_bullets_max":2,"target_metric_bullets_max":0,"never_create_unapproved_near_numeric_latency_or_scale_claims":True,
        "fidelity_bullets":8,"cigna_bullets":7,"target_bullets":6
      },
      "output_schema":{
        "summary":"3 concise recruiter-friendly sentences aligned to the target title and strongest supported JD requirements",
        "skills":{"category":["JD-relevant technical skills and terminology; do not treat the master profile as a technical whitelist"]},
        "experience":[{"company":"exact employer","title":"exact title","dates":"exact dates","bullets":["strong JD-specific bullet that preserves employer/domain facts and does not invent a false specific accomplishment or metric"]}],
        "education":"preserve exactly"
      }
    }
    if audit_feedback:
        prompt["revision_mode"]=True;prompt["audit_feedback"]=audit_feedback
        prompt["task"]="Regenerate for the same complete JD and correct every legitimate audit gap. Preserve fixed factual history, cover missing material JD terminology naturally, and do not invent specific accomplishments, metrics, certifications, projects, employers, dates, or education."
    return prompt

def _extract_output_text(payload):
    if payload.get("output_text"):return payload["output_text"]
    chunks=[]
    for item in payload.get("output",[]):
        for part in item.get("content",[]):
            if part.get("type")=="output_text" and part.get("text"):chunks.append(part["text"])
    return "".join(chunks)

CACHE_DIR=Path("generated")/"llm_resume_cache"

def _cache_key(model,prompt):
    """Hash the exact quality-driving inputs so identical resume requests never spend twice."""
    payload=json.dumps({"model":model,"instructions":SYSTEM_PROMPT,"prompt":prompt},sort_keys=True,separators=(",",":"),ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def _read_cache(cache_key):
    path=CACHE_DIR/f"{cache_key}.json"
    if not path.exists():return None
    try:
        value=json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value,dict) else None
    except Exception:return None

def _write_cache(cache_key,value):
    CACHE_DIR.mkdir(parents=True,exist_ok=True)
    path=CACHE_DIR/f"{cache_key}.json"
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value,ensure_ascii=False),encoding="utf-8")
    tmp.replace(path)

def generate_with_llm(job,profile,audit_feedback=None,coverage_plan=None):
    key=os.getenv("OPENAI_API_KEY") or os.getenv("RESUME_LLM_API_KEY")
    if not key:return None
    endpoint=os.getenv("RESUME_LLM_ENDPOINT","https://api.openai.com/v1/responses");model=os.getenv("RESUME_LLM_MODEL","gpt-5.6")
    prompt=build_prompt(job,profile,audit_feedback,coverage_plan)
    cache_key=_cache_key(model,prompt)
    cached=_read_cache(cache_key)
    if cached is not None:
        print(f"Resume LLM cache HIT | {cache_key[:12]} | API call skipped",flush=True)
        return cached
    print(f"Resume LLM cache MISS | {cache_key[:12]} | calling API",flush=True)
    body=json.dumps({"model":model,"instructions":SYSTEM_PROMPT,"input":json.dumps(prompt),"max_output_tokens":12000}).encode("utf-8")
    req=request.Request(endpoint,data=body,headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},method="POST")
    try:
        with request.urlopen(req,timeout=180) as resp:payload=json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail=exc.read().decode("utf-8",errors="replace");raise RuntimeError(f"OpenAI API HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:raise RuntimeError(f"OpenAI API connection error: {exc.reason}") from exc
    text=_extract_output_text(payload)
    if not text:raise RuntimeError(f"OpenAI Responses API returned no output text: {json.dumps(payload)[:1200]}")
    try:result=json.loads(text)
    except json.JSONDecodeError as exc:raise RuntimeError(f"OpenAI returned non-JSON resume output: {text[:1200]}") from exc
    if not isinstance(result,dict):raise RuntimeError("OpenAI returned a resume payload that is not a JSON object")
    _write_cache(cache_key,result)
    return result
