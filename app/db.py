import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "job_agent.db"

def init_db():
    with sqlite3.connect(DB) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT,
            score INTEGER,
            decision TEXT,
            status TEXT DEFAULT 'DISCOVERED',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

def save_job(job, analysis):
    with sqlite3.connect(DB) as con:
        cur = con.execute(
            "INSERT INTO applications(company,title,url,score,decision) VALUES(?,?,?,?,?)",
            (job.company, job.title, job.url, analysis["score"], analysis["decision"]),
        )
        return cur.lastrowid
