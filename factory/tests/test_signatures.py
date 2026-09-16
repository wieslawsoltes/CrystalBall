"""Ephemeral signing keys are test fixtures, never trusted production reviewers."""
import base64
from copy import deepcopy
import datetime as dt
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from factory.evidence import canonical,context,key_id,load_json,pinned_policy,sign,verify
from factory.release_gate import check,source_fingerprint,materials_fingerprint
from factory.common import artifact_hash

NOW=dt.datetime(2026,9,16,12,tzinfo=dt.timezone.utc)
PLAN={'schema':1,'product':'SYNTHETIC FIXTURE','revision':'TEST','required':['optics']}


def fixture():
    key=Ed25519PrivateKey.generate()
    entry={'key_id':key_id(key.public_key()),'public_key':base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode(),
           'reviewer':'Test reviewer A','requirements':['optics'],'revoked':False,'not_before_utc':'2026-01-01T00:00:00Z','expires_utc':'2027-01-01T00:00:00Z'}
    policy={'schema':1,'product':PLAN['product'],'revision':'TEST','max_age_days':30,'thresholds':{'optics':1},'keys':[entry]}
    record={'requirement':'optics','status':'PASS','reviewer':'Test reviewer A','source_fingerprint':'synthetic-source',
            'reviewed_utc':'2026-09-16T11:00:00Z','valid_until_utc':'2026-09-20T00:00:00Z',
            'report':{'path':'raw.txt','sha256':hashlib.sha256(b'SYNTHETIC').hexdigest()}}
    return key,policy,record


def test_signature_and_artifact_integrity_are_both_required(tmp_path):
    key,policy,record=fixture();envelope=sign(record,key,PLAN)
    values,errors=verify(PLAN,[envelope],policy,now=NOW)
    assert not errors
    (tmp_path/'raw.txt').write_bytes(b'SYNTHETIC')
    assert not check(PLAN,values,'synthetic-source',tmp_path)
    (tmp_path/'raw.txt').write_text('tampered')
    assert check(PLAN,values,'synthetic-source',tmp_path)


@pytest.mark.parametrize('field,value',[('status','FAIL'),('reviewer','attacker'),('source_fingerprint','another-source'),('report',{'path':'other','sha256':'0'*64})])
def test_tampering_any_signed_payload_field_rejected(field,value):
    key,policy,record=fixture();envelope=sign(record,key,PLAN);envelope['payload'][field]=value
    assert verify(PLAN,[envelope],policy,now=NOW)[1]


@pytest.mark.parametrize('mutation',['revoked','expired','future','wrong_id','duplicate','no_keys','wrong_product','wrong_revision','scope','quorum'])
def test_untrusted_policy_or_key_is_rejected(mutation):
    key,policy,record=fixture();env=sign(record,key,PLAN);entry=policy['keys'][0]
    if mutation=='revoked':entry['revoked']=True
    if mutation=='expired':entry['expires_utc']='2026-01-02T00:00:00Z'
    if mutation=='future':entry['not_before_utc']='2026-10-01T00:00:00Z'
    if mutation=='wrong_id':entry['key_id']='0'*64
    if mutation=='duplicate':policy['keys'].append(deepcopy(entry))
    if mutation=='no_keys':policy['keys']=[]
    if mutation=='wrong_product':policy['product']='OTHER'
    if mutation=='wrong_revision':policy['revision']='OTHER'
    if mutation=='scope':entry['requirements']=[]
    if mutation=='quorum':policy['thresholds']['optics']=0
    assert verify(PLAN,[env],policy,now=NOW)[1]


def test_two_person_quorum_counts_people_not_rotated_keys():
    a,policy,record=fixture();b,other,_=fixture();env=sign(sign(record,a,PLAN),b,PLAN)
    policy['keys'].append(other['keys'][0]);policy['thresholds']['optics']=2
    assert verify(PLAN,[env],policy,now=NOW)[1]
    policy['keys'][1]['reviewer']='Test reviewer B'
    assert not verify(PLAN,[env],policy,now=NOW)[1]


def test_replay_under_different_plan_rejected():
    key,policy,record=fixture();env=sign(record,key,PLAN);changed={**PLAN,'release_status':'changed'}
    assert verify(changed,[env],policy,now=NOW)[1]


@pytest.mark.parametrize('value',['2026-09-15T00:00:00Z','2027-01-01T00:00:00Z','2026-09-20T00:00:00','bad'])
def test_evidence_expiration_and_time_boundaries(value):
    key,policy,record=fixture();record['valid_until_utc']=value
    assert verify(PLAN,[sign(record,key,PLAN)],policy,now=NOW)[1]


def test_duplicate_signatures_and_envelopes_rejected():
    key,policy,record=fixture();env=sign(record,key,PLAN)
    with pytest.raises(ValueError):sign(env,key,PLAN)
    assert verify(PLAN,[env,env],policy,now=NOW)[1]
    env['signatures']*=2
    assert verify(PLAN,[env],policy,now=NOW)[1]


def test_untrusted_external_key_rejected():
    key,policy,record=fixture();other=Ed25519PrivateKey.generate()
    assert verify(PLAN,[sign(record,other,PLAN)],policy,now=NOW)[1]


def test_canonical_format_is_deterministic_and_rejects_float_values():
    assert canonical({'z':1,'ą':'two'})==canonical({'ą':'two','z':1})
    for value in [1.0,float('nan'),float('inf'),{2:'x'}]:
        with pytest.raises(ValueError):canonical(value)


