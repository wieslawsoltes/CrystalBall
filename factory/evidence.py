"""Ed25519 evidence envelopes; trust must come from an independently pinned policy.

Signatures authenticate a statement, not its physical truth. No signing keys or
trusted reviewers ship with the product. CLI key files use encrypted PKCS8 PEM.
"""
from __future__ import annotations
import argparse
import base64
import datetime as dt
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

try:
    from .common import ROOT, private_write, artifact_hash
except ImportError:
    from common import ROOT, private_write, artifact_hash

DOMAIN = b'CrystalBall/manufacturing-evidence/v1\x00'
HEX = re.compile(r'[0-9a-f]{64}')
UTC = dt.timezone.utc


def canonical(value) -> bytes:
    """Project format v1: JSON, sorted keys, ASCII escapes, no floats or duplicates.

    This is an intentionally restricted project encoding, NOT RFC 8785/JCS.
    Decimal measurements belong in attachments or string-valued fields.
    """
    def valid(x):
        if x is None or type(x) in (str, bool, int):
            return
        if isinstance(x, list):
            for item in x: valid(item)
            return
        if isinstance(x, dict) and all(type(k) is str for k in x):
            for item in x.values(): valid(item)
            return
        raise ValueError('Signed JSON accepts only strings, integers, booleans, null, arrays and objects')
    valid(value)
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')


def parse_json(data: bytes):
    if len(data) > 2*1024*1024:
        raise ValueError('JSON input exceeds 2 MiB')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result: raise ValueError('Duplicate JSON key')
            result[key]=value
        return result
    def reject(_):raise ValueError('Nonfinite JSON is forbidden')
    return json.loads(data.decode('utf-8'),object_pairs_hook=unique,parse_constant=reject)


def load_json(path: Path):
    with path.open('rb') as stream:
        return parse_json(stream.read(2*1024*1024+1))


def timestamp(value: str) -> dt.datetime:
    if not isinstance(value,str):raise ValueError('Timestamp must be UTC text')
    result=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.utcoffset()!=dt.timedelta(0):raise ValueError('Explicit UTC timestamp required')
    return result



def context(plan: dict) -> dict:
    return {'product':plan['product'],'revision':plan['revision'],
            'plan_sha256':hashlib.sha256(canonical(plan)).hexdigest()}


def key_id(key: Ed25519PublicKey) -> str:
    return hashlib.sha256(key.public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).hexdigest()


def sign(record: dict, key: Ed25519PrivateKey, plan: dict) -> dict:
    if not isinstance(record,dict):raise ValueError('Evidence record must be an object')
    if 'payload' in record:
        envelope=json.loads(canonical(record));payload=envelope['payload']
        if envelope.get('schema')!=1 or not isinstance(envelope.get('signatures'),list):raise ValueError('Malformed envelope')
        if payload.get('context')!=context(plan):raise ValueError('Evidence is bound to another plan')
    else:
        payload=dict(record);payload['context']=context(plan)
        envelope={'schema':1,'payload':payload,'signatures':[]}
    ident=key_id(key.public_key())
    if any(s.get('key_id')==ident for s in envelope['signatures']):raise ValueError('Key already signed this envelope')
    envelope['signatures'].append({'key_id':ident,'signature':base64.b64encode(key.sign(DOMAIN+canonical(payload))).decode('ascii')})
    return envelope


def verify(plan: dict, envelopes, policy: dict, *, now: dt.datetime | None = None) -> tuple[list, list[str]]:
    now=now or dt.datetime.now(UTC)
    errors=[];records=[]
    try:
        required=plan['required']
        if not isinstance(required,list) or not required or len(required)!=len(set(required)):raise ValueError('Invalid requirements')
        if (policy.get('schema')!=1 or policy.get('product')!=plan['product'] or policy.get('revision')!=plan['revision']):
            raise ValueError('Policy does not match product/revision')
        thresholds=policy['thresholds'];keys=policy['keys'];age=policy['max_age_days']
        if set(thresholds)!=set(required) or any(type(n) is not int or not 1<=n<=5 for n in thresholds.values()):
            raise ValueError('Explicit quorum for every release requirement is required')
        if type(age) is not int or not 1<=age<=365:raise ValueError('Invalid policy age limit')
        if not isinstance(keys,list) or not keys:raise ValueError('No owner-configured reviewer keys')
        trusted={}
        for entry in keys:
            public=Ed25519PublicKey.from_public_bytes(base64.b64decode(entry['public_key'],validate=True))
            ident=key_id(public)
            if ident!=entry['key_id'] or ident in trusted:raise ValueError('Duplicate or mismatched policy key')
            if not isinstance(entry['reviewer'],str) or not entry['reviewer'].strip():raise ValueError('Missing reviewer identity')
            scopes=entry['requirements']
            if not isinstance(scopes,list) or not scopes or not set(scopes)<=set(required):raise ValueError('Invalid reviewer scopes')
            if type(entry['revoked']) is not bool:raise ValueError('Explicit key revocation state required')
            start,end=timestamp(entry['not_before_utc']),timestamp(entry['expires_utc'])
            if start>=end:raise ValueError('Invalid key lifetime')
            trusted[ident]=(entry,public,start,end)
        if not isinstance(envelopes,list) or len(envelopes)>len(required)*5:raise ValueError('Invalid evidence collection')
    except (KeyError,TypeError,ValueError,AttributeError) as exc:
        return [],['Invalid trust policy/evidence collection: '+str(exc)]
    seen=set()
    for envelope in envelopes:
        try:
            if not isinstance(envelope,dict) or set(envelope)!={'schema','payload','signatures'} or envelope['schema']!=1:
                raise ValueError('Malformed signed envelope')
            payload=envelope['payload'];signatures=envelope['signatures']
            if not isinstance(payload,dict):raise ValueError('Malformed signed payload')
            requirement=payload['requirement']
            if requirement not in required:raise ValueError('Unknown requirement')
            if requirement in seen:raise ValueError('Duplicate requirement envelope')
            seen.add(requirement);records.append(payload)
            if payload.get('context')!=context(plan):raise ValueError('Plan/product/revision context mismatch')
            reviewed=timestamp(payload['reviewed_utc']);until=timestamp(payload['valid_until_utc'])
            if reviewed>now+dt.timedelta(minutes=5) or reviewed<now-dt.timedelta(days=age) or not reviewed<until or now>=until:
                raise ValueError('Expired or invalid evidence lifetime')
            if until-reviewed>dt.timedelta(days=age):raise ValueError('Evidence exceeds policy lifetime')
            if not isinstance(signatures,list) or not 1<=len(signatures)<=20:raise ValueError('Invalid signature list')
            reviewers=set();used=set();message=DOMAIN+canonical(payload)
            for signature in signatures:
                if not isinstance(signature,dict) or set(signature)!={'key_id','signature'}:raise ValueError('Malformed signature')
                ident=signature['key_id']
                if ident in used or ident not in trusted:raise ValueError('Duplicate or untrusted signer')
                used.add(ident);entry,public,start,end=trusted[ident]
                if entry['revoked'] or not start<=reviewed<=now<end:raise ValueError('Revoked, expired or not-yet-valid key')
                if requirement not in entry['requirements']:raise ValueError('Signer is not authorized for this requirement')
                public.verify(base64.b64decode(signature['signature'],validate=True),message)
                reviewers.add(entry['reviewer'])
            if len(reviewers)<thresholds[requirement]:raise ValueError('Reviewer quorum not met')
            if payload.get('reviewer') not in reviewers:raise ValueError('Claimed reviewer is not an authenticated signer')
        except (KeyError,ValueError,TypeError,AttributeError,InvalidSignature) as exc:
            errors.append('Signed evidence rejected: '+(str(exc) or 'invalid signature'))
    for requirement in required:
        if requirement not in seen:errors.append(requirement+': signed evidence missing')
    return records,errors


