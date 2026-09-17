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
For every materially relevant JD technology from the base evidence or confirmed extended inventory, include the exact or standard technology name in Technical Skills and demonstrate it naturally in at least one Professional Experience bullet. Do not leave important JD technologies as skills-only keywords.
If the JD gives alternatives such as Beam/Flink/Spark Streaming or Dagster/Airflow, prioritize broad coverage when it remains readable: demonstrate confirmed technologies naturally across the three employers instead of keyword dumping them into one bullet.
Distribute JD technologies only where technically coherent. Fidelity stays financial/trading, Cigna stays healthcare, and Target stays retail/e-commerce.
Prefer coherent combinations: streaming tools with event pipelines; orchestration tools with DAG scheduling; BigQuery/Snowflake/Databricks with data platform or analytics workloads; Kubernetes/Helm/ArgoCD/Istio with containerized data-platform deployment; Terraform with infrastructure automation.
Do not fabricate certifications, team sizes, project names, numerical outcomes, or business results. Never invent a metric merely to strengthen a bullet.
STRICT METRIC RULE: Fidelity may have at most 2 metric-bearing bullets, Cigna at most 2, and Target must contain ZERO numeric scale, percentage, volume, latency, count, or performance metrics unless an audit retry explicitly says an approved metric is allowed. For Target, prefer qualitative scale wording such as high-volume, enterprise-scale, or large retail datasets instead of numbers.
Never stack boilerplate clauses, create keyword-dump bullets, or repeat the same phrases across bullets. Each bullet should communicate one coherent engineering accomplishment or responsibility and remain easy for a recruiter to read.
Optimize simultaneously for ATS alignment, JD technology evidence, and human readability. A high keyword score is not sufficient if the resume reads unnaturally.
When audit_feedback is supplied, treat missing_jd_keywords, skills_without_experience_evidence, metric_violations, repeated_phrases, repeated_opening_verbs, and human/readability scores as mandatory correction instructions for the next version.
Return valid JSON only with keys summary, skills, experience, and education."""

CONFIRMED_EXTENDED_TECHNOLOGIES=["BigQuery","Dagster","Apache Beam","Apache Flink","Kubernetes","ArgoCD","Helm","Istio"]

def build_prompt(job,profile,audit_feedback=None):
    return {"task":"Generate a fresh, human-readable, ATS-focused resume tailored directly to this JD.","job":{"company":job.company,"title":job.title,"description":job.description},"candidate_evidence":profile,"confirmed_extended_technology_inventory":CONFIRMED_EXTENDED_TECHNOLOGIES,"audit_feedback":audit_feedback or {},"tailoring_policy":{"jd_is_primary_target":True,"include_relevant_jd_required_and_preferred_skills":True,"use_confirmed_extended_technologies_when_jd_relevant":True,"skills_need_experience_evidence":True,"integrate_jd_technologies_naturally_into_experience":True,"preserve_employer_domain_context":True,"do_not_invent_metrics_certifications_or_business_results":True},"quality_rules":{"target_internal_ats_score":95,"target_technology_evidence_coverage":95,"target_human_quality_score":90,"optimize_human_readability":True,"no_keyword_stuffing":True,"no_repeated_boilerplate":True,"one_coherent_idea_per_bullet":True,"fidelity_metric_bullets_max":2,"cigna_metric_bullets_max":2,"target_metric_bullets_max":0,"fidelity_bullets":8,"cigna_bullets":7,"target_bullets":6},"output_schema":{"summary":"3 concise recruiter-friendly sentences using important JD terminology naturally","skills":{"category":["JD-relevant skill from base or confirmed extended technology inventory"]},"experience":[{"company":"exact employer","title":"exact title","dates":"exact dates","bullets":["fresh coherent JD-specific bullet with natural evidence for relevant listed technologies"]}],"education":"preserve exactly"}}

def _extract_output_text(payload):
    if payload.get("output_text"):return payload["output_text"]
    chunks=[]
    for item in payload.get("output",[]):
        for part in item.get("content",[]):
            if part.get("type")=="output_text" and part.get("text"):chunks.append(part["text"])
    return "".join(chunks)

def generate_with_llm(job,profile,audit_feedback=None):
    key=os.getenv("OPENAI_API_KEY") or os.getenv("RESUME_LLM_API_KEY")
    if not key:return None
    endpoint=os.getenv("RESUME_LLM_ENDPOINT","https://api.openai.com/v1/responses");model=os.getenv("RESUME_LLM_MODEL","gpt-5.6")
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
