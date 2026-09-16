/** Bounded authenticated transport. The project key never enters this module. */
export class Gateway {
  constructor(){this.base='';this.token='';this.aborters=new Set()}
  configure(url,token){
    const base=new URL(url||location.origin);
    if(base.protocol!=='https:'&&!(base.protocol==='http:'&&['localhost','127.0.0.1','[::1]'].includes(base.hostname)))throw new Error('Use HTTPS, or HTTP on localhost only.');
    if(base.username||base.password||base.search||base.hash||base.pathname!=='/')throw new Error('Enter a gateway origin without credentials or a path.');
    if(!/^[\x21-\x7e]{32,128}$/.test(token)||token.startsWith('sk-'))throw new Error('Enter a device token, not an OpenAI API key. The project key stays on your gateway.');
    this.base=base.origin;this.token=token;
  }
  fork(){const copy=new Gateway();copy.base=this.base;copy.token=this.token;return copy}
  async request(path,{body,method='POST',type='application/json',timeout=60000,signal}={}){
    if(!this.token)throw new Error('Connect your gateway first, or use the explicit demo mode.');
    if(!/^\/v1\/(text|fortune|speech|capabilities|realtime\/call(?:\/[A-Za-z0-9_-]{1,128})?)$/.test(path))throw new Error('Unsupported gateway endpoint');
    const own=new AbortController(),timer=setTimeout(()=>own.abort(),timeout);this.aborters.add(own);
    const joined=signal?AbortSignal.any([signal,own.signal]):own.signal;
    const cleanup=()=>{clearTimeout(timer);this.aborters.delete(own)};
    try{
      const r=await fetch(this.base+path,{method,headers:{Authorization:'Bearer '+this.token,...(body?{'Content-Type':type}:{})},body,signal:joined,credentials:'omit',redirect:'error',cache:'no-store',referrerPolicy:'no-referrer'});
      if(!r.body){cleanup();if(!r.ok)throw new Error(`Gateway returned ${r.status}`);return r}
      const max=!r.ok?8192:path==='/v1/text'?262144:path==='/v1/speech'?2160000:path.includes('/realtime/')?32768:8192;
      const reader=r.body.getReader();let total=0;
      const bounded=new ReadableStream({
        async pull(controller){try{const x=await reader.read();if(x.done){reader.releaseLock();cleanup();controller.close();return}total+=x.value.byteLength;if(total>max)throw new Error('Gateway response exceeds bounds');controller.enqueue(x.value)}catch(error){own.abort();await reader.cancel().catch(()=>{});cleanup();controller.error(error)}},
        async cancel(){own.abort();await reader.cancel().catch(()=>{});cleanup()}
      });
      const result=new Response(bounded,{status:r.status,statusText:r.statusText,headers:r.headers});
      if(!r.ok){let message=`Gateway returned ${r.status}`;try{const e=await result.json();if(typeof e.detail==='string')message=e.detail.slice(0,240)}catch{}throw new Error(message)}
      return result;
    }catch(error){cleanup();throw error}
  }
  async text(text,onText,signal){
    const r=await this.request('/v1/text',{body:JSON.stringify({text}),signal});if(!r.body)throw new Error('Streaming is unavailable');
    const reader=r.body.getReader(),decoder=new TextDecoder();let pending='',complete=false;
    try{while(true){const {done,value}=await reader.read();if(done)break;pending+=decoder.decode(value,{stream:true});if(pending.length>65536)throw new Error('Gateway line exceeds bounds');let end;while((end=pending.indexOf('\n'))>=0){const line=pending.slice(0,end);pending=pending.slice(end+1);if(!line)continue;const e=JSON.parse(line);if(e.type==='error')throw new Error(e.message||'Generation interrupted');if(['text','done'].includes(e.type)&&typeof e.text==='string')onText(e.text.slice(0,400));if(e.type==='done')complete=true}}if(!complete)throw new Error('The reading did not finish. Please try again.')}finally{await reader.cancel().catch(()=>{});reader.releaseLock()}
  }
  async fortune(wav,signal){const r=await this.request('/v1/fortune',{body:wav,type:'audio/wav',signal});const x=await r.json();if(typeof x.text!=='string'||x.text.length>400)throw new Error('Invalid reading');return x.text}
  async speech(text,signal){return (await this.request('/v1/speech',{body:JSON.stringify({text}),signal})).arrayBuffer()}
  async capabilities(){return (await this.request('/v1/capabilities',{method:'GET',timeout:5000})).json()}
  cancel(){for(const a of this.aborters)a.abort();this.aborters.clear()}
  forget(){this.cancel();this.token='';this.base=''}
}
