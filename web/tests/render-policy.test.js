import test from 'node:test';
import assert from 'node:assert/strict';
import {surfaceSize,SceneClock,ResolutionBudget} from '../src/render-policy.js';
import {validateCAD,packCAD} from '../src/cad-data.js';
import {readFileSync} from 'node:fs';

for (const [width,height,dpr] of [[1440,1000,1],[390,844,3],[32000,1000,2],[1,100000,1],[100000,1,2],[0,0,1],[NaN,Infinity,NaN]]) {
  test(`render surface bounded for ${width} x ${height}`,()=>{
    const r=surfaceSize(width,height,dpr,1,4096);
    assert.ok(r.width>=1&&r.height>=1&&r.width<=4096&&r.height<=4096);
    assert.ok(r.width*r.height<=1_200_000);
  });
}
test('half quality reduces pixel area approximately fourfold',()=>{
  const a=surfaceSize(1440,1000,1,1),b=surfaceSize(1440,1000,1,.5);
  assert.ok(b.width*b.height<=a.width*a.height/4);
});
test('scene time excludes pauses and clamps suspended-tab jumps',()=>{
  const c=new SceneClock();assert.equal(c.advance(100,true),0);
  assert.equal(c.advance(120,true),.02);c.advance(300,false);c.advance(1000,false);
  assert.equal(c.advance(1010,true),.03);c.reset(100000);
  assert.equal(c.advance(100010,true),.04);assert.equal(c.advance(200000,true),.14);
  assert.equal(c.advance(199000,true),.14);assert.equal(c.advance(NaN,true),.14);
});
test('resolution hysteresis requires sustained samples and obeys quality bounds',()=>{
  const b=new ResolutionBudget();for(let i=0;i<7;i++)assert.equal(b.sample(40),false);
  assert.equal(b.sample(40),true);assert.equal(b.quality,.9);
  for(let i=0;i<200;i++)b.sample(70);assert.equal(b.quality,.5);
  for(let i=0;i<119;i++)assert.equal(b.sample(2),false);
  assert.equal(b.sample(2),true);assert.equal(b.quality,.6);
  for(let i=0;i<1000;i++)b.sample(2);assert.equal(b.quality,1);
  assert.equal(b.sample(NaN),false);
});
const triangle=()=>({name:'part',color:[1,0,0],opacity:1,explode:[0,0,1],vertices:[[0,0,0],[60,0,0],[0,60,0]],triangles:[[0,1,2]]});
test('CAD packing converts millimetres and coordinate handedness',()=>{
  const part=triangle();validateCAD([part]);const packed=packCAD(part);
  assert.equal(packed.length,18);assert.deepEqual([...packed.slice(0,6)],[0,0,0,0,1,0]);
  assert.deepEqual([...packed.slice(6,9)],[1,0,0]);assert.deepEqual([...packed.slice(12,15)],[0,0,1]);
});
test('invalid CAD documents fail before allocation',()=>{
  for(const mutate of [p=>p.vertices[0][0]=NaN,p=>p.triangles[0][0]=3,p=>p.opacity=-1,p=>p.name='<script>',p=>p.color=[2,0,0],p=>p.explode=[0,0,Infinity]]){
    const p=triangle();mutate(p);assert.throws(()=>validateCAD([p]));
  }
  assert.throws(()=>validateCAD([triangle(),triangle()]));assert.throws(()=>validateCAD([]));
});
test('all actual Rev B CAD parts satisfy the upload contract',()=>{
  const parts=JSON.parse(readFileSync(new URL('../assets/assembly.json',import.meta.url),'utf8'));
  assert.ok(validateCAD(parts).length>=26);
  for(const p of parts)assert.equal(packCAD(p).length,p.triangles.length*18);
});
