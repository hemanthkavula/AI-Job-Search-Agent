from __future__ import annotations
from app.sources.greenhouse import fetch_jobs as greenhouse_jobs
from app.sources.lever import fetch_jobs as lever_jobs
from app.sources.ashby import fetch_jobs as ashby_jobs
from app.sources.smartrecruiters import fetch_jobs as smartrecruiters_jobs

def discover(config: dict) -> list[dict]:
    jobs=[]
    errors=[]
    for src in config.get("greenhouse",[]):
        try: jobs.extend(greenhouse_jobs(src["board_token"]))
        except Exception as e: errors.append({"source":"greenhouse","company":src.get("company"),"error":str(e)})
    for src in config.get("lever",[]):
        try: jobs.extend(lever_jobs(src["site"]))
        except Exception as e: errors.append({"source":"lever","company":src.get("company"),"error":str(e)})
    for src in config.get("ashby",[]):
        try: jobs.extend(ashby_jobs(src["board_name"]))
        except Exception as e: errors.append({"source":"ashby","company":src.get("company"),"error":str(e)})
    for src in config.get("smartrecruiters",[]):
        identifier=src.get("company_identifier") or src.get("identifier")
        try:
            if not identifier: raise ValueError("Missing company_identifier")
            jobs.extend(smartrecruiters_jobs(identifier))
        except Exception as e: errors.append({"source":"smartrecruiters","company":src.get("company") or identifier,"error":str(e)})

    dedup={}
    for job in jobs:
        dedup[job["external_id"]]=job
    return list(dedup.values()), errors
