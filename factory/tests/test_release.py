import hashlib
from factory.release_gate import check

def evidence(tmp_path):
    p=tmp_path/'report.txt';p.write_text('Explicit synthetic test fixture, not production evidence.')
    return {'requirement':'optics','status':'PASS','source_fingerprint':'abc','reviewer':'test fixture',
            'reviewed_utc':'2025-01-01T00:00:00Z','report':{'path':'report.txt','sha256':hashlib.sha256(p.read_bytes()).hexdigest()}}

def test_empty_requirements_never_pass(tmp_path):assert check({'required':[]},[],'abc',tmp_path)
def test_missing_evidence_blocks(tmp_path):assert check({'required':['optics']},[],'abc',tmp_path)
def test_synthetic_complete_record_validates_structure_only(tmp_path):assert not check({'required':['optics']},[evidence(tmp_path)],'abc',tmp_path)
def test_stale_and_failed_record_blocks(tmp_path):
    e=evidence(tmp_path);e['status']='PENDING';e['source_fingerprint']='old'
    assert len(check({'required':['optics']},[e],'abc',tmp_path))>=2
def test_report_tamper_blocks(tmp_path):
    e=evidence(tmp_path);(tmp_path/'report.txt').write_text('changed')
    assert any('hash mismatch' in x for x in check({'required':['optics']},[e],'abc',tmp_path))
def test_duplicate_review_blocks(tmp_path):
    e=evidence(tmp_path);assert any('duplicate' in x for x in check({'required':['optics']},[e,e],'abc',tmp_path))
def test_outside_path_blocks(tmp_path):
    e=evidence(tmp_path);e['report']['path']='../escape';assert check({'required':['optics']},[e],'abc',tmp_path)
def test_undated_review_blocks(tmp_path):
    e=evidence(tmp_path);e['reviewed_utc']='';assert check({'required':['optics']},[e],'abc',tmp_path)
