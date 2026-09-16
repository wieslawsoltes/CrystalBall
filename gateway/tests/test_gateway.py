from __future__ import annotations
import hashlib, io, json, wave
import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import Settings, RateLimiter, ascii_text, validate_wav, create_app
TOKEN="test-device-token-"+"7"*40

def settings(**kwargs):
    return Settings(api_key="test-not-real",token_hashes={"ORB-TEST":hashlib.sha256(TOKEN.encode()).hexdigest()},hosts=("testserver",),**kwargs)
def wav(seconds=.5,rate=16000):
    out=io.BytesIO()
    with wave.open(out,"wb") as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate);w.writeframes(b'\0\0'*int(seconds*rate))
    return out.getvalue()
def provider(req):
    assert req.headers['authorization']=='Bearer test-not-real'
    if req.url.path.endswith('/audio/transcriptions'):
        assert b'RIFF' in req.content
        return httpx.Response(200,json={'text':'What does tomorrow hold?'})
    if req.url.path.endswith('/responses'):
        obj=json.loads(req.content);assert obj['store'] is False
        assert obj['max_output_tokens']==256
        return httpx.Response(200,json={'output':[{'type':'reasoning'},{'type':'message','content':[{'type':'output_text','text':'Perhaps a new conversation will open a door. Your choices remain your own.'}]}]})
    if req.url.path.endswith('/audio/speech'):
        assert json.loads(req.content)['response_format']=='pcm'
        return httpx.Response(200,content=b'\0\0'*2400)
    raise AssertionError(req.url)

def client(**kwargs):return TestClient(create_app(settings(**kwargs),httpx.MockTransport(provider)))
def auth():return {'Authorization':'Bearer '+TOKEN,'Content-Type':'audio/wav'}

def test_live_without_cloud():
    with client() as c:assert c.get('/healthz').json()['revision']=='A'
def test_auth_required():
    with client() as c:assert c.post('/v1/fortune',content=wav()).status_code==401
def test_auth_wrong():
    with client() as c:assert c.post('/v1/fortune',content=wav(),headers={'Authorization':'Bearer '+'x'*48}).status_code==401
def test_end_to_end_mocked():
    with client() as c:
        r=c.post('/v1/fortune',content=wav(),headers=auth());assert r.status_code==200,r.text
        assert r.json()['kind']=='ai_entertainment';assert len(r.json()['text'])<=400
        assert r.headers['cache-control']=='no-store';assert 'tomorrow' not in r.text
@pytest.mark.parametrize('body',[b'',b'notwav',wav()[:-5],wav(.1),wav(.5,8000)])
def test_bad_audio(body):
    with client() as c:assert c.post('/v1/fortune',content=body,headers=auth()).status_code==422

def test_oversize():
    with client() as c:assert c.post('/v1/fortune',content=b'0'*270000,headers=auth()).status_code==413

def test_bad_media_type():
    with client() as c:
        h=auth();h['Content-Type']='text/plain';assert c.post('/v1/fortune',content=wav(),headers=h).status_code==415

def test_tts_default_off():
    with client() as c:assert c.post('/v1/speech',json={'text':'Hello'},headers={'Authorization':'Bearer '+TOKEN}).status_code==403

def test_tts_pcm_enabled():
    with client(public_tts=True) as c:
        r=c.post('/v1/speech',json={'text':'AI-generated entertainment.'},headers={'Authorization':'Bearer '+TOKEN})
        assert r.status_code==200;assert len(r.content)==4800;assert '24000' in r.headers['x-pcm-format']

def test_tts_input_not_echoed():
    with client(public_tts=True) as c:
        r=c.post('/v1/speech',json={'text':'private','extra':'secret'},headers={'Authorization':'Bearer '+TOKEN})
        assert r.status_code==422;assert 'secret' not in r.text

def test_upstream_failure_sanitized():
    def bad(_):return httpx.Response(500,text='SECRET KEY PROVIDER MESSAGE')
    with TestClient(create_app(settings(),httpx.MockTransport(bad))) as c:
        r=c.post('/v1/fortune',content=wav(),headers=auth());assert r.status_code==502;assert 'SECRET' not in r.text

def test_rate_limits():
    t=[0.];r=RateLimiter(2,3,lambda:t[0]);r.take('a');r.take('a')
    with pytest.raises(HTTPException) as e:r.take('a')
    assert e.value.status_code==429;t[0]=61;r.take('a');t[0]=122
    with pytest.raises(HTTPException):r.take('a')
    t[0]=86401;r.take('a')

def test_gateway_rate_limit():
    with client(requests_per_minute=1) as c:
        assert c.post('/v1/fortune',content=wav(),headers=auth()).status_code==200
        assert c.post('/v1/fortune',content=wav(),headers=auth()).status_code==429

def test_ascii_normalization():
    assert ascii_text('Łódź — “a choice”…')=='Lodz - "a choice"...'
    assert len(ascii_text('word '*200))<=400

def test_empty_response_rejected():
    with pytest.raises(HTTPException):ascii_text('   \n')

def test_missing_credentials_fails_closed():
    with pytest.raises(ValueError):Settings('',{})

def test_wrong_host():
    with client() as c:assert c.get('/healthz',headers={'Host':'evil.example'}).status_code==400
