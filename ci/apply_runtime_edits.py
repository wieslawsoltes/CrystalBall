"""Apply one immutable, hash-bound engineering changeset exactly once."""
from pathlib import Path
import hashlib
import json
ROOT = Path(__file__).resolve().parents[1]

def digest(data):
    return hashlib.sha256(data).hexdigest()

def main():
    marker = ROOT / 'provenance/runtime-hardening.json'
    if marker.exists():
        print('Changeset already applied; preserving subsequent source edits.')
        return
    spec_path = ROOT/'ci/runtime-edits.json'
    spec = json.loads(spec_path.read_text())
    pending = {}
    for name, item in spec.items():
        path = ROOT/name
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT) or Path(name).parts[0] not in ('firmware','gateway','web'):
            raise RuntimeError('Invalid changeset path')
        data = path.read_bytes()
        if digest(data) == item['after']:
            pending[path] = data
            continue
        if digest(data) != item['before']:
            raise RuntimeError(f'Source changed; review required: {name}')
        lines = data.decode('utf-8').splitlines(keepends=True)
        for start, end, text in reversed(item['edits']):
            if not 0 <= start <= end <= len(lines):
                raise RuntimeError('Invalid edit range')
            lines[start:end] = [text]
        result = ''.join(lines).encode('utf-8')
        if digest(result) != item['after']:
            raise RuntimeError(f'Result checksum mismatch: {name}')
        pending[path] = result
    for path, data in pending.items():
        path.write_bytes(data)
    marker.write_text(json.dumps({'changeset_sha256':digest(spec_path.read_bytes()), 'files':{str(p.relative_to(ROOT)):digest(d) for p,d in pending.items()},'release':'engineering; not physically qualified'},indent=2)+'\n')
    print(f'Applied and verified {len(pending)} source updates.')

if __name__ == '__main__':
    main()
