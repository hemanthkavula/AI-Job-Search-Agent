from __future__ import annotations
import argparse, html, json, mimetypes
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
import uvicorn

ROOT=Path(__file__).resolve().parents[1]
LEDGER=ROOT/"generated"/"job_ledger.json"
CONFIRMED=ROOT/"data"/"confirmed_applications.json"
app=FastAPI(title="AI Job Search Agent")

def _json(path,default):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:return default

def _resume_path(row):
    # Show only the PDF artifact that can be submitted to an ATS.
    candidates=[
        row.get("pdf_path"),
        (row.get("queue_item") or {}).get("resume_path"),
        (row.get("retry_application") or {}).get("resume_path"),
        row.get("resume_path"),
    ]
    for value in candidates:
        if value:
            p=Path(value)
            if not p.is_absolute():p=ROOT/p
            if p.suffix.lower()==".pdf" and p.exists() and p.is_file():return p
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

def _applied_at(row):
    return row.get("submitted_at") or row.get("application_submitted_at") or (row.get("submission_confirmation") or {}).get("confirmed_at")

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
    confirmed=_json(CONFIRMED,{"applications":[]}).get("applications") or []
    confirmed_by_external={x.get("external_id"):x for x in confirmed if x.get("external_id")}
    confirmed_by_name={(str(x.get("company") or "").lower(),str(x.get("title") or "").lower()):x for x in confirmed}
    out=[]; matched=set()
    active={"READY_TO_APPLY","APPLICATION_IN_PROGRESS","IN_PROGRESS","RETRY_APPLICATION",
            "RETRY_RESUME_GENERATION","SUBMISSION_ATTEMPTED","SUBMITTED","SUBMITTED_CONFIRMED",
            "MANUAL_ACTION_REQUIRED","SECURITY_BLOCKED"}
    for key,row in (ledger.get("jobs") or {}).items():
        name_key=(str(row.get("company") or "").lower(),str(row.get("title") or "").lower())
        hist=None
        for eid in row.get("external_ids") or []:
            if eid in confirmed_by_external:hist=confirmed_by_external[eid];break
        hist=hist or confirmed_by_name.get(name_key)
        status=(hist or {}).get("status") or row.get("application_status") or "DISCOVERED"
        if status not in active:continue
        rp=_resume_path(row)
        resume_name=(hist or {}).get("resume") or (rp.name if rp else None)
        resume_url="/resume/"+quote(key,safe="") if rp else None
        if hist:matched.add((hist.get("company"),hist.get("title")))
        out.append({
            "key":key,"company":row.get("company") or (hist or {}).get("company") or "Unknown company",
            "title":row.get("title") or (hist or {}).get("title") or "Unknown role",
            "status":status,"stage":_stage(status),"source":row.get("source") or "",
            "portal":(hist or {}).get("portal") or _portal(row),
            "url":row.get("url") or (row.get("queue_item") or {}).get("url") or "",
            "resume":resume_name,"resume_url":resume_url,
            "updated":row.get("last_seen") or row.get("first_seen"),
            "applied_at":(hist or {}).get("submitted_date") or _applied_at(row),
            "reason":(hist or {}).get("confirmation") or row.get("application_reason") or "",
        })
    for hist in confirmed:
        if (hist.get("company"),hist.get("title")) in matched:continue
        out.append({
            "key":"history:"+str(hist.get("external_id") or hist.get("company"))+":"+str(hist.get("title")),
            "company":hist.get("company") or "Unknown company","title":hist.get("title") or "Unknown role",
            "status":"SUBMITTED_CONFIRMED","stage":"Applied","source":"","portal":hist.get("portal") or "Company portal",
            "url":hist.get("url") or "","resume":hist.get("resume"),"resume_url":None,
            "updated":hist.get("submitted_date"),"applied_at":hist.get("submitted_date"),
            "reason":hist.get("confirmation") or "Confirmed submitted."
        })
    out.sort(key=lambda x:x.get("updated") or x.get("applied_at") or "",reverse=True)
    return out

@app.get("/api/applications")
def applications():
    rows=_jobs()
    return {"applications":rows,"counts":{
        "all":len(rows),"queue":sum(x["stage"] in {"Ready to apply","Applying"} for x in rows),
        "applied":sum(x["stage"]=="Applied" for x in rows),
        "attention":sum(x["stage"] in {"Needs attention","Verify submission"} for x in rows),
    }}

@app.post("/api/applications/{job_key:path}/confirm-submitted")
def confirm_submitted(job_key:str):
    ledger=_json(LEDGER,{"jobs":{}})
    row=(ledger.get("jobs") or {}).get(job_key)
    if not row:raise HTTPException(404,"Job not found")
    now=datetime.now(timezone.utc).isoformat()
    row["application_status"]="SUBMITTED_CONFIRMED"
    row["application_result"]="SUBMITTED"
    row["submitted_at"]=row.get("submitted_at") or now
    row["last_seen"]=now
    row["submission_confirmed_manually"]=True
    row["application_reason"]="Submission confirmed in the employer/application portal."
    row["retry_application"]=None
    LEDGER.write_text(json.dumps(ledger,indent=2),encoding="utf-8")
    return {"ok":True,"status":"SUBMITTED_CONFIRMED","submitted_at":row["submitted_at"]}

@app.get("/resume/{job_key:path}")
def resume(job_key:str):
    ledger=_json(LEDGER,{"jobs":{}})
    row=(ledger.get("jobs") or {}).get(job_key)
    if not row:raise HTTPException(404,"Job not found")
    p=_resume_path(row)
    if not p:raise HTTPException(404,"Resume not available")
    if p.suffix.lower()!=".pdf":raise HTTPException(404,"PDF resume not available")
    return FileResponse(p,media_type="application/pdf",headers={"Content-Disposition":f'inline; filename="{p.name}"'})

