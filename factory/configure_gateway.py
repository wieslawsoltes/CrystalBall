"""Interactive, local-only gateway bootstrap. Never sends credentials over the network."""
from __future__ import annotations
import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
from urllib.parse import urlsplit
try:
    from .common import ROOT, origin, private_write, unit_id
except ImportError:
    from common import ROOT, origin, private_write, unit_id

def configure(unit: str, url: str, api_key: str, *, speech: bool = False,
              realtime: bool = False, browser_origins: tuple[str, ...] = (), root: Path = ROOT) -> tuple[Path, Path]:
    unit, url = unit_id(unit), origin(url)
    if not isinstance(browser_origins, (tuple, list)) or len(browser_origins) > 8:
        raise ValueError("At most eight explicit browser origins are allowed")
    allowed_origins = []
    for value in browser_origins:
        normalized = origin(value)
        if urlsplit(normalized).port == 443:
            normalized = normalized[:-4]
        if normalized not in allowed_origins:
            allowed_origins.append(normalized)
    if urlsplit(url).port not in (None, 443):
        raise ValueError('Bundled Compose deployment uses HTTPS port 443')
    if not isinstance(api_key, str) or not api_key.startswith('sk-') or not 20 <= len(api_key) <= 512 or not all(33 <= ord(c) <= 126 and c not in "'\\$" for c in api_key):
        raise ValueError('Enter a valid OpenAI project API key; it is stored only in the gateway environment')
    if realtime and not speech:
        raise ValueError('Live voice requires explicit public speech enablement')
    env_path = root/'gateway/.env'
    credentials = root/f'factory/private/{unit}.json'
    if env_path.exists() or env_path.is_symlink() or credentials.exists() or credentials.is_symlink():
        raise FileExistsError('Existing gateway configuration or unit file: back it up and rotate deliberately; nothing overwritten')
    secret = secrets.token_urlsafe(48)
    digest = hashlib.sha256(secret.encode('ascii')).hexdigest()
    cfg = {'schema':1, 'unit':unit, 'url':url, 'token':secret}
    hosts = ','.join(dict.fromkeys([urlsplit(url).hostname, 'localhost', '127.0.0.1']))
    values = {
        'OPENAI_API_KEY':api_key,
        'DEVICE_TOKEN_SHA256':json.dumps({unit:digest}, separators=(',', ':')),
        'ORB_HOST':urlsplit(url).netloc,
        'ALLOWED_HOSTS':hosts,
        'OPENAI_TEXT_MODEL':'gpt-4.1-mini', 'OPENAI_TRANSCRIBE_MODEL':'gpt-4o-mini-transcribe',
        'OPENAI_TTS_MODEL':'gpt-4o-mini-tts', 'OPENAI_VOICE':'coral',
        'OPENAI_REALTIME_MODEL':'gpt-realtime-2.1', 'REALTIME_SECONDS':'90',
        'PUBLIC_TTS':str(speech).lower(), 'REALTIME_ENABLED':str(realtime).lower(),
        'REQUESTS_PER_MINUTE':'8', 'REQUESTS_PER_DAY':'200',
        'REALTIME_DATABASE':'/var/lib/orb/voice.sqlite',
        'BUDGET_DATABASE':'/var/lib/orb/budget.sqlite', 'WEB_DIRECTORY':'/opt/orb/web',
        'CORS_ORIGINS':','.join(allowed_origins)
    }
    body = '# PRIVATE. Never commit or include in a manufacturing archive.\n'
    body += '\n'.join(f"{key}='{value}'" for key, value in values.items())+'\n'
    private_write(credentials, json.dumps(cfg, indent=2)+'\n')
    try:
        private_write(env_path, body)
    except BaseException:
        credentials.unlink(missing_ok=True)
        raise
    return env_path, credentials

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unit', default='orb-0001')
    parser.add_argument('--url', default='https://orb-gateway.home.arpa')
    parser.add_argument('--speech', action='store_true', help='Explicitly enable AI-generated speaker playback')
    parser.add_argument('--realtime', action='store_true', help='Enable experimental bounded live voice; requires live qualification')
    parser.add_argument('--browser-origin', action='append', default=[], help='Explicit HTTPS frontend origin; repeatable; no repository path')
    args = parser.parse_args()
    unit_id(args.unit); origin(args.url)
    api_key = os.environ.get('OPENAI_API_KEY') or getpass.getpass('OpenAI project API key (hidden): ')
    env, device = configure(args.unit, args.url, api_key, speech=args.speech, realtime=args.realtime, browser_origins=tuple(args.browser_origin))
    print(f'Created {env.relative_to(ROOT)} and {device.relative_to(ROOT)} with restrictive permissions.')
    print('The project key was not printed. Read the device JSON locally when pairing the browser.')
    print('Set LAN DNS, run: cd gateway && docker compose up --build -d')
    print('Trust your Caddy root CA on your own clients; never disable TLS verification.')
    if os.name == 'nt':
        print('Windows: restrict both files to your user using NTFS ACLs; POSIX mode bits do not enforce Windows ACLs.')

if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as exc:
        print(f'Configuration not created: {exc}', file=sys.stderr)
        raise SystemExit(2)
