import test from 'node:test';
import assert from 'node:assert/strict';
import {OrbRenderer} from '../src/renderer.js';
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return{promise,resolve,reject};};
const drain=()=>new Promise(r=>setImmediate(r));
let raf=0;
globalThis.requestAnimationFrame=()=>++raf;globalThis.cancelAnimationFrame=()=>{};
globalThis.matchMedia=()=>({matches:false});globalThis.devicePixelRatio=1;
globalThis.ResizeObserver=class{observe(){}unobserve(){}disconnect(){}};
globalThis.document=Object.assign(new EventTarget(),{hidden:false,documentElement:{dataset:{}}});
globalThis.GPUBufferUsage={UNIFORM:1,COPY_DST:2,VERTEX:4};globalThis.GPUTextureUsage={RENDER_ATTACHMENT:1};
class Canvas extends EventTarget {
  width=0;height=0;clientHeight=1000;
  getBoundingClientRect(){return{width:1440,height:1000};}
  getContext(kind){return kind==='webgpu'?{configure(){},unconfigure(){},getCurrentTexture:()=>({createView(){}})}:{};}
  cloneNode(){return new Canvas();}replaceWith(){}hasPointerCapture(){return false;}
}
function device() {
  const lost=deferred(),queue=deferred();let released=0;
  const value=Object.assign(new EventTarget(),{
    limits:{maxTextureDimension2D:8192,maxBufferSize:128*1024*1024},lost:lost.promise,
    destroy(){this.destroyed=true;},queue:{writeBuffer(){},onSubmittedWorkDone:()=>queue.promise},
    createBuffer:()=>({destroy(){released++;}}),createBindGroup:()=>({}),
    createTexture:()=>({destroy(){released++;}}),
    createShaderModule:()=>({getCompilationInfo:async()=>({messages:[]})}),
    createRenderPipelineAsync:async()=>({getBindGroupLayout:()=>({})})
  });return{value,lost,queue,released:()=>released};
}
const make=()=>{const info=[];const r=new OrbRenderer(new Canvas(),i=>info.push(i));r.drawGPU=()=>{};r.drawFallback=()=>{};r.drawCAD=()=>{};return{r,info};};
const mesh=[{name:'part',color:[1,0,0],opacity:1,explode:[0,0,0],vertices:[[0,0,0],[1,0,0],[0,1,0]],triangles:[[0,1,2]]}];

test('dispose during adapter acquisition prevents device creation',async()=>{
  const waiting=deferred();let calls=0;
  Object.defineProperty(navigator,'gpu',{configurable:true,value:{requestAdapter:()=>waiting.promise}});
  const{r}=make();const init=r.init();r.dispose();waiting.resolve({requestDevice(){calls++;}});await init;assert.equal(calls,0);
});
test('dispose during device acquisition destroys late device',async()=>{
  const waiting=deferred(),d=device();
  Object.defineProperty(navigator,'gpu',{configurable:true,value:{requestAdapter:async()=>({requestDevice:()=>waiting.promise})}});
  const{r}=make();const init=r.init();await drain();r.dispose();waiting.resolve(d.value);await init;assert.equal(d.value.destroyed,true);
});
test('fallback releases GPU and obsolete completion cannot update UI',async()=>{
  const d=device(),{r,info}=make();r.device=d.value;r.kind='WebGPU';r.context=r.canvas.getContext('webgpu');r.resize();
  r.tick(10);assert.equal(r.gpuBusy,true);r.fallback('test loss');
  assert.equal(d.value.destroyed,true);assert.equal(r.kind,'Canvas 2D');const n=info.length;
  d.queue.resolve();await drain();assert.equal(info.length,n);assert.equal(r.gpuBusy,false);r.dispose();
});
test('at most one frame is submitted and stationary CAD redraws only on change',async()=>{
  const d=device(),{r}=make();r.device=d.value;r.kind='WebGPU';let submits=0;r.drawGPU=()=>submits++;
  r.tick(1);r.tick(2);r.tick(3);assert.equal(submits,1);d.queue.resolve();await drain();
  r.cad=true;r.meshes=[];r.tick(4);await drain();const n=submits;r.tick(5);await drain();assert.equal(submits,n);
  r.params.yaw=.1;r.tick(6);await drain();assert.equal(submits,n+1);r.dispose();
});
test('concurrent CAD requests share one transaction and release all resources',async()=>{
  const d=device(),{r}=make();r.kind='WebGPU';r.device=d.value;let fetches=0;
  globalThis.fetch=async()=>{fetches++;return new Response(JSON.stringify(mesh));};
  const a=r.loadCAD(),b=r.loadCAD();assert.equal(a,b);assert.deepEqual(await a,['part']);assert.equal(fetches,1);
  assert.equal(r.meshes.length,1);assert.equal(r.meshes[0].vertices,undefined);
  r.dispose();assert.equal(d.released(),2);
});
test('CAD cancellation during shader creation cannot publish late geometry',async()=>{
  const d=device(),waiting=deferred(),{r}=make();r.kind='WebGPU';r.device=d.value;
  d.value.createRenderPipelineAsync=()=>waiting.promise;
  globalThis.fetch=async()=>new Response(JSON.stringify(mesh));
  const load=r.loadCAD();await drain();r.dispose();waiting.resolve({});
  await assert.rejects(load,{name:'AbortError'});assert.equal(r.meshes.length,0);assert.equal(r.loadedCAD,false);
});
test('failed CAD allocation rolls back every buffer created so far',async()=>{
  const d=device(),{r}=make();r.kind='WebGPU';r.device=d.value;
  d.value.createBindGroup=()=>{throw new Error('Allocation failed');};
  globalThis.fetch=async()=>new Response(JSON.stringify(mesh));
  await assert.rejects(r.loadCAD(),/Allocation failed/);assert.equal(d.released(),2);
  assert.equal(r.meshes.length,0);assert.equal(r.cadLoad,null);r.dispose();
});
