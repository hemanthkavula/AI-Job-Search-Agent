from __future__ import annotations
import sqlite3
from app.db import DB

def init_queue():
    with sqlite3.connect(DB) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS application_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER,
            resume_path TEXT,
            status TEXT DEFAULT 'READY_FOR_REVIEW',
            review_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

def enqueue(application_id: int, resume_path: str) -> int:
    init_queue()
    with sqlite3.connect(DB) as con:
        cur=con.execute(
            "INSERT INTO application_queue(application_id,resume_path) VALUES(?,?)",
            (application_id,resume_path),
        )
        return cur.lastrowid