def test_duplicate_keys_and_nonfinite_inputs_rejected(tmp_path):
    p=tmp_path/'input.json'
    for text in ['{"x":1,"x":2}','{"x":NaN}']:
        p.write_text(text)
        with pytest.raises(ValueError):load_json(p)


def test_external_policy_requires_independent_hash_pin(tmp_path):
    _,policy,_=fixture();p=tmp_path/'policy.json';p.write_text(json.dumps(policy));digest=hashlib.sha256(p.read_bytes()).hexdigest()
    assert pinned_policy(p,digest)==policy
    p.write_text('{}')
    with pytest.raises(ValueError):pinned_policy(p,digest)
    with pytest.raises(ValueError):pinned_policy(p,'')


@pytest.mark.parametrize('name',['gateway/Dockerfile','gateway/Caddyfile','gateway/compose.yaml','gateway/pyproject.toml','firmware/CMakeLists.txt','firmware/sdkconfig.defaults','.github/workflows/verify.yml','ci/package_handoff.py'])
def test_build_and_deployment_inputs_invalidate_design_evidence(tmp_path,name):
    p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('before')
    before=source_fingerprint(tmp_path);p.write_text('after')
    assert source_fingerprint(tmp_path)!=before


def test_manufacturing_outputs_are_separately_hash_bound(tmp_path):
    p=tmp_path/'manufacturing/cam-native/board.gbr';p.parent.mkdir(parents=True);p.write_text('before')
    before=materials_fingerprint(tmp_path);p.write_text('after');assert materials_fingerprint(tmp_path)!=before


def test_in_root_parent_symlink_rejected(tmp_path):
    folder=tmp_path/'real';folder.mkdir();(folder/'r.txt').write_text('test');(tmp_path/'alias').symlink_to(folder,target_is_directory=True)
    with pytest.raises(ValueError):artifact_hash(tmp_path,'alias/r.txt')


def test_empty_and_traversal_artifacts_rejected(tmp_path):
    (tmp_path/'empty').touch()
    for value in ['empty','../x','/tmp/x','a\\b','./empty']:
        with pytest.raises(ValueError):artifact_hash(tmp_path,value)


def test_pinned_policy_parses_the_same_verified_bytes(tmp_path, monkeypatch):
    import factory.evidence as module
    _, policy, _ = fixture()
    path = tmp_path / 'policy.json'
    path.write_text(json.dumps(policy))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    original = module.parse_json
    def replace_after_hash(data):
        path.write_text('{"untrusted_replacement":true}')
        return original(data)
    monkeypatch.setattr(module, 'parse_json', replace_after_hash)
    assert module.pinned_policy(path, digest) == policy


def test_empty_policy_template_cannot_authenticate(tmp_path, monkeypatch):
    import factory.evidence as module
    plan = tmp_path / 'plan.json'; plan.write_text(json.dumps(PLAN))
    out = tmp_path / 'policy.json'
    monkeypatch.setattr('sys.argv', ['evidence', 'policy-template', '--plan', str(plan), '--out', str(out)])
    monkeypatch.setattr(module.getpass, 'getpass', lambda *_: pytest.fail('Templates do not need signing passwords'))
    module.main()
    policy = json.loads(out.read_text())
    assert policy['keys'] == [] and policy['thresholds'] == {'optics': 2}
    assert verify(PLAN, [], policy, now=NOW)[1]


def test_signed_release_cli_authenticates_but_does_not_authorize(tmp_path, monkeypatch, capsys):
    import factory.release_gate as module
    key, policy, record = fixture()
    now = dt.datetime.now(dt.timezone.utc)
    record['reviewed_utc'] = (now-dt.timedelta(minutes=1)).isoformat()
    record['valid_until_utc'] = (now+dt.timedelta(days=1)).isoformat()
    policy['keys'][0]['not_before_utc'] = (now-dt.timedelta(days=2)).isoformat()
    policy['keys'][0]['expires_utc'] = (now+dt.timedelta(days=2)).isoformat()
    (tmp_path/'manufacturing').mkdir()
    (tmp_path/'manufacturing/release-plan.json').write_text(json.dumps(PLAN))
    (tmp_path/'raw.txt').write_bytes(b'SYNTHETIC')
    (tmp_path/'mechanical').mkdir()
    output = tmp_path/'mechanical/part.step'; output.write_text('SYNTHETIC GEOMETRY')
    record['source_fingerprint'] = source_fingerprint(tmp_path)
    record['materials_fingerprint'] = materials_fingerprint(tmp_path)
    evidence = tmp_path/'evidence.json'; evidence.write_text(json.dumps([sign(record,key,PLAN)]))
    trusted = tmp_path/'trusted.json'; trusted.write_text(json.dumps(policy))
    report = tmp_path/'result.json'
    digest = hashlib.sha256(trusted.read_bytes()).hexdigest()
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr('sys.argv', ['release_gate', '--evidence', str(evidence), '--trust-policy', str(trusted),
        '--policy-sha256', digest, '--output', str(report)])
    module.main()
    result = json.loads(report.read_text())
    assert result['authenticated']
    assert result['status'] == 'AUTHENTICATED_EVIDENCE_COMPLETE_REQUIRES_AUTHORIZED_SIGNOFF'
    output.write_text('TAMPERED SYNTHETIC GEOMETRY')
    with pytest.raises(SystemExit) as failure:
        module.main()
    assert failure.value.code == 1
    assert json.loads(report.read_text())['status'] == 'BLOCKED'
