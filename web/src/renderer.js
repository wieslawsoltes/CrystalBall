import {camera,project,clamp} from './math.js';
import {surfaceSize,SceneClock,ResolutionBudget} from './render-policy.js';
import {attachCameraInput} from './camera-input.js';
import {validateCAD,packCAD} from './cad-data.js';
const meshShader=`struct U{matrix:mat4x4f,offset:vec4f,color:vec4f};@group(0) @binding(0) var<uniform> u:U;struct O{@builtin(position) p:vec4f,@location(0) n:vec3f,@location(1) world:vec3f};@vertex fn vs(@location(0) p:vec3f,@location(1) n:vec3f)->O{var o:O;let w=p+u.offset.xyz;o.p=u.matrix*vec4f(w,1);o.n=n;o.world=w;return o;}@fragment fn fs(o:O)->@location(0) vec4f{let n=normalize(o.n);let l=normalize(vec3f(-3,5,4));let diffuse=.24+.68*abs(dot(n,l));let rim=pow(1.-abs(n.z),3.);return vec4f(u.color.rgb*diffuse+vec3f(.10,.065,.18)*rim,u.color.a);}`;
export class OrbRenderer {
  constructor(canvas,onInfo) {
    this.canvas=canvas; this.info=onInfo;
    this.params={yaw:0,pitch:0,zoom:1,glow:.75,art:true,split:false,view:0,activity:0};
    this.cad=false; this.explode=0; this.selected=''; this.hidden=new Set();
    this.paused=matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.frame=0; this.frames=0; this.disposed=false; this.fps=0; this.quality=1;
    this.meshes=[]; this.clock=new SceneClock(); this.budget=new ResolutionBudget();
    this.epoch=0; this.uniformData=new Float32Array(12);
    this.lifetime=new AbortController();
    this.observer=new ResizeObserver(()=>this.resize()); this.observer.observe(canvas);
    this.installInput();
    document.addEventListener('visibilitychange',()=>{
      this.clock.reset(performance.now()); this.budget.reset(); this.lastCompleted=0;
    },{signal:this.lifetime.signal});
  }
  installInput(){this.detachInput?.();this.detachInput=attachCameraInput(this.canvas,this.params,()=>this.reset());}
  reset(){Object.assign(this.params,{yaw:0,pitch:0,zoom:1});}
  async init() {
    const epoch=++this.epoch;
    const current=()=>!this.disposed&&this.epoch===epoch;
    try {
      if(!navigator.gpu)throw new Error('WebGPU unavailable');
      const adapter=await navigator.gpu.requestAdapter({powerPreference:'high-performance'});
      if(!current())return; if(!adapter)throw new Error('No WebGPU adapter');
      const device=await adapter.requestDevice();
      if(!current()){device.destroy();return;}
      this.device=device;
      device.lost.then(x=>{if(current())this.fallback('WebGPU device lost: '+x.reason);});
      device.addEventListener('uncapturederror',e=>{if(current())this.fallback('WebGPU validation error: '+e.error.message);},{signal:this.lifetime.signal});
      this.context=this.canvas.getContext('webgpu');
      if(!this.context)throw new Error('WebGPU canvas context unavailable');
      this.format=navigator.gpu.getPreferredCanvasFormat();
      this.context.configure({device,format:this.format,alphaMode:'opaque'});
      const response=await fetch(new URL('./orb.wgsl',import.meta.url),{signal:this.lifetime.signal});
      if(!response.ok)throw new Error('Crystal shader unavailable');
      const code=await response.text(); if(!current())return;
      const module=device.createShaderModule({label:'CrystalBall glass and nebula',code});
      const compile=await module.getCompilationInfo(); if(!current())return;
      const errors=compile.messages.filter(x=>x.type==='error');
      if(errors.length)throw new Error(errors.map(x=>x.message).join('\n'));
      const pipeline=await device.createRenderPipelineAsync({layout:'auto',vertex:{module,entryPoint:'vs'},fragment:{module,entryPoint:'fs',targets:[{format:this.format}]},primitive:{topology:'triangle-list'}});
      if(!current())return; this.pipeline=pipeline;
      this.uniform=device.createBuffer({size:64,usage:GPUBufferUsage.UNIFORM|GPUBufferUsage.COPY_DST});
      this.bind=device.createBindGroup({layout:pipeline.getBindGroupLayout(0),entries:[{binding:0,resource:{buffer:this.uniform}}]});
      this.kind='WebGPU';this.resize();
      this.info({renderer:this.kind,detail:adapter.info?.description||adapter.info?.device||'Native GPU pipeline'});
    } catch(error) {if(current())this.fallback(error.message);}
    if(!this.disposed)this.tick(performance.now());
    return this.kind;
  }
  releaseGPU() {
    this.cadAbort?.abort(); this.cadAbort=null; this.cadLoad=null;
    this.depth?.destroy(); this.depth=null; this.uniform?.destroy(); this.uniform=null;
    for(const m of this.meshes){m.buffer.destroy();m.uniform.destroy();}
    this.meshes=[];this.loadedCAD=false;this.meshPipeline=null;this.glassPipeline=null;
    this.device?.destroy();this.device=null;this.pipeline=null;this.bind=null;
  }
  fallback(reason) {
    if(this.disposed||this.kind==='Canvas 2D')return;
    ++this.epoch;this.kind='Canvas 2D';this.cad=false;this.gpuBusy=false;
    if(this.context){
      this.context.unconfigure();this.context=null;
      const previous=this.canvas,copy=previous.cloneNode();
      this.detachInput?.();this.observer.unobserve(previous);previous.replaceWith(copy);
      this.canvas=copy;this.observer.observe(copy);this.installInput();
    }
    this.releaseGPU();this.ctx=this.canvas.getContext('2d');
    document.documentElement.dataset.gpuIdle='true';
    this.resize();this.info({renderer:this.kind,detail:reason});
    this.tick(performance.now());
  }
  resize() {
    if(this.disposed)return;
    const r=this.canvas.getBoundingClientRect();if(!r.width||!r.height)return;
    const size=surfaceSize(r.width,r.height,devicePixelRatio,this.quality,this.device?.limits.maxTextureDimension2D);
    this.width=r.width;this.height=r.height;
    if(this.canvas.width===size.width&&this.canvas.height===size.height&&this.depth)return;
    this.drawnSignature='';
    this.canvas.width=size.width;this.canvas.height=size.height;
    if(this.device&&this.kind==='WebGPU'){
      this.depth?.destroy();
      this.depth=this.device.createTexture({size:[size.width,size.height],format:'depth24plus',usage:GPUTextureUsage.RENDER_ATTACHMENT});
    }
  }
  tick(now) {
    if(this.disposed)return;
    // tick() is public for explicit fallback boot; prevent duplicate RAF chains.
    cancelAnimationFrame(this.frame);this.frame=requestAnimationFrame(t=>this.tick(t));
    this.time=this.clock.advance(now,!this.paused&&!document.hidden);
    if(document.hidden||this.gpuBusy)return;
    const signature=JSON.stringify([this.kind,this.canvas.width,this.canvas.height,this.params,
      this.cad,this.explode,this.selected,[...this.hidden],this.meshes.length]);
    if((this.paused||this.cad)&&signature===this.drawnSignature)return;
    this.drawnSignature=signature;
    const epoch=this.epoch,submitted=performance.now();
    const completed=()=>{
      if(this.disposed||epoch!==this.epoch)return;
      const finish=performance.now(),dt=finish-(this.lastCompleted||finish-16);
      this.lastCompleted=finish;this.fps=this.fps?this.fps*.8+.2*1000/Math.max(1,dt):1000/Math.max(1,dt);
      this.frames++;this.gpuBusy=false;document.documentElement.dataset.gpuIdle='true';
      if(finish-(this.lastInfo||0)>500){this.lastInfo=finish;this.info({fps:Math.round(this.fps)});}
      if(!this.paused&&!this.cad&&this.kind==='WebGPU'&&this.budget.sample(finish-submitted)){
        this.quality=this.budget.quality;this.resize();
      }
    };
    try {
      if(this.kind==='WebGPU'){
        this.gpuBusy=true;document.documentElement.dataset.gpuIdle='false';
        if(this.cad&&this.meshes.length)this.drawCAD();else this.drawGPU();
        this.device.queue.onSubmittedWorkDone().then(completed,error=>{
          if(!this.disposed&&epoch===this.epoch){this.gpuBusy=false;this.fallback(error.message);}
        });
      }else{this.drawFallback();completed();}
    }catch(error){this.gpuBusy=false;this.fallback(error.message);}
  }
  drawGPU() {
    const p=this.params,v=this.uniformData;
    v.set([this.canvas.width,this.canvas.height,this.time||0,p.activity,p.yaw,p.pitch,p.zoom,p.glow,Number(p.art),Number(p.split),p.view,0]);
    this.device.queue.writeBuffer(this.uniform,0,v);
    const e=this.device.createCommandEncoder(),pass=e.beginRenderPass({colorAttachments:[{view:this.context.getCurrentTexture().createView(),clearValue:{r:0,g:0,b:0,a:1},loadOp:'clear',storeOp:'store'}]});
    pass.setPipeline(this.pipeline);pass.setBindGroup(0,this.bind);pass.draw(3);pass.end();this.device.queue.submit([e.finish()]);
  }
  screenAnchor() {
    if(!this.width||!this.height)return{x:0,y:0,width:0,visible:false};
    const w=this.width/(this.params.split?2:1),cam=camera(this.params.yaw,this.params.pitch,this.params.zoom,w/this.height);
    const p=project([0,1.87,.16],cam.matrix,w,this.height),a=project([-.45,1.87,.16],cam.matrix,w,this.height),b=project([.45,1.87,.16],cam.matrix,w,this.height);
    return{x:p[0],y:p[1],width:Math.abs(b[0]-a[0])*1.25,visible:!this.cad&&this.params.view===0&&Math.cos(this.params.yaw)>.45};
  }
  loadCAD() {
    if(this.loadedCAD)return Promise.resolve(this.meshes.map(x=>x.name));
    if(this.cadLoad)return this.cadLoad;
    if(this.disposed||this.kind!=='WebGPU')return Promise.reject(new Error('The CAD mesh viewer requires WebGPU. Beauty preview remains available.'));
    const promise=this.loadCADInternal();this.cadLoad=promise;
    const clear=()=>{if(this.cadLoad===promise)this.cadLoad=null;};
    promise.then(clear,clear);return promise;
  }
  async loadCADInternal() {
    const epoch=this.epoch,d=this.device,pending=[];
    const valid=()=>{if(this.disposed||epoch!==this.epoch)throw new DOMException('CAD load cancelled','AbortError');};
    const controller=new AbortController();this.cadAbort=controller;
    try {
      const response=await fetch(new URL('../assets/assembly.json',import.meta.url),{signal:controller.signal});
      if(!response.ok)throw new Error('CAD asset is not installed');
      // Bound streaming response before JSON parsing, even without Content-Length.
      const reader=response.body.getReader(),chunks=[];let bytes=0;
      try {while(true){const{value,done}=await reader.read();if(done)break;bytes+=value.byteLength;if(bytes>16*1024*1024)throw new Error('CAD document exceeds memory budget');chunks.push(value);}}
      finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
      valid();const body=new Uint8Array(bytes);let at=0;for(const c of chunks){body.set(c,at);at+=c.length;}
      const source=validateCAD(JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(body)));
      const m=d.createShaderModule({code:meshShader});
      const descriptor={layout:'auto',vertex:{module:m,entryPoint:'vs',buffers:[{arrayStride:24,attributes:[{shaderLocation:0,offset:0,format:'float32x3'},{shaderLocation:1,offset:12,format:'float32x3'}]}]},fragment:{module:m,entryPoint:'fs',targets:[{format:this.format,blend:{color:{srcFactor:'src-alpha',dstFactor:'one-minus-src-alpha'},alpha:{srcFactor:'one',dstFactor:'one-minus-src-alpha'}}}]},primitive:{topology:'triangle-list',cullMode:'none'},depthStencil:{format:'depth24plus',depthWriteEnabled:true,depthCompare:'less'}};
      const solid=await d.createRenderPipelineAsync(descriptor);valid();
      const glass=await d.createRenderPipelineAsync({...descriptor,depthStencil:{...descriptor.depthStencil,depthWriteEnabled:false}});valid();
      for(const part of source){
        const data=packCAD(part);
        if(data.byteLength>d.limits.maxBufferSize)throw new Error('CAD part exceeds device buffer limit');
        const buffer=d.createBuffer({size:data.byteLength,usage:GPUBufferUsage.VERTEX|GPUBufferUsage.COPY_DST});
        const item={name:part.name,color:part.color,opacity:part.opacity,explode:part.explode,buffer,uniform:null,count:data.length/6,data:new Float32Array(24)};
        pending.push(item); // Every partially allocated resource is owned before next allocation.
        item.uniform=d.createBuffer({size:96,usage:GPUBufferUsage.UNIFORM|GPUBufferUsage.COPY_DST});
        d.queue.writeBuffer(buffer,0,data);
        const bind=p=>d.createBindGroup({layout:p.getBindGroupLayout(0),entries:[{binding:0,resource:{buffer:item.uniform}}]});
        item.bind=bind(solid);item.glassBind=bind(glass);
      }
      valid();this.meshPipeline=solid;this.glassPipeline=glass;this.meshes=pending;this.loadedCAD=true;
      return pending.map(x=>x.name);
    }catch(error){for(const m of pending){m.buffer.destroy();m.uniform?.destroy();}throw error;}
    finally{if(this.cadAbort===controller)this.cadAbort=null;}
  }
  drawCAD() {
    const d=this.device,e=d.createCommandEncoder(),pass=e.beginRenderPass({colorAttachments:[{view:this.context.getCurrentTexture().createView(),loadOp:'clear',storeOp:'store',clearValue:{r:.024,g:.028,b:.045,a:1}}],depthStencilAttachment:{view:this.depth.createView(),depthLoadOp:'clear',depthStoreOp:'store',depthClearValue:1}});
    const p=this.params,cam=camera(p.yaw,p.pitch,p.zoom*(1+this.explode*.22),this.width/this.height);
    // Opaque first, transparent second. This is a mesh inspector, not refractive CAD optics.
    for(const glass of [false,true])for(const part of this.meshes){
      if(this.hidden.has(part.name)||(part.opacity<1)!==glass)continue;
      const v=part.data,exp=part.explode;v.set(cam.matrix);
      v.set([exp[0]/60*this.explode,exp[2]/60*this.explode,exp[1]/60*this.explode,0],16);
      v.set([...part.color,part.opacity],20);if(part.name===this.selected)v.set([.9,.58,.20,1],20);
      d.queue.writeBuffer(part.uniform,0,v);pass.setPipeline(glass?this.glassPipeline:this.meshPipeline);
      pass.setBindGroup(0,glass?part.glassBind:part.bind);pass.setVertexBuffer(0,part.buffer);pass.draw(part.count);
    }
    pass.end();d.queue.submit([e.finish()]);
  }
  drawFallback(){const ctx=this.ctx;if(!ctx)return;const w=this.canvas.width,h=this.canvas.height;ctx.fillStyle='#100b18';ctx.fillRect(0,0,w,h);const count=this.params.split?2:1;for(let n=0;n<count;n++){ctx.save();const width=w/count;ctx.translate(width*(n+.5),h*.53);const r=Math.min(width*.29,h*.27)/this.params.zoom;const grad=ctx.createRadialGradient(-r*.3,-r*.6,r*.02,0,-r*.2,r);grad.addColorStop(0,'#988bae');grad.addColorStop(.2,'#35264f');grad.addColorStop(.7,'#221436');grad.addColorStop(.92,'#554772');grad.addColorStop(1,'#b8a6d2');ctx.fillStyle=grad;ctx.beginPath();ctx.arc(0,-r*.2,r,0,Math.PI*2);ctx.fill();ctx.save();ctx.beginPath();ctx.arc(0,-r*.2,r*.95,0,Math.PI*2);ctx.clip();if(this.params.art){for(let i=0;i<14;i++){const a=i*2.39+(this.time||0)*.06,x=Math.sin(a)*r*.48,y=-r*.2+Math.cos(a*1.3)*r*.55,g=ctx.createRadialGradient(x,y,0,x,y,r*.6);g.addColorStop(0,`rgba(146,61,240,${.11*this.params.glow})`);g.addColorStop(1,'rgba(86,12,170,0)');ctx.fillStyle=g;ctx.fillRect(-r,-r*1.3,r*2,r*2.3)}}ctx.restore();const b=ctx.createLinearGradient(-r,0,r,0);b.addColorStop(0,'#09090b');b.addColorStop(.3,'#3b3030');b.addColorStop(.6,'#111016');b.addColorStop(1,'#060608');ctx.fillStyle=b;ctx.beginPath();ctx.moveTo(-r*.83,r*.66);ctx.lineTo(-r*1.1,r*1.35);ctx.quadraticCurveTo(0,r*1.65,r*1.1,r*1.35);ctx.lineTo(r*.83,r*.66);ctx.fill();ctx.strokeStyle='#8b672e';ctx.lineWidth=r*.022;for(const y of [.73,1.34]){ctx.beginPath();ctx.ellipse(0,r*y,r*(y===.73?.87:1.1),r*.13,0,0,Math.PI*2);ctx.stroke()}ctx.fillStyle='#b8944f';ctx.textAlign='center';ctx.font=`${r*.37}px Georgia`;ctx.fillText('✧  ☾  ✦',0,r*1.18);ctx.strokeStyle='#b377ff';ctx.shadowColor='#8539ee';ctx.shadowBlur=r*.13;ctx.lineWidth=r*.025;ctx.beginPath();ctx.ellipse(0,r*.68,r*.78,r*.10,0,0,Math.PI*2);ctx.stroke();ctx.restore()}}
  dispose() {
    if(this.disposed)return;this.disposed=true;++this.epoch;
    cancelAnimationFrame(this.frame);this.lifetime.abort();this.detachInput?.();this.observer.disconnect();
    this.context?.unconfigure();this.context=null;this.releaseGPU();
  }
}
