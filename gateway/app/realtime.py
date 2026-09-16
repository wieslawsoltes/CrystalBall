"""Crash-recoverable Realtime ownership journal and single-process supervisor.

Persist intent BEFORE contacting the provider and its ID BEFORE reading SDP.
An ambiguous create without an ID is never retried or automatically forgotten.
Only a successful provider hangup confirms cleanup (404 is not confirmation).
No SDP, audio, prompts, tokens, or project keys are stored here.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager, suppress
from dataclasses import dataclass
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from typing import Callable, Iterator
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

PROVIDER = re.compile(r"[A-Za-z0-9_-]{1,128}")


def provider_id(location: str) -> str:
    """Accept only the documented API call resource, never a caller URL."""
    url = urlsplit(location)
    if url.scheme and (url.scheme != 'https' or url.netloc != 'api.openai.com'):
        raise ValueError('Untrusted provider Location')
    if not url.scheme and url.netloc:
        raise ValueError('Protocol-relative Location is not supported')
    match = re.fullmatch(r'/v1/realtime/calls/([A-Za-z0-9_-]{1,128})', url.path)
    if not match or url.query or url.fragment:
        raise ValueError('Provider omitted a manageable call ID')
    return match[1]


class WorkerLock:
    """Kernel-owned lock: death releases it; never delete/unlink the lock file."""
    def __init__(self, path: Path):
        self.fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        try:
            if os.name == 'nt':
                import msvcrt
                if os.fstat(self.fd).st_size == 0:
                    os.write(self.fd, b'0')
                os.lseek(self.fd, 0, os.SEEK_SET)
                msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(self.fd)
            self.fd = -1
            raise RuntimeError('Realtime journal already owned by another worker') from None

    def close(self):
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


class Journal:
    def __init__(self, path: str):
        file = Path(path)
        if file.is_symlink():
            raise ValueError('Realtime journal cannot be a symlink')
        file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = str(file.resolve())
        self.lock = WorkerLock(Path(self.path + '.lock'))
        try:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(fd)
            with self.db() as db:
                version = db.execute('PRAGMA user_version').fetchone()[0]
                if version not in (0, 1):
                    raise ValueError('Unsupported realtime journal schema')
                db.execute('PRAGMA journal_mode=WAL')
                db.executescript('''
                    CREATE TABLE IF NOT EXISTS calls(
                        handle TEXT PRIMARY KEY, unit TEXT NOT NULL,
                        provider_id TEXT, state TEXT NOT NULL CHECK(state IN
                            ('RESERVED','ACTIVE','CLOSING','UNKNOWN','CLOSED','RESOLVED')),
                        created REAL NOT NULL, expires REAL NOT NULL,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        error TEXT NOT NULL DEFAULT '', review TEXT NOT NULL DEFAULT '');
                    PRAGMA user_version=1;
                ''')
            file.chmod(0o600)
        except BaseException:
            self.lock.close()
            raise

    @contextmanager
    def db(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=1)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA synchronous=FULL')
            with db:
                yield db
        finally:
            db.close()

    def rows(self) -> list[dict]:
        with self.db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM calls WHERE state NOT IN ('CLOSED','RESOLVED') ORDER BY created")]

    def reserve(self, unit: str, now: float, duration: int) -> str:
        handle = secrets.token_urlsafe(24)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            rows = list(db.execute("SELECT unit,state FROM calls WHERE state NOT IN ('CLOSED','RESOLVED')"))
            if any(r['state'] in ('UNKNOWN', 'CLOSING') for r in rows) or len(rows) >= 2:
                raise HTTPException(503, 'Voice cleanup or capacity unavailable')
            if any(r['unit'] == unit for r in rows):
                raise HTTPException(409, 'A voice session already exists for this device')
            db.execute("INSERT INTO calls(handle,unit,state,created,expires) VALUES (?,?,'RESERVED',?,?)", (handle,unit,now,now+duration))
        return handle

    def bind(self, handle: str, ident: str):
        if not PROVIDER.fullmatch(ident):
            raise ValueError('Invalid provider call ID')
        with self.db() as db:
            cur = db.execute("UPDATE calls SET provider_id=?,state='ACTIVE' WHERE handle=? AND state='RESERVED'", (ident,handle))
            if cur.rowcount != 1:
                raise ValueError('Invalid journal transition')

    def state(self, handle: str, state: str, error: str = ''):
        with self.db() as db:
            db.execute("UPDATE calls SET state=?,error=?,attempts=attempts+? WHERE handle=? AND state NOT IN ('CLOSED','RESOLVED')",
                       (state,error,int(state == 'CLOSING'),handle))

    def recover(self):
        with self.db() as db:
            # A request may have reached the provider immediately before process death.
            db.execute("UPDATE calls SET state='UNKNOWN',error='interrupted_create' WHERE state='RESERVED'")
            db.execute("UPDATE calls SET state='CLOSING',error='restart_cleanup' WHERE state='ACTIVE'")
            # Retain only operational metadata for seven days after creation.
            db.execute("DELETE FROM calls WHERE state IN ('CLOSED','RESOLVED') AND created < ?", (time.time()-7*86400,))

    def close(self):
        self.lock.close()


@dataclass
class Call:
    unit: str
    provider_id: str
    expires: float
    task: asyncio.Task | None = None


class Calls:
    def __init__(self, app, *, clock: Callable[[], float] = time.time):
        self.app, self.clock = app, clock
        self.active: dict[str, Call] = {}
        self.pending: set[str] = set()
        self.journal: Journal | None = None
        self.store_failed = False
        self.unknown = False
        self.failed: set[str] = set()
        self.locks: dict[str, asyncio.Lock] = {}
        self.background: set[asyncio.Task] = set()
        self.retry_task: asyncio.Task | None = None
        self.closed = False

    @property
    def unhealthy(self) -> bool:
        return self.store_failed or self.unknown or bool(self.failed)

    async def start(self):
        cfg = self.app.state.settings
        path = cfg.realtime_database or (cfg.budget_path + '.realtime' if cfg.budget_path else '')
        if not path:
            if cfg.realtime_enabled:
                raise ValueError('Live voice requires REALTIME_DATABASE or BUDGET_DATABASE')
            return
        self.journal = Journal(path)
        try:
            self.journal.recover()
            for row in self.journal.rows():
                if row["provider_id"] is not None and not PROVIDER.fullmatch(row["provider_id"]):
                    raise ValueError("Corrupt provider identifier in voice journal")
                if row['provider_id']:
                    self.active[row['handle']] = Call(row['unit'], row['provider_id'], row['expires'])
                    self.failed.add(row['handle'])
                else:
                    self.unknown = True
            # Even with live voice disabled, clean up sessions from an older process.
            await asyncio.gather(*(self.hangup(h) for h in list(self.active)), return_exceptions=True)
            self.retry_task = asyncio.create_task(self.retry(), name='orb-voice-cleanup')
        except BaseException:
            self.journal.close()
            raise

    def reserve(self, unit: str) -> str:
        if self.closed or self.unhealthy or self.journal is None:
            raise HTTPException(503, 'Voice recovery requires operator review')
        try:
            handle = self.journal.reserve(unit, self.clock(), self.app.state.settings.realtime_seconds)
        except sqlite3.Error:
            self.store_failed = True
            raise HTTPException(503, 'Voice journal unavailable') from None
        self.pending.add(unit)
        return handle

    def bind(self, handle: str, unit: str, ident: str):
        # Keep a RAM cleanup target even if disk fails immediately after response headers.
        call = Call(unit, ident, self.clock()+self.app.state.settings.realtime_seconds)
        self.active[handle] = call
        try:
            self.journal.bind(handle, ident)
        except sqlite3.Error:
            self.store_failed = True
            raise HTTPException(503, 'Voice journal unavailable') from None
        call.task = asyncio.create_task(self.expire(handle), name='orb-voice-deadline')

    def set_state(self, handle: str, state: str, error: str = '') -> bool:
        try:
            self.journal.state(handle, state, error)
            return True
        except sqlite3.Error:
            self.store_failed = True
            return False

    async def abort_create(self, handle: str):
        if handle in self.active:
            with suppress(HTTPException):
                await self.hangup(handle)
        else:
            self.unknown = True
            self.set_state(handle, 'UNKNOWN', 'ambiguous_create')

    def cleanup(self, handle: str) -> asyncio.Task:
        task = asyncio.create_task(self.abort_create(handle), name='orb-voice-abort')
        self.background.add(task)
        task.add_done_callback(self.background.discard)
        return task

    async def hangup(self, handle: str) -> None:
        lock = self.locks.setdefault(handle, asyncio.Lock())
        try:
            async with lock:
                call = self.active.get(handle)
                if call is None:
                    return
                self.failed.add(handle)
                self.set_state(handle, 'CLOSING', 'hangup_pending')
                client = self.app.state.upstream.client
                for attempt in range(3):
                    try:
                        async with client.stream('POST', f'https://api.openai.com/v1/realtime/calls/{call.provider_id}/hangup',
                            headers={'Authorization':'Bearer '+self.app.state.settings.api_key}, timeout=5) as response:
                            # Do not assume an undocumented 404/410 is proof of termination.
                            if response.status_code in (200, 204):
                                persisted = self.set_state(handle, 'CLOSED')
                                if persisted:
                                    self.active.pop(handle, None)
                                    self.failed.discard(handle)
                                    if call.task and call.task is not asyncio.current_task():
                                        call.task.cancel()
                                    return
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(.1 * (attempt+1))
                self.set_state(handle, 'CLOSING', 'hangup_unconfirmed')
                raise HTTPException(502, 'Voice cleanup unconfirmed; new calls disabled')
        finally:
            # Existing waiters retain the same lock object. No live call => no new work.
            if handle not in self.active:
                self.locks.pop(handle, None)

    async def expire(self, handle: str):
        call = self.active.get(handle)
        if call:
            # One monotonic sleep; wall-clock changes cannot extend a running session.
            await asyncio.sleep(max(0, call.expires-self.clock()))
            with suppress(HTTPException):
                await self.hangup(handle)

    async def retry(self):
        while True:
            await asyncio.sleep(5)
            await asyncio.gather(*(self.hangup(h) for h in list(self.failed)), return_exceptions=True)

    def status(self) -> dict:
        return {'ready': not self.closed and self.journal is not None and not self.unhealthy,
                'active': len(self.active), 'pending': len(self.pending),
                'cleanup_pending': len(self.failed), 'operator_review_required': self.unknown,
                'journal_fault': self.store_failed}

    async def close(self):
        self.closed = True
        tasks = [c.task for c in self.active.values() if c.task]
        if self.retry_task:
            tasks.append(self.retry_task)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.gather(*list(self.background), return_exceptions=True)
        await asyncio.gather(*(self.hangup(h) for h in list(self.active)), return_exceptions=True)
        if self.journal:
            self.journal.close()
