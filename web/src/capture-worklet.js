class Capture extends AudioWorkletProcessor {
  constructor(){super();this.buffer=new Float32Array(2048);this.at=0;this.running=true;this.port.onmessage=e=>{if(e.data==='stop'){this.flush();this.running=false;this.port.postMessage({done:true})}}}
  flush(){if(!this.at)return;const pcm=this.buffer.slice(0,this.at);this.port.postMessage({pcm},[pcm.buffer]);this.at=0}
  process(inputs){if(!this.running)return false;const channels=inputs[0];if(channels?.length){for(let i=0;i<channels[0].length;i++){let s=0;for(const ch of channels)s+=ch[i];this.buffer[this.at++]=s/channels.length;if(this.at===this.buffer.length)this.flush()}}return true}
}
registerProcessor('orb-capture',Capture);
