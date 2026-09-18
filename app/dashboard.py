from __future__ import annotations
import json,html
from pathlib import Path
from fastapi.responses import HTMLResponse

ROOT=Path(__file__).resolve().parents[1]
LEDGER=ROOT/"generated"/"job_ledger.json"
CYCLES=ROOT/"generated"/"cycles"
SOURCE_HEALTH=ROOT/"generated"/"source_health.json"

def _json(path,default):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:return default

def _latest_summaries(limit=12):
    if not CYCLES.exists():return []
    rows=[]
    for p in sorted(CYCLES.glob("*_summary.json"),reverse=True)[:limit]:
        row=_json(p,{})
        if row:rows.append(row)
    return rows

def dashboard_html() -> str:
    ledger=_json(LEDGER,{"jobs":{}})
    jobs=list((ledger.get("jobs") or {}).values())
    summaries=_latest_summaries()
    source_health=_json(SOURCE_HEALTH,{})
    counts={}
    for j in jobs:
        status=j.get("application_status") or "UNKNOWN";counts[status]=counts.get(status,0)+1
    latest=summaries[0] if summaries else {}
    cards=[
      ("Latest discovered",latest.get("discovered",0)),
      ("Latest eligible",latest.get("eligible",0)),
      ("Final JD verified",latest.get("final_jd_verified",0)),
      ("Ready to apply",counts.get("READY_TO_APPLY",0)),
      ("Artifact holds",counts.get("HOLD_ARTIFACT_VALIDATION",0)),
      ("Submitted",counts.get("SUBMITTED",0)),
      ("Manual action",counts.get("MANUAL_ACTION_REQUIRED",0)),
      ("Source errors",sum(1 for x in source_health.values() if x.get("status")=="ERROR")),
    ]
    card_html="".join(f"<div class='card'><span>{html.escape(k)}</span><b>{v}</b></div>" for k,v in cards)
    rows=[]
    for j in sorted(jobs,key=lambda x:x.get("last_seen",""),reverse=True)[:250]:
        url=html.escape(j.get("url") or "#",quote=True);resume=html.escape(str(j.get("pdf_path") or j.get("resume_path") or "—"))
        av=j.get("artifact_validation") or {}
        artifact=("PASS" if av.get("passed") else (f"HOLD: {av.get('reason')}" if av else "—"))
        if av and av.get("text_coverage") is not None:artifact+=f" ({av.get('text_coverage')}%)"
        rows.append("<tr>"+ "".join([
          f"<td>{html.escape(str(j.get('company') or ''))}</td>",
          f"<td>{html.escape(str(j.get('title') or ''))}</td>",
          f"<td>{html.escape(', '.join(j.get('sources') or [j.get('source') or '']))}</td>",
          f"<td>{html.escape(str(j.get('application_status') or ''))}</td>",
          f"<td><a href='{url}' target='_blank'>Open job</a></td>",
          f"<td class='resume'>{resume}</td>",
          f"<td>{html.escape(str(artifact))}</td>",
        ])+"</tr>")
    body="".join(rows) or "<tr><td colspan='7'>No pipeline jobs recorded yet.</td></tr>"
    health_rows="".join(
      f"<tr><td>{html.escape(str(x.get('source') or ''))}</td><td>{html.escape(str(x.get('company') or ''))}</td><td>{html.escape(str(x.get('status') or ''))}</td><td>{x.get('jobs_returned',0)}</td><td>{html.escape(str(x.get('checked_at') or ''))}</td><td>{html.escape(str(x.get('error') or ''))}</td></tr>"
      for x in sorted(source_health.values(),key=lambda y:(y.get("status")!="ERROR",y.get("source",""),y.get("company") or ""))
    )
    cycles="".join(f"<tr><td>{html.escape(str(x.get('cycle_id','')))}</td><td>{x.get('scan_window_hours','')}</td><td>{x.get('discovered',0)}</td><td>{x.get('eligible',0)}</td><td>{x.get('final_jd_verified',0)}</td><td>{x.get('ready_to_apply',0)}</td></tr>" for x in summaries)
    return f"""<!doctype html><html><head><title>AI Job Search Agent</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{{font-family:Arial,sans-serif;margin:28px;background:#f5f6f8;color:#171717}}h1{{margin-bottom:4px}}.sub{{color:#666;margin-bottom:22px}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:26px}}.card{{background:white;border:1px solid #ddd;border-radius:10px;padding:16px}}.card span{{display:block;color:#666;font-size:13px}}.card b{{font-size:28px}}table{{width:100%;border-collapse:collapse;background:white;margin-bottom:28px}}th,td{{padding:10px;border-bottom:1px solid #e5e5e5;text-align:left;font-size:13px}}th{{background:#171717;color:white;position:sticky;top:0}}a{{color:#1456b8}}.resume{{max-width:320px;overflow-wrap:anywhere}}.wrap{{overflow:auto;max-height:560px;background:white}}</style></head><body>
<h1>AI Job Search Agent</h1><div class="sub">Pipeline operations, applications and resume tracking</div>
<div class="cards">{card_html}</div>
<h2>Recent cycles</h2><div class="wrap"><table><tr><th>Cycle</th><th>Window (h)</th><th>Discovered</th><th>Eligible</th><th>Final JD</th><th>Ready</th></tr>{cycles or "<tr><td colspan='6'>No cycles yet.</td></tr>"}</table></div>
<h2>Source health</h2><div class="wrap"><table><tr><th>Source</th><th>Company / board</th><th>Status</th><th>Jobs returned</th><th>Checked</th><th>Error</th></tr>{health_rows or "<tr><td colspan='6'>No source health checks recorded yet.</td></tr>"}</table></div>
<h2>Jobs / applications</h2><div class="wrap"><table><tr><th>Company</th><th>Role</th><th>Sources</th><th>Status</th><th>Job</th><th>Resume used</th><th>Artifact validation</th></tr>{body}</table></div>
</body></html>"""
