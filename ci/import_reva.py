"""Reconstruct and SHA-256 verify the exact supplied Rev A files before import."""
from pathlib import Path
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_SHA = '1949999319f49bb6eb79f5541bd68453d9aae72ab17f88fe3aad5c4ecf256c3f'

def main():
    data = b''.join((ROOT / f'.imports/reva.{i:02}').read_bytes() for i in range(7))
    if hashlib.sha256(data).hexdigest() != ARCHIVE_SHA:
        raise RuntimeError('Import transport checksum mismatch')
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:xz') as archive:
        for member in archive.getmembers():
            path = ROOT / member.name
            if not member.isfile() or not path.resolve().is_relative_to(ROOT):
                raise RuntimeError(f'Unsafe archive entry: {member.name}')
            if member.size > 2_000_000:
                raise RuntimeError('Unexpected source size')
        archive.extractall(ROOT, filter='data')
    for directory in ('preview', 'hardware/fabrication', 'hardware/reports'):
        (ROOT / directory).mkdir(parents=True, exist_ok=True)
    for script in ('tools/pcb.py', 'tools/schematic.py'):
        subprocess.run([sys.executable, str(ROOT / script)], cwd=ROOT, check=True)
    import cadquery as cq
    sys.path.insert(0, str(ROOT / 'mechanical'))
    import model
    assembly = cq.Assembly(name='Aether_Orb_RevA')
    for name, obj, color, explode in model.ASS:
        if name == '17_fit_coupon':
            continue
        alpha = .16 if name == '04_optical_globe' else .4 if name == '11_beamsplitter_OPTICAL' else 1
        assembly.add(obj, name=name, color=cq.Color(*color, alpha))
    step = ROOT / 'mechanical/Aether_Orb_RevA_Assembly.step'
    assembly.save(str(step))
    data = step.read_bytes()
    data = re.sub(rb"'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'", b"'2026-09-16T11:36:30'", data, count=1)
    anchor = data.index(b'#39672 =')
    tail = (ROOT / 'provenance/reva/step-presentation-tail.txt').read_bytes()
    step.write_bytes(data[:anchor] + tail)
    manifest = json.loads((ROOT / 'provenance/reva/SHA256.json').read_text())
    bad = [name for name, expected in manifest.items()
           if not (ROOT/name).is_file() or hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != expected]
    if bad:
        raise RuntimeError(f'Original-file verification failed: {bad}')
    report = {'original_files': len(manifest), 'verified': len(manifest), 'mismatches': [],
              'archive_sha256': ARCHIVE_SHA, 'meaning': 'byte-identical import, not engineering validation'}
    (ROOT / 'provenance/reva/import-result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
