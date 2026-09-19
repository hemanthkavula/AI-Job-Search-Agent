from __future__ import annotations
import argparse, html, json, mimetypes
from pathlib import Path
from urllib.parse import quote
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
import uvicorn

ROOT=Path(__file__).resolve().parents[1]
LEDGER=ROOT/"generated"/"job_ledger.json"
app=FastAPI(title="AI Job Search Agent")

def _json(path,default):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:return default

def _resume_path(row):
    candidates=[
        row.get("resume_path"),row.get("pdf_path"),
        (row.get("queue_item") or {}).get("resume_path"),
        (row.get("retry_application") or {}).get("resume_path"),
    ]
    for value in candidates:
        if value:
            p=Path(value)
            if not p.is_absolute():p=ROOT/p
            if p.exists() and p.is_file():return p
    return None

def _portal(row):
    source=(row.get("source") or "").lower()
    url=row.get("url") or ""
    if "dice" in source or "dice.com" in url:return "Dice"
    if "workday" in source or "myworkdayjobs" in url:return "Workday"
    if "greenhouse" in source or "greenhouse" in url:return "Greenhouse"
    if "lever" in source or "lever.co" in url:return "Lever"
    if "smartrecruiters" in source:return "SmartRecruiters"
    if "ashby" in source:return "Ashby"
    if "ziprecruiter" in source:return "ZipRecruiter"
    return row.get("source") or "Company site"

def _stage(status):
    s=status or "DISCOVERED"
    if s in {"SUBMITTED","SUBMITTED_CONFIRMED"}:return "Applied"
    if s=="SUBMISSION_ATTEMPTED":return "Verify submission"
    if s=="READY_TO_APPLY":return "Ready to apply"
    if s in {"APPLICATION_IN_PROGRESS","IN_PROGRESS"}:return "Applying"
    if s in {"RETRY_APPLICATION","RETRY_RESUME_GENERATION"}:return "Retrying"
    if s in {"MANUAL_ACTION_REQUIRED","SECURITY_BLOCKED"}:return "Needs attention"
    if s in {"PERMANENT_SKIP","HOLD_ATS_REVIEW","HOLD_ARTIFACT_VALIDATION"}:return "Not applying"
    if "RESUME" in s:return "Resume"
    return "Processing"

def _jobs():
    ledger=_json(LEDGER,{"jobs":{}})
    out=[]
    for key,row in (ledger.get("jobs") or {}).items():
        status=row.get("application_status") or "DISCOVERED"
        # Application dashboard: hide raw discovery noise and show only jobs that
        # entered the resume/application workflow.
        relevant=bool(
            row.get("queue_item") or row.get("retry_application") or row.get("resume_path") or
            row.get("pdf_path") or row.get("application_result") or
            status in {"READY_TO_APPLY","APPLICATION_IN_PROGRESS","IN_PROGRESS","RETRY_APPLICATION",
                       "RETRY_RESUME_GENERATION","SUBMISSION_ATTEMPTED","SUBMITTED","SUBMITTED_CONFIRMED",
                       "MANUAL_ACTION_REQUIRED","SECURITY_BLOCKED"}
        )
        if not relevant:continue
        rp=_resume_path(row)
        out.append({
            "key":key,"company":row.get("company") or "Unknown company",
            "title":row.get("title") or "Unknown role","status":status,"stage":_stage(status),
            "source":row.get("source") or "","portal":_portal(row),
            "url":row.get("url") or (row.get("queue_item") or {}).get("url") or "",
            "resume":rp.name if rp else None,
            "resume_url":"/resume/"+quote(key,safe="") if rp else None,
            "updated":row.get("last_seen") or row.get("first_seen"),
            "reason":row.get("application_reason") or "",
        })
    out.sort(key=lambda x:x.get("updated") or "",reverse=True)
    return out

@app.get("/api/applications")
def applications():
    rows=_jobs()
    return {"applications":rows,"counts":{
        "all":len(rows),"queue":sum(x["stage"] in {"Ready to apply","Applying"} for x in rows),
        "applied":sum(x["stage"]=="Applied" for x in rows),
        "attention":sum(x["stage"] in {"Needs attention","Verify submission"} for x in rows),
    }}

@app.get("/resume/{job_key:path}")
def resume(job_key:str):
    ledger=_json(LEDGER,{"jobs":{}})
    row=(ledger.get("jobs") or {}).get(job_key)
    if not row:raise HTTPException(404,"Job not found")
    p=_resume_path(row)
    if not p:raise HTTPException(404,"Resume not available")
    return FileResponse(p,media_type=mimetypes.guess_type(p.name)[0] or "application/octet-stream",filename=p.name)

