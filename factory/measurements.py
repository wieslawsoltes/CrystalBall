"""Evaluate supplied first-article measurements; never acquire or invent readings.

Each value carries expanded uncertainty U and its declared coverage factor k.
PASS means [value-U,value+U] is wholly within declared specification limits;
FAIL means disjoint; overlap is INDETERMINATE. No statistical confidence or
product-safety approval is inferred from this interval test.
"""
from __future__ import annotations
import argparse
import datetime as dt
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path
import sys
try:
    from .common import ROOT, artifact_hash, private_write, unit_id
    from .release_gate import source_fingerprint
except ImportError:
    from common import ROOT, artifact_hash, private_write, unit_id
    from release_gate import source_fingerprint


def number(value) -> Decimal:
    if type(value) not in (str,int) or len(str(value))>40:
        raise ValueError('Measurements must be decimal strings or integers')
    result=Decimal(value)
    if not result.is_finite() or abs(result)>Decimal('1e12') or not -12 <= result.as_tuple().exponent <= 12:
        raise ValueError('Measurement outside finite decimal bounds')
    return result


def date(value):
    if not isinstance(value,str):raise ValueError('Explicit UTC timestamp required')
    result=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.utcoffset()!=dt.timedelta(0):raise ValueError('Explicit UTC timestamp required')
    return result


def interval_decision(value, uncertainty, lower=None, upper=None) -> dict:
    with localcontext() as ctx:
        ctx.prec=80
        value,uncertainty=number(value),number(uncertainty)
        if uncertainty<=0:raise ValueError('Positive expanded measurement uncertainty required')
        lower=None if lower is None else number(lower)
        upper=None if upper is None else number(upper)
        if lower is None and upper is None or lower is not None and upper is not None and lower>=upper:
            raise ValueError('Invalid specification limits')
        low,high=value-uncertainty,value+uncertainty
        inside=(lower is None or low>=lower) and (upper is None or high<=upper)
        outside=(lower is not None and high<lower) or (upper is not None and low>upper)
        return {'decision':'PASS' if inside else 'FAIL' if outside else 'INDETERMINATE',
                'interval_low':str(low),'interval_high':str(high)}


