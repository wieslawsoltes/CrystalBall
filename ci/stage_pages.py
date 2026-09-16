"""Stage only tracked browser assets, never the repository or gateway secrets."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '_site'


def main():
    if OUT.is_symlink():
        raise ValueError('Refusing a symbolic-link staging directory')
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    names = subprocess.check_output(['git', 'ls-files', '-z', 'web'], cwd=ROOT).decode().split('\0')
    hashes = {}
    for name in filter(None, names):
        rel = Path(name).relative_to('web')
        approved = (rel.as_posix() in ('index.html', 'style.css') or
                    rel.parts[0] in ('src', 'assets') and
                    rel.suffix in ('.js', '.wgsl', '.json', '.svg', '.png', '.webp'))
        if not approved:
            continue
        path = ROOT / name
        if any((ROOT / p).is_symlink() for p in [name, *Path(name).parents]):
            raise ValueError('Browser assets must not traverse symlinks')
        if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError('Invalid browser asset: ' + name)
        data = path.read_bytes()
        if re.search(rb'sk-(?:proj-)?[A-Za-z0-9_-]{20,}', data) or b'-----BEGIN PRIVATE KEY-----' in data:
            raise ValueError('Possible credential in browser asset; publication blocked')
        dest = OUT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        hashes[rel.as_posix()] = hashlib.sha256(data).hexdigest()
    for name in ('index.html', 'style.css', 'src/app.js', 'src/orb.wgsl', 'assets/assembly.json'):
        if name not in hashes:
            raise ValueError('Missing browser entry point: ' + name)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    (OUT / '.nojekyll').write_text('')
    (OUT / 'build.json').write_text(json.dumps({
        'schema': 1, 'source_commit': commit, 'files': hashes,
        'mode': 'Offline demo until explicitly paired to an external gateway',
        'release': 'ENGINEERING_CANDIDATE_NOT_PRODUCTION_RELEASED'
    }, indent=2) + '\n')
    print(f'Staged {len(hashes)} public browser assets from {commit}; no gateway, test or factory files.')


if __name__ == '__main__':
    main()
