import hashlib
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import Settings, create_app

ORIGIN = 'https://wieslawsoltes.github.io'
TOKEN = 'synthetic-browser-token-' + 'x'*32


def app():
    def no_paid_call(_):
        raise AssertionError('Pairing capabilities must not call OpenAI')
    cfg = Settings(api_key='test-only', token_hashes={'PAGES':hashlib.sha256(TOKEN.encode()).hexdigest()},
                   hosts=('testserver',), cors_origins=(ORIGIN,))
    return create_app(cfg, httpx.MockTransport(no_paid_call))


@pytest.mark.parametrize('endpoint,method', [('/v1/text','POST'),('/v1/fortune','POST'),('/v1/speech','POST'),
    ('/v1/realtime/call','POST'),('/v1/realtime/call/'+'x'*32,'DELETE'),('/v1/capabilities','GET')])
def test_pages_preflight_accepts_auth_headers_and_only_explicit_origin(endpoint, method):
    with TestClient(app()) as client:
        headers={'Origin':ORIGIN,'Access-Control-Request-Method':method,'Access-Control-Request-Headers':'authorization,content-type'}
        result=client.options(endpoint,headers=headers)
        assert result.status_code==200 and result.headers['access-control-allow-origin']==ORIGIN
        denied=client.options(endpoint,headers={**headers,'Origin':'https://untrusted.example'})
        assert denied.status_code==400 and 'access-control-allow-origin' not in denied.headers


def test_cors_does_not_replace_device_authentication_or_expose_project_key():
    with TestClient(app()) as client:
        assert client.get('/v1/capabilities',headers={'Origin':ORIGIN}).status_code==401
        result=client.get('/v1/capabilities',headers={'Origin':ORIGIN,'Authorization':'Bearer '+TOKEN})
        assert result.status_code==200 and result.headers['access-control-allow-origin']==ORIGIN
        assert 'test-only' not in result.text
        assert 'X-Orb-Call' in result.headers['access-control-expose-headers']
        assert 'X-Orb-Duration' in result.headers['access-control-expose-headers']
        assert 'access-control-allow-credentials' not in result.headers
