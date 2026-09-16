"""Fail-closed release evidence checker with optional externally trusted signatures.

Without --trust-policy AND --policy-sha256 this is a structural check only.
Even authenticated evidence is not an automatic manufacturing authorization.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
try:
    from .common import artifact_hash
except ImportError:
    from common import artifact_hash

ROOT=Path(__file__).resolve().parents[1]
EXTENSIONS={'.py','.c','.h','.js','.wgsl','.css','.html','.csv','.json','.kicad_pcb',
            '.kicad_sch','.kicad_pro','.kicad_dru','.kicad_sym','.kicad_mod',
            '.yaml','.yml','.toml','.lock','.cmake','.sh'}
NAMES={'Dockerfile','Caddyfile','CMakeLists.txt','sdkconfig.defaults','.env.example','sym-lib-table','fp-lib-table'}
EXCLUDE={'__pycache__','.pytest_cache','node_modules','build','private','cam-native','generated','reports'}


def source_fingerprint(root: Path=ROOT) -> str:
    entries=[]
    for folder in ('firmware','hardware','mechanical','web','gateway','factory','tools','tests','ci','.github'):
        for path in (root/folder).rglob('*'):
            rel=path.relative_to(root)
            if EXCLUDE.intersection(rel.parts):continue
            if path.is_symlink():raise ValueError('Design sources cannot contain symbolic links: '+str(rel))
            if path.is_file() and (path.suffix in EXTENSIONS or path.name in NAMES):
                entries.append((rel.as_posix(),hashlib.sha256(path.read_bytes()).hexdigest()))
    for name in ('manufacturing/handbook.md','manufacturing/release-plan.json','manufacturing/qualification-plan.json','.dockerignore','.gitignore'):
        path=root/name
        if path.is_symlink():raise ValueError('Design sources cannot contain symbolic links')
        if path.is_file():entries.append((name,hashlib.sha256(path.read_bytes()).hexdigest()))
    if not entries:raise ValueError('No design sources found')
    return hashlib.sha256(json.dumps(sorted(entries),separators=(',',':')).encode()).hexdigest()


def materials_fingerprint(root: Path=ROOT) -> str:
    """Bind manufacturing outputs as well as source; exclude self-referential status."""
    entries=[]
    for folder in ('mechanical','manufacturing/cam-native','manufacturing/generated'):
        for path in (root/folder).rglob('*'):
            if '__pycache__' in path.parts or path.name in ('SHA256.json','release-status.json'):continue
            if path.is_symlink():raise ValueError('Manufacturing output cannot be a symbolic link')
            if path.is_file():entries.append((path.relative_to(root).as_posix(),hashlib.sha256(path.read_bytes()).hexdigest()))
    return hashlib.sha256(json.dumps(sorted(entries),separators=(',',':')).encode()).hexdigest()


def check(plan: dict, evidence: list, fingerprint: str, root: Path=ROOT) -> list[str]:
    errors=[]
    required=plan.get('required') if isinstance(plan,dict) else None
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
        try:
            actual=artifact_hash(root,name)
        except (ValueError,OSError):errors.append(f'{key}: report unavailable or unsafe');continue
        if actual!=digest:errors.append(f'{key}: report hash mismatch')
    return errors


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,help='JSON list of evidence records, or signed envelopes with --trust-policy')
    parser.add_argument('--trust-policy',type=Path,help='Owner-controlled reviewer policy')
    parser.add_argument('--policy-sha256',help='Independently pinned policy SHA-256')
    parser.add_argument('--fingerprint',action='store_true')
    parser.add_argument('--materials-fingerprint',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();fingerprint=source_fingerprint(ROOT)
    if args.fingerprint:print(fingerprint);return
    if args.materials_fingerprint:print(materials_fingerprint(ROOT));return
    plan=json.loads((ROOT/'manufacturing/release-plan.json').read_text())
    if args.evidence and args.evidence.stat().st_size>2*1024*1024:
        raise ValueError('Evidence JSON exceeds 2 MiB')
    evidence=json.loads(args.evidence.read_text()) if args.evidence else []
    signed_errors=[]
    if args.trust_policy or args.policy_sha256:
        if not args.trust_policy or not args.policy_sha256:raise ValueError('Both --trust-policy and --policy-sha256 are required')
        try:
            from .evidence import load_json,pinned_policy,verify
        except ImportError:
            from evidence import load_json,pinned_policy,verify
        evidence=load_json(args.evidence) if args.evidence else []
        evidence,signed_errors=verify(plan,evidence,pinned_policy(args.trust_policy,args.policy_sha256))
        materials=materials_fingerprint(ROOT)
        for record in evidence:
            if record.get('materials_fingerprint')!=materials:
                signed_errors.append(str(record.get('requirement'))+': stale/missing manufacturing outputs fingerprint')
    errors=check(plan,evidence,fingerprint,ROOT)+signed_errors
    authenticated=bool(args.trust_policy) and not errors
    status='BLOCKED' if errors else 'AUTHENTICATED_EVIDENCE_COMPLETE_REQUIRES_AUTHORIZED_SIGNOFF' if authenticated else 'EVIDENCE_COMPLETE_REQUIRES_AUTHORIZED_SIGNOFF'
    report={'schema':2,'status':status,'authenticated':authenticated,'source_fingerprint':fingerprint,
            'materials_fingerprint':materials_fingerprint(ROOT),'errors':errors,
            'limitation':'Reviewer authentication requires an externally pinned trust policy; signatures do not prove measurement truth or certify manufacture.'}
    text=json.dumps(report,indent=2)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text)
    print(text,end='')
    if errors:raise SystemExit(1)


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,TypeError) as exc:
        print(f'Release gate failed: {exc}',file=sys.stderr);raise SystemExit(2)