def pinned_policy(path: Path, expected: str):
    if not isinstance(expected,str) or not HEX.fullmatch(expected):raise ValueError('Independently pinned policy SHA-256 required')
    if path.stat().st_size>2*1024*1024:raise ValueError('Policy exceeds bounds')
    with path.open('rb') as stream:
        data=stream.read(2*1024*1024+1)
    if len(data)>2*1024*1024:raise ValueError('Policy exceeds bounds')
    if hashlib.sha256(data).hexdigest()!=expected:raise ValueError('Trust policy hash mismatch')
    # Parse the very bytes authenticated by the pin, not a second path read.
    return parse_json(data)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    k=sub.add_parser('keygen');k.add_argument('--private-key',type=Path,required=True);k.add_argument('--public-key',type=Path,required=True)
    s=sub.add_parser('sign');s.add_argument('--record',type=Path,required=True);s.add_argument('--private-key',type=Path,required=True)
    s.add_argument('--plan',type=Path,default=ROOT/'manufacturing/release-plan.json');s.add_argument('--out',type=Path,required=True)
    t=sub.add_parser('policy-template');t.add_argument('--plan',type=Path,default=ROOT/'manufacturing/release-plan.json');t.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    if args.action=='policy-template':
        plan=load_json(args.plan)
        value={'schema':1,'product':plan['product'],'revision':plan['revision'],'max_age_days':30,
               'thresholds':{name:2 for name in plan['required']},'keys':[]}
        private_write(args.out,json.dumps(value,indent=2)+'\n')
        print('Untrusted template created. No reviewer is enrolled and no approval is implied.')
        return
    password=getpass.getpass('Signing-key passphrase (hidden): ').encode('utf-8')
    if len(password)<12:raise ValueError('Use a signing passphrase of at least 12 UTF-8 bytes')
    if args.action=='keygen':
        if password!=getpass.getpass('Repeat passphrase: ').encode('utf-8'):raise ValueError('Passphrases differ')
        if args.public_key.exists() or args.private_key.exists():raise FileExistsError('Refusing to replace existing key material')
        key=Ed25519PrivateKey.generate()
        private_write(args.private_key,key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.BestAvailableEncryption(password)))
        try:
            private_write(args.public_key,json.dumps({'key_id':key_id(key.public_key()),'public_key':base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode()},indent=2)+'\n')
        except BaseException:
            args.private_key.unlink(missing_ok=True)
            raise
        print('Key created. Public key is NOT trusted until independently enrolled by the release authority.')
    else:
        key_path=args.private_key
        if key_path.is_symlink() or not key_path.is_file() or key_path.stat().st_size>16384:raise ValueError('Invalid private-key file')
        if os.name!='nt' and key_path.stat().st_mode & 0o077:raise ValueError('Private-key permissions must be 0600')
        key=serialization.load_pem_private_key(key_path.read_bytes(),password=password)
        if not isinstance(key,Ed25519PrivateKey):raise ValueError('Only Ed25519 signing keys are accepted')
        value=sign(load_json(args.record),key,load_json(args.plan))
        private_write(args.out,json.dumps(value,indent=2)+'\n');print('Signed statement written; no production authorization was inferred.')


if __name__=='__main__':
    try:main()
    except (ValueError,TypeError,KeyError,OSError) as exc:
        print('Evidence operation failed: '+str(exc),file=sys.stderr);raise SystemExit(2)
