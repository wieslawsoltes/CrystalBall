"""Synthetic fault injection: never contacts the paid provider."""
import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import Settings, create_app
from app.realtime import Calls, Journal, provider_id
from app.voice_admin import reconcile

TOKEN = 'voice-unit-' + 'x'*40
AUTH = {'Authorization':'Bearer '+TOKEN, 'Content-Type':'application/sdp'}
SDP = b'v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n'


def settings(path, **extra):
    return Settings(api_key='test-project-secret', token_hashes={'test':hashlib.sha256(TOKEN.encode()).hexdigest()},
                    hosts=('testserver',), realtime_enabled=True, public_tts=True,
                    realtime_database=str(path), **extra)


def test_requires_durable_journal():
    with pytest.raises(ValueError, match='requires'):
        with TestClient(create_app(settings(''))):
            pass


def test_exclusive_kernel_worker_lock(tmp_path):
    path=str(tmp_path/'calls.sqlite')
    first=Journal(path)
    try:
        with pytest.raises(RuntimeError, match='another worker'):
            Journal(path)
    finally:
        first.close()
    second=Journal(path);second.close()


def test_restart_recovers_known_call_even_when_feature_disabled(tmp_path):
    path=tmp_path/'calls.sqlite';j=Journal(str(path));h=j.reserve('test',time.time(),90);j.bind(h,'rtc_KNOWN');j.close()
    seen=[]
    def provider(r):
        seen.append(str(r.url));return httpx.Response(200)
    cfg=replace(settings(path),realtime_enabled=False)
    with TestClient(create_app(cfg,httpx.MockTransport(provider))) as c:
        assert not c.app.state.calls.active
        assert not c.app.state.calls.unhealthy
    assert seen == ['https://api.openai.com/v1/realtime/calls/rtc_KNOWN/hangup']
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT state FROM calls').fetchone()[0]=='CLOSED'


def test_ambiguous_creation_survives_restart_and_requires_review(tmp_path):
    path=tmp_path/'calls.sqlite';j=Journal(str(path));h=j.reserve('test',time.time(),90);j.close()
    def never(_):raise AssertionError('Unknown ID must not trigger a guessed provider request')
    for _ in range(2):
        with TestClient(create_app(settings(path),httpx.MockTransport(never))) as c:
            health=c.get('/v1/capabilities',headers=AUTH).json()
            assert health['voice_health']['operator_review_required'] is True
            assert health['realtime'] is False
            assert c.post('/v1/realtime/call',headers=AUTH,content=SDP).status_code==503
    j=Journal(str(path));report=tmp_path/'review.txt';report.write_text('SYNTHETIC: no real provider session existed.')
    reconcile(j,h,'synthetic operator',report);j.close()
    with TestClient(create_app(settings(path),httpx.MockTransport(never))) as c:
        assert c.get('/v1/capabilities',headers=AUTH).json()['realtime'] is True


def test_reservation_is_durable_before_provider_contact_and_not_retried(tmp_path):
    path=tmp_path/'calls.sqlite';seen=[]
    def provider(r):
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT state,provider_id FROM calls').fetchone()==('RESERVED',None)
        seen.append(1)
        raise httpx.ReadTimeout('private network details')
    with TestClient(create_app(settings(path),httpx.MockTransport(provider))) as c:
        r=c.post('/v1/realtime/call',headers=AUTH,content=SDP)
        assert r.status_code==504 and 'private network' not in r.text
        assert c.post('/v1/realtime/call',headers=AUTH,content=SDP).status_code==503
    assert seen==[1]
    j=Journal(str(path));assert j.rows()[0]['state']=='UNKNOWN';j.close()


@pytest.mark.parametrize('location',['','https://evil.invalid/v1/realtime/calls/rtc_x','//api.openai.com/v1/realtime/calls/x',
    '/v1/realtime/calls/x?token=private','/v1/realtime/calls/x#fragment','/v1/realtime/calls/../x','/other/x',
    'http://api.openai.com/v1/realtime/calls/x','https://user@api.openai.com/v1/realtime/calls/x'])
def test_provider_location_validation(location):
    with pytest.raises(ValueError):provider_id(location)


@pytest.mark.parametrize('location',['/v1/realtime/calls/rtc_x','https://api.openai.com/v1/realtime/calls/rtc_x'])
def test_valid_provider_location(location):assert provider_id(location)=='rtc_x'


class BrokenSDP(httpx.AsyncByteStream):
    def __init__(self,path):self.path=path
    async def __aiter__(self):
        with sqlite3.connect(self.path) as db:
            assert db.execute('SELECT state,provider_id FROM calls').fetchone()==('ACTIVE','rtc_BROKEN')
        yield b'v=0\r\n'
        raise httpx.ReadError('sensitive SDP details')


