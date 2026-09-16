"""All values in this file are synthetic computational fixtures, not measurements."""
from copy import deepcopy
import datetime as dt
from decimal import InvalidOperation
import hashlib
import pytest
from factory.measurements import interval_decision,number,plan_hash,evaluate,template

NOW=dt.datetime(2026,9,16,12,tzinfo=dt.timezone.utc)


def fixture(tmp_path):
    (tmp_path/'raw.txt').write_text('SYNTHETIC acquired data fixture')
    plan={'schema':1,'product':'TEST','revision':'TEST','approved':True,'max_age_days':30,
          'cases':[{'id':'rail','unit':'V','lower':'4.75','upper':'5.25'}]}
    run=template(plan,'TEST-1','test-fingerprint');run.update(operator='Test',fixture_id='TEST',fixture_revision='TEST',data_kind='MEASURED')
    # MEASURED above tests the branch only. Nothing from this fixture is emitted as release evidence.
    run['readings'][0].update(value='5.00',expanded_uncertainty='0.05',coverage_factor='2',instrument_id='TEST',
        calibrated_utc='2026-09-01T00:00:00Z',calibration_due_utc='2026-10-01T00:00:00Z',measured_utc='2026-09-16T11:00:00Z',
        raw={'path':'raw.txt','sha256':hashlib.sha256((tmp_path/'raw.txt').read_bytes()).hexdigest()})
    return plan,run


@pytest.mark.parametrize('v,u,result',[('5','0.05','PASS'),('5.20','0.05','PASS'),('5.21','0.05','INDETERMINATE'),('5.30','0.05','INDETERMINATE'),('5.31','0.05','FAIL'),('4.79','0.05','INDETERMINATE'),('4.69','0.05','FAIL')])
def test_interval_rule_and_decimal_boundaries(v,u,result):assert interval_decision(v,u,'4.75','5.25')['decision']==result


def test_one_sided_limits():
    assert interval_decision('42','1',upper='45')['decision']=='PASS'
    assert interval_decision('44.5','1',upper='45')['decision']=='INDETERMINATE'
    assert interval_decision('5','0.5',lower='4')['decision']=='PASS'


@pytest.mark.parametrize('value',['NaN','Infinity','-Infinity','1e100','0e99999999','0.00000000000001',True,None,1.2,'not-a-number'])
def test_invalid_decimal_values(value):
    with pytest.raises((ValueError,InvalidOperation)):number(value)


def test_synthetic_structure_validates_but_never_becomes_production_authorization(tmp_path):
    plan,run=fixture(tmp_path);result=evaluate(plan,run,'test-fingerprint',tmp_path,NOW)
    assert result['status']=='WITHIN_DECLARED_LIMITS_REQUIRES_REVIEW'
    assert result['results'][0]['decision']=='PASS'


@pytest.mark.parametrize('change',['draft','synthetic','not_tested','stale','changed_plan','duplicate','unknown','missing','wrong_unit','expired_cal','not_calibrated','future','old','zero_uncertainty','missing_factor','wrong_attachment','missing_raw','missing_operator'])
def test_incomplete_invalid_or_unqualified_data_blocks(tmp_path,change):
    plan,run=fixture(tmp_path);r=run['readings'][0]
    if change=='draft':plan['approved']=False;run['plan_sha256']=plan_hash(plan)
    if change=='synthetic':run['data_kind']='SYNTHETIC'
    if change=='not_tested':run['data_kind']='NOT_TESTED'
    if change=='stale':run['source_fingerprint']='old'
    if change=='changed_plan':plan['cases'][0]['upper']='6'
    if change=='duplicate':run['readings'].append(deepcopy(r))
    if change=='unknown':r['case']='unknown'
    if change=='missing':run['readings']=[]
    if change=='wrong_unit':r['unit']='mV'
    if change=='expired_cal':r['calibration_due_utc']='2026-09-15T00:00:00Z'
    if change=='not_calibrated':r['calibrated_utc']='2026-09-17T00:00:00Z'
    if change=='future':r['measured_utc']='2026-09-17T00:00:00Z'
    if change=='old':r['calibrated_utc']='2026-01-01T00:00:00Z';r['measured_utc']='2026-08-01T00:00:00Z'
    if change=='zero_uncertainty':r['expanded_uncertainty']='0'
    if change=='missing_factor':r['coverage_factor']=None
    if change=='wrong_attachment':r['raw']['sha256']='0'*64
    if change=='missing_raw':r['raw']['path']='missing.txt'
    if change=='missing_operator':run['operator']=''
    assert evaluate(plan,run,'test-fingerprint',tmp_path,NOW)['status']=='BLOCKED'


def test_blank_template_never_invents_measurements(tmp_path):
    plan,_=fixture(tmp_path);run=template(plan,'TEST-2','test-fingerprint')
    assert run['data_kind']=='NOT_TESTED' and all(row['value'] is None for row in run['readings'])
    assert evaluate(plan,run,'test-fingerprint',tmp_path,NOW)['status']=='BLOCKED'


def test_malformed_empty_plan_never_passes(tmp_path):
    plan,run=fixture(tmp_path);plan['cases']=[];run['readings']=[];run['plan_sha256']=plan_hash(plan)
    assert evaluate(plan,run,'test-fingerprint',tmp_path,NOW)['status']=='BLOCKED'
