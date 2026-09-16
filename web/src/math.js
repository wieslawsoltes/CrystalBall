export const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
export const sub=(a,b)=>a.map((x,i)=>x-b[i]);
export const dot=(a,b)=>a.reduce((s,x,i)=>s+x*b[i],0);
export const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
export const normalize=a=>{const l=Math.hypot(...a)||1;return a.map(x=>x/l)};
export function multiply(a,b){const c=new Float32Array(16);for(let j=0;j<4;j++)for(let i=0;i<4;i++)for(let k=0;k<4;k++)c[j*4+i]+=a[k*4+i]*b[j*4+k];return c}
export function lookAt(eye,center){const z=normalize(sub(eye,center)),x=normalize(cross([0,1,0],z)),y=cross(z,x);return new Float32Array([x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,-dot(x,eye),-dot(y,eye),-dot(z,eye),1])}
export function perspective(fov,aspect,near=.05,far=100){const f=1/Math.tan(fov/2);return new Float32Array([f/aspect,0,0,0,0,f,0,0,0,0,far/(near-far),-1,0,0,far*near/(near-far),0])}
export function project(v,m,w,h){const p=[...v,1],r=Array.from({length:4},(_,i)=>p.reduce((s,x,j)=>s+x*m[j*4+i],0));return [(r[0]/r[3]*.5+.5)*w,(.5-r[1]/r[3]*.5)*h,r[3]]}
export function camera(yaw=0,pitch=0,zoom=1,aspect=1){const d=6.7*zoom,eye=[Math.sin(yaw)*d,2.6+pitch*d,Math.cos(yaw)*d];return{eye,matrix:multiply(perspective(.65,aspect),lookAt(eye,[0,1.4,0]))}}
/** Only this allowlist is serialized to a public client window. */
export function publicState(state){return {v:1,activity:['idle','recording','thinking','speaking','ready','error'].includes(state.activity)?state.activity:'idle',glow:clamp(Number(state.glow)||.6,.05,1),art:!!state.art}}
export function pages(text,columns=22,rows=10){const result=[];let line='',page=[];for(const word of String(text).trim().split(/\s+/)){let remaining=word;while(remaining.length>columns){if(line){page.push(line);line=''}page.push(remaining.slice(0,columns));remaining=remaining.slice(columns)}if(line.length+remaining.length+1>columns){page.push(line);line=remaining}else line+=(line?' ':'')+remaining}if(line)page.push(line);for(let i=0;i<page.length;i+=rows)result.push(page.slice(i,i+rows).join('\n'));return result.length?result:['']}
