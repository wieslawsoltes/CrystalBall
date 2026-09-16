"""Archive committed public files only; never package workspace credentials."""
from pathlib import Path
import hashlib
import json
import subprocess
import zipfile
ROOT = Path(__file__).resolve().parents[1]
def main():
    names = subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    for name in filter(None,names):
        path=Path(name)
        if (any(x in path.parts for x in ('private', '.venv', '__pycache__', 'node_modules'))
            or any(x.endswith('.egg-info') for x in path.parts) or name.startswith('gateway/build/')
            or path.name == '.env' or path.suffix in ('.key','.pem') or path.name in ('nvs.bin','nvs.csv')):
            raise RuntimeError(f'Private or generated build material is tracked; packaging stopped: {name}')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    folder=ROOT/'handoff-package';folder.mkdir(exist_ok=True)
    archive=folder/'CrystalBall-RevB-Engineering-Handoff.zip'
    subprocess.run(['git','archive','--format=zip','--prefix=CrystalBall/','-o',str(archive),'HEAD'],cwd=ROOT,check=True)
    with zipfile.ZipFile(archive) as z:
        manifest={n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if not n.endswith('/')}
    record={'source_commit':commit,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
            'files':len(manifest),'release_status':'ENGINEERING_CANDIDATE_NOT_PRODUCTION_RELEASED',
            'limitations':['Physical qualification and owner authorization pending','OpenAI tests mocked','No deployable credential-bearing firmware image included']}
    (folder/'PACKAGE.json').write_text(json.dumps(record,indent=2)+'\n')
    (folder/'FILE-SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(record,indent=2))
if __name__=='__main__':main()
