"""Prove an installable gateway wheel contains exactly the reviewed Python sources."""
import argparse
import base64
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def verify(wheel: Path, source: Path):
    expected = {}
    for file in source.rglob('*.py'):
        if file.is_symlink() or any(p.is_symlink() for p in file.parents):
            raise ValueError('Source symlink is not allowed')
        expected['app/' + file.relative_to(source).as_posix()] = file.read_bytes()
    if not expected or 'app/main.py' not in expected:
        raise ValueError('Missing gateway source')
    with zipfile.ZipFile(wheel) as archive:
        entries = [i for i in archive.infolist() if not i.is_dir()]
        names = [i.filename for i in entries]
        if len(names) != len(set(names)) or sum(i.file_size for i in entries) > 8 * 1024 * 1024:
            raise ValueError('Duplicate or oversized wheel')
        for item in entries:
            p = PurePosixPath(item.filename)
            if (p.is_absolute() or '..' in p.parts or '\\' in item.filename or
                p.as_posix() != item.filename or stat.S_ISLNK(item.external_attr >> 16)):
                raise ValueError('Unsafe wheel entry')
        actual = {n: archive.read(n) for n in names if n.startswith('app/')}
        if actual != expected:
            mismatches = sorted(n for n in actual.keys() | expected.keys() if actual.get(n) != expected.get(n))
            raise ValueError('Wheel/source mismatch: ' + ', '.join(mismatches))
        records = [n for n in names if n.endswith('.dist-info/RECORD')]
        if len(records) != 1:
            raise ValueError('Wheel must contain one RECORD')
        record = records[0]
        rows = list(csv.reader(io.StringIO(archive.read(record).decode('utf-8'))))
        if any(len(r) != 3 for r in rows) or len({r[0] for r in rows}) != len(rows) or {r[0] for r in rows} != set(names):
            raise ValueError('Invalid RECORD file coverage')
        for name, digest, size in rows:
            if name == record:
                if digest or size:
                    raise ValueError('Invalid RECORD self-reference')
                continue
            data = archive.read(name)
            actual_digest = 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()
            if digest != actual_digest or size != str(len(data)):
                raise ValueError('Invalid RECORD digest: ' + name)
    return {'passed': True, 'wheel_sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(),
            'python_files': len(expected),
            'sources': {n: hashlib.sha256(b).hexdigest() for n, b in sorted(expected.items())}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wheel', type=Path)
    parser.add_argument('--source', type=Path, default=ROOT / 'gateway/app')
    parser.add_argument('--output', type=Path, default=ROOT / 'verification/units/wheel.json')
    args = parser.parse_args()
    report = verify(args.wheel, args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
