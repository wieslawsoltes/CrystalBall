"""Offline-only voice journal inspection/reconciliation. Stop the gateway first.

This tool never calls OpenAI and never asserts that a call ended by itself.
Reconciliation requires an operator's external termination investigation report.
The kernel worker lock prevents concurrent mutation of a running supervisor.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import sqlite3
import time
from .realtime import Journal


def reconcile(journal: Journal, handle: str, reviewer: str, report: Path):
    if not re.fullmatch(r'[A-Za-z0-9_-]{32}', handle):
        raise ValueError('Invalid local call handle')
    if not reviewer.strip() or len(reviewer) > 128 or any(ord(c) < 32 for c in reviewer):
        raise ValueError('Named reviewer required')
    if report.is_symlink() or not report.is_file() or not 1 <= report.stat().st_size <= 8*1024*1024:
        raise ValueError('A regular nonempty review report (up to 8 MiB) is required')
    digest = hashlib.sha256(report.read_bytes()).hexdigest()
    record = json.dumps({'reviewer':reviewer, 'report_sha256':digest,
                         'reviewed_at':int(time.time()), 'disposition':'operator_confirmed_provider_termination'}, sort_keys=True)
    with journal.db() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT state FROM calls WHERE handle=?', (handle,)).fetchone()
        if row is None or row['state'] in ('CLOSED','RESOLVED'):
            raise ValueError('No unresolved call with this handle')
        db.execute("UPDATE calls SET state='RESOLVED',review=?,error='' WHERE handle=?", (record,handle))
    return digest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database', required=True, type=Path)
    sub = p.add_subparsers(dest='action', required=True)
    sub.add_parser('inspect')
    s = sub.add_parser('reconcile')
    s.add_argument('--handle', required=True)
    s.add_argument('--reviewer', required=True)
    s.add_argument('--report', required=True, type=Path)
    s.add_argument('--confirmed-provider-closed', required=True, action='store_true')
    args = p.parse_args()
    if not args.database.is_file():
        raise ValueError('Journal must already exist; no file was created')
    journal = Journal(str(args.database))
    try:
        if args.action == 'inspect':
            print(json.dumps({'unresolved':journal.rows(), 'note':'Metadata only; provider termination must be investigated externally.'}, indent=2))
        else:
            digest = reconcile(journal,args.handle,args.reviewer,args.report)
            print(json.dumps({'recorded':'operator attestation, not provider verification', 'report_sha256':digest}))
    finally:
        journal.close()


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, RuntimeError, sqlite3.Error) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
