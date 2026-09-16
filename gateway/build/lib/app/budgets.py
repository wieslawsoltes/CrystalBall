"""Durable admission budgets without storing prompts, audio, answers or tokens."""
from __future__ import annotations
import sqlite3
import time
from pathlib import Path
from fastapi import HTTPException

class DurableBudget:
    def __init__(self, path: str, minute: int, day: int):
        self.path, self.minute, self.day = path, minute, day
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path, timeout=2) as db:
            db.executescript('PRAGMA journal_mode=WAL; CREATE TABLE IF NOT EXISTS admissions(unit TEXT NOT NULL, at REAL NOT NULL); CREATE INDEX IF NOT EXISTS admissions_unit_at ON admissions(unit,at);')
        Path(path).chmod(0o600)

    def take(self, unit: str):
        now = time.time()
        try:
            with sqlite3.connect(self.path, timeout=2) as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('DELETE FROM admissions WHERE at <= ?', (now-86400,))
                count, recent = db.execute('SELECT COUNT(*), COALESCE(SUM(at > ?),0) FROM admissions WHERE unit=?', (now-60,unit)).fetchone()
                if count >= self.day or recent >= self.minute:
                    raise HTTPException(429, 'Device request budget exhausted', headers={'Retry-After':'60'})
                db.execute('INSERT INTO admissions VALUES (?,?)', (unit,now))
        except sqlite3.Error:
            raise HTTPException(503, 'Admission store unavailable') from None
