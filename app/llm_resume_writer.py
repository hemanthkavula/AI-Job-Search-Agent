from __future__ import annotations
import json, os
from urllib import request

SYSTEM_PROMPT = """You are an expert ATS resume writer for senior data engineering roles.
Create a genuinely JD-specific resume, not a reordered or mechanically spun master resume.
Preserve all employers, titles, dates, locations, education, and certifications exactly.
Domain lock: Fidelity=financial services; Cigna=healthcare; Target=retail.
Use exactly 8 Fidelity bullets, 7 Cigna bullets, and 6 Target bullets.
Use exact JD terminology naturally when supported by the candidate evidence.
Never invent employer-specific use of a technology, project, metric, responsibility, or result.
Never stack boilerplate clauses or repeat phrases across bullets.
Preserve the meaning and strength of documented accomplishments.
Return JSON only."""

def build_prompt(job, profile, audit_feedback=None):
    return {
      "task":"Generate a fresh, human-readable, ATS-focused resume tailored to this JD.",
      "job":{"company":job.company,"title":job.title,"description":job.description},
      "candidate_evidence":profile,
      "audit_feedback":audit_feedback or {},
      "output_schema":{
        "summary":"3 concise sentences",
        "skills":{"category":["skill"]},
        "experience":[{"company":"exact employer","title":"exact title","dates":"exact dates","bullets":["new JD-specific wording grounded only in evidence"]}],
        "education":"preserve exactly"
      }
    }

def generate_with_llm(job, profile, audit_feedback=None):
    """Provider-neutral hook. Set RESUME_LLM_ENDPOINT and RESUME_LLM_API_KEY.
    Endpoint must accept OpenAI-compatible JSON and return choices[0].message.content."""
    endpoint=os.getenv("RESUME_LLM_ENDPOINT")
    key=os.getenv("RESUME_LLM_API_KEY")
    model=os.getenv("RESUME_LLM_MODEL","gpt-5.6")
    if not endpoint or not key:
        return None
    body=json.dumps({"model":model,"messages":[
      {"role":"system","content":SYSTEM_PROMPT},
      {"role":"user","content":json.dumps(build_prompt(job,profile,audit_feedback))}
    ],"response_format":{"type":"json_object"}}).encode()
    req=request.Request(endpoint,data=body,headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"})
    with request.urlopen(req,timeout=120) as resp:
        payload=json.loads(resp.read().decode())
    return json.loads(payload["choices"][0]["message"]["content"])
