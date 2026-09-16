"""Fail-closed manufacturing evidence checker; not a certification or signature verifier."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = {'.py','.c','.h','.js','.wgsl','.css','.html','.csv','.json','.kicad_pcb','.kicad_sch','.kicad_pro','.kicad_dru','.kicad_sym','.kicad_mod'}
EXCLUDE = {'__pycache__','.pytest_cache','node_modules','build','private','cam-native','generated','reports'}

def source_fingerprint(root: Path = ROOT) -> str:
    entries = []
    for folder in ('firmware','hardware','mechanical','web','gateway','factory','tools'):
        for path in (root/folder).rglob('*'):
            rel = path.relative_to(root)
            if path.is_file() and not path.is_symlink() and path.suffix in EXTENSIONS and not EXCLUDE.intersection(rel.parts):
                entries.append((rel.as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()))
    for name in ('manufacturing/handbook.md','manufacturing/release-plan.json'):
        path=root/name
        if path.exists():entries.append((name,hashlib.sha256(path.read_bytes()).hexdigest()))
    if not entries:raise ValueError('No design sources found')
    return hashlib.sha256(json.dumps(sorted(entries),separators=(',',':')).encode()).hexdigest()

def check(plan: dict, evidence: list, fingerprint: str, root: Path = ROOT) -> list[str]:
    errors=[]
    required=plan.get('required')
    if not isinstance(required,list) or not required or not all(isinstance(x,str) and x for x in required) or len(required)!=len(set(required)):
        return ['Invalid or empty release requirement set']
    if not isinstance(evidence,list):return ['Evidence must be a list']
    grouped={}
    for record in evidence:
        if not isinstance(record,dict):errors.append('Malformed evidence record');continue
        key=record.get('requirement')
        if not isinstance(key,str) or key not in required:errors.append('Unknown evidence requirement');continue
        if key in grouped:errors.append(f'{key}: duplicate evidence')
        grouped[key]=record
    for key in required:
        record=grouped.get(key)
        if record is None:errors.append(f'{key}: missing evidence');continue
        if record.get('status')!='PASS':errors.append(f'{key}: not PASS')
        if record.get('source_fingerprint')!=fingerprint:errors.append(f'{key}: stale design fingerprint')
        reviewer=record.get('reviewer')
        if not isinstance(reviewer,str) or not reviewer.strip():errors.append(f'{key}: reviewer missing')
        try:
            date=dt.datetime.fromisoformat(record.get('reviewed_utc','').replace('Z','+00:00'))
            if date.tzinfo is None or date>dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=5):raise ValueError()
        except (ValueError,TypeError,AttributeError):errors.append(f'{key}: invalid review timestamp')
        report=record.get('report',{})
        if not isinstance(report,dict):errors.append(f'{key}: invalid report');continue
        name,digest=report.get('path'),report.get('sha256')
        if not isinstance(name,str) or not name or not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):
            errors.append(f'{key}: report path/hash missing');continue
        path=root/name
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
            errors.append(f'{key}: report unavailable or unsafe');continue
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:errors.append(f'{key}: report hash mismatch')
    return errors

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,help='JSON list of reviewed, hash-bound evidence records')
    parser.add_argument('--fingerprint',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    fingerprint=source_fingerprint()
    if args.fingerprint:print(fingerprint);return
    plan=json.loads((ROOT/'manufacturing/release-plan.json').read_text())
    evidence=json.loads(args.evidence.read_text()) if args.evidence else []
    errors=check(plan,evidence,fingerprint)
    report={'schema':1,'status':'BLOCKED' if errors else 'EVIDENCE_COMPLETE_REQUIRES_AUTHORIZED_SIGNOFF',
            'source_fingerprint':fingerprint,'errors':errors,
            'limitation':'Checks completeness and integrity only; does not authenticate reviewers or establish compliance.'}
    text=json.dumps(report,indent=2)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text)
    print(text,end='')
    if errors:raise SystemExit(1)

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,TypeError) as exc:
        print(f'Release gate failed: {exc}',file=sys.stderr);raise SystemExit(2)
