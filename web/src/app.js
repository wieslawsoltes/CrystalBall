import {OrbRenderer} from './renderer.js';
import {Gateway} from './api.js';
import {Recorder,Speaker,LiveVoice} from './audio.js';
import {publicState,pages,clamp} from './math.js';

const $=id=>document.getElementById(id), url=new URL(location.href);
const isPublic=url.searchParams.get('client')==='1';
const channel=typeof BroadcastChannel==='function'?new BroadcastChannel('crystalball-visual-v1'):null;
const state={mode:'demo',activity:'idle',glow:.75,art:true,text:'',page:0,eraseAt:0,operation:0,recording:false,voice:false,capabilities:null};
const renderer=new OrbRenderer($('orb'),info=>{if(info.renderer){$('renderer-label').textContent=info.renderer;document.documentElement.dataset.renderer=info.renderer;$('renderer-label').title=info.detail||''}if(info.fps)$('fps-label').textContent=`${info.fps} FPS`});
if(url.searchParams.get('test')==='1')renderer.paused=true;
if(url.searchParams.get('renderer')==='canvas'){renderer.fallback('Explicit compatibility preview');renderer.tick(performance.now())}else await renderer.init();

function applyVisual(v){if(!v||v.v!==1)return;const x=publicState(v);renderer.params.glow=x.glow;renderer.params.art=x.art;renderer.params.activity=({recording:2,thinking:1,speaking:2,ready:.4,error:0,idle:0})[x.activity];}
function broadcast(){channel?.postMessage(publicState(state))}
function toast(message){$('toast').textContent=String(message).slice(0,350);$('toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').hidden=true,6500)}
if(isPublic){
  document.body.classList.add('public');renderer.params.view=1;renderer.resize();
  if(channel)channel.onmessage=e=>applyVisual(e.data);
  // This page never creates the gateway client, microphone or private transcript.
  window.addEventListener('pagehide',()=>{channel?.close();renderer.dispose()},{once:true});
}else{
  const api=new Gateway(),recorder=new Recorder(),speaker=new Speaker(),live=new LiveVoice(api);
  let abort=null,recordDown=false,selectedPart='',cadReady=false;
  const samples=[
    'A new beginning need not arrive with a grand sign. Perhaps it begins with a small conversation, a skill you practise, or a door you choose to open. Give curiosity a little room. The next step is still yours to decide.',
    'The crystal offers a fictional image: two paths meeting beneath a quiet sky. One is familiar; the other invites a question. Rather than seeking certainty, notice what matters to you, and choose one small, reversible step.',
    'Imagine a lantern illuminating only the next few stones. You do not need to see the whole road to explore thoughtfully. A patient question or a generous conversation may reveal a possibility you had not considered.',
    'A small seed rests beneath the surface. This is a story, not a prediction: attention, practice and kindness can give an idea room to grow. Which possibility would you enjoy nurturing this week?',
    'The orb reflects a pause between chapters. Nothing here determines your future. You may find something useful by looking at an old problem from a new angle, or asking someone you trust what they see.'
  ];
  function setActivity(activity,message){state.activity=activity;$('stage-state').textContent=message||({idle:'THE ORB IS QUIET',recording:'LISTENING · MICROPHONE ACTIVE',thinking:'A REFLECTION IS TAKING SHAPE',speaking:'AI-GENERATED VOICE',ready:'A MOMENT TO REFLECT',error:'THE CONNECTION NEEDS ATTENTION'})[activity];$('activity-dot').classList.toggle('recording',activity==='recording');applyVisual({...publicState(state)});broadcast();const busy=['recording','thinking','speaking'].includes(activity)||state.voice;$('ask').disabled=busy;$('cancel').disabled=!busy;$('speak').disabled=!state.text||!state.capabilities?.speech||state.mode!=='live'||busy;$('live-voice').disabled=state.mode!=='live'||!state.capabilities?.realtime||busy&&!state.voice;}
  function showText(text,kind=state.mode==='demo'?'DEMO · FICTIONAL SAMPLE':'OPENAI · FICTIONAL REFLECTION'){
    state.text=String(text).slice(0,400);const p=pages(state.text);state.page=clamp(state.page,0,p.length-1);$('answer').textContent=p[state.page]||'';$('reflection-text').textContent=p[state.page]||'';$('reflection-page').textContent=`${state.page+1} / ${p.length} · AI ENTERTAINMENT`;$('answer-kind').textContent=kind;$('page-label').textContent=`${state.page+1} / ${p.length}`;$('previous').disabled=p.length<2;$('next').disabled=p.length<2;$('erase').disabled=!state.text;updatePlate();
  }
  function updatePlate(){const anchor=renderer.screenAnchor(),p=$('reflection');p.hidden=!state.text||!anchor.visible;p.style.left=anchor.x+'px';p.style.top=anchor.y+'px';p.style.width=clamp(anchor.width,135,230)+'px';$('reflection-text').style.fontSize=clamp(anchor.width*.049,8,12)+'px'}
  function erase(){state.text='';state.page=0;state.eraseAt=0;$('reflection').hidden=true;$('reflection-text').textContent='';$('reflection-page').textContent='';$('answer').textContent='The last reflection has been erased. Ask a new question when you are ready.';$('answer-kind').textContent='A MOMENT OF STILLNESS';$('erase-count').textContent='';$('page-label').textContent='—';for(const id of ['previous','next','speak','erase'])$(id).disabled=true;if(!state.recording&&!state.voice)setActivity('idle')}
  async function cancel(){const partial=state.activity==='thinking';state.operation++;abort?.abort();api.cancel();recordDown=false;state.recording=false;state.voice=false;$('record').classList.remove('recording');$('record').textContent='● Hold to ask';$('live-voice').textContent='Live voice';$('level').style.width='0';speaker.stop();await Promise.allSettled([recorder.stop(false),live.stop()]);$('voice-note').textContent='Microphone off. Capture and playback stopped.';if(partial)erase();setActivity(state.text?'ready':'idle')}
  async function ask(question){
    if(['recording','thinking','speaking'].includes(state.activity)||state.voice)return;
    if(!question.trim()){toast('Write a question before consulting the orb.');$('question').focus();return}
    const op=++state.operation;abort=new AbortController();state.page=0;state.eraseAt=0;showText('');setActivity('thinking');
    try{
      if(state.mode==='demo'){
        const hash=[...question].reduce((h,c)=>(Math.imul(h,31)+c.charCodeAt(0))>>>0,7),text=samples[hash%samples.length];
        for(let i=0;i<text.length+7;i+=7){await new Promise(r=>setTimeout(r,24));if(op!==state.operation)return;showText(text.slice(0,i))}
      }else await api.text(question,text=>{if(op===state.operation)showText(text)},AbortSignal.any([abort.signal,AbortSignal.timeout(65000)]));
      if(op!==state.operation)return;state.eraseAt=Date.now()+90000;setActivity('ready');
    }catch(error){if(op!==state.operation)return;erase();setActivity('error');toast(error.name==='AbortError'?'Request cancelled.':error.message)}
  }
  async function startRecording(){
    if(recordDown||state.recording||['recording','thinking','speaking'].includes(state.activity)||state.voice)return;
    if(state.mode!=='live'){toast('Connect a gateway and select OpenAI gateway mode to record. Demo never opens your microphone.');return}
    recordDown=true;const op=++state.operation;abort=new AbortController();state.page=0;erase();state.recording=true;setActivity('recording','WAITING FOR MICROPHONE PERMISSION');$('record').classList.add('recording');$('record').textContent='■ Release to send';$('voice-note').textContent='Recording starts only with microphone permission. Release to send; maximum eight seconds.';
    try{const active=await recorder.start(rms=>{$('level').style.width=clamp(rms*500,0,100)+'%'},()=>finishRecording());if(active&&op===state.operation&&recordDown)setActivity('recording');else if(!recordDown)await recorder.stop(false)}catch(error){recordDown=false;state.recording=false;await cancel();toast(error.message)}
  }
  async function finishRecording(){
    if(!recordDown)return;recordDown=false;state.recording=false;const op=state.operation;$('record').classList.remove('recording');$('record').textContent='● Hold to ask';$('level').style.width='0';setActivity('thinking');$('voice-note').textContent='Microphone off. Sending the recording for transcription and a fictional reflection.';
    try{const wav=await recorder.stop(true);if(op!==state.operation)return;if(!wav){setActivity('idle');$('voice-note').textContent='Microphone off. No recording was sent.';return}let text;try{text=await api.fortune(wav,AbortSignal.any([abort.signal,AbortSignal.timeout(65000)]))}finally{new Uint8Array(wav).fill(0)}if(op!==state.operation)return;showText(text);state.eraseAt=Date.now()+90000;setActivity('ready');$('voice-note').textContent='Microphone off. The local recording buffer has been released.'}catch(error){if(op!==state.operation)return;erase();setActivity('error');toast(error.message)}
  }
  $('question-form').addEventListener('submit',e=>{e.preventDefault();ask($('question').value)});
  $('question').addEventListener('input',()=>$('character-count').textContent=`${$('question').value.length} / 2000`);
  $('question').addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key==='Enter'){e.preventDefault();ask($('question').value)}});
  $('record').addEventListener('pointerdown',e=>{if(e.button!==0)return;e.preventDefault();$('record').setPointerCapture(e.pointerId);startRecording()});$('record').addEventListener('pointerup',()=>finishRecording());$('record').addEventListener('pointercancel',()=>cancel());
  $('record').addEventListener('keydown',e=>{if([' ','Enter'].includes(e.key)&&!e.repeat){e.preventDefault();startRecording()}});$('record').addEventListener('keyup',e=>{if([' ','Enter'].includes(e.key)){e.preventDefault();finishRecording()}});
  $('cancel').addEventListener('click',()=>cancel());$('erase').addEventListener('click',async()=>{await cancel();erase();$('question').value='';$('character-count').textContent='0 / 2000'});
  $('previous').addEventListener('click',()=>{const p=pages(state.text);state.page=(state.page+p.length-1)%p.length;showText(state.text)});$('next').addEventListener('click',()=>{state.page=(state.page+1)%pages(state.text).length;showText(state.text)});
  $('speak').addEventListener('click',async()=>{const op=++state.operation;abort=new AbortController();setActivity('speaking');$('voice-note').textContent='The voice you hear is AI-generated. Microphone remains off.';try{await speaker.unlock();if(op!==state.operation)return;const pcm=await api.speech(state.text,AbortSignal.any([abort.signal,AbortSignal.timeout(60000)]));if(op!==state.operation){new Uint8Array(pcm).fill(0);return}await speaker.play(pcm,()=>{if(op===state.operation)setActivity('ready')})}catch(error){if(op===state.operation){setActivity('error');toast(error.message)}}});
  $('live-voice').addEventListener('click',async()=>{if(state.voice){await cancel();return}await cancel();const op=++state.operation;state.voice=true;$('live-voice').textContent='End live voice';setActivity('speaking');$('voice-note').textContent='Live microphone and AI-generated voice are active. End live voice to stop.';try{await live.start(text=>{if(op===state.operation){showText(text,'LIVE AI VOICE · TRANSCRIPT');state.eraseAt=Date.now()+90000}},message=>{$('voice-note').textContent=message;if(!live.pc){state.voice=false;$('live-voice').textContent='Live voice';setActivity('ready')}})}catch(error){state.voice=false;$('live-voice').textContent='Live voice';setActivity('error');toast(error.message)}});
  async function mode(value){if(value==='live'&&!api.token){$('settings').showModal();return}await cancel();state.mode=value;erase();$('mode-demo').classList.toggle('selected',value==='demo');$('mode-live').classList.toggle('selected',value==='live');$('mode-demo').setAttribute('aria-pressed',value==='demo');$('mode-live').setAttribute('aria-pressed',value==='live');$('voice-note').textContent=value==='demo'?'Microphone off. Demo uses local fictional samples; no API calls are made.':'Microphone off. Hold to ask sends audio to your gateway and OpenAI. Public voice is opt-in.';setActivity('idle')}
  $('mode-demo').addEventListener('click',()=>mode('demo'));$('mode-live').addEventListener('click',()=>mode('live'));
  $('settings-open').addEventListener('click',()=>$('settings').showModal());
  $('connect-form').addEventListener('submit',async e=>{e.preventDefault();$('connection-error').textContent='';try{api.configure($('gateway-url').value,$('device-token').value);state.capabilities=await api.capabilities();$('device-token').value='';$('settings').close();$('connection').classList.add('live');$('connection').lastChild.textContent=' Gateway connected';$('settings-open').innerHTML='Gateway settings <span>↗</span>';mode('live');toast('Gateway connected. Project API key stays on the server.')}catch(error){api.forget();$('connection-error').textContent=error.message}});
  $('forget').addEventListener('click',async()=>{await cancel();api.forget();state.capabilities=null;$('device-token').value='';$('connection').classList.remove('live');$('connection').lastChild.textContent=' Demo / offline';$('settings-open').innerHTML='Connect gateway <span>↗</span>';mode('demo');$('settings').close();toast('Credentials forgotten in this tab.')});
  document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>{const view=b.dataset.view;document.querySelectorAll('[data-view]').forEach(x=>{const active=x===b;x.classList.toggle('selected',active);x.setAttribute('aria-pressed',active)});renderer.params.split=view==='split';renderer.params.view=view==='client'?1:0;renderer.reset();updatePlate()}));
  $('glow').addEventListener('input',()=>{state.glow=Number($('glow').value)/100;$('glow-output').textContent=$('glow').value+'%';applyVisual(publicState(state));broadcast()});$('art').addEventListener('change',()=>{state.art=$('art').checked;applyVisual(publicState(state));broadcast()});
  $('client-window').addEventListener('click',()=>{const target=new URL(location.href);target.search='?client=1';target.hash='';window.open(target,'_blank','noopener,noreferrer');setTimeout(broadcast,600)});
  $('reset-view').addEventListener('click',()=>renderer.reset());$('motion').addEventListener('click',()=>{renderer.paused=!renderer.paused;$('motion').textContent=renderer.paused?'▷':'Ⅱ';$('motion').setAttribute('aria-pressed',renderer.paused)});$('fullscreen').addEventListener('click',()=>{if(document.fullscreenElement)document.exitFullscreen();else document.querySelector('.stage').requestFullscreen().catch(()=>toast('Fullscreen is unavailable in this browser.'))});
  async function engineering(on){
    if(on){try{if(!cadReady){const names=await renderer.loadCAD();for(const name of names){const row=document.createElement('div');row.className='part';row.setAttribute('role','listitem');const check=document.createElement('input');check.type='checkbox';check.checked=true;check.setAttribute('aria-label','Show '+name);check.onchange=()=>check.checked?renderer.hidden.delete(name):renderer.hidden.add(name);const button=document.createElement('button');button.textContent=name.replace(/^\d+_|^REF_/g,'').replaceAll('_',' ');button.onclick=()=>{selectedPart=name;renderer.selected=name;document.querySelectorAll('.part').forEach(x=>x.classList.toggle('selected',x===row))};row.append(check,button);$('parts').append(row)}cadReady=true}}catch(error){toast(error.message);return}}
    renderer.cad=on;renderer.params.split=false;renderer.params.view=0;renderer.reset();$('experience-panel').hidden=on;$('engineering-panel').hidden=!on;$('experience').classList.toggle('active',!on);$('engineering').classList.toggle('active',on);$('experience').setAttribute('aria-pressed',!on);$('engineering').setAttribute('aria-pressed',on);$('scene-kicker').textContent=on?'ENGINEERING / 02':'EXPERIENCE / 01';$('scene-title').innerHTML=on?'Designed in layers.<br><em>Made to be explored.</em>':'A little mystery.<br><em>A new perspective.</em>';document.querySelector('.view-control').hidden=on;updatePlate();
  }
  $('experience').addEventListener('click',()=>engineering(false));$('engineering').addEventListener('click',()=>engineering(true));$('explode').addEventListener('input',()=>{renderer.explode=Number($('explode').value)/100;$('explode-output').textContent=$('explode').value+'%'});$('isolate').addEventListener('click',()=>{if(!selectedPart){toast('Select a component first.');return}renderer.hidden=new Set(renderer.meshes.filter(x=>x.name!==selectedPart).map(x=>x.name));document.querySelectorAll('.part input').forEach(x=>x.checked=x.getAttribute('aria-label')==='Show '+selectedPart)});$('show-all').addEventListener('click',()=>{renderer.hidden.clear();document.querySelectorAll('.part input').forEach(x=>x.checked=true)});
  const uiTimer=setInterval(()=>{updatePlate();if(state.eraseAt){const remaining=Math.ceil((state.eraseAt-Date.now())/1000);if(remaining<=0){speaker.stop();erase()}else $('erase-count').textContent=`ERASES IN ${remaining}s`}},100);
  window.addEventListener('blur',()=>{if(recordDown||state.recording)cancel()});document.addEventListener('visibilitychange',()=>{if(document.hidden&&(state.recording||state.voice))cancel()});window.addEventListener('pagehide',()=>{clearInterval(uiTimer);abort?.abort();api.cancel();recorder.stop(false);live.stop();speaker.close();api.forget();channel?.close();renderer.dispose()},{once:true});
  setActivity('idle');
}
