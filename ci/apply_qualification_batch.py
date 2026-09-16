"""Apply reviewed UTF-8 source patches once, with exact preimage/postimage hashes.

The XZ pieces are a transport container, not encrypted data. Original Rev A
history is untouched. Later source edits are never reverted by re-running this.
"""
from pathlib import Path
import hashlib
import json
import lzma
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BATCHES = {
    'recovery': '0dc7b668d12be7fbf2fa3e0a6b18177c2f021be34c6fb2085a302436f78a585a',
    'qualification': '5758b45e9e659f3d73306448e56b6248651884ff078eac682a4abd9bc360a10a',
}


def load_batch(name):
    expected = BATCHES[name]
    data = b''.join((ROOT / f'ci/batches/2026-09-16/{name}.{i:02}').read_bytes() for i in range(2))
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('Source transport hash mismatch')
    decoder = lzma.LZMADecompressor(memlimit=128*1024*1024)
    source = decoder.decompress(data, max_length=2*1024*1024+1)
    if not decoder.eof or decoder.unused_data or len(source)>2*1024*1024:
        raise ValueError('Invalid/bounded XZ source transport')
    batch = json.loads(source)
    if batch.get('schema')!=1 or batch.get('batch')!=name or not 1<=len(batch['entries'])<=40:
        raise ValueError('Invalid source batch')
    return batch['entries']


def apply(name):
    entries = load_batch(name)
    marker = ROOT / f'provenance/{name}-2026-09-16.json'
    if marker.exists():
        if json.loads(marker.read_text()).get('transport_sha256') != BATCHES[name]:
            raise ValueError('Conflicting batch provenance')
        print(name + ': already applied; preserving subsequent changes')
        return
    patches, seen = [], set()
    for item in entries:
        name_in = item['path']; rel = Path(name_in); path = ROOT/rel
        if (rel.as_posix()!=name_in or rel.is_absolute() or '..' in rel.parts or '\\' in name_in
            or rel.parts[0] not in ('web','gateway','factory','manufacturing','tools','docs','README.md','.gitignore')
            or 'private' in rel.parts or rel.name=='.env' or name_in in seen):
            raise ValueError('Unsafe/duplicate source path')
        if any(p.is_symlink() for p in [path, *path.parents]) or not path.resolve().is_relative_to(ROOT):
            raise ValueError('Symlink or escaped source path')
        before=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        if before != item['before_sha256']:
            raise ValueError('Preimage mismatch: '+name_in)
        patch=item['patch']
        first='--- a/'+name_in+'\n' if before else '--- /dev/null\n'
        if not patch.startswith(first+'+++ b/'+name_in+'\n'):
            raise ValueError('Invalid patch target')
        stats=subprocess.check_output(['git','apply','--numstat','-'],input=patch.encode(),cwd=ROOT,text=False)
        if len(stats.splitlines())!=1 or stats.decode().rstrip('\n').split('\t')[-1]!=name_in:
            raise ValueError('Patch affects an unexpected target')
        seen.add(name_in);patches.append(patch)
    payload=''.join(patches).encode()
    subprocess.run(['git','apply','--check','--whitespace=nowarn','-'],input=payload,cwd=ROOT,check=True)
    subprocess.run(['git','apply','--whitespace=nowarn','-'],input=payload,cwd=ROOT,check=True)
    for item in entries:
        if hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError('Postimage mismatch: '+item['path'])
    marker.parent.mkdir(exist_ok=True)
    marker.write_text(json.dumps({'transport_sha256':BATCHES[name],
        'files':{item['path']:item['sha256'] for item in entries},
        'meaning':'Reviewed source import, not physical qualification or production approval'},indent=2)+'\n')
    print(f'{name}: verified {len(entries)} exact source files')


if __name__=='__main__':
    for name in BATCHES:
        apply(name)
