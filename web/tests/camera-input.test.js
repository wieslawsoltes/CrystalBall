import test from 'node:test';
import assert from 'node:assert/strict';
import {attachCameraInput} from '../src/camera-input.js';
class Canvas extends EventTarget {
  captures=new Set();clientHeight=1000;
  setPointerCapture(id){this.captures.add(id);} hasPointerCapture(id){return this.captures.has(id);}
  releasePointerCapture(id){this.captures.delete(id);} focus(){}
  send(type,values){const e=new Event(type,{cancelable:true});Object.assign(e,values);this.dispatchEvent(e);return e;}
}
const point=(id,x,y)=>({pointerId:id,button:0,clientX:x,clientY:y});
const setup=()=>{const c=new Canvas(),p={yaw:0,pitch:0,zoom:1};const stop=attachCameraInput(c,p,()=>Object.assign(p,{yaw:0,pitch:0,zoom:1}));return{c,p,stop};};
test('orbit stops on lost pointer capture',()=>{
  const{c,p}=setup();c.send('pointerdown',point(1,10,10));c.send('pointermove',point(1,20,30));
  assert.equal(p.yaw,.07);assert.equal(p.pitch,.05);c.send('lostpointercapture',point(1,20,30));
  c.send('pointermove',point(1,100,100));assert.equal(p.yaw,.07);
});
test('pinch changes distance not orbit; a third pointer is ignored',()=>{
  const{c,p}=setup();c.send('pointerdown',point(1,0,0));c.send('pointerdown',point(2,100,0));
  c.send('pointerdown',point(3,200,0));assert.equal(c.captures.size,2);
  c.send('pointermove',point(2,150,0));assert.equal(p.zoom,2/3);assert.equal(p.yaw,0);
  c.send('pointercancel',point(2,150,0));c.send('pointermove',point(1,5,0));assert.equal(p.yaw,.035);
});
test('keyboard camera controls are bounded and resettable',()=>{
  const{c,p}=setup();assert.equal(c.send('keydown',{key:'ArrowRight'}).defaultPrevented,true);
  for(let i=0;i<100;i++)c.send('keydown',{key:'+'});assert.equal(p.zoom,.55);
  c.send('keydown',{key:'Home'});assert.deepEqual(p,{yaw:0,pitch:0,zoom:1});
  assert.equal(c.send('keydown',{key:'a'}).defaultPrevented,false);
});
test('wheel normalizes line and page delta units',()=>{
  const a=setup(),b=setup();a.c.send('wheel',{deltaY:1,deltaMode:1});b.c.send('wheel',{deltaY:16,deltaMode:0});
  assert.equal(a.p.zoom,b.p.zoom);a.c.send('wheel',{deltaY:1,deltaMode:2});assert.equal(a.p.zoom,1.8);
});
test('disposing detaches input and releases every capture',()=>{
  const{c,p,stop}=setup();c.send('pointerdown',point(1,10,10));stop();stop();
  assert.equal(c.captures.size,0);c.send('pointermove',point(1,20,20));c.send('keydown',{key:'ArrowLeft'});assert.equal(p.yaw,0);
});
test('secondary mouse button cannot start orbit',()=>{
  const{c,p}=setup();c.send('pointerdown',{...point(1,0,0),button:2});c.send('pointermove',point(1,10,10));assert.equal(p.yaw,0);
});
