import hashlib
import json
import time
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import Settings, create_app
from app.budgets import DurableBudget

TOKEN = 'browser-token-' + 'x' * 40
AUTH = {'Authorization': 'Bearer ' + TOKEN}

def cfg(**extra):
    return Settings(api_key='test-project-secret', token_hashes={'BROWSER':hashlib.sha256(TOKEN.encode()).hexdigest()}, hosts=('testserver',), **extra)

def stream(*events):
    return ''.join('data: '+json.dumps(e)+'\r\n\r\n' for e in events)

def response(text='A conversation may open a door. The choice is yours.'):
    return httpx.Response(200, content=stream({'type':'response.output_text.delta','delta':text}, {'type':'response.completed'}), headers={'Content-Type':'text/event-stream'})

def use(provider=lambda _:response(), **extra):
    return TestClient(create_app(cfg(**extra),httpx.MockTransport(provider)))

def events(r):
    return [json.loads(line) for line in r.text.splitlines()]

def test_stream_contract():
    def provider(r):
        data=json.loads(r.content)
        assert r.url == 'https://api.openai.com/v1/responses'
        assert data['store'] is False and data['stream'] is True
        assert data['input']=='A question' and data['max_output_tokens']==256
        assert r.headers['authorization']=='Bearer test-project-secret'
        return response()
    with use(provider) as c:
        r=c.post('/v1/text',json={'text':'A question'},headers=AUTH)
        assert r.status_code==200
        assert events(r)[-1]['type']=='done'
        assert events(r)[-1]['kind']=='ai_entertainment'
        assert len(events(r)[-1]['text'])<=400
        assert 'test-project-secret' not in r.text
        assert c.app.state.slots._value==2

@pytest.mark.parametrize('payload',[{}, {'text':''},{'text':' '},{'text':'a'*2001},{'text':'secret','extra':'private'},{'text':123}])
def test_bad_question_sanitized(payload):
    with use() as c:
        r=c.post('/v1/text',json=payload,headers=AUTH)
        assert r.status_code==422
        assert 'secret' not in r.text and 'private' not in r.text

@pytest.mark.parametrize('endpoint',['/v1/text','/v1/realtime/call','/v1/capabilities'])
def test_auth(endpoint):
    with use() as c:
        r=c.get(endpoint) if endpoint.endswith('capabilities') else c.post(endpoint)
        assert r.status_code==401

@pytest.mark.parametrize('provider_response',[
    httpx.Response(500,text='private provider stack and key'),
    httpx.Response(200,content=stream({'type':'error','message':'private provider stack and key'})),
    httpx.Response(200,content=stream({'type':'response.output_text.delta','delta':'partial'})),
    httpx.Response(200,content='data: nope\n\n'),
    httpx.Response(200,content=stream({'type':'response.output_text.delta','delta':'x'*8001})),
    httpx.Response(200,content=stream({'type':'response.failed'})),
    httpx.Response(200,content=stream({'type':'response.incomplete'})),
    httpx.Response(200,content='data: '+'x'*270000),
])
def test_stream_failure_does_not_report_completed(provider_response):
    with use(lambda _:provider_response) as c:
        r=c.post('/v1/text',json={'text':'A question'},headers=AUTH)
        assert events(r)[-1]['type']=='error'
        assert 'private provider' not in r.text
        assert c.app.state.slots._value==2

def test_web_request_bound():
    with use() as c:
        assert c.post('/v1/text',content='x'*12001,headers={**AUTH,'Content-Type':'application/json'}).status_code==413
        assert c.post('/v1/text',content='{}',headers={**AUTH,'Content-Type':'text/plain'}).status_code==415

def test_capabilities_no_key_and_budget_free():
    with use(requests_per_minute=1) as c:
        for _ in range(5):
            r=c.get('/v1/capabilities',headers=AUTH)
            assert r.json()['speech'] is False and r.json()['realtime'] is False
            assert 'secret' not in r.text
        assert c.post('/v1/text',json={'text':'A question'},headers=AUTH).status_code==200

def test_cors_allowlist():
    with use(cors_origins=('https://owner.example',)) as c:
        r=c.options('/v1/text',headers={'Origin':'https://owner.example','Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'authorization,content-type'})
        assert r.headers['access-control-allow-origin']=='https://owner.example'
        r=c.options('/v1/text',headers={'Origin':'https://evil.example','Access-Control-Request-Method':'POST'})
        assert r.status_code==400 and 'access-control-allow-origin' not in r.headers

@pytest.mark.parametrize('origin',['*','http://public.example','https://owner.example/path','https://user:password@owner.example'])
def test_bad_cors_config(origin):
    with pytest.raises(ValueError): cfg(cors_origins=(origin,))

def test_durable_budget_survives_restart(tmp_path):
    db=str(tmp_path/'budget.sqlite3')
    DurableBudget(db,1,2).take('A')
    with pytest.raises(HTTPException) as e: DurableBudget(db,1,2).take('A')
    assert e.value.status_code==429
    DurableBudget(db,1,2).take('B')
    assert 'A question' not in Path(db).read_bytes().decode('latin1')

def test_live_voice_defaults_disabled():
    with use(public_tts=True) as c:
        assert c.post('/v1/realtime/call',headers={**AUTH,'Content-Type':'application/sdp'},content='v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n').status_code==403

def test_live_voice_handshake_hangup_and_ownership(tmp_path):
    seen=[]
    def provider(r):
        seen.append(r.url.path)
        assert r.headers['authorization']=='Bearer test-project-secret'
        if r.url.path.endswith('/hangup'):return httpx.Response(200)
        assert b'gpt-realtime-2.1' in r.content and b'marin' in r.content
        return httpx.Response(201,content=b'v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n',headers={'Location':'/v1/realtime/calls/rtc_TEST'})
    with use(provider,public_tts=True,realtime_enabled=True,realtime_database=str(tmp_path/"voice.sqlite"),requests_per_minute=1) as c:
        r=c.post('/v1/realtime/call',headers={**AUTH,'Content-Type':'application/sdp'},content='v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n')
        assert r.status_code==200
        h=r.headers['x-orb-call']
        assert 'test-project-secret' not in r.text
        assert c.delete('/v1/realtime/call/'+h,headers=AUTH).status_code==204
        assert len(c.app.state.calls.active)==0
    assert seen[-1].endswith('/rtc_TEST/hangup')

def test_static_opt_in(tmp_path):
    (tmp_path/'index.html').write_text('<h1>CrystalBall</h1>')
    with use(web_dir=str(tmp_path)) as c:
        r=c.get('/')
        assert r.status_code==200 and '<h1>CrystalBall</h1>' in r.text
        assert r.headers['x-frame-options']=='DENY'
