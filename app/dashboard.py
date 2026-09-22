from __future__ import annotations
import argparse, json, os, io, shutil, tarfile, tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse
import uvicorn

ROOT=Path(__file__).resolve().parents[1]
STATE_DIR=Path(os.getenv("JOB_AGENT_STATE_DIR", ROOT/"generated"))
LEDGER=STATE_DIR/"job_ledger.json"
CONFIRMED=STATE_DIR/"confirmed_applications.json"
HIDDEN=STATE_DIR/"hidden_applications.json"
app=FastAPI(title="AI Job Search Agent")

def _json(path,default):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:return default

def _save_confirmed(data):
    CONFIRMED.parent.mkdir(parents=True,exist_ok=True)
    CONFIRMED.write_text(json.dumps(data,indent=2),encoding="utf-8")

def _hidden_keys():
    data=_json(HIDDEN,{"job_keys":[]})
    return set(data.get("job_keys") or [])

def _hide_job(job_key):
    keys=_hidden_keys()
    keys.add(job_key)
    HIDDEN.parent.mkdir(parents=True,exist_ok=True)
    HIDDEN.write_text(json.dumps({"job_keys":sorted(keys)},indent=2),encoding="utf-8")

def _resume_path(row):
    candidates=[
        row.get("pdf_path"),
        (row.get("queue_item") or {}).get("resume_path"),
        (row.get("retry_application") or {}).get("resume_path"),
        row.get("resume_path"),
    ]
    for value in candidates:
        if value:
            p=Path(value)
            if not p.is_absolute():
                local=ROOT/p
                persisted=STATE_DIR.parent/p
                p=persisted if persisted.exists() else local
            elif not p.exists():
                # Queue entries created on ephemeral GitHub runners can contain
                # absolute /home/runner/.../generated/... paths. After syncing to
                # Railway, remap that generated-relative suffix onto STATE_DIR.
                parts=p.parts
                try:
                    generated_idx=parts.index("generated")
                except ValueError:
                    generated_idx=-1
                if generated_idx >= 0:
                    relative=Path(*parts[generated_idx+1:])
                    persisted=STATE_DIR/relative
                    if persisted.exists():
                        p=persisted
            if p.suffix.lower()==".pdf" and p.exists() and p.is_file():return p
    return None

def _portal(row):
    source=(row.get("source") or "").lower();url=row.get("url") or ""
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

def _confirmed_map():
    data=_json(CONFIRMED,{"applications":[]})
    apps=data.get("applications") or []
    return data,apps

def _resume_path_from_confirmed(hist):
    if not hist:return None
    value=hist.get("resume_path")
    if value:
        p=Path(value)
        if not p.is_absolute():
            p=STATE_DIR/p
        if p.suffix.lower()==".pdf" and p.exists() and p.is_file():
            return p
    # Older applied records did not persist the resume path. Recover the
    # validated artifact from another ledger record for the same company/title.
    company=str(hist.get("company") or "").strip().lower()
    title=str(hist.get("title") or "").strip().lower()
    if not company or not title:return None
    ledger=_json(LEDGER,{"jobs":{}})
    for row in (ledger.get("jobs") or {}).values():
        if str(row.get("company") or "").strip().lower()!=company:continue
        if str(row.get("title") or "").strip().lower()!=title:continue
        p=_resume_path(row)
        if p:return p
    return None

