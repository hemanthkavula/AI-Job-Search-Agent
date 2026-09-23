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
CYCLES=STATE_DIR/"cycles"
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
            "created":row.get("first_seen") or row.get("last_seen"),
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

def _pipelines():
    out=[]
    if not CYCLES.exists():return out
    for p in CYCLES.glob("*_summary.json"):
        data=_json(p,{})
        cycle=str(data.get("cycle_id") or p.name.replace("_summary.json",""))
        try: when=datetime.strptime(cycle,"%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).isoformat()
        except Exception: when=None
        out.append({"cycle_id":cycle,"created":when,"discovered":data.get("discovered",0),"eligible":data.get("eligible",0),"prepared":data.get("prepared",0),"ready_to_apply":data.get("ready_to_apply",0)})
    out.sort(key=lambda x:x.get("created") or "",reverse=True)
    return out

@app.get("/api/pipelines")
def pipelines():
    return {"pipelines":_pipelines()}

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
*{box-sizing:border-box}body{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;background:#f8fafc;color:#0f172a}header{height:64px;padding:0 3.5%;background:#fff;border-bottom:1px solid #e5e7eb;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:10}.brand{display:flex;align-items:center;gap:12px;font-size:18px;font-weight:800}.brandIcon{width:32px;height:32px;border-radius:8px;background:#2563eb;color:#fff;display:grid;place-items:center}.live{font-size:12px;color:#15803d;background:#ecfdf3;padding:7px 12px;border-radius:999px;font-weight:700}main{padding:28px 3.5% 40px;max-width:1800px;margin:auto}.hero{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}.hero h1{font-size:30px;margin:0 0 4px;letter-spacing:-.6px}.sub{font-size:14px;color:#64748b}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:20px}.stat{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:17px 20px;display:flex;align-items:center;gap:14px;min-height:88px}.statIcon{width:42px;height:42px;border-radius:10px;background:#eff6ff;display:grid;place-items:center;font-size:19px}.stat:nth-child(2) .statIcon{background:#fff7ed}.stat:nth-child(3) .statIcon{background:#ecfdf3}.stat:nth-child(4) .statIcon{background:#fef2f2}.stat span{font-size:12px;color:#64748b;font-weight:700}.stat b{font-size:24px;display:block;margin-top:2px}.datebar{display:flex;gap:10px;align-items:center;background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:10px 14px;margin-bottom:12px}.datebar label{font-size:12px;font-weight:800;color:#64748b}.datebar select{height:38px;border:1px solid #dbe2ea;background:#fff;border-radius:8px;padding:0 12px;color:#334155}.pipelines{display:flex;gap:10px;overflow-x:auto;margin-bottom:18px}.pipe{min-width:220px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:11px 13px}.pipe b{font-size:12px}.pipe div{font-size:11px;color:#64748b;margin-top:5px}.toolbar{display:grid;grid-template-columns:minmax(280px,1fr) 210px 190px 140px;gap:10px;background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:10px;margin-bottom:18px}.toolbar input,.toolbar select,.toolbar button{height:42px;border:1px solid #dbe2ea;background:#fff;border-radius:8px;padding:0 13px;font-size:13px;color:#334155}.toolbar input{width:100%}.table{background:#fff;border:1px solid #e2e8f0;border-radius:12px;overflow:hidden}.row{display:grid;grid-template-columns:minmax(280px,1.55fr) 160px 120px 130px minmax(430px,1.25fr);gap:14px;align-items:center;padding:11px 18px;border-bottom:1px solid #eef2f7;min-height:70px}.row:last-child{border-bottom:0}.head{min-height:auto;background:#f8fafc;color:#64748b;font-size:11px;text-transform:uppercase;font-weight:800;padding-top:11px;padding-bottom:11px}.companyWrap{display:flex;align-items:center;gap:12px}.avatar{width:38px;height:38px;border:1px solid #dbe2ea;border-radius:9px;background:#f8fafc;display:grid;place-items:center;font-weight:800;color:#334155;flex:none}.company{font-weight:800;font-size:14px}.role{font-size:12px;color:#64748b;margin-top:3px}.portal{font-size:12px;color:#64748b}.badge{display:inline-block;padding:6px 10px;border-radius:999px;font-size:11px;font-weight:800;background:#f1f5f9}.applied{background:#dcfce7;color:#15803d}.ready-to-apply,.applying{background:#eff6ff;color:#2563eb}.needs-attention,.verify-submission{background:#fff7ed;color:#c2410c}.retrying{background:#f5f3ff;color:#6d28d9}.date{font-size:12px;color:#64748b}.actions{display:flex;align-items:center;justify-content:flex-start;gap:8px;flex-wrap:nowrap}.btn{height:36px;border:1px solid #dbe2ea;background:#fff;color:#334155;text-decoration:none;padding:0 12px;border-radius:8px;font-size:11px;font-weight:750;white-space:nowrap;cursor:pointer;display:inline-flex;align-items:center;justify-content:center}.btn.primary{color:#2563eb;background:#eff6ff;border-color:#dbeafe}.btn.appliedBtn{background:#15803d;color:#fff;border-color:#15803d}.btn.moreBtn{font-size:20px;width:38px;padding:0}.menuWrap{position:relative}.menu{display:none;position:absolute;right:0;top:40px;background:#fff;border:1px solid #e2e8f0;border-radius:9px;padding:6px;box-shadow:0 10px 28px rgba(15,23,42,.12);z-index:5}.menu.open{display:block}.deleteBtn{color:#b91c1c;border:0;background:#fff;width:100%}.empty{padding:35px;text-align:center;color:#64748b}
@media(max-width:1100px){.row{grid-template-columns:1.4fr 130px 100px 110px 340px}.toolbar{grid-template-columns:1fr 190px}.toolbar .secondary{display:none}}@media(max-width:800px){header{padding:0 4%}main{padding:20px 4%}.stats{grid-template-columns:1fr 1fr}.head{display:none}.row{grid-template-columns:1fr;padding:16px}.table{background:transparent;border:0}.row{background:#fff;border:1px solid #e2e8f0;border-radius:12px;margin-bottom:10px}.actions{flex-wrap:wrap}.toolbar{grid-template-columns:1fr}.toolbar .secondary{display:block}}
</style></head><body><header><div class="brand"><div class="brandIcon">▣</div><span>AI Job Search Agent</span></div><div class="live">● Live</div></header><main><div class="hero"><div><h1>Application Tracker</h1><div class="sub">Track and manage your job applications in one place</div></div></div>
<div class="stats"><div class="stat"><div class="statIcon">▤</div><div><span>Total Applications</span><b id="all">0</b></div></div><div class="stat"><div class="statIcon">➤</div><div><span>Ready to Apply</span><b id="queue">0</b></div></div><div class="stat"><div class="statIcon">✓</div><div><span>Applied</span><b id="applied">0</b></div></div><div class="stat"><div class="statIcon">!</div><div><span>Needs Attention</span><b id="attention">0</b></div></div></div>
<div class="datebar"><label>Created date</label><select id="dateFilter"><option value="">All dates</option></select><span class="sub" id="dateSummary"></span></div><div id="pipelines" class="pipelines"></div>
<div class="toolbar"><input id="search" placeholder="⌕  Search company, role, or keywords..."><select id="filter"><option value="">All statuses</option><option>Ready to apply</option><option>Applied</option><option>Applying</option><option>Retrying</option><option>Needs attention</option><option>Verify submission</option></select><select id="sourceFilter" class="secondary"><option value="">All sources</option></select><button id="clearFilters" class="secondary">Clear filters</button></div>
<div class="table"><div class="row head"><div>Company / Role</div><div>Status</div><div>Source</div><div>Applied</div><div>Actions</div></div><div id="jobs"></div></div></main><script>
let rows=[];const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));const cls=s=>String(s).toLowerCase().replaceAll(" ","-");const dt=v=>{if(!v)return"—";let d=new Date(v);return isNaN(d)?v:d.toLocaleDateString()};const initial=s=>(String(s||"?").trim()[0]||"?").toUpperCase();
async function markApplied(key,btn){if(!confirm("Mark this application as Applied?"))return;if(btn){btn.disabled=true;btn.textContent="Saving..."}try{let r=await fetch("/api/applications/"+encodeURIComponent(key)+"/confirm-submitted",{method:"POST"});if(!r.ok)throw new Error(await r.text());await load()}catch(e){alert("Could not update status.");if(btn){btn.disabled=false;btn.textContent="Mark Applied"}}}
async function deleteRow(key,btn){if(!confirm("Delete this application from the dashboard? It will be hidden from display."))return;try{let r=await fetch("/api/applications/"+encodeURIComponent(key),{method:"DELETE"});if(!r.ok)throw new Error(await r.text());await load()}catch(e){alert("Could not delete this application.")}}
const day=v=>{if(!v)return"";let d=new Date(v);if(isNaN(d))return String(v).slice(0,10);return d.toLocaleDateString("en-CA")};function render(){let q=search.value.toLowerCase(),f=filter.value,s=sourceFilter.value,dd=dateFilter.value;x=rows.filter(r=>(!q||(r.company+" "+r.title+" "+r.portal).toLowerCase().includes(q))&&(!f||r.stage===f)&&(!s||r.portal===s)&&(!dd||day(r.created)===dd));dateSummary.textContent=dd?x.length+" jobs created on "+dd:"";jobs.innerHTML=x.map(r=>'<div class="row"><div class="companyWrap"><div class="avatar">'+esc(initial(r.company))+'</div><div><div class="company">'+esc(r.company)+'</div><div class="role">'+esc(r.title)+'</div></div></div><div><span class="badge '+cls(r.stage)+'">'+esc(r.stage)+'</span></div><div class="portal">'+esc(r.portal)+'</div><div class="date">'+(r.stage==="Applied"?dt(r.applied_at):"—")+'</div><div class="actions">'+(r.url?'<a class="btn primary" href="'+esc(r.url)+'" target="_blank">↗ Open Job</a>':'')+(r.stage!=="Applied"?'<button class="btn appliedBtn" data-job-key="'+esc(r.key)+'">✓ Mark Applied</button>':'<span class="badge applied">✓ Applied</span>')+(r.resume_url?'<a class="btn" href="'+r.resume_url+'" target="_blank">▤ View Resume</a>':'<span class="btn" style="opacity:.5">Resume unavailable</span>')+'<div class="menuWrap"><button class="btn moreBtn" data-menu="1">⋮</button><div class="menu"><button class="btn deleteBtn" data-delete-key="'+esc(r.key)+'">Delete application</button></div></div></div></div>').join("")||'<div class="empty">No applications in this view.</div>'}
async function load(){let [d,p]=await Promise.all([fetch("/api/applications",{cache:"no-store"}).then(r=>r.json()),fetch("/api/pipelines",{cache:"no-store"}).then(r=>r.json())]);rows=d.applications;let selected=dateFilter.value;let dates=[...new Set(rows.map(r=>day(r.created)).filter(Boolean))].sort().reverse();dateFilter.innerHTML='<option value="">All dates</option>'+dates.map(v=>'<option value="'+esc(v)+'">'+esc(v)+'</option>').join("");dateFilter.value=dates.includes(selected)?selected:"";let pd=dateFilter.value;let pp=(p.pipelines||[]).filter(v=>!pd||day(v.created)===pd);pipelines.innerHTML=pp.map(v=>'<div class="pipe"><b>Pipeline '+esc(v.cycle_id)+'</b><div>'+dt(v.created)+' · '+esc(v.discovered)+' discovered · '+esc(v.ready_to_apply)+' ready</div></div>').join("")||'<div class="sub">No pipeline records for this date.</div>';Object.entries(d.counts).forEach(([k,v])=>document.getElementById(k).textContent=v);let current=sourceFilter.value;sourceFilter.innerHTML='<option value="">All sources</option>'+[...new Set(rows.map(r=>r.portal).filter(Boolean))].sort().map(v=>'<option>'+esc(v)+'</option>').join("");sourceFilter.value=current;render()}
jobs.addEventListener("click",e=>{let m=e.target.closest("button[data-menu]");if(m){document.querySelectorAll(".menu.open").forEach(x=>{if(x!==m.nextElementSibling)x.classList.remove("open")});m.nextElementSibling.classList.toggle("open");return}let b=e.target.closest("button[data-job-key]");if(b){markApplied(b.dataset.jobKey,b);return}let d=e.target.closest("button[data-delete-key]");if(d)deleteRow(d.dataset.deleteKey,d)});search.oninput=render;filter.onchange=render;sourceFilter.onchange=render;dateFilter.onchange=()=>{render();load()};clearFilters.onclick=()=>{search.value="";filter.value="";sourceFilter.value="";render()};load();setInterval(load,10000);
</script></body></html>""")

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--host",default="0.0.0.0");ap.add_argument("--port",type=int,default=int(os.getenv("PORT","8765")));a=ap.parse_args()
    uvicorn.run("app.dashboard:app",host=a.host,port=a.port,reload=False)

if __name__=="__main__":main()
