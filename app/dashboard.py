from __future__ import annotations
import sqlite3
from fastapi.responses import HTMLResponse
from app.db import DB

def dashboard_html() -> str:
    with sqlite3.connect(DB) as con:
        con.row_factory=sqlite3.Row
        rows=con.execute("""
          SELECT q.id queue_id,a.company,a.title,a.url,a.score,a.decision,
                 q.resume_path,q.status,q.created_at
          FROM application_queue q
          JOIN applications a ON a.id=q.application_id
          ORDER BY a.score DESC,q.created_at DESC
          LIMIT 100
        """).fetchall()
    cards=[]
    for r in rows:
        url=r["url"] or "#"
        cards.append(f"""<tr>
          <td>{r['company']}</td><td>{r['title']}</td><td><b>{r['score']}%</b></td>
          <td>{r['decision']}</td><td>{r['status']}</td>
          <td><a href="{url}" target="_blank">Open job</a></td>
          <td><code>{r['resume_path']}</code></td>
        </tr>""")
    body="".join(cards) or "<tr><td colspan='7'>No queued applications yet.</td></tr>"
    return f"""<!doctype html><html><head><title>AI Job Search Agent</title>
    <style>body{{font-family:Arial;margin:32px;background:#f7f7f8}}table{{width:100%;border-collapse:collapse;background:white}}
    th,td{{padding:12px;border-bottom:1px solid #ddd;text-align:left}}th{{background:#111;color:white}}
    h1{{margin-bottom:4px}}.sub{{color:#666;margin-bottom:24px}}</style></head><body>
    <h1>AI Job Search Agent</h1><div class="sub">Hemanth Kavula — review queue</div>
    <table><tr><th>Company</th><th>Role</th><th>Match</th><th>Decision</th><th>Status</th><th>Job</th><th>Resume</th></tr>
    {body}</table></body></html>"""
