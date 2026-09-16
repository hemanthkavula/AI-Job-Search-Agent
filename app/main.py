from fastapi import FastAPI
from app.models import JobInput, JobAnalysis
from app.config import load_profile
from app.scoring import analyze_job
from app.tailoring import build_tailoring_plan
from app.db import init_db, save_job

app = FastAPI(title="AI Job Search Agent", version="0.1.0")
profile = load_profile()

@app.on_event("startup")
def startup():
    init_db()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/profile")
def get_profile():
    safe = dict(profile)
    safe.pop("contact", None)
    return safe

@app.post("/jobs/analyze", response_model=JobAnalysis)
def analyze(job: JobInput):
    result = analyze_job(job, profile)
    save_job(job, result)
    return result

@app.post("/jobs/tailoring-plan")
def tailoring_plan(job: JobInput):
    analysis = analyze_job(job, profile)
    return {"analysis": analysis, "tailoring_plan": build_tailoring_plan(job, analysis, profile)}
