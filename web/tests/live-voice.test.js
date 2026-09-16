import test from 'node:test';
import assert from 'node:assert/strict';
import {LiveVoice} from '../src/live-voice.js';
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {resolve,reject,promise}};
const tick=()=>new Promise(r=>setImmediate(r));
function setup(){
  const mic=deferred(),offer=deferred(),reply=deferred(),remote=deferred();
  const track={stopped:false,stop(){this.stopped=true}};
  const stream={getTracks:()=>[track]};
  const calls=[],messages=[];
  const api={token:'original',fork(){const identity=this.token;return {request(path,options){calls.push({identity,path,options});return options.method==='DELETE'?Promise.resolve(new Response(null,{status:204})):reply.promise},forget(){}}}};
  Object.defineProperty(globalThis,'navigator',{configurable:true,value:{mediaDevices:{getUserMedia:()=>mic.promise}}});
  let pc;
  globalThis.RTCPeerConnection=class {
    constructor(){pc=this;this.dc={close(){this.closed=true}};this.closed=false;this.remoteCalls=0;this.connectionState='new';}
    addTrack(){} createDataChannel(){return this.dc} createOffer(){return offer.promise}
    async setLocalDescription(){} async setRemoteDescription(){this.remoteCalls++;await remote.promise}
    close(){this.closed=true}
  };
  globalThis.Audio=class {play(){return Promise.resolve()} pause(){} };
  const live=new LiveVoice(api);
  return {mic,offer,reply,remote,track,stream,calls,messages,api,live,get pc(){return pc},
    async begin(){const p=live.start(x=>messages.push(x),x=>messages.push(x));mic.resolve(stream);await tick();offer.resolve({sdp:'v=0\r\nm=audio'});await tick();return {p}},
    response(handle='h'.repeat(32),duration='90'){return new Response('v=0\r\nm=audio',{headers:{'X-Orb-Call':handle,'X-Orb-Duration':duration}})}};
}

test('stop while permission is pending closes the late microphone without creating a peer',async()=>{
  const x=setup(),p=x.live.start(()=>{},()=>{});await x.live.stop();x.mic.resolve(x.stream);
  assert.equal(await p,false);assert.equal(x.track.stopped,true);assert.equal(x.pc,undefined);assert.equal(x.calls.length,0);
});
test('stop during offer generation does not send SDP',async()=>{
  const x=setup(),p=x.live.start(()=>{},()=>{});x.mic.resolve(x.stream);await tick();await x.live.stop();
  x.offer.resolve({sdp:'v=0'});assert.equal(await p,false);assert.equal(x.track.stopped,true);assert.equal(x.calls.length,0);
});
test('late successful response is hung up with original credential snapshot',async()=>{
  const x=setup(),{p}=await x.begin();const old=x.pc;await x.live.stop();x.api.token='replacement';
  x.reply.resolve(x.response());assert.equal(await p,false);
  assert.equal(old.remoteCalls,0);assert.equal(x.track.stopped,true);
  const end=x.calls.find(c=>c.options.method==='DELETE');assert.equal(end.identity,'original');assert.ok(end.path.endsWith('h'.repeat(32)));
});
test('stale data-channel callback cannot restore erased private text',async()=>{
  const x=setup(),{p}=await x.begin();const callback=x.pc.dc.onmessage;
  await x.live.stop();callback({data:JSON.stringify({type:'response.output_text.delta',delta:'must not appear'})});
  x.reply.resolve(x.response());await p;assert.deepEqual(x.messages,[]);
});
test('stop while applying remote description cannot arm a timer or report active',async()=>{
  const x=setup(),{p}=await x.begin();x.reply.resolve(x.response());await tick();assert.equal(x.pc.remoteCalls,1);
  await x.live.stop();x.remote.resolve();assert.equal(await p,false);assert.deepEqual(x.messages,[]);assert.equal(x.live.pc,null);
});
test('normal voice lifecycle clears tracks, peer, channel and transcript on stop',async()=>{
  const x=setup(),{p}=await x.begin();const peer=x.pc;x.remote.resolve();x.reply.resolve(x.response());assert.equal(await p,true);
  peer.dc.onmessage({data:JSON.stringify({type:'response.output_audio_transcript.delta',delta:'Hello'})});
  assert.ok(x.messages.includes('Hello'));await x.live.stop();assert.equal(peer.closed,true);assert.equal(peer.dc.onmessage,null);assert.equal(peer.dc.closed,true);assert.equal(x.track.stopped,true);
  await x.live.stop();assert.equal(x.calls.filter(c=>c.options.method==='DELETE').length,1);
});
test('overlapping start rejects instead of reassigning a pending attempt',async()=>{
  const x=setup(),p=x.live.start(()=>{},()=>{});await assert.rejects(x.live.start(()=>{},()=>{}),/already/);
  await x.live.stop();x.mic.resolve(x.stream);await p;
});
test('invalid duration triggers cleanup and never starts voice',async()=>{
  const x=setup(),{p}=await x.begin();x.reply.resolve(x.response('h'.repeat(32),'Infinity'));
  await assert.rejects(p,/Invalid gateway/);assert.equal(x.track.stopped,true);assert.equal(x.live.pc,null);assert.equal(x.calls.length,2);
});
test('malformed data-channel messages never throw or propagate',async()=>{
  const x=setup(),{p}=await x.begin();x.remote.resolve();x.reply.resolve(x.response());await p;
  const initial=x.messages.length;for(const data of ['null','42','nope','{}','x'.repeat(65537)])x.pc.dc.onmessage({data});
  assert.equal(x.messages.length,initial);await x.live.stop();
});
