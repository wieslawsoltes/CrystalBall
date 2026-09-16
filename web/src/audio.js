import {wav16k,pcmFloats} from './wave.js';
export class Recorder {
  constructor(){this.generation=0;this.context=null;this.stream=null;this.node=null;this.chunks=[];this.count=0;this.stopping=null}
  async start(onLevel,onLimit){
    if(this.stream||this.context)throw new Error('Microphone already active');
    const generation=++this.generation;
    if(!navigator.mediaDevices?.getUserMedia)throw new Error('Microphone requires HTTPS or localhost.');
    const stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true},video:false});
    if(generation!==this.generation){stream.getTracks().forEach(t=>t.stop());return false}
    this.stream=stream;this.context=new AudioContext();this.chunks=[];this.count=0;
    try{
      await this.context.audioWorklet.addModule(new URL('./capture-worklet.js',import.meta.url));
      if(generation!==this.generation)return false;
      this.node=new AudioWorkletNode(this.context,'orb-capture');const source=this.context.createMediaStreamSource(stream),mute=this.context.createGain();mute.gain.value=0;
      source.connect(this.node);this.node.connect(mute).connect(this.context.destination);
      this.node.port.onmessage=({data})=>{if(data.done){this.flushResolve?.();return}if(!data.pcm||!this.context)return;const n=Math.min(data.pcm.length,Math.floor(this.context.sampleRate*8)-this.count);if(n<=0)return;const pcm=data.pcm.slice(0,n);this.chunks.push(pcm);this.count+=n;let rms=0;for(const x of pcm)rms+=x*x;onLevel(Math.sqrt(rms/pcm.length));if(this.count>=this.context.sampleRate*8)onLimit()};
      await this.context.resume();this.timer=setTimeout(onLimit,8000);return true;
    }catch(error){await this.stop(false);throw error}
  }
  async stop(send=true){
    ++this.generation;clearTimeout(this.timer);
    if(this.stopping)return this.stopping;
    this.stopping=this.finish(send);try{return await this.stopping}finally{this.stopping=null}
  }
  async finish(send){
    const ctx=this.context;
    try{
      if(this.node)await new Promise(resolve=>{this.flushResolve=resolve;this.node.port.postMessage('stop');setTimeout(resolve,100)});
      this.stream?.getTracks().forEach(t=>t.stop());this.node?.disconnect();
      const rate=ctx?.sampleRate||16000,pcm=new Float32Array(this.count);let at=0;for(const chunk of this.chunks){pcm.set(chunk,at);at+=chunk.length;chunk.fill(0)}
      let result=null;if(send&&pcm.length)result=wav16k(pcm,rate);pcm.fill(0);return result;
    }finally{this.stream?.getTracks().forEach(t=>t.stop());if(ctx&&ctx.state!=='closed')await ctx.close();this.stream=null;this.context=null;this.node=null;this.chunks=[];this.count=0;this.flushResolve=null}
  }
}
export class Speaker {
  constructor(){this.context=null;this.source=null;this.gain=null;this.buffer=null;this.generation=0;this.level=0}
  unlock(){
    this.context??=new AudioContext();
    // Calling resume synchronously from the click is required by mobile audio policies.
    return this.context.resume();
  }
  async play(pcm,onEnd){
    this.stop();const generation=this.generation;
    try{
      await this.unlock();
      if(generation!==this.generation)return false;
      const floats=pcmFloats(pcm),buffer=this.context.createBuffer(1,floats.length,24000);
      buffer.copyToChannel(floats,0);floats.fill(0);
      const source=this.context.createBufferSource(),gain=this.context.createGain();
      gain.gain.value=.35;source.buffer=buffer;source.connect(gain).connect(this.context.destination);
      this.source=source;this.gain=gain;this.buffer=buffer;
      source.onended=()=>{if(this.source!==source)return;this.release();onEnd?.()};
      source.start();return true;
    }finally{new Uint8Array(pcm).fill(0)}
  }
  release(){
    this.source?.disconnect();this.gain?.disconnect();
    this.buffer?.getChannelData(0).fill(0);
    this.source=null;this.gain=null;this.buffer=null;
  }
  stop(){
    ++this.generation;
    if(this.source){this.source.onended=null;try{this.source.stop()}catch{}}
    this.release();
  }
  async close(){this.stop();const context=this.context;this.context=null;if(context&&context.state!=='closed')await context.close()}
}
export class LiveVoice {
  constructor(api){this.api=api;this.pc=null;this.stream=null;this.handle=null;this.generation=0}
  async start(onText,onState){
    const g=++this.generation;
    const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false});
    if(g!==this.generation){stream.getTracks().forEach(t=>t.stop());return}
    this.stream=stream;
    const pc=new RTCPeerConnection();this.pc=pc;
    this.audio=new Audio();this.audio.autoplay=true;this.audio.volume=.5;
    pc.ontrack=e=>{if(g!==this.generation||!this.audio)return;this.audio.srcObject=e.streams[0];this.audio.play().catch(()=>onState('Tap live voice again to end; audio playback was blocked.'))};
    this.stream.getTracks().forEach(t=>pc.addTrack(t,this.stream));
    const dc=pc.createDataChannel('oai-events');let text='';dc.onmessage=e=>{if(typeof e.data!=='string'||e.data.length>65536)return;let data;try{data=JSON.parse(e.data)}catch{return}if(data.type==='response.created')text='';if(['response.output_audio_transcript.delta','response.audio_transcript.delta','response.output_text.delta'].includes(data.type)&&typeof data.delta==='string'){text=(text+data.delta).slice(0,400);onText(text)}if(data.type==='error')onState('Live voice reported an error. End the session and check the gateway.')};
    pc.onconnectionstatechange=()=>{if(['failed','closed','disconnected'].includes(pc.connectionState))this.stop().finally(()=>onState('Live voice ended.'))};
    try{const offer=await pc.createOffer();await pc.setLocalDescription(offer);const r=await this.api.request('/v1/realtime/call',{body:offer.sdp,type:'application/sdp',timeout:30000});this.handle=r.headers.get('X-Orb-Call');if(g!==this.generation){await this.stop();return}await pc.setRemoteDescription({type:'answer',sdp:await r.text()});const seconds=Number(r.headers.get('X-Orb-Duration'))||90;this.timer=setTimeout(()=>this.stop().finally(()=>onState('Live voice time limit reached.')),seconds*1000);onState(`Live AI voice · maximum ${seconds} seconds`)}catch(error){await this.stop();throw error}
  }
  async stop(){
    ++this.generation;clearTimeout(this.timer);const handle=this.handle;this.handle=null;const pc=this.pc;this.pc=null;if(pc){pc.ontrack=null;pc.onconnectionstatechange=null;pc.close()}this.stream?.getTracks().forEach(t=>t.stop());this.stream=null;if(this.audio){this.audio.pause();this.audio.srcObject=null;this.audio=null}if(handle)await this.api.request('/v1/realtime/call/'+encodeURIComponent(handle),{method:'DELETE',timeout:15000}).catch(()=>{});
  }
}
