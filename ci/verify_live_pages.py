"""Verify the public HTTPS deployment against the manifest produced by the build job.

No credentials, TLS overrides, redirects or guessed deployment URLs. This tests
published bytes, not live AI, actual browser behavior or physical performance.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

BASE = 'https://wieslawsoltes.github.io/CrystalBall/'
MAX_ASSET = 16 * 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def validate_manifest(raw):
    if len(raw) > 128 * 1024:
        raise ValueError('Manifest exceeds publication limit')
    manifest = json.loads(raw)
    if (manifest.get('schema') != 1 or
        re.fullmatch(r'[a-f0-9]{40}', manifest.get('source_commit', '')) is None or
        manifest.get('release') != 'ENGINEERING_CANDIDATE_NOT_PRODUCTION_RELEASED'):
        raise ValueError('Unexpected publication manifest')
    files = manifest.get('files')
    if not isinstance(files, dict) or not 5 <= len(files) <= 100:
        raise ValueError('Unexpected publication file count')
    for name, digest in files.items():
        path = PurePosixPath(name)
        if (not re.fullmatch(r'[A-Za-z0-9_./-]+', name) or
            path.is_absolute() or '..' in path.parts or path.as_posix() != name or
            not re.fullmatch(r'[a-f0-9]{64}', digest)):
            raise ValueError('Unsafe publication entry')
    if not {'index.html', 'style.css', 'src/app.js', 'src/orb.wgsl', 'assets/assembly.json'} <= files.keys():
        raise ValueError('Publication lacks required entry points')
    return manifest


def verify_once(expected_bytes, read):
    expected = validate_manifest(expected_bytes)
    commit = expected['source_commit']
    query = '?crystalball_verify=' + commit
    actual = read(BASE + 'build.json' + query, 128 * 1024)
    if actual != expected_bytes:
        raise ValueError('Public build manifest differs from tested build')
    checked = {}
    for name, digest in expected['files'].items():
        data = read(BASE + name + query, MAX_ASSET)
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Public asset differs from tested build: ' + name)
        checked[name] = digest
    return {'passed': True, 'url': BASE, 'source_commit': commit, 'files': checked,
            'manifest_sha256': hashlib.sha256(actual).hexdigest(),
            'verified_at': datetime.now(timezone.utc).isoformat(),
            'meaning': 'Public HTTPS asset hashes match tested build; not live-provider qualification'}


def network_reader(url, limit):
    request = Request(url, headers={'User-Agent': 'CrystalBall-deployment-verifier/1',
                                   'Accept-Encoding': 'identity', 'Cache-Control': 'no-cache'})
    with build_opener(NoRedirect()).open(request, timeout=10) as response:
        if response.status != 200 or response.geturl() != url:
            raise ValueError('Unexpected public HTTPS response')
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError('Public asset exceeds publication limit')
        return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('verification/deployment/report.json'))
    args = parser.parse_args()
    with args.manifest.open('rb') as file:
        expected = file.read(128 * 1024 + 1)
    validate_manifest(expected)
    errors = []
    report = {'passed': False, 'url': BASE}
    for attempt in range(6):
        try:
            report = verify_once(expected, network_reader)
            report['attempts'] = attempt + 1
            break
        except (ValueError, HTTPError, URLError, TimeoutError, OSError) as error:
            errors.append(str(error))
            if attempt < 5:
                time.sleep(5)
    report['prior_attempt_errors'] = errors
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