@app.get("/",response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>My Job Applications</title><style>
*{box-sizing:border-box}body{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;background:#f6f7fb;color:#182033}
.top{padding:26px max(20px,5vw);background:#101828;color:#fff}.top h1{margin:0;font-size:26px}.top p{color:#b7c0d1;margin:7px 0 0}
main{padding:22px max(16px,5vw)}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}
.stat,.job{background:#fff;border:1px solid #e4e8f0;border-radius:14px}.stat{padding:16px}.stat span{font-size:12px;color:#667085;font-weight:700;text-transform:uppercase}.stat b{display:block;font-size:28px;margin-top:5px}
.controls{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 16px}.controls input,.controls select{padding:11px 13px;border:1px solid #d7dce5;border-radius:9px;background:#fff;font-size:14px}
.controls input{flex:1;min-width:220px}.jobs{display:grid;gap:12px}.job{padding:18px;display:grid;grid-template-columns:minmax(240px,2fr) minmax(120px,.7fr) minmax(150px,.8fr) auto;gap:18px;align-items:center}
.company{font-weight:800;font-size:16px}.title{margin-top:4px;color:#475467}.meta{font-size:12px;color:#7a8495;margin-top:7px}.label{font-size:11px;color:#8490a3;text-transform:uppercase;font-weight:800;margin-bottom:5px}.badge{display:inline-block;padding:6px 9px;border-radius:999px;background:#eef2f6;font-size:12px;font-weight:800}
.applied{background:#dcfce7;color:#166534}.ready-to-apply,.applying{background:#dbeafe;color:#1d4ed8}.needs-attention,.verify-submission{background:#fef3c7;color:#92400e}.retrying{background:#f3e8ff;color:#7e22ce}
.actions{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}.btn{display:inline-block;padding:9px 12px;border-radius:8px;text-decoration:none;font-size:13px;font-weight:700;background:#101828;color:#fff}.btn.secondary{background:#fff;color:#344054;border:1px solid #d0d5dd}.empty{background:#fff;padding:35px;border-radius:14px;text-align:center;color:#667085}
@media(max-width:850px){.stats{grid-template-columns:repeat(2,1fr)}.job{grid-template-columns:1fr}.actions{justify-content:flex-start}}
@media(max-width:480px){.stats{grid-template-columns:1fr 1fr}.top{padding:20px}.job{padding:15px}}
</style></head><body><div class="top"><h1>My Job Applications</h1><p>Resume → queue → application → submission. Live from the agent ledger.</p></div><main>
<div class="stats"><div class="stat"><span>In pipeline</span><b id="all">0</b></div><div class="stat"><span>Queue</span><b id="queue">0</b></div><div class="stat"><span>Applied</span><b id="applied">0</b></div><div class="stat"><span>Needs attention</span><b id="attention">0</b></div></div>
<div class="controls"><input id="search" placeholder="Search company or role"><select id="filter"><option value="">All statuses</option><option>Ready to apply</option><option>Applying</option><option>Applied</option><option>Needs attention</option><option>Verify submission</option><option>Retrying</option></select></div>
<div class="jobs" id="jobs"></div></main><script>
let rows=[];const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const cls=s=>String(s).toLowerCase().replaceAll(" ","-");
function render(){let q=document.getElementById("search").value.toLowerCase(),f=document.getElementById("filter").value;let x=rows.filter(r=>(!q||(r.company+" "+r.title).toLowerCase().includes(q))&&(!f||r.stage===f));document.getElementById("jobs").innerHTML=x.map(r=>`<div class="job"><div><div class="company">${esc(r.company)}</div><div class="title">${esc(r.title)}</div><div class="meta">${esc(r.portal)} • updated ${r.updated?new Date(r.updated).toLocaleString():"—"}</div></div><div><div class="label">Status</div><span class="badge ${cls(r.stage)}">${esc(r.stage)}</span></div><div><div class="label">Resume</div>${r.resume?`<a href="${r.resume_url}" target="_blank">${esc(r.resume)}</a>`:"Not generated yet"}</div><div class="actions">${r.url?`<a class="btn" href="${esc(r.url)}" target="_blank">Open application</a>`:""}${r.resume_url?`<a class="btn secondary" href="${r.resume_url}" target="_blank">Open resume</a>`:""}</div></div>`).join("")||'<div class="empty">No application-pipeline jobs match this view.</div>'}
async function load(){let d=await fetch("/api/applications",{cache:"no-store"}).then(r=>r.json());rows=d.applications;Object.entries(d.counts).forEach(([k,v])=>document.getElementById(k).textContent=v);render()}
search.oninput=render;filter.onchange=render;load();setInterval(load,5000);
</script></body></html>""")

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--host",default="127.0.0.1");ap.add_argument("--port",type=int,default=8765);a=ap.parse_args()
    uvicorn.run("app.dashboard:app",host=a.host,port=a.port,reload=False)

if __name__=="__main__":main()
