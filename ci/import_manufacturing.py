"""One-time import of reviewed manufacturing text sources, bound to their SHA-256.

The two transport pieces are an ordinary XZ tar archive, not encrypted data.
Only the five explicitly named regular text files below are accepted. Generated
PDF/CSV/DXF files are built from those sources by the handoff workflow.
"""
from pathlib import Path
import hashlib
import io
import json
import tarfile
ROOT = Path(__file__).resolve().parents[1]
SHA = '8c11d02f4311fa31e37a4099f1f96abff30320470f855140b27738d2bc28401b'
FILES = {
    'manufacturing/handbook.md':'34533750aa28932029cb15dacee62cf87d93c7cf22f44399eaabaf5ac9963300',
    'manufacturing/release-plan.json':'f369abecc2082843a5bdd767ebb54ce6c3b9dd2dea87d0aba9639291582b9d82',
    'factory/release_gate.py':'3f00f4b279654faa37a3c03833070d626efeb2867b0505ae077619564931f498',
    'factory/tests/test_release.py':'0f430880254a01261f2bb7170c85354dec5da3a420325ece02650900a31c8c5a',
    'tools/manufacturing.py':'8ea7bd5cd3f13862335402268bd6839bc8c9e9507fa522b8de9693715a227f7b'
}
def main():
    marker = ROOT/'provenance/manufacturing-import.json'
    if marker.exists():
        print('Sources already imported; preserving subsequent edits.');return
    data = b''.join((ROOT/f'.imports/manufacturing.{i:02}').read_bytes() for i in range(2))
    if hashlib.sha256(data).hexdigest() != SHA:
        raise RuntimeError('Manufacturing source transport checksum mismatch')
    pending = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:xz') as archive:
        members = archive.getmembers()
        if len(members) != len(FILES):raise RuntimeError('Unexpected file count')
        for member in members:
            if not member.isfile() or member.name not in FILES or member.size > 100000 or member.name in pending:
                raise RuntimeError('Unexpected archive member')
            path = ROOT/member.name
            if path.exists() or path.is_symlink() or not path.resolve().is_relative_to(ROOT):
                raise RuntimeError('Refusing to overwrite or escape repository')
            payload = archive.extractfile(member).read()
            payload.decode('utf-8')
            if hashlib.sha256(payload).hexdigest() != FILES[member.name]:
                raise RuntimeError(f'Source integrity failure: {member.name}')
            pending[member.name] = payload
    for name, payload in pending.items():
        path = ROOT/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(payload)
    marker.parent.mkdir(exist_ok=True)
    marker.write_text(json.dumps({'transport_sha256':SHA,'files':FILES,'release':'ENGINEERING_CANDIDATE'},indent=2)+'\n')
    print('Verified and imported all five manufacturing sources.')
if __name__ == '__main__':main()
