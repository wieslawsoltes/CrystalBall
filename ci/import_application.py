"""One-time transfer of reviewed plain-text application source; never reverts later edits."""
from pathlib import Path
import hashlib, io, json, tarfile
ROOT=Path(__file__).resolve().parents[1]
SHA='9b77b7291feb1ef99e816c34b2009d44901b8990b165fea200992256c0561ffe'
def main():
    marker=ROOT/'provenance/application-import.json'
    if marker.exists():
        print('Application already imported; preserving current source.');return
    data=b''.join((ROOT/f'.imports/application.{i:02}').read_bytes() for i in range(5))
    if hashlib.sha256(data).hexdigest()!=SHA:raise RuntimeError('Source transport checksum mismatch')
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:xz') as archive:
        members=archive.getmembers()
        if len(members)!=21 or sum(m.size for m in members)>300000:raise RuntimeError('Unexpected archive shape')
        for m in members:
            path=ROOT/m.name
            if not m.isfile() or m.size>200000 or not path.resolve().is_relative_to(ROOT) or Path(m.name).parts[0] not in ('web','gateway','tests'):
                raise RuntimeError('Unsafe source entry')
        archive.extractall(ROOT,filter='data')
    test=ROOT/'tests/browser.py'
    content=test.read_text().replace("document.documentElement.dataset.renderer?.startsWith('WebGPU')", "document.documentElement.dataset.renderer==='WebGPU'")
    content=content.replace("await page.locator('#explode').fill('70');await page.locator('#explode').dispatch_event('input')", "await page.locator('#explode').evaluate(\"el=>{el.value='70';el.dispatchEvent(new Event('input',{bubbles:true}))}\")")
    test.write_text(content)
    marker.parent.mkdir(exist_ok=True)
    marker.write_text(json.dumps({'source_archive_sha256':SHA,'files':{m.name:hashlib.sha256((ROOT/m.name).read_bytes()).hexdigest() for m in members},'test_adjustments':['range input uses DOM input event','require exact WebGPU renderer label'],'release':'engineering; physical validation outstanding'},indent=2)+'\n')
if __name__=='__main__':main()
