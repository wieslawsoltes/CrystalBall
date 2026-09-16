/** Windowed-sinc anti-aliasing resampler; WAV format shared with ESP32 firmware. */
export function wav16k(input, rate){
  if(!(input instanceof Float32Array)||!Number.isFinite(rate)||rate<8000||rate>192000)throw new TypeError('Invalid PCM input');
  if(input.length/rate<.3||input.length/rate>8.01)throw new RangeError('Record between 0.3 and 8 seconds');
  const length=Math.min(128000,Math.floor(input.length*16000/rate)),out=new ArrayBuffer(44+length*2),v=new DataView(out);
  const tag=(s,p)=>{for(let i=0;i<s.length;i++)v.setUint8(p+i,s.charCodeAt(i))};
  tag('RIFF',0);v.setUint32(4,out.byteLength-8,true);tag('WAVEfmt ',8);v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,16000,true);v.setUint32(28,32000,true);v.setUint16(32,2,true);v.setUint16(34,16,true);tag('data',36);v.setUint32(40,length*2,true);
  const ratio=rate/16000,cutoff=.45*Math.min(1,1/ratio),half=24;
  for(let i=0;i<length;i++){
    const at=i*ratio,base=Math.floor(at);let sample=0,total=0;
    if(rate===16000)sample=input[i];
    else{for(let j=-half+1;j<=half;j++){const n=base+j;if(n<0||n>=input.length)continue;const x=n-at,t=2*Math.PI*cutoff*x,w=(Math.abs(t)<1e-8?2*cutoff:Math.sin(t)/(Math.PI*x))*(.5+.5*Math.cos(Math.PI*x/half));sample+=input[n]*w;total+=w}sample/=total||1}
    sample=Number.isFinite(sample)?Math.max(-1,Math.min(1,sample)):0;v.setInt16(44+i*2,Math.round(sample*(sample<0?32768:32767)),true);
  }
  return out;
}
export function pcmFloats(buffer){if(!(buffer instanceof ArrayBuffer)||!buffer.byteLength||buffer.byteLength%2||buffer.byteLength>2160000)throw new RangeError('Invalid 24 kHz mono PCM');const d=new DataView(buffer),f=new Float32Array(buffer.byteLength/2);for(let i=0;i<f.length;i++)f[i]=d.getInt16(i*2,true)/32768;return f}