@app.get("/",response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Application Tracker</title><style>
*{box-sizing:border-box}body{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;background:#f7f8fb;color:#101828}header{padding:24px 5%;background:#fff;border-bottom:1px solid #e4e7ec;display:flex;justify-content:space-between;align-items:center}h1{font-size:23px;margin:0}.sub{font-size:13px;color:#667085;margin-top:5px}.live{font-size:12px;color:#027a48;background:#ecfdf3;padding:7px 10px;border-radius:20px;font-weight:700}
main{padding:22px 5%}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}.stat{background:#fff;border:1px solid #e4e7ec;border-radius:12px;padding:16px}.stat span{font-size:11px;color:#667085;text-transform:uppercase;font-weight:800}.stat b{font-size:26px;display:block;margin-top:5px}
.toolbar{display:flex;gap:10px;margin-bottom:14px}.toolbar input,.toolbar select{border:1px solid #d0d5dd;background:#fff;border-radius:9px;padding:10px 12px;font-size:14px}.toolbar input{flex:1}
.table{background:#fff;border:1px solid #e4e7ec;border-radius:12px;overflow:hidden}.row{display:grid;grid-template-columns:minmax(220px,1.5fr) 130px minmax(180px,1fr) 110px 190px;gap:14px;align-items:center;padding:15px 18px;border-bottom:1px solid #eef0f3}.row:last-child{border-bottom:0}.head{background:#f9fafb;color:#667085;font-size:11px;text-transform:uppercase;font-weight:800;padding-top:11px;padding-bottom:11px}.company{font-weight:800}.role{font-size:13px;color:#475467;margin-top:3px}.portal{font-size:12px;color:#667085;margin-top:4px}.badge{display:inline-block;padding:6px 9px;border-radius:20px;font-size:11px;font-weight:800;background:#f2f4f7}.applied{background:#ecfdf3;color:#027a48}.ready-to-apply,.applying{background:#eff8ff;color:#175cd3}.needs-attention,.verify-submission{background:#fffaeb;color:#b54708}.retrying{background:#f4f3ff;color:#5925dc}.resume{font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.date{font-size:12px;color:#475467}.actions{display:flex;gap:7px}.btn{border:1px solid #d0d5dd;background:#fff;color:#344054;text-decoration:none;padding:8px 10px;border-radius:8px;font-size:12px;font-weight:700;white-space:nowrap}.btn.primary{background:#101828;color:#fff;border-color:#101828}.empty{padding:35px;text-align:center;color:#667085}
@media(max-width:900px){header{padding:18px 4%}main{padding:16px 4%}.stats{grid-template-columns:1fr 1fr}.head{display:none}.row{grid-template-columns:1fr}.table{background:transparent;border:0}.row{background:#fff;border:1px solid #e4e7ec;border-radius:12px;margin-bottom:10px}.resume{white-space:normal}.actions{flex-wrap:wrap}}
</style></head><body><header><div><h1>Application Tracker</h1><div class="sub">Only jobs that reached the application workflow</div></div><div class="live">● Live</div></header><main>
<div class="stats"><div class="stat"><span>Application pipeline</span><b id="all">0</b></div><div class="stat"><span>Ready / applying</span><b id="queue">0</b></div><div class="stat"><span>Submitted</span><b id="applied">0</b></div><div class="stat"><span>Needs attention</span><b id="attention">0</b></div></div>
<div class="toolbar"><input id="search" placeholder="Search company or role"><select id="filter"><option value="">All application statuses</option><option>Applied</option><option>Ready to apply</option><option>Applying</option><option>Retrying</option><option>Needs attention</option><option>Verify submission</option></select></div>
<div class="table"><div class="row head"><div>Company / role</div><div>Status</div><div>Resume</div><div>Applied</div><div>Actions</div></div><div id="jobs"></div></div></main><script>
let rows=[];const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));const cls=s=>String(s).toLowerCase().replaceAll(" ","-");const dt=v=>{if(!v)return"—";let d=new Date(v.length===10?v+"T12:00:00":v);return isNaN(d)?v:d.toLocaleDateString()};
function render(){let q=search.value.toLowerCase(),f=filter.value,x=rows.filter(r=>(!q||(r.company+" "+r.title).toLowerCase().includes(q))&&(!f||r.stage===f));jobs.innerHTML=x.map(r=>`<div class="row"><div><div class="company">${esc(r.company)}</div><div class="role">${esc(r.title)}</div><div class="portal">${esc(r.portal)}</div></div><div><span class="badge ${cls(r.stage)}">${esc(r.stage)}</span></div><div class="resume">${r.resume_url?"PDF ready":"PDF unavailable"}</div><div class="date">${r.stage==="Applied"?dt(r.applied_at):"—"}</div><div class="actions">${r.resume_url?`<a class="btn" href="${r.resume_url}" target="_blank">View resume</a>`:""}${r.url?`<a class="btn primary" href="${esc(r.url)}" target="_blank">Job portal</a>`:""}</div></div>`).join("")||'<div class="empty">No applications in this view.</div>'}
async function load(){let d=await fetch("/api/applications",{cache:"no-store"}).then(r=>r.json());rows=d.applications;Object.entries(d.counts).forEach(([k,v])=>document.getElementById(k).textContent=v);render()}search.oninput=render;filter.onchange=render;load();setInterval(load,5000);
</script></body></html>""")

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--host",default="127.0.0.1");ap.add_argument("--port",type=int,default=8765);a=ap.parse_args()
    uvicorn.run("app.dashboard:app",host=a.host,port=a.port,reload=False)

if __name__=="__main__":main()