def _jobs():
    ledger=_json(LEDGER,{"jobs":{}})
    _,confirmed=_confirmed_map()
    by_key={x.get("job_key"):x for x in confirmed if x.get("job_key")}
    by_name={(str(x.get("company") or "").lower(),str(x.get("title") or "").lower()):x for x in confirmed}
    out=[]
    hidden=_hidden_keys()
    active={"READY_TO_APPLY","APPLICATION_IN_PROGRESS","IN_PROGRESS","RETRY_APPLICATION","RETRY_RESUME_GENERATION","SUBMISSION_ATTEMPTED","SUBMITTED","SUBMITTED_CONFIRMED","MANUAL_ACTION_REQUIRED","SECURITY_BLOCKED"}
    for key,row in (ledger.get("jobs") or {}).items():
        if key in hidden:continue
        hist=by_key.get(key) or by_name.get((str(row.get("company") or "").lower(),str(row.get("title") or "").lower()))
        status=(hist or {}).get("status") or row.get("application_status") or "DISCOVERED"
        if status not in active:continue
        rp=_resume_path(row) or _resume_path_from_confirmed(hist)
        out.append({
            "key":key,
            "company":row.get("company") or (hist or {}).get("company") or "Unknown company",
            "title":row.get("title") or (hist or {}).get("title") or "Unknown role",
            "status":status,
            "stage":_stage(status),
            "source":row.get("source") or "",
            "portal":_portal(row),
            "url":row.get("url") or (row.get("queue_item") or {}).get("url") or "",
            "resume":rp.name if rp else None,
            "resume_url":"/resume/"+quote(key,safe="") if rp else None,
            "updated":row.get("last_seen") or row.get("first_seen"),
            "applied_at":(hist or {}).get("submitted_at") or row.get("submitted_at"),
            "reason":(hist or {}).get("reason") or row.get("application_reason") or "",
        })
    out.sort(key=lambda x:x.get("updated") or x.get("applied_at") or "",reverse=True)
    return out

@app.get("/health")
def health():
    return {"ok":True,"ledger_exists":LEDGER.exists(),"confirmed_exists":CONFIRMED.exists()}

@app.post("/api/sync")
async def sync_state(request:Request):
    expected=os.getenv("DASHBOARD_SYNC_TOKEN","")
    supplied=request.headers.get("x-dashboard-token","")
    if not expected or supplied != expected:
        raise HTTPException(401,"Unauthorized")
    body=await request.body()
    if not body:
        raise HTTPException(400,"Empty sync payload")
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td)
        try:
            with tarfile.open(fileobj=io.BytesIO(body),mode="r:gz") as tf:
                for member in tf.getmembers():
                    target=(tmp/member.name).resolve()
                    if tmp.resolve() not in target.parents and target != tmp.resolve():
                        raise HTTPException(400,"Unsafe archive path")
                tf.extractall(tmp)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(400,f"Invalid sync archive: {exc}")
        source=tmp/"generated"
        if not source.exists():
            raise HTTPException(400,"Archive must contain generated/")
        STATE_DIR.mkdir(parents=True,exist_ok=True)
        for item in source.iterdir():
            if item.name in {"confirmed_applications.json","hidden_applications.json"}:
                continue
            dest=STATE_DIR/item.name
            if item.is_dir():
                shutil.copytree(item,dest,dirs_exist_ok=True)
            else:
                shutil.copy2(item,dest)
    return {"ok":True,"ledger_exists":LEDGER.exists()}

@app.get("/api/applications")
def applications():
    rows=_jobs()
    return {"applications":rows,"counts":{
        "all":len(rows),
        "queue":sum(x["stage"] in {"Ready to apply","Applying"} for x in rows),
        "applied":sum(x["stage"]=="Applied" for x in rows),
        "attention":sum(x["stage"] in {"Needs attention","Verify submission"} for x in rows),
    }}

@app.delete("/api/applications/{job_key:path}")
def hide_application(job_key:str):
    ledger=_json(LEDGER,{"jobs":{}})
    if job_key not in (ledger.get("jobs") or {}):
        raise HTTPException(404,"Job not found")
    _hide_job(job_key)
    return {"ok":True,"hidden":True}

@app.post("/api/applications/{job_key:path}/confirm-submitted")
def confirm_submitted(job_key:str):
    ledger=_json(LEDGER,{"jobs":{}})
    row=(ledger.get("jobs") or {}).get(job_key)
    if not row:raise HTTPException(404,"Job not found")
    now=datetime.now(timezone.utc).isoformat()
    data,apps=_confirmed_map()
    existing=next((x for x in apps if x.get("job_key")==job_key),None)
    rp=_resume_path(row)
    payload={
        "job_key":job_key,
        "company":row.get("company"),
        "title":row.get("title"),
        "url":row.get("url") or (row.get("queue_item") or {}).get("url") or "",
        "resume_path":str(rp.relative_to(STATE_DIR)) if rp and STATE_DIR in rp.parents else (str(rp) if rp else None),
        "status":"SUBMITTED_CONFIRMED",
        "submitted_at":now,
        "reason":"Marked applied from hosted dashboard.",
    }
    if existing:existing.update(payload)
    else:apps.append(payload)
    data["applications"]=apps
    _save_confirmed(data)
    return {"ok":True,"status":"SUBMITTED_CONFIRMED","submitted_at":now}

