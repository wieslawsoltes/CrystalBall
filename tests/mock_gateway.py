"""Loopback-only CI fixture. No network connection to OpenAI is made."""
import hashlib
import json
from pathlib import Path
import httpx
from app.main import Settings, create_app
TOKEN = 'browser-test-device-token-not-a-secret'
TEXT = 'A quiet possibility appears. This is a fictional reflection, not a prediction. Ask a thoughtful question and choose a small step that feels right to you.'
def provider(request):
    path = request.url.path
    if path == '/v1/responses':
        payload=json.loads(request.content)
        if payload.get('stream'):
            events=[{'type':'response.output_text.delta','delta':TEXT[:55]}, {'type':'response.output_text.delta','delta':TEXT[55:]}, {'type':'response.completed'}]
            return httpx.Response(200,content=''.join('data: '+json.dumps(x)+'\n\n' for x in events),headers={'content-type':'text/event-stream'})
        return httpx.Response(200,json={'output':[{'type':'message','content':[{'type':'output_text','text':TEXT}]}]})
    if path.endswith('/transcriptions'):return httpx.Response(200,json={'text':'What might I discover?'})
    if path.endswith('/speech'):return httpx.Response(200,content=b'\0\0'*12000)
    return httpx.Response(503,json={'error':'UNEXPECTED MOCK ENDPOINT'})
app=create_app(Settings(api_key='CI_MOCK_NO_PROVIDER_KEY', token_hashes={'browser':hashlib.sha256(TOKEN.encode()).hexdigest()}, requests_per_minute=120, requests_per_day=10000, public_tts=True, web_dir=str(Path(__file__).resolve().parents[1]/'web')),transport=httpx.MockTransport(provider))