def plan_hash(plan):
    return hashlib.sha256(json.dumps(plan,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def evaluate(plan: dict, run: dict, fingerprint: str, root: Path=ROOT, now=None) -> dict:
    now=now or dt.datetime.now(dt.timezone.utc);errors=[];results=[]
    try:
        if plan.get('schema')!=1 or run.get('schema')!=1:raise ValueError('Unsupported measurement schema')
        if plan['product']!=run['product'] or plan['revision']!=run['revision']:raise ValueError('Product/revision mismatch')
        if run['source_fingerprint']!=fingerprint:raise ValueError('Stale design fingerprint')
        if run['plan_sha256']!=plan_hash(plan):raise ValueError('Changed qualification plan')
        unit_id(run['serial'])
        for field in ('operator','fixture_id','fixture_revision'):
            if not isinstance(run.get(field),str) or not run[field].strip():raise ValueError('Missing '+field)
        cases=plan['cases'];readings=run['readings']
        if not isinstance(cases,list) or not 1<=len(cases)<=1000:raise ValueError('Empty or oversized test plan')
        if not isinstance(readings,list) or len(readings)>10000:raise ValueError('Invalid readings collection')
        if type(plan['approved']) is not bool:raise ValueError('Explicit plan approval status required')
        ids=[case['id'] for case in cases]
        if len(set(ids))!=len(ids) or not all(isinstance(i,str) and i for i in ids):raise ValueError('Duplicate/invalid case IDs')
        if type(plan['max_age_days']) is not int or not 1<=plan['max_age_days']<=365:raise ValueError('Invalid age limit')
        grouped={}
        for reading in readings:
            key=reading['case']
            if key not in ids:raise ValueError('Unknown measurement case')
            if key in grouped:raise ValueError('Duplicate measurement case')
            grouped[key]=reading
        for case in cases:
            # Validate limits even for missing readings: empty/invalid plans never pass.
            interval_decision('0','1',case.get('lower'),case.get('upper'))
            key=case['id'];row=grouped.get(key)
            if row is None:
                results.append({'case':key,'decision':'NOT_TESTED'});errors.append(key+': missing reading');continue
            try:
                if row['unit']!=case['unit']:raise ValueError('Unit mismatch; no implicit conversions')
                measured=date(row['measured_utc']);due=date(row['calibration_due_utc'])
                calibrated=date(row['calibrated_utc'])
                if not calibrated<=measured<=now or measured>=due:raise ValueError('Measurement outside calibrated interval or in future')
                if measured<now-dt.timedelta(days=plan['max_age_days']):raise ValueError('Measurement is too old')
                if not isinstance(row['instrument_id'],str) or not row['instrument_id'].strip():raise ValueError('Instrument identity missing')
                if not Decimal(1)<=number(row['coverage_factor'])<=Decimal(10):raise ValueError('Coverage factor must be 1 to 10')
                if artifact_hash(root,row['raw']['path'])!=row['raw']['sha256']:raise ValueError('Raw acquisition attachment hash mismatch')
                outcome=interval_decision(row['value'],row['expanded_uncertainty'],case.get('lower'),case.get('upper'))
                results.append({'case':key,'unit':case['unit'],**outcome})
                if outcome['decision']!='PASS':errors.append(key+': '+outcome['decision'])
            except (KeyError,TypeError,ValueError,OSError,InvalidOperation) as exc:
                results.append({'case':key,'decision':'INVALID'});errors.append(key+': '+str(exc))
        if plan['approved'] is not True:errors.append('Qualification limits are DRAFT; owner approval is absent')
        if run.get('data_kind')!='MEASURED':errors.append('Input is NOT_TESTED or SYNTHETIC, not physical acquisition')
    except (KeyError,TypeError,ValueError,AttributeError,InvalidOperation) as exc:
        errors.append('Invalid measurement run: '+str(exc))
    return {'schema':1,'status':'BLOCKED' if errors else 'WITHIN_DECLARED_LIMITS_REQUIRES_REVIEW',
            'source_fingerprint':fingerprint,'plan_sha256':plan_hash(plan),'results':results,'errors':errors,
            'limitation':'Computational evaluation of supplied data only. Plan approval and measurement provenance require authenticated review. No production authorization.'}


def template(plan,serial,fingerprint):
    unit_id(serial)
    return {'schema':1,'product':plan['product'],'revision':plan['revision'],'serial':serial,
            'source_fingerprint':fingerprint,'plan_sha256':plan_hash(plan),'data_kind':'NOT_TESTED',
            'operator':'','fixture_id':'','fixture_revision':'',
            'readings':[{'case':c['id'],'unit':c['unit'],'value':None,'expanded_uncertainty':None,
                        'coverage_factor':None,'instrument_id':'','calibrated_utc':'','calibration_due_utc':'',
                        'measured_utc':'','raw':{'path':'','sha256':''}} for c in plan['cases']]}


def read(path):
    if path.stat().st_size>2*1024*1024:raise ValueError('Measurement JSON exceeds 2 MiB')
    def pairs(items):
        data={}
        for key,value in items:
            if key in data:raise ValueError('Duplicate JSON key')
            data[key]=value
        return data
    def reject(_):raise ValueError('Nonfinite JSON is forbidden')
    return json.loads(path.read_text(),object_pairs_hook=pairs,parse_constant=reject)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['template','evaluate'])
    p.add_argument('--plan',type=Path,default=ROOT/'manufacturing/qualification-plan.json')
    p.add_argument('--serial');p.add_argument('--run',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();plan=read(a.plan);fingerprint=source_fingerprint()
    if a.action=='template':result=template(plan,a.serial,fingerprint)
    else:
        if a.run is None:raise ValueError('--run is required')
        result=evaluate(plan,read(a.run),fingerprint)
        result['run_sha256']=hashlib.sha256(a.run.read_bytes()).hexdigest()
    private_write(a.out,json.dumps(result,indent=2)+'\n')
    print(result.get('status','NOT_TESTED template created'))
    if a.action=='evaluate' and result['status']=='BLOCKED':raise SystemExit(1)


if __name__=='__main__':
    try:main()
    except (ValueError,TypeError,KeyError,OSError,InvalidOperation) as exc:
        print('Measurement operation failed: '+str(exc),file=sys.stderr);raise SystemExit(2)