@app.get("/resume/{job_key:path}")
def resume(job_key:str):
    ledger=_json(LEDGER,{"jobs":{}})
    row=(ledger.get("jobs") or {}).get(job_key)
    if not row:raise HTTPException(404,"Job not found")
    _,confirmed=_confirmed_map()
    hist=next((x for x in confirmed if x.get("job_key")==job_key),None)
    if not hist:
        hist=next((x for x in confirmed if str(x.get("company") or "").lower()==str(row.get("company") or "").lower() and str(x.get("title") or "").lower()==str(row.get("title") or "").lower()),None)
    p=_resume_path(row) or _resume_path_from_confirmed(hist)
    if not p:raise HTTPException(404,"Resume not available")
    return FileResponse(p,media_type="application/pdf",headers={"Content-Disposition":f'inline; filename="{p.name}"'})

@app.get("/",response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Application Tracker</title><style>
*{box-sizing:border-box}body{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;background:#f7f8fb;color:#101828}header{padding:24px 5%;background:#fff;border-bottom:1px solid #e4e7ec;display:flex;justify-content:space-between;align-items:center}h1{font-size:23px;margin:0}.sub{font-size:13px;color:#667085;margin-top:5px}.live{font-size:12px;color:#027a48;background:#ecfdf3;padding:7px 10px;border-radius:20px;font-weight:700}
main{padding:22px 5%}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}.stat{background:#fff;border:1px solid #e4e7ec;border-radius:12px;padding:16px}.stat span{font-size:11px;color:#667085;text-transform:uppercase;font-weight:800}.stat b{font-size:26px;display:block;margin-top:5px}
.toolbar{display:flex;gap:10px;margin-bottom:14px}.toolbar input,.toolbar select{border:1px solid #d0d5dd;background:#fff;border-radius:9px;padding:10px 12px;font-size:14px}.toolbar input{flex:1}
.table{background:#fff;border:1px solid #e4e7ec;border-radius:12px;overflow:hidden}.row{display:grid;grid-template-columns:minmax(220px,1.5fr) 130px minmax(160px,1fr) 110px 260px;gap:14px;align-items:center;padding:15px 18px;border-bottom:1px solid #eef0f3}.row:last-child{border-bottom:0}.head{background:#f9fafb;color:#667085;font-size:11px;text-transform:uppercase;font-weight:800;padding-top:11px;padding-bottom:11px}.company{font-weight:800}.role{font-size:13px;color:#475467;margin-top:3px}.portal{font-size:12px;color:#667085;margin-top:4px}.badge{display:inline-block;padding:6px 9px;border-radius:20px;font-size:11px;font-weight:800;background:#f2f4f7}.applied{background:#ecfdf3;color:#027a48}.ready-to-apply,.applying{background:#eff8ff;color:#175cd3}.needs-attention,.verify-submission{background:#fffaeb;color:#b54708}.retrying{background:#f4f3ff;color:#5925dc}.resume{font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.date{font-size:12px;color:#475467}.actions{display:flex;gap:7px;flex-wrap:wrap}.btn{border:1px solid #d0d5dd;background:#fff;color:#344054;text-decoration:none;padding:8px 10px;border-radius:8px;font-size:12px;font-weight:700;white-space:nowrap;cursor:pointer}.btn.primary{background:#101828;color:#fff;border-color:#101828}.btn.appliedBtn{background:#067647;color:white;border-color:#067647}.btn.deleteBtn{color:#b42318;border-color:#fda29b;background:#fff}.empty{padding:35px;text-align:center;color:#667085}
@media(max-width:900px){header{padding:18px 4%}main{padding:16px 4%}.stats{grid-template-columns:1fr 1fr}.head{display:none}.row{grid-template-columns:1fr}.table{background:transparent;border:0}.row{background:#fff;border:1px solid #e4e7ec;border-radius:12px;margin-bottom:10px}.resume{white-space:normal}}
</style></head><body><header><div><h1>Application Tracker</h1><div class="sub">Ready-to-apply queue and applied history</div></div><div class="live">● Live</div></header><main>
<div class="stats"><div class="stat"><span>Application pipeline</span><b id="all">0</b></div><div class="stat"><span>Ready / applying</span><b id="queue">0</b></div><div class="stat"><span>Applied</span><b id="applied">0</b></div><div class="stat"><span>Needs attention</span><b id="attention">0</b></div></div>
<div class="toolbar"><input id="search" placeholder="Search company or role"><select id="filter"><option value="">All application statuses</option><option>Ready to apply</option><option>Applied</option><option>Applying</option><option>Retrying</option><option>Needs attention</option><option>Verify submission</option></select></div>
<div class="table"><div class="row head"><div>Company / role</div><div>Status</div><div>Resume</div><div>Applied</div><div>Actions</div></div><div id="jobs"></div></div></main><script>
let rows=[];const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));const cls=s=>String(s).toLowerCase().replaceAll(" ","-");const dt=v=>{if(!v)return"—";let d=new Date(v);return isNaN(d)?v:d.toLocaleDateString()};
async function markApplied(key,btn){if(!confirm("Mark this application as Applied?"))return;if(btn){btn.disabled=true;btn.textContent="Saving..."}try{let r=await fetch("/api/applications/"+encodeURIComponent(key)+"/confirm-submitted",{method:"POST"});if(!r.ok)throw new Error(await r.text());await load()}catch(e){alert("Could not update status.");if(btn){btn.disabled=false;btn.textContent="Mark Applied"}}}
async function deleteRow(key,btn){if(!confirm("Delete this application from the dashboard? It will be hidden from display."))return;if(btn){btn.disabled=true;btn.textContent="Deleting..."}try{let r=await fetch("/api/applications/"+encodeURIComponent(key),{method:"DELETE"});if(!r.ok)throw new Error(await r.text());await load()}catch(e){alert("Could not delete this application.");if(btn){btn.disabled=false;btn.textContent="Delete"}}}
function render(){let q=search.value.toLowerCase(),f=filter.value,x=rows.filter(r=>(!q||(r.company+" "+r.title).toLowerCase().includes(q))&&(!f||r.stage===f));jobs.innerHTML=x.map(r=>'<div class="row"><div><div class="company">'+esc(r.company)+'</div><div class="role">'+esc(r.title)+'</div><div class="portal">'+esc(r.portal)+'</div></div><div><span class="badge '+cls(r.stage)+'">'+esc(r.stage)+'</span></div><div class="resume">'+(r.resume_url?'<a class="btn" href="'+r.resume_url+'" target="_blank">View resume</a>':'PDF unavailable')+'</div><div class="date">'+(r.stage==="Applied"?'<span class="badge applied">✓ Applied</span><div style="margin-top:5px">'+dt(r.applied_at)+'</div>':"—")+'</div><div class="actions">'+(r.url?'<a class="btn primary" href="'+esc(r.url)+'" target="_blank">Open job / Apply</a>':'')+(r.stage!=="Applied"?'<button class="btn appliedBtn" data-job-key="'+esc(r.key)+'">Mark Applied</button>':'<span class="badge applied">✓ Already applied</span>')+'<button class="btn deleteBtn" data-delete-key="'+esc(r.key)+'">Delete</button></div></div>').join("")||'<div class="empty">No applications in this view.</div>'}
async function load(){let d=await fetch("/api/applications",{cache:"no-store"}).then(r=>r.json());rows=d.applications;Object.entries(d.counts).forEach(([k,v])=>document.getElementById(k).textContent=v);render()}jobs.addEventListener("click",e=>{let b=e.target.closest("button[data-job-key]");if(b){markApplied(b.dataset.jobKey,b);return}let d=e.target.closest("button[data-delete-key]");if(d)deleteRow(d.dataset.deleteKey,d)});search.oninput=render;filter.onchange=render;load();setInterval(load,10000);
</script></body></html>""")

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--host",default="0.0.0.0");ap.add_argument("--port",type=int,default=int(os.getenv("PORT","8765")));a=ap.parse_args()
    uvicorn.run("app.dashboard:app",host=a.host,port=a.port,reload=False)

if __name__=="__main__":main()
