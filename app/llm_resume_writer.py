from __future__ import annotations
import json, os
from urllib import request

SYSTEM_PROMPT = """You are an expert ATS resume writer for senior data engineering roles.
Create a genuinely JD-specific resume, not a reordered or mechanically spun master resume.
Preserve all employers, titles, dates, locations, education, and certifications exactly.
Domain lock: Fidelity=financial services; Cigna=healthcare; Target=retail.
Use exactly 8 Fidelity bullets, 7 Cigna bullets, and 6 Target bullets.
Use exact JD terminology naturally only when supported by candidate evidence.
Never invent employer-specific use of a technology, project, metric, responsibility, or result.
Never add unsupported JD-only technologies merely to increase keyword coverage.
Never stack boilerplate clauses or repeat phrases across bullets.
Preserve the meaning and strength of documented accomplishments.
Fidelity may contain at most 2 metric-bearing bullets; Cigna at most 2; Target must contain zero fabricated metrics.
Return valid JSON only."""


def build_prompt(job, profile, audit_feedback=None):
    return {
        "task": "Generate a fresh, human-readable, ATS-focused resume tailored to this JD.",
        "job": {"company": job.company, "title": job.title, "description": job.description},
        "candidate_evidence": profile,
        "audit_feedback": audit_feedback or {},
        "quality_rules": {
            "no_keyword_stuffing": True,
            "no_repeated_boilerplate": True,
            "no_unsupported_employer_claims": True,
            "preserve_fact_strength": True,
            "fidelity_bullets": 8,
            "cigna_bullets": 7,
            "target_bullets": 6,
        },
        "output_schema": {
            "summary": "3 concise recruiter-friendly sentences",
            "skills": {"category": ["verified/relevant skill"]},
            "experience": [
                {
                    "company": "exact employer",
                    "title": "exact title",
                    "dates": "exact dates",
                    "bullets": ["fresh JD-specific wording grounded only in evidence"],
                }
            ],
            "education": "preserve exactly",
        },
    }


def _extract_output_text(payload):
    if payload.get("output_text"):
        return payload["output_text"]
    chunks = []
    for item in payload.get("output", []):
        for part in item.get("content", []):
            if part.get("type") == "output_text" and part.get("text"):
                chunks.append(part["text"])
    return "".join(chunks)


def generate_with_llm(job, profile, audit_feedback=None):
    """Generate structured resume content through the OpenAI Responses API.

    Required environment variable: OPENAI_API_KEY.
    Optional: RESUME_LLM_MODEL (defaults to gpt-5.6).
    """
    key = os.getenv("OPENAI_API_KEY") or os.getenv("RESUME_LLM_API_KEY")
    if not key:
        return None

    endpoint = os.getenv("RESUME_LLM_ENDPOINT", "https://api.openai.com/v1/responses")
    model = os.getenv("RESUME_LLM_MODEL", "gpt-5.6")
    body = json.dumps(
        {
            "model": model,
            "instructions": SYSTEM_PROMPT,
            "input": json.dumps(build_prompt(job, profile, audit_feedback)),
            "reasoning": {"effort": "medium"},
            "text": {"format": {"type": "json_object"}},
        }
    ).encode("utf-8")

    req = request.Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=180) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    text = _extract_output_text(payload)
    if not text:
        raise RuntimeError("OpenAI Responses API returned no output text")
    return json.loads(text)
