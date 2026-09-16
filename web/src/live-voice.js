/** A voice attempt owns its peer, tracks, callbacks and credential snapshot.
 * Stopping frees local capture immediately; a late SDP reply is cleaned up using
 * the ORIGINAL gateway identity, never the credentials of a replacement session.
 */
export class LiveVoice {
  constructor(api) { this.api=api; this.run=null; this.generation=0; this.cleanupWarning=''; }
  get pc() { return this.run?.pc??null; }
  get stream() { return this.run?.stream??null; }
  get handle() { return this.run?.handle??null; }
  current(run) { return this.run===run&&!run.stopped; }

  async start(onText,onState) {
    if(this.run) throw new Error('A voice session is already starting or active.');
    if(!navigator.mediaDevices?.getUserMedia) throw new Error('Microphone requires HTTPS or localhost.');
    const run={generation:++this.generation,api:this.api.fork(),stopped:false,pc:null,
      stream:null,audio:null,dc:null,handle:null,text:'',timer:null,cleanup:null};
    this.run=run; this.cleanupWarning='';
    const state=message=>{if(this.current(run))onState(message)};
    try {
      const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false});
      run.stream=stream;
      if(!this.current(run)) return false;
      const pc=new RTCPeerConnection(); run.pc=pc;
      const audio=new Audio(); run.audio=audio; audio.autoplay=true; audio.volume=.5;
      pc.ontrack=event=>{
        if(!this.current(run))return;
        audio.srcObject=event.streams?.[0]??new MediaStream([event.track]);
        audio.play().catch(()=>state('Audio playback was blocked. End live voice and retry with a user gesture.'));
      };
      stream.getTracks().forEach(track=>pc.addTrack(track,stream));
      const dc=pc.createDataChannel('oai-events'); run.dc=dc;
      dc.onmessage=event=>{
        if(!this.current(run)||typeof event.data!=='string'||event.data.length>65536)return;
        let data;try{data=JSON.parse(event.data)}catch{return}
        if(!data||typeof data!=='object')return;
        if(data.type==='response.created')run.text='';
        if(['response.output_audio_transcript.delta','response.audio_transcript.delta','response.output_text.delta'].includes(data.type)&&typeof data.delta==='string'){
          run.text=(run.text+data.delta).slice(0,400); onText(run.text);
        }
        if(data.type==='error')state('Live voice reported an error. End the session and check the gateway.');
      };
      pc.onconnectionstatechange=()=>{
        if(this.current(run)&&['failed','closed','disconnected'].includes(pc.connectionState))this.end(run,onState,'Live voice ended.');
      };
      const offer=await pc.createOffer(); if(!this.current(run))return false;
      await pc.setLocalDescription(offer); if(!this.current(run))return false;
      // This bounded request deliberately outlives local cancellation so its call
      // handle can be terminated. A process/network loss is covered by the journal.
      const reply=await run.api.request('/v1/realtime/call',{body:offer.sdp,type:'application/sdp',timeout:30000});
      const handle=reply.headers.get('X-Orb-Call');
      if(!/^[A-Za-z0-9_-]{32}$/.test(handle??'')){
        await reply.body?.cancel(); throw new Error('Gateway omitted a manageable voice handle.');
      }
      run.handle=handle;
      if(!this.current(run)){await reply.body?.cancel();return false}
      const sdp=await reply.text(); if(!this.current(run))return false;
      const seconds=Number(reply.headers.get('X-Orb-Duration'));
      if(!Number.isInteger(seconds)||seconds<30||seconds>300||!sdp.startsWith('v=0'))throw new Error('Invalid gateway voice session.');
      await pc.setRemoteDescription({type:'answer',sdp}); if(!this.current(run))return false;
      run.timer=setTimeout(()=>this.end(run,onState,'Live voice time limit reached.'),seconds*1000);
      state(`Live AI voice · maximum ${seconds} seconds`);return true;
    } catch(error) {
      const current=this.current(run);
      if(current){this.run=null;this.generation++;}
      run.stopped=true;
      await this.dispose(run);
      if(current)throw error;
      return false;
    } finally {
      if(!this.current(run)){await this.dispose(run);run.api.forget();}
    }
  }

  end(run,onState,message) {
    const generation=this.generation+1;
    void this.stop().then(()=>{if(this.generation===generation)onState(message)});
  }

  detach(run) {
    run.stopped=true;clearTimeout(run.timer);run.text='';
    if(run.dc){run.dc.onmessage=null;run.dc.onerror=null;try{run.dc.close()}catch{}run.dc=null;}
    if(run.pc){run.pc.ontrack=null;run.pc.onconnectionstatechange=null;run.pc.close();run.pc=null;}
    run.stream?.getTracks().forEach(track=>track.stop());run.stream=null;
    if(run.audio){run.audio.pause();run.audio.srcObject=null;run.audio=null;}
  }

  async dispose(run) {
    this.detach(run);
    if(run.cleanup)return run.cleanup;
    if(!run.handle)return;
    if(!run.cleanup){
      const handle=run.handle;run.handle=null;
      run.cleanup=run.api.request('/v1/realtime/call/'+encodeURIComponent(handle),{method:'DELETE',timeout:15000})
        .then(async r=>{await r.body?.cancel();return true})
        .catch(()=>{this.cleanupWarning='Local microphone stopped. Provider hangup was not confirmed; the gateway will retry cleanup.';return false})
        .finally(()=>run.api.forget());
    }
    return run.cleanup;
  }

  async stop() {
    ++this.generation;
    const run=this.run;this.run=null;
    if(!run)return;
    await this.dispose(run);
  }
}
