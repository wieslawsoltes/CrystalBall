"""BREP/mesh/interference checks. Not a substitute for measured component fit."""
from pathlib import Path
import sys,json,itertools
import trimesh
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'mechanical'))
import model
pairs=[]
objects=[(n,o.val()) for n,o,_,_ in model.ASS if n!='17_fit_coupon']
for (n,a),(m,b) in itertools.combinations(objects,2):
    x,y=a.BoundingBox(),b.BoundingBox()
    if x.xmax<=y.xmin+1e-5 or y.xmax<=x.xmin+1e-5 or x.ymax<=y.ymin+1e-5 or y.ymax<=x.ymin+1e-5 or x.zmax<=y.zmin+1e-5 or y.zmax<=x.zmin+1e-5:continue
    v=a.intersect(b).Volume()
    if v>0.02:
        pairs.append({'a':n,'b':m,'intersection_mm3':round(v,3)})
        print(pairs[-1],flush=True)
meshes=[]
for f in (ROOT/'mechanical/stl').glob('*.stl'):
    mesh=trimesh.load(f,force='mesh');meshes.append({'part':f.stem,'watertight':bool(mesh.is_watertight),'winding_consistent':bool(mesh.is_winding_consistent),'triangles':len(mesh.faces),'zmin':round(float(mesh.bounds[0,2]),5)})
report={'checked':'BREP boolean intersections and exported STL topology','intersections':pairs,'meshes':meshes,
        'note':'Vendor components are envelope proxies. Exact terminal, cable, button, insert and tolerance-stack fit requires first article.'}
(ROOT/'hardware/reports/mechanical-checks.json').write_text(json.dumps(report,indent=2))
print('COMPLETE',len(pairs),'intersections',sum(not m['watertight'] for m in meshes),'nonwatertight',flush=True)

if pairs or not meshes or any(not m["watertight"] or not m["winding_consistent"] for m in meshes):
    raise SystemExit(1)