def test_failed_sdp_download_immediately_cleans_known_call(tmp_path):
    path=tmp_path/'calls.sqlite';seen=[]
    def provider(r):
        seen.append(r.url.path)
        if r.url.path.endswith('/hangup'):return httpx.Response(200)
        return httpx.Response(201,stream=BrokenSDP(path),headers={'Location':'/v1/realtime/calls/rtc_BROKEN'})
    with TestClient(create_app(settings(path),httpx.MockTransport(provider))) as c:
        assert c.post('/v1/realtime/call',headers=AUTH,content=SDP).status_code==504
        assert not c.app.state.calls.active
        assert not c.app.state.calls.unhealthy
    assert seen[-1].endswith('/rtc_BROKEN/hangup')


@pytest.mark.parametrize('status',[404,410,401,500])
def test_unconfirmed_hangup_persists_and_blocks_new_sessions(tmp_path,status):
    path=tmp_path/'calls.sqlite'
    def provider(r):
        if r.url.path.endswith('/hangup'):return httpx.Response(status)
        return httpx.Response(201,content=SDP,headers={'Location':'/v1/realtime/calls/rtc_TEST'})
    with TestClient(create_app(settings(path),httpx.MockTransport(provider))) as c:
        r=c.post('/v1/realtime/call',headers=AUTH,content=SDP);assert r.status_code==200
        assert c.delete('/v1/realtime/call/'+r.headers['x-orb-call'],headers=AUTH).status_code==502
        assert c.post('/v1/realtime/call',headers=AUTH,content=SDP).status_code==503
    j=Journal(str(path));assert j.rows()[0]['state']=='CLOSING';j.close()


def test_failed_cleanup_recovered_on_later_restart(tmp_path):
    path=tmp_path/'calls.sqlite';j=Journal(str(path));h=j.reserve('test',time.time(),90);j.bind(h,'rtc_KNOWN');j.state(h,'CLOSING');j.close()
    with TestClient(create_app(settings(path),httpx.MockTransport(lambda _:httpx.Response(200)))) as c:
        assert c.get('/v1/capabilities',headers=AUTH).json()['voice_health']['ready'] is True


def test_journal_metadata_contains_no_sdp_or_credentials(tmp_path):
    path=tmp_path/'calls.sqlite'
    def provider(r):
        if r.url.path.endswith('/hangup'):return httpx.Response(200)
        return httpx.Response(201,content=SDP,headers={'Location':'/v1/realtime/calls/rtc_PRIVATE'})
    with TestClient(create_app(settings(path),httpx.MockTransport(provider))) as c:
        assert c.post('/v1/realtime/call',headers=AUTH,content=SDP).status_code==200
    data=b''.join(p.read_bytes() for p in tmp_path.glob('calls.sqlite*'))
    assert TOKEN.encode() not in data and b'test-project-secret' not in data and b'm=audio' not in data


def test_schema_and_disk_failure_fail_closed(tmp_path):
    path=tmp_path/'calls.sqlite';j=Journal(str(path));j.close()
    with sqlite3.connect(path) as db:db.execute('PRAGMA user_version=999')
    with pytest.raises(ValueError,match='schema'):Journal(str(path))


def test_concurrent_admission_and_hangup_are_serialized(tmp_path):
    async def run():
        seen=[]
        async def provider(r):
            seen.append(r.url.path);await asyncio.sleep(.01);return httpx.Response(200)
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
            app=SimpleNamespace(state=SimpleNamespace(settings=settings(tmp_path/'calls.sqlite'),upstream=SimpleNamespace(client=client)))
            calls=Calls(app);await calls.start()
            h=calls.reserve('test');calls.bind(h,'test','rtc_A');calls.pending.clear()
            with pytest.raises(HTTPException) as e:calls.reserve('test')
            assert e.value.status_code==409
            second=calls.reserve('other')
            with pytest.raises(HTTPException) as e:calls.reserve('third')
            assert e.value.status_code==503
            calls.set_state(second,'CLOSED')
            await asyncio.gather(calls.hangup(h),calls.hangup(h),calls.hangup(h))
            assert len(seen)==1
            await calls.close()
    asyncio.run(run())


def test_journal_write_failure_never_contacts_provider(tmp_path,monkeypatch):
    def never(_):raise AssertionError('Provider should not be reached')
    with TestClient(create_app(settings(tmp_path/'calls.sqlite'),httpx.MockTransport(never))) as c:
        def broken(*_):raise sqlite3.OperationalError('disk full')
        monkeypatch.setattr(c.app.state.calls.journal,'reserve',broken)
        r=c.post('/v1/realtime/call',headers=AUTH,content=SDP)
        assert r.status_code==503 and 'disk full' not in r.text
        assert c.get('/v1/capabilities',headers=AUTH).json()['voice_health']['journal_fault'] is True
