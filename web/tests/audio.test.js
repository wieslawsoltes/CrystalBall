import test from 'node:test';
import assert from 'node:assert/strict';
import {Speaker} from '../src/audio.js';
class MockContext {
  static pending=false;static resolve=null;
  constructor(){this.state='suspended';this.destination={};this.started=0}
  resume(){this.state='running';return MockContext.pending?new Promise(r=>MockContext.resolve=r):Promise.resolve()}
  createBuffer(channels,count,rate){assert.equal(rate,24000);const data=new Float32Array(count);return {copyToChannel:x=>data.set(x),getChannelData:()=>data}}
  createBufferSource(){return {connect:target=>target,disconnect:()=>{},stop:()=>{},start:()=>{this.started++},onended:null}}
  createGain(){return {gain:{value:1},connect:()=>{},disconnect:()=>{}}}
  close(){this.state='closed';return Promise.resolve()}
}
globalThis.AudioContext=MockContext;
test('unlock creates and resumes context before awaiting the network', async()=>{
  const speaker=new Speaker();const unlocked=speaker.unlock();
  assert.equal(speaker.context.state,'running');await unlocked;await speaker.close();
});
test('cancel during context resume cannot start stale audio and wipes PCM', async()=>{
  MockContext.pending=true;const speaker=new Speaker(),pcm=new Uint8Array([7,3,4,9]).buffer;
  const play=speaker.play(pcm);speaker.stop();MockContext.resolve();
  assert.equal(await play,false);assert.equal(speaker.context.started,0);
  assert.deepEqual([...new Uint8Array(pcm)],[0,0,0,0]);MockContext.pending=false;await speaker.close();
});
test('playback end wipes AudioBuffer and detaches graph', async()=>{
  const speaker=new Speaker(),pcm=new Uint8Array([0,64,0,64]).buffer;
  let ended=false;assert.equal(await speaker.play(pcm,()=>ended=true),true);
  const buffer=speaker.buffer;assert.notEqual(buffer.getChannelData(0)[0],0);
  speaker.source.onended();assert.equal(ended,true);assert.equal(speaker.source,null);
  assert.ok(buffer.getChannelData(0).every(x=>x===0));await speaker.close();
});
