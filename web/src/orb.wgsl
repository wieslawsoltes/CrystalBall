struct Params { resolution:vec2f, time:f32, activity:f32, yaw:f32, pitch:f32, zoom:f32, glow:f32, art:f32, split:f32, view:f32, pad:f32 }
@group(0) @binding(0) var<uniform> u:Params;
struct Vertex { @builtin(position) position:vec4f }
@vertex fn vs(@builtin(vertex_index) index:u32)->Vertex {var p=array<vec2f,3>(vec2f(-1,-1),vec2f(3,-1),vec2f(-1,3));return Vertex(vec4f(p[index],0,1));}
fn hash(p:vec3f)->f32 {var q=fract(p*.1031);q+=dot(q,q.yzx+33.33);return fract((q.x+q.y)*q.z);}
fn noise(p:vec3f)->f32{let i=floor(p);let f=fract(p);let w=f*f*(3.-2.*f);return mix(mix(mix(hash(i),hash(i+vec3f(1,0,0)),w.x),mix(hash(i+vec3f(0,1,0)),hash(i+vec3f(1,1,0)),w.x),w.y),mix(mix(hash(i+vec3f(0,0,1)),hash(i+vec3f(1,0,1)),w.x),mix(hash(i+vec3f(0,1,1)),hash(i+vec3f(1,1,1)),w.x),w.y),w.z);}
fn fbm(p:vec3f)->f32 {var q=p;var s=0.;var a=.5;for(var i=0;i<4;i++){s+=a*noise(q);q=q*2.03+vec3f(3.1,1.7,2.8);a*=.5;}return s;}
fn box(p:vec3f,b:vec3f)->f32 {let q=abs(p)-b;return length(max(q,vec3f(0)))+min(max(q.x,max(q.y,q.z)),0.);}
fn cylinder(p:vec3f,r:f32,h:f32)->f32 {let q=vec2f(length(p.xz)-r,abs(p.y)-h);return min(max(q.x,q.y),0.)+length(max(q,vec2f(0)));}
fn torus(p:vec3f,r:f32,t:f32)->f32{return length(vec2f(length(p.xz)-r,p.y))-t;}
fn best(a:vec2f,b:vec2f)->vec2f{return select(b,a,a.x<b.x);}
fn base(p:vec3f)->vec2f {
 let taper=1.14-.13*clamp((p.y-.23)/.7,0.,1.);
 var d=vec2f(cylinder(p-vec3f(0,.61,0),taper,.38)-.018,1);
 d=best(d,vec2f(cylinder(p-vec3f(0,.12,0),1.23,.075)-.025,1));
 d=best(d,vec2f(torus(p-vec3f(0,.235,0),1.155,.039),2));
 d=best(d,vec2f(cylinder(p-vec3f(0,1.065,0),1.08,.045)-.025,1));
 d=best(d,vec2f(torus(p-vec3f(0,1.14,0),1.01,.035),2));
 d=best(d,vec2f(torus(p-vec3f(0,.072,0),1.228,.014),2));
 return d;
}
fn normal(p:vec3f)->vec3f{let e=.0008;return normalize(vec3f(base(p+vec3f(e,0,0)).x-base(p-vec3f(e,0,0)).x,base(p+vec3f(0,e,0)).x-base(p-vec3f(0,e,0)).x,base(p+vec3f(0,0,e)).x-base(p-vec3f(0,0,e)).x));}
fn env(d:vec3f)->vec3f{
 var col=mix(vec3f(.009,.008,.022),vec3f(.06,.045,.10),max(d.y,0.));
 col+=vec3f(.53,.60,.82)*pow(max(dot(d,normalize(vec3f(-1,2,1))),0.),55.);
 col+=vec3f(1.,.41,.14)*pow(max(dot(d,normalize(vec3f(2,.5,-1))),0.),160.);
 col+=vec3f(.12,.06,.28)*pow(max(dot(d,normalize(vec3f(-2,0,-1))),0.),25.);
 return col;
}
fn star(p:vec2f,r:f32)->f32{let a=atan2(p.x,p.y);let k=.48+.52*pow(max(cos(a*5.),0.),.6);return length(p)-r*k;}
fn decoration(p:vec3f)->f32 {
 let angle=atan2(p.x,p.z);let q=vec2f(angle*1.08,p.y-.60);
 let cres=max(length(q)-.205,-(length(q-vec2f(.087,.068))-.181));
 var d=cres;
 d=min(d,star(q-vec2f(.44,.10),.115));d=min(d,star(q-vec2f(-.44,-.05),.105));
 d=min(d,star(q-vec2f(.78,-.12),.066));d=min(d,star(q-vec2f(-.77,.15),.064));
 d=min(d,star(q-vec2f(.15,-.24),.04));d=min(d,star(q-vec2f(-.2,.25),.036));
 let a=atan2(q.y-.035,q.x+1.16);let sun=vec2f(q.x+1.16,q.y-.035);
 d=min(d,length(sun)-(.103+.044*pow(max(cos(a*12.),0.),8.)));
 if(abs(angle)>1.65){d=min(d,star(vec2f(fract((angle+3.14)*1.6)-.5,p.y-.62),.11));}
 return 1.-smoothstep(-.004,.006,d);
}
fn shade(p:vec3f,n:vec3f,rd:vec3f,material:f32)->vec3f{
 let light=normalize(vec3f(-3,5,4));let halfv=normalize(light-rd);
 let metal=max(select(0.,1.,material>1.5),decoration(p)*select(0.,1.,material<1.5));
 let rough=fbm(p*58.);
 let black=vec3f(.022,.02,.031)*(1.+rough*.15);let gold=vec3f(.64,.36,.105)*(0.66+.42*rough);
 var col=mix(black,gold,metal)*(.12+max(dot(n,light),0.)*.72);
 col+=mix(vec3f(.09),vec3f(.87,.55,.23),metal)*pow(max(dot(n,halfv),0.),mix(45.,95.,metal))*.7;
 col+=env(reflect(rd,n))*mix(.55,.65,metal);
 col+=vec3f(.18,.018,.45)*pow(max(n.y,0.),2.)*u.glow*.7;
 return col;
}
fn sphere(ro:vec3f,rd:vec3f)->vec2f{let o=ro-vec3f(0,1.8667,0);let b=dot(o,rd);let c=dot(o,o)-1.;let h=b*b-c;if(h<0.){return vec2f(-1);}return vec2f(-b-sqrt(h),-b+sqrt(h));}
@fragment fn fs(@builtin(position) frag:vec4f)->@location(0) vec4f {
 var xy=frag.xy;var res=u.resolution;var yaw=u.yaw;
 if(u.split>.5){res.x*=.5;if(xy.x>res.x){xy.x-=res.x;yaw+=3.14159265;}}
 else if(u.view>.5){yaw+=3.14159265;}
 let uv=(xy/res*2.-1.)*vec2f(res.x/res.y,-1.);
 let distance=6.7*u.zoom;let ro=vec3f(sin(yaw)*distance,2.6+u.pitch*distance,cos(yaw)*distance);
 let fw=normalize(vec3f(0,1.4,0)-ro);let rt=normalize(cross(fw,vec3f(0,1,0)));let up=cross(rt,fw);
 let rd=normalize(fw+(rt*uv.x+up*uv.y)*tan(.65*.5));
 let tFloor=-ro.y/rd.y;var col=env(rd)*.45;var distanceHit=40.;
 if(tFloor>0.){
   let p=ro+rd*tFloor;let radius=length(p.xz);let weave=.96+.04*sin(p.x*210.)*sin(p.z*160.);
   let shadow=1.-.85*exp(-radius*radius*.8);
   col=vec3f(.042,.014,.054)*weave*shadow+vec3f(.065,.007,.20)*exp(-radius*radius*.7)*u.glow;
   col+=vec3f(.03,.009,.05)*fbm(p*3.);distanceHit=tFloor;
 }
 var t=0.;var hit=vec2f(0);
 for(var i=0;i<100;i++){let p=ro+rd*t;hit=base(p);if(hit.x<.0009||t>min(distanceHit,22.)){break;}t+=max(hit.x*.85,.0005);}
 if(t<min(distanceHit,22.)){let p=ro+rd*t;col=shade(p,normal(p),rd,hit.y);distanceHit=t;}
 let ss=sphere(ro,rd);
 if(ss.x>0.&&ss.x<distanceHit){
   let p=ro+rd*ss.x;
   if(p.y>1.198){
     let n=normalize(p-vec3f(0,1.8667,0));let facing=max(dot(-rd,n),0.);let fres=.038+.962*pow(1.-facing,5.);
     let reflected=env(reflect(rd,n));let refracted=refract(rd,n,1./1.49);
     var glow=vec3f(0);var transmission=1.;let lengthIn=ss.y-ss.x;let dt=lengthIn/36.;
     if(u.art>.5){
       for(var i=0;i<36;i++){
         var q=ro+rd*(ss.x+(f32(i)+.5)*dt)-vec3f(0,1.8667,0);
         let radial=length(q);let angle=u.time*.09+q.y*.9;let c=cos(angle);let s=sin(angle);q=vec3f(q.x*c-q.z*s,q.y,q.x*s+q.z*c);
         let warp=vec3f(fbm(q*2.+u.time*.02),fbm(q*2.6-2.),fbm(q*3.+5.));
         let clouds=fbm(q*4.+warp*3.+vec3f(0,-u.time*.07,0));
         let density=smoothstep(.40,.71,clouds)*(1.-smoothstep(.75,.98,radial));
         let filaments=pow(max(0.,1.-abs(clouds-.53)*15.),5.)*.22;
         let energy=(density+filaments*(1.-smoothstep(.85,1.,radial)))*(0.5+u.glow)*(1.+u.activity*.18);
         glow+=transmission*energy*dt*mix(vec3f(.16,.011,.54),vec3f(.84,.32,1.6),pow(density,1.4));
         transmission*=exp(-density*dt*1.8);
       }
     }
     let edge=pow(1.-facing,2.3);let lower=pow(max(-n.y,0.),4.);
     col=col*transmission*.76+glow*1.7+reflected*(.22+fres*1.5);
     col+=vec3f(.14,.025,.50)*(edge*.6+lower*2.)*u.glow;
     col+=vec3f(.67,.66,.85)*pow(max(dot(reflect(rd,n),normalize(vec3f(-1.8,3,2))),0.),140.);
     col+=vec3f(.3,.22,.53)*pow(edge,3.);
   }
 }
 // Perimeter halo; this is the only luminous effect promised by the hardware.
 let th=(1.22-ro.y)/rd.y;
 if(th>0.){let p=ro+rd*th;let r=length(p.xz);let ring=exp(-pow((r-.77)*70.,2.));if(th<distanceHit+.03){col+=vec3f(.39,.065,1.1)*ring*u.glow;}}
 col=col/(vec3f(.8)+col);col=pow(max(col,vec3f(0)),vec3f(1./2.2));
 col*=1.-.18*pow(length(xy/res-.5),2.);
 return vec4f(col,1);
}
