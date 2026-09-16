#!/usr/bin/env node
var kr=Object.defineProperty;var d=(n,t)=>kr(n,"name",{value:t,configurable:!0});var gn=(n,t)=>()=>(n&&(t=n(n=0)),t);var wc=(n,t)=>{for(var e in t)kr(n,e,{get:t[e],enumerable:!0})};function Nn(n,t,e){let i=n*n,s=i*i,r=Kh+i*(jh+i*Qh)+i*s*(tf+i*ef),o=i*n;return e?n-(i*(.5*t-o*r)-t-o*To):n+o*(To+i*r)}function Ln(n,t){let e=n*n,i=e*e,s=e*(nf+e*(sf+e*rf))+i*i*(of+e*(af+e*cf)),r=.5*e,o=1-r;return o+(1-o-r+(e*s-n*t))}function Io(n){let t=Math.trunc(n*lf+(n>0?.5:-.5)),e=t,i=n-e*uf,s=e*hf,r=i;s=e*ff,i=r-s,s=e*df-(r-i-s),r=i,s=e*pf,i=r-s,s=e*mf-(r-i-s);let o=i-s;return Ci.n=t,Ci.r=o,Ci.tail=i-o-s,Ci}function Po(n){throw new RangeError(`deterministic sin/cos is defined for |x| < ${qs} radians, got ${n}`)}function ht(n){let t=Math.abs(n);if(!Number.isFinite(n))return NaN;if(t<=tn)return t<Ro?n:Nn(n,0,!1);t<qs||Po(n);let{n:e,r:i,tail:s}=Io(n);switch(e&3){case 0:return Nn(i,s,!0);case 1:return Ln(i,s);case 2:return-Nn(i,s,!0);default:return-Ln(i,s)}}function rt(n){let t=Math.abs(n);if(!Number.isFinite(n))return NaN;if(t<=tn)return t<Ro?1:Ln(n,0);t<qs||Po(n);let{n:e,r:i,tail:s}=Io(n);switch(e&3){case 0:return Ln(i,s);case 1:return-Nn(i,s,!0);case 2:return-Ln(i,s);default:return Nn(i,s,!0)}}function Xs(n){return Dn.setFloat64(0,n),Dn.getInt32(0)}function Qe(n){return Xs(n)>>>31===1}function gf(n){return Dn.setFloat64(0,n),Dn.setUint32(4,0),Dn.getFloat64(0)}function Ws(n){let t=n*(xf+n*(_f+n*(yf+n*(vf+n*(Mf+n*bf))))),e=1+n*(Sf+n*(Af+n*(Tf+n*wf)));return t/e}function No(n){let t=Math.abs(n);if(!(t<=1))return NaN;if(t===1)return n>0?0:xe+2*Ri;if(t<.5)return t<6938893903907228e-33?Ce+Ri:Ce-(n-(Ri-n*Ws(n*n)));if(n<0){let o=(1+n)*.5,a=Math.sqrt(o);return xe-2*(a+(Ws(o)*a-Ri))}let e=(1-n)*.5,i=Math.sqrt(e),s=gf(i),r=(e-s*s)/(i+s);return 2*(s+(Ws(e)*i+r))}function Co(n){if(Number.isNaN(n))return NaN;let t=Qe(n),e=Math.abs(n),i;if(e>=7378697629483821e4){let l=wo[3]+Eo[3];return t?-l:l}if(e<.4375){if(e<1862645149230957e-24)return n;i=-1,e=n}else e<.6875?(i=0,e=(2*e-1)/(2+e)):e<1.1875?(i=1,e=(e-1)/(e+1)):e<2.4375?(i=2,e=(e-1.5)/(1+1.5*e)):(i=3,e=-1/e);let s=e*e,r=s*s,o=s*(Zt[0]+r*(Zt[2]+r*(Zt[4]+r*(Zt[6]+r*(Zt[8]+r*Zt[10]))))),a=r*(Zt[1]+r*(Zt[3]+r*(Zt[5]+r*(Zt[7]+r*Zt[9]))));if(i<0)return e-e*(o+a);let c=wo[i]-(e*(o+a)-Eo[i]-e);return t?-c:c}function $s(n,t){if(Number.isNaN(t)||Number.isNaN(n))return NaN;if(t===1)return Co(n);let e=(Qe(n)?1:0)|(Qe(t)?2:0);if(n===0)return e<2?n:e===2?xe:-xe;if(t===0)return Qe(n)?-Ce:Ce;if(!Number.isFinite(t))return Number.isFinite(n)?[0,-0,xe,-xe][e]:[tn,-tn,3*tn,-3*tn][e];if(!Number.isFinite(n))return Qe(n)?-Ce:Ce;let i=(Xs(n)&2147483647)-(Xs(t)&2147483647)>>20,s;switch(i>60?s=Ce+.5*Hs:Qe(t)&&i<-60?s=0:s=Co(Math.abs(n/t)),e){case 0:return s;case 1:return-s;case 2:return xe-(s-Hs);default:return s-Hs-xe}}var To,Kh,jh,Qh,tf,ef,nf,sf,rf,of,af,cf,tn,lf,uf,hf,ff,df,pf,mf,Ro,qs,Ci,Dn,xe,Hs,Ce,Ri,xf,_f,yf,vf,Mf,bf,Sf,Af,Tf,wf,wo,Eo,Zt,Un=gn(()=>{To=-.16666666666666632,Kh=.00833333333332249,jh=-.0001984126982985795,Qh=27557313707070068e-22,tf=-25050760253406863e-24,ef=158969099521155e-24,nf=.0416666666666666,sf=-.001388888888887411,rf=2480158728947673e-20,of=-27557314351390663e-23,af=2087572321298175e-24,cf=-11359647557788195e-27,tn=.7853981633974483,lf=.6366197723675814,uf=1.5707963267341256,hf=6077100506506192e-26,ff=6077100506303966e-26,df=20222662487959506e-37,pf=20222662487111665e-37,mf=84784276603689e-45,Ro=3725290298461914e-24,qs=524288;d(Nn,"kernelSin");d(Ln,"kernelCos");Ci={n:0,r:0,tail:0};d(Io,"reducePio2");d(Po,"outOfRange");d(ht,"sin");d(rt,"cos");Dn=new DataView(new ArrayBuffer(8));d(Xs,"highWord");d(Qe,"signBit");d(gf,"dropLowWord");xe=3.141592653589793,Hs=12246467991473532e-32,Ce=1.5707963267948966,Ri=6123233995736766e-32,xf=.16666666666666666,_f=-.3255658186224009,yf=.20121253213486293,vf=-.04005553450067941,Mf=.0007915349942898145,bf=3479331075960212e-20,Sf=-2.403394911734414,Af=2.0209457602335057,Tf=-.6882839716054533,wf=.07703815055590194;d(Ws,"acosR");d(No,"acos");wo=[.4636476090008061,.7853981633974483,.982793723247329,1.5707963267948966],Eo=[22698777452961687e-33,3061616997868383e-32,13903311031230998e-33,6123233995736766e-32],Zt=[.3333333333333293,-.19999999999876483,.14285714272503466,-.11111110405462356,.09090887133436507,-.0769187620504483,.06661073137387531,-.058335701337905735,.049768779946159324,-.036531572744216916,.016285820115365782];d(Co,"atan");d($s,"atan2")});function zi(n,t,e){if(!n)return null;let i=n.userData.cadTubeShader;if(!i){let r=n.onBeforeCompile,o=n.customProgramCacheKey;i=n.userData.cadTubeShader={stages:{}},n.onBeforeCompile=function(a,c){r.call(this,a,c);for(let u of Ea){let h=i.stages[u];h&&(Object.assign(a.uniforms,h.uniforms),h.apply(a,i.stages))}let l=`#include <common>
varying vec3 ${ve};`;a.vertexShader=a.vertexShader.replace("#include <common>",l),a.fragmentShader=a.fragmentShader.replace("#include <common>",l)},n.customProgramCacheKey=function(){let a=Ea.filter(c=>i.stages[c]).join("+");return`${o.call(this)}:cad-tube:${a}`},n.needsUpdate=!0}let s=i.stages[t];return s||(s=i.stages[t]=e(),n.needsUpdate=!0),s}var ve,Hn,Bi,Ea,ki=gn(()=>{ve="vCadTubeMaterial",Hn="cadTubeMaterial",Bi="braid",Ea=["gpu",Bi];d(zi,"ensureTubeMaterialStage")});function Pd(n,t){t["gpu"]||(n.vertexShader=n.vertexShader.replace("#include <common>",`#include <common>
attribute vec3 ${Hn};`).replace("#include <begin_vertex>",`#include <begin_vertex>
${ve} = ${Hn};`)),n.fragmentShader=n.fragmentShader.replace("#include <common>",`#include <common>
${Id}`).replace("#include <color_fragment>",`#include <color_fragment>
float cadBraidRelief = cadBraidHeight();
diffuseColor.rgb *= 1.0 + 0.22 * cadBraidRelief / max(cadBraidParameters.y, 0.000001);`).replace("#include <normal_fragment_maps>",`#include <normal_fragment_maps>
if (cadBraidEnabled > 0.5) normal = cadBraidNormal(-vViewPosition, normal, cadBraidRelief);`)}function Ca(n,t,e){if(!t||!e&&!t.userData.cadTubeShader?.stages[Bi])return;let i=zi(t,Bi,()=>({uniforms:{cadBraidParameters:{value:new n.Vector3(1,0,8)},cadBraidEnabled:{value:0}},apply:Pd}));i.uniforms.cadBraidEnabled.value=e?1:0,e&&i.uniforms.cadBraidParameters.value.set(e.pitch,e.depth,e.strands)}var Id,Ra=gn(()=>{ki();Id=`
uniform vec3 cadBraidParameters;
uniform float cadBraidEnabled;
float cadBraidHeight() {
  float angle = atan(${ve}.z, ${ve}.y);
  float turns = ${ve}.x / cadBraidParameters.x;
  float carrierA = cadBraidParameters.z * (angle / 6.28318530718 + turns);
  float carrierB = cadBraidParameters.z * (angle / 6.28318530718 - turns);
  float a = fract(carrierA), b = fract(carrierB);
  float bandA = sqrt(max(0.0, 1.0 - pow((a - 0.5) / 0.44, 2.0)));
  float bandB = sqrt(max(0.0, 1.0 - pow((b - 0.5) / 0.44, 2.0)));
  float over = mod(floor(carrierA) + floor(carrierB), 2.0);
  float crown = mix(max(bandA, bandB * 0.60), max(bandB, bandA * 0.60), over);
  float fineFibers = 0.035 * cos(6.28318530718 * 5.0 * mix(carrierA, carrierB, over));
  return cadBraidEnabled * cadBraidParameters.y * (crown + fineFibers - 1.035);
}
vec3 cadBraidNormal(vec3 surfacePosition, vec3 surfaceNormal, float height) {
  vec3 dx = dFdx(surfacePosition), dy = dFdy(surfacePosition);
  vec3 r1 = cross(dy, surfaceNormal), r2 = cross(surfaceNormal, dx);
  float determinant = dot(dx, r1);
  vec3 gradient = sign(determinant) * (dFdx(height) * r1 + dFdy(height) * r2);
  return normalize(abs(determinant) * surfaceNormal - gradient);
}
`;d(Pd,"applyBraidStage");d(Ca,"applyTubeBraidMaterial")});function Ud(n,t){let e=[];for(let o of n.segments){let a=o.kind==="bezier"?o.table:null,c=a?.length??(o.kind==="line"?2:Math.ceil(o.length/o.radius/Ld)+1);for(let l=0;l<c;l++){let u=a?.[l],h=u?u.s:o.length*l/(c-1),f=o.offset+h,p=u?.curvature?u:t(n,f),m={s:f,point:p.point,tangent:p.tangent,normal:p.normal,curvature:p.curvature};e.length&&f<=e.at(-1).s+1e-12?e[e.length-1]=m:e.push(m)}}let i=Math.max(2,Math.ceil(n.length/Nd)+1),s=new Float32Array(i*16),r=0;for(let o=0;o<i;o++){let a=n.length*o/(i-1);for(;r<e.length-2&&e[r+1].s<a;)r++;let c=e[r],l=e[r+1],u=l.s-c.s,h=Math.max(0,Math.min(1,(a-c.s)/u)),f=1-h,p=2*h*h*h-3*h*h+1,m=h*h*h-2*h*h+h,g=-2*h*h*h+3*h*h,x=h*h*h-h*h,_=f*c.tangent[0]+h*l.tangent[0],v=f*c.tangent[1]+h*l.tangent[1],y=f*c.tangent[2]+h*l.tangent[2],b=Math.sqrt(_*_+v*v+y*y);_/=b,v/=b,y/=b;let T=f*c.normal[0]+h*l.normal[0],S=f*c.normal[1]+h*l.normal[1],M=f*c.normal[2]+h*l.normal[2],A=T*_+S*v+M*y;T-=A*_,S-=A*v,M-=A*y;let I=Math.sqrt(T*T+S*S+M*M);T/=I,S/=I,M/=I;let C=o*16;for(let N=0;N<3;N++)s[C+N]=p*c.point[N]+m*u*c.tangent[N]+g*l.point[N]+x*u*l.tangent[N],s[C+12+N]=f*c.curvature[N]+h*l.curvature[N];s.set([_,v,y],C+4),s.set([T,S,M],C+8)}return{data:s,count:i}}function Od(n){n.vertexShader=n.vertexShader.replace("#include <common>",`#include <common>
${Fd}`).replace("#include <beginnormal_vertex>",`#include <beginnormal_vertex>
cadEvaluateTube();
if (cadTubeGpuEnabled > 0.5) objectNormal = cadGpuNormal;`).replace("#include <begin_vertex>",`#include <begin_vertex>
cadEvaluateTube();
if (cadTubeGpuEnabled > 0.5) transformed = cadGpuPoint;
${ve} = cadTubeMaterialCoordinates();`)}function yr(n,t){if(!n)return;let e=zi(n,"gpu",()=>({uniforms:t,apply:Od}));if(e.uniforms!==t)for(let[i,s]of Object.entries(t))e.uniforms[i]?e.uniforms[i].value=s.value:(e.uniforms[i]=s,n.needsUpdate=!0)}function Mr(n){let t=n?.tubeGpuState;t&&(t.uniforms.cadTubeGpuEnabled.value=0,t.active=!1,n.mesh.userData.cadBeforeRaycast=null)}function br(n){let t=n?.tubeGpuState;if(t?.active)for(let e of[n.mesh,n.silhouette,n.ghostMesh])e&&yr(e.material,t.uniforms)}function Bd(n,t,e,i,s){let r=e.mapping,o=Dd,a=Math.ceil(r.values.length/4/o),c=r.values;r.gpu||(c=new Float32Array(o*a*4),c.set(r.values));let l=new n.DataTexture(c,o,a,n.RGBAFormat,n.FloatType);l.needsUpdate=!0;let u=r.gpu?r.indices:new Float32Array(r.indices);e.geometry.setAttribute("cadTubeMappingIndex",new n.BufferAttribute(u,1));let h=0;for(let f=0;f<r.values.length;f+=8){let p=r.values[f+1],m=r.values[f+2],g=r.values[f+3];h=Math.max(h,Math.sqrt(p*p+m*m+g*g))}return{mapping:r,mappingTexture:l,radius:h,active:!0,uniforms:{cadTubeMappingTexture:{value:l},cadTubeFrameTexture:{value:null},cadTubeMappingSize:{value:new n.Vector2(o,a)},cadTubeFrameCount:{value:0},cadTubeRestLength:{value:i.rest.length},cadTubeGpuEnabled:{value:1},cadTubeGpuParameters:{value:new n.Vector3},cadTubeGpuInverse:{value:s.clone()},cadTubeGpuNormalMatrix:{value:new n.Matrix3().getNormalMatrix(s)}}}}function zd(n,t,e,i,s,r,o){let a=i.frames;t.mesh.userData.cadBeforeRaycast=c=>{if(!i.active)return!0;let l=c.ray.clone().applyMatrix4(t.mesh.matrixWorld.clone().invert());if(!l.intersectsBox(e.geometry.boundingBox))return!1;let u=l.clone().applyMatrix4(r.clone().invert()),h=new n.Vector3,f=new n.Vector3,p=Math.max(1,Math.floor((a.count-1)/s.path.length)),m=!1;for(let g=0;g<a.count-1;g+=p){let x=Math.min(g+p,a.count-1);h.fromArray(a.data,g*16),f.fromArray(a.data,x*16);let _=i.radius+(x-g)*s.path.length/(a.count-1)/2+1e-4;if(u.distanceSqToSegment(h,f)<=_*_){m=!0;break}}return m?(i.cpuSpec!==s.pathSpec&&(o(),i.cpuSpec=s.pathSpec),!0):!1}}function Ia(n,t,e,i,s,r,o){if(!t.gpuTubeDeformationAllowed||i.path.length>vr)return!1;let a=t.tubeGpuState;(!a||a.mapping!==e.mapping)&&(a?.mappingTexture.dispose(),a?.frameTexture?.dispose(),a=t.tubeGpuState=Bd(n,t,e,i,s)),a.cleanupInstalled||(e.geometry.addEventListener("dispose",()=>{a.mappingTexture.dispose(),a.frameTexture?.dispose()}),a.cleanupInstalled=!0);let c=Ud(i.path,r);!a.frameTexture||a.frameTexture.image.height!==c.count?(a.frameTexture?.dispose(),a.frameTexture=new n.DataTexture(c.data,4,c.count,n.RGBAFormat,n.FloatType)):a.frameTexture.image.data.set(c.data),a.frameTexture.needsUpdate=!0,a.frames=c,a.active=!0,a.cpuSpec=null;let l=a.uniforms;l.cadTubeFrameTexture.value=a.frameTexture,l.cadTubeFrameCount.value=c.count,l.cadTubeGpuEnabled.value=1,l.cadTubeGpuParameters.value.set(i.twistDeg*Math.PI/180,i.path.length/i.rest.length,0),l.cadTubeGpuInverse.value.copy(s),l.cadTubeGpuNormalMatrix.value.getNormalMatrix(s),br(t),t.mesh.customDepthMaterial||(t.mesh.customDepthMaterial=new n.MeshDepthMaterial({depthPacking:n.RGBADepthPacking}),t.mesh.customDistanceMaterial=new n.MeshDistanceMaterial,t.mesh.material.addEventListener("dispose",()=>{t.mesh.customDepthMaterial?.dispose(),t.mesh.customDistanceMaterial?.dispose()})),yr(t.mesh.customDepthMaterial,l),yr(t.mesh.customDistanceMaterial,l);let u=new n.Box3;for(let h of i.path.segments)u.expandByPoint(new n.Vector3().fromArray(h.bounds.min)),u.expandByPoint(new n.Vector3().fromArray(h.bounds.max));return u.expandByScalar(a.radius+1e-4),t.partBounds={min:u.min.toArray(),max:u.max.toArray()},e.geometry.boundingBox=u.clone().applyMatrix4(s),e.geometry.boundingSphere=e.geometry.boundingBox.getBoundingSphere(new n.Sphere),zd(n,t,e,a,i,s,o),!0}var vr,Nd,Ld,Dd,Fd,Pa=gn(()=>{ki();vr=819.1,Nd=.1,Ld=.01,Dd=1024;d(Ud,"buildGpuTubeFrames");Fd=`
attribute float cadTubeMappingIndex;
uniform sampler2D cadTubeMappingTexture;
uniform sampler2D cadTubeFrameTexture;
uniform vec2 cadTubeMappingSize;
uniform float cadTubeFrameCount;
uniform float cadTubeRestLength;
uniform float cadTubeGpuEnabled;
uniform vec3 cadTubeGpuParameters;
uniform mat4 cadTubeGpuInverse;
uniform mat3 cadTubeGpuNormalMatrix;
vec3 cadGpuPoint;
vec3 cadGpuNormal;
bool cadGpuEvaluated = false;
vec4 cadMapping(float index) {
  vec2 texel = vec2(mod(index, cadTubeMappingSize.x), floor(index / cadTubeMappingSize.x));
  return texture2D(cadTubeMappingTexture, (texel + 0.5) / cadTubeMappingSize);
}
vec3 cadFrame(float row, float column) {
  return texture2D(cadTubeFrameTexture, vec2((column + 0.5) / 4.0, (row + 0.5) / cadTubeFrameCount)).xyz;
}
vec3 cadTubeMaterialCoordinates() {
  vec4 a = cadMapping(2.0 * cadTubeMappingIndex);
  return vec3(a.x * cadTubeRestLength, a.yz);
}
void cadEvaluateTube() {
  if (cadGpuEvaluated || cadTubeGpuEnabled < 0.5) return;
  cadGpuEvaluated = true;
  vec4 a = cadMapping(2.0 * cadTubeMappingIndex);
  vec4 b = cadMapping(2.0 * cadTubeMappingIndex + 1.0);
  float f = clamp(a.x, 0.0, 1.0) * (cadTubeFrameCount - 1.0);
  float lo = floor(f);
  float hi = min(lo + 1.0, cadTubeFrameCount - 1.0);
  float u = f - lo;
  vec3 p = mix(cadFrame(lo, 0.0), cadFrame(hi, 0.0), u);
  vec3 t = normalize(mix(cadFrame(lo, 1.0), cadFrame(hi, 1.0), u));
  vec3 n = mix(cadFrame(lo, 2.0), cadFrame(hi, 2.0), u);
  n = normalize(n - t * dot(n, t));
  vec3 v = cross(t, n);
  vec3 curvature = mix(cadFrame(lo, 3.0), cadFrame(hi, 3.0), u);
  float c = cos(cadTubeGpuParameters.x);
  float s = sin(cadTubeGpuParameters.x);
  vec2 transverse = mat2(c, s, -s, c) * a.yz;
  vec3 offset = n * transverse.x + v * transverse.y;
  float metric = 1.0 - dot(curvature, offset);
  vec2 normalPair = mat2(c, s, -s, c) * b.xy;
  vec3 normalValue = n * normalPair.x + v * normalPair.y + t * b.z * b.w / (metric * cadTubeGpuParameters.y);
  cadGpuPoint = (cadTubeGpuInverse * vec4(p + offset + a.w * t, 1.0)).xyz;
  cadGpuNormal = normalize(cadTubeGpuNormalMatrix * normalValue);
}
`;d(Od,"applyGpuStage");d(yr,"patchMaterial");d(Mr,"disableGpuTube");d(br,"syncGpuTubeMaterials");d(Bd,"createGpuState");d(zd,"installRaycastGuard");d(Ia,"applyGpuTube")});var Ya={};wc(Ya,{applyRecordTubeDeformation:()=>ip,applyTubeDeformationToLineObject:()=>Cr,compileDeformation:()=>jt,compileTubePath:()=>Xa,normalizeTubeDeformation:()=>Kd,poseTubeBake:()=>Yn,prepareTubeBake:()=>Rr,projectTubePath:()=>qn,restMappingKey:()=>$n,sameTubeDeformation:()=>Fe,sameTubeRestShape:()=>wr,sampleTubePath:()=>un});function Vd(n,t){let e=0;for(let i=0;i<3;i++)e+=Math.max(n.min[i]-t[i],0,t[i]-n.max[i])**2;return e}function ft(n){throw new Error(`animation deformTube: ${n}`)}function De(n,t){return(!Array.isArray(n)||n.length!==3||!n.every(Number.isFinite))&&ft(`${t} must be a finite vec3`),n.slice()}function on(n,t){let e=Wt(n);return e<Ue&&ft(`${t} must be nonzero`),Tt(n,1/e)}function Vi(n,t,e){(!n||typeof n!="object"||Array.isArray(n))&&ft(`${e} must be an object`);for(let i of Object.keys(n))t.includes(i)||ft(`unknown ${e} key ${JSON.stringify(i)}; expected ${t.join(", ")}`)}function Gi(n,t,e){let i=rt(e),s=ht(e);return cn(cn(Tt(n,i),Tt(Me(t,n),s)),Tt(t,dt(t,n)*(1-i)))}function Xn(n,t){let e=1-t;return[0,1,2].map(i=>e*e*e*n[0][i]+3*e*e*t*n[1][i]+3*e*t*t*n[2][i]+t*t*t*n[3][i])}function ln(n,t){let e=1-t;return[0,1,2].map(i=>3*e*e*(n[1][i]-n[0][i])+6*e*t*(n[2][i]-n[1][i])+3*t*t*(n[3][i]-n[2][i]))}function za(n,t){return[0,1,2].map(e=>6*(1-t)*(n[2][e]-2*n[1][e]+n[0][e])+6*t*(n[3][e]-2*n[2][e]+n[1][e]))}function Wn(n,t,e){let i=(t+e)/2,s=(e-t)/2,r=0;for(let o=0;o<5;o++){let a=i+s*Gd[o],c=1-a,l=3*c*c,u=6*c*a,h=3*a*a,f=l*(n[1][0]-n[0][0])+u*(n[2][0]-n[1][0])+h*(n[3][0]-n[2][0]),p=l*(n[1][1]-n[0][1])+u*(n[2][1]-n[1][1])+h*(n[3][1]-n[2][1]),m=l*(n[1][2]-n[0][2])+u*(n[2][2]-n[1][2])+h*(n[3][2]-n[2][2]);r+=Hd[o]*Math.sqrt(f*f+p*p+m*m)}return s*r}function ka(n,t,e){let i=Me(t,e),s=Wt(i),r=dt(t,e);return s<Ue?(r<0&&ft("path tangent reverses"),n.slice()):Gi(n,Tt(i,1/s),$s(s,r))}function Wd(n){let t=[{t:0,s:0,tangent:n.tangent,normal:n.normal}],e=d((i,s,r=0)=>{let o=(i+s)/2,a=Wn(n.points,i,s),c=Wn(n.points,i,o),l=Wn(n.points,o,s),u=on(ln(n.points,i),"Bezier tangent"),h=on(ln(n.points,s),"Bezier tangent");if(r<20&&(s-i>1/128||Math.abs(a-c-l)>1e-9||dt(u,h)<.9999)){e(i,o,r+1),e(o,s,r+1);return}dt(u,h)<.99&&ft("Bezier has a cusp or unresolved tangent");let f=t.at(-1);t.push({t:s,s:f.s+c+l,tangent:h,normal:ka(f.normal,f.tangent,h)})},"append");e(0,1),n.table=t,n.length=t.at(-1).s}function Va(n,t){let e=n.table,i=0,s=e.length-1;for(;s-i>1;){let c=i+s>>1;e[c].s<t?i=c:s=c}let r=e[i],o=e[s],a=r.t+(o.t-r.t)*(t-r.s)/(o.s-r.s);for(let c=0;c<3;c++){let l=r.s+Wn(n.points,r.t,a)-t;if(Math.abs(l)<1e-11)break;a=Math.max(r.t,Math.min(o.t,a-l/Wt(ln(n.points,a))))}return{t:a,lower:r}}function Ga(n,t){return n.kind==="line"?cn(n.start,Tt(n.tangent,t)):n.kind==="bezier"?Xn(n.points,Va(n,t).t):cn(n.center,Gi(n.radial,n.axis,t/n.radius*n.sign))}function Tr(n,t){if(n.kind==="bezier"){let{t:a,lower:c}=Va(n,t),l=ln(n.points,a),u=Wt(l),h=Tt(l,1/u),f=ka(c.normal,c.tangent,h),p=za(n.points,a),m=Tt(Bt(p,Tt(h,dt(p,h))),1/(u*u));return{point:Xn(n.points,a),tangent:h,normal:f,binormal:Me(h,f),curvature:m}}let e=n.kind==="arc"?t/n.radius*n.sign:0,i=e?Gi(n.tangent,n.axis,e):n.tangent,s=e?Gi(n.normal,n.axis,e):n.normal,r=Ga(n,t),o=n.kind==="arc"?Tt(Bt(n.center,r),1/(n.radius*n.radius)):[0,0,0];return{point:r,tangent:i,normal:s,binormal:Me(i,s),curvature:o}}function Ha(n){return Vi(n,["segments","normal"],"path"),(!Array.isArray(n.segments)||!n.segments.length)&&ft("path needs at least one segment"),n.normal===void 0&&ft("path normal is required: give both the rest and the posed path an explicit transverse normal seed"),De(n.normal,"normal")}function Wa(n,t){return Vi(n,Da[n.kind]||Da.arc,`segment ${t}`),n.kind==="line"?{kind:"line",start:De(n.start,"start"),end:De(n.end,"end")}:n.kind==="arc"?{kind:"arc",center:De(n.center,"center"),axis:De(n.axis,"axis"),start:De(n.start,"start"),sweepDeg:n.sweepDeg}:n.kind==="bezier"?((!Array.isArray(n.points)||n.points.length!==4)&&ft("Bezier points must contain four vec3 control points"),{kind:"bezier",points:n.points.map(e=>De(e,"Bezier point"))}):ft(`unknown segment kind ${JSON.stringify(n.kind)}; expected line, arc, bezier`)}function Xd(n,t){let e=Wa(n,t);if(e.kind==="line"){let{start:s,end:r}=e,o=Bt(r,s);return{kind:"line",start:s,end:r,tangent:on(o,"line"),length:Wt(o),radius:1/0}}if(e.kind==="arc"){let{center:s,start:r}=e,o=on(e.axis,"axis"),a=Bt(r,s),c=Wt(a),l=e.sweepDeg*Math.PI/180;(!Number.isFinite(l)||Math.abs(l)<Ue||Math.abs(l)>2*Math.PI+Ue)&&ft("arc sweepDeg must be nonzero and at most 360 degrees"),(c<Ue||Math.abs(dt(a,o))>Ue*Math.max(1,c))&&ft("arc start must be in its normal plane with nonzero radius");let u=Math.sign(l),h=Tt(Me(o,a),u/c),f={kind:"arc",center:s,start:r,axis:o,radial:a,radius:c,sign:u,tangent:h,length:c*Math.abs(l)};return f.end=Ga(f,f.length),f}let i=e.points;return{kind:"bezier",points:i,start:i[0],end:i[3],tangent:on(ln(i,0),"Bezier tangent"),radius:1/0}}function qd(n){return Math.min(...n.table.map(t=>{let e=ln(n.points,t.t),i=za(n.points,t.t),s=Wt(e);return s*s*s/Wt(Me(e,i))}))}function $d(n){if(n.kind==="arc")return{min:n.center.map(e=>e-n.radius),max:n.center.map(e=>e+n.radius)};let t=n.kind==="bezier"?n.points:[n.start,n.end];return{min:[0,1,2].map(e=>Math.min(...t.map(i=>i[e]))),max:[0,1,2].map(e=>Math.max(...t.map(i=>i[e])))}}function Xa(n){let t=Ha(n),e=0,i=null,s=n.segments.map((o,a)=>{let c=Xd(o,a);if(i){Wt(Bt(i.end,c.start))>1e-5&&ft(`path discontinuity before segment ${a}`);let l=Tr(i,i.length);dt(l.tangent,c.tangent)<1-1e-7&&ft(`path is not tangent-continuous before segment ${a}`),c.normal=l.normal}else c.normal=on(Bt(t,Tt(c.tangent,dt(t,c.tangent))),"path normal transverse to first tangent");return c.kind==="bezier"&&Wd(c),c.offset=e,c.bounds=$d(c),e+=c.length,i=c,c}),r={segments:s,length:e};return Object.defineProperty(r,"minRadius",{get(){for(let o of s)o.kind==="bezier"&&o.radius===1/0&&(o.radius=qd(o));return Math.min(...s.map(o=>o.radius))}}),r}function un(n,t){Number.isFinite(t)||ft("path distance must be finite");let e=t<=0?n.segments[0]:n.segments.find(o=>t<=o.offset+o.length)||n.segments.at(-1),i=t-e.offset,s=Math.max(0,Math.min(e.length,i)),r=Tr(e,s);return i!==s&&(r.point=cn(r.point,Tt(r.tangent,i-s))),r}function Yd(n){if(!n.tablePoints){let t=new Float64Array(n.table.length*3);n.table.forEach((e,i)=>{let s=Xn(n.points,e.t);t[i*3]=s[0],t[i*3+1]=s[1],t[i*3+2]=s[2]}),n.tablePoints=t}return n.tablePoints}function Zd(n,t){let e=Yd(n),i=0,s=1/0;for(let l=0;l<n.table.length;l++){let u=(t[0]-e[l*3])**2+(t[1]-e[l*3+1])**2+(t[2]-e[l*3+2])**2;u<s&&(s=u,i=l)}let r=n.table[Math.max(0,i-1)].t,o=n.table[Math.min(n.table.length-1,i+1)].t;for(let l=0;l<35;l++){let u=r+(o-r)/3,h=o-(o-r)/3;La(t,Xn(n.points,u))<La(t,Xn(n.points,h))?o=h:r=u}let a=(r+o)/2,c=n.table.findLast(l=>l.t<=a)||n.table[0];return c.s+Wn(n.points,c.t,a)}function Jd(n,t){let e=Bt(t,n.center),i=$s(dt(Me(n.radial,e),n.axis),dt(n.radial,e))*n.sign;i<0&&(i+=2*Math.PI);let s=i*n.radius;return s>n.length?Wt(Bt(t,n.start))<Wt(Bt(t,n.end))?0:n.length:s}function qn(n,t){let e=null,i=n.segments.map(s=>({segment:s,bound:Vd(s.bounds,t)})).sort((s,r)=>s.bound-r.bound);for(let{segment:s,bound:r}of i){if(e&&r>e.distanceSq+1e-12)break;let o;s.kind==="line"?o=dt(Bt(t,s.start),s.tangent):s.kind==="bezier"?o=Zd(s,t):o=Jd(s,t),o=Math.max(0,Math.min(s.length,o));let a=Tr(s,o),c=Bt(t,a.point),l=dt(c,c);(!e||l<e.distanceSq)&&(e={distance:s.offset+o,distanceSq:l,transverse:[dt(c,a.normal),dt(c,a.binormal)],axial:dt(c,a.tangent)})}return e}function Ua(n){let t=JSON.stringify(n),e=rn.get(t);return e?rn.delete(t):e=Xa(n),rn.set(t,e),rn.size>kd&&rn.delete(rn.keys().next().value),e}function Fa(n){return{normal:Ha(n),segments:n.segments.map((t,e)=>Wa(t,e))}}function an(n,t){if(n===t)return!0;if(Array.isArray(n))return!Array.isArray(t)||n.length!==t.length?!1:n.every((e,i)=>an(e,t[i]));if(n&&typeof n=="object"){if(!t||typeof t!="object"||Array.isArray(t))return!1;let e=Object.keys(n);return e.length===Object.keys(t).length&&e.every(i=>an(n[i],t[i]))}return!1}function Fe(n,t){return n===t?!0:!n||!t?!1:n.twistDeg===t.twistDeg&&n.maxSegmentLength===t.maxSegmentLength&&an(n.braid,t.braid)&&an(n.restSpec,t.restSpec)&&an(n.pathSpec,t.pathSpec)}function wr(n,t){return n.maxSegmentLength===t.maxSegmentLength&&an(n.restSpec,t.restSpec)}function jt(n){return{...n,rest:Ua(n.restSpec),path:Ua(n.pathSpec)}}function Kd(n){Vi(n,["rest","path","twistDeg","maxSegmentLength","braid"],"deformation");let t=n.twistDeg??0;Number.isFinite(t)||ft("twistDeg must be finite");let e=n.maxSegmentLength??1;(!Number.isFinite(e)||e<.05)&&ft("maxSegmentLength must be at least 0.05 mm");let i=null;if(n.braid){Vi(n.braid,["pitch","depth","strands"],"braid");let{pitch:s,depth:r,strands:o}=n.braid;Number.isFinite(s)&&s>0&&Number.isFinite(r)&&r>=0&&Number.isInteger(o)&&o>=2&&o<=64&&o%2===0||ft("braid needs positive pitch, nonnegative depth, and an even strand count from 2 to 64"),i={pitch:s,depth:r,strands:o}}return{restSpec:Fa(n.rest),pathSpec:Fa(n.path),twistDeg:t,maxSegmentLength:e,braid:i}}function Oa(n,t,e){let i=[];for(let s=0;s<n.length;s++){let r=n[s],o=n[(s+1)%n.length],a=e?r[0]>=t:r[0]<=t,c=e?o[0]>=t:o[0]<=t;if(a&&i.push(r),a!==c){let l=(t-r[0])/(o[0]-r[0]);i.push(r.map((u,h)=>u+l*(o[h]-u)))}}return i.filter((s,r)=>!r||Math.abs(s[1]-i[r-1][1])+Math.abs(s[2]-i[r-1][2])+Math.abs(s[3]-i[r-1][3])>1e-10)}function jd(n,t,e,i,s){if(s>=e.length)return{geometry:t,sourceTriangles:null};let r=t.attributes.position,o=new n.Vector3,a=new Float64Array(r.count),c=new Map;for(let _=0;_<r.count;_++){let v=[r.getX(_),r.getY(_),r.getZ(_)].join(","),y=c.get(v);y===void 0&&(o.fromBufferAttribute(r,_).applyMatrix4(i),y=qn(e,o.toArray()).distance,c.set(v,y)),a[_]=y}c.clear();let l=t.index?.count??r.count;if(l%3)return{geometry:t.clone(),sourceTriangles:null};let u=Object.entries(t.attributes),h=Object.fromEntries(u.map(([_])=>[_,[]])),f=[],p=[],m=new Map,g=d(_=>t.index?t.index.getX(_):_,"index");for(let _=0;_<l;_+=3){let v=[g(_),g(_+1),g(_+2)],y=v.map(M=>a[M]),b=y.map((M,A)=>[M,...[0,1,2].map(I=>A===I?1:0)]),T=Math.floor(Math.min(...y)/s),S=Math.floor(Math.max(...y)/s);for(let M=T;M<=S;M++){let A=Oa(Oa(b,M*s,!0),(M+1)*s,!1);for(let I=1;I<A.length-1;I++){let C=[A[0],A[I],A[I+1]],N=Bt(C[1].slice(1),C[0].slice(1)),R=Bt(C[2].slice(1),C[0].slice(1));if(!(Wt(Me(N,R))<1e-12)){f.push(_/3),f.length>Na&&ft(`refined tube exceeds ${Na} triangles; increase maxSegmentLength`);for(let w of C){let P=v.map((E,D)=>[E,Math.round(w[D+1]*1e10)]).filter(([,E])=>E).sort((E,D)=>E[0]-D[0]).map(E=>E.join(":")).join(","),L=m.get(P);if(L===void 0){L=m.size,m.set(P,L);for(let[E,D]of u)for(let F=0;F<D.itemSize;F++)h[E].push(v.reduce((O,U,B)=>O+w[B+1]*D.getComponent(U,F),0))}p.push(L)}}}}}let x=t.clone();for(let[_,v]of u)x.setAttribute(_,new n.Float32BufferAttribute(h[_],v.itemSize));return x.setIndex(p),x.clearGroups(),{geometry:x,sourceTriangles:new Uint32Array(f)}}function qa(n,t,e,i,s,r=!1){let o=[],a=r?new Float32Array(t.count):new Uint32Array(t.count),c=new Map,l=new n.Vector3,u=new n.Matrix3().getNormalMatrix(s),h=new n.Vector3;for(let p=0;p<t.count;p++){let m=[t.getX(p),t.getY(p),t.getZ(p),...e?[e.getX(p),e.getY(p),e.getZ(p)]:[]].join(","),g=c.get(m);if(g!==void 0){a[p]=g;continue}let x=o.length/8;c.set(m,x),a[p]=x,l.fromBufferAttribute(t,p).applyMatrix4(s);let _=qn(i,[l.x,l.y,l.z]),v=un(i,_.distance),y=cn(Tt(v.normal,_.transverse[0]),Tt(v.binormal,_.transverse[1])),b=1-dt(v.curvature,y);b<=Ue&&ft("rest mesh crosses the centerline curvature radius");let T=[0,0,0];if(e){h.fromBufferAttribute(e,p).applyNormalMatrix(u);let S=[h.x,h.y,h.z];T=[dt(S,v.normal),dt(S,v.binormal),dt(S,v.tangent)]}o.push(_.distance/i.length,..._.transverse,_.axial,...T,b)}let f=r?new Float32Array(Math.ceil(o.length/4096)*4096):new Float64Array(o.length);return f.set(o),{values:f,indices:a,gpu:r}}function Er(n,t,e,i,s,r){let{path:o,rest:a}=s,c=new n.Vector3,l=new n.Vector3,u=new n.Matrix3().getNormalMatrix(r),h=s.twistDeg*Math.PI/180,f=rt(h),p=ht(h),m=o.length/a.length,g=new Map,x=i.values,_=new Map;for(let v=0;v<t.count;v++){let y=i.indices[v],b=_.get(y);if(b!==void 0){t.setXYZ(v,t.getX(b),t.getY(b),t.getZ(b)),e&&e.setXYZ(v,e.getX(b),e.getY(b),e.getZ(b));continue}_.set(y,v);let T=y*8,S=x[T],M=g.get(S);M||(M=un(o,S*o.length),g.set(S,M));let A=f*x[T+1]-p*x[T+2],I=p*x[T+1]+f*x[T+2],C=M.normal[0]*A+M.binormal[0]*I,N=M.normal[1]*A+M.binormal[1]*I,R=M.normal[2]*A+M.binormal[2]*I,w=M.curvature[0]*C+M.curvature[1]*N+M.curvature[2]*R;if(1-w<=Sr){let L=(1-Sr)/w;C*=L,N*=L,R*=L,w=1-Sr}let P=1-w;if(c.set(M.point[0]+C+x[T+3]*M.tangent[0],M.point[1]+N+x[T+3]*M.tangent[1],M.point[2]+R+x[T+3]*M.tangent[2]).applyMatrix4(r),t.setXYZ(v,c.x,c.y,c.z),e){let L=f*x[T+4]-p*x[T+5],E=p*x[T+4]+f*x[T+5],D=x[T+6]*x[T+7]/(P*m);l.set(L*M.normal[0]+E*M.binormal[0]+D*M.tangent[0],L*M.normal[1]+E*M.binormal[1]+D*M.tangent[1],L*M.normal[2]+E*M.binormal[2]+D*M.tangent[2]).applyNormalMatrix(u),e.setXYZ(v,l.x,l.y,l.z)}}t.needsUpdate=!0,e&&(e.needsUpdate=!0)}function Qd(n,t,e,i,s,r){let o=e.clone(),a=e.attributes.instanceStart,c=e.attributes.instanceEnd,l=e.attributes.position;if(!a&&!l)return o;let u=a?null:e.index,h=a?a.count:u?u.count/2:t.isLineSegments?l.count/2:l.count-1,f=d((y,b)=>u?u.getX(y*2+b):t.isLineSegments?y*2+b:y+b,"vertexOf"),p=a?[]:Object.entries(e.attributes).filter(([y])=>y!=="position"),m=Object.fromEntries(p.map(([y])=>[y,[]])),g=new n.Vector3,x=new n.Vector3,_=new n.Vector3,v=[];for(let y=0;y<h;y++){let b=a?y:f(y,0),T=c?y:f(y,1);g.fromBufferAttribute(a||l,b),x.fromBufferAttribute(c||l,T);let S=qn(i,_.copy(g).applyMatrix4(s).toArray()).distance,M=qn(i,_.copy(x).applyMatrix4(s).toArray()).distance,A=Math.max(1,Math.ceil(Math.abs(M-S)/r));for(let I=0;I<A;I++)for(let C of[I/A,(I+1)/A]){v.push(g.x+(x.x-g.x)*C,g.y+(x.y-g.y)*C,g.z+(x.z-g.z)*C);for(let[N,R]of p){let w=C<1?b:T;for(let P=0;P<R.itemSize;P++)m[N].push(R.array[w*R.itemSize+P])}}}if(a)o.setPositions(v);else{o.setAttribute("position",new n.Float32BufferAttribute(v,3));for(let[y,b]of p)o.setAttribute(y,new n.BufferAttribute(new b.array.constructor(m[y]),b.itemSize,b.normalized));o.setIndex(null)}return o}function Cr(n,t,e,i=new n.Matrix4){if(!t)return;for(let c of t.children||[])Cr(n,c,e,i);if(!t.geometry)return;let s=t.tubeLineDeformationState;if(!e&&!s?.active||e&&s?.active&&Fe(s.lastSpec,e))return;let r=e?jt(e):null,o=e?$n(e):s?.restKey;if(!s||e&&o!==s.restKey){let c=s?.original||t.geometry,l=Qd(n,t,c,r.rest,i,r.maxSegmentLength),u=l.clone();s?.geometry.dispose(),u.userData={...u.userData,cadSceneCachedGeometry:!1};let h=l.attributes.instanceStart?["instanceStart","instanceEnd"]:["position"];s=t.tubeLineDeformationState={original:c,source:l,geometry:u,names:h,mappings:{},restKey:null,active:!1},t.geometry=u}if(!e){for(let c of s.names){let l=s.geometry.attributes[c],u=s.source.attributes[c];for(let h=0;h<u.count;h++)l.setXYZ(h,u.getX(h),u.getY(h),u.getZ(h));l.needsUpdate=!0}s.geometry.computeBoundingBox(),s.geometry.computeBoundingSphere(),s.active=!1;return}let a=i.clone().invert();for(let c of s.names)o!==s.restKey&&(s.mappings[c]=qa(n,s.source.attributes[c],null,r.rest,i)),Er(n,s.geometry.attributes[c],null,s.mappings[c],r,a);s.restKey=o,s.active=!0,s.lastSpec=e,s.geometry.computeBoundingBox(),s.geometry.computeBoundingSphere()}function tp(n,t){return`${$n(n)}|${t.elements.map(e=>Number(e).toPrecision(9)).join(",")}`}function $a(n,t,e,i){let s=Ba.get(t);s||(s=new Map,Ba.set(t,s));let r=tp(e,i),o=s.get(r);if(!o){let a=jd(n,t,e.rest,i,e.maxSegmentLength);o={restSource:a.geometry,sourceTriangles:a.sourceTriangles,mappings:new Map},s.set(r,o)}return o}function Ar(n,t,e,i,s){let r=s?"gpu":"exact",o=t.mappings.get(r);return o||(o=qa(n,t.restSource.attributes.position,t.restSource.attributes.normal,e.rest,i,s),t.mappings.set(r,o)),o}function Rr(n,t,e,i){let s=$a(n,t,e,i);return{geometry:s.restSource,sourceTriangles:s.sourceTriangles,mapping:Ar(n,s,e,i,!1),vertexCount:s.restSource.attributes.position.count}}function Yn(n,t,e,i,s,r=null){Er(n,s,r,t.mapping,e,i)}function ep(n,t,e,i,s){let r=e?.original||t.mesh.geometry,o=e?.originalFaceIds||t.mesh.userData?.faceIds,a=$a(n,r,i,s),c=a.restSource,l=new n.BufferGeometry;l.setIndex(c.index);for(let[h,f]of Object.entries(c.attributes)){let p=!t.gpuTubeDeformationAllowed&&(h==="position"||h==="normal");l.setAttribute(h,p?f.clone():f)}l.userData={...l.userData,cadSceneCachedGeometry:!1,__bvhSkipped:!0},l.boundsTree=null,e?.geometry.dispose();let u={original:r,originalFaceIds:o,source:c,prepared:a,geometry:l,active:!1,restKey:$n(i),mapping:null,partBounds:e?.partBounds||t.partBounds};return t.mesh.geometry=l,o&&a.sourceTriangles&&(t.mesh.userData.faceIds=new Uint32Array(a.sourceTriangles.map(h=>o[h]))),t.geometry=l,t.silhouette&&(t.silhouette.geometry=l),t.ghostMesh&&(t.ghostMesh.geometry=l),u}function np(n,t){t.geometry.attributes.position.copy(t.source.attributes.position),t.geometry.attributes.position.needsUpdate=!0,t.source.attributes.normal&&(t.geometry.attributes.normal.copy(t.source.attributes.normal),t.geometry.attributes.normal.needsUpdate=!0),t.geometry.computeBoundingBox(),t.geometry.computeBoundingSphere(),n.partBounds=t.partBounds,t.active=!1}function ip(n,t,e){if(!t?.mesh?.geometry)return;t.effectDeformation=e||null,Ca(n,t.material||t.mesh.material,e?.braid||null),e&&t.edgeInstance&&t.detachEdgeInstance?.();let i=new n.Matrix4;t.baseTransform&&i.fromArray(t.baseTransform).transpose(),(!e||t.edges?.visible!==!1)&&Cr(n,t.edges,e,i);let s=t.tubeDeformationState;if(e&&s?.active&&Fe(s.lastSpec,e)){br(t);return}if(!e&&!s?.active)return;let r=e?jt(e):null;if(e||Mr(t),(!s||e&&$n(e)!==s.restKey)&&(s=t.tubeDeformationState=ep(n,t,s,r,i)),!e){np(t,s);return}let o=i.clone().invert(),a=t.gpuTubeDeformationAllowed&&r.path.length<=vr;if(!s.mapping&&(s.mapping=Ar(n,s.prepared,r,i,a),!s.mapping.gpu)){let u=new Float32Array(s.geometry.attributes.position.count*3);for(let h=0;h<u.length/3;h++){let f=s.mapping.indices[h]*8,p=s.mapping.values;u.set([p[f]*r.rest.length,p[f+1],p[f+2]],h*3)}s.geometry.setAttribute(Hn,new n.BufferAttribute(u,3))}let c=d(()=>{for(let u of["position","normal"])s.geometry.attributes[u]===s.source.attributes[u]&&s.geometry.setAttribute(u,s.source.attributes[u].clone());s.exactMapping??=s.mapping.gpu?Ar(n,s.prepared,r,i,!1):s.mapping,Er(n,s.geometry.attributes.position,s.geometry.attributes.normal,s.exactMapping,r,o),s.geometry.computeBoundingBox(),s.geometry.computeBoundingSphere()},"materialize");if(Ia(n,t,s,r,o,un,c)){s.active=!0,s.lastSpec=e;return}Mr(t),c();let l=s.geometry.boundingBox.clone().applyMatrix4(i);t.partBounds={min:l.min.toArray(),max:l.max.toArray()},s.active=!0,s.lastSpec=e}var Ue,Sr,Na,kd,cn,Bt,Tt,dt,Me,Wt,La,Gd,Hd,Da,rn,$n,Ba,Hi=gn(()=>{Ra();Pa();ki();Un();Ue=1e-7,Sr=.05,Na=7e5,kd=128,cn=d((n,t)=>n.map((e,i)=>e+t[i]),"add"),Bt=d((n,t)=>n.map((e,i)=>e-t[i]),"sub"),Tt=d((n,t)=>n.map(e=>e*t),"mul"),dt=d((n,t)=>n.reduce((e,i,s)=>e+i*t[s],0),"dot"),Me=d((n,t)=>[n[1]*t[2]-n[2]*t[1],n[2]*t[0]-n[0]*t[2],n[0]*t[1]-n[1]*t[0]],"cross"),Wt=d(n=>Math.sqrt(n.reduce((t,e)=>t+e*e,0)),"length"),La=d((n,t)=>(n[0]-t[0])**2+(n[1]-t[1])**2+(n[2]-t[2])**2,"distanceSq");d(Vd,"boundsDistanceSq");d(ft,"fail");d(De,"vector");d(on,"unit");d(Vi,"keys");d(Gi,"rotate");d(Xn,"bezierAt");d(ln,"bezierDerivative");d(za,"bezierSecond");Gd=[0,.5384693101056831,-.5384693101056831,.906179845938664,-.906179845938664],Hd=[.5688888888888889,.4786286704993665,.4786286704993665,.2369268850561891,.2369268850561891];d(Wn,"bezierLength");d(ka,"transport");d(Wd,"buildBezierTable");d(Va,"bezierParameter");d(Ga,"segmentPoint");d(Tr,"segmentFrame");Da={line:["kind","start","end"],arc:["kind","center","axis","start","sweepDeg"],bezier:["kind","points"]};d(Ha,"pathSpecNormal");d(Wa,"canonicalSegment");d(Xd,"compileSegment");d(qd,"sampledBezierRadius");d($d,"segmentBounds");d(Xa,"compileTubePath");d(un,"sampleTubePath");d(Yd,"tablePoints");d(Zd,"closestBezierDistance");d(Jd,"closestArcDistance");d(qn,"projectTubePath");rn=new Map;d(Ua,"cachedCompile");d(Fa,"canonicalPathSpec");d(an,"sameNumbers");d(Fe,"sameTubeDeformation");d(wr,"sameTubeRestShape");d(jt,"compileDeformation");d(Kd,"normalizeTubeDeformation");$n=d(n=>JSON.stringify([n.restSpec,n.maxSegmentLength]),"restMappingKey");d(Oa,"clipPolygon");d(jd,"refineRestMesh");d(qa,"mappingFor");d(Er,"updateAttribute");d(Qd,"refineLineGeometry");d(Cr,"applyTubeDeformationToLineObject");Ba=new WeakMap;d(tp,"restPreparationKey");d($a,"prepareRestSurface");d(Ar,"preparedMapping");d(Rr,"prepareTubeBake");d(Yn,"poseTubeBake");d(ep,"createDeformationState");d(np,"restoreRestSurface");d(ip,"applyRecordTubeDeformation")});import dn from"node:fs";import pn from"node:path";function Vr(n){let t=new DataView(n,0,12);if(t.getUint32(0,!0)!==1179800915)throw new Error("not a SURF container");let e=t.getUint32(4,!0);if(e!==2)throw new Error(`unsupported SURF version ${e}`);let i=t.getUint32(8,!0),s=new Uint8Array(n,12,i),r=JSON.parse(new TextDecoder().decode(s)),o=12+i,a=new Float32Array(n.slice(o,o+(n.byteLength-o>>2<<2)));return{index:r,floats:a}}d(Vr,"parseSurf");function ae(n,t){let[e,i]=t;return n.subarray(e,e+i)}d(ae,"floatSpan");var io=1;var so=3;var os=0,as=1,cs=2,ls=3,us=4,hs=5,fs=6,ds=7,ro=0,oo=1,ao=2;var Ps=1,Ns=2,Ls=3,Ds=4,Us=5,Fs=6,Os=7;var Bs=300,co=301,zs=302;var lo=306,ps=1e3,bn=1001,ms=1002;var uo=1006;var ho=1008;var fo=1009;var po=1015;var mo=1023;var Tn=2300,li=2301,ai=2302,gs=2303,xs=2400,_s=2401,ys=2402;var ks="",Gt="srgb",vs="srgb-linear",Ms="linear",ci="srgb";var bs=35044;var Sn=2e3,Ss=2001;function Ec(n){for(let t=n.length-1;t>=0;--t)if(n[t]>=65535)return!0;return!1}d(Ec,"arrayNeedsUint32");function Cc(n){return ArrayBuffer.isView(n)&&!(n instanceof DataView)}d(Cc,"isTypedArray");function As(n){return document.createElementNS("http://www.w3.org/1999/xhtml",n)}d(As,"createElementNS");var Gr={},ui=null;function go(n){let t=n[0];if(typeof t=="string"&&t.startsWith("TSL:")){let e=n[1];e&&e.isStackTrace?n[0]+=" "+e.getLocation():n[1]='Stack trace not available. Enable "THREE.Node.captureStackTrace" to capture stack traces.'}return n}d(go,"enhanceLogMessage");function gt(...n){n=go(n);let t="THREE."+n.shift();if(ui)ui("warn",t,...n);else{let e=n[0];e&&e.isStackTrace?console.warn(e.getError(t)):console.warn(t,...n)}}d(gt,"warn");function ot(...n){n=go(n);let t="THREE."+n.shift();if(ui)ui("error",t,...n);else{let e=n[0];e&&e.isStackTrace?console.error(e.getError(t)):console.error(t,...n)}}d(ot,"error");function Ye(...n){let t=n.join(" ");t in Gr||(Gr[t]=!0,gt(...n))}d(Ye,"warnOnce");var Rc={[os]:as,[cs]:fs,[us]:ds,[ls]:hs,[as]:os,[fs]:cs,[ds]:us,[hs]:ls},Te=class{static{d(this,"EventDispatcher")}addEventListener(t,e){this._listeners===void 0&&(this._listeners={});let i=this._listeners;i[t]===void 0&&(i[t]=[]),i[t].indexOf(e)===-1&&i[t].push(e)}hasEventListener(t,e){let i=this._listeners;return i===void 0?!1:i[t]!==void 0&&i[t].indexOf(e)!==-1}removeEventListener(t,e){let i=this._listeners;if(i===void 0)return;let s=i[t];if(s!==void 0){let r=s.indexOf(e);r!==-1&&s.splice(r,1)}}dispatchEvent(t){let e=this._listeners;if(e===void 0)return;let i=e[t.type];if(i!==void 0){t.target=this;let s=i.slice(0);for(let r=0,o=s.length;r<o;r++)s[r].call(this,t);t.target=null}}},bt=["00","01","02","03","04","05","06","07","08","09","0a","0b","0c","0d","0e","0f","10","11","12","13","14","15","16","17","18","19","1a","1b","1c","1d","1e","1f","20","21","22","23","24","25","26","27","28","29","2a","2b","2c","2d","2e","2f","30","31","32","33","34","35","36","37","38","39","3a","3b","3c","3d","3e","3f","40","41","42","43","44","45","46","47","48","49","4a","4b","4c","4d","4e","4f","50","51","52","53","54","55","56","57","58","59","5a","5b","5c","5d","5e","5f","60","61","62","63","64","65","66","67","68","69","6a","6b","6c","6d","6e","6f","70","71","72","73","74","75","76","77","78","79","7a","7b","7c","7d","7e","7f","80","81","82","83","84","85","86","87","88","89","8a","8b","8c","8d","8e","8f","90","91","92","93","94","95","96","97","98","99","9a","9b","9c","9d","9e","9f","a0","a1","a2","a3","a4","a5","a6","a7","a8","a9","aa","ab","ac","ad","ae","af","b0","b1","b2","b3","b4","b5","b6","b7","b8","b9","ba","bb","bc","bd","be","bf","c0","c1","c2","c3","c4","c5","c6","c7","c8","c9","ca","cb","cc","cd","ce","cf","d0","d1","d2","d3","d4","d5","d6","d7","d8","d9","da","db","dc","dd","de","df","e0","e1","e2","e3","e4","e5","e6","e7","e8","e9","ea","eb","ec","ed","ee","ef","f0","f1","f2","f3","f4","f5","f6","f7","f8","f9","fa","fb","fc","fd","fe","ff"];var Hp=Math.PI/180,Ic=180/Math.PI;function Ei(){let n=Math.random()*4294967295|0,t=Math.random()*4294967295|0,e=Math.random()*4294967295|0,i=Math.random()*4294967295|0;return(bt[n&255]+bt[n>>8&255]+bt[n>>16&255]+bt[n>>24&255]+"-"+bt[t&255]+bt[t>>8&255]+"-"+bt[t>>16&15|64]+bt[t>>24&255]+"-"+bt[e&63|128]+bt[e>>8&255]+"-"+bt[e>>16&255]+bt[e>>24&255]+bt[i&255]+bt[i>>8&255]+bt[i>>16&255]+bt[i>>24&255]).toLowerCase()}d(Ei,"generateUUID");function K(n,t,e){return Math.max(t,Math.min(e,n))}d(K,"clamp");function Pc(n,t){return(n%t+t)%t}d(Pc,"euclideanModulo");function Ji(n,t,e){return(1-e)*n+e*t}d(Ji,"lerp");function xn(n,t){switch(t.constructor){case Float32Array:return n;case Uint32Array:return n/4294967295;case Uint16Array:return n/65535;case Uint8Array:return n/255;case Int32Array:return Math.max(n/2147483647,-1);case Int16Array:return Math.max(n/32767,-1);case Int8Array:return Math.max(n/127,-1);default:throw new Error("THREE.MathUtils: Invalid component type.")}}d(xn,"denormalize");function Et(n,t){switch(t.constructor){case Float32Array:return n;case Uint32Array:return Math.round(n*4294967295);case Uint16Array:return Math.round(n*65535);case Uint8Array:return Math.round(n*255);case Int32Array:return Math.round(n*2147483647);case Int16Array:return Math.round(n*32767);case Int8Array:return Math.round(n*127);default:throw new Error("THREE.MathUtils: Invalid component type.")}}d(Et,"normalize");var xt=class n{static{d(this,"Vector2")}static{n.prototype.isVector2=!0}constructor(t=0,e=0){this.x=t,this.y=e}get width(){return this.x}set width(t){this.x=t}get height(){return this.y}set height(t){this.y=t}set(t,e){return this.x=t,this.y=e,this}setScalar(t){return this.x=t,this.y=t,this}setX(t){return this.x=t,this}setY(t){return this.y=t,this}setComponent(t,e){switch(t){case 0:this.x=e;break;case 1:this.y=e;break;default:throw new Error("THREE.Vector2: index is out of range: "+t)}return this}getComponent(t){switch(t){case 0:return this.x;case 1:return this.y;default:throw new Error("THREE.Vector2: index is out of range: "+t)}}clone(){return new this.constructor(this.x,this.y)}copy(t){return this.x=t.x,this.y=t.y,this}add(t){return this.x+=t.x,this.y+=t.y,this}addScalar(t){return this.x+=t,this.y+=t,this}addVectors(t,e){return this.x=t.x+e.x,this.y=t.y+e.y,this}addScaledVector(t,e){return this.x+=t.x*e,this.y+=t.y*e,this}sub(t){return this.x-=t.x,this.y-=t.y,this}subScalar(t){return this.x-=t,this.y-=t,this}subVectors(t,e){return this.x=t.x-e.x,this.y=t.y-e.y,this}multiply(t){return this.x*=t.x,this.y*=t.y,this}multiplyScalar(t){return this.x*=t,this.y*=t,this}divide(t){return this.x/=t.x,this.y/=t.y,this}divideScalar(t){return this.multiplyScalar(1/t)}applyMatrix3(t){let e=this.x,i=this.y,s=t.elements;return this.x=s[0]*e+s[3]*i+s[6],this.y=s[1]*e+s[4]*i+s[7],this}min(t){return this.x=Math.min(this.x,t.x),this.y=Math.min(this.y,t.y),this}max(t){return this.x=Math.max(this.x,t.x),this.y=Math.max(this.y,t.y),this}clamp(t,e){return this.x=K(this.x,t.x,e.x),this.y=K(this.y,t.y,e.y),this}clampScalar(t,e){return this.x=K(this.x,t,e),this.y=K(this.y,t,e),this}clampLength(t,e){let i=this.length();return this.divideScalar(i||1).multiplyScalar(K(i,t,e))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this}negate(){return this.x=-this.x,this.y=-this.y,this}dot(t){return this.x*t.x+this.y*t.y}cross(t){return this.x*t.y-this.y*t.x}lengthSq(){return this.x*this.x+this.y*this.y}length(){return Math.sqrt(this.x*this.x+this.y*this.y)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)}normalize(){return this.divideScalar(this.length()||1)}angle(){return Math.atan2(-this.y,-this.x)+Math.PI}angleTo(t){let e=Math.sqrt(this.lengthSq()*t.lengthSq());if(e===0)return Math.PI/2;let i=this.dot(t)/e;return Math.acos(K(i,-1,1))}distanceTo(t){return Math.sqrt(this.distanceToSquared(t))}distanceToSquared(t){let e=this.x-t.x,i=this.y-t.y;return e*e+i*i}manhattanDistanceTo(t){return Math.abs(this.x-t.x)+Math.abs(this.y-t.y)}setLength(t){return this.normalize().multiplyScalar(t)}lerp(t,e){return this.x+=(t.x-this.x)*e,this.y+=(t.y-this.y)*e,this}lerpVectors(t,e,i){return this.x=t.x+(e.x-t.x)*i,this.y=t.y+(e.y-t.y)*i,this}equals(t){return t.x===this.x&&t.y===this.y}fromArray(t,e=0){return this.x=t[e],this.y=t[e+1],this}toArray(t=[],e=0){return t[e]=this.x,t[e+1]=this.y,t}fromBufferAttribute(t,e){return this.x=t.getX(e),this.y=t.getY(e),this}rotateAround(t,e){let i=Math.cos(e),s=Math.sin(e),r=this.x-t.x,o=this.y-t.y;return this.x=r*i-o*s+t.x,this.y=r*s+o*i+t.y,this}random(){return this.x=Math.random(),this.y=Math.random(),this}*[Symbol.iterator](){yield this.x,yield this.y}},Yt=class{static{d(this,"Quaternion")}constructor(t=0,e=0,i=0,s=1){this.isQuaternion=!0,this._x=t,this._y=e,this._z=i,this._w=s}static slerpFlat(t,e,i,s,r,o,a){let c=i[s+0],l=i[s+1],u=i[s+2],h=i[s+3],f=r[o+0],p=r[o+1],m=r[o+2],g=r[o+3];if(h!==g||c!==f||l!==p||u!==m){let x=c*f+l*p+u*m+h*g;x<0&&(f=-f,p=-p,m=-m,g=-g,x=-x);let _=1-a;if(x<.9995){let v=Math.acos(x),y=Math.sin(v);_=Math.sin(_*v)/y,a=Math.sin(a*v)/y,c=c*_+f*a,l=l*_+p*a,u=u*_+m*a,h=h*_+g*a}else{c=c*_+f*a,l=l*_+p*a,u=u*_+m*a,h=h*_+g*a;let v=1/Math.sqrt(c*c+l*l+u*u+h*h);c*=v,l*=v,u*=v,h*=v}}t[e]=c,t[e+1]=l,t[e+2]=u,t[e+3]=h}static multiplyQuaternionsFlat(t,e,i,s,r,o){let a=i[s],c=i[s+1],l=i[s+2],u=i[s+3],h=r[o],f=r[o+1],p=r[o+2],m=r[o+3];return t[e]=a*m+u*h+c*p-l*f,t[e+1]=c*m+u*f+l*h-a*p,t[e+2]=l*m+u*p+a*f-c*h,t[e+3]=u*m-a*h-c*f-l*p,t}get x(){return this._x}set x(t){this._x=t,this._onChangeCallback()}get y(){return this._y}set y(t){this._y=t,this._onChangeCallback()}get z(){return this._z}set z(t){this._z=t,this._onChangeCallback()}get w(){return this._w}set w(t){this._w=t,this._onChangeCallback()}set(t,e,i,s){return this._x=t,this._y=e,this._z=i,this._w=s,this._onChangeCallback(),this}clone(){return new this.constructor(this._x,this._y,this._z,this._w)}copy(t){return this._x=t.x,this._y=t.y,this._z=t.z,this._w=t.w,this._onChangeCallback(),this}setFromEuler(t,e=!0){let i=t._x,s=t._y,r=t._z,o=t._order,a=Math.cos,c=Math.sin,l=a(i/2),u=a(s/2),h=a(r/2),f=c(i/2),p=c(s/2),m=c(r/2);switch(o){case"XYZ":this._x=f*u*h+l*p*m,this._y=l*p*h-f*u*m,this._z=l*u*m+f*p*h,this._w=l*u*h-f*p*m;break;case"YXZ":this._x=f*u*h+l*p*m,this._y=l*p*h-f*u*m,this._z=l*u*m-f*p*h,this._w=l*u*h+f*p*m;break;case"ZXY":this._x=f*u*h-l*p*m,this._y=l*p*h+f*u*m,this._z=l*u*m+f*p*h,this._w=l*u*h-f*p*m;break;case"ZYX":this._x=f*u*h-l*p*m,this._y=l*p*h+f*u*m,this._z=l*u*m-f*p*h,this._w=l*u*h+f*p*m;break;case"YZX":this._x=f*u*h+l*p*m,this._y=l*p*h+f*u*m,this._z=l*u*m-f*p*h,this._w=l*u*h-f*p*m;break;case"XZY":this._x=f*u*h-l*p*m,this._y=l*p*h-f*u*m,this._z=l*u*m+f*p*h,this._w=l*u*h+f*p*m;break;default:gt("Quaternion: .setFromEuler() encountered an unknown order: "+o)}return e===!0&&this._onChangeCallback(),this}setFromAxisAngle(t,e){let i=e/2,s=Math.sin(i);return this._x=t.x*s,this._y=t.y*s,this._z=t.z*s,this._w=Math.cos(i),this._onChangeCallback(),this}setFromRotationMatrix(t){let e=t.elements,i=e[0],s=e[4],r=e[8],o=e[1],a=e[5],c=e[9],l=e[2],u=e[6],h=e[10],f=i+a+h;if(f>0){let p=.5/Math.sqrt(f+1);this._w=.25/p,this._x=(u-c)*p,this._y=(r-l)*p,this._z=(o-s)*p}else if(i>a&&i>h){let p=2*Math.sqrt(1+i-a-h);this._w=(u-c)/p,this._x=.25*p,this._y=(s+o)/p,this._z=(r+l)/p}else if(a>h){let p=2*Math.sqrt(1+a-i-h);this._w=(r-l)/p,this._x=(s+o)/p,this._y=.25*p,this._z=(c+u)/p}else{let p=2*Math.sqrt(1+h-i-a);this._w=(o-s)/p,this._x=(r+l)/p,this._y=(c+u)/p,this._z=.25*p}return this._onChangeCallback(),this}setFromUnitVectors(t,e){let i=t.dot(e)+1;return i<1e-8?(i=0,Math.abs(t.x)>Math.abs(t.z)?(this._x=-t.y,this._y=t.x,this._z=0,this._w=i):(this._x=0,this._y=-t.z,this._z=t.y,this._w=i)):(this._x=t.y*e.z-t.z*e.y,this._y=t.z*e.x-t.x*e.z,this._z=t.x*e.y-t.y*e.x,this._w=i),this.normalize()}angleTo(t){return 2*Math.acos(Math.abs(K(this.dot(t),-1,1)))}rotateTowards(t,e){let i=this.angleTo(t);if(i===0)return this;let s=Math.min(1,e/i);return this.slerp(t,s),this}identity(){return this.set(0,0,0,1)}invert(){return this.conjugate()}conjugate(){return this._x*=-1,this._y*=-1,this._z*=-1,this._onChangeCallback(),this}dot(t){return this._x*t._x+this._y*t._y+this._z*t._z+this._w*t._w}lengthSq(){return this._x*this._x+this._y*this._y+this._z*this._z+this._w*this._w}length(){return Math.sqrt(this._x*this._x+this._y*this._y+this._z*this._z+this._w*this._w)}normalize(){let t=this.length();return t===0?(this._x=0,this._y=0,this._z=0,this._w=1):(t=1/t,this._x=this._x*t,this._y=this._y*t,this._z=this._z*t,this._w=this._w*t),this._onChangeCallback(),this}multiply(t){return this.multiplyQuaternions(this,t)}premultiply(t){return this.multiplyQuaternions(t,this)}multiplyQuaternions(t,e){let i=t._x,s=t._y,r=t._z,o=t._w,a=e._x,c=e._y,l=e._z,u=e._w;return this._x=i*u+o*a+s*l-r*c,this._y=s*u+o*c+r*a-i*l,this._z=r*u+o*l+i*c-s*a,this._w=o*u-i*a-s*c-r*l,this._onChangeCallback(),this}slerp(t,e){let i=t._x,s=t._y,r=t._z,o=t._w,a=this.dot(t);a<0&&(i=-i,s=-s,r=-r,o=-o,a=-a);let c=1-e;if(a<.9995){let l=Math.acos(a),u=Math.sin(l);c=Math.sin(c*l)/u,e=Math.sin(e*l)/u,this._x=this._x*c+i*e,this._y=this._y*c+s*e,this._z=this._z*c+r*e,this._w=this._w*c+o*e,this._onChangeCallback()}else this._x=this._x*c+i*e,this._y=this._y*c+s*e,this._z=this._z*c+r*e,this._w=this._w*c+o*e,this.normalize();return this}slerpQuaternions(t,e,i){return this.copy(t).slerp(e,i)}random(){let t=2*Math.PI*Math.random(),e=2*Math.PI*Math.random(),i=Math.random(),s=Math.sqrt(1-i),r=Math.sqrt(i);return this.set(s*Math.sin(t),s*Math.cos(t),r*Math.sin(e),r*Math.cos(e))}equals(t){return t._x===this._x&&t._y===this._y&&t._z===this._z&&t._w===this._w}fromArray(t,e=0){return this._x=t[e],this._y=t[e+1],this._z=t[e+2],this._w=t[e+3],this._onChangeCallback(),this}toArray(t=[],e=0){return t[e]=this._x,t[e+1]=this._y,t[e+2]=this._z,t[e+3]=this._w,t}fromBufferAttribute(t,e){return this._x=t.getX(e),this._y=t.getY(e),this._z=t.getZ(e),this._w=t.getW(e),this._onChangeCallback(),this}toJSON(){return this.toArray()}_onChange(t){return this._onChangeCallback=t,this}_onChangeCallback(){}*[Symbol.iterator](){yield this._x,yield this._y,yield this._z,yield this._w}},k=class n{static{d(this,"Vector3")}static{n.prototype.isVector3=!0}constructor(t=0,e=0,i=0){this.x=t,this.y=e,this.z=i}set(t,e,i){return i===void 0&&(i=this.z),this.x=t,this.y=e,this.z=i,this}setScalar(t){return this.x=t,this.y=t,this.z=t,this}setX(t){return this.x=t,this}setY(t){return this.y=t,this}setZ(t){return this.z=t,this}setComponent(t,e){switch(t){case 0:this.x=e;break;case 1:this.y=e;break;case 2:this.z=e;break;default:throw new Error("THREE.Vector3: index is out of range: "+t)}return this}getComponent(t){switch(t){case 0:return this.x;case 1:return this.y;case 2:return this.z;default:throw new Error("THREE.Vector3: index is out of range: "+t)}}clone(){return new this.constructor(this.x,this.y,this.z)}copy(t){return this.x=t.x,this.y=t.y,this.z=t.z,this}add(t){return this.x+=t.x,this.y+=t.y,this.z+=t.z,this}addScalar(t){return this.x+=t,this.y+=t,this.z+=t,this}addVectors(t,e){return this.x=t.x+e.x,this.y=t.y+e.y,this.z=t.z+e.z,this}addScaledVector(t,e){return this.x+=t.x*e,this.y+=t.y*e,this.z+=t.z*e,this}sub(t){return this.x-=t.x,this.y-=t.y,this.z-=t.z,this}subScalar(t){return this.x-=t,this.y-=t,this.z-=t,this}subVectors(t,e){return this.x=t.x-e.x,this.y=t.y-e.y,this.z=t.z-e.z,this}multiply(t){return this.x*=t.x,this.y*=t.y,this.z*=t.z,this}multiplyScalar(t){return this.x*=t,this.y*=t,this.z*=t,this}multiplyVectors(t,e){return this.x=t.x*e.x,this.y=t.y*e.y,this.z=t.z*e.z,this}applyEuler(t){return this.applyQuaternion(Hr.setFromEuler(t))}applyAxisAngle(t,e){return this.applyQuaternion(Hr.setFromAxisAngle(t,e))}applyMatrix3(t){let e=this.x,i=this.y,s=this.z,r=t.elements;return this.x=r[0]*e+r[3]*i+r[6]*s,this.y=r[1]*e+r[4]*i+r[7]*s,this.z=r[2]*e+r[5]*i+r[8]*s,this}applyNormalMatrix(t){return this.applyMatrix3(t).normalize()}applyMatrix4(t){let e=this.x,i=this.y,s=this.z,r=t.elements,o=1/(r[3]*e+r[7]*i+r[11]*s+r[15]);return this.x=(r[0]*e+r[4]*i+r[8]*s+r[12])*o,this.y=(r[1]*e+r[5]*i+r[9]*s+r[13])*o,this.z=(r[2]*e+r[6]*i+r[10]*s+r[14])*o,this}applyQuaternion(t){let e=this.x,i=this.y,s=this.z,r=t.x,o=t.y,a=t.z,c=t.w,l=2*(o*s-a*i),u=2*(a*e-r*s),h=2*(r*i-o*e);return this.x=e+c*l+o*h-a*u,this.y=i+c*u+a*l-r*h,this.z=s+c*h+r*u-o*l,this}project(t){return this.applyMatrix4(t.matrixWorldInverse).applyMatrix4(t.projectionMatrix)}unproject(t){return this.applyMatrix4(t.projectionMatrixInverse).applyMatrix4(t.matrixWorld)}transformDirection(t){let e=this.x,i=this.y,s=this.z,r=t.elements;return this.x=r[0]*e+r[4]*i+r[8]*s,this.y=r[1]*e+r[5]*i+r[9]*s,this.z=r[2]*e+r[6]*i+r[10]*s,this.normalize()}divide(t){return this.x/=t.x,this.y/=t.y,this.z/=t.z,this}divideScalar(t){return this.multiplyScalar(1/t)}min(t){return this.x=Math.min(this.x,t.x),this.y=Math.min(this.y,t.y),this.z=Math.min(this.z,t.z),this}max(t){return this.x=Math.max(this.x,t.x),this.y=Math.max(this.y,t.y),this.z=Math.max(this.z,t.z),this}clamp(t,e){return this.x=K(this.x,t.x,e.x),this.y=K(this.y,t.y,e.y),this.z=K(this.z,t.z,e.z),this}clampScalar(t,e){return this.x=K(this.x,t,e),this.y=K(this.y,t,e),this.z=K(this.z,t,e),this}clampLength(t,e){let i=this.length();return this.divideScalar(i||1).multiplyScalar(K(i,t,e))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this.z=Math.floor(this.z),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this.z=Math.ceil(this.z),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this.z=Math.round(this.z),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this.z=Math.trunc(this.z),this}negate(){return this.x=-this.x,this.y=-this.y,this.z=-this.z,this}dot(t){return this.x*t.x+this.y*t.y+this.z*t.z}lengthSq(){return this.x*this.x+this.y*this.y+this.z*this.z}length(){return Math.sqrt(this.x*this.x+this.y*this.y+this.z*this.z)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)+Math.abs(this.z)}normalize(){return this.divideScalar(this.length()||1)}setLength(t){return this.normalize().multiplyScalar(t)}lerp(t,e){return this.x+=(t.x-this.x)*e,this.y+=(t.y-this.y)*e,this.z+=(t.z-this.z)*e,this}lerpVectors(t,e,i){return this.x=t.x+(e.x-t.x)*i,this.y=t.y+(e.y-t.y)*i,this.z=t.z+(e.z-t.z)*i,this}cross(t){return this.crossVectors(this,t)}crossVectors(t,e){let i=t.x,s=t.y,r=t.z,o=e.x,a=e.y,c=e.z;return this.x=s*c-r*a,this.y=r*o-i*c,this.z=i*a-s*o,this}projectOnVector(t){let e=t.lengthSq();if(e===0)return this.set(0,0,0);let i=t.dot(this)/e;return this.copy(t).multiplyScalar(i)}projectOnPlane(t){return Ki.copy(this).projectOnVector(t),this.sub(Ki)}reflect(t){return this.sub(Ki.copy(t).multiplyScalar(2*this.dot(t)))}angleTo(t){let e=Math.sqrt(this.lengthSq()*t.lengthSq());if(e===0)return Math.PI/2;let i=this.dot(t)/e;return Math.acos(K(i,-1,1))}distanceTo(t){return Math.sqrt(this.distanceToSquared(t))}distanceToSquared(t){let e=this.x-t.x,i=this.y-t.y,s=this.z-t.z;return e*e+i*i+s*s}manhattanDistanceTo(t){return Math.abs(this.x-t.x)+Math.abs(this.y-t.y)+Math.abs(this.z-t.z)}setFromSpherical(t){return this.setFromSphericalCoords(t.radius,t.phi,t.theta)}setFromSphericalCoords(t,e,i){let s=Math.sin(e)*t;return this.x=s*Math.sin(i),this.y=Math.cos(e)*t,this.z=s*Math.cos(i),this}setFromCylindrical(t){return this.setFromCylindricalCoords(t.radius,t.theta,t.y)}setFromCylindricalCoords(t,e,i){return this.x=t*Math.sin(e),this.y=i,this.z=t*Math.cos(e),this}setFromMatrixPosition(t){let e=t.elements;return this.x=e[12],this.y=e[13],this.z=e[14],this}setFromMatrixScale(t){let e=this.setFromMatrixColumn(t,0).length(),i=this.setFromMatrixColumn(t,1).length(),s=this.setFromMatrixColumn(t,2).length();return this.x=e,this.y=i,this.z=s,this}setFromMatrixColumn(t,e){return this.fromArray(t.elements,e*4)}setFromMatrix3Column(t,e){return this.fromArray(t.elements,e*3)}setFromEuler(t){return this.x=t._x,this.y=t._y,this.z=t._z,this}setFromColor(t){return this.x=t.r,this.y=t.g,this.z=t.b,this}equals(t){return t.x===this.x&&t.y===this.y&&t.z===this.z}fromArray(t,e=0){return this.x=t[e],this.y=t[e+1],this.z=t[e+2],this}toArray(t=[],e=0){return t[e]=this.x,t[e+1]=this.y,t[e+2]=this.z,t}fromBufferAttribute(t,e){return this.x=t.getX(e),this.y=t.getY(e),this.z=t.getZ(e),this}random(){return this.x=Math.random(),this.y=Math.random(),this.z=Math.random(),this}randomDirection(){let t=Math.random()*Math.PI*2,e=Math.random()*2-1,i=Math.sqrt(1-e*e);return this.x=i*Math.cos(t),this.y=e,this.z=i*Math.sin(t),this}*[Symbol.iterator](){yield this.x,yield this.y,yield this.z}},Ki=new k,Hr=new Yt,Y=class n{static{d(this,"Matrix3")}static{n.prototype.isMatrix3=!0}constructor(t,e,i,s,r,o,a,c,l){this.elements=[1,0,0,0,1,0,0,0,1],t!==void 0&&this.set(t,e,i,s,r,o,a,c,l)}set(t,e,i,s,r,o,a,c,l){let u=this.elements;return u[0]=t,u[1]=s,u[2]=a,u[3]=e,u[4]=r,u[5]=c,u[6]=i,u[7]=o,u[8]=l,this}identity(){return this.set(1,0,0,0,1,0,0,0,1),this}copy(t){let e=this.elements,i=t.elements;return e[0]=i[0],e[1]=i[1],e[2]=i[2],e[3]=i[3],e[4]=i[4],e[5]=i[5],e[6]=i[6],e[7]=i[7],e[8]=i[8],this}extractBasis(t,e,i){return t.setFromMatrix3Column(this,0),e.setFromMatrix3Column(this,1),i.setFromMatrix3Column(this,2),this}setFromMatrix4(t){let e=t.elements;return this.set(e[0],e[4],e[8],e[1],e[5],e[9],e[2],e[6],e[10]),this}multiply(t){return this.multiplyMatrices(this,t)}premultiply(t){return this.multiplyMatrices(t,this)}multiplyMatrices(t,e){let i=t.elements,s=e.elements,r=this.elements,o=i[0],a=i[3],c=i[6],l=i[1],u=i[4],h=i[7],f=i[2],p=i[5],m=i[8],g=s[0],x=s[3],_=s[6],v=s[1],y=s[4],b=s[7],T=s[2],S=s[5],M=s[8];return r[0]=o*g+a*v+c*T,r[3]=o*x+a*y+c*S,r[6]=o*_+a*b+c*M,r[1]=l*g+u*v+h*T,r[4]=l*x+u*y+h*S,r[7]=l*_+u*b+h*M,r[2]=f*g+p*v+m*T,r[5]=f*x+p*y+m*S,r[8]=f*_+p*b+m*M,this}multiplyScalar(t){let e=this.elements;return e[0]*=t,e[3]*=t,e[6]*=t,e[1]*=t,e[4]*=t,e[7]*=t,e[2]*=t,e[5]*=t,e[8]*=t,this}determinant(){let t=this.elements,e=t[0],i=t[1],s=t[2],r=t[3],o=t[4],a=t[5],c=t[6],l=t[7],u=t[8];return e*o*u-e*a*l-i*r*u+i*a*c+s*r*l-s*o*c}invert(){let t=this.elements,e=t[0],i=t[1],s=t[2],r=t[3],o=t[4],a=t[5],c=t[6],l=t[7],u=t[8],h=u*o-a*l,f=a*c-u*r,p=l*r-o*c,m=e*h+i*f+s*p;if(m===0)return this.set(0,0,0,0,0,0,0,0,0);let g=1/m;return t[0]=h*g,t[1]=(s*l-u*i)*g,t[2]=(a*i-s*o)*g,t[3]=f*g,t[4]=(u*e-s*c)*g,t[5]=(s*r-a*e)*g,t[6]=p*g,t[7]=(i*c-l*e)*g,t[8]=(o*e-i*r)*g,this}transpose(){let t,e=this.elements;return t=e[1],e[1]=e[3],e[3]=t,t=e[2],e[2]=e[6],e[6]=t,t=e[5],e[5]=e[7],e[7]=t,this}getNormalMatrix(t){return this.setFromMatrix4(t).invert().transpose()}transposeIntoArray(t){let e=this.elements;return t[0]=e[0],t[1]=e[3],t[2]=e[6],t[3]=e[1],t[4]=e[4],t[5]=e[7],t[6]=e[2],t[7]=e[5],t[8]=e[8],this}setUvTransform(t,e,i,s,r,o,a){let c=Math.cos(r),l=Math.sin(r);return this.set(i*c,i*l,-i*(c*o+l*a)+o+t,-s*l,s*c,-s*(-l*o+c*a)+a+e,0,0,1),this}scale(t,e){return Ye("Matrix3: .scale() is deprecated. Use .makeScale() instead."),this.premultiply(ji.makeScale(t,e)),this}rotate(t){return Ye("Matrix3: .rotate() is deprecated. Use .makeRotation() instead."),this.premultiply(ji.makeRotation(-t)),this}translate(t,e){return Ye("Matrix3: .translate() is deprecated. Use .makeTranslation() instead."),this.premultiply(ji.makeTranslation(t,e)),this}makeTranslation(t,e){return t.isVector2?this.set(1,0,t.x,0,1,t.y,0,0,1):this.set(1,0,t,0,1,e,0,0,1),this}makeRotation(t){let e=Math.cos(t),i=Math.sin(t);return this.set(e,-i,0,i,e,0,0,0,1),this}makeScale(t,e){return this.set(t,0,0,0,e,0,0,0,1),this}equals(t){let e=this.elements,i=t.elements;for(let s=0;s<9;s++)if(e[s]!==i[s])return!1;return!0}fromArray(t,e=0){for(let i=0;i<9;i++)this.elements[i]=t[i+e];return this}toArray(t=[],e=0){let i=this.elements;return t[e]=i[0],t[e+1]=i[1],t[e+2]=i[2],t[e+3]=i[3],t[e+4]=i[4],t[e+5]=i[5],t[e+6]=i[6],t[e+7]=i[7],t[e+8]=i[8],t}clone(){return new this.constructor().fromArray(this.elements)}},ji=new Y,Wr=new Y().set(.4123908,.3575843,.1804808,.212639,.7151687,.0721923,.0193308,.1191948,.9505322),Xr=new Y().set(3.2409699,-1.5373832,-.4986108,-.9692436,1.8759675,.0415551,.0556301,-.203977,1.0569715);function Nc(){let n={enabled:!0,workingColorSpace:vs,spaces:{},convert:d(function(s,r,o){return this.enabled===!1||r===o||!r||!o||(this.spaces[r].transfer===ci&&(s.r=ne(s.r),s.g=ne(s.g),s.b=ne(s.b)),this.spaces[r].primaries!==this.spaces[o].primaries&&(s.applyMatrix3(this.spaces[r].toXYZ),s.applyMatrix3(this.spaces[o].fromXYZ)),this.spaces[o].transfer===ci&&(s.r=Ze(s.r),s.g=Ze(s.g),s.b=Ze(s.b))),s},"convert"),workingToColorSpace:d(function(s,r){return this.convert(s,this.workingColorSpace,r)},"workingToColorSpace"),colorSpaceToWorking:d(function(s,r){return this.convert(s,r,this.workingColorSpace)},"colorSpaceToWorking"),getPrimaries:d(function(s){return this.spaces[s].primaries},"getPrimaries"),getTransfer:d(function(s){return s===ks?Ms:this.spaces[s].transfer},"getTransfer"),getToneMappingMode:d(function(s){return this.spaces[s].outputColorSpaceConfig.toneMappingMode||"standard"},"getToneMappingMode"),getLuminanceCoefficients:d(function(s,r=this.workingColorSpace){return s.fromArray(this.spaces[r].luminanceCoefficients)},"getLuminanceCoefficients"),define:d(function(s){Object.assign(this.spaces,s)},"define"),_getMatrix:d(function(s,r,o){return s.copy(this.spaces[r].toXYZ).multiply(this.spaces[o].fromXYZ)},"_getMatrix"),_getDrawingBufferColorSpace:d(function(s){return this.spaces[s].outputColorSpaceConfig.drawingBufferColorSpace},"_getDrawingBufferColorSpace"),_getUnpackColorSpace:d(function(s=this.workingColorSpace){return this.spaces[s].workingColorSpaceConfig.unpackColorSpace},"_getUnpackColorSpace"),fromWorkingColorSpace:d(function(s,r){return Ye("ColorManagement: .fromWorkingColorSpace() has been renamed to .workingToColorSpace()."),n.workingToColorSpace(s,r)},"fromWorkingColorSpace"),toWorkingColorSpace:d(function(s,r){return Ye("ColorManagement: .toWorkingColorSpace() has been renamed to .colorSpaceToWorking()."),n.colorSpaceToWorking(s,r)},"toWorkingColorSpace")},t=[.64,.33,.3,.6,.15,.06],e=[.2126,.7152,.0722],i=[.3127,.329];return n.define({[vs]:{primaries:t,whitePoint:i,transfer:Ms,toXYZ:Wr,fromXYZ:Xr,luminanceCoefficients:e,workingColorSpaceConfig:{unpackColorSpace:Gt},outputColorSpaceConfig:{drawingBufferColorSpace:Gt}},[Gt]:{primaries:t,whitePoint:i,transfer:ci,toXYZ:Wr,fromXYZ:Xr,luminanceCoefficients:e,outputColorSpaceConfig:{drawingBufferColorSpace:Gt}}}),n}d(Nc,"createColorManagement");var Vt=Nc();function ne(n){return n<.04045?n*.0773993808:Math.pow(n*.9478672986+.0521327014,2.4)}d(ne,"SRGBToLinear");function Ze(n){return n<.0031308?n*12.92:1.055*Math.pow(n,.41666)-.055}d(Ze,"LinearToSRGB");var ke,hi=class{static{d(this,"ImageUtils")}static getDataURL(t,e="image/png"){if(/^data:/i.test(t.src)||typeof HTMLCanvasElement>"u")return t.src;let i;if(t instanceof HTMLCanvasElement)i=t;else{ke===void 0&&(ke=As("canvas")),ke.width=t.width,ke.height=t.height;let s=ke.getContext("2d");t instanceof ImageData?s.putImageData(t,0,0):s.drawImage(t,0,0,t.width,t.height),i=ke}return i.toDataURL(e)}static sRGBToLinear(t){if(typeof HTMLImageElement<"u"&&t instanceof HTMLImageElement||typeof HTMLCanvasElement<"u"&&t instanceof HTMLCanvasElement||typeof ImageBitmap<"u"&&t instanceof ImageBitmap){let e=As("canvas");e.width=t.width,e.height=t.height;let i=e.getContext("2d");i.drawImage(t,0,0,t.width,t.height);let s=i.getImageData(0,0,t.width,t.height),r=s.data;for(let o=0;o<r.length;o++)r[o]=ne(r[o]/255)*255;return i.putImageData(s,0,0),e}else if(t.data){let e=t.data.slice(0);for(let i=0;i<e.length;i++)e instanceof Uint8Array||e instanceof Uint8ClampedArray?e[i]=Math.floor(ne(e[i]/255)*255):e[i]=ne(e[i]);return{data:e,width:t.width,height:t.height}}else return gt("ImageUtils.sRGBToLinear(): Unsupported image type. No color space conversion applied."),t}},Lc=0,fi=class{static{d(this,"Source")}constructor(t=null){this.isSource=!0,Object.defineProperty(this,"id",{value:Lc++}),this.uuid=Ei(),this.data=t,this.dataReady=!0,this.version=0}getSize(t){let e=this.data;return typeof HTMLVideoElement<"u"&&e instanceof HTMLVideoElement?t.set(e.videoWidth,e.videoHeight,0):typeof VideoFrame<"u"&&e instanceof VideoFrame?t.set(e.displayWidth,e.displayHeight,0):e!==null?t.set(e.width,e.height,e.depth||0):t.set(0,0,0),t}set needsUpdate(t){t===!0&&this.version++}toJSON(t){let e=t===void 0||typeof t=="string";if(!e&&t.images[this.uuid]!==void 0)return t.images[this.uuid];let i={uuid:this.uuid,url:""},s=this.data;if(s!==null){let r;if(Array.isArray(s)){r=[];for(let o=0,a=s.length;o<a;o++)s[o].isDataTexture?r.push(Qi(s[o].image)):r.push(Qi(s[o]))}else r=Qi(s);i.url=r}return e||(t.images[this.uuid]=i),i}};function Qi(n){return typeof HTMLImageElement<"u"&&n instanceof HTMLImageElement||typeof HTMLCanvasElement<"u"&&n instanceof HTMLCanvasElement||typeof ImageBitmap<"u"&&n instanceof ImageBitmap?hi.getDataURL(n):n.data?{data:Array.from(n.data),width:n.width,height:n.height,type:n.data.constructor.name}:(gt("Texture: Unable to serialize Texture."),{})}d(Qi,"serializeImage");var Dc=0,ts=new k,Je=class n extends Te{static{d(this,"Texture")}constructor(t=n.DEFAULT_IMAGE,e=n.DEFAULT_MAPPING,i=bn,s=bn,r=uo,o=ho,a=mo,c=fo,l=n.DEFAULT_ANISOTROPY,u=ks){super(),this.isTexture=!0,Object.defineProperty(this,"id",{value:Dc++}),this.uuid=Ei(),this.name="",this.source=new fi(t),this.mipmaps=[],this.mapping=e,this.channel=0,this.wrapS=i,this.wrapT=s,this.magFilter=r,this.minFilter=o,this.anisotropy=l,this.format=a,this.internalFormat=null,this.type=c,this.offset=new xt(0,0),this.repeat=new xt(1,1),this.center=new xt(0,0),this.rotation=0,this.matrixAutoUpdate=!0,this.matrix=new Y,this.generateMipmaps=!0,this.premultiplyAlpha=!1,this.flipY=!0,this.unpackAlignment=4,this.colorSpace=u,this.userData={},this.updateRanges=[],this.version=0,this.onUpdate=null,this.renderTarget=null,this.isRenderTargetTexture=!1,this.isArrayTexture=!!(t&&t.depth&&t.depth>1),this.pmremVersion=0,this.normalized=!1}get width(){return this.source.getSize(ts).x}get height(){return this.source.getSize(ts).y}get depth(){return this.source.getSize(ts).z}get image(){return this.source.data}set image(t){this.source.data=t}updateMatrix(){this.matrix.setUvTransform(this.offset.x,this.offset.y,this.repeat.x,this.repeat.y,this.rotation,this.center.x,this.center.y)}addUpdateRange(t,e){this.updateRanges.push({start:t,count:e})}clearUpdateRanges(){this.updateRanges.length=0}clone(){return new this.constructor().copy(this)}copy(t){return this.name=t.name,this.source=t.source,this.mipmaps=t.mipmaps.slice(0),this.mapping=t.mapping,this.channel=t.channel,this.wrapS=t.wrapS,this.wrapT=t.wrapT,this.magFilter=t.magFilter,this.minFilter=t.minFilter,this.anisotropy=t.anisotropy,this.format=t.format,this.internalFormat=t.internalFormat,this.type=t.type,this.normalized=t.normalized,this.offset.copy(t.offset),this.repeat.copy(t.repeat),this.center.copy(t.center),this.rotation=t.rotation,this.matrixAutoUpdate=t.matrixAutoUpdate,this.matrix.copy(t.matrix),this.generateMipmaps=t.generateMipmaps,this.premultiplyAlpha=t.premultiplyAlpha,this.flipY=t.flipY,this.unpackAlignment=t.unpackAlignment,this.colorSpace=t.colorSpace,this.renderTarget=t.renderTarget,this.isRenderTargetTexture=t.isRenderTargetTexture,this.isArrayTexture=t.isArrayTexture,this.userData=JSON.parse(JSON.stringify(t.userData)),this.needsUpdate=!0,this}setValues(t){for(let e in t){let i=t[e];if(i===void 0){gt(`Texture.setValues(): parameter '${e}' has value of undefined.`);continue}let s=this[e];if(s===void 0){gt(`Texture.setValues(): property '${e}' does not exist.`);continue}s&&i&&s.isVector2&&i.isVector2||s&&i&&s.isVector3&&i.isVector3||s&&i&&s.isMatrix3&&i.isMatrix3?s.copy(i):this[e]=i}}toJSON(t){let e=t===void 0||typeof t=="string";if(!e&&t.textures[this.uuid]!==void 0)return t.textures[this.uuid];let i={metadata:{version:4.7,type:"Texture",generator:"Texture.toJSON"},uuid:this.uuid,name:this.name,image:this.source.toJSON(t).uuid,mapping:this.mapping,channel:this.channel,repeat:[this.repeat.x,this.repeat.y],offset:[this.offset.x,this.offset.y],center:[this.center.x,this.center.y],rotation:this.rotation,wrap:[this.wrapS,this.wrapT],format:this.format,internalFormat:this.internalFormat,type:this.type,normalized:this.normalized,colorSpace:this.colorSpace,minFilter:this.minFilter,magFilter:this.magFilter,anisotropy:this.anisotropy,flipY:this.flipY,generateMipmaps:this.generateMipmaps,premultiplyAlpha:this.premultiplyAlpha,unpackAlignment:this.unpackAlignment};return Object.keys(this.userData).length>0&&(i.userData=this.userData),e||(t.textures[this.uuid]=i),i}dispose(){this.dispatchEvent({type:"dispose"})}transformUv(t){if(this.mapping!==Bs)return t;if(t.applyMatrix3(this.matrix),t.x<0||t.x>1)switch(this.wrapS){case ps:t.x=t.x-Math.floor(t.x);break;case bn:t.x=t.x<0?0:1;break;case ms:Math.abs(Math.floor(t.x)%2)===1?t.x=Math.ceil(t.x)-t.x:t.x=t.x-Math.floor(t.x);break}if(t.y<0||t.y>1)switch(this.wrapT){case ps:t.y=t.y-Math.floor(t.y);break;case bn:t.y=t.y<0?0:1;break;case ms:Math.abs(Math.floor(t.y)%2)===1?t.y=Math.ceil(t.y)-t.y:t.y=t.y-Math.floor(t.y);break}return this.flipY&&(t.y=1-t.y),t}set needsUpdate(t){t===!0&&(this.version++,this.source.needsUpdate=!0)}set needsPMREMUpdate(t){t===!0&&this.pmremVersion++}};Je.DEFAULT_IMAGE=null;Je.DEFAULT_MAPPING=Bs;Je.DEFAULT_ANISOTROPY=1;var Ts=class n{static{d(this,"Vector4")}static{n.prototype.isVector4=!0}constructor(t=0,e=0,i=0,s=1){this.x=t,this.y=e,this.z=i,this.w=s}get width(){return this.z}set width(t){this.z=t}get height(){return this.w}set height(t){this.w=t}set(t,e,i,s){return this.x=t,this.y=e,this.z=i,this.w=s,this}setScalar(t){return this.x=t,this.y=t,this.z=t,this.w=t,this}setX(t){return this.x=t,this}setY(t){return this.y=t,this}setZ(t){return this.z=t,this}setW(t){return this.w=t,this}setComponent(t,e){switch(t){case 0:this.x=e;break;case 1:this.y=e;break;case 2:this.z=e;break;case 3:this.w=e;break;default:throw new Error("THREE.Vector4: index is out of range: "+t)}return this}getComponent(t){switch(t){case 0:return this.x;case 1:return this.y;case 2:return this.z;case 3:return this.w;default:throw new Error("THREE.Vector4: index is out of range: "+t)}}clone(){return new this.constructor(this.x,this.y,this.z,this.w)}copy(t){return this.x=t.x,this.y=t.y,this.z=t.z,this.w=t.w!==void 0?t.w:1,this}add(t){return this.x+=t.x,this.y+=t.y,this.z+=t.z,this.w+=t.w,this}addScalar(t){return this.x+=t,this.y+=t,this.z+=t,this.w+=t,this}addVectors(t,e){return this.x=t.x+e.x,this.y=t.y+e.y,this.z=t.z+e.z,this.w=t.w+e.w,this}addScaledVector(t,e){return this.x+=t.x*e,this.y+=t.y*e,this.z+=t.z*e,this.w+=t.w*e,this}sub(t){return this.x-=t.x,this.y-=t.y,this.z-=t.z,this.w-=t.w,this}subScalar(t){return this.x-=t,this.y-=t,this.z-=t,this.w-=t,this}subVectors(t,e){return this.x=t.x-e.x,this.y=t.y-e.y,this.z=t.z-e.z,this.w=t.w-e.w,this}multiply(t){return this.x*=t.x,this.y*=t.y,this.z*=t.z,this.w*=t.w,this}multiplyScalar(t){return this.x*=t,this.y*=t,this.z*=t,this.w*=t,this}applyMatrix4(t){let e=this.x,i=this.y,s=this.z,r=this.w,o=t.elements;return this.x=o[0]*e+o[4]*i+o[8]*s+o[12]*r,this.y=o[1]*e+o[5]*i+o[9]*s+o[13]*r,this.z=o[2]*e+o[6]*i+o[10]*s+o[14]*r,this.w=o[3]*e+o[7]*i+o[11]*s+o[15]*r,this}divide(t){return this.x/=t.x,this.y/=t.y,this.z/=t.z,this.w/=t.w,this}divideScalar(t){return this.multiplyScalar(1/t)}setAxisAngleFromQuaternion(t){this.w=2*Math.acos(t.w);let e=Math.sqrt(1-t.w*t.w);return e<1e-4?(this.x=1,this.y=0,this.z=0):(this.x=t.x/e,this.y=t.y/e,this.z=t.z/e),this}setAxisAngleFromRotationMatrix(t){let e,i,s,r,c=t.elements,l=c[0],u=c[4],h=c[8],f=c[1],p=c[5],m=c[9],g=c[2],x=c[6],_=c[10];if(Math.abs(u-f)<.01&&Math.abs(h-g)<.01&&Math.abs(m-x)<.01){if(Math.abs(u+f)<.1&&Math.abs(h+g)<.1&&Math.abs(m+x)<.1&&Math.abs(l+p+_-3)<.1)return this.set(1,0,0,0),this;e=Math.PI;let y=(l+1)/2,b=(p+1)/2,T=(_+1)/2,S=(u+f)/4,M=(h+g)/4,A=(m+x)/4;return y>b&&y>T?y<.01?(i=0,s=.707106781,r=.707106781):(i=Math.sqrt(y),s=S/i,r=M/i):b>T?b<.01?(i=.707106781,s=0,r=.707106781):(s=Math.sqrt(b),i=S/s,r=A/s):T<.01?(i=.707106781,s=.707106781,r=0):(r=Math.sqrt(T),i=M/r,s=A/r),this.set(i,s,r,e),this}let v=Math.sqrt((x-m)*(x-m)+(h-g)*(h-g)+(f-u)*(f-u));return Math.abs(v)<.001&&(v=1),this.x=(x-m)/v,this.y=(h-g)/v,this.z=(f-u)/v,this.w=Math.acos((l+p+_-1)/2),this}setFromMatrixPosition(t){let e=t.elements;return this.x=e[12],this.y=e[13],this.z=e[14],this.w=e[15],this}min(t){return this.x=Math.min(this.x,t.x),this.y=Math.min(this.y,t.y),this.z=Math.min(this.z,t.z),this.w=Math.min(this.w,t.w),this}max(t){return this.x=Math.max(this.x,t.x),this.y=Math.max(this.y,t.y),this.z=Math.max(this.z,t.z),this.w=Math.max(this.w,t.w),this}clamp(t,e){return this.x=K(this.x,t.x,e.x),this.y=K(this.y,t.y,e.y),this.z=K(this.z,t.z,e.z),this.w=K(this.w,t.w,e.w),this}clampScalar(t,e){return this.x=K(this.x,t,e),this.y=K(this.y,t,e),this.z=K(this.z,t,e),this.w=K(this.w,t,e),this}clampLength(t,e){let i=this.length();return this.divideScalar(i||1).multiplyScalar(K(i,t,e))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this.z=Math.floor(this.z),this.w=Math.floor(this.w),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this.z=Math.ceil(this.z),this.w=Math.ceil(this.w),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this.z=Math.round(this.z),this.w=Math.round(this.w),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this.z=Math.trunc(this.z),this.w=Math.trunc(this.w),this}negate(){return this.x=-this.x,this.y=-this.y,this.z=-this.z,this.w=-this.w,this}dot(t){return this.x*t.x+this.y*t.y+this.z*t.z+this.w*t.w}lengthSq(){return this.x*this.x+this.y*this.y+this.z*this.z+this.w*this.w}length(){return Math.sqrt(this.x*this.x+this.y*this.y+this.z*this.z+this.w*this.w)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)+Math.abs(this.z)+Math.abs(this.w)}normalize(){return this.divideScalar(this.length()||1)}setLength(t){return this.normalize().multiplyScalar(t)}lerp(t,e){return this.x+=(t.x-this.x)*e,this.y+=(t.y-this.y)*e,this.z+=(t.z-this.z)*e,this.w+=(t.w-this.w)*e,this}lerpVectors(t,e,i){return this.x=t.x+(e.x-t.x)*i,this.y=t.y+(e.y-t.y)*i,this.z=t.z+(e.z-t.z)*i,this.w=t.w+(e.w-t.w)*i,this}equals(t){return t.x===this.x&&t.y===this.y&&t.z===this.z&&t.w===this.w}fromArray(t,e=0){return this.x=t[e],this.y=t[e+1],this.z=t[e+2],this.w=t[e+3],this}toArray(t=[],e=0){return t[e]=this.x,t[e+1]=this.y,t[e+2]=this.z,t[e+3]=this.w,t}fromBufferAttribute(t,e){return this.x=t.getX(e),this.y=t.getY(e),this.z=t.getZ(e),this.w=t.getW(e),this}random(){return this.x=Math.random(),this.y=Math.random(),this.z=Math.random(),this.w=Math.random(),this}*[Symbol.iterator](){yield this.x,yield this.y,yield this.z,yield this.w}};var _t=class n{static{d(this,"Matrix4")}static{n.prototype.isMatrix4=!0}constructor(t,e,i,s,r,o,a,c,l,u,h,f,p,m,g,x){this.elements=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],t!==void 0&&this.set(t,e,i,s,r,o,a,c,l,u,h,f,p,m,g,x)}set(t,e,i,s,r,o,a,c,l,u,h,f,p,m,g,x){let _=this.elements;return _[0]=t,_[4]=e,_[8]=i,_[12]=s,_[1]=r,_[5]=o,_[9]=a,_[13]=c,_[2]=l,_[6]=u,_[10]=h,_[14]=f,_[3]=p,_[7]=m,_[11]=g,_[15]=x,this}identity(){return this.set(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1),this}clone(){return new n().fromArray(this.elements)}copy(t){let e=this.elements,i=t.elements;return e[0]=i[0],e[1]=i[1],e[2]=i[2],e[3]=i[3],e[4]=i[4],e[5]=i[5],e[6]=i[6],e[7]=i[7],e[8]=i[8],e[9]=i[9],e[10]=i[10],e[11]=i[11],e[12]=i[12],e[13]=i[13],e[14]=i[14],e[15]=i[15],this}copyPosition(t){let e=this.elements,i=t.elements;return e[12]=i[12],e[13]=i[13],e[14]=i[14],this}setFromMatrix3(t){let e=t.elements;return this.set(e[0],e[3],e[6],0,e[1],e[4],e[7],0,e[2],e[5],e[8],0,0,0,0,1),this}extractBasis(t,e,i){return this.determinantAffine()===0?(t.set(1,0,0),e.set(0,1,0),i.set(0,0,1),this):(t.setFromMatrixColumn(this,0),e.setFromMatrixColumn(this,1),i.setFromMatrixColumn(this,2),this)}makeBasis(t,e,i){return this.set(t.x,e.x,i.x,0,t.y,e.y,i.y,0,t.z,e.z,i.z,0,0,0,0,1),this}extractRotation(t){if(t.determinantAffine()===0)return this.identity();let e=this.elements,i=t.elements,s=1/Ve.setFromMatrixColumn(t,0).length(),r=1/Ve.setFromMatrixColumn(t,1).length(),o=1/Ve.setFromMatrixColumn(t,2).length();return e[0]=i[0]*s,e[1]=i[1]*s,e[2]=i[2]*s,e[3]=0,e[4]=i[4]*r,e[5]=i[5]*r,e[6]=i[6]*r,e[7]=0,e[8]=i[8]*o,e[9]=i[9]*o,e[10]=i[10]*o,e[11]=0,e[12]=0,e[13]=0,e[14]=0,e[15]=1,this}makeRotationFromEuler(t){let e=this.elements,i=t.x,s=t.y,r=t.z,o=Math.cos(i),a=Math.sin(i),c=Math.cos(s),l=Math.sin(s),u=Math.cos(r),h=Math.sin(r);if(t.order==="XYZ"){let f=o*u,p=o*h,m=a*u,g=a*h;e[0]=c*u,e[4]=-c*h,e[8]=l,e[1]=p+m*l,e[5]=f-g*l,e[9]=-a*c,e[2]=g-f*l,e[6]=m+p*l,e[10]=o*c}else if(t.order==="YXZ"){let f=c*u,p=c*h,m=l*u,g=l*h;e[0]=f+g*a,e[4]=m*a-p,e[8]=o*l,e[1]=o*h,e[5]=o*u,e[9]=-a,e[2]=p*a-m,e[6]=g+f*a,e[10]=o*c}else if(t.order==="ZXY"){let f=c*u,p=c*h,m=l*u,g=l*h;e[0]=f-g*a,e[4]=-o*h,e[8]=m+p*a,e[1]=p+m*a,e[5]=o*u,e[9]=g-f*a,e[2]=-o*l,e[6]=a,e[10]=o*c}else if(t.order==="ZYX"){let f=o*u,p=o*h,m=a*u,g=a*h;e[0]=c*u,e[4]=m*l-p,e[8]=f*l+g,e[1]=c*h,e[5]=g*l+f,e[9]=p*l-m,e[2]=-l,e[6]=a*c,e[10]=o*c}else if(t.order==="YZX"){let f=o*c,p=o*l,m=a*c,g=a*l;e[0]=c*u,e[4]=g-f*h,e[8]=m*h+p,e[1]=h,e[5]=o*u,e[9]=-a*u,e[2]=-l*u,e[6]=p*h+m,e[10]=f-g*h}else if(t.order==="XZY"){let f=o*c,p=o*l,m=a*c,g=a*l;e[0]=c*u,e[4]=-h,e[8]=l*u,e[1]=f*h+g,e[5]=o*u,e[9]=p*h-m,e[2]=m*h-p,e[6]=a*u,e[10]=g*h+f}return e[3]=0,e[7]=0,e[11]=0,e[12]=0,e[13]=0,e[14]=0,e[15]=1,this}makeRotationFromQuaternion(t){return this.compose(Uc,t,Fc)}lookAt(t,e,i){let s=this.elements;return Lt.subVectors(t,e),Lt.lengthSq()===0&&(Lt.z=1),Lt.normalize(),ce.crossVectors(i,Lt),ce.lengthSq()===0&&(Math.abs(i.z)===1?Lt.x+=1e-4:Lt.z+=1e-4,Lt.normalize(),ce.crossVectors(i,Lt)),ce.normalize(),Kn.crossVectors(Lt,ce),s[0]=ce.x,s[4]=Kn.x,s[8]=Lt.x,s[1]=ce.y,s[5]=Kn.y,s[9]=Lt.y,s[2]=ce.z,s[6]=Kn.z,s[10]=Lt.z,this}multiply(t){return this.multiplyMatrices(this,t)}premultiply(t){return this.multiplyMatrices(t,this)}multiplyMatrices(t,e){let i=t.elements,s=e.elements,r=this.elements,o=i[0],a=i[4],c=i[8],l=i[12],u=i[1],h=i[5],f=i[9],p=i[13],m=i[2],g=i[6],x=i[10],_=i[14],v=i[3],y=i[7],b=i[11],T=i[15],S=s[0],M=s[4],A=s[8],I=s[12],C=s[1],N=s[5],R=s[9],w=s[13],P=s[2],L=s[6],E=s[10],D=s[14],F=s[3],O=s[7],U=s[11],B=s[15];return r[0]=o*S+a*C+c*P+l*F,r[4]=o*M+a*N+c*L+l*O,r[8]=o*A+a*R+c*E+l*U,r[12]=o*I+a*w+c*D+l*B,r[1]=u*S+h*C+f*P+p*F,r[5]=u*M+h*N+f*L+p*O,r[9]=u*A+h*R+f*E+p*U,r[13]=u*I+h*w+f*D+p*B,r[2]=m*S+g*C+x*P+_*F,r[6]=m*M+g*N+x*L+_*O,r[10]=m*A+g*R+x*E+_*U,r[14]=m*I+g*w+x*D+_*B,r[3]=v*S+y*C+b*P+T*F,r[7]=v*M+y*N+b*L+T*O,r[11]=v*A+y*R+b*E+T*U,r[15]=v*I+y*w+b*D+T*B,this}multiplyScalar(t){let e=this.elements;return e[0]*=t,e[4]*=t,e[8]*=t,e[12]*=t,e[1]*=t,e[5]*=t,e[9]*=t,e[13]*=t,e[2]*=t,e[6]*=t,e[10]*=t,e[14]*=t,e[3]*=t,e[7]*=t,e[11]*=t,e[15]*=t,this}determinant(){let t=this.elements,e=t[0],i=t[4],s=t[8],r=t[12],o=t[1],a=t[5],c=t[9],l=t[13],u=t[2],h=t[6],f=t[10],p=t[14],m=t[3],g=t[7],x=t[11],_=t[15],v=c*p-l*f,y=a*p-l*h,b=a*f-c*h,T=o*p-l*u,S=o*f-c*u,M=o*h-a*u;return e*(g*v-x*y+_*b)-i*(m*v-x*T+_*S)+s*(m*y-g*T+_*M)-r*(m*b-g*S+x*M)}determinantAffine(){let t=this.elements,e=t[0],i=t[4],s=t[8],r=t[1],o=t[5],a=t[9],c=t[2],l=t[6],u=t[10];return e*(o*u-a*l)-i*(r*u-a*c)+s*(r*l-o*c)}transpose(){let t=this.elements,e;return e=t[1],t[1]=t[4],t[4]=e,e=t[2],t[2]=t[8],t[8]=e,e=t[6],t[6]=t[9],t[9]=e,e=t[3],t[3]=t[12],t[12]=e,e=t[7],t[7]=t[13],t[13]=e,e=t[11],t[11]=t[14],t[14]=e,this}setPosition(t,e,i){let s=this.elements;return t.isVector3?(s[12]=t.x,s[13]=t.y,s[14]=t.z):(s[12]=t,s[13]=e,s[14]=i),this}invert(){let t=this.elements,e=t[0],i=t[1],s=t[2],r=t[3],o=t[4],a=t[5],c=t[6],l=t[7],u=t[8],h=t[9],f=t[10],p=t[11],m=t[12],g=t[13],x=t[14],_=t[15],v=e*a-i*o,y=e*c-s*o,b=e*l-r*o,T=i*c-s*a,S=i*l-r*a,M=s*l-r*c,A=u*g-h*m,I=u*x-f*m,C=u*_-p*m,N=h*x-f*g,R=h*_-p*g,w=f*_-p*x,P=v*w-y*R+b*N+T*C-S*I+M*A;if(P===0)return this.set(0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0);let L=1/P;return t[0]=(a*w-c*R+l*N)*L,t[1]=(s*R-i*w-r*N)*L,t[2]=(g*M-x*S+_*T)*L,t[3]=(f*S-h*M-p*T)*L,t[4]=(c*C-o*w-l*I)*L,t[5]=(e*w-s*C+r*I)*L,t[6]=(x*b-m*M-_*y)*L,t[7]=(u*M-f*b+p*y)*L,t[8]=(o*R-a*C+l*A)*L,t[9]=(i*C-e*R-r*A)*L,t[10]=(m*S-g*b+_*v)*L,t[11]=(h*b-u*S-p*v)*L,t[12]=(a*I-o*N-c*A)*L,t[13]=(e*N-i*I+s*A)*L,t[14]=(g*y-m*T-x*v)*L,t[15]=(u*T-h*y+f*v)*L,this}scale(t){let e=this.elements,i=t.x,s=t.y,r=t.z;return e[0]*=i,e[4]*=s,e[8]*=r,e[1]*=i,e[5]*=s,e[9]*=r,e[2]*=i,e[6]*=s,e[10]*=r,e[3]*=i,e[7]*=s,e[11]*=r,this}getMaxScaleOnAxis(){let t=this.elements,e=t[0]*t[0]+t[1]*t[1]+t[2]*t[2],i=t[4]*t[4]+t[5]*t[5]+t[6]*t[6],s=t[8]*t[8]+t[9]*t[9]+t[10]*t[10];return Math.sqrt(Math.max(e,i,s))}makeTranslation(t,e,i){return t.isVector3?this.set(1,0,0,t.x,0,1,0,t.y,0,0,1,t.z,0,0,0,1):this.set(1,0,0,t,0,1,0,e,0,0,1,i,0,0,0,1),this}makeRotationX(t){let e=Math.cos(t),i=Math.sin(t);return this.set(1,0,0,0,0,e,-i,0,0,i,e,0,0,0,0,1),this}makeRotationY(t){let e=Math.cos(t),i=Math.sin(t);return this.set(e,0,i,0,0,1,0,0,-i,0,e,0,0,0,0,1),this}makeRotationZ(t){let e=Math.cos(t),i=Math.sin(t);return this.set(e,-i,0,0,i,e,0,0,0,0,1,0,0,0,0,1),this}makeRotationAxis(t,e){let i=Math.cos(e),s=Math.sin(e),r=1-i,o=t.x,a=t.y,c=t.z,l=r*o,u=r*a;return this.set(l*o+i,l*a-s*c,l*c+s*a,0,l*a+s*c,u*a+i,u*c-s*o,0,l*c-s*a,u*c+s*o,r*c*c+i,0,0,0,0,1),this}makeScale(t,e,i){return this.set(t,0,0,0,0,e,0,0,0,0,i,0,0,0,0,1),this}makeShear(t,e,i,s,r,o){return this.set(1,i,r,0,t,1,o,0,e,s,1,0,0,0,0,1),this}compose(t,e,i){let s=this.elements,r=e._x,o=e._y,a=e._z,c=e._w,l=r+r,u=o+o,h=a+a,f=r*l,p=r*u,m=r*h,g=o*u,x=o*h,_=a*h,v=c*l,y=c*u,b=c*h,T=i.x,S=i.y,M=i.z;return s[0]=(1-(g+_))*T,s[1]=(p+b)*T,s[2]=(m-y)*T,s[3]=0,s[4]=(p-b)*S,s[5]=(1-(f+_))*S,s[6]=(x+v)*S,s[7]=0,s[8]=(m+y)*M,s[9]=(x-v)*M,s[10]=(1-(f+g))*M,s[11]=0,s[12]=t.x,s[13]=t.y,s[14]=t.z,s[15]=1,this}decompose(t,e,i){let s=this.elements;t.x=s[12],t.y=s[13],t.z=s[14];let r=this.determinantAffine();if(r===0)return i.set(1,1,1),e.identity(),this;let o=Ve.set(s[0],s[1],s[2]).length(),a=Ve.set(s[4],s[5],s[6]).length(),c=Ve.set(s[8],s[9],s[10]).length();r<0&&(o=-o),qt.copy(this);let l=1/o,u=1/a,h=1/c;return qt.elements[0]*=l,qt.elements[1]*=l,qt.elements[2]*=l,qt.elements[4]*=u,qt.elements[5]*=u,qt.elements[6]*=u,qt.elements[8]*=h,qt.elements[9]*=h,qt.elements[10]*=h,e.setFromRotationMatrix(qt),i.x=o,i.y=a,i.z=c,this}makePerspective(t,e,i,s,r,o,a=Sn,c=!1){let l=this.elements,u=2*r/(e-t),h=2*r/(i-s),f=(e+t)/(e-t),p=(i+s)/(i-s),m,g;if(c)m=r/(o-r),g=o*r/(o-r);else if(a===Sn)m=-(o+r)/(o-r),g=-2*o*r/(o-r);else if(a===Ss)m=-o/(o-r),g=-o*r/(o-r);else throw new Error("THREE.Matrix4.makePerspective(): Invalid coordinate system: "+a);return l[0]=u,l[4]=0,l[8]=f,l[12]=0,l[1]=0,l[5]=h,l[9]=p,l[13]=0,l[2]=0,l[6]=0,l[10]=m,l[14]=g,l[3]=0,l[7]=0,l[11]=-1,l[15]=0,this}makeOrthographic(t,e,i,s,r,o,a=Sn,c=!1){let l=this.elements,u=2/(e-t),h=2/(i-s),f=-(e+t)/(e-t),p=-(i+s)/(i-s),m,g;if(c)m=1/(o-r),g=o/(o-r);else if(a===Sn)m=-2/(o-r),g=-(o+r)/(o-r);else if(a===Ss)m=-1/(o-r),g=-r/(o-r);else throw new Error("THREE.Matrix4.makeOrthographic(): Invalid coordinate system: "+a);return l[0]=u,l[4]=0,l[8]=0,l[12]=f,l[1]=0,l[5]=h,l[9]=0,l[13]=p,l[2]=0,l[6]=0,l[10]=m,l[14]=g,l[3]=0,l[7]=0,l[11]=0,l[15]=1,this}equals(t){let e=this.elements,i=t.elements;for(let s=0;s<16;s++)if(e[s]!==i[s])return!1;return!0}fromArray(t,e=0){for(let i=0;i<16;i++)this.elements[i]=t[i+e];return this}toArray(t=[],e=0){let i=this.elements;return t[e]=i[0],t[e+1]=i[1],t[e+2]=i[2],t[e+3]=i[3],t[e+4]=i[4],t[e+5]=i[5],t[e+6]=i[6],t[e+7]=i[7],t[e+8]=i[8],t[e+9]=i[9],t[e+10]=i[10],t[e+11]=i[11],t[e+12]=i[12],t[e+13]=i[13],t[e+14]=i[14],t[e+15]=i[15],t}},Ve=new k,qt=new _t,Uc=new k(0,0,0),Fc=new k(1,1,1),ce=new k,Kn=new k,Lt=new k,qr=new _t,$r=new Yt,wn=class n{static{d(this,"Euler")}constructor(t=0,e=0,i=0,s=n.DEFAULT_ORDER){this.isEuler=!0,this._x=t,this._y=e,this._z=i,this._order=s}get x(){return this._x}set x(t){this._x=t,this._onChangeCallback()}get y(){return this._y}set y(t){this._y=t,this._onChangeCallback()}get z(){return this._z}set z(t){this._z=t,this._onChangeCallback()}get order(){return this._order}set order(t){this._order=t,this._onChangeCallback()}set(t,e,i,s=this._order){return this._x=t,this._y=e,this._z=i,this._order=s,this._onChangeCallback(),this}clone(){return new this.constructor(this._x,this._y,this._z,this._order)}copy(t){return this._x=t._x,this._y=t._y,this._z=t._z,this._order=t._order,this._onChangeCallback(),this}setFromRotationMatrix(t,e=this._order,i=!0){let s=t.elements,r=s[0],o=s[4],a=s[8],c=s[1],l=s[5],u=s[9],h=s[2],f=s[6],p=s[10];switch(e){case"XYZ":this._y=Math.asin(K(a,-1,1)),Math.abs(a)<.9999999?(this._x=Math.atan2(-u,p),this._z=Math.atan2(-o,r)):(this._x=Math.atan2(f,l),this._z=0);break;case"YXZ":this._x=Math.asin(-K(u,-1,1)),Math.abs(u)<.9999999?(this._y=Math.atan2(a,p),this._z=Math.atan2(c,l)):(this._y=Math.atan2(-h,r),this._z=0);break;case"ZXY":this._x=Math.asin(K(f,-1,1)),Math.abs(f)<.9999999?(this._y=Math.atan2(-h,p),this._z=Math.atan2(-o,l)):(this._y=0,this._z=Math.atan2(c,r));break;case"ZYX":this._y=Math.asin(-K(h,-1,1)),Math.abs(h)<.9999999?(this._x=Math.atan2(f,p),this._z=Math.atan2(c,r)):(this._x=0,this._z=Math.atan2(-o,l));break;case"YZX":this._z=Math.asin(K(c,-1,1)),Math.abs(c)<.9999999?(this._x=Math.atan2(-u,l),this._y=Math.atan2(-h,r)):(this._x=0,this._y=Math.atan2(a,p));break;case"XZY":this._z=Math.asin(-K(o,-1,1)),Math.abs(o)<.9999999?(this._x=Math.atan2(f,l),this._y=Math.atan2(a,r)):(this._x=Math.atan2(-u,p),this._y=0);break;default:gt("Euler: .setFromRotationMatrix() encountered an unknown order: "+e)}return this._order=e,i===!0&&this._onChangeCallback(),this}setFromQuaternion(t,e,i){return qr.makeRotationFromQuaternion(t),this.setFromRotationMatrix(qr,e,i)}setFromVector3(t,e=this._order){return this.set(t.x,t.y,t.z,e)}reorder(t){return $r.setFromEuler(this),this.setFromQuaternion($r,t)}equals(t){return t._x===this._x&&t._y===this._y&&t._z===this._z&&t._order===this._order}fromArray(t){return this._x=t[0],this._y=t[1],this._z=t[2],t[3]!==void 0&&(this._order=t[3]),this._onChangeCallback(),this}toArray(t=[],e=0){return t[e]=this._x,t[e+1]=this._y,t[e+2]=this._z,t[e+3]=this._order,t}_onChange(t){return this._onChangeCallback=t,this}_onChangeCallback(){}*[Symbol.iterator](){yield this._x,yield this._y,yield this._z,yield this._order}};wn.DEFAULT_ORDER="XYZ";var di=class{static{d(this,"Layers")}constructor(){this.mask=1}set(t){this.mask=(1<<t|0)>>>0}enable(t){this.mask|=1<<t|0}enableAll(){this.mask=-1}toggle(t){this.mask^=1<<t|0}disable(t){this.mask&=~(1<<t|0)}disableAll(){this.mask=0}test(t){return(this.mask&t.mask)!==0}isEnabled(t){return(this.mask&(1<<t|0))!==0}},Oc=0,Yr=new k,Ge=new Yt,te=new _t,jn=new k,_n=new k,Bc=new k,zc=new Yt,Zr=new k(1,0,0),Jr=new k(0,1,0),Kr=new k(0,0,1),jr={type:"added"},kc={type:"removed"},He={type:"childadded",child:null},es={type:"childremoved",child:null},we=class n extends Te{static{d(this,"Object3D")}constructor(){super(),this.isObject3D=!0,Object.defineProperty(this,"id",{value:Oc++}),this.uuid=Ei(),this.name="",this.type="Object3D",this.parent=null,this.children=[],this.up=n.DEFAULT_UP.clone();let t=new k,e=new wn,i=new Yt,s=new k(1,1,1);function r(){i.setFromEuler(e,!1)}d(r,"onRotationChange");function o(){e.setFromQuaternion(i,void 0,!1)}d(o,"onQuaternionChange"),e._onChange(r),i._onChange(o),Object.defineProperties(this,{position:{configurable:!0,enumerable:!0,value:t},rotation:{configurable:!0,enumerable:!0,value:e},quaternion:{configurable:!0,enumerable:!0,value:i},scale:{configurable:!0,enumerable:!0,value:s},modelViewMatrix:{value:new _t},normalMatrix:{value:new Y}}),this.matrix=new _t,this.matrixWorld=new _t,this.matrixAutoUpdate=n.DEFAULT_MATRIX_AUTO_UPDATE,this.matrixWorldAutoUpdate=n.DEFAULT_MATRIX_WORLD_AUTO_UPDATE,this.matrixWorldNeedsUpdate=!1,this.layers=new di,this.visible=!0,this.castShadow=!1,this.receiveShadow=!1,this.frustumCulled=!0,this.renderOrder=0,this.animations=[],this.customDepthMaterial=void 0,this.customDistanceMaterial=void 0,this.static=!1,this.userData={},this.pivot=null}onBeforeShadow(){}onAfterShadow(){}onBeforeRender(){}onAfterRender(){}applyMatrix4(t){this.matrixAutoUpdate&&this.updateMatrix(),this.matrix.premultiply(t),this.matrix.decompose(this.position,this.quaternion,this.scale)}applyQuaternion(t){return this.quaternion.premultiply(t),this}setRotationFromAxisAngle(t,e){this.quaternion.setFromAxisAngle(t,e)}setRotationFromEuler(t){this.quaternion.setFromEuler(t,!0)}setRotationFromMatrix(t){this.quaternion.setFromRotationMatrix(t)}setRotationFromQuaternion(t){this.quaternion.copy(t)}rotateOnAxis(t,e){return Ge.setFromAxisAngle(t,e),this.quaternion.multiply(Ge),this}rotateOnWorldAxis(t,e){return Ge.setFromAxisAngle(t,e),this.quaternion.premultiply(Ge),this}rotateX(t){return this.rotateOnAxis(Zr,t)}rotateY(t){return this.rotateOnAxis(Jr,t)}rotateZ(t){return this.rotateOnAxis(Kr,t)}translateOnAxis(t,e){return Yr.copy(t).applyQuaternion(this.quaternion),this.position.add(Yr.multiplyScalar(e)),this}translateX(t){return this.translateOnAxis(Zr,t)}translateY(t){return this.translateOnAxis(Jr,t)}translateZ(t){return this.translateOnAxis(Kr,t)}localToWorld(t){return this.updateWorldMatrix(!0,!1),t.applyMatrix4(this.matrixWorld)}worldToLocal(t){return this.updateWorldMatrix(!0,!1),t.applyMatrix4(te.copy(this.matrixWorld).invert())}lookAt(t,e,i){t.isVector3?jn.copy(t):jn.set(t,e,i);let s=this.parent;this.updateWorldMatrix(!0,!1),_n.setFromMatrixPosition(this.matrixWorld),this.isCamera||this.isLight?te.lookAt(_n,jn,this.up):te.lookAt(jn,_n,this.up),this.quaternion.setFromRotationMatrix(te),s&&(te.extractRotation(s.matrixWorld),Ge.setFromRotationMatrix(te),this.quaternion.premultiply(Ge.invert()))}add(t){if(arguments.length>1){for(let e=0;e<arguments.length;e++)this.add(arguments[e]);return this}return t===this?(ot("Object3D.add: object can't be added as a child of itself.",t),this):(t&&t.isObject3D?(t.removeFromParent(),t.parent=this,this.children.push(t),t.dispatchEvent(jr),He.child=t,this.dispatchEvent(He),He.child=null):ot("Object3D.add: object not an instance of THREE.Object3D.",t),this)}remove(t){if(arguments.length>1){for(let i=0;i<arguments.length;i++)this.remove(arguments[i]);return this}let e=this.children.indexOf(t);return e!==-1&&(t.parent=null,this.children.splice(e,1),t.dispatchEvent(kc),es.child=t,this.dispatchEvent(es),es.child=null),this}removeFromParent(){let t=this.parent;return t!==null&&t.remove(this),this}clear(){return this.remove(...this.children)}attach(t){return this.updateWorldMatrix(!0,!1),te.copy(this.matrixWorld).invert(),t.parent!==null&&(t.parent.updateWorldMatrix(!0,!1),te.multiply(t.parent.matrixWorld)),t.applyMatrix4(te),t.removeFromParent(),t.parent=this,this.children.push(t),t.updateWorldMatrix(!1,!0),t.dispatchEvent(jr),He.child=t,this.dispatchEvent(He),He.child=null,this}getObjectById(t){return this.getObjectByProperty("id",t)}getObjectByName(t){return this.getObjectByProperty("name",t)}getObjectByProperty(t,e){if(this[t]===e)return this;for(let i=0,s=this.children.length;i<s;i++){let o=this.children[i].getObjectByProperty(t,e);if(o!==void 0)return o}}getObjectsByProperty(t,e,i=[]){this[t]===e&&i.push(this);let s=this.children;for(let r=0,o=s.length;r<o;r++)s[r].getObjectsByProperty(t,e,i);return i}getWorldPosition(t){return this.updateWorldMatrix(!0,!1),t.setFromMatrixPosition(this.matrixWorld)}getWorldQuaternion(t){return this.updateWorldMatrix(!0,!1),this.matrixWorld.decompose(_n,t,Bc),t}getWorldScale(t){return this.updateWorldMatrix(!0,!1),this.matrixWorld.decompose(_n,zc,t),t}getWorldDirection(t){this.updateWorldMatrix(!0,!1);let e=this.matrixWorld.elements;return t.set(e[8],e[9],e[10]).normalize()}raycast(){}traverse(t){t(this);let e=this.children;for(let i=0,s=e.length;i<s;i++)e[i].traverse(t)}traverseVisible(t){if(this.visible===!1)return;t(this);let e=this.children;for(let i=0,s=e.length;i<s;i++)e[i].traverseVisible(t)}traverseAncestors(t){let e=this.parent;e!==null&&(t(e),e.traverseAncestors(t))}updateMatrix(){this.matrix.compose(this.position,this.quaternion,this.scale);let t=this.pivot;if(t!==null){let e=t.x,i=t.y,s=t.z,r=this.matrix.elements;r[12]+=e-r[0]*e-r[4]*i-r[8]*s,r[13]+=i-r[1]*e-r[5]*i-r[9]*s,r[14]+=s-r[2]*e-r[6]*i-r[10]*s}this.matrixWorldNeedsUpdate=!0}updateMatrixWorld(t){this.matrixAutoUpdate&&this.updateMatrix(),(this.matrixWorldNeedsUpdate||t)&&(this.matrixWorldAutoUpdate===!0&&(this.parent===null?this.matrixWorld.copy(this.matrix):this.matrixWorld.multiplyMatrices(this.parent.matrixWorld,this.matrix)),this.matrixWorldNeedsUpdate=!1,t=!0);let e=this.children;for(let i=0,s=e.length;i<s;i++)e[i].updateMatrixWorld(t)}updateWorldMatrix(t,e,i=!1){let s=this.parent;if(t===!0&&s!==null&&s.updateWorldMatrix(!0,!1),this.matrixAutoUpdate&&this.updateMatrix(),(this.matrixWorldNeedsUpdate||i)&&(this.matrixWorldAutoUpdate===!0&&(this.parent===null?this.matrixWorld.copy(this.matrix):this.matrixWorld.multiplyMatrices(this.parent.matrixWorld,this.matrix)),this.matrixWorldNeedsUpdate=!1,i=!0),e===!0){let r=this.children;for(let o=0,a=r.length;o<a;o++)r[o].updateWorldMatrix(!1,!0,i)}}toJSON(t){let e=t===void 0||typeof t=="string",i={};e&&(t={geometries:{},materials:{},textures:{},images:{},shapes:{},skeletons:{},animations:{},nodes:{}},i.metadata={version:4.7,type:"Object",generator:"Object3D.toJSON"});let s={};s.uuid=this.uuid,s.type=this.type,this.name!==""&&(s.name=this.name),this.castShadow===!0&&(s.castShadow=!0),this.receiveShadow===!0&&(s.receiveShadow=!0),this.visible===!1&&(s.visible=!1),this.frustumCulled===!1&&(s.frustumCulled=!1),this.renderOrder!==0&&(s.renderOrder=this.renderOrder),this.static!==!1&&(s.static=this.static),Object.keys(this.userData).length>0&&(s.userData=this.userData),s.layers=this.layers.mask,s.matrix=this.matrix.toArray(),s.up=this.up.toArray(),this.pivot!==null&&(s.pivot=this.pivot.toArray()),this.matrixAutoUpdate===!1&&(s.matrixAutoUpdate=!1),this.morphTargetDictionary!==void 0&&(s.morphTargetDictionary=Object.assign({},this.morphTargetDictionary)),this.morphTargetInfluences!==void 0&&(s.morphTargetInfluences=this.morphTargetInfluences.slice()),this.isInstancedMesh&&(s.type="InstancedMesh",s.count=this.count,s.instanceMatrix=this.instanceMatrix.toJSON(),this.instanceColor!==null&&(s.instanceColor=this.instanceColor.toJSON())),this.isBatchedMesh&&(s.type="BatchedMesh",s.perObjectFrustumCulled=this.perObjectFrustumCulled,s.sortObjects=this.sortObjects,s.drawRanges=this._drawRanges,s.reservedRanges=this._reservedRanges,s.geometryInfo=this._geometryInfo.map(a=>({...a,boundingBox:a.boundingBox?a.boundingBox.toJSON():void 0,boundingSphere:a.boundingSphere?a.boundingSphere.toJSON():void 0})),s.instanceInfo=this._instanceInfo.map(a=>({...a})),s.availableInstanceIds=this._availableInstanceIds.slice(),s.availableGeometryIds=this._availableGeometryIds.slice(),s.nextIndexStart=this._nextIndexStart,s.nextVertexStart=this._nextVertexStart,s.geometryCount=this._geometryCount,s.maxInstanceCount=this._maxInstanceCount,s.maxVertexCount=this._maxVertexCount,s.maxIndexCount=this._maxIndexCount,s.geometryInitialized=this._geometryInitialized,s.matricesTexture=this._matricesTexture.toJSON(t),s.indirectTexture=this._indirectTexture.toJSON(t),this._colorsTexture!==null&&(s.colorsTexture=this._colorsTexture.toJSON(t)),this.boundingSphere!==null&&(s.boundingSphere=this.boundingSphere.toJSON()),this.boundingBox!==null&&(s.boundingBox=this.boundingBox.toJSON()));function r(a,c){return a[c.uuid]===void 0&&(a[c.uuid]=c.toJSON(t)),c.uuid}if(d(r,"serialize"),this.isScene)this.background&&(this.background.isColor?s.background=this.background.toJSON():this.background.isTexture&&(s.background=this.background.toJSON(t).uuid)),this.environment&&this.environment.isTexture&&this.environment.isRenderTargetTexture!==!0&&(s.environment=this.environment.toJSON(t).uuid);else if(this.isMesh||this.isLine||this.isPoints){s.geometry=r(t.geometries,this.geometry);let a=this.geometry.parameters;if(a!==void 0&&a.shapes!==void 0){let c=a.shapes;if(Array.isArray(c))for(let l=0,u=c.length;l<u;l++){let h=c[l];r(t.shapes,h)}else r(t.shapes,c)}}if(this.isSkinnedMesh&&(s.bindMode=this.bindMode,s.bindMatrix=this.bindMatrix.toArray(),this.skeleton!==void 0&&(r(t.skeletons,this.skeleton),s.skeleton=this.skeleton.uuid)),this.material!==void 0)if(Array.isArray(this.material)){let a=[];for(let c=0,l=this.material.length;c<l;c++)a.push(r(t.materials,this.material[c]));s.material=a}else s.material=r(t.materials,this.material);if(this.children.length>0){s.children=[];for(let a=0;a<this.children.length;a++)s.children.push(this.children[a].toJSON(t).object)}if(this.animations.length>0){s.animations=[];for(let a=0;a<this.animations.length;a++){let c=this.animations[a];s.animations.push(r(t.animations,c))}}if(e){let a=o(t.geometries),c=o(t.materials),l=o(t.textures),u=o(t.images),h=o(t.shapes),f=o(t.skeletons),p=o(t.animations),m=o(t.nodes);a.length>0&&(i.geometries=a),c.length>0&&(i.materials=c),l.length>0&&(i.textures=l),u.length>0&&(i.images=u),h.length>0&&(i.shapes=h),f.length>0&&(i.skeletons=f),p.length>0&&(i.animations=p),m.length>0&&(i.nodes=m)}return i.object=s,i;function o(a){let c=[];for(let l in a){let u=a[l];delete u.metadata,c.push(u)}return c}d(o,"extractFromCache")}clone(t){return new this.constructor().copy(this,t)}copy(t,e=!0){if(this.name=t.name,this.up.copy(t.up),this.position.copy(t.position),this.rotation.order=t.rotation.order,this.quaternion.copy(t.quaternion),this.scale.copy(t.scale),this.pivot=t.pivot!==null?t.pivot.clone():null,this.matrix.copy(t.matrix),this.matrixWorld.copy(t.matrixWorld),this.matrixAutoUpdate=t.matrixAutoUpdate,this.matrixWorldAutoUpdate=t.matrixWorldAutoUpdate,this.matrixWorldNeedsUpdate=t.matrixWorldNeedsUpdate,this.layers.mask=t.layers.mask,this.visible=t.visible,this.castShadow=t.castShadow,this.receiveShadow=t.receiveShadow,this.frustumCulled=t.frustumCulled,this.renderOrder=t.renderOrder,this.static=t.static,this.animations=t.animations.slice(),this.userData=JSON.parse(JSON.stringify(t.userData)),e===!0)for(let i=0;i<t.children.length;i++){let s=t.children[i];this.add(s.clone())}return this}};we.DEFAULT_UP=new k(0,1,0);we.DEFAULT_MATRIX_AUTO_UPDATE=!0;we.DEFAULT_MATRIX_WORLD_AUTO_UPDATE=!0;var xo={aliceblue:15792383,antiquewhite:16444375,aqua:65535,aquamarine:8388564,azure:15794175,beige:16119260,bisque:16770244,black:0,blanchedalmond:16772045,blue:255,blueviolet:9055202,brown:10824234,burlywood:14596231,cadetblue:6266528,chartreuse:8388352,chocolate:13789470,coral:16744272,cornflowerblue:6591981,cornsilk:16775388,crimson:14423100,cyan:65535,darkblue:139,darkcyan:35723,darkgoldenrod:12092939,darkgray:11119017,darkgreen:25600,darkgrey:11119017,darkkhaki:12433259,darkmagenta:9109643,darkolivegreen:5597999,darkorange:16747520,darkorchid:10040012,darkred:9109504,darksalmon:15308410,darkseagreen:9419919,darkslateblue:4734347,darkslategray:3100495,darkslategrey:3100495,darkturquoise:52945,darkviolet:9699539,deeppink:16716947,deepskyblue:49151,dimgray:6908265,dimgrey:6908265,dodgerblue:2003199,firebrick:11674146,floralwhite:16775920,forestgreen:2263842,fuchsia:16711935,gainsboro:14474460,ghostwhite:16316671,gold:16766720,goldenrod:14329120,gray:8421504,green:32768,greenyellow:11403055,grey:8421504,honeydew:15794160,hotpink:16738740,indianred:13458524,indigo:4915330,ivory:16777200,khaki:15787660,lavender:15132410,lavenderblush:16773365,lawngreen:8190976,lemonchiffon:16775885,lightblue:11393254,lightcoral:15761536,lightcyan:14745599,lightgoldenrodyellow:16448210,lightgray:13882323,lightgreen:9498256,lightgrey:13882323,lightpink:16758465,lightsalmon:16752762,lightseagreen:2142890,lightskyblue:8900346,lightslategray:7833753,lightslategrey:7833753,lightsteelblue:11584734,lightyellow:16777184,lime:65280,limegreen:3329330,linen:16445670,magenta:16711935,maroon:8388608,mediumaquamarine:6737322,mediumblue:205,mediumorchid:12211667,mediumpurple:9662683,mediumseagreen:3978097,mediumslateblue:8087790,mediumspringgreen:64154,mediumturquoise:4772300,mediumvioletred:13047173,midnightblue:1644912,mintcream:16121850,mistyrose:16770273,moccasin:16770229,navajowhite:16768685,navy:128,oldlace:16643558,olive:8421376,olivedrab:7048739,orange:16753920,orangered:16729344,orchid:14315734,palegoldenrod:15657130,palegreen:10025880,paleturquoise:11529966,palevioletred:14381203,papayawhip:16773077,peachpuff:16767673,peru:13468991,pink:16761035,plum:14524637,powderblue:11591910,purple:8388736,rebeccapurple:6697881,red:16711680,rosybrown:12357519,royalblue:4286945,saddlebrown:9127187,salmon:16416882,sandybrown:16032864,seagreen:3050327,seashell:16774638,sienna:10506797,silver:12632256,skyblue:8900331,slateblue:6970061,slategray:7372944,slategrey:7372944,snow:16775930,springgreen:65407,steelblue:4620980,tan:13808780,teal:32896,thistle:14204888,tomato:16737095,turquoise:4251856,violet:15631086,wheat:16113331,white:16777215,whitesmoke:16119285,yellow:16776960,yellowgreen:10145074},le={h:0,s:0,l:0},Qn={h:0,s:0,l:0};function ns(n,t,e){return e<0&&(e+=1),e>1&&(e-=1),e<1/6?n+(t-n)*6*e:e<1/2?t:e<2/3?n+(t-n)*6*(2/3-e):n}d(ns,"hue2rgb");var yt=class{static{d(this,"Color")}constructor(t,e,i){return this.isColor=!0,this.r=1,this.g=1,this.b=1,this.set(t,e,i)}set(t,e,i){if(e===void 0&&i===void 0){let s=t;s&&s.isColor?this.copy(s):typeof s=="number"?this.setHex(s):typeof s=="string"&&this.setStyle(s)}else this.setRGB(t,e,i);return this}setScalar(t){return this.r=t,this.g=t,this.b=t,this}setHex(t,e=Gt){return t=Math.floor(t),this.r=(t>>16&255)/255,this.g=(t>>8&255)/255,this.b=(t&255)/255,Vt.colorSpaceToWorking(this,e),this}setRGB(t,e,i,s=Vt.workingColorSpace){return this.r=t,this.g=e,this.b=i,Vt.colorSpaceToWorking(this,s),this}setHSL(t,e,i,s=Vt.workingColorSpace){if(t=Pc(t,1),e=K(e,0,1),i=K(i,0,1),e===0)this.r=this.g=this.b=i;else{let r=i<=.5?i*(1+e):i+e-i*e,o=2*i-r;this.r=ns(o,r,t+1/3),this.g=ns(o,r,t),this.b=ns(o,r,t-1/3)}return Vt.colorSpaceToWorking(this,s),this}setStyle(t,e=Gt){function i(r){r!==void 0&&parseFloat(r)<1&&gt("Color: Alpha component of "+t+" will be ignored.")}d(i,"handleAlpha");let s;if(s=/^(\w+)\(([^\)]*)\)/.exec(t)){let r,o=s[1],a=s[2];switch(o){case"rgb":case"rgba":if(r=/^\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(a))return i(r[4]),this.setRGB(Math.min(255,parseInt(r[1],10))/255,Math.min(255,parseInt(r[2],10))/255,Math.min(255,parseInt(r[3],10))/255,e);if(r=/^\s*(\d+)\%\s*,\s*(\d+)\%\s*,\s*(\d+)\%\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(a))return i(r[4]),this.setRGB(Math.min(100,parseInt(r[1],10))/100,Math.min(100,parseInt(r[2],10))/100,Math.min(100,parseInt(r[3],10))/100,e);break;case"hsl":case"hsla":if(r=/^\s*(\d*\.?\d+)\s*,\s*(\d*\.?\d+)\%\s*,\s*(\d*\.?\d+)\%\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(a))return i(r[4]),this.setHSL(parseFloat(r[1])/360,parseFloat(r[2])/100,parseFloat(r[3])/100,e);break;default:gt("Color: Unknown color model "+t)}}else if(s=/^\#([A-Fa-f\d]+)$/.exec(t)){let r=s[1],o=r.length;if(o===3)return this.setRGB(parseInt(r.charAt(0),16)/15,parseInt(r.charAt(1),16)/15,parseInt(r.charAt(2),16)/15,e);if(o===6)return this.setHex(parseInt(r,16),e);gt("Color: Invalid hex color "+t)}else if(t&&t.length>0)return this.setColorName(t,e);return this}setColorName(t,e=Gt){let i=xo[t.toLowerCase()];return i!==void 0?this.setHex(i,e):gt("Color: Unknown color "+t),this}clone(){return new this.constructor(this.r,this.g,this.b)}copy(t){return this.r=t.r,this.g=t.g,this.b=t.b,this}copySRGBToLinear(t){return this.r=ne(t.r),this.g=ne(t.g),this.b=ne(t.b),this}copyLinearToSRGB(t){return this.r=Ze(t.r),this.g=Ze(t.g),this.b=Ze(t.b),this}convertSRGBToLinear(){return this.copySRGBToLinear(this),this}convertLinearToSRGB(){return this.copyLinearToSRGB(this),this}getHex(t=Gt){return Vt.workingToColorSpace(St.copy(this),t),Math.round(K(St.r*255,0,255))*65536+Math.round(K(St.g*255,0,255))*256+Math.round(K(St.b*255,0,255))}getHexString(t=Gt){return("000000"+this.getHex(t).toString(16)).slice(-6)}getHSL(t,e=Vt.workingColorSpace){Vt.workingToColorSpace(St.copy(this),e);let i=St.r,s=St.g,r=St.b,o=Math.max(i,s,r),a=Math.min(i,s,r),c,l,u=(a+o)/2;if(a===o)c=0,l=0;else{let h=o-a;switch(l=u<=.5?h/(o+a):h/(2-o-a),o){case i:c=(s-r)/h+(s<r?6:0);break;case s:c=(r-i)/h+2;break;case r:c=(i-s)/h+4;break}c/=6}return t.h=c,t.s=l,t.l=u,t}getRGB(t,e=Vt.workingColorSpace){return Vt.workingToColorSpace(St.copy(this),e),t.r=St.r,t.g=St.g,t.b=St.b,t}getStyle(t=Gt){Vt.workingToColorSpace(St.copy(this),t);let e=St.r,i=St.g,s=St.b;return t!==Gt?`color(${t} ${e.toFixed(3)} ${i.toFixed(3)} ${s.toFixed(3)})`:`rgb(${Math.round(e*255)},${Math.round(i*255)},${Math.round(s*255)})`}offsetHSL(t,e,i){return this.getHSL(le),this.setHSL(le.h+t,le.s+e,le.l+i)}add(t){return this.r+=t.r,this.g+=t.g,this.b+=t.b,this}addColors(t,e){return this.r=t.r+e.r,this.g=t.g+e.g,this.b=t.b+e.b,this}addScalar(t){return this.r+=t,this.g+=t,this.b+=t,this}sub(t){return this.r=Math.max(0,this.r-t.r),this.g=Math.max(0,this.g-t.g),this.b=Math.max(0,this.b-t.b),this}multiply(t){return this.r*=t.r,this.g*=t.g,this.b*=t.b,this}multiplyScalar(t){return this.r*=t,this.g*=t,this.b*=t,this}lerp(t,e){return this.r+=(t.r-this.r)*e,this.g+=(t.g-this.g)*e,this.b+=(t.b-this.b)*e,this}lerpColors(t,e,i){return this.r=t.r+(e.r-t.r)*i,this.g=t.g+(e.g-t.g)*i,this.b=t.b+(e.b-t.b)*i,this}lerpHSL(t,e){this.getHSL(le),t.getHSL(Qn);let i=Ji(le.h,Qn.h,e),s=Ji(le.s,Qn.s,e),r=Ji(le.l,Qn.l,e);return this.setHSL(i,s,r),this}setFromVector3(t){return this.r=t.x,this.g=t.y,this.b=t.z,this}applyMatrix3(t){let e=this.r,i=this.g,s=this.b,r=t.elements;return this.r=r[0]*e+r[3]*i+r[6]*s,this.g=r[1]*e+r[4]*i+r[7]*s,this.b=r[2]*e+r[5]*i+r[8]*s,this}equals(t){return t.r===this.r&&t.g===this.g&&t.b===this.b}fromArray(t,e=0){return this.r=t[e],this.g=t[e+1],this.b=t[e+2],this}toArray(t=[],e=0){return t[e]=this.r,t[e+1]=this.g,t[e+2]=this.b,t}fromBufferAttribute(t,e){return this.r=t.getX(e),this.g=t.getY(e),this.b=t.getZ(e),this}toJSON(){return this.getHex()}*[Symbol.iterator](){yield this.r,yield this.g,yield this.b}},St=new yt;yt.NAMES=xo;var fe=class{static{d(this,"Box3")}constructor(t=new k(1/0,1/0,1/0),e=new k(-1/0,-1/0,-1/0)){this.isBox3=!0,this.min=t,this.max=e}set(t,e){return this.min.copy(t),this.max.copy(e),this}setFromArray(t){this.makeEmpty();for(let e=0,i=t.length;e<i;e+=3)this.expandByPoint($t.fromArray(t,e));return this}setFromBufferAttribute(t){this.makeEmpty();for(let e=0,i=t.count;e<i;e++)this.expandByPoint($t.fromBufferAttribute(t,e));return this}setFromPoints(t){this.makeEmpty();for(let e=0,i=t.length;e<i;e++)this.expandByPoint(t[e]);return this}setFromCenterAndSize(t,e){let i=$t.copy(e).multiplyScalar(.5);return this.min.copy(t).sub(i),this.max.copy(t).add(i),this}setFromObject(t,e=!1){return this.makeEmpty(),this.expandByObject(t,e)}clone(){return new this.constructor().copy(this)}copy(t){return this.min.copy(t.min),this.max.copy(t.max),this}makeEmpty(){return this.min.x=this.min.y=this.min.z=1/0,this.max.x=this.max.y=this.max.z=-1/0,this}isEmpty(){return this.max.x<this.min.x||this.max.y<this.min.y||this.max.z<this.min.z}getCenter(t){return this.isEmpty()?t.set(0,0,0):t.addVectors(this.min,this.max).multiplyScalar(.5)}getSize(t){return this.isEmpty()?t.set(0,0,0):t.subVectors(this.max,this.min)}expandByPoint(t){return this.min.min(t),this.max.max(t),this}expandByVector(t){return this.min.sub(t),this.max.add(t),this}expandByScalar(t){return this.min.addScalar(-t),this.max.addScalar(t),this}expandByObject(t,e=!1){t.updateWorldMatrix(!1,!1);let i=t.geometry;if(i!==void 0){let r=i.getAttribute("position");if(e===!0&&r!==void 0&&t.isInstancedMesh!==!0)for(let o=0,a=r.count;o<a;o++)t.isMesh===!0?t.getVertexPosition(o,$t):$t.fromBufferAttribute(r,o),$t.applyMatrix4(t.matrixWorld),this.expandByPoint($t);else t.boundingBox!==void 0?(t.boundingBox===null&&t.computeBoundingBox(),ti.copy(t.boundingBox)):(i.boundingBox===null&&i.computeBoundingBox(),ti.copy(i.boundingBox)),ti.applyMatrix4(t.matrixWorld),this.union(ti)}let s=t.children;for(let r=0,o=s.length;r<o;r++)this.expandByObject(s[r],e);return this}containsPoint(t){return t.x>=this.min.x&&t.x<=this.max.x&&t.y>=this.min.y&&t.y<=this.max.y&&t.z>=this.min.z&&t.z<=this.max.z}containsBox(t){return this.min.x<=t.min.x&&t.max.x<=this.max.x&&this.min.y<=t.min.y&&t.max.y<=this.max.y&&this.min.z<=t.min.z&&t.max.z<=this.max.z}getParameter(t,e){return e.set((t.x-this.min.x)/(this.max.x-this.min.x),(t.y-this.min.y)/(this.max.y-this.min.y),(t.z-this.min.z)/(this.max.z-this.min.z))}intersectsBox(t){return t.max.x>=this.min.x&&t.min.x<=this.max.x&&t.max.y>=this.min.y&&t.min.y<=this.max.y&&t.max.z>=this.min.z&&t.min.z<=this.max.z}intersectsSphere(t){return this.clampPoint(t.center,$t),$t.distanceToSquared(t.center)<=t.radius*t.radius}intersectsPlane(t){let e,i;return t.normal.x>0?(e=t.normal.x*this.min.x,i=t.normal.x*this.max.x):(e=t.normal.x*this.max.x,i=t.normal.x*this.min.x),t.normal.y>0?(e+=t.normal.y*this.min.y,i+=t.normal.y*this.max.y):(e+=t.normal.y*this.max.y,i+=t.normal.y*this.min.y),t.normal.z>0?(e+=t.normal.z*this.min.z,i+=t.normal.z*this.max.z):(e+=t.normal.z*this.max.z,i+=t.normal.z*this.min.z),e<=-t.constant&&i>=-t.constant}intersectsTriangle(t){if(this.isEmpty())return!1;this.getCenter(yn),ei.subVectors(this.max,yn),We.subVectors(t.a,yn),Xe.subVectors(t.b,yn),qe.subVectors(t.c,yn),ue.subVectors(Xe,We),he.subVectors(qe,Xe),Se.subVectors(We,qe);let e=[0,-ue.z,ue.y,0,-he.z,he.y,0,-Se.z,Se.y,ue.z,0,-ue.x,he.z,0,-he.x,Se.z,0,-Se.x,-ue.y,ue.x,0,-he.y,he.x,0,-Se.y,Se.x,0];return!is(e,We,Xe,qe,ei)||(e=[1,0,0,0,1,0,0,0,1],!is(e,We,Xe,qe,ei))?!1:(ni.crossVectors(ue,he),e=[ni.x,ni.y,ni.z],is(e,We,Xe,qe,ei))}clampPoint(t,e){return e.copy(t).clamp(this.min,this.max)}distanceToPoint(t){return this.clampPoint(t,$t).distanceTo(t)}getBoundingSphere(t){return this.isEmpty()?t.makeEmpty():(this.getCenter(t.center),t.radius=this.getSize($t).length()*.5),t}intersect(t){return this.min.max(t.min),this.max.min(t.max),this.isEmpty()&&this.makeEmpty(),this}union(t){return this.min.min(t.min),this.max.max(t.max),this}applyMatrix4(t){return this.isEmpty()?this:(ee[0].set(this.min.x,this.min.y,this.min.z).applyMatrix4(t),ee[1].set(this.min.x,this.min.y,this.max.z).applyMatrix4(t),ee[2].set(this.min.x,this.max.y,this.min.z).applyMatrix4(t),ee[3].set(this.min.x,this.max.y,this.max.z).applyMatrix4(t),ee[4].set(this.max.x,this.min.y,this.min.z).applyMatrix4(t),ee[5].set(this.max.x,this.min.y,this.max.z).applyMatrix4(t),ee[6].set(this.max.x,this.max.y,this.min.z).applyMatrix4(t),ee[7].set(this.max.x,this.max.y,this.max.z).applyMatrix4(t),this.setFromPoints(ee),this)}translate(t){return this.min.add(t),this.max.add(t),this}equals(t){return t.min.equals(this.min)&&t.max.equals(this.max)}toJSON(){return{min:this.min.toArray(),max:this.max.toArray()}}fromJSON(t){return this.min.fromArray(t.min),this.max.fromArray(t.max),this}},ee=[new k,new k,new k,new k,new k,new k,new k,new k],$t=new k,ti=new fe,We=new k,Xe=new k,qe=new k,ue=new k,he=new k,Se=new k,yn=new k,ei=new k,ni=new k,Ae=new k;function is(n,t,e,i,s){for(let r=0,o=n.length-3;r<=o;r+=3){Ae.fromArray(n,r);let a=s.x*Math.abs(Ae.x)+s.y*Math.abs(Ae.y)+s.z*Math.abs(Ae.z),c=t.dot(Ae),l=e.dot(Ae),u=i.dot(Ae);if(Math.max(-Math.max(c,l,u),Math.min(c,l,u))>a)return!1}return!0}d(is,"satForAxes");var ut=new k,ii=new xt,Vc=0,Ut=class extends Te{static{d(this,"BufferAttribute")}constructor(t,e,i=!1){if(super(),Array.isArray(t))throw new TypeError("THREE.BufferAttribute: array should be a Typed Array.");this.isBufferAttribute=!0,Object.defineProperty(this,"id",{value:Vc++}),this.name="",this.array=t,this.itemSize=e,this.count=t!==void 0?t.length/e:0,this.normalized=i,this.usage=bs,this.updateRanges=[],this.gpuType=po,this.version=0}onUploadCallback(){}set needsUpdate(t){t===!0&&this.version++}setUsage(t){return this.usage=t,this}addUpdateRange(t,e){this.updateRanges.push({start:t,count:e})}clearUpdateRanges(){this.updateRanges.length=0}copy(t){return this.name=t.name,this.array=new t.array.constructor(t.array),this.itemSize=t.itemSize,this.count=t.count,this.normalized=t.normalized,this.usage=t.usage,this.gpuType=t.gpuType,this}copyAt(t,e,i){t*=this.itemSize,i*=e.itemSize;for(let s=0,r=this.itemSize;s<r;s++)this.array[t+s]=e.array[i+s];return this}copyArray(t){return this.array.set(t),this}applyMatrix3(t){if(this.itemSize===2)for(let e=0,i=this.count;e<i;e++)ii.fromBufferAttribute(this,e),ii.applyMatrix3(t),this.setXY(e,ii.x,ii.y);else if(this.itemSize===3)for(let e=0,i=this.count;e<i;e++)ut.fromBufferAttribute(this,e),ut.applyMatrix3(t),this.setXYZ(e,ut.x,ut.y,ut.z);return this}applyMatrix4(t){for(let e=0,i=this.count;e<i;e++)ut.fromBufferAttribute(this,e),ut.applyMatrix4(t),this.setXYZ(e,ut.x,ut.y,ut.z);return this}applyNormalMatrix(t){for(let e=0,i=this.count;e<i;e++)ut.fromBufferAttribute(this,e),ut.applyNormalMatrix(t),this.setXYZ(e,ut.x,ut.y,ut.z);return this}transformDirection(t){for(let e=0,i=this.count;e<i;e++)ut.fromBufferAttribute(this,e),ut.transformDirection(t),this.setXYZ(e,ut.x,ut.y,ut.z);return this}set(t,e=0){return this.array.set(t,e),this}getComponent(t,e){let i=this.array[t*this.itemSize+e];return this.normalized&&(i=xn(i,this.array)),i}setComponent(t,e,i){return this.normalized&&(i=Et(i,this.array)),this.array[t*this.itemSize+e]=i,this}getX(t){let e=this.array[t*this.itemSize];return this.normalized&&(e=xn(e,this.array)),e}setX(t,e){return this.normalized&&(e=Et(e,this.array)),this.array[t*this.itemSize]=e,this}getY(t){let e=this.array[t*this.itemSize+1];return this.normalized&&(e=xn(e,this.array)),e}setY(t,e){return this.normalized&&(e=Et(e,this.array)),this.array[t*this.itemSize+1]=e,this}getZ(t){let e=this.array[t*this.itemSize+2];return this.normalized&&(e=xn(e,this.array)),e}setZ(t,e){return this.normalized&&(e=Et(e,this.array)),this.array[t*this.itemSize+2]=e,this}getW(t){let e=this.array[t*this.itemSize+3];return this.normalized&&(e=xn(e,this.array)),e}setW(t,e){return this.normalized&&(e=Et(e,this.array)),this.array[t*this.itemSize+3]=e,this}setXY(t,e,i){return t*=this.itemSize,this.normalized&&(e=Et(e,this.array),i=Et(i,this.array)),this.array[t+0]=e,this.array[t+1]=i,this}setXYZ(t,e,i,s){return t*=this.itemSize,this.normalized&&(e=Et(e,this.array),i=Et(i,this.array),s=Et(s,this.array)),this.array[t+0]=e,this.array[t+1]=i,this.array[t+2]=s,this}setXYZW(t,e,i,s,r){return t*=this.itemSize,this.normalized&&(e=Et(e,this.array),i=Et(i,this.array),s=Et(s,this.array),r=Et(r,this.array)),this.array[t+0]=e,this.array[t+1]=i,this.array[t+2]=s,this.array[t+3]=r,this}onUpload(t){return this.onUploadCallback=t,this}clone(){return new this.constructor(this.array,this.itemSize).copy(this)}toJSON(){let t={itemSize:this.itemSize,type:this.array.constructor.name,array:Array.from(this.array),normalized:this.normalized};return this.name!==""&&(t.name=this.name),this.usage!==bs&&(t.usage=this.usage),t}dispose(){this.dispatchEvent({type:"dispose"})}};var pi=class extends Ut{static{d(this,"Uint16BufferAttribute")}constructor(t,e,i){super(new Uint16Array(t),e,i)}};var mi=class extends Ut{static{d(this,"Uint32BufferAttribute")}constructor(t,e,i){super(new Uint32Array(t),e,i)}};var de=class extends Ut{static{d(this,"Float32BufferAttribute")}constructor(t,e,i){super(new Float32Array(t),e,i)}},Gc=new fe,vn=new k,ss=new k,gi=class{static{d(this,"Sphere")}constructor(t=new k,e=-1){this.isSphere=!0,this.center=t,this.radius=e}set(t,e){return this.center.copy(t),this.radius=e,this}setFromPoints(t,e){let i=this.center;e!==void 0?i.copy(e):Gc.setFromPoints(t).getCenter(i);let s=0;for(let r=0,o=t.length;r<o;r++)s=Math.max(s,i.distanceToSquared(t[r]));return this.radius=Math.sqrt(s),this}copy(t){return this.center.copy(t.center),this.radius=t.radius,this}isEmpty(){return this.radius<0}makeEmpty(){return this.center.set(0,0,0),this.radius=-1,this}containsPoint(t){return t.distanceToSquared(this.center)<=this.radius*this.radius}distanceToPoint(t){return t.distanceTo(this.center)-this.radius}intersectsSphere(t){let e=this.radius+t.radius;return t.center.distanceToSquared(this.center)<=e*e}intersectsBox(t){return t.intersectsSphere(this)}intersectsPlane(t){return Math.abs(t.distanceToPoint(this.center))<=this.radius}clampPoint(t,e){let i=this.center.distanceToSquared(t);return e.copy(t),i>this.radius*this.radius&&(e.sub(this.center).normalize(),e.multiplyScalar(this.radius).add(this.center)),e}getBoundingBox(t){return this.isEmpty()?(t.makeEmpty(),t):(t.set(this.center,this.center),t.expandByScalar(this.radius),t)}applyMatrix4(t){return this.center.applyMatrix4(t),this.radius=this.radius*t.getMaxScaleOnAxis(),this}translate(t){return this.center.add(t),this}expandByPoint(t){if(this.isEmpty())return this.center.copy(t),this.radius=0,this;vn.subVectors(t,this.center);let e=vn.lengthSq();if(e>this.radius*this.radius){let i=Math.sqrt(e),s=(i-this.radius)*.5;this.center.addScaledVector(vn,s/i),this.radius+=s}return this}union(t){return t.isEmpty()?this:this.isEmpty()?(this.copy(t),this):(this.center.equals(t.center)===!0?this.radius=Math.max(this.radius,t.radius):(ss.subVectors(t.center,this.center).setLength(t.radius),this.expandByPoint(vn.copy(t.center).add(ss)),this.expandByPoint(vn.copy(t.center).sub(ss))),this)}equals(t){return t.center.equals(this.center)&&t.radius===this.radius}clone(){return new this.constructor().copy(this)}toJSON(){return{radius:this.radius,center:this.center.toArray()}}fromJSON(t){return this.radius=t.radius,this.center.fromArray(t.center),this}},Hc=0,kt=new _t,rs=new we,$e=new k,Dt=new fe,Mn=new fe,mt=new k,Ke=class n extends Te{static{d(this,"BufferGeometry")}constructor(){super(),this.isBufferGeometry=!0,Object.defineProperty(this,"id",{value:Hc++}),this.uuid=Ei(),this.name="",this.type="BufferGeometry",this.index=null,this.indirect=null,this.indirectOffset=0,this.attributes={},this.morphAttributes={},this.morphTargetsRelative=!1,this.groups=[],this.boundingBox=null,this.boundingSphere=null,this.drawRange={start:0,count:1/0},this.userData={},this._transformed=!1}getIndex(){return this.index}setIndex(t){return Array.isArray(t)?this.index=new(Ec(t)?mi:pi)(t,1):this.index=t,this}setIndirect(t,e=0){return this.indirect=t,this.indirectOffset=e,this}getIndirect(){return this.indirect}getAttribute(t){return this.attributes[t]}setAttribute(t,e){return this.attributes[t]=e,this}deleteAttribute(t){return delete this.attributes[t],this}hasAttribute(t){return this.attributes[t]!==void 0}addGroup(t,e,i=0){this.groups.push({start:t,count:e,materialIndex:i})}clearGroups(){this.groups=[]}setDrawRange(t,e){this.drawRange.start=t,this.drawRange.count=e}applyMatrix4(t){let e=this.attributes.position;e!==void 0&&(e.applyMatrix4(t),e.needsUpdate=!0);let i=this.attributes.normal;if(i!==void 0){let r=new Y().getNormalMatrix(t);i.applyNormalMatrix(r),i.needsUpdate=!0}let s=this.attributes.tangent;return s!==void 0&&(s.transformDirection(t),s.needsUpdate=!0),this.boundingBox!==null&&this.computeBoundingBox(),this.boundingSphere!==null&&this.computeBoundingSphere(),this._transformed=!0,this}applyQuaternion(t){return kt.makeRotationFromQuaternion(t),this.applyMatrix4(kt),this}rotateX(t){return kt.makeRotationX(t),this.applyMatrix4(kt),this}rotateY(t){return kt.makeRotationY(t),this.applyMatrix4(kt),this}rotateZ(t){return kt.makeRotationZ(t),this.applyMatrix4(kt),this}translate(t,e,i){return kt.makeTranslation(t,e,i),this.applyMatrix4(kt),this}scale(t,e,i){return kt.makeScale(t,e,i),this.applyMatrix4(kt),this}lookAt(t){return rs.lookAt(t),rs.updateMatrix(),this.applyMatrix4(rs.matrix),this}center(){return this.computeBoundingBox(),this.boundingBox.getCenter($e).negate(),this.translate($e.x,$e.y,$e.z),this}setFromPoints(t){let e=this.getAttribute("position");if(e===void 0){let i=[];for(let s=0,r=t.length;s<r;s++){let o=t[s];i.push(o.x,o.y,o.z||0)}this.setAttribute("position",new de(i,3))}else{let i=Math.min(t.length,e.count);for(let s=0;s<i;s++){let r=t[s];e.setXYZ(s,r.x,r.y,r.z||0)}t.length>e.count&&gt("BufferGeometry: Buffer size too small for points data. Use .dispose() and create a new geometry."),e.needsUpdate=!0}return this}computeBoundingBox(){this.boundingBox===null&&(this.boundingBox=new fe);let t=this.attributes.position,e=this.morphAttributes.position;if(t&&t.isGLBufferAttribute){ot("BufferGeometry.computeBoundingBox(): GLBufferAttribute requires a manual bounding box.",this),this.boundingBox.set(new k(-1/0,-1/0,-1/0),new k(1/0,1/0,1/0));return}if(t!==void 0){if(this.boundingBox.setFromBufferAttribute(t),e)for(let i=0,s=e.length;i<s;i++){let r=e[i];Dt.setFromBufferAttribute(r),this.morphTargetsRelative?(mt.addVectors(this.boundingBox.min,Dt.min),this.boundingBox.expandByPoint(mt),mt.addVectors(this.boundingBox.max,Dt.max),this.boundingBox.expandByPoint(mt)):(this.boundingBox.expandByPoint(Dt.min),this.boundingBox.expandByPoint(Dt.max))}}else this.boundingBox.makeEmpty();(isNaN(this.boundingBox.min.x)||isNaN(this.boundingBox.min.y)||isNaN(this.boundingBox.min.z))&&ot('BufferGeometry.computeBoundingBox(): Computed min/max have NaN values. The "position" attribute is likely to have NaN values.',this)}computeBoundingSphere(){this.boundingSphere===null&&(this.boundingSphere=new gi);let t=this.attributes.position,e=this.morphAttributes.position;if(t&&t.isGLBufferAttribute){ot("BufferGeometry.computeBoundingSphere(): GLBufferAttribute requires a manual bounding sphere.",this),this.boundingSphere.set(new k,1/0);return}if(t){let i=this.boundingSphere.center;if(Dt.setFromBufferAttribute(t),e)for(let r=0,o=e.length;r<o;r++){let a=e[r];Mn.setFromBufferAttribute(a),this.morphTargetsRelative?(mt.addVectors(Dt.min,Mn.min),Dt.expandByPoint(mt),mt.addVectors(Dt.max,Mn.max),Dt.expandByPoint(mt)):(Dt.expandByPoint(Mn.min),Dt.expandByPoint(Mn.max))}Dt.getCenter(i);let s=0;for(let r=0,o=t.count;r<o;r++)mt.fromBufferAttribute(t,r),s=Math.max(s,i.distanceToSquared(mt));if(e)for(let r=0,o=e.length;r<o;r++){let a=e[r],c=this.morphTargetsRelative;for(let l=0,u=a.count;l<u;l++)mt.fromBufferAttribute(a,l),c&&($e.fromBufferAttribute(t,l),mt.add($e)),s=Math.max(s,i.distanceToSquared(mt))}this.boundingSphere.radius=Math.sqrt(s),isNaN(this.boundingSphere.radius)&&ot('BufferGeometry.computeBoundingSphere(): Computed radius is NaN. The "position" attribute is likely to have NaN values.',this)}}computeTangents(){let t=this.index,e=this.attributes;if(t===null||e.position===void 0||e.normal===void 0||e.uv===void 0){ot("BufferGeometry: .computeTangents() failed. Missing required attributes (index, position, normal or uv)");return}let i=e.position,s=e.normal,r=e.uv,o=this.getAttribute("tangent");(o===void 0||o.count!==i.count)&&(o=new Ut(new Float32Array(4*i.count),4),this.setAttribute("tangent",o));let a=[],c=[];for(let A=0;A<i.count;A++)a[A]=new k,c[A]=new k;let l=new k,u=new k,h=new k,f=new xt,p=new xt,m=new xt,g=new k,x=new k;function _(A,I,C){l.fromBufferAttribute(i,A),u.fromBufferAttribute(i,I),h.fromBufferAttribute(i,C),f.fromBufferAttribute(r,A),p.fromBufferAttribute(r,I),m.fromBufferAttribute(r,C),u.sub(l),h.sub(l),p.sub(f),m.sub(f);let N=1/(p.x*m.y-m.x*p.y);isFinite(N)&&(g.copy(u).multiplyScalar(m.y).addScaledVector(h,-p.y).multiplyScalar(N),x.copy(h).multiplyScalar(p.x).addScaledVector(u,-m.x).multiplyScalar(N),a[A].add(g),a[I].add(g),a[C].add(g),c[A].add(x),c[I].add(x),c[C].add(x))}d(_,"handleTriangle");let v=this.groups;v.length===0&&(v=[{start:0,count:t.count}]);for(let A=0,I=v.length;A<I;++A){let C=v[A],N=C.start,R=C.count;for(let w=N,P=N+R;w<P;w+=3)_(t.getX(w+0),t.getX(w+1),t.getX(w+2))}let y=new k,b=new k,T=new k,S=new k;function M(A){T.fromBufferAttribute(s,A),S.copy(T);let I=a[A];y.copy(I),y.sub(T.multiplyScalar(T.dot(I))).normalize(),b.crossVectors(S,I);let N=b.dot(c[A])<0?-1:1;o.setXYZW(A,y.x,y.y,y.z,N)}d(M,"handleVertex");for(let A=0,I=v.length;A<I;++A){let C=v[A],N=C.start,R=C.count;for(let w=N,P=N+R;w<P;w+=3)M(t.getX(w+0)),M(t.getX(w+1)),M(t.getX(w+2))}this._transformed=!0}computeVertexNormals(){let t=this.index,e=this.getAttribute("position");if(e!==void 0){let i=this.getAttribute("normal");if(i===void 0||i.count!==e.count)i=new Ut(new Float32Array(e.count*3),3),this.setAttribute("normal",i);else for(let f=0,p=i.count;f<p;f++)i.setXYZ(f,0,0,0);let s=new k,r=new k,o=new k,a=new k,c=new k,l=new k,u=new k,h=new k;if(t)for(let f=0,p=t.count;f<p;f+=3){let m=t.getX(f+0),g=t.getX(f+1),x=t.getX(f+2);s.fromBufferAttribute(e,m),r.fromBufferAttribute(e,g),o.fromBufferAttribute(e,x),u.subVectors(o,r),h.subVectors(s,r),u.cross(h),a.fromBufferAttribute(i,m),c.fromBufferAttribute(i,g),l.fromBufferAttribute(i,x),a.add(u),c.add(u),l.add(u),i.setXYZ(m,a.x,a.y,a.z),i.setXYZ(g,c.x,c.y,c.z),i.setXYZ(x,l.x,l.y,l.z)}else for(let f=0,p=e.count;f<p;f+=3)s.fromBufferAttribute(e,f+0),r.fromBufferAttribute(e,f+1),o.fromBufferAttribute(e,f+2),u.subVectors(o,r),h.subVectors(s,r),u.cross(h),i.setXYZ(f+0,u.x,u.y,u.z),i.setXYZ(f+1,u.x,u.y,u.z),i.setXYZ(f+2,u.x,u.y,u.z);this.normalizeNormals(),i.needsUpdate=!0}}normalizeNormals(){let t=this.attributes.normal;for(let e=0,i=t.count;e<i;e++)mt.fromBufferAttribute(t,e),mt.normalize(),t.setXYZ(e,mt.x,mt.y,mt.z)}toNonIndexed(){function t(a,c){let l=a.array,u=a.itemSize,h=a.normalized,f=new l.constructor(c.length*u),p=0,m=0;for(let g=0,x=c.length;g<x;g++){a.isInterleavedBufferAttribute?p=c[g]*a.data.stride+a.offset:p=c[g]*u;for(let _=0;_<u;_++)f[m++]=l[p++]}return new Ut(f,u,h)}if(d(t,"convertBufferAttribute"),this.index===null)return gt("BufferGeometry.toNonIndexed(): BufferGeometry is already non-indexed."),this;let e=new n,i=this.index.array,s=this.attributes;for(let a in s){let c=s[a],l=t(c,i);e.setAttribute(a,l)}let r=this.morphAttributes;for(let a in r){let c=[],l=r[a];for(let u=0,h=l.length;u<h;u++){let f=l[u],p=t(f,i);c.push(p)}e.morphAttributes[a]=c}e.morphTargetsRelative=this.morphTargetsRelative;let o=this.groups;for(let a=0,c=o.length;a<c;a++){let l=o[a];e.addGroup(l.start,l.count,l.materialIndex)}return e}toJSON(){let t={metadata:{version:4.7,type:"BufferGeometry",generator:"BufferGeometry.toJSON"}};if(t.uuid=this.uuid,t.type=this.parameters!==void 0&&this._transformed===!0?"BufferGeometry":this.type,this.name!==""&&(t.name=this.name),Object.keys(this.userData).length>0&&(t.userData=this.userData),this.parameters!==void 0&&this._transformed!==!0){let c=this.parameters;for(let l in c)c[l]!==void 0&&(t[l]=c[l]);return t}t.data={attributes:{}};let e=this.index;e!==null&&(t.data.index={type:e.array.constructor.name,array:Array.prototype.slice.call(e.array)});let i=this.attributes;for(let c in i){let l=i[c];t.data.attributes[c]=l.toJSON(t.data)}let s={},r=!1;for(let c in this.morphAttributes){let l=this.morphAttributes[c],u=[];for(let h=0,f=l.length;h<f;h++){let p=l[h];u.push(p.toJSON(t.data))}u.length>0&&(s[c]=u,r=!0)}r&&(t.data.morphAttributes=s,t.data.morphTargetsRelative=this.morphTargetsRelative);let o=this.groups;o.length>0&&(t.data.groups=JSON.parse(JSON.stringify(o)));let a=this.boundingSphere;return a!==null&&(t.data.boundingSphere=a.toJSON()),t}clone(){return new this.constructor().copy(this)}copy(t){this.index=null,this.attributes={},this.morphAttributes={},this.groups=[],this.boundingBox=null,this.boundingSphere=null;let e={};this.name=t.name;let i=t.index;i!==null&&this.setIndex(i.clone());let s=t.attributes;for(let l in s){let u=s[l];this.setAttribute(l,u.clone(e))}let r=t.morphAttributes;for(let l in r){let u=[],h=r[l];for(let f=0,p=h.length;f<p;f++)u.push(h[f].clone(e));this.morphAttributes[l]=u}this.morphTargetsRelative=t.morphTargetsRelative;let o=t.groups;for(let l=0,u=o.length;l<u;l++){let h=o[l];this.addGroup(h.start,h.count,h.materialIndex)}let a=t.boundingBox;a!==null&&(this.boundingBox=a.clone());let c=t.boundingSphere;return c!==null&&(this.boundingSphere=c.clone()),this.drawRange.start=t.drawRange.start,this.drawRange.count=t.drawRange.count,this.userData=t.userData,this._transformed=t._transformed,this}dispose(){this.dispatchEvent({type:"dispose"})}};function Wc(n,t,e=2){let i=t&&t.length,s=i?t[0]*e:n.length,r=_o(n,0,s,e,!0),o=[];if(!r||r.next===r.prev)return o;let a,c,l;if(i&&(r=Zc(n,t,r,e)),n.length>80*e){a=n[0],c=n[1];let u=a,h=c;for(let f=e;f<s;f+=e){let p=n[f],m=n[f+1];p<a&&(a=p),m<c&&(c=m),p>u&&(u=p),m>h&&(h=m)}l=Math.max(u-a,h-c),l=l!==0?32767/l:0}return En(r,o,e,a,c,l,0),o}d(Wc,"earcut");function _o(n,t,e,i,s){let r;if(s===ol(n,t,e,i)>0)for(let o=t;o<e;o+=i)r=Qr(o/i|0,n[o],n[o+1],r);else for(let o=e-i;o>=t;o-=i)r=Qr(o/i|0,n[o],n[o+1],r);return r&&je(r,r.next)&&(Rn(r),r=r.next),r}d(_o,"linkedList");function Ee(n,t){if(!n)return n;t||(t=n);let e=n,i;do if(i=!1,!e.steiner&&(je(e,e.next)||at(e.prev,e,e.next)===0)){if(Rn(e),e=t=e.prev,e===e.next)break;i=!0}else e=e.next;while(i||e!==t);return t}d(Ee,"filterPoints");function En(n,t,e,i,s,r,o){if(!n)return;!o&&r&&tl(n,i,s,r);let a=n;for(;n.prev!==n.next;){let c=n.prev,l=n.next;if(r?qc(n,i,s,r):Xc(n)){t.push(c.i,n.i,l.i),Rn(n),n=l.next,a=l.next;continue}if(n=l,n===a){o?o===1?(n=$c(Ee(n),t),En(n,t,e,i,s,r,2)):o===2&&Yc(n,t,e,i,s,r):En(Ee(n),t,e,i,s,r,1);break}}}d(En,"earcutLinked");function Xc(n){let t=n.prev,e=n,i=n.next;if(at(t,e,i)>=0)return!1;let s=t.x,r=e.x,o=i.x,a=t.y,c=e.y,l=i.y,u=Math.min(s,r,o),h=Math.min(a,c,l),f=Math.max(s,r,o),p=Math.max(a,c,l),m=i.next;for(;m!==t;){if(m.x>=u&&m.x<=f&&m.y>=h&&m.y<=p&&An(s,a,r,c,o,l,m.x,m.y)&&at(m.prev,m,m.next)>=0)return!1;m=m.next}return!0}d(Xc,"isEar");function qc(n,t,e,i){let s=n.prev,r=n,o=n.next;if(at(s,r,o)>=0)return!1;let a=s.x,c=r.x,l=o.x,u=s.y,h=r.y,f=o.y,p=Math.min(a,c,l),m=Math.min(u,h,f),g=Math.max(a,c,l),x=Math.max(u,h,f),_=ws(p,m,t,e,i),v=ws(g,x,t,e,i),y=n.prevZ,b=n.nextZ;for(;y&&y.z>=_&&b&&b.z<=v;){if(y.x>=p&&y.x<=g&&y.y>=m&&y.y<=x&&y!==s&&y!==o&&An(a,u,c,h,l,f,y.x,y.y)&&at(y.prev,y,y.next)>=0||(y=y.prevZ,b.x>=p&&b.x<=g&&b.y>=m&&b.y<=x&&b!==s&&b!==o&&An(a,u,c,h,l,f,b.x,b.y)&&at(b.prev,b,b.next)>=0))return!1;b=b.nextZ}for(;y&&y.z>=_;){if(y.x>=p&&y.x<=g&&y.y>=m&&y.y<=x&&y!==s&&y!==o&&An(a,u,c,h,l,f,y.x,y.y)&&at(y.prev,y,y.next)>=0)return!1;y=y.prevZ}for(;b&&b.z<=v;){if(b.x>=p&&b.x<=g&&b.y>=m&&b.y<=x&&b!==s&&b!==o&&An(a,u,c,h,l,f,b.x,b.y)&&at(b.prev,b,b.next)>=0)return!1;b=b.nextZ}return!0}d(qc,"isEarHashed");function $c(n,t){let e=n;do{let i=e.prev,s=e.next.next;!je(i,s)&&vo(i,e,e.next,s)&&Cn(i,s)&&Cn(s,i)&&(t.push(i.i,e.i,s.i),Rn(e),Rn(e.next),e=n=s),e=e.next}while(e!==n);return Ee(e)}d($c,"cureLocalIntersections");function Yc(n,t,e,i,s,r){let o=n;do{let a=o.next.next;for(;a!==o.prev;){if(o.i!==a.i&&il(o,a)){let c=Mo(o,a);o=Ee(o,o.next),c=Ee(c,c.next),En(o,t,e,i,s,r,0),En(c,t,e,i,s,r,0);return}a=a.next}o=o.next}while(o!==n)}d(Yc,"splitEarcut");function Zc(n,t,e,i){let s=[];for(let r=0,o=t.length;r<o;r++){let a=t[r]*i,c=r<o-1?t[r+1]*i:n.length,l=_o(n,a,c,i,!1);l===l.next&&(l.steiner=!0),s.push(nl(l))}s.sort(Jc);for(let r=0;r<s.length;r++)e=Kc(s[r],e);return e}d(Zc,"eliminateHoles");function Jc(n,t){let e=n.x-t.x;if(e===0&&(e=n.y-t.y,e===0)){let i=(n.next.y-n.y)/(n.next.x-n.x),s=(t.next.y-t.y)/(t.next.x-t.x);e=i-s}return e}d(Jc,"compareXYSlope");function Kc(n,t){let e=jc(n,t);if(!e)return t;let i=Mo(e,n);return Ee(i,i.next),Ee(e,e.next)}d(Kc,"eliminateHole");function jc(n,t){let e=t,i=n.x,s=n.y,r=-1/0,o;if(je(n,e))return e;do{if(je(n,e.next))return e.next;if(s<=e.y&&s>=e.next.y&&e.next.y!==e.y){let h=e.x+(s-e.y)*(e.next.x-e.x)/(e.next.y-e.y);if(h<=i&&h>r&&(r=h,o=e.x<e.next.x?e:e.next,h===i))return o}e=e.next}while(e!==t);if(!o)return null;let a=o,c=o.x,l=o.y,u=1/0;e=o;do{if(i>=e.x&&e.x>=c&&i!==e.x&&yo(s<l?i:r,s,c,l,s<l?r:i,s,e.x,e.y)){let h=Math.abs(s-e.y)/(i-e.x);Cn(e,n)&&(h<u||h===u&&(e.x>o.x||e.x===o.x&&Qc(o,e)))&&(o=e,u=h)}e=e.next}while(e!==a);return o}d(jc,"findHoleBridge");function Qc(n,t){return at(n.prev,n,t.prev)<0&&at(t.next,n,n.next)<0}d(Qc,"sectorContainsSector");function tl(n,t,e,i){let s=n;do s.z===0&&(s.z=ws(s.x,s.y,t,e,i)),s.prevZ=s.prev,s.nextZ=s.next,s=s.next;while(s!==n);s.prevZ.nextZ=null,s.prevZ=null,el(s)}d(tl,"indexCurve");function el(n){let t,e=1;do{let i=n,s;n=null;let r=null;for(t=0;i;){t++;let o=i,a=0;for(let l=0;l<e&&(a++,o=o.nextZ,!!o);l++);let c=e;for(;a>0||c>0&&o;)a!==0&&(c===0||!o||i.z<=o.z)?(s=i,i=i.nextZ,a--):(s=o,o=o.nextZ,c--),r?r.nextZ=s:n=s,s.prevZ=r,r=s;i=o}r.nextZ=null,e*=2}while(t>1);return n}d(el,"sortLinked");function ws(n,t,e,i,s){return n=(n-e)*s|0,t=(t-i)*s|0,n=(n|n<<8)&16711935,n=(n|n<<4)&252645135,n=(n|n<<2)&858993459,n=(n|n<<1)&1431655765,t=(t|t<<8)&16711935,t=(t|t<<4)&252645135,t=(t|t<<2)&858993459,t=(t|t<<1)&1431655765,n|t<<1}d(ws,"zOrder");function nl(n){let t=n,e=n;do(t.x<e.x||t.x===e.x&&t.y<e.y)&&(e=t),t=t.next;while(t!==n);return e}d(nl,"getLeftmost");function yo(n,t,e,i,s,r,o,a){return(s-o)*(t-a)>=(n-o)*(r-a)&&(n-o)*(i-a)>=(e-o)*(t-a)&&(e-o)*(r-a)>=(s-o)*(i-a)}d(yo,"pointInTriangle");function An(n,t,e,i,s,r,o,a){return!(n===o&&t===a)&&yo(n,t,e,i,s,r,o,a)}d(An,"pointInTriangleExceptFirst");function il(n,t){return n.next.i!==t.i&&n.prev.i!==t.i&&!sl(n,t)&&(Cn(n,t)&&Cn(t,n)&&rl(n,t)&&(at(n.prev,n,t.prev)||at(n,t.prev,t))||je(n,t)&&at(n.prev,n,n.next)>0&&at(t.prev,t,t.next)>0)}d(il,"isValidDiagonal");function at(n,t,e){return(t.y-n.y)*(e.x-t.x)-(t.x-n.x)*(e.y-t.y)}d(at,"area");function je(n,t){return n.x===t.x&&n.y===t.y}d(je,"equals");function vo(n,t,e,i){let s=ri(at(n,t,e)),r=ri(at(n,t,i)),o=ri(at(e,i,n)),a=ri(at(e,i,t));return!!(s!==r&&o!==a||s===0&&si(n,e,t)||r===0&&si(n,i,t)||o===0&&si(e,n,i)||a===0&&si(e,t,i))}d(vo,"intersects");function si(n,t,e){return t.x<=Math.max(n.x,e.x)&&t.x>=Math.min(n.x,e.x)&&t.y<=Math.max(n.y,e.y)&&t.y>=Math.min(n.y,e.y)}d(si,"onSegment");function ri(n){return n>0?1:n<0?-1:0}d(ri,"sign");function sl(n,t){let e=n;do{if(e.i!==n.i&&e.next.i!==n.i&&e.i!==t.i&&e.next.i!==t.i&&vo(e,e.next,n,t))return!0;e=e.next}while(e!==n);return!1}d(sl,"intersectsPolygon");function Cn(n,t){return at(n.prev,n,n.next)<0?at(n,t,n.next)>=0&&at(n,n.prev,t)>=0:at(n,t,n.prev)<0||at(n,n.next,t)<0}d(Cn,"locallyInside");function rl(n,t){let e=n,i=!1,s=(n.x+t.x)/2,r=(n.y+t.y)/2;do e.y>r!=e.next.y>r&&e.next.y!==e.y&&s<(e.next.x-e.x)*(r-e.y)/(e.next.y-e.y)+e.x&&(i=!i),e=e.next;while(e!==n);return i}d(rl,"middleInside");function Mo(n,t){let e=Es(n.i,n.x,n.y),i=Es(t.i,t.x,t.y),s=n.next,r=t.prev;return n.next=t,t.prev=n,e.next=s,s.prev=e,i.next=e,e.prev=i,r.next=i,i.prev=r,i}d(Mo,"splitPolygon");function Qr(n,t,e,i){let s=Es(n,t,e);return i?(s.next=i.next,s.prev=i,i.next.prev=s,i.next=s):(s.prev=s,s.next=s),s}d(Qr,"insertNode");function Rn(n){n.next.prev=n.prev,n.prev.next=n.next,n.prevZ&&(n.prevZ.nextZ=n.nextZ),n.nextZ&&(n.nextZ.prevZ=n.prevZ)}d(Rn,"removeNode");function Es(n,t,e){return{i:n,x:t,y:e,prev:null,next:null,z:0,prevZ:null,nextZ:null,steiner:!1}}d(Es,"createNode");function ol(n,t,e,i){let s=0;for(let r=t,o=e-i;r<e;r+=i)s+=(n[o]-n[r])*(n[r+1]+n[o+1]),o=r;return s}d(ol,"signedArea");var Cs=class{static{d(this,"Earcut")}static triangulate(t,e,i=2){return Wc(t,e,i)}},In=class n{static{d(this,"ShapeUtils")}static area(t){let e=t.length,i=0;for(let s=e-1,r=0;r<e;s=r++)i+=t[s].x*t[r].y-t[r].x*t[s].y;return i*.5}static isClockWise(t){return n.area(t)<0}static triangulateShape(t,e){let i=[],s=[],r=[];to(t),eo(i,t);let o=t.length;e.forEach(to);for(let c=0;c<e.length;c++)s.push(o),o+=e[c].length,eo(i,e[c]);let a=Cs.triangulate(i,s);for(let c=0;c<a.length;c+=3)r.push(a.slice(c,c+3));return r}};function to(n){let t=n.length;t>2&&n[t-1].equals(n[0])&&n.pop()}d(to,"removeDupEndPts");function eo(n,t){for(let e=0;e<t.length;e++)n.push(t[e].x),n.push(t[e].y)}d(eo,"addContour");function bo(n){let t={};for(let e in n){t[e]={};for(let i in n[e]){let s=n[e][i];if(no(s))s.isRenderTargetTexture?(gt("UniformsUtils: Textures of render targets cannot be cloned via cloneUniforms() or mergeUniforms()."),t[e][i]=null):t[e][i]=s.clone();else if(Array.isArray(s))if(no(s[0])){let r=[];for(let o=0,a=s.length;o<a;o++)r[o]=s[o].clone();t[e][i]=r}else t[e][i]=s.slice();else t[e][i]=s}}return t}d(bo,"cloneUniforms");function At(n){let t={};for(let e=0;e<n.length;e++){let i=bo(n[e]);for(let s in i)t[s]=i[s]}return t}d(At,"mergeUniforms");function no(n){return n&&(n.isColor||n.isMatrix3||n.isMatrix4||n.isVector2||n.isVector3||n.isVector4||n.isTexture||n.isQuaternion)}d(no,"isThreeObject");function oi(n,t){return!n||n.constructor===t?n:typeof t.BYTES_PER_ELEMENT=="number"?new t(n):Array.prototype.slice.call(n)}d(oi,"convertArray");var pe=class{static{d(this,"Interpolant")}constructor(t,e,i,s){this.parameterPositions=t,this._cachedIndex=0,this.resultBuffer=s!==void 0?s:new e.constructor(i),this.sampleValues=e,this.valueSize=i,this.settings=null,this.DefaultSettings_={}}evaluate(t){let e=this.parameterPositions,i=this._cachedIndex,s=e[i],r=e[i-1];n:{t:{let o;e:{i:if(!(t<s)){for(let a=i+2;;){if(s===void 0){if(t<r)break i;return i=e.length,this._cachedIndex=i,this.copySampleValue_(i-1)}if(i===a)break;if(r=s,s=e[++i],t<s)break t}o=e.length;break e}if(!(t>=r)){let a=e[1];t<a&&(i=2,r=a);for(let c=i-2;;){if(r===void 0)return this._cachedIndex=0,this.copySampleValue_(0);if(i===c)break;if(s=r,r=e[--i-1],t>=r)break t}o=i,i=0;break e}break n}for(;i<o;){let a=i+o>>>1;t<e[a]?o=a:i=a+1}if(s=e[i],r=e[i-1],r===void 0)return this._cachedIndex=0,this.copySampleValue_(0);if(s===void 0)return i=e.length,this._cachedIndex=i,this.copySampleValue_(i-1)}this._cachedIndex=i,this.intervalChanged_(i,r,s)}return this.interpolate_(i,r,t,s)}getSettings_(){return this.settings||this.DefaultSettings_}copySampleValue_(t){let e=this.resultBuffer,i=this.sampleValues,s=this.valueSize,r=t*s;for(let o=0;o!==s;++o)e[o]=i[r+o];return e}interpolate_(){throw new Error("THREE.Interpolant: Call to abstract method.")}intervalChanged_(){}},xi=class extends pe{static{d(this,"CubicInterpolant")}constructor(t,e,i,s){super(t,e,i,s),this._weightPrev=-0,this._offsetPrev=-0,this._weightNext=-0,this._offsetNext=-0,this.DefaultSettings_={endingStart:xs,endingEnd:xs}}intervalChanged_(t,e,i){let s=this.parameterPositions,r=t-2,o=t+1,a=s[r],c=s[o];if(a===void 0)switch(this.getSettings_().endingStart){case _s:r=t,a=2*e-i;break;case ys:r=s.length-2,a=e+s[r]-s[r+1];break;default:r=t,a=i}if(c===void 0)switch(this.getSettings_().endingEnd){case _s:o=t,c=2*i-e;break;case ys:o=1,c=i+s[1]-s[0];break;default:o=t-1,c=e}let l=(i-e)*.5,u=this.valueSize;this._weightPrev=l/(e-a),this._weightNext=l/(c-i),this._offsetPrev=r*u,this._offsetNext=o*u}interpolate_(t,e,i,s){let r=this.resultBuffer,o=this.sampleValues,a=this.valueSize,c=t*a,l=c-a,u=this._offsetPrev,h=this._offsetNext,f=this._weightPrev,p=this._weightNext,m=(i-e)/(s-e),g=m*m,x=g*m,_=-f*x+2*f*g-f*m,v=(1+f)*x+(-1.5-2*f)*g+(-.5+f)*m+1,y=(-1-p)*x+(1.5+p)*g+.5*m,b=p*x-p*g;for(let T=0;T!==a;++T)r[T]=_*o[u+T]+v*o[l+T]+y*o[c+T]+b*o[h+T];return r}},_i=class extends pe{static{d(this,"LinearInterpolant")}constructor(t,e,i,s){super(t,e,i,s)}interpolate_(t,e,i,s){let r=this.resultBuffer,o=this.sampleValues,a=this.valueSize,c=t*a,l=c-a,u=(i-e)/(s-e),h=1-u;for(let f=0;f!==a;++f)r[f]=o[l+f]*h+o[c+f]*u;return r}},yi=class extends pe{static{d(this,"DiscreteInterpolant")}constructor(t,e,i,s){super(t,e,i,s)}interpolate_(t){return this.copySampleValue_(t-1)}},vi=class extends pe{static{d(this,"BezierInterpolant")}interpolate_(t,e,i,s){let r=this.resultBuffer,o=this.sampleValues,a=this.valueSize,c=t*a,l=c-a,u=this.inTangents,h=this.outTangents;if(!u||!h){let m=(i-e)/(s-e),g=1-m;for(let x=0;x!==a;++x)r[x]=o[l+x]*g+o[c+x]*m;return r}let f=a*2,p=t-1;for(let m=0;m!==a;++m){let g=o[l+m],x=o[c+m],_=p*f+m*2,v=h[_],y=h[_+1],b=t*f+m*2,T=u[b],S=u[b+1],M=(i-e)/(s-e),A,I,C,N,R;for(let w=0;w<8;w++){A=M*M,I=A*M,C=1-M,N=C*C,R=N*C;let L=R*e+3*N*M*v+3*C*A*T+I*s-i;if(Math.abs(L)<1e-10)break;let E=3*N*(v-e)+6*C*M*(T-v)+3*A*(s-T);if(Math.abs(E)<1e-10)break;M=M-L/E,M=Math.max(0,Math.min(1,M))}r[m]=R*g+3*N*M*y+3*C*A*S+I*x}return r}},Ft=class{static{d(this,"KeyframeTrack")}constructor(t,e,i,s){if(t===void 0)throw new Error("THREE.KeyframeTrack: track name is undefined");if(e===void 0||e.length===0)throw new Error("THREE.KeyframeTrack: no keyframes in track named "+t);this.name=t,this.times=oi(e,this.TimeBufferType),this.values=oi(i,this.ValueBufferType),this.setInterpolation(s||this.DefaultInterpolation)}static toJSON(t){let e=t.constructor,i;if(e.toJSON!==this.toJSON)i=e.toJSON(t);else{i={name:t.name,times:oi(t.times,Array),values:oi(t.values,Array)};let s=t.getInterpolation();s!==t.DefaultInterpolation&&(i.interpolation=s)}return i.type=t.ValueTypeName,i}InterpolantFactoryMethodDiscrete(t){return new yi(this.times,this.values,this.getValueSize(),t)}InterpolantFactoryMethodLinear(t){return new _i(this.times,this.values,this.getValueSize(),t)}InterpolantFactoryMethodSmooth(t){return new xi(this.times,this.values,this.getValueSize(),t)}InterpolantFactoryMethodBezier(t){let e=new vi(this.times,this.values,this.getValueSize(),t);return this.settings&&(e.inTangents=this.settings.inTangents,e.outTangents=this.settings.outTangents),e}setInterpolation(t){let e;switch(t){case Tn:e=this.InterpolantFactoryMethodDiscrete;break;case li:e=this.InterpolantFactoryMethodLinear;break;case ai:e=this.InterpolantFactoryMethodSmooth;break;case gs:e=this.InterpolantFactoryMethodBezier;break}if(e===void 0){let i="unsupported interpolation for "+this.ValueTypeName+" keyframe track named "+this.name;if(this.createInterpolant===void 0)if(t!==this.DefaultInterpolation)this.setInterpolation(this.DefaultInterpolation);else throw new Error(i);return gt("KeyframeTrack:",i),this}return this.createInterpolant=e,this}getInterpolation(){switch(this.createInterpolant){case this.InterpolantFactoryMethodDiscrete:return Tn;case this.InterpolantFactoryMethodLinear:return li;case this.InterpolantFactoryMethodSmooth:return ai;case this.InterpolantFactoryMethodBezier:return gs}}getValueSize(){return this.values.length/this.times.length}shift(t){if(t!==0){let e=this.times;for(let i=0,s=e.length;i!==s;++i)e[i]+=t}return this}scale(t){if(t!==1){let e=this.times;for(let i=0,s=e.length;i!==s;++i)e[i]*=t}return this}trim(t,e){let i=this.times,s=i.length,r=0,o=s-1;for(;r!==s&&i[r]<t;)++r;for(;o!==-1&&i[o]>e;)--o;if(++o,r!==0||o!==s){r>=o&&(o=Math.max(o,1),r=o-1);let a=this.getValueSize();this.times=i.slice(r,o),this.values=this.values.slice(r*a,o*a)}return this}validate(){let t=!0,e=this.getValueSize();e-Math.floor(e)!==0&&(ot("KeyframeTrack: Invalid value size in track.",this),t=!1);let i=this.times,s=this.values,r=i.length;r===0&&(ot("KeyframeTrack: Track is empty.",this),t=!1);let o=null;for(let a=0;a!==r;a++){let c=i[a];if(typeof c=="number"&&isNaN(c)){ot("KeyframeTrack: Time is not a valid number.",this,a,c),t=!1;break}if(o!==null&&o>c){ot("KeyframeTrack: Out of order keys.",this,a,c,o),t=!1;break}o=c}if(s!==void 0&&Cc(s))for(let a=0,c=s.length;a!==c;++a){let l=s[a];if(isNaN(l)){ot("KeyframeTrack: Value is not a valid number.",this,a,l),t=!1;break}}return t}optimize(){let t=this.times.slice(),e=this.values.slice(),i=this.getValueSize(),s=this.getInterpolation()===ai,r=t.length-1,o=1;for(let a=1;a<r;++a){let c=!1,l=t[a],u=t[a+1];if(l!==u&&(a!==1||l!==t[0]))if(s)c=!0;else{let h=a*i,f=h-i,p=h+i;for(let m=0;m!==i;++m){let g=e[h+m];if(g!==e[f+m]||g!==e[p+m]){c=!0;break}}}if(c){if(a!==o){t[o]=t[a];let h=a*i,f=o*i;for(let p=0;p!==i;++p)e[f+p]=e[h+p]}++o}}if(r>0){t[o]=t[r];for(let a=r*i,c=o*i,l=0;l!==i;++l)e[c+l]=e[a+l];++o}return o!==t.length?(this.times=t.slice(0,o),this.values=e.slice(0,o*i)):(this.times=t,this.values=e),this}clone(){let t=this.times.slice(),e=this.values.slice(),i=this.constructor,s=new i(this.name,t,e);return s.createInterpolant=this.createInterpolant,s}};Ft.prototype.ValueTypeName="";Ft.prototype.TimeBufferType=Float32Array;Ft.prototype.ValueBufferType=Float32Array;Ft.prototype.DefaultInterpolation=li;var me=class extends Ft{static{d(this,"BooleanKeyframeTrack")}constructor(t,e,i){super(t,e,i)}};me.prototype.ValueTypeName="bool";me.prototype.ValueBufferType=Array;me.prototype.DefaultInterpolation=Tn;me.prototype.InterpolantFactoryMethodLinear=void 0;me.prototype.InterpolantFactoryMethodSmooth=void 0;var Mi=class extends Ft{static{d(this,"ColorKeyframeTrack")}constructor(t,e,i,s){super(t,e,i,s)}};Mi.prototype.ValueTypeName="color";var bi=class extends Ft{static{d(this,"NumberKeyframeTrack")}constructor(t,e,i,s){super(t,e,i,s)}};bi.prototype.ValueTypeName="number";var Si=class extends pe{static{d(this,"QuaternionLinearInterpolant")}constructor(t,e,i,s){super(t,e,i,s)}interpolate_(t,e,i,s){let r=this.resultBuffer,o=this.sampleValues,a=this.valueSize,c=(i-e)/(s-e),l=t*a;for(let u=l+a;l!==u;l+=4)Yt.slerpFlat(r,0,o,l-a,o,l,c);return r}},Pn=class extends Ft{static{d(this,"QuaternionKeyframeTrack")}constructor(t,e,i,s){super(t,e,i,s)}InterpolantFactoryMethodLinear(t){return new Si(this.times,this.values,this.getValueSize(),t)}};Pn.prototype.ValueTypeName="quaternion";Pn.prototype.InterpolantFactoryMethodSmooth=void 0;var ge=class extends Ft{static{d(this,"StringKeyframeTrack")}constructor(t,e,i){super(t,e,i)}};ge.prototype.ValueTypeName="string";ge.prototype.ValueBufferType=Array;ge.prototype.DefaultInterpolation=Tn;ge.prototype.InterpolantFactoryMethodLinear=void 0;ge.prototype.InterpolantFactoryMethodSmooth=void 0;var Ai=class extends Ft{static{d(this,"VectorKeyframeTrack")}constructor(t,e,i,s){super(t,e,i,s)}};Ai.prototype.ValueTypeName="vector";var Ti=class{static{d(this,"LoadingManager")}constructor(t,e,i){let s=this,r=!1,o=0,a=0,c,l=[];this.onStart=void 0,this.onLoad=t,this.onProgress=e,this.onError=i,this._abortController=null,this.itemStart=function(u){a++,r===!1&&s.onStart!==void 0&&s.onStart(u,o,a),r=!0},this.itemEnd=function(u){o++,s.onProgress!==void 0&&s.onProgress(u,o,a),o===a&&(r=!1,s.onLoad!==void 0&&s.onLoad())},this.itemError=function(u){s.onError!==void 0&&s.onError(u)},this.resolveURL=function(u){return u=u.normalize("NFC"),c?c(u):u},this.setURLModifier=function(u){return c=u,this},this.addHandler=function(u,h){return l.push(u,h),this},this.removeHandler=function(u){let h=l.indexOf(u);return h!==-1&&l.splice(h,2),this},this.getHandler=function(u){for(let h=0,f=l.length;h<f;h+=2){let p=l[h],m=l[h+1];if(p.global&&(p.lastIndex=0),p.test(u))return m}return null},this.abort=function(){return this.abortController.abort(),this._abortController=null,this}}get abortController(){return this._abortController||(this._abortController=new AbortController),this._abortController}},So=new Ti,wi=class{static{d(this,"Loader")}constructor(t){this.manager=t!==void 0?t:So,this.crossOrigin="anonymous",this.withCredentials=!1,this.path="",this.resourcePath="",this.requestHeader={},typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("observe",{detail:this}))}load(){}loadAsync(t,e){let i=this;return new Promise(function(s,r){i.load(t,s,e,r)})}parse(){}setCrossOrigin(t){return this.crossOrigin=t,this}setWithCredentials(t){return this.withCredentials=t,this}setPath(t){return this.path=t,this}setResourcePath(t){return this.resourcePath=t,this}setRequestHeader(t){return this.requestHeader=t,this}abort(){return this}};wi.DEFAULT_MATERIAL_NAME="__DEFAULT";var Vs="\\[\\]\\.:\\/",al=new RegExp("["+Vs+"]","g"),Gs="[^"+Vs+"]",cl="[^"+Vs.replace("\\.","")+"]",ll=/((?:WC+[\/:])*)/.source.replace("WC",Gs),ul=/(WCOD+)?/.source.replace("WCOD",cl),hl=/(?:\.(WC+)(?:\[(.+)\])?)?/.source.replace("WC",Gs),fl=/\.(WC+)(?:\[(.+)\])?/.source.replace("WC",Gs),dl=new RegExp("^"+ll+ul+hl+fl+"$"),pl=["material","materials","bones","map"],Rs=class{static{d(this,"Composite")}constructor(t,e,i){let s=i||it.parseTrackName(e);this._targetGroup=t,this._bindings=t.subscribe_(e,s)}getValue(t,e){this.bind();let i=this._targetGroup.nCachedObjects_,s=this._bindings[i];s!==void 0&&s.getValue(t,e)}setValue(t,e){let i=this._bindings;for(let s=this._targetGroup.nCachedObjects_,r=i.length;s!==r;++s)i[s].setValue(t,e)}bind(){let t=this._bindings;for(let e=this._targetGroup.nCachedObjects_,i=t.length;e!==i;++e)t[e].bind()}unbind(){let t=this._bindings;for(let e=this._targetGroup.nCachedObjects_,i=t.length;e!==i;++e)t[e].unbind()}},it=class n{static{d(this,"PropertyBinding")}constructor(t,e,i){this.path=e,this.parsedPath=i||n.parseTrackName(e),this.node=n.findNode(t,this.parsedPath.nodeName),this.rootNode=t,this.getValue=this._getValue_unbound,this.setValue=this._setValue_unbound}static create(t,e,i){return t&&t.isAnimationObjectGroup?new n.Composite(t,e,i):new n(t,e,i)}static sanitizeNodeName(t){return t.replace(/\s/g,"_").replace(al,"")}static parseTrackName(t){let e=dl.exec(t);if(e===null)throw new Error("THREE.PropertyBinding: Cannot parse trackName: "+t);let i={nodeName:e[2],objectName:e[3],objectIndex:e[4],propertyName:e[5],propertyIndex:e[6]},s=i.nodeName&&i.nodeName.lastIndexOf(".");if(s!==void 0&&s!==-1){let r=i.nodeName.substring(s+1);pl.indexOf(r)!==-1&&(i.nodeName=i.nodeName.substring(0,s),i.objectName=r)}if(i.propertyName===null||i.propertyName.length===0)throw new Error("THREE.PropertyBinding: can not parse propertyName from trackName: "+t);return i}static findNode(t,e){if(e===void 0||e===""||e==="."||e===-1||e===t.name||e===t.uuid)return t;if(t.skeleton){let i=t.skeleton.getBoneByName(e);if(i!==void 0)return i}if(t.children){let i=d(function(r){for(let o=0;o<r.length;o++){let a=r[o];if(a.name===e||a.uuid===e)return a;let c=i(a.children);if(c)return c}return null},"searchNodeSubtree"),s=i(t.children);if(s)return s}return null}_getValue_unavailable(){}_setValue_unavailable(){}_getValue_direct(t,e){t[e]=this.targetObject[this.propertyName]}_getValue_array(t,e){let i=this.resolvedProperty;for(let s=0,r=i.length;s!==r;++s)t[e++]=i[s]}_getValue_arrayElement(t,e){t[e]=this.resolvedProperty[this.propertyIndex]}_getValue_toArray(t,e){this.resolvedProperty.toArray(t,e)}_setValue_direct(t,e){this.targetObject[this.propertyName]=t[e]}_setValue_direct_setNeedsUpdate(t,e){this.targetObject[this.propertyName]=t[e],this.targetObject.needsUpdate=!0}_setValue_direct_setMatrixWorldNeedsUpdate(t,e){this.targetObject[this.propertyName]=t[e],this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_array(t,e){let i=this.resolvedProperty;for(let s=0,r=i.length;s!==r;++s)i[s]=t[e++]}_setValue_array_setNeedsUpdate(t,e){let i=this.resolvedProperty;for(let s=0,r=i.length;s!==r;++s)i[s]=t[e++];this.targetObject.needsUpdate=!0}_setValue_array_setMatrixWorldNeedsUpdate(t,e){let i=this.resolvedProperty;for(let s=0,r=i.length;s!==r;++s)i[s]=t[e++];this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_arrayElement(t,e){this.resolvedProperty[this.propertyIndex]=t[e]}_setValue_arrayElement_setNeedsUpdate(t,e){this.resolvedProperty[this.propertyIndex]=t[e],this.targetObject.needsUpdate=!0}_setValue_arrayElement_setMatrixWorldNeedsUpdate(t,e){this.resolvedProperty[this.propertyIndex]=t[e],this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_fromArray(t,e){this.resolvedProperty.fromArray(t,e)}_setValue_fromArray_setNeedsUpdate(t,e){this.resolvedProperty.fromArray(t,e),this.targetObject.needsUpdate=!0}_setValue_fromArray_setMatrixWorldNeedsUpdate(t,e){this.resolvedProperty.fromArray(t,e),this.targetObject.matrixWorldNeedsUpdate=!0}_getValue_unbound(t,e){this.bind(),this.getValue(t,e)}_setValue_unbound(t,e){this.bind(),this.setValue(t,e)}bind(){let t=this.node,e=this.parsedPath,i=e.objectName,s=e.propertyName,r=e.propertyIndex;if(t||(t=n.findNode(this.rootNode,e.nodeName),this.node=t),this.getValue=this._getValue_unavailable,this.setValue=this._setValue_unavailable,!t){gt("PropertyBinding: No target node found for track: "+this.path+".");return}if(i){let l=e.objectIndex;switch(i){case"materials":if(!t.material){ot("PropertyBinding: Can not bind to material as node does not have a material.",this);return}if(!t.material.materials){ot("PropertyBinding: Can not bind to material.materials as node.material does not have a materials array.",this);return}t=t.material.materials;break;case"bones":if(!t.skeleton){ot("PropertyBinding: Can not bind to bones as node does not have a skeleton.",this);return}t=t.skeleton.bones;for(let u=0;u<t.length;u++)if(t[u].name===l){l=u;break}break;case"map":if("map"in t){t=t.map;break}if(!t.material){ot("PropertyBinding: Can not bind to material as node does not have a material.",this);return}if(!t.material.map){ot("PropertyBinding: Can not bind to material.map as node.material does not have a map.",this);return}t=t.material.map;break;default:if(t[i]===void 0){ot("PropertyBinding: Can not bind to objectName of node undefined.",this);return}t=t[i]}if(l!==void 0){if(t[l]===void 0){ot("PropertyBinding: Trying to bind to objectIndex of objectName, but is undefined.",this,t);return}t=t[l]}}let o=t[s];if(o===void 0){let l=e.nodeName;ot("PropertyBinding: Trying to update property for track: "+l+"."+s+" but it wasn't found.",t);return}let a=this.Versioning.None;this.targetObject=t,t.isMaterial===!0?a=this.Versioning.NeedsUpdate:t.isObject3D===!0&&(a=this.Versioning.MatrixWorldNeedsUpdate);let c=this.BindingType.Direct;if(r!==void 0){if(s==="morphTargetInfluences"){if(!t.geometry){ot("PropertyBinding: Can not bind to morphTargetInfluences because node does not have a geometry.",this);return}if(!t.geometry.morphAttributes){ot("PropertyBinding: Can not bind to morphTargetInfluences because node does not have a geometry.morphAttributes.",this);return}t.morphTargetDictionary[r]!==void 0&&(r=t.morphTargetDictionary[r])}c=this.BindingType.ArrayElement,this.resolvedProperty=o,this.propertyIndex=r}else o.fromArray!==void 0&&o.toArray!==void 0?(c=this.BindingType.HasFromToArray,this.resolvedProperty=o):Array.isArray(o)?(c=this.BindingType.EntireArray,this.resolvedProperty=o):this.propertyName=s;this.getValue=this.GetterByBindingType[c],this.setValue=this.SetterByBindingTypeAndVersioning[c][a]}unbind(){this.node=null,this.getValue=this._getValue_unbound,this.setValue=this._setValue_unbound}};it.Composite=Rs;it.prototype.BindingType={Direct:0,EntireArray:1,ArrayElement:2,HasFromToArray:3};it.prototype.Versioning={None:0,NeedsUpdate:1,MatrixWorldNeedsUpdate:2};it.prototype.GetterByBindingType=[it.prototype._getValue_direct,it.prototype._getValue_array,it.prototype._getValue_arrayElement,it.prototype._getValue_toArray];it.prototype.SetterByBindingTypeAndVersioning=[[it.prototype._setValue_direct,it.prototype._setValue_direct_setNeedsUpdate,it.prototype._setValue_direct_setMatrixWorldNeedsUpdate],[it.prototype._setValue_array,it.prototype._setValue_array_setNeedsUpdate,it.prototype._setValue_array_setMatrixWorldNeedsUpdate],[it.prototype._setValue_arrayElement,it.prototype._setValue_arrayElement_setNeedsUpdate,it.prototype._setValue_arrayElement_setMatrixWorldNeedsUpdate],[it.prototype._setValue_fromArray,it.prototype._setValue_fromArray_setNeedsUpdate,it.prototype._setValue_fromArray_setMatrixWorldNeedsUpdate]];var Wp=new Float32Array(1);var Is=class n{static{d(this,"Matrix2")}static{n.prototype.isMatrix2=!0}constructor(t,e,i,s){this.elements=[1,0,0,1],t!==void 0&&this.set(t,e,i,s)}identity(){return this.set(1,0,0,1),this}fromArray(t,e=0){for(let i=0;i<4;i++)this.elements[i]=t[i+e];return this}set(t,e,i,s){let r=this.elements;return r[0]=t,r[2]=e,r[1]=i,r[3]=s,this}};typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("register",{detail:{revision:"185"}}));typeof window<"u"&&(window.__THREE__?gt("WARNING: Multiple instances of Three.js being imported."):window.__THREE__="185");var ml=`#ifdef USE_ALPHAHASH
	if ( diffuseColor.a < getAlphaHashThreshold( vPosition ) ) discard;
#endif`,gl=`#ifdef USE_ALPHAHASH
	const float ALPHA_HASH_SCALE = 0.05;
	float hash2D( vec2 value ) {
		return fract( 1.0e4 * sin( 17.0 * value.x + 0.1 * value.y ) * ( 0.1 + abs( sin( 13.0 * value.y + value.x ) ) ) );
	}
	float hash3D( vec3 value ) {
		return hash2D( vec2( hash2D( value.xy ), value.z ) );
	}
	float getAlphaHashThreshold( vec3 position ) {
		float maxDeriv = max(
			length( dFdx( position.xyz ) ),
			length( dFdy( position.xyz ) )
		);
		float pixScale = 1.0 / ( ALPHA_HASH_SCALE * maxDeriv );
		vec2 pixScales = vec2(
			exp2( floor( log2( pixScale ) ) ),
			exp2( ceil( log2( pixScale ) ) )
		);
		vec2 alpha = vec2(
			hash3D( floor( pixScales.x * position.xyz ) ),
			hash3D( floor( pixScales.y * position.xyz ) )
		);
		float lerpFactor = fract( log2( pixScale ) );
		float x = ( 1.0 - lerpFactor ) * alpha.x + lerpFactor * alpha.y;
		float a = min( lerpFactor, 1.0 - lerpFactor );
		vec3 cases = vec3(
			x * x / ( 2.0 * a * ( 1.0 - a ) ),
			( x - 0.5 * a ) / ( 1.0 - a ),
			1.0 - ( ( 1.0 - x ) * ( 1.0 - x ) / ( 2.0 * a * ( 1.0 - a ) ) )
		);
		float threshold = ( x < ( 1.0 - a ) )
			? ( ( x < a ) ? cases.x : cases.y )
			: cases.z;
		return clamp( threshold , 1.0e-6, 1.0 );
	}
#endif`,xl=`#ifdef USE_ALPHAMAP
	diffuseColor.a *= texture2D( alphaMap, vAlphaMapUv ).g;
#endif`,_l=`#ifdef USE_ALPHAMAP
	uniform sampler2D alphaMap;
#endif`,yl=`#ifdef USE_ALPHATEST
	#ifdef ALPHA_TO_COVERAGE
	diffuseColor.a = smoothstep( alphaTest, alphaTest + fwidth( diffuseColor.a ), diffuseColor.a );
	if ( diffuseColor.a == 0.0 ) discard;
	#else
	if ( diffuseColor.a < alphaTest ) discard;
	#endif
#endif`,vl=`#ifdef USE_ALPHATEST
	uniform float alphaTest;
#endif`,Ml=`#ifdef USE_AOMAP
	float ambientOcclusion = ( texture2D( aoMap, vAoMapUv ).r - 1.0 ) * aoMapIntensity + 1.0;
	reflectedLight.indirectDiffuse *= ambientOcclusion;
	#if defined( USE_CLEARCOAT ) 
		clearcoatSpecularIndirect *= ambientOcclusion;
	#endif
	#if defined( USE_SHEEN ) 
		sheenSpecularIndirect *= ambientOcclusion;
	#endif
	#if defined( USE_ENVMAP ) && defined( STANDARD )
		float dotNV = saturate( dot( geometryNormal, geometryViewDir ) );
		reflectedLight.indirectSpecular *= computeSpecularOcclusion( dotNV, ambientOcclusion, material.roughness );
	#endif
#endif`,bl=`#ifdef USE_AOMAP
	uniform sampler2D aoMap;
	uniform float aoMapIntensity;
#endif`,Sl=`#ifdef USE_BATCHING
	#if ! defined( GL_ANGLE_multi_draw )
	#define gl_DrawID _gl_DrawID
	uniform int _gl_DrawID;
	#endif
	uniform highp sampler2D batchingTexture;
	uniform highp usampler2D batchingIdTexture;
	mat4 getBatchingMatrix( const in float i ) {
		int size = textureSize( batchingTexture, 0 ).x;
		int j = int( i ) * 4;
		int x = j % size;
		int y = j / size;
		vec4 v1 = texelFetch( batchingTexture, ivec2( x, y ), 0 );
		vec4 v2 = texelFetch( batchingTexture, ivec2( x + 1, y ), 0 );
		vec4 v3 = texelFetch( batchingTexture, ivec2( x + 2, y ), 0 );
		vec4 v4 = texelFetch( batchingTexture, ivec2( x + 3, y ), 0 );
		return mat4( v1, v2, v3, v4 );
	}
	float getIndirectIndex( const in int i ) {
		int size = textureSize( batchingIdTexture, 0 ).x;
		int x = i % size;
		int y = i / size;
		return float( texelFetch( batchingIdTexture, ivec2( x, y ), 0 ).r );
	}
#endif
#ifdef USE_BATCHING_COLOR
	uniform sampler2D batchingColorTexture;
	vec4 getBatchingColor( const in float i ) {
		int size = textureSize( batchingColorTexture, 0 ).x;
		int j = int( i );
		int x = j % size;
		int y = j / size;
		return texelFetch( batchingColorTexture, ivec2( x, y ), 0 );
	}
#endif`,Al=`#ifdef USE_BATCHING
	mat4 batchingMatrix = getBatchingMatrix( getIndirectIndex( gl_DrawID ) );
#endif`,Tl=`vec3 transformed = vec3( position );
#ifdef USE_ALPHAHASH
	vPosition = vec3( position );
#endif`,wl=`vec3 objectNormal = vec3( normal );
#ifdef USE_TANGENT
	vec3 objectTangent = vec3( tangent.xyz );
#endif`,El=`float G_BlinnPhong_Implicit( ) {
	return 0.25;
}
float D_BlinnPhong( const in float shininess, const in float dotNH ) {
	return RECIPROCAL_PI * ( shininess * 0.5 + 1.0 ) * pow( dotNH, shininess );
}
vec3 BRDF_BlinnPhong( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in vec3 specularColor, const in float shininess ) {
	vec3 halfDir = normalize( lightDir + viewDir );
	float dotNH = saturate( dot( normal, halfDir ) );
	float dotVH = saturate( dot( viewDir, halfDir ) );
	vec3 F = F_Schlick( specularColor, 1.0, dotVH );
	float G = G_BlinnPhong_Implicit( );
	float D = D_BlinnPhong( shininess, dotNH );
	return F * ( G * D );
} // validated`,Cl=`#ifdef USE_IRIDESCENCE
	const mat3 XYZ_TO_REC709 = mat3(
		 3.2404542, -0.9692660,  0.0556434,
		-1.5371385,  1.8760108, -0.2040259,
		-0.4985314,  0.0415560,  1.0572252
	);
	vec3 Fresnel0ToIor( vec3 fresnel0 ) {
		vec3 sqrtF0 = sqrt( fresnel0 );
		return ( vec3( 1.0 ) + sqrtF0 ) / ( vec3( 1.0 ) - sqrtF0 );
	}
	vec3 IorToFresnel0( vec3 transmittedIor, float incidentIor ) {
		return pow2( ( transmittedIor - vec3( incidentIor ) ) / ( transmittedIor + vec3( incidentIor ) ) );
	}
	float IorToFresnel0( float transmittedIor, float incidentIor ) {
		return pow2( ( transmittedIor - incidentIor ) / ( transmittedIor + incidentIor ));
	}
	vec3 evalSensitivity( float OPD, vec3 shift ) {
		float phase = 2.0 * PI * OPD * 1.0e-9;
		vec3 val = vec3( 5.4856e-13, 4.4201e-13, 5.2481e-13 );
		vec3 pos = vec3( 1.6810e+06, 1.7953e+06, 2.2084e+06 );
		vec3 var = vec3( 4.3278e+09, 9.3046e+09, 6.6121e+09 );
		vec3 xyz = val * sqrt( 2.0 * PI * var ) * cos( pos * phase + shift ) * exp( - pow2( phase ) * var );
		xyz.x += 9.7470e-14 * sqrt( 2.0 * PI * 4.5282e+09 ) * cos( 2.2399e+06 * phase + shift[ 0 ] ) * exp( - 4.5282e+09 * pow2( phase ) );
		xyz /= 1.0685e-7;
		vec3 rgb = XYZ_TO_REC709 * xyz;
		return rgb;
	}
	vec3 evalIridescence( float outsideIOR, float eta2, float cosTheta1, float thinFilmThickness, vec3 baseF0 ) {
		vec3 I;
		float iridescenceIOR = mix( outsideIOR, eta2, smoothstep( 0.0, 0.03, thinFilmThickness ) );
		float sinTheta2Sq = pow2( outsideIOR / iridescenceIOR ) * ( 1.0 - pow2( cosTheta1 ) );
		float cosTheta2Sq = 1.0 - sinTheta2Sq;
		if ( cosTheta2Sq < 0.0 ) {
			return vec3( 1.0 );
		}
		float cosTheta2 = sqrt( cosTheta2Sq );
		float R0 = IorToFresnel0( iridescenceIOR, outsideIOR );
		float R12 = F_Schlick( R0, 1.0, cosTheta1 );
		float T121 = 1.0 - R12;
		float phi12 = 0.0;
		if ( iridescenceIOR < outsideIOR ) phi12 = PI;
		float phi21 = PI - phi12;
		vec3 baseIOR = Fresnel0ToIor( clamp( baseF0, 0.0, 0.9999 ) );		vec3 R1 = IorToFresnel0( baseIOR, iridescenceIOR );
		vec3 R23 = F_Schlick( R1, 1.0, cosTheta2 );
		vec3 phi23 = vec3( 0.0 );
		if ( baseIOR[ 0 ] < iridescenceIOR ) phi23[ 0 ] = PI;
		if ( baseIOR[ 1 ] < iridescenceIOR ) phi23[ 1 ] = PI;
		if ( baseIOR[ 2 ] < iridescenceIOR ) phi23[ 2 ] = PI;
		float OPD = 2.0 * iridescenceIOR * thinFilmThickness * cosTheta2;
		vec3 phi = vec3( phi21 ) + phi23;
		vec3 R123 = clamp( R12 * R23, 1e-5, 0.9999 );
		vec3 r123 = sqrt( R123 );
		vec3 Rs = pow2( T121 ) * R23 / ( vec3( 1.0 ) - R123 );
		vec3 C0 = R12 + Rs;
		I = C0;
		vec3 Cm = Rs - T121;
		for ( int m = 1; m <= 2; ++ m ) {
			Cm *= r123;
			vec3 Sm = 2.0 * evalSensitivity( float( m ) * OPD, float( m ) * phi );
			I += Cm * Sm;
		}
		return max( I, vec3( 0.0 ) );
	}
#endif`,Rl=`#ifdef USE_BUMPMAP
	uniform sampler2D bumpMap;
	uniform float bumpScale;
	vec2 dHdxy_fwd() {
		vec2 dSTdx = dFdx( vBumpMapUv );
		vec2 dSTdy = dFdy( vBumpMapUv );
		float Hll = bumpScale * texture2D( bumpMap, vBumpMapUv ).x;
		float dBx = bumpScale * texture2D( bumpMap, vBumpMapUv + dSTdx ).x - Hll;
		float dBy = bumpScale * texture2D( bumpMap, vBumpMapUv + dSTdy ).x - Hll;
		return vec2( dBx, dBy );
	}
	vec3 perturbNormalArb( vec3 surf_pos, vec3 surf_norm, vec2 dHdxy, float faceDirection ) {
		vec3 vSigmaX = normalize( dFdx( surf_pos.xyz ) );
		vec3 vSigmaY = normalize( dFdy( surf_pos.xyz ) );
		vec3 vN = surf_norm;
		vec3 R1 = cross( vSigmaY, vN );
		vec3 R2 = cross( vN, vSigmaX );
		float fDet = dot( vSigmaX, R1 ) * faceDirection;
		vec3 vGrad = sign( fDet ) * ( dHdxy.x * R1 + dHdxy.y * R2 );
		return normalize( abs( fDet ) * surf_norm - vGrad );
	}
#endif`,Il=`#if NUM_CLIPPING_PLANES > 0
	vec4 plane;
	#ifdef ALPHA_TO_COVERAGE
		float distanceToPlane, distanceGradient;
		float clipOpacity = 1.0;
		#pragma unroll_loop_start
		for ( int i = 0; i < UNION_CLIPPING_PLANES; i ++ ) {
			plane = clippingPlanes[ i ];
			distanceToPlane = - dot( vClipPosition, plane.xyz ) + plane.w;
			distanceGradient = fwidth( distanceToPlane ) / 2.0;
			clipOpacity *= smoothstep( - distanceGradient, distanceGradient, distanceToPlane );
			if ( clipOpacity == 0.0 ) discard;
		}
		#pragma unroll_loop_end
		#if UNION_CLIPPING_PLANES < NUM_CLIPPING_PLANES
			float unionClipOpacity = 1.0;
			#pragma unroll_loop_start
			for ( int i = UNION_CLIPPING_PLANES; i < NUM_CLIPPING_PLANES; i ++ ) {
				plane = clippingPlanes[ i ];
				distanceToPlane = - dot( vClipPosition, plane.xyz ) + plane.w;
				distanceGradient = fwidth( distanceToPlane ) / 2.0;
				unionClipOpacity *= 1.0 - smoothstep( - distanceGradient, distanceGradient, distanceToPlane );
			}
			#pragma unroll_loop_end
			clipOpacity *= 1.0 - unionClipOpacity;
		#endif
		diffuseColor.a *= clipOpacity;
		if ( diffuseColor.a == 0.0 ) discard;
	#else
		#pragma unroll_loop_start
		for ( int i = 0; i < UNION_CLIPPING_PLANES; i ++ ) {
			plane = clippingPlanes[ i ];
			if ( dot( vClipPosition, plane.xyz ) > plane.w ) discard;
		}
		#pragma unroll_loop_end
		#if UNION_CLIPPING_PLANES < NUM_CLIPPING_PLANES
			bool clipped = true;
			#pragma unroll_loop_start
			for ( int i = UNION_CLIPPING_PLANES; i < NUM_CLIPPING_PLANES; i ++ ) {
				plane = clippingPlanes[ i ];
				clipped = ( dot( vClipPosition, plane.xyz ) > plane.w ) && clipped;
			}
			#pragma unroll_loop_end
			if ( clipped ) discard;
		#endif
	#endif
#endif`,Pl=`#if NUM_CLIPPING_PLANES > 0
	varying vec3 vClipPosition;
	uniform vec4 clippingPlanes[ NUM_CLIPPING_PLANES ];
#endif`,Nl=`#if NUM_CLIPPING_PLANES > 0
	varying vec3 vClipPosition;
#endif`,Ll=`#if NUM_CLIPPING_PLANES > 0
	vClipPosition = - mvPosition.xyz;
#endif`,Dl=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA )
	diffuseColor *= vColor;
#endif`,Ul=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA )
	varying vec4 vColor;
#endif`,Fl=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA ) || defined( USE_INSTANCING_COLOR ) || defined( USE_BATCHING_COLOR )
	varying vec4 vColor;
#endif`,Ol=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA ) || defined( USE_INSTANCING_COLOR ) || defined( USE_BATCHING_COLOR )
	vColor = vec4( 1.0 );
#endif
#ifdef USE_COLOR_ALPHA
	vColor *= color;
#elif defined( USE_COLOR )
	vColor.rgb *= color;
#endif
#ifdef USE_INSTANCING_COLOR
	vColor.rgb *= instanceColor.rgb;
#endif
#ifdef USE_BATCHING_COLOR
	vColor *= getBatchingColor( getIndirectIndex( gl_DrawID ) );
#endif`,Bl=`#define PI 3.141592653589793
#define PI2 6.283185307179586
#define PI_HALF 1.5707963267948966
#define RECIPROCAL_PI 0.3183098861837907
#define RECIPROCAL_PI2 0.15915494309189535
#define EPSILON 1e-6
#ifndef saturate
#define saturate( a ) clamp( a, 0.0, 1.0 )
#endif
#define whiteComplement( a ) ( 1.0 - saturate( a ) )
float pow2( const in float x ) { return x*x; }
vec3 pow2( const in vec3 x ) { return x*x; }
float pow3( const in float x ) { return x*x*x; }
float pow4( const in float x ) { float x2 = x*x; return x2*x2; }
float max3( const in vec3 v ) { return max( max( v.x, v.y ), v.z ); }
float average( const in vec3 v ) { return dot( v, vec3( 0.3333333 ) ); }
highp float rand( const in vec2 uv ) {
	const highp float a = 12.9898, b = 78.233, c = 43758.5453;
	highp float dt = dot( uv.xy, vec2( a,b ) ), sn = mod( dt, PI );
	return fract( sin( sn ) * c );
}
#ifdef HIGH_PRECISION
	float precisionSafeLength( vec3 v ) { return length( v ); }
#else
	float precisionSafeLength( vec3 v ) {
		float maxComponent = max3( abs( v ) );
		return length( v / maxComponent ) * maxComponent;
	}
#endif
struct IncidentLight {
	vec3 color;
	vec3 direction;
	bool visible;
};
struct ReflectedLight {
	vec3 directDiffuse;
	vec3 directSpecular;
	vec3 indirectDiffuse;
	vec3 indirectSpecular;
};
#ifdef USE_ALPHAHASH
	varying vec3 vPosition;
#endif
vec3 transformDirection( in vec3 dir, in mat4 matrix ) {
	return normalize( ( matrix * vec4( dir, 0.0 ) ).xyz );
}
#define inverseTransformDirection transformDirectionByInverseViewMatrix
vec3 transformNormalByInverseViewMatrix( in vec3 normal, in mat4 viewMatrix ) {
	return normalize( ( vec4( normal, 0.0 ) * viewMatrix ).xyz );
}
vec3 transformDirectionByInverseViewMatrix( in vec3 dir, in mat4 viewMatrix ) {
	return normalize( ( vec4( dir, 0.0 ) * viewMatrix ).xyz );
}
bool isPerspectiveMatrix( mat4 m ) {
	return m[ 2 ][ 3 ] == - 1.0;
}
vec2 equirectUv( in vec3 dir ) {
	float u = atan( dir.z, dir.x ) * RECIPROCAL_PI2 + 0.5;
	float v = asin( clamp( dir.y, - 1.0, 1.0 ) ) * RECIPROCAL_PI + 0.5;
	return vec2( u, v );
}
vec3 BRDF_Lambert( const in vec3 diffuseColor ) {
	return RECIPROCAL_PI * diffuseColor;
}
vec3 F_Schlick( const in vec3 f0, const in float f90, const in float dotVH ) {
	float fresnel = exp2( ( - 5.55473 * dotVH - 6.98316 ) * dotVH );
	return f0 * ( 1.0 - fresnel ) + ( f90 * fresnel );
}
float F_Schlick( const in float f0, const in float f90, const in float dotVH ) {
	float fresnel = exp2( ( - 5.55473 * dotVH - 6.98316 ) * dotVH );
	return f0 * ( 1.0 - fresnel ) + ( f90 * fresnel );
} // validated`,zl=`#ifdef ENVMAP_TYPE_CUBE_UV
	#define cubeUV_minMipLevel 4.0
	#define cubeUV_minTileSize 16.0
	float getFace( vec3 direction ) {
		vec3 absDirection = abs( direction );
		float face = - 1.0;
		if ( absDirection.x > absDirection.z ) {
			if ( absDirection.x > absDirection.y )
				face = direction.x > 0.0 ? 0.0 : 3.0;
			else
				face = direction.y > 0.0 ? 1.0 : 4.0;
		} else {
			if ( absDirection.z > absDirection.y )
				face = direction.z > 0.0 ? 2.0 : 5.0;
			else
				face = direction.y > 0.0 ? 1.0 : 4.0;
		}
		return face;
	}
	vec2 getUV( vec3 direction, float face ) {
		vec2 uv;
		if ( face == 0.0 ) {
			uv = vec2( direction.z, direction.y ) / abs( direction.x );
		} else if ( face == 1.0 ) {
			uv = vec2( - direction.x, - direction.z ) / abs( direction.y );
		} else if ( face == 2.0 ) {
			uv = vec2( - direction.x, direction.y ) / abs( direction.z );
		} else if ( face == 3.0 ) {
			uv = vec2( - direction.z, direction.y ) / abs( direction.x );
		} else if ( face == 4.0 ) {
			uv = vec2( - direction.x, direction.z ) / abs( direction.y );
		} else {
			uv = vec2( direction.x, direction.y ) / abs( direction.z );
		}
		return 0.5 * ( uv + 1.0 );
	}
	vec3 bilinearCubeUV( sampler2D envMap, vec3 direction, float mipInt ) {
		float face = getFace( direction );
		float filterInt = max( cubeUV_minMipLevel - mipInt, 0.0 );
		mipInt = max( mipInt, cubeUV_minMipLevel );
		float faceSize = exp2( mipInt );
		highp vec2 uv = getUV( direction, face ) * ( faceSize - 2.0 ) + 1.0;
		if ( face > 2.0 ) {
			uv.y += faceSize;
			face -= 3.0;
		}
		uv.x += face * faceSize;
		uv.x += filterInt * 3.0 * cubeUV_minTileSize;
		uv.y += 4.0 * ( exp2( CUBEUV_MAX_MIP ) - faceSize );
		uv.x *= CUBEUV_TEXEL_WIDTH;
		uv.y *= CUBEUV_TEXEL_HEIGHT;
		#ifdef texture2DGradEXT
			return texture2DGradEXT( envMap, uv, vec2( 0.0 ), vec2( 0.0 ) ).rgb;
		#else
			return texture2D( envMap, uv ).rgb;
		#endif
	}
	#define cubeUV_r0 1.0
	#define cubeUV_m0 - 2.0
	#define cubeUV_r1 0.8
	#define cubeUV_m1 - 1.0
	#define cubeUV_r4 0.4
	#define cubeUV_m4 2.0
	#define cubeUV_r5 0.305
	#define cubeUV_m5 3.0
	#define cubeUV_r6 0.21
	#define cubeUV_m6 4.0
	float roughnessToMip( float roughness ) {
		float mip = 0.0;
		if ( roughness >= cubeUV_r1 ) {
			mip = ( cubeUV_r0 - roughness ) * ( cubeUV_m1 - cubeUV_m0 ) / ( cubeUV_r0 - cubeUV_r1 ) + cubeUV_m0;
		} else if ( roughness >= cubeUV_r4 ) {
			mip = ( cubeUV_r1 - roughness ) * ( cubeUV_m4 - cubeUV_m1 ) / ( cubeUV_r1 - cubeUV_r4 ) + cubeUV_m1;
		} else if ( roughness >= cubeUV_r5 ) {
			mip = ( cubeUV_r4 - roughness ) * ( cubeUV_m5 - cubeUV_m4 ) / ( cubeUV_r4 - cubeUV_r5 ) + cubeUV_m4;
		} else if ( roughness >= cubeUV_r6 ) {
			mip = ( cubeUV_r5 - roughness ) * ( cubeUV_m6 - cubeUV_m5 ) / ( cubeUV_r5 - cubeUV_r6 ) + cubeUV_m5;
		} else {
			mip = - 2.0 * log2( 1.16 * roughness );		}
		return mip;
	}
	vec4 textureCubeUV( sampler2D envMap, vec3 sampleDir, float roughness ) {
		float mip = clamp( roughnessToMip( roughness ), cubeUV_m0, CUBEUV_MAX_MIP );
		float mipF = fract( mip );
		float mipInt = floor( mip );
		vec3 color0 = bilinearCubeUV( envMap, sampleDir, mipInt );
		if ( mipF == 0.0 ) {
			return vec4( color0, 1.0 );
		} else {
			vec3 color1 = bilinearCubeUV( envMap, sampleDir, mipInt + 1.0 );
			return vec4( mix( color0, color1, mipF ), 1.0 );
		}
	}
#endif`,kl=`vec3 transformedNormal = objectNormal;
#ifdef USE_TANGENT
	vec3 transformedTangent = objectTangent;
#endif
#ifdef USE_BATCHING
	mat3 bm = mat3( batchingMatrix );
	transformedNormal /= vec3( dot( bm[ 0 ], bm[ 0 ] ), dot( bm[ 1 ], bm[ 1 ] ), dot( bm[ 2 ], bm[ 2 ] ) );
	transformedNormal = bm * transformedNormal;
	#ifdef USE_TANGENT
		transformedTangent = bm * transformedTangent;
	#endif
#endif
#ifdef USE_INSTANCING
	mat3 im = mat3( instanceMatrix );
	transformedNormal /= vec3( dot( im[ 0 ], im[ 0 ] ), dot( im[ 1 ], im[ 1 ] ), dot( im[ 2 ], im[ 2 ] ) );
	transformedNormal = im * transformedNormal;
	#ifdef USE_TANGENT
		transformedTangent = im * transformedTangent;
	#endif
#endif
transformedNormal = normalMatrix * transformedNormal;
#ifdef FLIP_SIDED
	transformedNormal = - transformedNormal;
#endif
#ifdef USE_TANGENT
	transformedTangent = ( modelViewMatrix * vec4( transformedTangent, 0.0 ) ).xyz;
#endif`,Vl=`#ifdef USE_DISPLACEMENTMAP
	uniform sampler2D displacementMap;
	uniform float displacementScale;
	uniform float displacementBias;
#endif`,Gl=`#ifdef USE_DISPLACEMENTMAP
	transformed += normalize( objectNormal ) * ( texture2D( displacementMap, vDisplacementMapUv ).x * displacementScale + displacementBias );
#endif`,Hl=`#ifdef USE_EMISSIVEMAP
	vec4 emissiveColor = texture2D( emissiveMap, vEmissiveMapUv );
	#ifdef DECODE_VIDEO_TEXTURE_EMISSIVE
		emissiveColor = sRGBTransferEOTF( emissiveColor );
	#endif
	totalEmissiveRadiance *= emissiveColor.rgb;
#endif`,Wl=`#ifdef USE_EMISSIVEMAP
	uniform sampler2D emissiveMap;
#endif`,Xl="gl_FragColor = linearToOutputTexel( gl_FragColor );",ql=`vec4 LinearTransferOETF( in vec4 value ) {
	return value;
}
vec4 sRGBTransferEOTF( in vec4 value ) {
	return vec4( mix( pow( value.rgb * 0.9478672986 + vec3( 0.0521327014 ), vec3( 2.4 ) ), value.rgb * 0.0773993808, vec3( lessThanEqual( value.rgb, vec3( 0.04045 ) ) ) ), value.a );
}
vec4 sRGBTransferOETF( in vec4 value ) {
	return vec4( mix( pow( value.rgb, vec3( 0.41666 ) ) * 1.055 - vec3( 0.055 ), value.rgb * 12.92, vec3( lessThanEqual( value.rgb, vec3( 0.0031308 ) ) ) ), value.a );
}`,$l=`#ifdef USE_ENVMAP
	#ifdef ENV_WORLDPOS
		vec3 cameraToFrag;
		if ( isOrthographic ) {
			cameraToFrag = normalize( vec3( - viewMatrix[ 0 ][ 2 ], - viewMatrix[ 1 ][ 2 ], - viewMatrix[ 2 ][ 2 ] ) );
		} else {
			cameraToFrag = normalize( vWorldPosition - cameraPosition );
		}
		vec3 worldNormal = transformNormalByInverseViewMatrix( normal, viewMatrix );
		#ifdef ENVMAP_MODE_REFLECTION
			vec3 reflectVec = reflect( cameraToFrag, worldNormal );
		#else
			vec3 reflectVec = refract( cameraToFrag, worldNormal, refractionRatio );
		#endif
	#else
		vec3 reflectVec = vReflect;
	#endif
	#ifdef ENVMAP_TYPE_CUBE
		vec4 envColor = textureCube( envMap, envMapRotation * reflectVec );
		#ifdef ENVMAP_BLENDING_MULTIPLY
			outgoingLight = mix( outgoingLight, outgoingLight * envColor.xyz, specularStrength * reflectivity );
		#elif defined( ENVMAP_BLENDING_MIX )
			outgoingLight = mix( outgoingLight, envColor.xyz, specularStrength * reflectivity );
		#elif defined( ENVMAP_BLENDING_ADD )
			outgoingLight += envColor.xyz * specularStrength * reflectivity;
		#endif
	#endif
#endif`,Yl=`#ifdef USE_ENVMAP
	uniform float envMapIntensity;
	uniform mat3 envMapRotation;
	#ifdef ENVMAP_TYPE_CUBE
		uniform samplerCube envMap;
	#else
		uniform sampler2D envMap;
	#endif
#endif`,Zl=`#ifdef USE_ENVMAP
	uniform float reflectivity;
	#if defined( USE_BUMPMAP ) || defined( USE_NORMALMAP ) || defined( PHONG ) || defined( LAMBERT )
		#define ENV_WORLDPOS
	#endif
	#ifdef ENV_WORLDPOS
		varying vec3 vWorldPosition;
		uniform float refractionRatio;
	#else
		varying vec3 vReflect;
	#endif
#endif`,Jl=`#ifdef USE_ENVMAP
	#if defined( USE_BUMPMAP ) || defined( USE_NORMALMAP ) || defined( PHONG ) || defined( LAMBERT )
		#define ENV_WORLDPOS
	#endif
	#ifdef ENV_WORLDPOS
		
		varying vec3 vWorldPosition;
	#else
		varying vec3 vReflect;
		uniform float refractionRatio;
	#endif
#endif`,Kl=`#ifdef USE_ENVMAP
	#ifdef ENV_WORLDPOS
		vWorldPosition = worldPosition.xyz;
	#else
		vec3 cameraToVertex;
		if ( isOrthographic ) {
			cameraToVertex = normalize( vec3( - viewMatrix[ 0 ][ 2 ], - viewMatrix[ 1 ][ 2 ], - viewMatrix[ 2 ][ 2 ] ) );
		} else {
			cameraToVertex = normalize( worldPosition.xyz - cameraPosition );
		}
		vec3 worldNormal = transformNormalByInverseViewMatrix( transformedNormal, viewMatrix );
		#ifdef ENVMAP_MODE_REFLECTION
			vReflect = reflect( cameraToVertex, worldNormal );
		#else
			vReflect = refract( cameraToVertex, worldNormal, refractionRatio );
		#endif
	#endif
#endif`,jl=`#ifdef USE_FOG
	vFogDepth = - mvPosition.z;
#endif`,Ql=`#ifdef USE_FOG
	varying float vFogDepth;
#endif`,tu=`#ifdef USE_FOG
	#ifdef FOG_EXP2
		float fogFactor = 1.0 - exp( - fogDensity * fogDensity * vFogDepth * vFogDepth );
	#else
		float fogFactor = smoothstep( fogNear, fogFar, vFogDepth );
	#endif
	gl_FragColor.rgb = mix( gl_FragColor.rgb, fogColor, fogFactor );
#endif`,eu=`#ifdef USE_FOG
	uniform vec3 fogColor;
	varying float vFogDepth;
	#ifdef FOG_EXP2
		uniform float fogDensity;
	#else
		uniform float fogNear;
		uniform float fogFar;
	#endif
#endif`,nu=`#ifdef USE_GRADIENTMAP
	uniform sampler2D gradientMap;
#endif
vec3 getGradientIrradiance( vec3 normal, vec3 lightDirection ) {
	float dotNL = dot( normal, lightDirection );
	vec2 coord = vec2( dotNL * 0.5 + 0.5, 0.0 );
	#ifdef USE_GRADIENTMAP
		return vec3( texture2D( gradientMap, coord ).r );
	#else
		vec2 fw = fwidth( coord ) * 0.5;
		return mix( vec3( 0.7 ), vec3( 1.0 ), smoothstep( 0.7 - fw.x, 0.7 + fw.x, coord.x ) );
	#endif
}`,iu=`#ifdef USE_LIGHTMAP
	uniform sampler2D lightMap;
	uniform float lightMapIntensity;
#endif`,su=`LambertMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.specularStrength = specularStrength;`,ru=`varying vec3 vViewPosition;
struct LambertMaterial {
	vec3 diffuseColor;
	float specularStrength;
};
void RE_Direct_Lambert( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in LambertMaterial material, inout ReflectedLight reflectedLight ) {
	float dotNL = saturate( dot( geometryNormal, directLight.direction ) );
	vec3 irradiance = dotNL * directLight.color;
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
void RE_IndirectDiffuse_Lambert( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in LambertMaterial material, inout ReflectedLight reflectedLight ) {
	reflectedLight.indirectDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
#define RE_Direct				RE_Direct_Lambert
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Lambert`,ou=`uniform bool receiveShadow;
uniform vec3 ambientLightColor;
#if defined( USE_LIGHT_PROBES )
	uniform vec3 lightProbe[ 9 ];
#endif
vec3 shGetIrradianceAt( in vec3 normal, in vec3 shCoefficients[ 9 ] ) {
	float x = normal.x, y = normal.y, z = normal.z;
	vec3 result = shCoefficients[ 0 ] * 0.886227;
	result += shCoefficients[ 1 ] * 2.0 * 0.511664 * y;
	result += shCoefficients[ 2 ] * 2.0 * 0.511664 * z;
	result += shCoefficients[ 3 ] * 2.0 * 0.511664 * x;
	result += shCoefficients[ 4 ] * 2.0 * 0.429043 * x * y;
	result += shCoefficients[ 5 ] * 2.0 * 0.429043 * y * z;
	result += shCoefficients[ 6 ] * ( 0.743125 * z * z - 0.247708 );
	result += shCoefficients[ 7 ] * 2.0 * 0.429043 * x * z;
	result += shCoefficients[ 8 ] * 0.429043 * ( x * x - y * y );
	return result;
}
vec3 getLightProbeIrradiance( const in vec3 lightProbe[ 9 ], const in vec3 normal ) {
	vec3 worldNormal = transformNormalByInverseViewMatrix( normal, viewMatrix );
	vec3 irradiance = shGetIrradianceAt( worldNormal, lightProbe );
	return irradiance;
}
vec3 getAmbientLightIrradiance( const in vec3 ambientLightColor ) {
	vec3 irradiance = ambientLightColor;
	return irradiance;
}
float getDistanceAttenuation( const in float lightDistance, const in float cutoffDistance, const in float decayExponent ) {
	float distanceFalloff = 1.0 / max( pow( lightDistance, decayExponent ), 0.01 );
	if ( cutoffDistance > 0.0 ) {
		distanceFalloff *= pow2( saturate( 1.0 - pow4( lightDistance / cutoffDistance ) ) );
	}
	return distanceFalloff;
}
float getSpotAttenuation( const in float coneCosine, const in float penumbraCosine, const in float angleCosine ) {
	return smoothstep( coneCosine, penumbraCosine, angleCosine );
}
#if NUM_DIR_LIGHTS > 0
	struct DirectionalLight {
		vec3 direction;
		vec3 color;
	};
	uniform DirectionalLight directionalLights[ NUM_DIR_LIGHTS ];
	void getDirectionalLightInfo( const in DirectionalLight directionalLight, out IncidentLight light ) {
		light.color = directionalLight.color;
		light.direction = directionalLight.direction;
		light.visible = true;
	}
#endif
#if NUM_POINT_LIGHTS > 0
	struct PointLight {
		vec3 position;
		vec3 color;
		float distance;
		float decay;
	};
	uniform PointLight pointLights[ NUM_POINT_LIGHTS ];
	void getPointLightInfo( const in PointLight pointLight, const in vec3 geometryPosition, out IncidentLight light ) {
		vec3 lVector = pointLight.position - geometryPosition;
		light.direction = normalize( lVector );
		float lightDistance = length( lVector );
		light.color = pointLight.color;
		light.color *= getDistanceAttenuation( lightDistance, pointLight.distance, pointLight.decay );
		light.visible = ( light.color != vec3( 0.0 ) );
	}
#endif
#if NUM_SPOT_LIGHTS > 0
	struct SpotLight {
		vec3 position;
		vec3 direction;
		vec3 color;
		float distance;
		float decay;
		float coneCos;
		float penumbraCos;
	};
	uniform SpotLight spotLights[ NUM_SPOT_LIGHTS ];
	void getSpotLightInfo( const in SpotLight spotLight, const in vec3 geometryPosition, out IncidentLight light ) {
		vec3 lVector = spotLight.position - geometryPosition;
		light.direction = normalize( lVector );
		float angleCos = dot( light.direction, spotLight.direction );
		float spotAttenuation = getSpotAttenuation( spotLight.coneCos, spotLight.penumbraCos, angleCos );
		if ( spotAttenuation > 0.0 ) {
			float lightDistance = length( lVector );
			light.color = spotLight.color * spotAttenuation;
			light.color *= getDistanceAttenuation( lightDistance, spotLight.distance, spotLight.decay );
			light.visible = ( light.color != vec3( 0.0 ) );
		} else {
			light.color = vec3( 0.0 );
			light.visible = false;
		}
	}
#endif
#if NUM_RECT_AREA_LIGHTS > 0
	struct RectAreaLight {
		vec3 color;
		vec3 position;
		vec3 halfWidth;
		vec3 halfHeight;
	};
	uniform sampler2D ltc_1;	uniform sampler2D ltc_2;
	uniform RectAreaLight rectAreaLights[ NUM_RECT_AREA_LIGHTS ];
#endif
#if NUM_HEMI_LIGHTS > 0
	struct HemisphereLight {
		vec3 direction;
		vec3 skyColor;
		vec3 groundColor;
	};
	uniform HemisphereLight hemisphereLights[ NUM_HEMI_LIGHTS ];
	vec3 getHemisphereLightIrradiance( const in HemisphereLight hemiLight, const in vec3 normal ) {
		float dotNL = dot( normal, hemiLight.direction );
		float hemiDiffuseWeight = 0.5 * dotNL + 0.5;
		vec3 irradiance = mix( hemiLight.groundColor, hemiLight.skyColor, hemiDiffuseWeight );
		return irradiance;
	}
#endif
#include <lightprobes_pars_fragment>`,au=`#ifdef USE_ENVMAP
	vec3 getIBLIrradiance( const in vec3 normal ) {
		#ifdef ENVMAP_TYPE_CUBE_UV
			vec3 worldNormal = transformNormalByInverseViewMatrix( normal, viewMatrix );
			vec4 envMapColor = textureCubeUV( envMap, envMapRotation * worldNormal, 1.0 );
			return PI * envMapColor.rgb * envMapIntensity;
		#else
			return vec3( 0.0 );
		#endif
	}
	vec3 getIBLRadiance( const in vec3 viewDir, const in vec3 normal, const in float roughness ) {
		#ifdef ENVMAP_TYPE_CUBE_UV
			vec3 reflectVec = reflect( - viewDir, normal );
			reflectVec = normalize( mix( reflectVec, normal, pow4( roughness ) ) );
			reflectVec = transformDirectionByInverseViewMatrix( reflectVec, viewMatrix );
			vec4 envMapColor = textureCubeUV( envMap, envMapRotation * reflectVec, roughness );
			return envMapColor.rgb * envMapIntensity;
		#else
			return vec3( 0.0 );
		#endif
	}
	#ifdef USE_ANISOTROPY
		vec3 getIBLAnisotropyRadiance( const in vec3 viewDir, const in vec3 normal, const in float roughness, const in vec3 bitangent, const in float anisotropy ) {
			#ifdef ENVMAP_TYPE_CUBE_UV
				vec3 bentNormal = cross( bitangent, viewDir );
				bentNormal = normalize( cross( bentNormal, bitangent ) );
				bentNormal = normalize( mix( bentNormal, normal, pow2( pow2( 1.0 - anisotropy * ( 1.0 - roughness ) ) ) ) );
				return getIBLRadiance( viewDir, bentNormal, roughness );
			#else
				return vec3( 0.0 );
			#endif
		}
	#endif
#endif`,cu=`ToonMaterial material;
material.diffuseColor = diffuseColor.rgb;`,lu=`varying vec3 vViewPosition;
struct ToonMaterial {
	vec3 diffuseColor;
};
void RE_Direct_Toon( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in ToonMaterial material, inout ReflectedLight reflectedLight ) {
	vec3 irradiance = getGradientIrradiance( geometryNormal, directLight.direction ) * directLight.color;
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
void RE_IndirectDiffuse_Toon( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in ToonMaterial material, inout ReflectedLight reflectedLight ) {
	reflectedLight.indirectDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
#define RE_Direct				RE_Direct_Toon
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Toon`,uu=`BlinnPhongMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.specularColor = specular;
material.specularShininess = shininess;
material.specularStrength = specularStrength;`,hu=`varying vec3 vViewPosition;
struct BlinnPhongMaterial {
	vec3 diffuseColor;
	vec3 specularColor;
	float specularShininess;
	float specularStrength;
};
void RE_Direct_BlinnPhong( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in BlinnPhongMaterial material, inout ReflectedLight reflectedLight ) {
	float dotNL = saturate( dot( geometryNormal, directLight.direction ) );
	vec3 irradiance = dotNL * directLight.color;
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
	reflectedLight.directSpecular += irradiance * BRDF_BlinnPhong( directLight.direction, geometryViewDir, geometryNormal, material.specularColor, material.specularShininess ) * material.specularStrength;
}
void RE_IndirectDiffuse_BlinnPhong( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in BlinnPhongMaterial material, inout ReflectedLight reflectedLight ) {
	reflectedLight.indirectDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
#define RE_Direct				RE_Direct_BlinnPhong
#define RE_IndirectDiffuse		RE_IndirectDiffuse_BlinnPhong`,fu=`PhysicalMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.diffuseContribution = diffuseColor.rgb * ( 1.0 - metalnessFactor );
material.metalness = metalnessFactor;
vec3 dxy = max( abs( dFdx( nonPerturbedNormal ) ), abs( dFdy( nonPerturbedNormal ) ) );
float geometryRoughness = max( max( dxy.x, dxy.y ), dxy.z );
material.roughness = max( roughnessFactor, 0.0525 );material.roughness += geometryRoughness;
material.roughness = min( material.roughness, 1.0 );
#ifdef IOR
	material.ior = ior;
	#ifdef USE_SPECULAR
		float specularIntensityFactor = specularIntensity;
		vec3 specularColorFactor = specularColor;
		#ifdef USE_SPECULAR_COLORMAP
			specularColorFactor *= texture2D( specularColorMap, vSpecularColorMapUv ).rgb;
		#endif
		#ifdef USE_SPECULAR_INTENSITYMAP
			specularIntensityFactor *= texture2D( specularIntensityMap, vSpecularIntensityMapUv ).a;
		#endif
		material.specularF90 = mix( specularIntensityFactor, 1.0, metalnessFactor );
	#else
		float specularIntensityFactor = 1.0;
		vec3 specularColorFactor = vec3( 1.0 );
		material.specularF90 = 1.0;
	#endif
	material.specularColor = min( pow2( ( material.ior - 1.0 ) / ( material.ior + 1.0 ) ) * specularColorFactor, vec3( 1.0 ) ) * specularIntensityFactor;
	material.specularColorBlended = mix( material.specularColor, diffuseColor.rgb, metalnessFactor );
#else
	material.specularColor = vec3( 0.04 );
	material.specularColorBlended = mix( material.specularColor, diffuseColor.rgb, metalnessFactor );
	material.specularF90 = 1.0;
#endif
#ifdef USE_CLEARCOAT
	material.clearcoat = clearcoat;
	material.clearcoatRoughness = clearcoatRoughness;
	material.clearcoatF0 = vec3( 0.04 );
	material.clearcoatF90 = 1.0;
	#ifdef USE_CLEARCOATMAP
		material.clearcoat *= texture2D( clearcoatMap, vClearcoatMapUv ).x;
	#endif
	#ifdef USE_CLEARCOAT_ROUGHNESSMAP
		material.clearcoatRoughness *= texture2D( clearcoatRoughnessMap, vClearcoatRoughnessMapUv ).y;
	#endif
	material.clearcoat = saturate( material.clearcoat );	material.clearcoatRoughness = max( material.clearcoatRoughness, 0.0525 );
	material.clearcoatRoughness += geometryRoughness;
	material.clearcoatRoughness = min( material.clearcoatRoughness, 1.0 );
#endif
#ifdef USE_DISPERSION
	material.dispersion = dispersion;
#endif
#ifdef USE_IRIDESCENCE
	material.iridescence = iridescence;
	material.iridescenceIOR = iridescenceIOR;
	#ifdef USE_IRIDESCENCEMAP
		material.iridescence *= texture2D( iridescenceMap, vIridescenceMapUv ).r;
	#endif
	#ifdef USE_IRIDESCENCE_THICKNESSMAP
		material.iridescenceThickness = (iridescenceThicknessMaximum - iridescenceThicknessMinimum) * texture2D( iridescenceThicknessMap, vIridescenceThicknessMapUv ).g + iridescenceThicknessMinimum;
	#else
		material.iridescenceThickness = iridescenceThicknessMaximum;
	#endif
#endif
#ifdef USE_SHEEN
	material.sheenColor = sheenColor;
	#ifdef USE_SHEEN_COLORMAP
		material.sheenColor *= texture2D( sheenColorMap, vSheenColorMapUv ).rgb;
	#endif
	material.sheenRoughness = clamp( sheenRoughness, 0.0001, 1.0 );
	#ifdef USE_SHEEN_ROUGHNESSMAP
		material.sheenRoughness *= texture2D( sheenRoughnessMap, vSheenRoughnessMapUv ).a;
	#endif
#endif
#ifdef USE_ANISOTROPY
	#ifdef USE_ANISOTROPYMAP
		mat2 anisotropyMat = mat2( anisotropyVector.x, anisotropyVector.y, - anisotropyVector.y, anisotropyVector.x );
		vec3 anisotropyPolar = texture2D( anisotropyMap, vAnisotropyMapUv ).rgb;
		vec2 anisotropyV = anisotropyMat * normalize( 2.0 * anisotropyPolar.rg - vec2( 1.0 ) ) * anisotropyPolar.b;
	#else
		vec2 anisotropyV = anisotropyVector;
	#endif
	material.anisotropy = length( anisotropyV );
	if( material.anisotropy == 0.0 ) {
		anisotropyV = vec2( 1.0, 0.0 );
	} else {
		anisotropyV /= material.anisotropy;
		material.anisotropy = saturate( material.anisotropy );
	}
	material.alphaT = mix( pow2( material.roughness ), 1.0, pow2( material.anisotropy ) );
	material.anisotropyT = tbn[ 0 ] * anisotropyV.x + tbn[ 1 ] * anisotropyV.y;
	material.anisotropyB = tbn[ 1 ] * anisotropyV.x - tbn[ 0 ] * anisotropyV.y;
#endif`,du=`uniform sampler2D dfgLUT;
struct PhysicalMaterial {
	vec3 diffuseColor;
	vec3 diffuseContribution;
	vec3 specularColor;
	vec3 specularColorBlended;
	float roughness;
	float metalness;
	float specularF90;
	float dispersion;
	#ifdef USE_CLEARCOAT
		float clearcoat;
		float clearcoatRoughness;
		vec3 clearcoatF0;
		float clearcoatF90;
	#endif
	#ifdef USE_IRIDESCENCE
		float iridescence;
		float iridescenceIOR;
		float iridescenceThickness;
		vec3 iridescenceFresnel;
		vec3 iridescenceF0;
		vec3 iridescenceFresnelDielectric;
		vec3 iridescenceFresnelMetallic;
	#endif
	#ifdef USE_SHEEN
		vec3 sheenColor;
		float sheenRoughness;
	#endif
	#ifdef IOR
		float ior;
	#endif
	#ifdef USE_TRANSMISSION
		float transmission;
		float transmissionAlpha;
		float thickness;
		float attenuationDistance;
		vec3 attenuationColor;
	#endif
	#ifdef USE_ANISOTROPY
		float anisotropy;
		float alphaT;
		vec3 anisotropyT;
		vec3 anisotropyB;
	#endif
};
vec3 clearcoatSpecularDirect = vec3( 0.0 );
vec3 clearcoatSpecularIndirect = vec3( 0.0 );
vec3 sheenSpecularDirect = vec3( 0.0 );
vec3 sheenSpecularIndirect = vec3(0.0 );
vec3 Schlick_to_F0( const in vec3 f, const in float f90, const in float dotVH ) {
    float x = clamp( 1.0 - dotVH, 0.0, 1.0 );
    float x2 = x * x;
    float x5 = clamp( x * x2 * x2, 0.0, 0.9999 );
    return ( f - vec3( f90 ) * x5 ) / ( 1.0 - x5 );
}
float V_GGX_SmithCorrelated( const in float alpha, const in float dotNL, const in float dotNV ) {
	float a2 = pow2( alpha );
	float gv = dotNL * sqrt( a2 + ( 1.0 - a2 ) * pow2( dotNV ) );
	float gl = dotNV * sqrt( a2 + ( 1.0 - a2 ) * pow2( dotNL ) );
	return 0.5 / max( gv + gl, EPSILON );
}
float D_GGX( const in float alpha, const in float dotNH ) {
	float a2 = pow2( alpha );
	float denom = pow2( dotNH ) * ( a2 - 1.0 ) + 1.0;
	return RECIPROCAL_PI * a2 / pow2( denom );
}
#ifdef USE_ANISOTROPY
	float V_GGX_SmithCorrelated_Anisotropic( const in float alphaT, const in float alphaB, const in float dotTV, const in float dotBV, const in float dotTL, const in float dotBL, const in float dotNV, const in float dotNL ) {
		float gv = dotNL * length( vec3( alphaT * dotTV, alphaB * dotBV, dotNV ) );
		float gl = dotNV * length( vec3( alphaT * dotTL, alphaB * dotBL, dotNL ) );
		return 0.5 / max( gv + gl, EPSILON );
	}
	float D_GGX_Anisotropic( const in float alphaT, const in float alphaB, const in float dotNH, const in float dotTH, const in float dotBH ) {
		float a2 = alphaT * alphaB;
		highp vec3 v = vec3( alphaB * dotTH, alphaT * dotBH, a2 * dotNH );
		highp float v2 = dot( v, v );
		float w2 = a2 / v2;
		return RECIPROCAL_PI * a2 * pow2 ( w2 );
	}
#endif
#ifdef USE_CLEARCOAT
	vec3 BRDF_GGX_Clearcoat( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in PhysicalMaterial material) {
		vec3 f0 = material.clearcoatF0;
		float f90 = material.clearcoatF90;
		float roughness = material.clearcoatRoughness;
		float alpha = pow2( roughness );
		vec3 halfDir = normalize( lightDir + viewDir );
		float dotNL = saturate( dot( normal, lightDir ) );
		float dotNV = saturate( dot( normal, viewDir ) );
		float dotNH = saturate( dot( normal, halfDir ) );
		float dotVH = saturate( dot( viewDir, halfDir ) );
		vec3 F = F_Schlick( f0, f90, dotVH );
		float V = V_GGX_SmithCorrelated( alpha, dotNL, dotNV );
		float D = D_GGX( alpha, dotNH );
		return F * ( V * D );
	}
#endif
vec3 BRDF_GGX( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in PhysicalMaterial material ) {
	vec3 f0 = material.specularColorBlended;
	float f90 = material.specularF90;
	float roughness = material.roughness;
	float alpha = pow2( roughness );
	vec3 halfDir = normalize( lightDir + viewDir );
	float dotNL = saturate( dot( normal, lightDir ) );
	float dotNV = saturate( dot( normal, viewDir ) );
	float dotNH = saturate( dot( normal, halfDir ) );
	float dotVH = saturate( dot( viewDir, halfDir ) );
	vec3 F = F_Schlick( f0, f90, dotVH );
	#ifdef USE_IRIDESCENCE
		F = mix( F, material.iridescenceFresnel, material.iridescence );
	#endif
	#ifdef USE_ANISOTROPY
		float dotTL = dot( material.anisotropyT, lightDir );
		float dotTV = dot( material.anisotropyT, viewDir );
		float dotTH = dot( material.anisotropyT, halfDir );
		float dotBL = dot( material.anisotropyB, lightDir );
		float dotBV = dot( material.anisotropyB, viewDir );
		float dotBH = dot( material.anisotropyB, halfDir );
		float V = V_GGX_SmithCorrelated_Anisotropic( material.alphaT, alpha, dotTV, dotBV, dotTL, dotBL, dotNV, dotNL );
		float D = D_GGX_Anisotropic( material.alphaT, alpha, dotNH, dotTH, dotBH );
	#else
		float V = V_GGX_SmithCorrelated( alpha, dotNL, dotNV );
		float D = D_GGX( alpha, dotNH );
	#endif
	return F * ( V * D );
}
vec2 LTC_Uv( const in vec3 N, const in vec3 V, const in float roughness ) {
	const float LUT_SIZE = 64.0;
	const float LUT_SCALE = ( LUT_SIZE - 1.0 ) / LUT_SIZE;
	const float LUT_BIAS = 0.5 / LUT_SIZE;
	float dotNV = saturate( dot( N, V ) );
	vec2 uv = vec2( roughness, sqrt( 1.0 - dotNV ) );
	uv = uv * LUT_SCALE + LUT_BIAS;
	return uv;
}
float LTC_ClippedSphereFormFactor( const in vec3 f ) {
	float l = length( f );
	return max( ( l * l + f.z ) / ( l + 1.0 ), 0.0 );
}
vec3 LTC_EdgeVectorFormFactor( const in vec3 v1, const in vec3 v2 ) {
	float x = dot( v1, v2 );
	float y = abs( x );
	float a = 0.8543985 + ( 0.4965155 + 0.0145206 * y ) * y;
	float b = 3.4175940 + ( 4.1616724 + y ) * y;
	float v = a / b;
	float theta_sintheta = ( x > 0.0 ) ? v : 0.5 * inversesqrt( max( 1.0 - x * x, 1e-7 ) ) - v;
	return cross( v1, v2 ) * theta_sintheta;
}
vec3 LTC_Evaluate( const in vec3 N, const in vec3 V, const in vec3 P, const in mat3 mInv, const in vec3 rectCoords[ 4 ] ) {
	vec3 v1 = rectCoords[ 1 ] - rectCoords[ 0 ];
	vec3 v2 = rectCoords[ 3 ] - rectCoords[ 0 ];
	vec3 lightNormal = cross( v1, v2 );
	if( dot( lightNormal, P - rectCoords[ 0 ] ) < 0.0 ) return vec3( 0.0 );
	vec3 T1, T2;
	T1 = normalize( V - N * dot( V, N ) );
	T2 = - cross( N, T1 );
	mat3 mat = mInv * transpose( mat3( T1, T2, N ) );
	vec3 coords[ 4 ];
	coords[ 0 ] = mat * ( rectCoords[ 0 ] - P );
	coords[ 1 ] = mat * ( rectCoords[ 1 ] - P );
	coords[ 2 ] = mat * ( rectCoords[ 2 ] - P );
	coords[ 3 ] = mat * ( rectCoords[ 3 ] - P );
	coords[ 0 ] = normalize( coords[ 0 ] );
	coords[ 1 ] = normalize( coords[ 1 ] );
	coords[ 2 ] = normalize( coords[ 2 ] );
	coords[ 3 ] = normalize( coords[ 3 ] );
	vec3 vectorFormFactor = vec3( 0.0 );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 0 ], coords[ 1 ] );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 1 ], coords[ 2 ] );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 2 ], coords[ 3 ] );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 3 ], coords[ 0 ] );
	float result = LTC_ClippedSphereFormFactor( vectorFormFactor );
	return vec3( result );
}
#if defined( USE_SHEEN )
float D_Charlie( float roughness, float dotNH ) {
	float alpha = pow2( roughness );
	float invAlpha = 1.0 / alpha;
	float cos2h = dotNH * dotNH;
	float sin2h = max( 1.0 - cos2h, 0.0078125 );
	return ( 2.0 + invAlpha ) * pow( sin2h, invAlpha * 0.5 ) / ( 2.0 * PI );
}
float V_Neubelt( float dotNV, float dotNL ) {
	return saturate( 1.0 / ( 4.0 * ( dotNL + dotNV - dotNL * dotNV ) ) );
}
vec3 BRDF_Sheen( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, vec3 sheenColor, const in float sheenRoughness ) {
	vec3 halfDir = normalize( lightDir + viewDir );
	float dotNL = saturate( dot( normal, lightDir ) );
	float dotNV = saturate( dot( normal, viewDir ) );
	float dotNH = saturate( dot( normal, halfDir ) );
	float D = D_Charlie( sheenRoughness, dotNH );
	float V = V_Neubelt( dotNV, dotNL );
	return sheenColor * ( D * V );
}
#endif
float IBLSheenBRDF( const in vec3 normal, const in vec3 viewDir, const in float roughness ) {
	float dotNV = saturate( dot( normal, viewDir ) );
	float r2 = roughness * roughness;
	float rInv = 1.0 / ( roughness + 0.1 );
	float a = -1.9362 + 1.0678 * roughness + 0.4573 * r2 - 0.8469 * rInv;
	float b = -0.6014 + 0.5538 * roughness - 0.4670 * r2 - 0.1255 * rInv;
	float DG = exp( a * dotNV + b );
	return saturate( DG );
}
vec3 EnvironmentBRDF( const in vec3 normal, const in vec3 viewDir, const in vec3 specularColor, const in float specularF90, const in float roughness ) {
	float dotNV = saturate( dot( normal, viewDir ) );
	vec2 fab = texture2D( dfgLUT, vec2( roughness, dotNV ) ).rg;
	return specularColor * fab.x + specularF90 * fab.y;
}
#ifdef USE_IRIDESCENCE
void computeMultiscatteringIridescence( const in vec3 normal, const in vec3 viewDir, const in vec3 specularColor, const in float specularF90, const in float iridescence, const in vec3 iridescenceF0, const in float roughness, inout vec3 singleScatter, inout vec3 multiScatter ) {
#else
void computeMultiscattering( const in vec3 normal, const in vec3 viewDir, const in vec3 specularColor, const in float specularF90, const in float roughness, inout vec3 singleScatter, inout vec3 multiScatter ) {
#endif
	float dotNV = saturate( dot( normal, viewDir ) );
	vec2 fab = texture2D( dfgLUT, vec2( roughness, dotNV ) ).rg;
	#ifdef USE_IRIDESCENCE
		vec3 Fr = mix( specularColor, iridescenceF0, iridescence );
	#else
		vec3 Fr = specularColor;
	#endif
	vec3 FssEss = Fr * fab.x + specularF90 * fab.y;
	float Ess = fab.x + fab.y;
	float Ems = 1.0 - Ess;
	vec3 Favg = Fr + ( 1.0 - Fr ) * 0.047619;	vec3 Fms = FssEss * Favg / ( 1.0 - Ems * Favg );
	singleScatter += FssEss;
	multiScatter += Fms * Ems;
}
vec3 BRDF_GGX_Multiscatter( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in PhysicalMaterial material ) {
	vec3 singleScatter = BRDF_GGX( lightDir, viewDir, normal, material );
	float dotNL = saturate( dot( normal, lightDir ) );
	float dotNV = saturate( dot( normal, viewDir ) );
	vec2 dfgV = texture2D( dfgLUT, vec2( material.roughness, dotNV ) ).rg;
	vec2 dfgL = texture2D( dfgLUT, vec2( material.roughness, dotNL ) ).rg;
	vec3 FssEss_V = material.specularColorBlended * dfgV.x + material.specularF90 * dfgV.y;
	vec3 FssEss_L = material.specularColorBlended * dfgL.x + material.specularF90 * dfgL.y;
	float Ess_V = dfgV.x + dfgV.y;
	float Ess_L = dfgL.x + dfgL.y;
	float Ems_V = 1.0 - Ess_V;
	float Ems_L = 1.0 - Ess_L;
	vec3 Favg = material.specularColorBlended + ( 1.0 - material.specularColorBlended ) * 0.047619;
	vec3 Fms = FssEss_V * FssEss_L * Favg / ( 1.0 - Ems_V * Ems_L * Favg + EPSILON );
	float compensationFactor = Ems_V * Ems_L;
	vec3 multiScatter = Fms * compensationFactor;
	return singleScatter + multiScatter;
}
#if NUM_RECT_AREA_LIGHTS > 0
	void RE_Direct_RectArea_Physical( const in RectAreaLight rectAreaLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
		vec3 normal = geometryNormal;
		vec3 viewDir = geometryViewDir;
		vec3 position = geometryPosition;
		vec3 lightPos = rectAreaLight.position;
		vec3 halfWidth = rectAreaLight.halfWidth;
		vec3 halfHeight = rectAreaLight.halfHeight;
		vec3 lightColor = rectAreaLight.color;
		float roughness = material.roughness;
		vec3 rectCoords[ 4 ];
		rectCoords[ 0 ] = lightPos + halfWidth - halfHeight;		rectCoords[ 1 ] = lightPos - halfWidth - halfHeight;
		rectCoords[ 2 ] = lightPos - halfWidth + halfHeight;
		rectCoords[ 3 ] = lightPos + halfWidth + halfHeight;
		vec2 uv = LTC_Uv( normal, viewDir, roughness );
		vec4 t1 = texture2D( ltc_1, uv );
		vec4 t2 = texture2D( ltc_2, uv );
		mat3 mInv = mat3(
			vec3( t1.x, 0, t1.y ),
			vec3(    0, 1,    0 ),
			vec3( t1.z, 0, t1.w )
		);
		vec3 fresnel = ( material.specularColorBlended * t2.x + ( material.specularF90 - material.specularColorBlended ) * t2.y );
		reflectedLight.directSpecular += lightColor * fresnel * LTC_Evaluate( normal, viewDir, position, mInv, rectCoords );
		reflectedLight.directDiffuse += lightColor * material.diffuseContribution * LTC_Evaluate( normal, viewDir, position, mat3( 1.0 ), rectCoords );
		#ifdef USE_CLEARCOAT
			vec3 Ncc = geometryClearcoatNormal;
			vec2 uvClearcoat = LTC_Uv( Ncc, viewDir, material.clearcoatRoughness );
			vec4 t1Clearcoat = texture2D( ltc_1, uvClearcoat );
			vec4 t2Clearcoat = texture2D( ltc_2, uvClearcoat );
			mat3 mInvClearcoat = mat3(
				vec3( t1Clearcoat.x, 0, t1Clearcoat.y ),
				vec3(             0, 1,             0 ),
				vec3( t1Clearcoat.z, 0, t1Clearcoat.w )
			);
			vec3 fresnelClearcoat = material.clearcoatF0 * t2Clearcoat.x + ( material.clearcoatF90 - material.clearcoatF0 ) * t2Clearcoat.y;
			clearcoatSpecularDirect += lightColor * fresnelClearcoat * LTC_Evaluate( Ncc, viewDir, position, mInvClearcoat, rectCoords );
		#endif
	}
#endif
void RE_Direct_Physical( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
	float dotNL = saturate( dot( geometryNormal, directLight.direction ) );
	vec3 irradiance = dotNL * directLight.color;
	#ifdef USE_CLEARCOAT
		float dotNLcc = saturate( dot( geometryClearcoatNormal, directLight.direction ) );
		vec3 ccIrradiance = dotNLcc * directLight.color;
		clearcoatSpecularDirect += ccIrradiance * BRDF_GGX_Clearcoat( directLight.direction, geometryViewDir, geometryClearcoatNormal, material );
	#endif
	#ifdef USE_SHEEN
 
 		sheenSpecularDirect += irradiance * BRDF_Sheen( directLight.direction, geometryViewDir, geometryNormal, material.sheenColor, material.sheenRoughness );
 
 		float sheenAlbedoV = IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness );
 		float sheenAlbedoL = IBLSheenBRDF( geometryNormal, directLight.direction, material.sheenRoughness );
 
 		float sheenEnergyComp = 1.0 - max3( material.sheenColor ) * max( sheenAlbedoV, sheenAlbedoL );
 
 		irradiance *= sheenEnergyComp;
 
 	#endif
	reflectedLight.directSpecular += irradiance * BRDF_GGX_Multiscatter( directLight.direction, geometryViewDir, geometryNormal, material );
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseContribution );
}
void RE_IndirectDiffuse_Physical( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
	vec3 diffuse = irradiance * BRDF_Lambert( material.diffuseContribution );
	#ifdef USE_SHEEN
		float sheenAlbedo = IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness );
		float sheenEnergyComp = 1.0 - max3( material.sheenColor ) * sheenAlbedo;
		diffuse *= sheenEnergyComp;
	#endif
	reflectedLight.indirectDiffuse += diffuse;
}
void RE_IndirectSpecular_Physical( const in vec3 radiance, const in vec3 irradiance, const in vec3 clearcoatRadiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight) {
	#ifdef USE_CLEARCOAT
		clearcoatSpecularIndirect += clearcoatRadiance * EnvironmentBRDF( geometryClearcoatNormal, geometryViewDir, material.clearcoatF0, material.clearcoatF90, material.clearcoatRoughness );
	#endif
	#ifdef USE_SHEEN
		sheenSpecularIndirect += irradiance * material.sheenColor * IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness ) * RECIPROCAL_PI;
 	#endif
	vec3 singleScatteringDielectric = vec3( 0.0 );
	vec3 multiScatteringDielectric = vec3( 0.0 );
	vec3 singleScatteringMetallic = vec3( 0.0 );
	vec3 multiScatteringMetallic = vec3( 0.0 );
	#ifdef USE_IRIDESCENCE
		computeMultiscatteringIridescence( geometryNormal, geometryViewDir, material.specularColor, material.specularF90, material.iridescence, material.iridescenceFresnelDielectric, material.roughness, singleScatteringDielectric, multiScatteringDielectric );
		computeMultiscatteringIridescence( geometryNormal, geometryViewDir, material.diffuseColor, material.specularF90, material.iridescence, material.iridescenceFresnelMetallic, material.roughness, singleScatteringMetallic, multiScatteringMetallic );
	#else
		computeMultiscattering( geometryNormal, geometryViewDir, material.specularColor, material.specularF90, material.roughness, singleScatteringDielectric, multiScatteringDielectric );
		computeMultiscattering( geometryNormal, geometryViewDir, material.diffuseColor, material.specularF90, material.roughness, singleScatteringMetallic, multiScatteringMetallic );
	#endif
	vec3 singleScattering = mix( singleScatteringDielectric, singleScatteringMetallic, material.metalness );
	vec3 multiScattering = mix( multiScatteringDielectric, multiScatteringMetallic, material.metalness );
	vec3 totalScatteringDielectric = singleScatteringDielectric + multiScatteringDielectric;
	vec3 diffuse = material.diffuseContribution * ( 1.0 - totalScatteringDielectric );
	vec3 cosineWeightedIrradiance = irradiance * RECIPROCAL_PI;
	vec3 indirectSpecular = radiance * singleScattering;
	indirectSpecular += multiScattering * cosineWeightedIrradiance;
	vec3 indirectDiffuse = diffuse * cosineWeightedIrradiance;
	#ifdef USE_SHEEN
		float sheenAlbedo = IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness );
		float sheenEnergyComp = 1.0 - max3( material.sheenColor ) * sheenAlbedo;
		indirectSpecular *= sheenEnergyComp;
		indirectDiffuse *= sheenEnergyComp;
	#endif
	reflectedLight.indirectSpecular += indirectSpecular;
	reflectedLight.indirectDiffuse += indirectDiffuse;
}
#define RE_Direct				RE_Direct_Physical
#define RE_Direct_RectArea		RE_Direct_RectArea_Physical
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Physical
#define RE_IndirectSpecular		RE_IndirectSpecular_Physical
float computeSpecularOcclusion( const in float dotNV, const in float ambientOcclusion, const in float roughness ) {
	return saturate( pow( dotNV + ambientOcclusion, exp2( - 16.0 * roughness - 1.0 ) ) - 1.0 + ambientOcclusion );
}`,pu=`
vec3 geometryPosition = - vViewPosition;
vec3 geometryNormal = normal;
vec3 geometryViewDir = ( isOrthographic ) ? vec3( 0, 0, 1 ) : normalize( vViewPosition );
vec3 geometryClearcoatNormal = vec3( 0.0 );
#ifdef USE_CLEARCOAT
	geometryClearcoatNormal = clearcoatNormal;
#endif
#ifdef USE_IRIDESCENCE
	float dotNVi = saturate( dot( normal, geometryViewDir ) );
	if ( material.iridescenceThickness == 0.0 ) {
		material.iridescence = 0.0;
	} else {
		material.iridescence = saturate( material.iridescence );
	}
	if ( material.iridescence > 0.0 ) {
		material.iridescenceFresnelDielectric = evalIridescence( 1.0, material.iridescenceIOR, dotNVi, material.iridescenceThickness, material.specularColor );
		material.iridescenceFresnelMetallic = evalIridescence( 1.0, material.iridescenceIOR, dotNVi, material.iridescenceThickness, material.diffuseColor );
		material.iridescenceFresnel = mix( material.iridescenceFresnelDielectric, material.iridescenceFresnelMetallic, material.metalness );
		material.iridescenceF0 = Schlick_to_F0( material.iridescenceFresnel, 1.0, dotNVi );
	}
#endif
IncidentLight directLight;
#if ( NUM_POINT_LIGHTS > 0 ) && defined( RE_Direct )
	PointLight pointLight;
	#if defined( USE_SHADOWMAP ) && NUM_POINT_LIGHT_SHADOWS > 0
	PointLightShadow pointLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_POINT_LIGHTS; i ++ ) {
		pointLight = pointLights[ i ];
		getPointLightInfo( pointLight, geometryPosition, directLight );
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_POINT_LIGHT_SHADOWS ) && ( defined( SHADOWMAP_TYPE_PCF ) || defined( SHADOWMAP_TYPE_BASIC ) )
		pointLightShadow = pointLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getPointShadow( pointShadowMap[ i ], pointLightShadow.shadowMapSize, pointLightShadow.shadowIntensity, pointLightShadow.shadowBias, pointLightShadow.shadowRadius, vPointShadowCoord[ i ], pointLightShadow.shadowCameraNear, pointLightShadow.shadowCameraFar ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_SPOT_LIGHTS > 0 ) && defined( RE_Direct )
	SpotLight spotLight;
	vec4 spotColor;
	vec3 spotLightCoord;
	bool inSpotLightMap;
	#if defined( USE_SHADOWMAP ) && NUM_SPOT_LIGHT_SHADOWS > 0
	SpotLightShadow spotLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SPOT_LIGHTS; i ++ ) {
		spotLight = spotLights[ i ];
		getSpotLightInfo( spotLight, geometryPosition, directLight );
		#if ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS_WITH_MAPS )
		#define SPOT_LIGHT_MAP_INDEX UNROLLED_LOOP_INDEX
		#elif ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
		#define SPOT_LIGHT_MAP_INDEX NUM_SPOT_LIGHT_MAPS
		#else
		#define SPOT_LIGHT_MAP_INDEX ( UNROLLED_LOOP_INDEX - NUM_SPOT_LIGHT_SHADOWS + NUM_SPOT_LIGHT_SHADOWS_WITH_MAPS )
		#endif
		#if ( SPOT_LIGHT_MAP_INDEX < NUM_SPOT_LIGHT_MAPS )
			spotLightCoord = vSpotLightCoord[ i ].xyz / vSpotLightCoord[ i ].w;
			inSpotLightMap = all( lessThan( abs( spotLightCoord * 2. - 1. ), vec3( 1.0 ) ) );
			spotColor = texture2D( spotLightMap[ SPOT_LIGHT_MAP_INDEX ], spotLightCoord.xy );
			directLight.color = inSpotLightMap ? directLight.color * spotColor.rgb : directLight.color;
		#endif
		#undef SPOT_LIGHT_MAP_INDEX
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
		spotLightShadow = spotLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getShadow( spotShadowMap[ i ], spotLightShadow.shadowMapSize, spotLightShadow.shadowIntensity, spotLightShadow.shadowBias, spotLightShadow.shadowRadius, vSpotLightCoord[ i ] ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_DIR_LIGHTS > 0 ) && defined( RE_Direct )
	DirectionalLight directionalLight;
	#if defined( USE_SHADOWMAP ) && NUM_DIR_LIGHT_SHADOWS > 0
	DirectionalLightShadow directionalLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_DIR_LIGHTS; i ++ ) {
		directionalLight = directionalLights[ i ];
		getDirectionalLightInfo( directionalLight, directLight );
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_DIR_LIGHT_SHADOWS )
		directionalLightShadow = directionalLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getShadow( directionalShadowMap[ i ], directionalLightShadow.shadowMapSize, directionalLightShadow.shadowIntensity, directionalLightShadow.shadowBias, directionalLightShadow.shadowRadius, vDirectionalShadowCoord[ i ] ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_RECT_AREA_LIGHTS > 0 ) && defined( RE_Direct_RectArea )
	RectAreaLight rectAreaLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_RECT_AREA_LIGHTS; i ++ ) {
		rectAreaLight = rectAreaLights[ i ];
		RE_Direct_RectArea( rectAreaLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if defined( RE_IndirectDiffuse )
	vec3 iblIrradiance = vec3( 0.0 );
	vec3 irradiance = getAmbientLightIrradiance( ambientLightColor );
	#if defined( USE_LIGHT_PROBES )
		irradiance += getLightProbeIrradiance( lightProbe, geometryNormal );
	#endif
	#if ( NUM_HEMI_LIGHTS > 0 )
		#pragma unroll_loop_start
		for ( int i = 0; i < NUM_HEMI_LIGHTS; i ++ ) {
			irradiance += getHemisphereLightIrradiance( hemisphereLights[ i ], geometryNormal );
		}
		#pragma unroll_loop_end
	#endif
	#ifdef USE_LIGHT_PROBES_GRID
		vec3 probeWorldPos = ( ( vec4( geometryPosition, 1.0 ) - viewMatrix[ 3 ] ) * viewMatrix ).xyz;
		vec3 probeWorldNormal = transformNormalByInverseViewMatrix( geometryNormal, viewMatrix );
		irradiance += getLightProbeGridIrradiance( probeWorldPos, probeWorldNormal );
	#endif
#endif
#if defined( RE_IndirectSpecular )
	vec3 radiance = vec3( 0.0 );
	vec3 clearcoatRadiance = vec3( 0.0 );
#endif`,mu=`#if defined( RE_IndirectDiffuse )
	#ifdef USE_LIGHTMAP
		vec4 lightMapTexel = texture2D( lightMap, vLightMapUv );
		vec3 lightMapIrradiance = lightMapTexel.rgb * lightMapIntensity;
		irradiance += lightMapIrradiance;
	#endif
	#if defined( USE_ENVMAP ) && defined( ENVMAP_TYPE_CUBE_UV )
		#if defined( STANDARD ) || defined( LAMBERT ) || defined( PHONG )
			iblIrradiance += getIBLIrradiance( geometryNormal );
		#endif
	#endif
#endif
#if defined( USE_ENVMAP ) && defined( RE_IndirectSpecular )
	#ifdef USE_ANISOTROPY
		radiance += getIBLAnisotropyRadiance( geometryViewDir, geometryNormal, material.roughness, material.anisotropyB, material.anisotropy );
	#else
		radiance += getIBLRadiance( geometryViewDir, geometryNormal, material.roughness );
	#endif
	#ifdef USE_CLEARCOAT
		clearcoatRadiance += getIBLRadiance( geometryViewDir, geometryClearcoatNormal, material.clearcoatRoughness );
	#endif
#endif`,gu=`#if defined( RE_IndirectDiffuse )
	#if defined( LAMBERT ) || defined( PHONG )
		irradiance += iblIrradiance;
	#endif
	RE_IndirectDiffuse( irradiance, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
#endif
#if defined( RE_IndirectSpecular )
	RE_IndirectSpecular( radiance, iblIrradiance, clearcoatRadiance, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
#endif`,xu=`#ifdef USE_LIGHT_PROBES_GRID
uniform highp sampler3D probesSH;
uniform vec3 probesMin;
uniform vec3 probesMax;
uniform vec3 probesResolution;
vec3 getLightProbeGridIrradiance( vec3 worldPos, vec3 worldNormal ) {
	vec3 res = probesResolution;
	vec3 gridRange = probesMax - probesMin;
	vec3 resMinusOne = res - 1.0;
	vec3 probeSpacing = gridRange / resMinusOne;
	vec3 samplePos = worldPos + worldNormal * probeSpacing * 0.5;
	vec3 uvw = clamp( ( samplePos - probesMin ) / gridRange, 0.0, 1.0 );
	uvw = uvw * resMinusOne / res + 0.5 / res;
	float nz          = res.z;
	float paddedSlices = nz + 2.0;
	float atlasDepth  = 7.0 * paddedSlices;
	float uvZBase     = uvw.z * nz + 1.0;
	vec4 s0 = texture( probesSH, vec3( uvw.xy, ( uvZBase                       ) / atlasDepth ) );
	vec4 s1 = texture( probesSH, vec3( uvw.xy, ( uvZBase +       paddedSlices   ) / atlasDepth ) );
	vec4 s2 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 2.0 * paddedSlices   ) / atlasDepth ) );
	vec4 s3 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 3.0 * paddedSlices   ) / atlasDepth ) );
	vec4 s4 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 4.0 * paddedSlices   ) / atlasDepth ) );
	vec4 s5 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 5.0 * paddedSlices   ) / atlasDepth ) );
	vec4 s6 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 6.0 * paddedSlices   ) / atlasDepth ) );
	vec3 c0 = s0.xyz;
	vec3 c1 = vec3( s0.w, s1.xy );
	vec3 c2 = vec3( s1.zw, s2.x );
	vec3 c3 = s2.yzw;
	vec3 c4 = s3.xyz;
	vec3 c5 = vec3( s3.w, s4.xy );
	vec3 c6 = vec3( s4.zw, s5.x );
	vec3 c7 = s5.yzw;
	vec3 c8 = s6.xyz;
	float x = worldNormal.x, y = worldNormal.y, z = worldNormal.z;
	vec3 result = c0 * 0.886227;
	result += c1 * 2.0 * 0.511664 * y;
	result += c2 * 2.0 * 0.511664 * z;
	result += c3 * 2.0 * 0.511664 * x;
	result += c4 * 2.0 * 0.429043 * x * y;
	result += c5 * 2.0 * 0.429043 * y * z;
	result += c6 * ( 0.743125 * z * z - 0.247708 );
	result += c7 * 2.0 * 0.429043 * x * z;
	result += c8 * 0.429043 * ( x * x - y * y );
	return max( result, vec3( 0.0 ) );
}
#endif`,_u=`#if defined( USE_LOGARITHMIC_DEPTH_BUFFER )
	gl_FragDepth = vIsPerspective == 0.0 ? gl_FragCoord.z : log2( vFragDepth ) * logDepthBufFC * 0.5;
#endif`,yu=`#if defined( USE_LOGARITHMIC_DEPTH_BUFFER )
	uniform float logDepthBufFC;
	varying float vFragDepth;
	varying float vIsPerspective;
#endif`,vu=`#ifdef USE_LOGARITHMIC_DEPTH_BUFFER
	varying float vFragDepth;
	varying float vIsPerspective;
#endif`,Mu=`#ifdef USE_LOGARITHMIC_DEPTH_BUFFER
	vFragDepth = 1.0 + gl_Position.w;
	vIsPerspective = float( isPerspectiveMatrix( projectionMatrix ) );
#endif`,bu=`#ifdef USE_MAP
	vec4 sampledDiffuseColor = texture2D( map, vMapUv );
	#ifdef DECODE_VIDEO_TEXTURE
		sampledDiffuseColor = sRGBTransferEOTF( sampledDiffuseColor );
	#endif
	diffuseColor *= sampledDiffuseColor;
#endif`,Su=`#ifdef USE_MAP
	uniform sampler2D map;
#endif`,Au=`#if defined( USE_MAP ) || defined( USE_ALPHAMAP )
	#if defined( USE_POINTS_UV )
		vec2 uv = vUv;
	#else
		vec2 uv = ( uvTransform * vec3( gl_PointCoord.x, 1.0 - gl_PointCoord.y, 1 ) ).xy;
	#endif
#endif
#ifdef USE_MAP
	diffuseColor *= texture2D( map, uv );
#endif
#ifdef USE_ALPHAMAP
	diffuseColor.a *= texture2D( alphaMap, uv ).g;
#endif`,Tu=`#if defined( USE_POINTS_UV )
	varying vec2 vUv;
#else
	#if defined( USE_MAP ) || defined( USE_ALPHAMAP )
		uniform mat3 uvTransform;
	#endif
#endif
#ifdef USE_MAP
	uniform sampler2D map;
#endif
#ifdef USE_ALPHAMAP
	uniform sampler2D alphaMap;
#endif`,wu=`float metalnessFactor = metalness;
#ifdef USE_METALNESSMAP
	vec4 texelMetalness = texture2D( metalnessMap, vMetalnessMapUv );
	metalnessFactor *= texelMetalness.b;
#endif`,Eu=`#ifdef USE_METALNESSMAP
	uniform sampler2D metalnessMap;
#endif`,Cu=`#ifdef USE_INSTANCING_MORPH
	float morphTargetInfluences[ MORPHTARGETS_COUNT ];
	float morphTargetBaseInfluence = texelFetch( morphTexture, ivec2( 0, gl_InstanceID ), 0 ).r;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		morphTargetInfluences[i] =  texelFetch( morphTexture, ivec2( i + 1, gl_InstanceID ), 0 ).r;
	}
#endif`,Ru=`#if defined( USE_MORPHCOLORS )
	vColor *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		#if defined( USE_COLOR_ALPHA )
			if ( morphTargetInfluences[ i ] != 0.0 ) vColor += getMorph( gl_VertexID, i, 2 ) * morphTargetInfluences[ i ];
		#elif defined( USE_COLOR )
			if ( morphTargetInfluences[ i ] != 0.0 ) vColor += getMorph( gl_VertexID, i, 2 ).rgb * morphTargetInfluences[ i ];
		#endif
	}
#endif`,Iu=`#ifdef USE_MORPHNORMALS
	objectNormal *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		if ( morphTargetInfluences[ i ] != 0.0 ) objectNormal += getMorph( gl_VertexID, i, 1 ).xyz * morphTargetInfluences[ i ];
	}
#endif`,Pu=`#ifdef USE_MORPHTARGETS
	#ifndef USE_INSTANCING_MORPH
		uniform float morphTargetBaseInfluence;
		uniform float morphTargetInfluences[ MORPHTARGETS_COUNT ];
	#endif
	uniform sampler2DArray morphTargetsTexture;
	uniform ivec2 morphTargetsTextureSize;
	vec4 getMorph( const in int vertexIndex, const in int morphTargetIndex, const in int offset ) {
		int texelIndex = vertexIndex * MORPHTARGETS_TEXTURE_STRIDE + offset;
		int y = texelIndex / morphTargetsTextureSize.x;
		int x = texelIndex - y * morphTargetsTextureSize.x;
		ivec3 morphUV = ivec3( x, y, morphTargetIndex );
		return texelFetch( morphTargetsTexture, morphUV, 0 );
	}
#endif`,Nu=`#ifdef USE_MORPHTARGETS
	transformed *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		if ( morphTargetInfluences[ i ] != 0.0 ) transformed += getMorph( gl_VertexID, i, 0 ).xyz * morphTargetInfluences[ i ];
	}
#endif`,Lu=`float faceDirection = gl_FrontFacing ? 1.0 : - 1.0;
#ifdef FLAT_SHADED
	vec3 fdx = dFdx( vViewPosition );
	vec3 fdy = dFdy( vViewPosition );
	vec3 normal = normalize( cross( fdx, fdy ) );
#else
	vec3 normal = normalize( vNormal );
	#ifdef DOUBLE_SIDED
		normal *= faceDirection;
	#endif
#endif
#if defined( USE_NORMALMAP_TANGENTSPACE ) || defined( USE_CLEARCOAT_NORMALMAP ) || defined( USE_ANISOTROPY )
	#ifdef USE_TANGENT
		mat3 tbn = mat3( normalize( vTangent ), normalize( vBitangent ), normal );
	#else
		mat3 tbn = getTangentFrame( - vViewPosition, normal,
		#if defined( USE_NORMALMAP )
			vNormalMapUv
		#elif defined( USE_CLEARCOAT_NORMALMAP )
			vClearcoatNormalMapUv
		#else
			vUv
		#endif
		);
	#endif
	#ifdef DOUBLE_SIDED
		tbn[0] *= faceDirection;
		tbn[1] *= faceDirection;
	#endif
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	#ifdef USE_TANGENT
		mat3 tbn2 = mat3( normalize( vTangent ), normalize( vBitangent ), normal );
	#else
		mat3 tbn2 = getTangentFrame( - vViewPosition, normal, vClearcoatNormalMapUv );
	#endif
	#ifdef DOUBLE_SIDED
		tbn2[0] *= faceDirection;
		tbn2[1] *= faceDirection;
	#endif
#endif
vec3 nonPerturbedNormal = normal;`,Du=`#ifdef USE_NORMALMAP_OBJECTSPACE
	normal = texture2D( normalMap, vNormalMapUv ).xyz * 2.0 - 1.0;
	#ifdef FLIP_SIDED
		normal = - normal;
	#endif
	#ifdef DOUBLE_SIDED
		normal = normal * faceDirection;
	#endif
	normal = normalize( normalMatrix * normal );
#elif defined( USE_NORMALMAP_TANGENTSPACE )
	vec3 mapN = texture2D( normalMap, vNormalMapUv ).xyz * 2.0 - 1.0;
	#if defined( USE_PACKED_NORMALMAP )
		mapN = vec3( mapN.xy, sqrt( saturate( 1.0 - dot( mapN.xy, mapN.xy ) ) ) );
	#endif
	mapN.xy *= normalScale;
	normal = normalize( tbn * mapN );
#elif defined( USE_BUMPMAP )
	normal = perturbNormalArb( - vViewPosition, normal, dHdxy_fwd(), faceDirection );
#endif`,Uu=`#ifndef FLAT_SHADED
	varying vec3 vNormal;
	#ifdef USE_TANGENT
		varying vec3 vTangent;
		varying vec3 vBitangent;
	#endif
#endif`,Fu=`#ifndef FLAT_SHADED
	varying vec3 vNormal;
	#ifdef USE_TANGENT
		varying vec3 vTangent;
		varying vec3 vBitangent;
	#endif
#endif`,Ou=`#ifndef FLAT_SHADED
	vNormal = normalize( transformedNormal );
	#ifdef USE_TANGENT
		vTangent = normalize( transformedTangent );
		vBitangent = normalize( cross( vNormal, vTangent ) * tangent.w );
		#ifdef FLIP_SIDED
			vBitangent = - vBitangent;
		#endif
	#endif
#endif`,Bu=`#ifdef USE_NORMALMAP
	uniform sampler2D normalMap;
	uniform vec2 normalScale;
#endif
#ifdef USE_NORMALMAP_OBJECTSPACE
	uniform mat3 normalMatrix;
#endif
#if ! defined ( USE_TANGENT ) && ( defined ( USE_NORMALMAP_TANGENTSPACE ) || defined ( USE_CLEARCOAT_NORMALMAP ) || defined( USE_ANISOTROPY ) )
	mat3 getTangentFrame( vec3 eye_pos, vec3 surf_norm, vec2 uv ) {
		vec3 q0 = dFdx( eye_pos.xyz );
		vec3 q1 = dFdy( eye_pos.xyz );
		vec2 st0 = dFdx( uv.st );
		vec2 st1 = dFdy( uv.st );
		vec3 N = surf_norm;
		vec3 q1perp = cross( q1, N );
		vec3 q0perp = cross( N, q0 );
		vec3 T = q1perp * st0.x + q0perp * st1.x;
		vec3 B = q1perp * st0.y + q0perp * st1.y;
		float det = max( dot( T, T ), dot( B, B ) );
		float scale = ( det == 0.0 ) ? 0.0 : inversesqrt( det );
		return mat3( T * scale, B * scale, N );
	}
#endif`,zu=`#ifdef USE_CLEARCOAT
	vec3 clearcoatNormal = nonPerturbedNormal;
#endif`,ku=`#ifdef USE_CLEARCOAT_NORMALMAP
	vec3 clearcoatMapN = texture2D( clearcoatNormalMap, vClearcoatNormalMapUv ).xyz * 2.0 - 1.0;
	clearcoatMapN.xy *= clearcoatNormalScale;
	clearcoatNormal = normalize( tbn2 * clearcoatMapN );
#endif`,Vu=`#ifdef USE_CLEARCOATMAP
	uniform sampler2D clearcoatMap;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	uniform sampler2D clearcoatNormalMap;
	uniform vec2 clearcoatNormalScale;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	uniform sampler2D clearcoatRoughnessMap;
#endif`,Gu=`#ifdef USE_IRIDESCENCEMAP
	uniform sampler2D iridescenceMap;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	uniform sampler2D iridescenceThicknessMap;
#endif`,Hu=`#ifdef OPAQUE
diffuseColor.a = 1.0;
#endif
#ifdef USE_TRANSMISSION
diffuseColor.a *= material.transmissionAlpha;
#endif
gl_FragColor = vec4( outgoingLight, diffuseColor.a );`,Wu=`vec3 packNormalToRGB( const in vec3 normal ) {
	return normalize( normal ) * 0.5 + 0.5;
}
vec3 unpackRGBToNormal( const in vec3 rgb ) {
	return 2.0 * rgb.xyz - 1.0;
}
const float PackUpscale = 256. / 255.;const float UnpackDownscale = 255. / 256.;const float ShiftRight8 = 1. / 256.;
const float Inv255 = 1. / 255.;
const vec4 PackFactors = vec4( 1.0, 256.0, 256.0 * 256.0, 256.0 * 256.0 * 256.0 );
const vec2 UnpackFactors2 = vec2( UnpackDownscale, 1.0 / PackFactors.g );
const vec3 UnpackFactors3 = vec3( UnpackDownscale / PackFactors.rg, 1.0 / PackFactors.b );
const vec4 UnpackFactors4 = vec4( UnpackDownscale / PackFactors.rgb, 1.0 / PackFactors.a );
vec4 packDepthToRGBA( const in float v ) {
	if( v <= 0.0 )
		return vec4( 0., 0., 0., 0. );
	if( v >= 1.0 )
		return vec4( 1., 1., 1., 1. );
	float vuf;
	float af = modf( v * PackFactors.a, vuf );
	float bf = modf( vuf * ShiftRight8, vuf );
	float gf = modf( vuf * ShiftRight8, vuf );
	return vec4( vuf * Inv255, gf * PackUpscale, bf * PackUpscale, af );
}
vec3 packDepthToRGB( const in float v ) {
	if( v <= 0.0 )
		return vec3( 0., 0., 0. );
	if( v >= 1.0 )
		return vec3( 1., 1., 1. );
	float vuf;
	float bf = modf( v * PackFactors.b, vuf );
	float gf = modf( vuf * ShiftRight8, vuf );
	return vec3( vuf * Inv255, gf * PackUpscale, bf );
}
vec2 packDepthToRG( const in float v ) {
	if( v <= 0.0 )
		return vec2( 0., 0. );
	if( v >= 1.0 )
		return vec2( 1., 1. );
	float vuf;
	float gf = modf( v * 256., vuf );
	return vec2( vuf * Inv255, gf );
}
float unpackRGBAToDepth( const in vec4 v ) {
	return dot( v, UnpackFactors4 );
}
float unpackRGBToDepth( const in vec3 v ) {
	return dot( v, UnpackFactors3 );
}
float unpackRGToDepth( const in vec2 v ) {
	return v.r * UnpackFactors2.r + v.g * UnpackFactors2.g;
}
vec4 pack2HalfToRGBA( const in vec2 v ) {
	vec4 r = vec4( v.x, fract( v.x * 255.0 ), v.y, fract( v.y * 255.0 ) );
	return vec4( r.x - r.y / 255.0, r.y, r.z - r.w / 255.0, r.w );
}
vec2 unpackRGBATo2Half( const in vec4 v ) {
	return vec2( v.x + ( v.y / 255.0 ), v.z + ( v.w / 255.0 ) );
}
float viewZToOrthographicDepth( const in float viewZ, const in float near, const in float far ) {
	return ( viewZ + near ) / ( near - far );
}
float orthographicDepthToViewZ( const in float depth, const in float near, const in float far ) {
	#ifdef USE_REVERSED_DEPTH_BUFFER
	
		return depth * ( far - near ) - far;
	#else
		return depth * ( near - far ) - near;
	#endif
}
float viewZToPerspectiveDepth( const in float viewZ, const in float near, const in float far ) {
	return ( ( near + viewZ ) * far ) / ( ( far - near ) * viewZ );
}
float perspectiveDepthToViewZ( const in float depth, const in float near, const in float far ) {
	
	#ifdef USE_REVERSED_DEPTH_BUFFER
		return ( near * far ) / ( ( near - far ) * depth - near );
	#else
		return ( near * far ) / ( ( far - near ) * depth - far );
	#endif
}`,Xu=`#ifdef PREMULTIPLIED_ALPHA
	gl_FragColor.rgb *= gl_FragColor.a;
#endif`,qu=`vec4 mvPosition = vec4( transformed, 1.0 );
#ifdef USE_BATCHING
	mvPosition = batchingMatrix * mvPosition;
#endif
#ifdef USE_INSTANCING
	mvPosition = instanceMatrix * mvPosition;
#endif
mvPosition = modelViewMatrix * mvPosition;
gl_Position = projectionMatrix * mvPosition;`,$u=`#ifdef DITHERING
	gl_FragColor.rgb = dithering( gl_FragColor.rgb );
#endif`,Yu=`#ifdef DITHERING
	vec3 dithering( vec3 color ) {
		float grid_position = rand( gl_FragCoord.xy );
		vec3 dither_shift_RGB = vec3( 0.25 / 255.0, -0.25 / 255.0, 0.25 / 255.0 );
		dither_shift_RGB = mix( 2.0 * dither_shift_RGB, -2.0 * dither_shift_RGB, grid_position );
		return color + dither_shift_RGB;
	}
#endif`,Zu=`float roughnessFactor = roughness;
#ifdef USE_ROUGHNESSMAP
	vec4 texelRoughness = texture2D( roughnessMap, vRoughnessMapUv );
	roughnessFactor *= texelRoughness.g;
#endif`,Ju=`#ifdef USE_ROUGHNESSMAP
	uniform sampler2D roughnessMap;
#endif`,Ku=`#if NUM_SPOT_LIGHT_COORDS > 0
	varying vec4 vSpotLightCoord[ NUM_SPOT_LIGHT_COORDS ];
#endif
#if NUM_SPOT_LIGHT_MAPS > 0
	uniform sampler2D spotLightMap[ NUM_SPOT_LIGHT_MAPS ];
#endif
#ifdef USE_SHADOWMAP
	#if NUM_DIR_LIGHT_SHADOWS > 0
		#if defined( SHADOWMAP_TYPE_PCF )
			uniform sampler2DShadow directionalShadowMap[ NUM_DIR_LIGHT_SHADOWS ];
		#else
			uniform sampler2D directionalShadowMap[ NUM_DIR_LIGHT_SHADOWS ];
		#endif
		varying vec4 vDirectionalShadowCoord[ NUM_DIR_LIGHT_SHADOWS ];
		struct DirectionalLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform DirectionalLightShadow directionalLightShadows[ NUM_DIR_LIGHT_SHADOWS ];
	#endif
	#if NUM_SPOT_LIGHT_SHADOWS > 0
		#if defined( SHADOWMAP_TYPE_PCF )
			uniform sampler2DShadow spotShadowMap[ NUM_SPOT_LIGHT_SHADOWS ];
		#else
			uniform sampler2D spotShadowMap[ NUM_SPOT_LIGHT_SHADOWS ];
		#endif
		struct SpotLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform SpotLightShadow spotLightShadows[ NUM_SPOT_LIGHT_SHADOWS ];
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
		#if defined( SHADOWMAP_TYPE_PCF )
			uniform samplerCubeShadow pointShadowMap[ NUM_POINT_LIGHT_SHADOWS ];
		#elif defined( SHADOWMAP_TYPE_BASIC )
			uniform samplerCube pointShadowMap[ NUM_POINT_LIGHT_SHADOWS ];
		#endif
		varying vec4 vPointShadowCoord[ NUM_POINT_LIGHT_SHADOWS ];
		struct PointLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
			float shadowCameraNear;
			float shadowCameraFar;
		};
		uniform PointLightShadow pointLightShadows[ NUM_POINT_LIGHT_SHADOWS ];
	#endif
	#if defined( SHADOWMAP_TYPE_PCF )
		float interleavedGradientNoise( vec2 position ) {
			return fract( 52.9829189 * fract( dot( position, vec2( 0.06711056, 0.00583715 ) ) ) );
		}
		vec2 vogelDiskSample( int sampleIndex, int samplesCount, float phi ) {
			const float goldenAngle = 2.399963229728653;
			float r = sqrt( ( float( sampleIndex ) + 0.5 ) / float( samplesCount ) );
			float theta = float( sampleIndex ) * goldenAngle + phi;
			return vec2( cos( theta ), sin( theta ) ) * r;
		}
	#endif
	#if defined( SHADOWMAP_TYPE_PCF )
		float getShadow( sampler2DShadow shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord ) {
			float shadow = 1.0;
			shadowCoord.xyz /= shadowCoord.w;
			shadowCoord.z += shadowBias;
			bool inFrustum = shadowCoord.x >= 0.0 && shadowCoord.x <= 1.0 && shadowCoord.y >= 0.0 && shadowCoord.y <= 1.0;
			bool frustumTest = inFrustum && shadowCoord.z <= 1.0;
			if ( frustumTest ) {
				vec2 texelSize = vec2( 1.0 ) / shadowMapSize;
				float radius = shadowRadius * texelSize.x;
				float phi = interleavedGradientNoise( gl_FragCoord.xy ) * PI2;
				shadow = (
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 0, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 1, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 2, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 3, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 4, 5, phi ) * radius, shadowCoord.z ) )
				) * 0.2;
			}
			return mix( 1.0, shadow, shadowIntensity );
		}
	#elif defined( SHADOWMAP_TYPE_VSM )
		float getShadow( sampler2D shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord ) {
			float shadow = 1.0;
			shadowCoord.xyz /= shadowCoord.w;
			#ifdef USE_REVERSED_DEPTH_BUFFER
				shadowCoord.z -= shadowBias;
			#else
				shadowCoord.z += shadowBias;
			#endif
			bool inFrustum = shadowCoord.x >= 0.0 && shadowCoord.x <= 1.0 && shadowCoord.y >= 0.0 && shadowCoord.y <= 1.0;
			bool frustumTest = inFrustum && shadowCoord.z <= 1.0;
			if ( frustumTest ) {
				vec2 distribution = texture2D( shadowMap, shadowCoord.xy ).rg;
				float mean = distribution.x;
				float variance = distribution.y * distribution.y;
				#ifdef USE_REVERSED_DEPTH_BUFFER
					float hard_shadow = step( mean, shadowCoord.z );
				#else
					float hard_shadow = step( shadowCoord.z, mean );
				#endif
				
				if ( hard_shadow == 1.0 ) {
					shadow = 1.0;
				} else {
					variance = max( variance, 0.0000001 );
					float d = shadowCoord.z - mean;
					float p_max = variance / ( variance + d * d );
					p_max = clamp( ( p_max - 0.3 ) / 0.65, 0.0, 1.0 );
					shadow = max( hard_shadow, p_max );
				}
			}
			return mix( 1.0, shadow, shadowIntensity );
		}
	#else
		float getShadow( sampler2D shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord ) {
			float shadow = 1.0;
			shadowCoord.xyz /= shadowCoord.w;
			#ifdef USE_REVERSED_DEPTH_BUFFER
				shadowCoord.z -= shadowBias;
			#else
				shadowCoord.z += shadowBias;
			#endif
			bool inFrustum = shadowCoord.x >= 0.0 && shadowCoord.x <= 1.0 && shadowCoord.y >= 0.0 && shadowCoord.y <= 1.0;
			bool frustumTest = inFrustum && shadowCoord.z <= 1.0;
			if ( frustumTest ) {
				float depth = texture2D( shadowMap, shadowCoord.xy ).r;
				#ifdef USE_REVERSED_DEPTH_BUFFER
					shadow = step( depth, shadowCoord.z );
				#else
					shadow = step( shadowCoord.z, depth );
				#endif
			}
			return mix( 1.0, shadow, shadowIntensity );
		}
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
	#if defined( SHADOWMAP_TYPE_PCF )
	float getPointShadow( samplerCubeShadow shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord, float shadowCameraNear, float shadowCameraFar ) {
		float shadow = 1.0;
		vec3 lightToPosition = shadowCoord.xyz;
		vec3 bd3D = normalize( lightToPosition );
		vec3 absVec = abs( lightToPosition );
		float viewSpaceZ = max( max( absVec.x, absVec.y ), absVec.z );
		if ( viewSpaceZ - shadowCameraFar <= 0.0 && viewSpaceZ - shadowCameraNear >= 0.0 ) {
			#ifdef USE_REVERSED_DEPTH_BUFFER
				float dp = ( shadowCameraNear * ( shadowCameraFar - viewSpaceZ ) ) / ( viewSpaceZ * ( shadowCameraFar - shadowCameraNear ) );
				dp -= shadowBias;
			#else
				float dp = ( shadowCameraFar * ( viewSpaceZ - shadowCameraNear ) ) / ( viewSpaceZ * ( shadowCameraFar - shadowCameraNear ) );
				dp += shadowBias;
			#endif
			float texelSize = shadowRadius / shadowMapSize.x;
			vec3 absDir = abs( bd3D );
			vec3 tangent = absDir.x > absDir.z ? vec3( 0.0, 1.0, 0.0 ) : vec3( 1.0, 0.0, 0.0 );
			tangent = normalize( cross( bd3D, tangent ) );
			vec3 bitangent = cross( bd3D, tangent );
			float phi = interleavedGradientNoise( gl_FragCoord.xy ) * PI2;
			vec2 sample0 = vogelDiskSample( 0, 5, phi );
			vec2 sample1 = vogelDiskSample( 1, 5, phi );
			vec2 sample2 = vogelDiskSample( 2, 5, phi );
			vec2 sample3 = vogelDiskSample( 3, 5, phi );
			vec2 sample4 = vogelDiskSample( 4, 5, phi );
			shadow = (
				texture( shadowMap, vec4( bd3D + ( tangent * sample0.x + bitangent * sample0.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample1.x + bitangent * sample1.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample2.x + bitangent * sample2.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample3.x + bitangent * sample3.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample4.x + bitangent * sample4.y ) * texelSize, dp ) )
			) * 0.2;
		}
		return mix( 1.0, shadow, shadowIntensity );
	}
	#elif defined( SHADOWMAP_TYPE_BASIC )
	float getPointShadow( samplerCube shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord, float shadowCameraNear, float shadowCameraFar ) {
		float shadow = 1.0;
		vec3 lightToPosition = shadowCoord.xyz;
		vec3 absVec = abs( lightToPosition );
		float viewSpaceZ = max( max( absVec.x, absVec.y ), absVec.z );
		if ( viewSpaceZ - shadowCameraFar <= 0.0 && viewSpaceZ - shadowCameraNear >= 0.0 ) {
			float dp = ( shadowCameraFar * ( viewSpaceZ - shadowCameraNear ) ) / ( viewSpaceZ * ( shadowCameraFar - shadowCameraNear ) );
			dp += shadowBias;
			vec3 bd3D = normalize( lightToPosition );
			float depth = textureCube( shadowMap, bd3D ).r;
			#ifdef USE_REVERSED_DEPTH_BUFFER
				depth = 1.0 - depth;
			#endif
			shadow = step( dp, depth );
		}
		return mix( 1.0, shadow, shadowIntensity );
	}
	#endif
	#endif
#endif`,ju=`#if NUM_SPOT_LIGHT_COORDS > 0
	uniform mat4 spotLightMatrix[ NUM_SPOT_LIGHT_COORDS ];
	varying vec4 vSpotLightCoord[ NUM_SPOT_LIGHT_COORDS ];
#endif
#ifdef USE_SHADOWMAP
	#if NUM_DIR_LIGHT_SHADOWS > 0
		uniform mat4 directionalShadowMatrix[ NUM_DIR_LIGHT_SHADOWS ];
		varying vec4 vDirectionalShadowCoord[ NUM_DIR_LIGHT_SHADOWS ];
		struct DirectionalLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform DirectionalLightShadow directionalLightShadows[ NUM_DIR_LIGHT_SHADOWS ];
	#endif
	#if NUM_SPOT_LIGHT_SHADOWS > 0
		struct SpotLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform SpotLightShadow spotLightShadows[ NUM_SPOT_LIGHT_SHADOWS ];
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
		uniform mat4 pointShadowMatrix[ NUM_POINT_LIGHT_SHADOWS ];
		varying vec4 vPointShadowCoord[ NUM_POINT_LIGHT_SHADOWS ];
		struct PointLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
			float shadowCameraNear;
			float shadowCameraFar;
		};
		uniform PointLightShadow pointLightShadows[ NUM_POINT_LIGHT_SHADOWS ];
	#endif
#endif`,Qu=`#if ( defined( USE_SHADOWMAP ) && ( NUM_DIR_LIGHT_SHADOWS > 0 || NUM_POINT_LIGHT_SHADOWS > 0 ) ) || ( NUM_SPOT_LIGHT_COORDS > 0 )
	#ifdef HAS_NORMAL
		vec3 shadowWorldNormal = transformNormalByInverseViewMatrix( transformedNormal, viewMatrix );
	#else
		vec3 shadowWorldNormal = vec3( 0.0 );
	#endif
	vec4 shadowWorldPosition;
#endif
#if defined( USE_SHADOWMAP )
	#if NUM_DIR_LIGHT_SHADOWS > 0
		#pragma unroll_loop_start
		for ( int i = 0; i < NUM_DIR_LIGHT_SHADOWS; i ++ ) {
			shadowWorldPosition = worldPosition + vec4( shadowWorldNormal * directionalLightShadows[ i ].shadowNormalBias, 0 );
			vDirectionalShadowCoord[ i ] = directionalShadowMatrix[ i ] * shadowWorldPosition;
		}
		#pragma unroll_loop_end
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
		#pragma unroll_loop_start
		for ( int i = 0; i < NUM_POINT_LIGHT_SHADOWS; i ++ ) {
			shadowWorldPosition = worldPosition + vec4( shadowWorldNormal * pointLightShadows[ i ].shadowNormalBias, 0 );
			vPointShadowCoord[ i ] = pointShadowMatrix[ i ] * shadowWorldPosition;
		}
		#pragma unroll_loop_end
	#endif
#endif
#if NUM_SPOT_LIGHT_COORDS > 0
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SPOT_LIGHT_COORDS; i ++ ) {
		shadowWorldPosition = worldPosition;
		#if ( defined( USE_SHADOWMAP ) && UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
			shadowWorldPosition.xyz += shadowWorldNormal * spotLightShadows[ i ].shadowNormalBias;
		#endif
		vSpotLightCoord[ i ] = spotLightMatrix[ i ] * shadowWorldPosition;
	}
	#pragma unroll_loop_end
#endif`,th=`float getShadowMask() {
	float shadow = 1.0;
	#ifdef USE_SHADOWMAP
	#if NUM_DIR_LIGHT_SHADOWS > 0
	DirectionalLightShadow directionalLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_DIR_LIGHT_SHADOWS; i ++ ) {
		directionalLight = directionalLightShadows[ i ];
		shadow *= receiveShadow ? getShadow( directionalShadowMap[ i ], directionalLight.shadowMapSize, directionalLight.shadowIntensity, directionalLight.shadowBias, directionalLight.shadowRadius, vDirectionalShadowCoord[ i ] ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#if NUM_SPOT_LIGHT_SHADOWS > 0
	SpotLightShadow spotLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SPOT_LIGHT_SHADOWS; i ++ ) {
		spotLight = spotLightShadows[ i ];
		shadow *= receiveShadow ? getShadow( spotShadowMap[ i ], spotLight.shadowMapSize, spotLight.shadowIntensity, spotLight.shadowBias, spotLight.shadowRadius, vSpotLightCoord[ i ] ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0 && ( defined( SHADOWMAP_TYPE_PCF ) || defined( SHADOWMAP_TYPE_BASIC ) )
	PointLightShadow pointLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_POINT_LIGHT_SHADOWS; i ++ ) {
		pointLight = pointLightShadows[ i ];
		shadow *= receiveShadow ? getPointShadow( pointShadowMap[ i ], pointLight.shadowMapSize, pointLight.shadowIntensity, pointLight.shadowBias, pointLight.shadowRadius, vPointShadowCoord[ i ], pointLight.shadowCameraNear, pointLight.shadowCameraFar ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#endif
	return shadow;
}`,eh=`#ifdef USE_SKINNING
	mat4 boneMatX = getBoneMatrix( skinIndex.x );
	mat4 boneMatY = getBoneMatrix( skinIndex.y );
	mat4 boneMatZ = getBoneMatrix( skinIndex.z );
	mat4 boneMatW = getBoneMatrix( skinIndex.w );
#endif`,nh=`#ifdef USE_SKINNING
	uniform mat4 bindMatrix;
	uniform mat4 bindMatrixInverse;
	uniform highp sampler2D boneTexture;
	mat4 getBoneMatrix( const in float i ) {
		int size = textureSize( boneTexture, 0 ).x;
		int j = int( i ) * 4;
		int x = j % size;
		int y = j / size;
		vec4 v1 = texelFetch( boneTexture, ivec2( x, y ), 0 );
		vec4 v2 = texelFetch( boneTexture, ivec2( x + 1, y ), 0 );
		vec4 v3 = texelFetch( boneTexture, ivec2( x + 2, y ), 0 );
		vec4 v4 = texelFetch( boneTexture, ivec2( x + 3, y ), 0 );
		return mat4( v1, v2, v3, v4 );
	}
#endif`,ih=`#ifdef USE_SKINNING
	vec4 skinVertex = bindMatrix * vec4( transformed, 1.0 );
	vec4 skinned = vec4( 0.0 );
	skinned += boneMatX * skinVertex * skinWeight.x;
	skinned += boneMatY * skinVertex * skinWeight.y;
	skinned += boneMatZ * skinVertex * skinWeight.z;
	skinned += boneMatW * skinVertex * skinWeight.w;
	transformed = ( bindMatrixInverse * skinned ).xyz;
#endif`,sh=`#ifdef USE_SKINNING
	mat4 skinMatrix = mat4( 0.0 );
	skinMatrix += skinWeight.x * boneMatX;
	skinMatrix += skinWeight.y * boneMatY;
	skinMatrix += skinWeight.z * boneMatZ;
	skinMatrix += skinWeight.w * boneMatW;
	skinMatrix = bindMatrixInverse * skinMatrix * bindMatrix;
	objectNormal = vec4( skinMatrix * vec4( objectNormal, 0.0 ) ).xyz;
	#ifdef USE_TANGENT
		objectTangent = vec4( skinMatrix * vec4( objectTangent, 0.0 ) ).xyz;
	#endif
#endif`,rh=`float specularStrength;
#ifdef USE_SPECULARMAP
	vec4 texelSpecular = texture2D( specularMap, vSpecularMapUv );
	specularStrength = texelSpecular.r;
#else
	specularStrength = 1.0;
#endif`,oh=`#ifdef USE_SPECULARMAP
	uniform sampler2D specularMap;
#endif`,ah=`#if defined( TONE_MAPPING )
	gl_FragColor.rgb = toneMapping( gl_FragColor.rgb );
#endif`,ch=`#ifndef saturate
#define saturate( a ) clamp( a, 0.0, 1.0 )
#endif
uniform float toneMappingExposure;
vec3 LinearToneMapping( vec3 color ) {
	return saturate( toneMappingExposure * color );
}
vec3 ReinhardToneMapping( vec3 color ) {
	color *= toneMappingExposure;
	return saturate( color / ( vec3( 1.0 ) + color ) );
}
vec3 CineonToneMapping( vec3 color ) {
	color *= toneMappingExposure;
	color = max( vec3( 0.0 ), color - 0.004 );
	return pow( ( color * ( 6.2 * color + 0.5 ) ) / ( color * ( 6.2 * color + 1.7 ) + 0.06 ), vec3( 2.2 ) );
}
vec3 RRTAndODTFit( vec3 v ) {
	vec3 a = v * ( v + 0.0245786 ) - 0.000090537;
	vec3 b = v * ( 0.983729 * v + 0.4329510 ) + 0.238081;
	return a / b;
}
vec3 ACESFilmicToneMapping( vec3 color ) {
	const mat3 ACESInputMat = mat3(
		vec3( 0.59719, 0.07600, 0.02840 ),		vec3( 0.35458, 0.90834, 0.13383 ),
		vec3( 0.04823, 0.01566, 0.83777 )
	);
	const mat3 ACESOutputMat = mat3(
		vec3(  1.60475, -0.10208, -0.00327 ),		vec3( -0.53108,  1.10813, -0.07276 ),
		vec3( -0.07367, -0.00605,  1.07602 )
	);
	color *= toneMappingExposure / 0.6;
	color = ACESInputMat * color;
	color = RRTAndODTFit( color );
	color = ACESOutputMat * color;
	return saturate( color );
}
const mat3 LINEAR_REC2020_TO_LINEAR_SRGB = mat3(
	vec3( 1.6605, - 0.1246, - 0.0182 ),
	vec3( - 0.5876, 1.1329, - 0.1006 ),
	vec3( - 0.0728, - 0.0083, 1.1187 )
);
const mat3 LINEAR_SRGB_TO_LINEAR_REC2020 = mat3(
	vec3( 0.6274, 0.0691, 0.0164 ),
	vec3( 0.3293, 0.9195, 0.0880 ),
	vec3( 0.0433, 0.0113, 0.8956 )
);
vec3 agxDefaultContrastApprox( vec3 x ) {
	vec3 x2 = x * x;
	vec3 x4 = x2 * x2;
	return + 15.5 * x4 * x2
		- 40.14 * x4 * x
		+ 31.96 * x4
		- 6.868 * x2 * x
		+ 0.4298 * x2
		+ 0.1191 * x
		- 0.00232;
}
vec3 AgXToneMapping( vec3 color ) {
	const mat3 AgXInsetMatrix = mat3(
		vec3( 0.856627153315983, 0.137318972929847, 0.11189821299995 ),
		vec3( 0.0951212405381588, 0.761241990602591, 0.0767994186031903 ),
		vec3( 0.0482516061458583, 0.101439036467562, 0.811302368396859 )
	);
	const mat3 AgXOutsetMatrix = mat3(
		vec3( 1.1271005818144368, - 0.1413297634984383, - 0.14132976349843826 ),
		vec3( - 0.11060664309660323, 1.157823702216272, - 0.11060664309660294 ),
		vec3( - 0.016493938717834573, - 0.016493938717834257, 1.2519364065950405 )
	);
	const float AgxMinEv = - 12.47393;	const float AgxMaxEv = 4.026069;
	color *= toneMappingExposure;
	color = LINEAR_SRGB_TO_LINEAR_REC2020 * color;
	color = AgXInsetMatrix * color;
	color = max( color, 1e-10 );	color = log2( color );
	color = ( color - AgxMinEv ) / ( AgxMaxEv - AgxMinEv );
	color = clamp( color, 0.0, 1.0 );
	color = agxDefaultContrastApprox( color );
	color = AgXOutsetMatrix * color;
	color = pow( max( vec3( 0.0 ), color ), vec3( 2.2 ) );
	color = LINEAR_REC2020_TO_LINEAR_SRGB * color;
	color = clamp( color, 0.0, 1.0 );
	return color;
}
vec3 NeutralToneMapping( vec3 color ) {
	const float StartCompression = 0.8 - 0.04;
	const float Desaturation = 0.15;
	color *= toneMappingExposure;
	float x = min( color.r, min( color.g, color.b ) );
	float offset = x < 0.08 ? x - 6.25 * x * x : 0.04;
	color -= offset;
	float peak = max( color.r, max( color.g, color.b ) );
	if ( peak < StartCompression ) return color;
	float d = 1. - StartCompression;
	float newPeak = 1. - d * d / ( peak + d - StartCompression );
	color *= newPeak / peak;
	float g = 1. - 1. / ( Desaturation * ( peak - newPeak ) + 1. );
	return mix( color, vec3( newPeak ), g );
}
vec3 CustomToneMapping( vec3 color ) { return color; }`,lh=`#ifdef USE_TRANSMISSION
	material.transmission = transmission;
	material.transmissionAlpha = 1.0;
	material.thickness = thickness;
	material.attenuationDistance = attenuationDistance;
	material.attenuationColor = attenuationColor;
	#ifdef USE_TRANSMISSIONMAP
		material.transmission *= texture2D( transmissionMap, vTransmissionMapUv ).r;
	#endif
	#ifdef USE_THICKNESSMAP
		material.thickness *= texture2D( thicknessMap, vThicknessMapUv ).g;
	#endif
	vec3 pos = vWorldPosition;
	vec3 v = normalize( cameraPosition - pos );
	vec3 n = transformNormalByInverseViewMatrix( normal, viewMatrix );
	vec4 transmitted = getIBLVolumeRefraction(
		n, v, material.roughness, material.diffuseContribution, material.specularColorBlended, material.specularF90,
		pos, modelMatrix, viewMatrix, projectionMatrix, material.dispersion, material.ior, material.thickness,
		material.attenuationColor, material.attenuationDistance );
	material.transmissionAlpha = mix( material.transmissionAlpha, transmitted.a, material.transmission );
	totalDiffuse = mix( totalDiffuse, transmitted.rgb, material.transmission );
#endif`,uh=`#ifdef USE_TRANSMISSION
	uniform float transmission;
	uniform float thickness;
	uniform float attenuationDistance;
	uniform vec3 attenuationColor;
	#ifdef USE_TRANSMISSIONMAP
		uniform sampler2D transmissionMap;
	#endif
	#ifdef USE_THICKNESSMAP
		uniform sampler2D thicknessMap;
	#endif
	uniform vec2 transmissionSamplerSize;
	uniform sampler2D transmissionSamplerMap;
	uniform mat4 modelMatrix;
	uniform mat4 projectionMatrix;
	varying vec3 vWorldPosition;
	float w0( float a ) {
		return ( 1.0 / 6.0 ) * ( a * ( a * ( - a + 3.0 ) - 3.0 ) + 1.0 );
	}
	float w1( float a ) {
		return ( 1.0 / 6.0 ) * ( a *  a * ( 3.0 * a - 6.0 ) + 4.0 );
	}
	float w2( float a ){
		return ( 1.0 / 6.0 ) * ( a * ( a * ( - 3.0 * a + 3.0 ) + 3.0 ) + 1.0 );
	}
	float w3( float a ) {
		return ( 1.0 / 6.0 ) * ( a * a * a );
	}
	float g0( float a ) {
		return w0( a ) + w1( a );
	}
	float g1( float a ) {
		return w2( a ) + w3( a );
	}
	float h0( float a ) {
		return - 1.0 + w1( a ) / ( w0( a ) + w1( a ) );
	}
	float h1( float a ) {
		return 1.0 + w3( a ) / ( w2( a ) + w3( a ) );
	}
	vec4 bicubic( sampler2D tex, vec2 uv, vec4 texelSize, float lod ) {
		uv = uv * texelSize.zw + 0.5;
		vec2 iuv = floor( uv );
		vec2 fuv = fract( uv );
		float g0x = g0( fuv.x );
		float g1x = g1( fuv.x );
		float h0x = h0( fuv.x );
		float h1x = h1( fuv.x );
		float h0y = h0( fuv.y );
		float h1y = h1( fuv.y );
		vec2 p0 = ( vec2( iuv.x + h0x, iuv.y + h0y ) - 0.5 ) * texelSize.xy;
		vec2 p1 = ( vec2( iuv.x + h1x, iuv.y + h0y ) - 0.5 ) * texelSize.xy;
		vec2 p2 = ( vec2( iuv.x + h0x, iuv.y + h1y ) - 0.5 ) * texelSize.xy;
		vec2 p3 = ( vec2( iuv.x + h1x, iuv.y + h1y ) - 0.5 ) * texelSize.xy;
		return g0( fuv.y ) * ( g0x * textureLod( tex, p0, lod ) + g1x * textureLod( tex, p1, lod ) ) +
			g1( fuv.y ) * ( g0x * textureLod( tex, p2, lod ) + g1x * textureLod( tex, p3, lod ) );
	}
	vec4 textureBicubic( sampler2D sampler, vec2 uv, float lod ) {
		vec2 fLodSize = vec2( textureSize( sampler, int( lod ) ) );
		vec2 cLodSize = vec2( textureSize( sampler, int( lod + 1.0 ) ) );
		vec2 fLodSizeInv = 1.0 / fLodSize;
		vec2 cLodSizeInv = 1.0 / cLodSize;
		vec4 fSample = bicubic( sampler, uv, vec4( fLodSizeInv, fLodSize ), floor( lod ) );
		vec4 cSample = bicubic( sampler, uv, vec4( cLodSizeInv, cLodSize ), ceil( lod ) );
		return mix( fSample, cSample, fract( lod ) );
	}
	vec3 getVolumeTransmissionRay( const in vec3 n, const in vec3 v, const in float thickness, const in float ior, const in mat4 modelMatrix ) {
		vec3 refractionVector = refract( - v, normalize( n ), 1.0 / ior );
		vec3 modelScale;
		modelScale.x = length( vec3( modelMatrix[ 0 ].xyz ) );
		modelScale.y = length( vec3( modelMatrix[ 1 ].xyz ) );
		modelScale.z = length( vec3( modelMatrix[ 2 ].xyz ) );
		return normalize( refractionVector ) * thickness * modelScale;
	}
	float applyIorToRoughness( const in float roughness, const in float ior ) {
		return roughness * clamp( ior * 2.0 - 2.0, 0.0, 1.0 );
	}
	vec4 getTransmissionSample( const in vec2 fragCoord, const in float roughness, const in float ior ) {
		float lod = log2( transmissionSamplerSize.x ) * applyIorToRoughness( roughness, ior );
		return textureBicubic( transmissionSamplerMap, fragCoord.xy, lod );
	}
	vec3 volumeAttenuation( const in float transmissionDistance, const in vec3 attenuationColor, const in float attenuationDistance ) {
		if ( isinf( attenuationDistance ) ) {
			return vec3( 1.0 );
		} else {
			vec3 attenuationCoefficient = -log( attenuationColor ) / attenuationDistance;
			vec3 transmittance = exp( - attenuationCoefficient * transmissionDistance );			return transmittance;
		}
	}
	vec4 getIBLVolumeRefraction( const in vec3 n, const in vec3 v, const in float roughness, const in vec3 diffuseColor,
		const in vec3 specularColor, const in float specularF90, const in vec3 position, const in mat4 modelMatrix,
		const in mat4 viewMatrix, const in mat4 projMatrix, const in float dispersion, const in float ior, const in float thickness,
		const in vec3 attenuationColor, const in float attenuationDistance ) {
		vec4 transmittedLight;
		vec3 transmittance;
		#ifdef USE_DISPERSION
			float halfSpread = ( ior - 1.0 ) * 0.025 * dispersion;
			vec3 iors = vec3( ior - halfSpread, ior, ior + halfSpread );
			for ( int i = 0; i < 3; i ++ ) {
				vec3 transmissionRay = getVolumeTransmissionRay( n, v, thickness, iors[ i ], modelMatrix );
				vec3 refractedRayExit = position + transmissionRay;
				vec4 ndcPos = projMatrix * viewMatrix * vec4( refractedRayExit, 1.0 );
				vec2 refractionCoords = ndcPos.xy / ndcPos.w;
				refractionCoords += 1.0;
				refractionCoords /= 2.0;
				vec4 transmissionSample = getTransmissionSample( refractionCoords, roughness, iors[ i ] );
				transmittedLight[ i ] = transmissionSample[ i ];
				transmittedLight.a += transmissionSample.a;
				transmittance[ i ] = diffuseColor[ i ] * volumeAttenuation( length( transmissionRay ), attenuationColor, attenuationDistance )[ i ];
			}
			transmittedLight.a /= 3.0;
		#else
			vec3 transmissionRay = getVolumeTransmissionRay( n, v, thickness, ior, modelMatrix );
			vec3 refractedRayExit = position + transmissionRay;
			vec4 ndcPos = projMatrix * viewMatrix * vec4( refractedRayExit, 1.0 );
			vec2 refractionCoords = ndcPos.xy / ndcPos.w;
			refractionCoords += 1.0;
			refractionCoords /= 2.0;
			transmittedLight = getTransmissionSample( refractionCoords, roughness, ior );
			transmittance = diffuseColor * volumeAttenuation( length( transmissionRay ), attenuationColor, attenuationDistance );
		#endif
		vec3 attenuatedColor = transmittance * transmittedLight.rgb;
		vec3 F = EnvironmentBRDF( n, v, specularColor, specularF90, roughness );
		float transmittanceFactor = ( transmittance.r + transmittance.g + transmittance.b ) / 3.0;
		return vec4( ( 1.0 - F ) * attenuatedColor, 1.0 - ( 1.0 - transmittedLight.a ) * transmittanceFactor );
	}
#endif`,hh=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
	varying vec2 vUv;
#endif
#ifdef USE_MAP
	varying vec2 vMapUv;
#endif
#ifdef USE_ALPHAMAP
	varying vec2 vAlphaMapUv;
#endif
#ifdef USE_LIGHTMAP
	varying vec2 vLightMapUv;
#endif
#ifdef USE_AOMAP
	varying vec2 vAoMapUv;
#endif
#ifdef USE_BUMPMAP
	varying vec2 vBumpMapUv;
#endif
#ifdef USE_NORMALMAP
	varying vec2 vNormalMapUv;
#endif
#ifdef USE_EMISSIVEMAP
	varying vec2 vEmissiveMapUv;
#endif
#ifdef USE_METALNESSMAP
	varying vec2 vMetalnessMapUv;
#endif
#ifdef USE_ROUGHNESSMAP
	varying vec2 vRoughnessMapUv;
#endif
#ifdef USE_ANISOTROPYMAP
	varying vec2 vAnisotropyMapUv;
#endif
#ifdef USE_CLEARCOATMAP
	varying vec2 vClearcoatMapUv;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	varying vec2 vClearcoatNormalMapUv;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	varying vec2 vClearcoatRoughnessMapUv;
#endif
#ifdef USE_IRIDESCENCEMAP
	varying vec2 vIridescenceMapUv;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	varying vec2 vIridescenceThicknessMapUv;
#endif
#ifdef USE_SHEEN_COLORMAP
	varying vec2 vSheenColorMapUv;
#endif
#ifdef USE_SHEEN_ROUGHNESSMAP
	varying vec2 vSheenRoughnessMapUv;
#endif
#ifdef USE_SPECULARMAP
	varying vec2 vSpecularMapUv;
#endif
#ifdef USE_SPECULAR_COLORMAP
	varying vec2 vSpecularColorMapUv;
#endif
#ifdef USE_SPECULAR_INTENSITYMAP
	varying vec2 vSpecularIntensityMapUv;
#endif
#ifdef USE_TRANSMISSIONMAP
	uniform mat3 transmissionMapTransform;
	varying vec2 vTransmissionMapUv;
#endif
#ifdef USE_THICKNESSMAP
	uniform mat3 thicknessMapTransform;
	varying vec2 vThicknessMapUv;
#endif`,fh=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
	varying vec2 vUv;
#endif
#ifdef USE_MAP
	uniform mat3 mapTransform;
	varying vec2 vMapUv;
#endif
#ifdef USE_ALPHAMAP
	uniform mat3 alphaMapTransform;
	varying vec2 vAlphaMapUv;
#endif
#ifdef USE_LIGHTMAP
	uniform mat3 lightMapTransform;
	varying vec2 vLightMapUv;
#endif
#ifdef USE_AOMAP
	uniform mat3 aoMapTransform;
	varying vec2 vAoMapUv;
#endif
#ifdef USE_BUMPMAP
	uniform mat3 bumpMapTransform;
	varying vec2 vBumpMapUv;
#endif
#ifdef USE_NORMALMAP
	uniform mat3 normalMapTransform;
	varying vec2 vNormalMapUv;
#endif
#ifdef USE_DISPLACEMENTMAP
	uniform mat3 displacementMapTransform;
	varying vec2 vDisplacementMapUv;
#endif
#ifdef USE_EMISSIVEMAP
	uniform mat3 emissiveMapTransform;
	varying vec2 vEmissiveMapUv;
#endif
#ifdef USE_METALNESSMAP
	uniform mat3 metalnessMapTransform;
	varying vec2 vMetalnessMapUv;
#endif
#ifdef USE_ROUGHNESSMAP
	uniform mat3 roughnessMapTransform;
	varying vec2 vRoughnessMapUv;
#endif
#ifdef USE_ANISOTROPYMAP
	uniform mat3 anisotropyMapTransform;
	varying vec2 vAnisotropyMapUv;
#endif
#ifdef USE_CLEARCOATMAP
	uniform mat3 clearcoatMapTransform;
	varying vec2 vClearcoatMapUv;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	uniform mat3 clearcoatNormalMapTransform;
	varying vec2 vClearcoatNormalMapUv;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	uniform mat3 clearcoatRoughnessMapTransform;
	varying vec2 vClearcoatRoughnessMapUv;
#endif
#ifdef USE_SHEEN_COLORMAP
	uniform mat3 sheenColorMapTransform;
	varying vec2 vSheenColorMapUv;
#endif
#ifdef USE_SHEEN_ROUGHNESSMAP
	uniform mat3 sheenRoughnessMapTransform;
	varying vec2 vSheenRoughnessMapUv;
#endif
#ifdef USE_IRIDESCENCEMAP
	uniform mat3 iridescenceMapTransform;
	varying vec2 vIridescenceMapUv;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	uniform mat3 iridescenceThicknessMapTransform;
	varying vec2 vIridescenceThicknessMapUv;
#endif
#ifdef USE_SPECULARMAP
	uniform mat3 specularMapTransform;
	varying vec2 vSpecularMapUv;
#endif
#ifdef USE_SPECULAR_COLORMAP
	uniform mat3 specularColorMapTransform;
	varying vec2 vSpecularColorMapUv;
#endif
#ifdef USE_SPECULAR_INTENSITYMAP
	uniform mat3 specularIntensityMapTransform;
	varying vec2 vSpecularIntensityMapUv;
#endif
#ifdef USE_TRANSMISSIONMAP
	uniform mat3 transmissionMapTransform;
	varying vec2 vTransmissionMapUv;
#endif
#ifdef USE_THICKNESSMAP
	uniform mat3 thicknessMapTransform;
	varying vec2 vThicknessMapUv;
#endif`,dh=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
	vUv = vec3( uv, 1 ).xy;
#endif
#ifdef USE_MAP
	vMapUv = ( mapTransform * vec3( MAP_UV, 1 ) ).xy;
#endif
#ifdef USE_ALPHAMAP
	vAlphaMapUv = ( alphaMapTransform * vec3( ALPHAMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_LIGHTMAP
	vLightMapUv = ( lightMapTransform * vec3( LIGHTMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_AOMAP
	vAoMapUv = ( aoMapTransform * vec3( AOMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_BUMPMAP
	vBumpMapUv = ( bumpMapTransform * vec3( BUMPMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_NORMALMAP
	vNormalMapUv = ( normalMapTransform * vec3( NORMALMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_DISPLACEMENTMAP
	vDisplacementMapUv = ( displacementMapTransform * vec3( DISPLACEMENTMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_EMISSIVEMAP
	vEmissiveMapUv = ( emissiveMapTransform * vec3( EMISSIVEMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_METALNESSMAP
	vMetalnessMapUv = ( metalnessMapTransform * vec3( METALNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_ROUGHNESSMAP
	vRoughnessMapUv = ( roughnessMapTransform * vec3( ROUGHNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_ANISOTROPYMAP
	vAnisotropyMapUv = ( anisotropyMapTransform * vec3( ANISOTROPYMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_CLEARCOATMAP
	vClearcoatMapUv = ( clearcoatMapTransform * vec3( CLEARCOATMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	vClearcoatNormalMapUv = ( clearcoatNormalMapTransform * vec3( CLEARCOAT_NORMALMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	vClearcoatRoughnessMapUv = ( clearcoatRoughnessMapTransform * vec3( CLEARCOAT_ROUGHNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_IRIDESCENCEMAP
	vIridescenceMapUv = ( iridescenceMapTransform * vec3( IRIDESCENCEMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	vIridescenceThicknessMapUv = ( iridescenceThicknessMapTransform * vec3( IRIDESCENCE_THICKNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SHEEN_COLORMAP
	vSheenColorMapUv = ( sheenColorMapTransform * vec3( SHEEN_COLORMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SHEEN_ROUGHNESSMAP
	vSheenRoughnessMapUv = ( sheenRoughnessMapTransform * vec3( SHEEN_ROUGHNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SPECULARMAP
	vSpecularMapUv = ( specularMapTransform * vec3( SPECULARMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SPECULAR_COLORMAP
	vSpecularColorMapUv = ( specularColorMapTransform * vec3( SPECULAR_COLORMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SPECULAR_INTENSITYMAP
	vSpecularIntensityMapUv = ( specularIntensityMapTransform * vec3( SPECULAR_INTENSITYMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_TRANSMISSIONMAP
	vTransmissionMapUv = ( transmissionMapTransform * vec3( TRANSMISSIONMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_THICKNESSMAP
	vThicknessMapUv = ( thicknessMapTransform * vec3( THICKNESSMAP_UV, 1 ) ).xy;
#endif`,ph=`#if defined( USE_ENVMAP ) || defined( DISTANCE ) || defined ( USE_SHADOWMAP ) || defined ( USE_TRANSMISSION ) || NUM_SPOT_LIGHT_COORDS > 0
	vec4 worldPosition = vec4( transformed, 1.0 );
	#ifdef USE_BATCHING
		worldPosition = batchingMatrix * worldPosition;
	#endif
	#ifdef USE_INSTANCING
		worldPosition = instanceMatrix * worldPosition;
	#endif
	worldPosition = modelMatrix * worldPosition;
#endif`,mh=`varying vec2 vUv;
uniform mat3 uvTransform;
void main() {
	vUv = ( uvTransform * vec3( uv, 1 ) ).xy;
	gl_Position = vec4( position.xy, 1.0, 1.0 );
}`,gh=`uniform sampler2D t2D;
uniform float backgroundIntensity;
varying vec2 vUv;
void main() {
	vec4 texColor = texture2D( t2D, vUv );
	#ifdef DECODE_VIDEO_TEXTURE
		texColor = vec4( mix( pow( texColor.rgb * 0.9478672986 + vec3( 0.0521327014 ), vec3( 2.4 ) ), texColor.rgb * 0.0773993808, vec3( lessThanEqual( texColor.rgb, vec3( 0.04045 ) ) ) ), texColor.w );
	#endif
	texColor.rgb *= backgroundIntensity;
	gl_FragColor = texColor;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,xh=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
	gl_Position.z = gl_Position.w;
}`,_h=`#ifdef ENVMAP_TYPE_CUBE
	uniform samplerCube envMap;
#elif defined( ENVMAP_TYPE_CUBE_UV )
	uniform sampler2D envMap;
#endif
uniform float backgroundBlurriness;
uniform float backgroundIntensity;
uniform mat3 backgroundRotation;
varying vec3 vWorldDirection;
#include <cube_uv_reflection_fragment>
void main() {
	#ifdef ENVMAP_TYPE_CUBE
		vec4 texColor = textureCube( envMap, backgroundRotation * vWorldDirection );
	#elif defined( ENVMAP_TYPE_CUBE_UV )
		vec4 texColor = textureCubeUV( envMap, backgroundRotation * vWorldDirection, backgroundBlurriness );
	#else
		vec4 texColor = vec4( 0.0, 0.0, 0.0, 1.0 );
	#endif
	texColor.rgb *= backgroundIntensity;
	gl_FragColor = texColor;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,yh=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
	gl_Position.z = gl_Position.w;
}`,vh=`uniform samplerCube tCube;
uniform float tFlip;
uniform float opacity;
varying vec3 vWorldDirection;
void main() {
	vec4 texColor = textureCube( tCube, vec3( tFlip * vWorldDirection.x, vWorldDirection.yz ) );
	gl_FragColor = texColor;
	gl_FragColor.a *= opacity;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,Mh=`#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
varying vec2 vHighPrecisionZW;
void main() {
	#include <uv_vertex>
	#include <batching_vertex>
	#include <skinbase_vertex>
	#include <morphinstance_vertex>
	#ifdef USE_DISPLACEMENTMAP
		#include <beginnormal_vertex>
		#include <morphnormal_vertex>
		#include <skinnormal_vertex>
	#endif
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vHighPrecisionZW = gl_Position.zw;
}`,bh=`#if DEPTH_PACKING == 3200
	uniform float opacity;
#endif
#include <common>
#include <packing>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
varying vec2 vHighPrecisionZW;
void main() {
	vec4 diffuseColor = vec4( 1.0 );
	#include <clipping_planes_fragment>
	#if DEPTH_PACKING == 3200
		diffuseColor.a = opacity;
	#endif
	#include <map_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <logdepthbuf_fragment>
	#ifdef USE_REVERSED_DEPTH_BUFFER
		float fragCoordZ = vHighPrecisionZW[ 0 ] / vHighPrecisionZW[ 1 ];
	#else
		float fragCoordZ = 0.5 * vHighPrecisionZW[ 0 ] / vHighPrecisionZW[ 1 ] + 0.5;
	#endif
	#if DEPTH_PACKING == 3200
		gl_FragColor = vec4( vec3( 1.0 - fragCoordZ ), opacity );
	#elif DEPTH_PACKING == 3201
		gl_FragColor = packDepthToRGBA( fragCoordZ );
	#elif DEPTH_PACKING == 3202
		gl_FragColor = vec4( packDepthToRGB( fragCoordZ ), 1.0 );
	#elif DEPTH_PACKING == 3203
		gl_FragColor = vec4( packDepthToRG( fragCoordZ ), 0.0, 1.0 );
	#endif
}`,Sh=`#define DISTANCE
varying vec3 vWorldPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <batching_vertex>
	#include <skinbase_vertex>
	#include <morphinstance_vertex>
	#ifdef USE_DISPLACEMENTMAP
		#include <beginnormal_vertex>
		#include <morphnormal_vertex>
		#include <skinnormal_vertex>
	#endif
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <worldpos_vertex>
	#include <clipping_planes_vertex>
	vWorldPosition = worldPosition.xyz;
}`,Ah=`#define DISTANCE
uniform vec3 referencePosition;
uniform float nearDistance;
uniform float farDistance;
varying vec3 vWorldPosition;
#include <common>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( 1.0 );
	#include <clipping_planes_fragment>
	#include <map_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	float dist = length( vWorldPosition - referencePosition );
	dist = ( dist - nearDistance ) / ( farDistance - nearDistance );
	dist = saturate( dist );
	gl_FragColor = vec4( dist, 0.0, 0.0, 1.0 );
}`,Th=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
}`,wh=`uniform sampler2D tEquirect;
varying vec3 vWorldDirection;
#include <common>
void main() {
	vec3 direction = normalize( vWorldDirection );
	vec2 sampleUV = equirectUv( direction );
	gl_FragColor = texture2D( tEquirect, sampleUV );
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,Eh=`uniform float scale;
attribute float lineDistance;
varying float vLineDistance;
#include <common>
#include <uv_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	vLineDistance = scale * lineDistance;
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <fog_vertex>
}`,Ch=`uniform vec3 diffuse;
uniform float opacity;
uniform float dashSize;
uniform float totalSize;
varying float vLineDistance;
#include <common>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <fog_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	if ( mod( vLineDistance, totalSize ) > dashSize ) {
		discard;
	}
	vec3 outgoingLight = vec3( 0.0 );
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	outgoingLight = diffuseColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
}`,Rh=`#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <envmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#if defined ( USE_ENVMAP ) || defined ( USE_SKINNING )
		#include <beginnormal_vertex>
		#include <morphnormal_vertex>
		#include <skinbase_vertex>
		#include <skinnormal_vertex>
		#include <defaultnormal_vertex>
	#endif
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <worldpos_vertex>
	#include <envmap_vertex>
	#include <fog_vertex>
}`,Ih=`uniform vec3 diffuse;
uniform float opacity;
#ifndef FLAT_SHADED
	varying vec3 vNormal;
#endif
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_pars_fragment>
#include <fog_pars_fragment>
#include <specularmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <specularmap_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	#ifdef USE_LIGHTMAP
		vec4 lightMapTexel = texture2D( lightMap, vLightMapUv );
		reflectedLight.indirectDiffuse += lightMapTexel.rgb * lightMapIntensity * RECIPROCAL_PI;
	#else
		reflectedLight.indirectDiffuse += vec3( 1.0 );
	#endif
	#include <aomap_fragment>
	reflectedLight.indirectDiffuse *= diffuseColor.rgb;
	vec3 outgoingLight = reflectedLight.indirectDiffuse;
	#include <envmap_fragment>
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,Ph=`#define LAMBERT
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <envmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <envmap_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,Nh=`#define LAMBERT
uniform vec3 diffuse;
uniform vec3 emissive;
uniform float opacity;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <cube_uv_reflection_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_pars_fragment>
#include <envmap_physical_pars_fragment>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_lambert_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <specularmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <specularmap_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_lambert_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + totalEmissiveRadiance;
	#include <envmap_fragment>
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,Lh=`#define MATCAP
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <color_pars_vertex>
#include <displacementmap_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <fog_vertex>
	vViewPosition = - mvPosition.xyz;
}`,Dh=`#define MATCAP
uniform vec3 diffuse;
uniform float opacity;
uniform sampler2D matcap;
varying vec3 vViewPosition;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <fog_pars_fragment>
#include <normal_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	vec3 viewDir = normalize( vViewPosition );
	vec3 x = normalize( vec3( viewDir.z, 0.0, - viewDir.x ) );
	vec3 y = cross( viewDir, x );
	vec2 uv = vec2( dot( x, normal ), dot( y, normal ) ) * 0.495 + 0.5;
	#ifdef USE_MATCAP
		vec4 matcapColor = texture2D( matcap, uv );
	#else
		vec4 matcapColor = vec4( vec3( mix( 0.2, 0.8, uv.y ) ), 1.0 );
	#endif
	vec3 outgoingLight = diffuseColor.rgb * matcapColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,Uh=`#define NORMAL
#if defined( FLAT_SHADED ) || defined( USE_BUMPMAP ) || defined( USE_NORMALMAP_TANGENTSPACE )
	varying vec3 vViewPosition;
#endif
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphinstance_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
#if defined( FLAT_SHADED ) || defined( USE_BUMPMAP ) || defined( USE_NORMALMAP_TANGENTSPACE )
	vViewPosition = - mvPosition.xyz;
#endif
}`,Fh=`#define NORMAL
uniform float opacity;
#if defined( FLAT_SHADED ) || defined( USE_BUMPMAP ) || defined( USE_NORMALMAP_TANGENTSPACE )
	varying vec3 vViewPosition;
#endif
#include <uv_pars_fragment>
#include <normal_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( 0.0, 0.0, 0.0, opacity );
	#include <clipping_planes_fragment>
	#include <logdepthbuf_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	gl_FragColor = vec4( normalize( normal ) * 0.5 + 0.5, diffuseColor.a );
	#ifdef OPAQUE
		gl_FragColor.a = 1.0;
	#endif
}`,Oh=`#define PHONG
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <envmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphinstance_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <envmap_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,Bh=`#define PHONG
uniform vec3 diffuse;
uniform vec3 emissive;
uniform vec3 specular;
uniform float shininess;
uniform float opacity;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <cube_uv_reflection_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_pars_fragment>
#include <envmap_physical_pars_fragment>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_phong_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <specularmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <specularmap_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_phong_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + reflectedLight.directSpecular + reflectedLight.indirectSpecular + totalEmissiveRadiance;
	#include <envmap_fragment>
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,zh=`#define STANDARD
varying vec3 vViewPosition;
#ifdef USE_TRANSMISSION
	varying vec3 vWorldPosition;
#endif
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
#ifdef USE_TRANSMISSION
	vWorldPosition = worldPosition.xyz;
#endif
}`,kh=`#define STANDARD
#ifdef PHYSICAL
	#define IOR
	#define USE_SPECULAR
#endif
uniform vec3 diffuse;
uniform vec3 emissive;
uniform float roughness;
uniform float metalness;
uniform float opacity;
#ifdef IOR
	uniform float ior;
#endif
#ifdef USE_SPECULAR
	uniform float specularIntensity;
	uniform vec3 specularColor;
	#ifdef USE_SPECULAR_COLORMAP
		uniform sampler2D specularColorMap;
	#endif
	#ifdef USE_SPECULAR_INTENSITYMAP
		uniform sampler2D specularIntensityMap;
	#endif
#endif
#ifdef USE_CLEARCOAT
	uniform float clearcoat;
	uniform float clearcoatRoughness;
#endif
#ifdef USE_DISPERSION
	uniform float dispersion;
#endif
#ifdef USE_IRIDESCENCE
	uniform float iridescence;
	uniform float iridescenceIOR;
	uniform float iridescenceThicknessMinimum;
	uniform float iridescenceThicknessMaximum;
#endif
#ifdef USE_SHEEN
	uniform vec3 sheenColor;
	uniform float sheenRoughness;
	#ifdef USE_SHEEN_COLORMAP
		uniform sampler2D sheenColorMap;
	#endif
	#ifdef USE_SHEEN_ROUGHNESSMAP
		uniform sampler2D sheenRoughnessMap;
	#endif
#endif
#ifdef USE_ANISOTROPY
	uniform vec2 anisotropyVector;
	#ifdef USE_ANISOTROPYMAP
		uniform sampler2D anisotropyMap;
	#endif
#endif
varying vec3 vViewPosition;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <iridescence_fragment>
#include <cube_uv_reflection_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_physical_pars_fragment>
#include <fog_pars_fragment>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_physical_pars_fragment>
#include <transmission_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <clearcoat_pars_fragment>
#include <iridescence_pars_fragment>
#include <roughnessmap_pars_fragment>
#include <metalnessmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <roughnessmap_fragment>
	#include <metalnessmap_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <clearcoat_normal_fragment_begin>
	#include <clearcoat_normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_physical_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 totalDiffuse = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse;
	vec3 totalSpecular = reflectedLight.directSpecular + reflectedLight.indirectSpecular;
	#include <transmission_fragment>
	vec3 outgoingLight = totalDiffuse + totalSpecular + totalEmissiveRadiance;
	#ifdef USE_SHEEN
 
		outgoingLight = outgoingLight + sheenSpecularDirect + sheenSpecularIndirect;
 
 	#endif
	#ifdef USE_CLEARCOAT
		float dotNVcc = saturate( dot( geometryClearcoatNormal, geometryViewDir ) );
		vec3 Fcc = F_Schlick( material.clearcoatF0, material.clearcoatF90, dotNVcc );
		outgoingLight = outgoingLight * ( 1.0 - material.clearcoat * Fcc ) + ( clearcoatSpecularDirect + clearcoatSpecularIndirect ) * material.clearcoat;
	#endif
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,Vh=`#define TOON
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,Gh=`#define TOON
uniform vec3 diffuse;
uniform vec3 emissive;
uniform float opacity;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <gradientmap_pars_fragment>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_toon_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_toon_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + totalEmissiveRadiance;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,Hh=`uniform float size;
uniform float scale;
#include <common>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
#ifdef USE_POINTS_UV
	varying vec2 vUv;
	uniform mat3 uvTransform;
#endif
void main() {
	#ifdef USE_POINTS_UV
		vUv = ( uvTransform * vec3( uv, 1 ) ).xy;
	#endif
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <project_vertex>
	gl_PointSize = size;
	#ifdef USE_SIZEATTENUATION
		bool isPerspective = isPerspectiveMatrix( projectionMatrix );
		if ( isPerspective ) gl_PointSize *= ( scale / - mvPosition.z );
	#endif
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <worldpos_vertex>
	#include <fog_vertex>
}`,Wh=`uniform vec3 diffuse;
uniform float opacity;
#include <common>
#include <color_pars_fragment>
#include <map_particle_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <fog_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	vec3 outgoingLight = vec3( 0.0 );
	#include <logdepthbuf_fragment>
	#include <map_particle_fragment>
	#include <color_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	outgoingLight = diffuseColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
}`,Xh=`#include <common>
#include <batching_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <shadowmap_pars_vertex>
void main() {
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphinstance_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <worldpos_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,qh=`uniform vec3 color;
uniform float opacity;
#include <common>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <logdepthbuf_pars_fragment>
#include <shadowmap_pars_fragment>
#include <shadowmask_pars_fragment>
void main() {
	#include <logdepthbuf_fragment>
	gl_FragColor = vec4( color, opacity * ( 1.0 - getShadowMask() ) );
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
}`,$h=`uniform float rotation;
uniform vec2 center;
#include <common>
#include <uv_pars_vertex>
#include <fog_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	vec4 mvPosition = modelViewMatrix[ 3 ];
	vec2 scale = vec2( length( modelMatrix[ 0 ].xyz ), length( modelMatrix[ 1 ].xyz ) );
	#ifndef USE_SIZEATTENUATION
		bool isPerspective = isPerspectiveMatrix( projectionMatrix );
		if ( isPerspective ) scale *= - mvPosition.z;
	#endif
	vec2 alignedPosition = ( position.xy - ( center - vec2( 0.5 ) ) ) * scale;
	vec2 rotatedPosition;
	rotatedPosition.x = cos( rotation ) * alignedPosition.x - sin( rotation ) * alignedPosition.y;
	rotatedPosition.y = sin( rotation ) * alignedPosition.x + cos( rotation ) * alignedPosition.y;
	mvPosition.xy += rotatedPosition;
	gl_Position = projectionMatrix * mvPosition;
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <fog_vertex>
}`,Yh=`uniform vec3 diffuse;
uniform float opacity;
#include <common>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <fog_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	vec3 outgoingLight = vec3( 0.0 );
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	outgoingLight = diffuseColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
}`,Z={alphahash_fragment:ml,alphahash_pars_fragment:gl,alphamap_fragment:xl,alphamap_pars_fragment:_l,alphatest_fragment:yl,alphatest_pars_fragment:vl,aomap_fragment:Ml,aomap_pars_fragment:bl,batching_pars_vertex:Sl,batching_vertex:Al,begin_vertex:Tl,beginnormal_vertex:wl,bsdfs:El,iridescence_fragment:Cl,bumpmap_pars_fragment:Rl,clipping_planes_fragment:Il,clipping_planes_pars_fragment:Pl,clipping_planes_pars_vertex:Nl,clipping_planes_vertex:Ll,color_fragment:Dl,color_pars_fragment:Ul,color_pars_vertex:Fl,color_vertex:Ol,common:Bl,cube_uv_reflection_fragment:zl,defaultnormal_vertex:kl,displacementmap_pars_vertex:Vl,displacementmap_vertex:Gl,emissivemap_fragment:Hl,emissivemap_pars_fragment:Wl,colorspace_fragment:Xl,colorspace_pars_fragment:ql,envmap_fragment:$l,envmap_common_pars_fragment:Yl,envmap_pars_fragment:Zl,envmap_pars_vertex:Jl,envmap_physical_pars_fragment:au,envmap_vertex:Kl,fog_vertex:jl,fog_pars_vertex:Ql,fog_fragment:tu,fog_pars_fragment:eu,gradientmap_pars_fragment:nu,lightmap_pars_fragment:iu,lights_lambert_fragment:su,lights_lambert_pars_fragment:ru,lights_pars_begin:ou,lights_toon_fragment:cu,lights_toon_pars_fragment:lu,lights_phong_fragment:uu,lights_phong_pars_fragment:hu,lights_physical_fragment:fu,lights_physical_pars_fragment:du,lights_fragment_begin:pu,lights_fragment_maps:mu,lights_fragment_end:gu,lightprobes_pars_fragment:xu,logdepthbuf_fragment:_u,logdepthbuf_pars_fragment:yu,logdepthbuf_pars_vertex:vu,logdepthbuf_vertex:Mu,map_fragment:bu,map_pars_fragment:Su,map_particle_fragment:Au,map_particle_pars_fragment:Tu,metalnessmap_fragment:wu,metalnessmap_pars_fragment:Eu,morphinstance_vertex:Cu,morphcolor_vertex:Ru,morphnormal_vertex:Iu,morphtarget_pars_vertex:Pu,morphtarget_vertex:Nu,normal_fragment_begin:Lu,normal_fragment_maps:Du,normal_pars_fragment:Uu,normal_pars_vertex:Fu,normal_vertex:Ou,normalmap_pars_fragment:Bu,clearcoat_normal_fragment_begin:zu,clearcoat_normal_fragment_maps:ku,clearcoat_pars_fragment:Vu,iridescence_pars_fragment:Gu,opaque_fragment:Hu,packing:Wu,premultiplied_alpha_fragment:Xu,project_vertex:qu,dithering_fragment:$u,dithering_pars_fragment:Yu,roughnessmap_fragment:Zu,roughnessmap_pars_fragment:Ju,shadowmap_pars_fragment:Ku,shadowmap_pars_vertex:ju,shadowmap_vertex:Qu,shadowmask_pars_fragment:th,skinbase_vertex:eh,skinning_pars_vertex:nh,skinning_vertex:ih,skinnormal_vertex:sh,specularmap_fragment:rh,specularmap_pars_fragment:oh,tonemapping_fragment:ah,tonemapping_pars_fragment:ch,transmission_fragment:lh,transmission_pars_fragment:uh,uv_pars_fragment:hh,uv_pars_vertex:fh,uv_vertex:dh,worldpos_vertex:ph,background_vert:mh,background_frag:gh,backgroundCube_vert:xh,backgroundCube_frag:_h,cube_vert:yh,cube_frag:vh,depth_vert:Mh,depth_frag:bh,distance_vert:Sh,distance_frag:Ah,equirect_vert:Th,equirect_frag:wh,linedashed_vert:Eh,linedashed_frag:Ch,meshbasic_vert:Rh,meshbasic_frag:Ih,meshlambert_vert:Ph,meshlambert_frag:Nh,meshmatcap_vert:Lh,meshmatcap_frag:Dh,meshnormal_vert:Uh,meshnormal_frag:Fh,meshphong_vert:Oh,meshphong_frag:Bh,meshphysical_vert:zh,meshphysical_frag:kh,meshtoon_vert:Vh,meshtoon_frag:Gh,points_vert:Hh,points_frag:Wh,shadow_vert:Xh,shadow_frag:qh,sprite_vert:$h,sprite_frag:Yh},H={common:{diffuse:{value:new yt(16777215)},opacity:{value:1},map:{value:null},mapTransform:{value:new Y},alphaMap:{value:null},alphaMapTransform:{value:new Y},alphaTest:{value:0}},specularmap:{specularMap:{value:null},specularMapTransform:{value:new Y}},envmap:{envMap:{value:null},envMapRotation:{value:new Y},reflectivity:{value:1},ior:{value:1.5},refractionRatio:{value:.98},dfgLUT:{value:null}},aomap:{aoMap:{value:null},aoMapIntensity:{value:1},aoMapTransform:{value:new Y}},lightmap:{lightMap:{value:null},lightMapIntensity:{value:1},lightMapTransform:{value:new Y}},bumpmap:{bumpMap:{value:null},bumpMapTransform:{value:new Y},bumpScale:{value:1}},normalmap:{normalMap:{value:null},normalMapTransform:{value:new Y},normalScale:{value:new xt(1,1)}},displacementmap:{displacementMap:{value:null},displacementMapTransform:{value:new Y},displacementScale:{value:1},displacementBias:{value:0}},emissivemap:{emissiveMap:{value:null},emissiveMapTransform:{value:new Y}},metalnessmap:{metalnessMap:{value:null},metalnessMapTransform:{value:new Y}},roughnessmap:{roughnessMap:{value:null},roughnessMapTransform:{value:new Y}},gradientmap:{gradientMap:{value:null}},fog:{fogDensity:{value:25e-5},fogNear:{value:1},fogFar:{value:2e3},fogColor:{value:new yt(16777215)}},lights:{ambientLightColor:{value:[]},lightProbe:{value:[]},directionalLights:{value:[],properties:{direction:{},color:{}}},directionalLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},directionalShadowMatrix:{value:[]},spotLights:{value:[],properties:{color:{},position:{},direction:{},distance:{},coneCos:{},penumbraCos:{},decay:{}}},spotLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},spotLightMap:{value:[]},spotLightMatrix:{value:[]},pointLights:{value:[],properties:{color:{},position:{},decay:{},distance:{}}},pointLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{},shadowCameraNear:{},shadowCameraFar:{}}},pointShadowMatrix:{value:[]},hemisphereLights:{value:[],properties:{direction:{},skyColor:{},groundColor:{}}},rectAreaLights:{value:[],properties:{color:{},position:{},width:{},height:{}}},ltc_1:{value:null},ltc_2:{value:null},probesSH:{value:null},probesMin:{value:new k},probesMax:{value:new k},probesResolution:{value:new k}},points:{diffuse:{value:new yt(16777215)},opacity:{value:1},size:{value:1},scale:{value:1},map:{value:null},alphaMap:{value:null},alphaMapTransform:{value:new Y},alphaTest:{value:0},uvTransform:{value:new Y}},sprite:{diffuse:{value:new yt(16777215)},opacity:{value:1},center:{value:new xt(.5,.5)},rotation:{value:0},map:{value:null},mapTransform:{value:new Y},alphaMap:{value:null},alphaMapTransform:{value:new Y},alphaTest:{value:0}}},Ao={basic:{uniforms:At([H.common,H.specularmap,H.envmap,H.aomap,H.lightmap,H.fog]),vertexShader:Z.meshbasic_vert,fragmentShader:Z.meshbasic_frag},lambert:{uniforms:At([H.common,H.specularmap,H.envmap,H.aomap,H.lightmap,H.emissivemap,H.bumpmap,H.normalmap,H.displacementmap,H.fog,H.lights,{emissive:{value:new yt(0)},envMapIntensity:{value:1}}]),vertexShader:Z.meshlambert_vert,fragmentShader:Z.meshlambert_frag},phong:{uniforms:At([H.common,H.specularmap,H.envmap,H.aomap,H.lightmap,H.emissivemap,H.bumpmap,H.normalmap,H.displacementmap,H.fog,H.lights,{emissive:{value:new yt(0)},specular:{value:new yt(1118481)},shininess:{value:30},envMapIntensity:{value:1}}]),vertexShader:Z.meshphong_vert,fragmentShader:Z.meshphong_frag},standard:{uniforms:At([H.common,H.envmap,H.aomap,H.lightmap,H.emissivemap,H.bumpmap,H.normalmap,H.displacementmap,H.roughnessmap,H.metalnessmap,H.fog,H.lights,{emissive:{value:new yt(0)},roughness:{value:1},metalness:{value:0},envMapIntensity:{value:1}}]),vertexShader:Z.meshphysical_vert,fragmentShader:Z.meshphysical_frag},toon:{uniforms:At([H.common,H.aomap,H.lightmap,H.emissivemap,H.bumpmap,H.normalmap,H.displacementmap,H.gradientmap,H.fog,H.lights,{emissive:{value:new yt(0)}}]),vertexShader:Z.meshtoon_vert,fragmentShader:Z.meshtoon_frag},matcap:{uniforms:At([H.common,H.bumpmap,H.normalmap,H.displacementmap,H.fog,{matcap:{value:null}}]),vertexShader:Z.meshmatcap_vert,fragmentShader:Z.meshmatcap_frag},points:{uniforms:At([H.points,H.fog]),vertexShader:Z.points_vert,fragmentShader:Z.points_frag},dashed:{uniforms:At([H.common,H.fog,{scale:{value:1},dashSize:{value:1},totalSize:{value:2}}]),vertexShader:Z.linedashed_vert,fragmentShader:Z.linedashed_frag},depth:{uniforms:At([H.common,H.displacementmap]),vertexShader:Z.depth_vert,fragmentShader:Z.depth_frag},normal:{uniforms:At([H.common,H.bumpmap,H.normalmap,H.displacementmap,{opacity:{value:1}}]),vertexShader:Z.meshnormal_vert,fragmentShader:Z.meshnormal_frag},sprite:{uniforms:At([H.sprite,H.fog]),vertexShader:Z.sprite_vert,fragmentShader:Z.sprite_frag},background:{uniforms:{uvTransform:{value:new Y},t2D:{value:null},backgroundIntensity:{value:1}},vertexShader:Z.background_vert,fragmentShader:Z.background_frag},backgroundCube:{uniforms:{envMap:{value:null},backgroundBlurriness:{value:0},backgroundIntensity:{value:1},backgroundRotation:{value:new Y}},vertexShader:Z.backgroundCube_vert,fragmentShader:Z.backgroundCube_frag},cube:{uniforms:{tCube:{value:null},tFlip:{value:-1},opacity:{value:1}},vertexShader:Z.cube_vert,fragmentShader:Z.cube_frag},equirect:{uniforms:{tEquirect:{value:null}},vertexShader:Z.equirect_vert,fragmentShader:Z.equirect_frag},distance:{uniforms:At([H.common,H.displacementmap,{referencePosition:{value:new k},nearDistance:{value:1},farDistance:{value:1e3}}]),vertexShader:Z.distance_vert,fragmentShader:Z.distance_frag},shadow:{uniforms:At([H.lights,H.fog,{color:{value:new yt(0)},opacity:{value:1}}]),vertexShader:Z.shadow_vert,fragmentShader:Z.shadow_frag}};Ao.physical={uniforms:At([Ao.standard.uniforms,{clearcoat:{value:0},clearcoatMap:{value:null},clearcoatMapTransform:{value:new Y},clearcoatNormalMap:{value:null},clearcoatNormalMapTransform:{value:new Y},clearcoatNormalScale:{value:new xt(1,1)},clearcoatRoughness:{value:0},clearcoatRoughnessMap:{value:null},clearcoatRoughnessMapTransform:{value:new Y},dispersion:{value:0},iridescence:{value:0},iridescenceMap:{value:null},iridescenceMapTransform:{value:new Y},iridescenceIOR:{value:1.3},iridescenceThicknessMinimum:{value:100},iridescenceThicknessMaximum:{value:400},iridescenceThicknessMap:{value:null},iridescenceThicknessMapTransform:{value:new Y},sheen:{value:0},sheenColor:{value:new yt(0)},sheenColorMap:{value:null},sheenColorMapTransform:{value:new Y},sheenRoughness:{value:1},sheenRoughnessMap:{value:null},sheenRoughnessMapTransform:{value:new Y},transmission:{value:0},transmissionMap:{value:null},transmissionMapTransform:{value:new Y},transmissionSamplerSize:{value:new xt},transmissionSamplerMap:{value:null},thickness:{value:0},thicknessMap:{value:null},thicknessMapTransform:{value:new Y},attenuationDistance:{value:0},attenuationColor:{value:new yt(0)},specularColor:{value:new yt(1,1,1)},specularColorMap:{value:null},specularColorMapTransform:{value:new Y},specularIntensity:{value:1},specularIntensityMap:{value:null},specularIntensityMapTransform:{value:new Y},anisotropyVector:{value:new xt},anisotropyMap:{value:null},anisotropyMapTransform:{value:new Y}}]),vertexShader:Z.meshphysical_vert,fragmentShader:Z.meshphysical_frag};var Zh=new Y;Zh.set(-1,0,0,0,1,0,0,0,1);var gv={[Ps]:"LINEAR_TONE_MAPPING",[Ns]:"REINHARD_TONE_MAPPING",[Ls]:"CINEON_TONE_MAPPING",[Ds]:"ACES_FILMIC_TONE_MAPPING",[Fs]:"AGX_TONE_MAPPING",[Os]:"NEUTRAL_TONE_MAPPING",[Us]:"CUSTOM_TONE_MAPPING"};var xv=new Float32Array(16),_v=new Float32Array(9),yv=new Float32Array(4);var vv={[Ps]:"Linear",[Ns]:"Reinhard",[Ls]:"Cineon",[Ds]:"ACESFilmic",[Fs]:"AgX",[Os]:"Neutral",[Us]:"Custom"};var Mv={[io]:"SHADOWMAP_TYPE_PCF",[so]:"SHADOWMAP_TYPE_VSM"};var bv={[co]:"ENVMAP_TYPE_CUBE",[zs]:"ENVMAP_TYPE_CUBE",[lo]:"ENVMAP_TYPE_CUBE_UV"};var Sv={[zs]:"ENVMAP_MODE_REFRACTION"};var Av={[ro]:"ENVMAP_BLENDING_MULTIPLY",[oo]:"ENVMAP_BLENDING_MIX",[ao]:"ENVMAP_BLENDING_ADD"};var Jh=new Y;Jh.set(-1,0,0,0,1,0,0,0,1);var Tv=new Uint16Array([12469,15057,12620,14925,13266,14620,13807,14376,14323,13990,14545,13625,14713,13328,14840,12882,14931,12528,14996,12233,15039,11829,15066,11525,15080,11295,15085,10976,15082,10705,15073,10495,13880,14564,13898,14542,13977,14430,14158,14124,14393,13732,14556,13410,14702,12996,14814,12596,14891,12291,14937,11834,14957,11489,14958,11194,14943,10803,14921,10506,14893,10278,14858,9960,14484,14039,14487,14025,14499,13941,14524,13740,14574,13468,14654,13106,14743,12678,14818,12344,14867,11893,14889,11509,14893,11180,14881,10751,14852,10428,14812,10128,14765,9754,14712,9466,14764,13480,14764,13475,14766,13440,14766,13347,14769,13070,14786,12713,14816,12387,14844,11957,14860,11549,14868,11215,14855,10751,14825,10403,14782,10044,14729,9651,14666,9352,14599,9029,14967,12835,14966,12831,14963,12804,14954,12723,14936,12564,14917,12347,14900,11958,14886,11569,14878,11247,14859,10765,14828,10401,14784,10011,14727,9600,14660,9289,14586,8893,14508,8533,15111,12234,15110,12234,15104,12216,15092,12156,15067,12010,15028,11776,14981,11500,14942,11205,14902,10752,14861,10393,14812,9991,14752,9570,14682,9252,14603,8808,14519,8445,14431,8145,15209,11449,15208,11451,15202,11451,15190,11438,15163,11384,15117,11274,15055,10979,14994,10648,14932,10343,14871,9936,14803,9532,14729,9218,14645,8742,14556,8381,14461,8020,14365,7603,15273,10603,15272,10607,15267,10619,15256,10631,15231,10614,15182,10535,15118,10389,15042,10167,14963,9787,14883,9447,14800,9115,14710,8665,14615,8318,14514,7911,14411,7507,14279,7198,15314,9675,15313,9683,15309,9712,15298,9759,15277,9797,15229,9773,15166,9668,15084,9487,14995,9274,14898,8910,14800,8539,14697,8234,14590,7790,14479,7409,14367,7067,14178,6621,15337,8619,15337,8631,15333,8677,15325,8769,15305,8871,15264,8940,15202,8909,15119,8775,15022,8565,14916,8328,14804,8009,14688,7614,14569,7287,14448,6888,14321,6483,14088,6171,15350,7402,15350,7419,15347,7480,15340,7613,15322,7804,15287,7973,15229,8057,15148,8012,15046,7846,14933,7611,14810,7357,14682,7069,14552,6656,14421,6316,14251,5948,14007,5528,15356,5942,15356,5977,15353,6119,15348,6294,15332,6551,15302,6824,15249,7044,15171,7122,15070,7050,14949,6861,14818,6611,14679,6349,14538,6067,14398,5651,14189,5311,13935,4958,15359,4123,15359,4153,15356,4296,15353,4646,15338,5160,15311,5508,15263,5829,15188,6042,15088,6094,14966,6001,14826,5796,14678,5543,14527,5287,14377,4985,14133,4586,13869,4257,15360,1563,15360,1642,15358,2076,15354,2636,15341,3350,15317,4019,15273,4429,15203,4732,15105,4911,14981,4932,14836,4818,14679,4621,14517,4386,14359,4156,14083,3795,13808,3437,15360,122,15360,137,15358,285,15355,636,15344,1274,15322,2177,15281,2765,15215,3223,15120,3451,14995,3569,14846,3567,14681,3466,14511,3305,14344,3121,14037,2800,13753,2467,15360,0,15360,1,15359,21,15355,89,15346,253,15325,479,15287,796,15225,1148,15133,1492,15008,1749,14856,1882,14685,1886,14506,1783,14324,1608,13996,1398,13702,1183]);Un();function Ys(n,t,e,i){let s=e;if(i>=n[s])return s-1;if(i<=n[t])return t;let r=t,o=s,a=r+o>>1;for(;i<n[a]||i>=n[a+1];)i<n[a]?o=a:r=a,a=r+o>>1;return a}d(Ys,"findSpan");var Lo=new Map;function Fn(n,t){let e=Lo.get(t);e||Lo.set(t,e=[]);let i=e[n];return i||(e[n]=i=new Float64Array(t)),i}d(Fn,"scratch");function Zs(n,t,e,i,s){let r=Fn(0,t+1),o=Fn(1,t+1);s[0]=1;for(let a=1;a<=t;a+=1){r[a]=i-n[e+1-a],o[a]=n[e+a]-i;let c=0;for(let l=0;l<a;l+=1){let u=s[l]/(o[l+1]+r[a-l]);s[l]=c+o[l+1]*u,c=r[a-l]*u}s[a]=c}return s}d(Zs,"basisFunctions");function Do(n,t,e,i){let s=n.deg,r=ae(t,n.poles),o=ae(t,n.knots),a=n.weights?ae(t,n.weights):null;if(n.period){let[f,p]=n.range;(e>p||e<f)&&(e=f+((e-f)%n.period+n.period)%n.period)}let c=Ys(o,s,n.n,e),l=Zs(o,s,c,e,Fn(2,s+1)),u=[0,0,0],h=0;for(let f=0;f<=s;f+=1){let p=c-s+f,m=a?a[p]:1,g=l[f]*m;for(let x=0;x<i;x+=1)u[x]+=g*r[p*i+x];h+=g}for(let f=0;f<i;f+=1)u[f]/=h;return u.slice(0,i)}d(Do,"evaluateBSplineCurve");var Ef={line(n,t){let{origin:e,dir:i}=n;return[e[0]+t*i[0],e[1]+t*i[1],e[2]+t*i[2]]},circle(n,t){let e=rt(t)*n.radius,i=ht(t)*n.radius;return Re(n,e,i,0)},ellipse(n,t){let e=rt(t)*n.majorRadius,i=ht(t)*n.minorRadius;return Re(n,e,i,0)}};function Jt(n,t,e){let i=Ef[n.kind];if(i)return i(n,e);if(n.kind==="bspline")return Do(n,t,e,3);throw new Error(`unknown curve kind ${n.kind}`)}d(Jt,"evaluateCurve3");function On(n,t,e){return Do(n,t,e,2)}d(On,"evaluatePCurve");function Re(n,t,e,i){let{origin:s,xdir:r,ydir:o,zdir:a}=n;return[s[0]+t*r[0]+e*o[0]+i*a[0],s[1]+t*r[1]+e*o[1]+i*a[1],s[2]+t*r[2]+e*o[2]+i*a[2]]}d(Re,"frameMix");function Cf(n,t,e,i){let{degU:s,degV:r,nu:o,nv:a}=n,c=ae(t,n.poles),l=ae(t,n.knotsU),u=ae(t,n.knotsV),h=n.weights?ae(t,n.weights):null,f=Ys(l,s,o,e),p=Ys(u,r,a,i),m=Zs(l,s,f,e,Fn(2,s+1)),g=Zs(u,r,p,i,Fn(3,r+1)),x=0,_=0,v=0,y=0;for(let b=0;b<=s;b+=1){let T=f-s+b;for(let S=0;S<=r;S+=1){let M=p-r+S,A=T*a+M,I=h?h[A]:1,C=m[b]*g[S]*I;x+=C*c[A*3],_+=C*c[A*3+1],v+=C*c[A*3+2],y+=C}}return[x/y,_/y,v/y]}d(Cf,"evaluateNurbsSurface");var Rf={plane(n,t,e){return Re(n,t,e,0)},cylinder(n,t,e){let i=n.radius;return Re(n,i*rt(t),i*ht(t),e)},cone(n,t,e){let i=n.radius+e*ht(n.semiAngle);return Math.abs(i)<(Math.abs(n.radius)+Math.abs(e))*Number.EPSILON*4&&(i=0),Re(n,i*rt(t),i*ht(t),e*rt(n.semiAngle))},sphere(n,t,e){let i=n.radius,s=Math.abs(rt(e))<Number.EPSILON*4?0:rt(e);return Re(n,i*s*rt(t),i*s*ht(t),i*ht(e))},torus(n,t,e){let i=n.majorRadius+n.minorRadius*rt(e);return Re(n,i*rt(t),i*ht(t),n.minorRadius*ht(e))}};function lt(n,t,e,i){let s=Rf[n.kind];if(s)return s(n,e,i);if(n.kind==="nurbs")return Cf(n,t,e,i);if(n.kind==="revolution"){let r=Jt(n.profile,t,i);return If(r,n.origin,n.dir,e)}if(n.kind==="extrusion"){let r=Jt(n.profile,t,e);return[r[0]+i*n.dir[0],r[1]+i*n.dir[1],r[2]+i*n.dir[2]]}throw new Error(`unknown surface kind ${n.kind}`)}d(lt,"evaluateSurface");function If(n,t,e,i){let s=n[0]-t[0],r=n[1]-t[1],o=n[2]-t[2],[a,c,l]=e,u=rt(i),h=ht(i),f=a*s+c*r+l*o,p=c*o-l*r,m=l*s-a*o,g=a*r-c*s;return[t[0]+s*u+p*h+a*f*(1-u),t[1]+r*u+m*h+c*f*(1-u),t[2]+o*u+g*h+l*f*(1-u)]}d(If,"rotateAroundAxis");function Bn(n,t,e,i,s,r){if(["plane","cylinder","cone","sphere","torus"].includes(n.kind)){let{xdir:M,ydir:A,zdir:I}=n,C=[M[1]*A[2]-M[2]*A[1],M[2]*A[0]-M[0]*A[2],M[0]*A[1]-M[1]*A[0]],N=C[0]*I[0]+C[1]*I[1]+C[2]*I[2]<0?-1:1,R=0,w=0,P=1;if(n.kind!=="plane"){let E=n.kind==="cone"?-n.semiAngle:n.kind==="cylinder"?0:i;R=rt(e)*rt(E),w=ht(e)*rt(E),P=ht(E)}let L=(r?-1:1)*N;return[0,1,2].map(E=>L*(R*M[E]+w*A[E]+P*I[E]))}let[o,a,c,l]=s,u=Math.max((a-o)*1e-4,1e-7),h=Math.max((l-c)*1e-4,1e-7),f=lt(n,t,e-u,i),p=lt(n,t,e+u,i),m=lt(n,t,e,i-h),g=lt(n,t,e,i+h),x=[p[0]-f[0],p[1]-f[1],p[2]-f[2]],_=[g[0]-m[0],g[1]-m[1],g[2]-m[2]],v=x[1]*_[2]-x[2]*_[1],y=x[2]*_[0]-x[0]*_[2],b=x[0]*_[1]-x[1]*_[0],T=Math.sqrt(v*v+y*y+b*b)||1,S=r?-1:1;return v=v/T*S,y=y/T*S,b=b/T*S,[v,y,b]}d(Bn,"evaluateSurfaceNormal");Un();var _e=4,Ct={chordTolerance:.0015,loopTolerance:5e-4,angleTolerance:.35,maxRefineDepth:7,minLoopSegments:8};function Q(n,t){return[n[0]-t[0],n[1]-t[1],n[2]-t[2]]}d(Q,"sub");function et(n){return Math.sqrt(n[0]*n[0]+n[1]*n[1]+n[2]*n[2])}d(et,"length3");function zn(n,t){return n.kind==="sphere"?Math.abs(rt(t))<1e-12:n.kind==="cone"?Math.abs(n.radius+t*ht(n.semiAngle))<(Math.abs(n.radius)+Math.abs(t))*1e-12:!1}d(zn,"singularU");function Uo(n,t,e,i,s){let r=[],o=[],a=[],c=[];for(let l=0;n.surface.kind!=="plane"&&l<2;l+=1){let u=n.uv[l*2],h=n.uv[l*2+1];c.push({d:l,lo:u,hi:h,epsilon:Math.max(Math.abs(u),Math.abs(h),h-u,1e-12)*2**-23})}for(let l of t){let u=!l.reversed,h=l.edgeOrd?s?.get(l.edgeOrd):null,f=null,p=null;if(h&&h.points.length>=2){let m=Nf(n,l,e,i,h);m&&(f=m.uvs,p=m.fractions)}f||(f=Pf(n,l,e,i));for(let m of f)for(let{d:g,lo:x,hi:_,epsilon:v}of c)Math.abs(m[g]-x)<=v?m[g]=x:Math.abs(m[g]-_)<=v&&(m[g]=_);u||(f.reverse(),p?.reverse());for(let m=0;m<f.length-1;m+=1)r.push(f[m]),o.push(l.edgeOrd||0),a.push(p?{ord:l.edgeOrd,f0:p[m],f1:p[m+1]}:null)}return r.segmentOrds=o,r.segmentMeta=a,r}d(Uo,"sampleLoopPolygon");function ko(n,t,e,i){let[s,r]=t.range,o=n.surface,a=d(g=>On(t,e,g),"uvOf"),c=d(g=>lt(o,e,g[0],g[1]),"xyzOf"),l=c(a(s)),u=c(a(r)),h=et(Q(l,u))<=i,f=Math.max(h?Ct.minLoopSegments:2,t.n??2),p=[];for(let g=0;g<=f;g+=1)p.push(s+(r-s)*g/f);let m=0;for(;m<Ct.maxRefineDepth;){let g=!1,x=[p[0]];for(let _=0;_+1<p.length;_+=1){let v=p[_],y=p[_+1],b=(v+y)/2,T=c(a(v)),S=c(a(y)),M=c(a(b)),A=[(T[0]+S[0])/2,(T[1]+S[1])/2,(T[2]+S[2])/2];et(Q(M,A))>i&&(x.push(b),g=!0),x.push(y)}if(p.length=0,p.push(...x),!g)break;m+=1}return{params:p,uvs:p.map(a)}}d(ko,"samplePCurveParams");function Pf(n,t,e,i){return ko(n,t,e,i).uvs}d(Pf,"samplePCurveAdaptive");function Nf(n,t,e,i,s){let r=ko(n,t,e,i);if(r.uvs.length<2)return null;let o=n.surface,a=r.uvs.map(T=>lt(o,e,T[0],T[1])),c=[0];for(let T=1;T<a.length;T+=1)c.push(c[T-1]+et(Q(a[T],a[T-1])));let l=c[c.length-1];if(!(l>0))return null;for(let T=0;T<c.length;T+=1)c[T]/=l;let u=s.points[0],h=s.points[s.points.length-1],f=et(Q(u,a[0]))+et(Q(h,a[a.length-1])),m=et(Q(u,a[a.length-1]))+et(Q(h,a[0]))<f,g=[],x=[],_=[],v=s.boundarySubset||s.points.map((T,S)=>S),y=v.length,b=0;for(let T=0;T<y;T+=1){let S=v[m?y-1-T:T],M=s.fractions[S],A=m?1-M:M;for(;b+1<c.length-1&&c[b+1]<A;)b+=1;let I;if(T===0)I=r.params[0];else if(T===y-1)I=r.params[r.params.length-1];else{let w=c[b],P=c[b+1],L=P>w?(A-w)/(P-w):0;I=r.params[b]+L*(r.params[b+1]-r.params[b])}let C=On(t,e,I),N=s.points[S],R=lt(o,e,C[0],C[1]);if(et(Q(R,N))>i*2)return null;g.push(C),x.push(M),_.push(I)}if(o.kind!=="plane"){let T=g.map(S=>lt(o,e,S[0],S[1]));for(let S=0;S<4;S+=1){let M=!1,A=[g[0]],I=[x[0]],C=[_[0]],N=[T[0]];for(let R=0;R+1<g.length;R+=1){let w=T[R],P=T[R+1],L=(_[R]+_[R+1])/2,E=On(t,e,L),D=lt(o,e,E[0],E[1]),F=[(w[0]+P[0])/2,(w[1]+P[1])/2,(w[2]+P[2])/2];et(Q(D,F))>i&&(A.push(E),I.push((x[R]+x[R+1])/2),C.push(L),N.push(D),M=!0),A.push(g[R+1]),I.push(x[R+1]),C.push(_[R+1]),N.push(T[R+1])}if(g.length=0,x.length=0,_.length=0,T.length=0,g.push(...A),x.push(...I),_.push(...C),T.push(...N),!M)break}}return{uvs:g,fractions:x}}d(Nf,"mapSharedEdgeToPCurve");function Ii(n,t,e){let i=n.fractions,s=i.length-1;if(t<=i[0])return n.points[0];if(t>=i[s])return n.points[s];let r=0,o=s;for(;r+1<o;){let f=r+o>>1;i[f]<=t?r=f:o=f}let a=i[r],c=i[r+1];if(t===a)return n.points[r];if(t===c)return n.points[r+1];let l=c>a?(t-a)/(c-a):0;if(n.curve&&e){let f=n.params[r]+l*(n.params[r+1]-n.params[r]);return Jt(n.curve,e,f)}let u=n.points[r],h=n.points[r+1];return[u[0]+l*(h[0]-u[0]),u[1]+l*(h[1]-u[1]),u[2]+l*(h[2]-u[2])]}d(Ii,"edgePointAt");function Lf(n,t,e){let[i,s]=n.range,r=Jt(n,t,i),o=Jt(n,t,s),a=!1;if(n.kind!=="line"){let g=et(Q(r,o));for(let x of[.25,.5,.75])g=Math.max(g,et(Q(r,Jt(n,t,i+x*(s-i)))));a=et(Q(r,o))<=g*2**-21}let c=n.kind==="line"?1:Math.max(a?8:4,n.n??2),l=[];for(let g=0;g<=c;g+=1)l.push(i+(s-i)*g/c);let u=0;for(;u<Ct.maxRefineDepth;){let g=!1,x=[l[0]];for(let _=0;_+1<l.length;_+=1){let v=l[_],y=l[_+1],b=(v+y)/2,T=Jt(n,t,v),S=Jt(n,t,y),M=Jt(n,t,b),A=[(T[0]+S[0])/2,(T[1]+S[1])/2,(T[2]+S[2])/2];et(Q(M,A))>e&&(x.push(b),g=!0),x.push(y)}if(l.length=0,l.push(...x),!g)break;u+=1}let h=l.map(g=>Jt(n,t,g));a&&h.length>1&&(h[h.length-1]=h[0]);let f=[0];for(let g=1;g<h.length;g+=1)f.push(f[g-1]+et(Q(h[g],h[g-1])));let p=f[f.length-1];if(p>0){for(let g=0;g<f.length;g+=1)f[g]/=p;f[f.length-1]=1}let m=[0];{let g=e*(Ct.loopTolerance/Ct.chordTolerance),x=0;for(let _=1;_<h.length;_+=1){if(_===h.length-1){m.push(_);break}let v=h[x],y=h[_+1],b=0;for(let T=x+1;T<=_;T+=1){let S=Q(h[T],v),M=Q(y,v),A=M[0]*M[0]+M[1]*M[1]+M[2]*M[2],I=A>0?(S[0]*M[0]+S[1]*M[1]+S[2]*M[2])/A:0,C=Math.max(0,Math.min(1,I)),N=[v[0]+C*M[0],v[1]+C*M[1],v[2]+C*M[2]];if(b=Math.max(b,et(Q(h[T],N))),b>g)break}b>g&&(m.push(_),x=_)}}return{curve:n,params:l,points:h,fractions:f,closed:a,length:p,boundarySubset:m}}d(Lf,"sampleSharedEdge");function Df(n){let t=0;for(let e=0;e<n.length;e+=1){let[i,s]=n[e],[r,o]=n[(e+1)%n.length];t+=i*o-r*s}return t/2}d(Df,"polygonArea");function Fo(n,t,e,i,s){let[r,o,a,c]=e,l=s===0?o-r:c-a;if(l<=0)return 1;let u=4,h=0;for(let p=0;p<=u;p+=1){let m=s===0?a+(c-a)*p/u:r+(o-r)*p/u;for(let g=0;g<u;g+=1){let x=(s===0?r:a)+l*g/u,_=x+l/u,v=(x+_)/2,y=d(A=>s===0?lt(n.surface,t,A,m):lt(n.surface,t,m,A),"at"),b=y(x),T=y(_),S=y(v),M=[(b[0]+T[0])/2,(b[1]+T[1])/2,(b[2]+T[2])/2];h=Math.max(h,et(Q(S,M)))}}if(h<=i)return 1;let f=Math.sqrt(h/i);return Math.min(256,Math.max(1,Math.ceil(u*f)))}d(Fo,"gridStepsForDirection");function Uf(n,t,e){let i=!1;for(let s of n)for(let r=0;r<s.length;r+=1){let[o,a]=s[r],[c,l]=s[(r+1)%s.length];a>e!=l>e&&t<(c-o)*(e-a)/(l-a)+o&&(i=!i)}return i}d(Uf,"pointInLoopsEvenOdd");function Ff(n,t,e,i,s){let r=n;for(let[o,a,c]of[[0,t,!1],[0,e,!0],[1,i,!1],[1,s,!0]]){let l=r;r=[];for(let u=0;u<l.length;u+=1){let h=l[u],f=l[(u+l.length-1)%l.length],p=c?h[o]<=a:h[o]>=a,m=c?f[o]<=a:f[o]>=a;if(p!==m){let g=(a-f[o])/(h[o]-f[o]);r.push([f[0]+g*(h[0]-f[0]),f[1]+g*(h[1]-f[1])])}p&&r.push(h)}if(r.length<3)return[]}return r}d(Ff,"clipPolygonToCell");function Vo(n,t,e,i,s=1/0){let r=1/0,o=-1/0,a=1/0,c=-1/0;for(let N of e)for(let[R,w]of N)R<r&&(r=R),R>o&&(o=R),w<a&&(a=w),w>c&&(c=w);if(!(o>r)||!(c>a))return null;let l=[r,o,a,c],u=Math.min(256,Math.max(Fo(n,t,l,i,0),Math.ceil((o-r)/s))),h=Math.min(256,Math.max(Fo(n,t,l,i,1),n.surface.kind==="sphere"?Math.ceil((c-a)/s):1)),f=(o-r)/u,p=(c-a)/h,m=d((N,R)=>[Math.min(u-1,Math.max(0,Math.floor((N-r)/f))),Math.min(h-1,Math.max(0,Math.floor((R-a)/p)))],"cellOf"),g=new Set,x=[],_=new Map;for(let N of e){let R=N.segmentOrds||[],w=N.segmentMeta||[];for(let P=0;P<N.length;P+=1){let[L,E]=N[P],[D,F]=N[(P+1)%N.length],O=x.length;x.push([L,E,D,F,R[P]||0,w[P]||null]);let[U,B]=m(Math.min(L,D),Math.min(E,F)),[z,G]=m(Math.max(L,D),Math.max(E,F));for(let X=U;X<=z;X+=1)for(let V=B;V<=G;V+=1){let W=X*h+V;g.add(W);let q=_.get(W);q||_.set(W,q=[]),q.push(O)}}}let v=[],y=new Map,b=Math.max(Math.abs(r),Math.abs(o),o-r,1e-12)*2**-23,T=Math.max(Math.abs(a),Math.abs(c),c-a,1e-12)*2**-23,S=d((N,R)=>{let w=Math.round((N-r)/f),P=Math.round((R-a)/p),L=w===u?o:r+w*f,E=P===h?c:a+P*p;n.surface.kind!=="plane"&&(Math.abs(N-L)<=b&&(N=L),Math.abs(R-E)<=T&&(R=E));let D=`${N}:${R}`,F=y.get(D);return F===void 0&&(F=v.length,v.push([N,R]),y.set(D,F)),F},"vertexId"),M=[],A=Math.abs((o-r)*(c-a))*1e-12||1e-30,I=[],C=[];for(let N=0;N<=u;N+=1)I.push(N===u?o:r+N*f);for(let N=0;N<=h;N+=1)C.push(N===h?c:a+N*p);for(let N=0;N<u;N+=1)for(let R=0;R<h;R+=1){let w=I[N],P=I[N+1],L=C[R],E=C[R+1];if(!g.has(N*h+R)){if(!Uf(e,(w+P)/2,(L+E)/2))continue;let V=S(w,L),W=S(P,L),q=S(P,E),$=S(w,E);M.push(V,W,q,V,q,$);continue}let D=e.map(V=>Ff(V,w,P,L,E)).filter(V=>V.length>=3);if(!D.length)continue;let F=0,O=0;for(let V=0;V<D.length;V+=1){let W=Math.abs(Df(D[V]));W>O&&(O=W,F=V)}if(O<=A)continue;let U=D[F].map(([V,W])=>new xt(V,W)),B=D.filter((V,W)=>W!==F).map(V=>V.map(([W,q])=>new xt(W,q))),z;try{z=In.triangulateShape(U,B)}catch{continue}let G=[...U,...B.flat()],X=G.map(({x:V,y:W})=>S(V,W));for(let[V,W,q]of z){let $=G[V],tt=G[W],J=G[q],j=(tt.x-$.x)*(J.y-$.y)-(J.x-$.x)*(tt.y-$.y);Math.abs(j)/2>A&&X[V]!==X[W]&&X[W]!==X[q]&&X[q]!==X[V]&&M.push(X[V],X[W],X[q])}}return{uvVerts:v,triangles:M,vertexIds:y,segmentIndex:{segments:x,segmentsByCell:_,cellOf:m,stepsV:h}}}d(Vo,"gridTriangulate");function Of(n,t,e,i,s,r){let o=s-e,a=r-i,c=o*o+a*a,l=c>0?((n-e)*o+(t-i)*a)/c:0;l=Math.max(0,Math.min(1,l));let u=e+l*o,h=i+l*a;return{distSq:(n-u)*(n-u)+(t-h)*(t-h),t:l}}d(Of,"projectToSegment");function Oo(n,t,e,i,s,r){let o=s-e,a=r-i,c=o*o+a*a,l=c>0?((n-e)*o+(t-i)*a)/c:0;l=Math.max(0,Math.min(1,l));let u=e+l*o,h=i+l*a;return(n-u)*(n-u)+(t-h)*(t-h)}d(Oo,"pointToSegmentDistanceSq");function Bf(n,t,e,i){let s=new Map,r=d((m,g)=>m<g?m*4294967296+g:g*4294967296+m,"keyOf");for(let m=0;m<n.length;m+=3){let[g,x,_]=[n[m],n[m+1],n[m+2]];for(let[v,y]of[[g,x],[x,_],[_,g]]){let b=r(v,y);s.set(b,(s.get(b)||0)+1)}}let{segments:o,segmentsByCell:a,cellOf:c,stepsV:l}=e,u=i*i,h=new Map,f=d((m,g)=>{let x=r(m,g);if(s.get(x)!==1)return 0;let _=h.get(x);if(_!==void 0)return _;_=0;let[v,y]=t[m],[b,T]=t[g],[S,M]=c((v+b)/2,(y+T)/2),A=a.get(S*l+M)||[];for(let I of A){let[C,N,R,w,P]=o[I];if(P&&Oo(v,y,C,N,R,w)<u&&Oo(b,T,C,N,R,w)<u){_=P;break}}return h.set(x,_),_},"ordOfMeshEdge"),p=new Uint32Array(n.length);for(let m=0;m<n.length;m+=3){let[g,x,_]=[n[m],n[m+1],n[m+2]];p[m]=f(x,_),p[m+1]=f(_,g),p[m+2]=f(g,x)}return p}d(Bf,"attributeBoundaryEdges");function zf(n,t,e,i={},s=null){let{chordTolerance:r,loopTolerance:o,angleTolerance:a,maxRefineDepth:c}={...Ct,...i},l=o*e,u=n.loops.map(w=>Uo(n,w,t,l,s)).filter(w=>w.length>=3);if(!u.length)return null;let h=0;{let w=1/0,P=-1/0,L=1/0,E=-1/0;for(let F of u)for(let[O,U]of F)O<w&&(w=O),O>P&&(P=O),U<L&&(L=U),U>E&&(E=U);let D=[[w,L],[P,L],[w,E],[P,E],[(w+P)/2,(L+E)/2]].map(([F,O])=>lt(n.surface,t,F,O));for(let F=0;F<D.length;F+=1)for(let O=F+1;O<D.length;O+=1)h=Math.max(h,et(Q(D[F],D[O])))}let f=Math.max(Math.min(e,h*4),1e-9),p=r*f,m=o*f,g=m<l?n.loops.map(w=>Uo(n,w,t,m,s)).filter(w=>w.length>=3):u;if(!g.length)return null;let x=g.length===1&&(zn(n.surface,n.uv[2])||zn(n.surface,n.uv[3]))&&g[0].every(([w,P])=>w===n.uv[0]||w===n.uv[1]||P===n.uv[2]||P===n.uv[3]),_=Vo(n,t,g,x?p/3:p,x?a/Math.SQRT2:1/0);if(!_)return null;let{uvVerts:v,triangles:y,vertexIds:b,segmentIndex:T}=_,S=y;if(!S.length)return null;let M=v.map(([w,P])=>lt(n.surface,t,w,P));if(x){let w=new Map,P=new Map;for(let E=0;E<v.length;E+=1){if(!zn(n.surface,v[E][1]))continue;let D=v[E][1];w.has(D)?P.set(E,w.get(D)):w.set(D,E)}let L=[];for(let E=0;E<S.length;E+=3){let[D,F,O]=S.slice(E,E+3).map(U=>P.get(U)??U);et(Q(M[D],M[F]))<=e*1e-12||et(Q(M[F],M[O]))<=e*1e-12||et(Q(M[O],M[D]))<=e*1e-12||L.push(D,F,O)}S=L}let A=d(([w,P])=>Bn(n.surface,t,w,P,n.uv,!1),"vertexNormal"),I=v.map(A),C=rt(a),N=d((w,P)=>w<P?`${w}_${P}`:`${P}_${w}`,"edgeKey");for(let w=0;w<(x?0:c);w+=1){let P=new Set,L=new Map,E=d((U,B)=>{let z=N(U,B),G=L.get(z);if(G===void 0){let X=(v[U][0]+v[B][0])/2,V=(v[U][1]+v[B][1])/2,W=lt(n.surface,t,X,V),q=[(M[U][0]+M[B][0])/2,(M[U][1]+M[B][1])/2,(M[U][2]+M[B][2])/2];G=et(Q(W,q))>p||I[U][0]*I[B][0]+I[U][1]*I[B][1]+I[U][2]*I[B][2]<C,L.set(z,G)}return G},"edgeChordBad");for(let U=0;U<S.length;U+=3){let B=S[U],z=S[U+1],G=S[U+2],X=!1;for(let[Pt,pt]of[[B,z],[z,G],[G,B]])E(Pt,pt)&&(P.add(N(Pt,pt)),X=!0);if(X)continue;let V=(v[B][0]+v[z][0]+v[G][0])/3,W=(v[B][1]+v[z][1]+v[G][1])/3,q=lt(n.surface,t,V,W),$=[(M[B][0]+M[z][0]+M[G][0])/3,(M[B][1]+M[z][1]+M[G][1])/3,(M[B][2]+M[z][2]+M[G][2])/3],tt=Q(M[z],M[B]),J=Q(M[G],M[B]),j=[tt[1]*J[2]-tt[2]*J[1],tt[2]*J[0]-tt[0]*J[2],tt[0]*J[1]-tt[1]*J[0]],nt=et(j),Mt=I[B];if(nt>1e-30&&Math.abs((j[0]*Mt[0]+j[1]*Mt[1]+j[2]*Mt[2])/nt)<C||et(Q(q,$))>p){let Pt=[B,z],pt=-1;for(let[oe,wt]of[[B,z],[z,G],[G,B]]){let be=v[oe][0]-v[wt][0],Xt=v[oe][1]-v[wt][1],Nt=be*be+Xt*Xt;Nt>pt&&(pt=Nt,Pt=[oe,wt])}P.add(N(Pt[0],Pt[1]))}}if(!P.size)break;let D=new Map,F=d((U,B)=>{let z=N(U,B);if(!P.has(z))return-1;let G=D.get(z);if(G===void 0){let X=(v[U][0]+v[B][0])/2,V=(v[U][1]+v[B][1])/2;G=v.length,v.push([X,V]),M.push(lt(n.surface,t,X,V)),I.push(A([X,V])),D.set(z,G)}return G},"midpointOf"),O=[];for(let U=0;U<S.length;U+=3){let B=S[U],z=S[U+1],G=S[U+2],X=F(B,z),V=F(z,G),W=F(G,B),q=(X>=0)+(V>=0)+(W>=0);if(q===0){O.push(B,z,G);continue}if(q===3)O.push(B,X,W,X,z,V,W,V,G,X,V,W);else if(q===2){let[$,tt,J,j,nt]=X>=0&&V>=0?[B,z,G,X,V]:V>=0&&W>=0?[z,G,B,V,W]:[G,B,z,W,X];O.push($,j,nt,$,nt,J,j,tt,nt)}else{let[$,tt,J,j]=X>=0?[B,z,G,X]:V>=0?[z,G,B,V]:[G,B,z,W];O.push($,j,J,j,tt,J)}}S=O}let R=new Map;if(s){let w=0,P=0;for(let[U,B]of v)w=Math.max(w,Math.abs(U)),P=Math.max(P,Math.abs(B));let L=Math.max(w,P,1)*1e-7,{segments:E,segmentsByCell:D,cellOf:F,stepsV:O}=T;for(let U=0;U<v.length;U+=1){let[B,z]=v[U],[G,X]=F(B,z),V=D.get(G*O+X);if(!V)continue;let W=new Map;for(let tt of V){let[J,j,nt,Mt,Qt,Pt]=E[tt];if(!Pt)continue;let pt=Of(B,z,J,j,nt,Mt);if(pt.distSq>=L*L){let be=L*L*16,Xt=(B-J)*(B-J)+(z-j)*(z-j),Nt=(B-nt)*(B-nt)+(z-Mt)*(z-Mt);if(Xt<be)pt={distSq:Xt,t:0};else if(Nt<be)pt={distSq:Nt,t:1};else continue}let oe=W.get(Qt);if(oe&&oe.distSq<=pt.distSq)continue;let wt=pt.t<1e-9?0:pt.t>1-1e-9?1:pt.t;W.set(Qt,{distSq:pt.distSq,f:Pt.f0+wt*(Pt.f1-Pt.f0)})}if(!W.size)continue;let q=[],$=null;for(let[tt,{distSq:J,f:j}]of W){let nt=s.get(tt);if(!nt)continue;let Mt=nt.closed&&j>=1-1e-12?0:j;q.push({ord:tt,f:Mt}),(!$||J<$.distSq)&&($={distSq:J,ord:tt,f:Mt,shared:nt})}q.length&&(q.sort((tt,J)=>tt.ord===$.ord&&tt.f===$.f?-1:J.ord===$.ord&&J.f===$.f?1:0),R.set(U,q),M[U]=Ii($.shared,$.f,t))}}return{uvVerts:v,xyz:M,nrm:I,triangles:S,segmentIndex:T,boundary:R,loops:g,singularGrid:x}}d(zf,"tessellateFaceRaw");function kf(n,t,e,i={}){if(t.singularGrid)return;let{chordTolerance:s,angleTolerance:r,maxRefineDepth:o}={...Ct,...i},{uvVerts:a,xyz:c,nrm:l,boundary:u}=t,h=t.mintedVerts;if(!h?.size)return;let f=t.triangles,p=0;for(let y of c)p=Math.max(p,et(Q(y,c[0])));let m=s*Math.max(p,1e-9),g=d(([y,b])=>Bn(n.surface,e,y,b,n.uv,!1),"vertexNormal"),x=rt(r),_=d((y,b)=>y<b?`${y}_${b}`:`${b}_${y}`,"edgeKey"),v=Math.min(3,o);for(let y=0;y<v;y+=1){let b=new Set;for(let A=0;A<f.length;A+=3){let[I,C,N]=[f[A],f[A+1],f[A+2]];if(!(!h.has(I)&&!h.has(C)&&!h.has(N)))for(let[R,w]of[[I,C],[C,N],[N,I]]){if(u.has(R)&&u.has(w))continue;let P=(a[R][0]+a[w][0])/2,L=(a[R][1]+a[w][1])/2,E=lt(n.surface,e,P,L);if(!E||!Number.isFinite(E[0]))continue;let D=[(c[R][0]+c[w][0])/2,(c[R][1]+c[w][1])/2,(c[R][2]+c[w][2])/2];et(Q(E,D))>m&&b.add(_(R,w))}}if(!b.size)break;let T=new Map,S=d((A,I)=>{let C=_(A,I);if(!b.has(C))return-1;let N=T.get(C);if(N===void 0){let R=(a[A][0]+a[I][0])/2,w=(a[A][1]+a[I][1])/2;N=a.length,a.push([R,w]),c.push(lt(n.surface,e,R,w)),l.push(g([R,w])),T.set(C,N)}return N},"midpointOf"),M=[];for(let A=0;A<f.length;A+=3){let I=f[A],C=f[A+1],N=f[A+2],R=S(I,C),w=S(C,N),P=S(N,I),L=(R>=0)+(w>=0)+(P>=0);if(L===0)M.push(I,C,N);else if(L===3)M.push(I,R,P,R,C,w,P,w,N,R,w,P);else if(L===2){let[E,D,F,O,U]=R>=0&&w>=0?[I,C,N,R,w]:w>=0&&P>=0?[C,N,I,w,P]:[N,I,C,P,R];M.push(E,O,U,E,U,F,O,D,U)}else{let[E,D,F,O]=R>=0?[I,C,N,R]:w>=0?[C,N,I,w]:[N,I,C,P];M.push(E,O,F,O,D,F)}}f=M}t.triangles=f}d(kf,"refineInteriorPostConform");function Vf(n,t){let{uvVerts:e,xyz:i,nrm:s,triangles:r,segmentIndex:o}=t,a=new Float32Array(i.length*3),c=new Float32Array(i.length*3),l=n.reversed?-1:1;for(let m=0;m<i.length;m+=1)a.set(i[m],m*3),c[m*3]=s[m][0]*l,c[m*3+1]=s[m][1]*l,c[m*3+2]=s[m][2]*l;let u=n.reversed?Hf(r):Uint32Array.from(r),h=0,f=0;for(let[m,g]of e)h=Math.max(h,Math.abs(m)),f=Math.max(f,Math.abs(g));let p=Bf(u,e,o,Math.max(h,f,1)*1e-7);return{positions:a,normals:c,indices:u,sideOrds:p,uv:e}}d(Vf,"finalizeFaceMesh");function Bo(n,t){let[e,i,s,r]=n.uv,o=i-e,a=r-s,c=1-1e-9;return(l,u)=>o>0&&Math.abs(t[l][0]-t[u][0])>=o*c||a>0&&Math.abs(t[l][1]-t[u][1])>=a*c}d(Bo,"seamImagePredicate");function zo(n,t,e){let i=d((r,o)=>{if(r===o)return!0;let a=t[r],c=t[o];return a[0]===c[0]&&a[1]===c[1]&&a[2]===c[2]},"samePoint"),s=[];for(let r=0;r<n.length;r+=3){let o=e.get(n[r])??n[r],a=e.get(n[r+1])??n[r+1],c=e.get(n[r+2])??n[r+2];i(o,a)||i(a,c)||i(c,o)||s.push(o,a,c)}return s}d(zo,"compactCollapsedTriangles");function Gf(n,t,e,i=0){let s=d(u=>{let h=t.get(u),f=h?.length?i*.5/h.length:0;return Math.min(.25,Math.max(1e-9,f))},"fractionEps"),r=1e-9,o=d((u,h)=>{let f=t.get(u),p=s(u);return h<=p?0:h>=1-p?f?.closed?0:1:h},"canonicalFraction"),a=new Map,c=d((u,h)=>{let f=a.get(u);f||a.set(u,f=[]),f.push(o(u,h))},"addFraction");for(let{raw:u}of n)for(let h of u.boundary.values())for(let{ord:f,f:p}of h)c(f,p);for(let[u,h]of a){let f=s(u);h.sort((g,x)=>g-x);let p=[];for(let g of h)(!p.length||g-p[p.length-1]>f)&&p.push(g);t.get(u)?.closed&&p.length>1&&1-p[p.length-1]<=f&&p.pop(),a.set(u,p)}let l=d((u,h)=>{let f=a.get(u);if(!f)return h;let p=0,m=f.length-1;for(;p<m;){let x=p+m>>1;f[x]<h?p=x+1:m=x}let g=[f[p],f[p-1]??f[p]];return Math.abs(g[0]-h)<=Math.abs(g[1]-h)?g[0]:g[1]},"representativeOf");for(let{face:u,raw:h}of n){if(u.surface.kind==="plane"){let{origin:g,xdir:x,ydir:_}=u.surface,v=new Map,y=h.loops.map(T=>{let S=[];S.segmentOrds=[],S.segmentMeta=[];for(let M=0;M<T.length;M+=1){let A=T.segmentMeta[M],I=A&&t.get(A.ord);if(!I){S.push(T[M]),S.segmentOrds.push(T.segmentOrds[M]),S.segmentMeta.push(null);continue}let C=d(D=>l(A.ord,o(A.ord,D)),"canonical"),N=d((D,F)=>I.closed&&D===0&&F>.5?1:D,"unwrap"),R=N(C(A.f0),A.f0),w=N(C(A.f1),A.f1),P=s(A.ord),L=a.get(A.ord).filter(D=>D>Math.min(R,w)+P&&D<Math.max(R,w)-P);w<R&&L.reverse();let E=[R,...L,w];for(let D=0;D<E.length;D+=1){if(D+1<E.length&&Math.abs(E[D+1]-E[D])<=P)continue;let F=o(A.ord,E[D]),O=Ii(I,F,e),U=Q(O,g),B=[U[0]*x[0]+U[1]*x[1]+U[2]*x[2],U[0]*_[0]+U[1]*_[1]+U[2]*_[2]];D+1<E.length&&(S.push(B),S.segmentOrds.push(A.ord),S.segmentMeta.push({ord:A.ord,f0:E[D],f1:E[D+1]}));let z=`${B[0]}:${B[1]}`,G=v.get(z);G?G.labels.push({ord:A.ord,f:F}):v.set(z,{xyz:O,labels:[{ord:A.ord,f:F}]})}}return S}),b=Vo(u,e,y,1/0);b?.triangles.length&&(Object.assign(h,b,{boundary:new Map,loops:y}),h.xyz=b.uvVerts.map(([T,S],M)=>{let A=v.get(`${T}:${S}`);return A&&h.boundary.set(M,A.labels),A?.xyz??lt(u.surface,e,T,S)}),h.nrm=b.uvVerts.map(([T,S])=>Bn(u.surface,e,T,S,u.uv,!1)))}for(let[g,x]of h.boundary){for(let y of x)y.f=l(y.ord,o(y.ord,y.f));x.sort((y,b)=>y.ord-b.ord||y.f-b.f);let _=x[0],v=t.get(_.ord);v&&(h.xyz[g]=Ii(v,_.f,e))}let f=Bo(u,h.uvVerts),p=new Map,m=new Map;for(let g of h.boundary.keys()){let x=h.xyz[g],_=`${x[0]}:${x[1]}:${x[2]}`,v=p.get(_);if(v===void 0){p.set(_,[g]);continue}let y=v.find(b=>!f(b,g));y!==void 0?m.set(g,y):v.push(g)}h.triangles=zo(h.triangles,h.xyz,m);for(let g of m.keys())h.boundary.delete(g)}for(let{face:u,raw:h}of n){let{uvVerts:f,xyz:p,nrm:m,boundary:g}=h;if(!g.size)continue;let x=new Map,_=d((R,w)=>R<w?R*4294967296+w:w*4294967296+R,"pairKey");for(let R=0;R<h.triangles.length;R+=3){let[w,P,L]=[h.triangles[R],h.triangles[R+1],h.triangles[R+2]];for(let[E,D]of[[w,P],[P,L],[L,w]]){let F=_(E,D);x.set(F,(x.get(F)||0)+1)}}let v=d(([R,w])=>Bn(u.surface,e,R,w,u.uv,!1),"vertexNormal"),y=new Map,b=d((R,w,P,L,E)=>{let D=`${R}:${w.toFixed(12)}:${Math.min(P,L)}:${Math.max(P,L)}`,F=y.get(D);if(F!==void 0)return F;let O=[zn(u.surface,f[P][1])?f[L][0]:zn(u.surface,f[L][1])?f[P][0]:f[P][0]+E*(f[L][0]-f[P][0]),f[P][1]+E*(f[L][1]-f[P][1])];F=f.length,f.push(O);let U=Ii(t.get(R),w,e);return p.push(U),m.push(v(O)),g.set(F,[{ord:R,f:w}]),(h.mintedVerts??=new Set).add(F),y.set(D,F),F},"vertexAt"),T=d((R,w)=>{let P=g.get(R),L=g.get(w);if(!P||!L||x.get(_(R,w))!==1)return null;let E=null,D=null;for(let z of P){let G=L.find(X=>X.ord===z.ord);if(G){E=z,D=G;break}}if(!E||!D)return null;let F=a.get(E.ord);if(!F)return null;let O=t.get(E.ord),U=s(E.ord),B=[];if(O?.closed){let z=(D.f-E.f+1)%1,G=z<=.5,X=G?E.f:D.f,V=G?z:(E.f-D.f+1)%1;if(V<=U*2)return null;for(let W of F){let q=(W-X+1)%1;q>U&&q<V-U&&B.push({f:W,s:G?q/V:1-q/V})}}else{let z=Math.min(E.f,D.f),G=Math.max(E.f,D.f);if(G-z<=U*2)return null;for(let X of F)X>z+U&&X<G-U&&B.push({f:X,s:(X-E.f)/(D.f-E.f)})}return B.length?(B.sort((z,G)=>z.s-G.s),{ord:E.ord,between:B}):null},"insertsFor"),S=[],M=d((R,w,P,L)=>{if(L>24){S.push(R,w,P);return}for(let[E,D,F]of[[R,w,P],[w,P,R],[P,R,w]]){let O=T(E,D);if(O){let U=E;for(let{f:B,s:z}of O.between){let G=b(O.ord,B,E,D,z);M(U,G,F,L+1),U=G}M(U,D,F,L+1);return}}S.push(R,w,P)},"emit"),A=h.triangles;for(let R=0;R<A.length;R+=3)M(A[R],A[R+1],A[R+2],0);h.triangles=S;let I=Bo(u,f),C=new Map,N=new Map;for(let R of g.keys()){let w=p[R],P=`${w[0]}:${w[1]}:${w[2]}`,L=C.get(P);if(L===void 0){C.set(P,[R]);continue}let E=L.find(D=>!I(D,R));E!==void 0?N.set(R,E):L.push(R)}h.triangles=zo(h.triangles,p,N);for(let[R,w]of N){let P=g.get(R),L=g.get(w);if(P&&L)for(let E of P)L.some(D=>D.ord===E.ord&&D.f===E.f)||L.push(E);g.delete(R)}}}d(Gf,"conformBoundaries");function Hf(n){let t=new Uint32Array(n.length);for(let e=0;e<n.length;e+=3)t[e]=n[e],t[e+1]=n[e+2],t[e+2]=n[e+1];return t}d(Hf,"flipWinding");function Go(n,t,e={}){let i=[1/0,1/0,1/0],s=[-1/0,-1/0,-1/0],r=[],o=0,a=0;for(let S of n.faces)for(let M of S.loops)for(let A of M)for(let I of[A.range[0],(A.range[0]+A.range[1])/2,A.range[1]]){let[C,N]=On(A,t,I),R=lt(S.surface,t,C,N);for(let w=0;w<3;w+=1)R[w]<i[w]&&(i[w]=R[w]),R[w]>s[w]&&(s[w]=R[w])}let c=Math.max(et(Q(s,i)),1e-6),{chordTolerance:l}={...Ct,...e},u=new Map;for(let S of n.edges)S.curve&&u.set(S.ord,Lf(S.curve,t,l*c));{let S=c*476837158203125e-21,M=[],A=d(I=>{for(let C of M)if(et(Q(C,I))<=S)return C;return M.push(I),I},"canonicalCorner");for(let I of u.values()){if(I.closed){let C=A(I.points[0]);I.points[0]=C,I.points[I.points.length-1]=C;continue}I.points[0]=A(I.points[0]),I.points[I.points.length-1]=A(I.points[I.points.length-1])}}let h=[];for(let S of n.faces){let M=zf(S,t,c,e,e.noSharedBoundaries?null:u);M&&h.push({face:S,raw:M})}if(!e.noSharedBoundaries&&!e.noConformPass){Gf(h,u,t,l*c);for(let{face:S,raw:M}of h)kf(S,M,t,e)}let f=e.collectBoundaryDebug?[]:null;for(let{face:S,raw:M}of h){f&&f.push({faceOrd:S.ord,reversed:!!S.reversed,xyz:M.xyz,triangles:M.triangles.slice(),boundaryByVert:new Map(M.boundary)});let A=Vf(S,M);A&&(r.push({ord:S.ord,color:S.color??null,mesh:A}),o+=A.positions.length/3,a+=A.indices.length)}let p=new Float32Array(o*3),m=new Float32Array(o*3),g=new Float32Array(o),x=new Uint32Array(a),_=new Uint32Array(a),v=[],y=0,b=0;for(let{ord:S,color:M,mesh:A}of r){p.set(A.positions,y*3),m.set(A.normals,y*3),g.fill(S,y,y+A.positions.length/3);for(let I=0;I<A.indices.length;I+=1)x[b+I]=A.indices[I]+y;A.sideOrds&&_.set(A.sideOrds,b),v.push({ord:S,color:M,indexStart:b,indexCount:A.indices.length}),y+=A.positions.length/3,b+=A.indices.length}i=[1/0,1/0,1/0],s=[-1/0,-1/0,-1/0];for(let S=0;S<p.length;S+=3)for(let M=0;M<3;M+=1){let A=p[S+M];A<i[M]&&(i[M]=A),A>s[M]&&(s[M]=A)}let T=[];for(let S of n.edges){let M=u.get(S.ord);if(!M)continue;let A=new Float32Array(M.points.length*3);for(let I=0;I<M.points.length;I+=1)A.set(M.points[I],I*3);T.push({ord:S.ord,visibilityClass:S.class,polyline:A})}return{positions:p,normals:m,faceOrds:g,indices:x,sideOrds:_,faceRanges:v,edges:T,bounds:{min:i,max:s},scale:c,...f?{boundaryDebug:f,sharedEdges:u}:{}}}d(Go,"tessellateComponent");var qo=1397966164,ie=4,Ni=1,$o=16*1024,Yo=4*1024*1024,Wf=/^[0-9a-f]{64}$/,Ho=new Set(["chordTolerance","chordToleranceF64","angleTolerance","angleToleranceF64"]),Zo=new Set(["none","feature","tangent","seam","degenerate","boundary","nonManifold","unknown"]);function Kt(n,t){let e=typeof n=="string"?n:"";if(!Wf.test(e))throw new TypeError(`${t} must be 64 lowercase hex characters`);return e}d(Kt,"requireDigest");function Wo(n){if(typeof n!="number"||!Number.isFinite(n)||n<=0)throw new TypeError("tessellation tolerances must be positive finite binary64 values");let t=new Uint8Array(8);return new DataView(t.buffer).setFloat64(0,n,!1),[...t].map(e=>e.toString(16).padStart(2,"0")).join("")}d(Wo,"float64Hex");var Jo=Object.freeze(["chordTolerance","angleTolerance"]),Xf=Object.freeze(Object.keys(Ct).filter(n=>!Jo.includes(n)));function Li(n={}){let t=Xf.filter(r=>Object.hasOwn(n,r)&&n[r]!==Ct[r]);if(t.length)throw new TypeError(`tessellation options are not part of the cache key: ${t.join(", ")}. Keyed options: ${Jo.join(", ")}`);let e={...Ct,...n},i=e.chordTolerance,s=e.angleTolerance;return Object.freeze({chordTolerance:i,chordToleranceF64:Wo(i),angleTolerance:s,angleToleranceF64:Wo(s)})}d(Li,"tessellationQuality");function Ie(n,t={}){let e=Kt(n,"surfaceInput"),i=Li(t);return`${e}-t${_e}-p${ie}-l${i.chordToleranceF64}-a${i.angleToleranceF64}`}d(Ie,"tessellationCacheKey");function Ko(n,t,e={}){return`${Ie(n,e)}-s${Kt(t,"surfaceObject")}`}d(Ko,"resolvedTessellationIdentity");function qf(n){return n+3&-4}d(qf,"align4");function Js(n){return n!==null&&typeof n=="object"&&!Array.isArray(n)}d(Js,"isObject");function Pi(n,t){return Array.isArray(n)&&n.length===t&&n.every(e=>typeof e=="number"&&Number.isFinite(e))}d(Pi,"finiteTuple");function Ks(n){return Number.isSafeInteger(n)&&n>0}d(Ks,"validOrdinal");function $f(n){if(!Array.isArray(n))return null;let t=new Map;for(let e of n){if(!Array.isArray(e)||e.length!==2||!Ks(e[0])||!Zo.has(e[1])||t.has(e[0]))return null;t.set(e[0],e[1])}return t}d($f,"edgeClassMap");function jo(n){if(!Js(n?.bounds)||!Pi(n.bounds.min,3)||!Pi(n.bounds.max,3)||n.bounds.min.some((r,o)=>r>n.bounds.max[o])||typeof n.scale!="number"||!Number.isFinite(n.scale)||n.scale<=0||n.partColor!=null&&!Pi(n.partColor,4)||!Array.isArray(n.faceRanges)||!Array.isArray(n.edges))return!1;let t=new Set,e=0;for(let r of n.faceRanges)if(!Js(r)||!Ks(r.ord)||t.has(r.ord)||!en(r.indexStart)||!en(r.indexCount)||r.indexStart%3!==0||r.indexCount%3!==0||r.indexStart!==e||r.color!=null&&!Pi(r.color,4)||(t.add(r.ord),e+=r.indexCount,!Number.isSafeInteger(e)))return!1;if(e!==n.indexCount)return!1;let i=$f(n.edgeClasses);if(!i)return!1;let s=new Set;for(let r of n.edges){if(!Js(r)||!Ks(r.ord)||s.has(r.ord)||!en(r.count)||r.count%3!==0||r.visibilityClass!=null&&!Zo.has(r.visibilityClass)||!i.has(r.ord)||r.visibilityClass!=null&&i.get(r.ord)!==r.visibilityClass)return!1;s.add(r.ord)}return!0}d(jo,"validRenderingMetadata");function Qo(n){return(Array.isArray(n?.edges)?n.edges:[]).map(e=>[e.ord,String(e.class??"none")])}d(Qo,"edgeClassesFromSurfIndex");function ta(n,{partColor:t=null,edgeClasses:e=null,surfaceInput:i,surfaceObject:s,tessellation:r={}}={}){let o=Array.isArray(n.edges)?n.edges:[];if(!Array.isArray(n.faceRanges)||!Array.isArray(e))throw new TypeError("TESS v4 requires complete faceRanges and edgeClasses metadata");let a=Li(r),c=Ie(i,r),l=Kt(s,"surfaceObject"),u={tessellationInput:c,surfaceInput:Kt(i,"surfaceInput"),surfaceDigest:l,quality:a,tessellatorVersion:_e,payloadVersion:ie,partColor:t??null,edgeClasses:e,faceRanges:n.faceRanges,bounds:{min:[...n.bounds.min],max:[...n.bounds.max]},scale:n.scale,positionCount:n.positions.length,normalCount:n.normals.length,faceOrdCount:n.faceOrds.length,indexCount:n.indices.length,sideOrdCount:n.sideOrds.length,edges:o.map(y=>({ord:y.ord,visibilityClass:y.visibilityClass??null,count:y.polyline.length}))};if(!jo(u))throw new TypeError("TESS v4 requires valid complete rendering metadata");let h=JSON.stringify(u),f=new TextEncoder().encode(h),p=qf(f.length),m=n.positions.length+n.normals.length+n.faceOrds.length+n.indices.length+n.sideOrds.length+o.reduce((y,b)=>y+b.polyline.length,0),g=new Uint8Array(12+p+m*4),x=new DataView(g.buffer);x.setUint32(0,qo,!0),x.setUint32(4,ie,!0),x.setUint32(8,p,!0),g.set(f,12),g.fill(32,12+f.length,12+p);let _=12+p,v=d((y,b)=>{new b(g.buffer,_,y.length).set(y),_+=y.length*4},"append");v(n.positions,Float32Array),v(n.normals,Float32Array),v(n.faceOrds,Float32Array),v(n.indices,Uint32Array),v(n.sideOrds,Uint32Array);for(let y of o)v(y.polyline,Float32Array);return g}d(ta,"encodeComponentTessellation");function en(n){return Number.isSafeInteger(n)&&n>=0}d(en,"validCount");function ea({headerBytes:n,arrayBytes:t,faceRangeCount:e,edgeCount:i,edgeClassCount:s,edgeSegmentCount:r}){if(![n,t,e,i,s,r].every(en)||n<=0||n>Yo||n%4!==0||t%4!==0)throw new TypeError("invalid tessellation size facts");let a=t+8*r+8*n+256*(e+i+s);if(!Number.isSafeInteger(a))throw new TypeError("tessellation decoded size exceeds the safe integer range");return a}d(ea,"tessellationDecodedBytes");function Yf(n,t={}){try{if(n?.tessellatorVersion!==_e||n?.payloadVersion!==ie)return null;let e=Kt(n.surfaceInput,"surfaceInput"),i=Kt(n.surfaceDigest,"surfaceDigest"),s=n.quality;if(!s||typeof s!="object"||Array.isArray(s)||Object.keys(s).length!==Ho.size||Object.keys(s).some(l=>!Ho.has(l)))return null;let r=Li({chordTolerance:s.chordTolerance,angleTolerance:s.angleTolerance});if(s.chordToleranceF64!==r.chordToleranceF64||s.angleToleranceF64!==r.angleToleranceF64)return null;let o=Ie(e,r);if(n.tessellationInput!==o)return null;let a=Ko(e,i,r);if(t.surfaceInput!==void 0&&Kt(t.surfaceInput,"expected surfaceInput")!==e)return null;let c=t.surfaceObject??t.surfaceDigest;return c!==void 0&&Kt(c,"expected surfaceObject")!==i||t.tessellationInput!==void 0&&String(t.tessellationInput)!==o||t.renderIdentity!==void 0&&String(t.renderIdentity)!==a||t.tessellation!==void 0&&Ie(e,t.tessellation)!==o?null:Object.freeze({surfaceInput:e,surfaceObject:i,tessellationInput:o,renderIdentity:a,quality:r,tessellatorVersion:_e,payloadVersion:ie})}catch{return null}}d(Yf,"decodedIdentity");function na(n,t={}){if(!(n instanceof Uint8Array)||n.length<12)return null;let e=new DataView(n.buffer,n.byteOffset,n.byteLength);if(e.getUint32(0,!0)!==qo||e.getUint32(4,!0)!==ie)return null;let i=e.getUint32(8,!0);if(i===0||i>Yo||i%4!==0||12+i>n.length)return null;let s=JSON.parse(new TextDecoder().decode(n.subarray(12,12+i))),r=Yf(s,t);if(!r||!Array.isArray(s.edges)||!Array.isArray(s.faceRanges)||!Array.isArray(s.edgeClasses))return null;let o=[s.positionCount,s.normalCount,s.faceOrdCount,s.indexCount,s.sideOrdCount],a=s.edges.map(p=>p?.count),c=[...o,...a];if(!c.every(en)||s.positionCount%3!==0||s.normalCount!==s.positionCount||s.faceOrdCount*3!==s.positionCount||s.indexCount%3!==0||s.sideOrdCount!==s.indexCount||a.some(p=>p%3!==0)||!jo(s))return null;let l=c.reduce((p,m)=>p+m,0);if(!Number.isSafeInteger(l)||l>Number.MAX_SAFE_INTEGER/4)return null;let u=l*4;if(n.length!==12+i+u)return null;let h=Object.freeze({headerBytes:i,arrayBytes:u,faceRangeCount:s.faceRanges.length,edgeCount:s.edges.length,edgeClassCount:s.edgeClasses.length,edgeSegmentCount:a.reduce((p,m)=>p+Math.max(0,m/3-1),0)}),f=ea(h);return{header:s,identity:r,sizes:h,decodedBytes:f}}d(na,"decodeEnvelope");function js(n,t={}){try{let e=na(n,t);if(!e)return null;let i=Object.freeze({byteLength:n.byteLength,decodedBytes:e.decodedBytes,surfaceInput:e.identity.surfaceInput,surfaceObject:e.identity.surfaceObject,tessellationInput:e.identity.tessellationInput,renderIdentity:e.identity.renderIdentity,quality:e.identity.quality,tessellatorVersion:_e,payloadVersion:ie,...e.sizes});for(let s of["byteLength","decodedBytes","surfaceInput","surfaceObject","tessellationInput","renderIdentity","tessellatorVersion","payloadVersion","headerBytes","arrayBytes","faceRangeCount","edgeCount","edgeClassCount","edgeSegmentCount"])if(t[s]!==void 0&&t[s]!==i[s])return null;return i}catch{return null}}d(js,"tessellationPayloadFacts");var Xo=new Set(["schemaVersion","object","byteLength","decodedBytes","surfaceInput","surfaceObject","tessellationInput","renderIdentity","quality","tessellatorVersion","payloadVersion","headerBytes","arrayBytes","faceRangeCount","edgeCount","edgeClassCount","edgeSegmentCount"]);function Qs(n,t={}){try{if(!n||typeof n!="object"||Array.isArray(n)||Object.keys(n).length!==Xo.size||Object.keys(n).some(l=>!Xo.has(l))||n.schemaVersion!==Ni||n.tessellatorVersion!==_e||n.payloadVersion!==ie)return null;let e=Kt(n.surfaceInput,"surfaceInput"),i=Kt(n.surfaceObject,"surfaceObject"),s=Kt(n.object,"object"),r=Li({chordTolerance:n.quality?.chordTolerance,angleTolerance:n.quality?.angleTolerance});if(n.quality?.chordToleranceF64!==r.chordToleranceF64||n.quality?.angleToleranceF64!==r.angleToleranceF64)return null;let o=Ie(e,r),a=Ko(e,i,r);if(n.tessellationInput!==o||n.renderIdentity!==a)return null;let c={headerBytes:n.headerBytes,arrayBytes:n.arrayBytes,faceRangeCount:n.faceRangeCount,edgeCount:n.edgeCount,edgeClassCount:n.edgeClassCount,edgeSegmentCount:n.edgeSegmentCount};return!en(n.byteLength)||n.byteLength<=0||n.byteLength!==12+n.headerBytes+n.arrayBytes||n.decodedBytes!==ea(c)||t.tessellationInput!==void 0&&t.tessellationInput!==o||t.object!==void 0&&t.object!==s||t.surfaceInput!==void 0&&t.surfaceInput!==e||t.surfaceObject!==void 0&&t.surfaceObject!==i?null:Object.freeze({schemaVersion:Ni,object:s,byteLength:n.byteLength,decodedBytes:n.decodedBytes,surfaceInput:e,surfaceObject:i,tessellationInput:o,renderIdentity:a,quality:r,tessellatorVersion:_e,payloadVersion:ie,...c})}catch{return null}}d(Qs,"validateTessellationProbeRow");function ia(n,t={}){try{let e=na(n,t);if(!e)return null;let{header:i,identity:s}=e,r=n.byteOffset+12+e.sizes.headerBytes,o=r%4===0,a=d((m,g)=>{let x=o?new g(n.buffer,r,m):new g(n.buffer.slice(r,r+m*4));return r+=m*4,x},"take"),c=a(i.positionCount,Float32Array),l=a(i.normalCount,Float32Array),u=a(i.faceOrdCount,Float32Array),h=a(i.indexCount,Uint32Array),f=a(i.sideOrdCount,Uint32Array),p=i.edges.map(m=>({ord:m.ord,visibilityClass:m.visibilityClass,polyline:a(m.count,Float32Array)}));return{component:{positions:c,normals:l,faceOrds:u,indices:h,sideOrds:f,faceRanges:i.faceRanges,edges:p,bounds:i.bounds,scale:i.scale},partColor:i.partColor??null,edgeClasses:Array.isArray(i.edgeClasses)?i.edgeClasses:null,identity:s}}catch{return null}}d(ia,"decodeComponentTessellation");var Vv=32*1024*1024;import{createHash as Zf,randomUUID as Jf}from"node:crypto";import Rt from"node:fs";import sa from"node:os";import Ht from"node:path";var tr=class extends Error{static{d(this,"TessellationMeshConflictError")}constructor(t="tessellation producer returned different bytes for the same immutable input"){super(t),this.name="TessellationMeshConflictError"}};function ra(n=process.env){return n.CADGEN_MESH_CACHE!=="0"}d(ra,"tessellationCacheEnabled");function oa(n=process.env){let t=(n.CADGEN_CACHE_DIR||"").trim();if(t){let e=t.replace(/^~(?=$|[/\\])/,sa.homedir()),i=Ht.resolve(e);return Ht.isAbsolute(e)||(n.CADGEN_CACHE_DIR=i),i}if(process.platform==="win32"){let e=(n.LOCALAPPDATA||"").trim();if(e)return Ht.join(e,"cadgen")}else{let e=(n.XDG_CACHE_HOME||"").trim();if(e)return Ht.join(e,"cadgen")}return Ht.join(sa.homedir(),".cache","cadgen")}d(oa,"cadgenCacheRootDir");function Kf(n=process.env){return Ht.join(oa(n),"index","mesh")}d(Kf,"tessellationCacheDir");function Di(n){return Zf("sha256").update(n).digest("hex")}d(Di,"digestBytes");function nr(n,t=process.env){return Ht.join(oa(t),"objects",n.slice(0,2),n.slice(2))}d(nr,"objectPath");function aa(n,t=process.env){return Ht.join(Kf(t),n)}d(aa,"indexPath");function jf(n){return Ht.join(Ht.dirname(n),`.${Ht.basename(n)}.${process.pid}.${Jf()}.tmp`)}d(jf,"tempPath");function ca(n,t){Rt.mkdirSync(Ht.dirname(n),{recursive:!0});let e=jf(n);try{Rt.writeFileSync(e,t,{flag:"wx"}),Rt.renameSync(e,n)}finally{try{Rt.unlinkSync(e)}catch{}}}d(ca,"writeAtomic");function Qf(n){let t=Rt.openSync(n,"r");try{let e=Rt.fstatSync(t);if(!e.isFile()||e.size<=0||e.size>$o)return null;let i=Buffer.allocUnsafe(e.size);return Rt.readSync(t,i,0,i.length,0)!==i.length?null:JSON.parse(i.toString("utf8"))}finally{Rt.closeSync(t)}}d(Qf,"readBoundedJson");function la(n,t=process.env){if(!ra(t))return null;try{let e=Qs(Qf(aa(n,t)),{tessellationInput:n});if(!e)return null;let i=Rt.statSync(nr(e.object,t));return i.isFile()&&i.size===e.byteLength?e:null}catch{return null}}d(la,"probeCachedTessellation");function er(n,t,e=t){if(!Number.isSafeInteger(t)||t<=0||!Number.isSafeInteger(e)||e<t)return null;let i;try{i=Rt.openSync(n,"r");let s=Rt.fstatSync(i);if(!s.isFile()||s.size!==t||s.size>e)return null;let r=Buffer.allocUnsafe(t),o=0;for(;o<r.byteLength;){let c=Rt.readSync(i,r,o,r.byteLength-o,o);if(c<=0)return null;o+=c}let a=Rt.fstatSync(i);return!a.isFile()||a.size!==t?null:new Uint8Array(r.buffer,r.byteOffset,r.byteLength)}catch{return null}finally{if(i!==void 0)try{Rt.closeSync(i)}catch{}}}d(er,"readExactObjectBytes");function ir(n,{expectedObject:t,maxBytes:e,env:i=process.env}={}){let s=la(n,i);if(!s||t!==void 0&&s.object!==t)return null;let r=e===void 0?s.byteLength:Number(e);if(!Number.isSafeInteger(r)||r<s.byteLength)return null;let o=er(nr(s.object,i),s.byteLength,r);return!o||Di(o)!==s.object||!js(o,s)?null:o}d(ir,"readCachedTessellationBytes");function td(n,t){let e=js(t,{tessellationInput:n});if(!e)throw new TypeError("invalid TESS v4 payload");let i=Qs({schemaVersion:Ni,object:Di(t),...e},{tessellationInput:n});if(!i)throw new TypeError("invalid TESS v4 mesh record");return i}d(td,"recordForPayload");function ed(n,t,e){let i=nr(n.object,e),s=er(i,n.byteLength);if(s&&Di(s)===n.object)return;ca(i,t);let r=er(i,n.byteLength);if(!r||Di(r)!==n.object)throw new Error(`tessellation object address mismatch for ${n.object}`)}d(ed,"putObject");function ua(n,t,e=process.env){if(!ra(e))return null;let i=t instanceof Uint8Array?t:new Uint8Array(t),s=td(n,i),r=la(n,e);if(r&&(r.object!==s.object||r.surfaceObject!==s.surfaceObject)&&ir(n,{expectedObject:r.object,env:e}))throw new tr;return ed(s,i,e),ca(aa(n,e),JSON.stringify(s)),s}d(ua,"writeCachedTessellationBytes");function Ui(n){return n<=.04045?n/12.92:((n+.055)/1.055)**2.4}d(Ui,"srgbToLinear");function nd(n){return n<=.0031308?n*12.92:1.055*n**(1/2.4)-.055}d(nd,"linearToSrgb");function id(n){let t=Math.min(1,Math.max(0,Number(n)||0));return Math.round(Math.min(1,Math.max(0,nd(t)))*255)}d(id,"linearChannelToSrgbByte");function se(n){return!Array.isArray(n)||n.length<3?null:`#${n.slice(0,3).map(e=>id(e).toString(16).padStart(2,"0")).join("")}`}d(se,"linearRgbToHex");var nn=globalThis.Buffer,sd=typeof TextEncoder<"u"?new TextEncoder:null;function rd(n,t=0){let e=Number(n);return Number.isFinite(e)?e:t}d(rd,"finiteNumber");function kn(n){return Math.min(Math.max(rd(n),0),1)}d(kn,"clamp01");function Fi(n,t="utf-8"){if(nn?.from)return nn.from(String(n),t);if(t!=="utf-8"&&t!=="utf8"){let e=String(n),i=new Uint8Array(e.length);for(let s=0;s<e.length;s+=1)i[s]=e.charCodeAt(s)&255;return i}return sd.encode(String(n))}d(Fi,"bytesFromString");function re(n,t=0){if(nn?.alloc)return nn.alloc(n,t);let e=new Uint8Array(n);return t&&e.fill(t),e}d(re,"allocBytes");function sn(n,t=void 0){if(nn?.concat)return nn.concat(n,t);let e=t??n.reduce((r,o)=>r+o.length,0),i=new Uint8Array(e),s=0;for(let r of n)i.set(r,s),s+=r.length;return i}d(sn,"concatBytes");function Ot(n){return new Uint8Array(n.buffer,n.byteOffset,n.byteLength)}d(Ot,"typedArrayBytes");function sr(n){return new DataView(n.buffer,n.byteOffset,n.byteLength)}d(sr,"viewFor");function st(n,t,e){sr(n).setUint16(t,e,!0)}d(st,"writeUInt16LE");function ct(n,t,e){sr(n).setUint32(t,e,!0)}d(ct,"writeUInt32LE");function rr(n,t,e){sr(n).setFloat32(t,e,!0)}d(rr,"writeFloatLE");function fa(n,t,e,i){let s=String(e).slice(0,i);for(let r=0;r<s.length;r+=1)n[t+r]=s.charCodeAt(r)&127}d(fa,"writeAscii");function ha(n,t=32){let e=(4-n.length%4)%4;return e?sn([n,re(e,t)]):n}d(ha,"align4Buffer");function Pe(n,t="model"){return String(n||t).trim().replace(/[\x00-\x1f<>:"/\\|?*]+/g,"-")||t}d(Pe,"sanitizeName");function or(n){let t=[1/0,1/0,1/0],e=[-1/0,-1/0,-1/0];for(let i=0;i<n.length;i+=3)t[0]=Math.min(t[0],n[i]),t[1]=Math.min(t[1],n[i+1]),t[2]=Math.min(t[2],n[i+2]),e[0]=Math.max(e[0],n[i]),e[1]=Math.max(e[1],n[i+1]),e[2]=Math.max(e[2],n[i+2]);return{min:t.map(i=>Number.isFinite(i)?i:0),max:e.map(i=>Number.isFinite(i)?i:0)}}d(or,"boundsForPositions");function da(n,t="#d4d4d8"){let e=String(n||t).trim(),i=/^#(?:[0-9a-fA-F]{3}){1,2}$/.test(e)?e:t,s=i.length===4?`${i[1]}${i[1]}${i[2]}${i[2]}${i[3]}${i[3]}`:i.slice(1);return[parseInt(s.slice(0,2),16)/255,parseInt(s.slice(2,4),16)/255,parseInt(s.slice(4,6),16)/255]}d(da,"hexToRgb01");function pa(n,t){let e=ha(sn(t),0);n.buffers=[{byteLength:e.length}];let i=ha(Fi(JSON.stringify(n)),32),s=20+i.length+8+e.length,r=re(12);ct(r,0,1179937895),ct(r,4,2),ct(r,8,s);let o=re(8);ct(o,0,i.length),ct(o,4,1313821514);let a=re(8);return ct(a,0,e.length),ct(a,4,5130562),sn([r,o,i,a,e],s)}d(pa,"buildGlb");function od(n,t){let e=n[t],i=n[t+1],s=n[t+2],r=n[t+3],o=n[t+4],a=n[t+5],c=n[t+6],l=n[t+7],u=n[t+8],h=r-e,f=o-i,p=a-s,m=c-e,g=l-i,x=u-s,_=f*x-p*g,v=p*m-h*x,y=h*g-f*m,b=Math.sqrt(_*_+v*v+y*y);return b>1e-12?[_/b,v/b,y/b]:[0,0,1]}d(od,"triangleNormal");function ma(n,{name:t="model"}={}){let e=n.positions||new Float32Array,i=Math.floor(e.length/9),s=re(84+i*50);fa(s,0,`cad ${Pe(t)}`,80),ct(s,80,i);let r=84;for(let o=0;o<i;o+=1){let a=o*9,c=od(e,a);for(let l of c)rr(s,r,l),r+=4;for(let l=0;l<9;l+=1)rr(s,r,e[a+l]),r+=4;st(s,r,0),r+=2}return s}d(ma,"meshToBinaryStl");function cr(n){return String(n??"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}d(cr,"xmlEscape");function ar(n){let t=ar.table;if(!t){t=new Uint32Array(256);for(let i=0;i<256;i+=1){let s=i;for(let r=0;r<8;r+=1)s=s&1?3988292384^s>>>1:s>>>1;t[i]=s>>>0}ar.table=t}let e=4294967295;for(let i of n)e=t[(e^i)&255]^e>>>8;return(e^4294967295)>>>0}d(ar,"crc32");function ga(n){let t=[],e=[],i=0,s=0,r=33;for(let l of n){let u=Fi(l.name),h=l.body instanceof Uint8Array?l.body:Fi(String(l.body||"")),f=ar(h),p=re(30);ct(p,0,67324752),st(p,4,20),st(p,6,0),st(p,8,0),st(p,10,s),st(p,12,r),ct(p,14,f),ct(p,18,h.length),ct(p,22,h.length),st(p,26,u.length),st(p,28,0),t.push(p,u,h);let m=re(46);ct(m,0,33639248),st(m,4,20),st(m,6,20),st(m,8,0),st(m,10,0),st(m,12,s),st(m,14,r),ct(m,16,f),ct(m,20,h.length),ct(m,24,h.length),st(m,28,u.length),st(m,30,0),st(m,32,0),st(m,34,0),st(m,36,0),ct(m,38,0),ct(m,42,i),e.push(m,u),i+=p.length+u.length+h.length}let o=i,a=sn(e),c=re(22);return ct(c,0,101010256),st(c,4,0),st(c,6,0),st(c,8,n.length),st(c,10,n.length),ct(c,12,a.length),ct(c,16,o),st(c,20,0),sn([...t,a,c])}d(ga,"zipStore");var Ne=5126,ad=5122,cd=5120,xa=5123,ld=5125,ye=34962,_a=34963,ud=4,hd=65535,Le=32767,lr=127;function ur(n){return n+3&-4}d(ur,"align4");function va(n,t){if(n.length>=t)return n;let e=new Uint8Array(t);return e.set(n,0),e}d(va,"padTo");function ya(n,t,e,i){if(e===t)return va(n,ur(n.length));let s=new Uint8Array(i*e);for(let r=0;r<i;r+=1)s.set(n.subarray(r*t,(r+1)*t),r*e);return s}d(ya,"strideElements");function fd(n,t){let e=n[t],i=n[t+1],s=n[t+2],r=n[t+3],o=n[t+4],a=n[t+5],c=n[t+6],l=n[t+7],u=n[t+8],h=r-e,f=o-i,p=a-s,m=c-e,g=l-i,x=u-s,_=f*x-p*g,v=p*m-h*x,y=h*g-f*m,b=Math.sqrt(_*_+v*v+y*y);return b>1e-12?[_/b,v/b,y/b]:[0,0,1]}d(fd,"faceNormal");function dd(n,t,{weldDecimals:e=5}={}){let i=Math.floor(n.length/3),s=10**e,r=d(h=>Math.round(h*s)/s,"q"),o=[],a=[],c=new Uint32Array(i),l=new Map,u=t&&t.length===n.length;for(let h=0;h*9<n.length;h+=1){let f=h*9,p=u?null:fd(n,f);for(let m=0;m<3;m+=1){let g=f+m*3,x=n[g],_=n[g+1],v=n[g+2],y=u?t[g]:p[0],b=u?t[g+1]:p[1],T=u?t[g+2]:p[2],S=`${r(x)},${r(_)},${r(v)},${r(y)},${r(b)},${r(T)}`,M=l.get(S);M===void 0&&(M=o.length/3,l.set(S,M),o.push(x,_,v),a.push(y,b,T)),c[h*3+m]=M}}return{positions:new Float32Array(o),normals:new Float32Array(a),indices:c.subarray(0,Math.floor(n.length/3)*3)}}d(dd,"weldMesh");function pd(n,t){let e=n.length/3,i=new Int16Array(n.length),s=[Math.max(t.max[0]-t.min[0],1e-9),Math.max(t.max[1]-t.min[1],1e-9),Math.max(t.max[2]-t.min[2],1e-9)];for(let r=0;r<e;r+=1)for(let o=0;o<3;o+=1){let a=r*3+o,c=(n[a]-t.min[o])/s[o];i[a]=Math.max(-Le,Math.min(Le,Math.round(c*Le)))}return{array:i,scale:s.map(r=>r/Le),translation:[t.min[0],t.min[1],t.min[2]]}}d(pd,"quantizePositions");function md(n){let t=new Int8Array(n.length);for(let e=0;e<n.length;e+=1)t[e]=Math.max(-lr,Math.min(lr,Math.round(n[e]*lr)));return t}d(md,"quantizeNormals");var gd=.42,xd=.03;function Vn(n,t){let e=Number(n?.[t]);return Number.isFinite(e)?kn(e):null}d(Vn,"finishChannel");function _d(n,t,e=null,i=null){let s=da(n).map(kn).map(Ui).map(Math.fround),r=Vn(i,"opacity"),o=e==null?r===null?1:r:kn(e),a=Vn(i,"roughness"),c=Vn(i,"metalness"),l=Vn(i,"clearcoat"),u=Vn(i,"clearcoatRoughness"),h={name:Pe(t||"material","material"),doubleSided:!0,extras:{cadSourceColor:!0},pbrMetallicRoughness:{baseColorFactor:[...s,o],roughnessFactor:a===null?gd:a,metallicFactor:c===null?xd:c}};return o<1&&(h.alphaMode="BLEND"),l!==null&&l>0&&(h.extensions={KHR_materials_clearcoat:{clearcoatFactor:l,...u===null?{}:{clearcoatRoughnessFactor:u}}}),h}d(_d,"materialFor");var yd=[["translation",3,"VEC3"],["rotation",4,"VEC4"],["scale",3,"VEC3"]];function vd(n,{nodeIndexByKey:t,targetCountByKey:e,accessors:i,pushView:s}){let r=[];for(let o of Array.isArray(n)?n:[]){let a=[],c=[],l=new Map,u=d(h=>{let f=l.get(h);if(f!==void 0)return f;if(!h||!h.length)throw new Error("writeGlb: an animation channel needs a non-empty times array");return i.push({bufferView:s(Ot(h)),byteOffset:0,componentType:Ne,count:h.length,type:"SCALAR",min:[h[0]],max:[h[h.length-1]]}),f=i.length-1,l.set(h,f),f},"timeAccessorFor");for(let h of o?.channels||[]){let f=t.get(String(h?.node));if(f===void 0)throw new Error(`writeGlb: animation channel targets node ${JSON.stringify(h?.node)}, which no primitive declared`);let p=u(h?.times||o?.times);if(h?.weights){let m=h?.times||o?.times,g=Number(h.targetCount),x=e.get(String(h.node))||0;if(!Number.isInteger(g)||g<1||g!==x)throw new Error(`writeGlb: weights channel on node ${JSON.stringify(h.node)} declares ${h.targetCount} morph targets, but its mesh has ${x}`);if(h.weights.length!==m.length*g)throw new Error(`writeGlb: weights channel on node ${JSON.stringify(h.node)} has ${h.weights.length} scalars for ${m.length} times x ${g} targets`);i.push({bufferView:s(Ot(h.weights)),byteOffset:0,componentType:Ne,count:h.weights.length,type:"SCALAR"}),a.push({input:p,output:i.length-1,interpolation:"LINEAR"}),c.push({sampler:a.length-1,target:{node:f,path:"weights"}})}for(let[m,g,x]of yd){let _=h?.[m];_&&(i.push({bufferView:s(Ot(_)),byteOffset:0,componentType:Ne,count:_.length/g,type:x}),a.push({input:p,output:i.length-1,interpolation:"LINEAR"}),c.push({sampler:a.length-1,target:{node:f,path:m}}))}}c.length&&r.push({name:Pe(o?.name||"clip","clip"),samplers:a,channels:c})}return r}d(vd,"buildAnimations");function Ma(n,t={}){let{preset:e="export",name:i="model",units:s="mm",weldDecimals:r=5,encoder:o=null,occurrenceIdPrefix:a=null,upAxis:c="y",animations:l=null,nodeTransforms:u=null}=t,h=String(c).trim().toLowerCase();if(h!=="y"&&h!=="z")throw new Error(`writeGlb: upAxis must be "y" (glTF) or "z" (CAD), got ${JSON.stringify(c)}`);let f=String(a||t.sourceKind||Pe(i,"model")),p=e==="render";if(p&&!o)throw new Error("writeGlb: preset 'render' requires meshoptimizer's MeshoptEncoder (await MeshoptEncoder.ready)");if(p&&(l||u))throw new Error("writeGlb: preset 'render' spends every node transform on dequantization, so it carries no animation or node TRS \u2014 use preset 'export' for an animated file");let m=Array.isArray(n?.primitives)&&n.primitives.length?n.primitives:[{positions:n?.positions,normals:n?.normals,color:t.color}],g=[],x=[],_=[],v=[],y=[],b=[],T=new Map,S=0,M=d(E=>{let D=ur(S);D>S&&(g.push(new Uint8Array(D-S)),S=D),g.push(E);let F=S;return S+=E.length,F},"appendBytes"),A=d((E,D)=>{let O={buffer:0,byteOffset:M(E),byteLength:E.length};return D&&(O.target=D),x.push(O),x.length-1},"pushView"),I=d((E,{count:D,stride:F,mode:O,target:U})=>{let B=M(E),z={byteLength:D*F,byteStride:F,extensions:{EXT_meshopt_compression:{buffer:0,byteOffset:B,byteLength:E.length,count:D,byteStride:F,mode:O}}};return U&&(z.target=U),x.push(z),x.length-1},"pushCompressedView");for(let E of m){let D=E?.positions instanceof Float32Array?E.positions:new Float32Array(E?.positions||[]);if(!D.length)continue;let F=Array.isArray(E?.targets)&&E.targets.length?E.targets:null;if(F){if(!E?.indices)throw new Error("writeGlb: morph targets need already-indexed input \u2014 a weld can merge two vertices a target moves apart, and the deltas would then be 1:1 with nothing");if(p)throw new Error("writeGlb: preset 'render' quantizes every attribute and carries no morph targets \u2014 use preset 'export' for a deforming file")}let O=E?.indices?{positions:D,normals:E.normals instanceof Float32Array&&E.normals.length===D.length?E.normals:new Float32Array(D.length),indices:E.indices}:dd(D,E?.normals,{weldDecimals:r}),U=O.positions.length/3,B=or(O.positions),z=null;if(typeof E?.colorAt=="function"){z=new Uint16Array(U*4);for(let vt=0;vt<U;vt+=1){let ze=E.colorAt(O.positions[vt*3],O.positions[vt*3+1],O.positions[vt*3+2],O.normals[vt*3],O.normals[vt*3+1],O.normals[vt*3+2]);for(let zt=0;zt<3;zt+=1)z[vt*4+zt]=Math.round(Ui(kn(Number(ze?.[zt])||0))*65535);z[vt*4+3]=65535}}let G,X,V=null,W,q,$=null,tt=null;if(p){let vt=pd(O.positions,B),ze=ya(Ot(vt.array),6,8,U),zt=ya(Ot(md(O.normals)),3,4,U);G=I(o.encodeVertexBuffer(ze,U,8),{count:U,stride:8,mode:"ATTRIBUTES",target:ye}),X=I(o.encodeVertexBuffer(zt,U,4),{count:U,stride:4,mode:"ATTRIBUTES",target:ye}),z&&(V=I(o.encodeVertexBuffer(Ot(z),U,8),{count:U,stride:8,mode:"ATTRIBUTES",target:ye})),$=vt.scale,tt=vt.translation,W={bufferView:G,byteOffset:0,componentType:ad,count:U,type:"VEC3",min:[0,0,0],max:[Le,Le,Le]},q={bufferView:X,byteOffset:0,componentType:cd,count:U,type:"VEC3",normalized:!0}}else G=A(Ot(O.positions),ye),X=A(Ot(O.normals),ye),z&&(V=A(Ot(z),ye)),W={bufferView:G,byteOffset:0,componentType:Ne,count:U,type:"VEC3",min:B.min,max:B.max},q={bufferView:X,byteOffset:0,componentType:Ne,count:U,type:"VEC3"};let J=U<=hd,j=J?new Uint16Array(O.indices):new Uint32Array(O.indices),nt=J?2:4,Mt=p?I(o.encodeIndexBuffer(new Uint8Array(j.buffer,j.byteOffset,j.byteLength),j.length,nt),{count:j.length,stride:nt,mode:"TRIANGLES",target:_a}):A(va(Ot(j),ur(j.byteLength)),_a);_.push(W);let Qt=_.length-1;_.push(q);let Pt=_.length-1,pt=null;z&&(_.push({bufferView:V,byteOffset:0,componentType:xa,count:U,type:"VEC4",normalized:!0}),pt=_.length-1),_.push({bufferView:Mt,byteOffset:0,componentType:J?xa:ld,count:j.length,type:"SCALAR"});let oe=_.length-1,wt=F?.map((vt,ze)=>{let zt=vt?.positionDeltas;if(!(zt instanceof Float32Array)||zt.length!==O.positions.length)throw new Error(`writeGlb: morph target ${ze} has ${zt?.length??"no"} position deltas for ${O.positions.length/3} vertices`);let Br=or(zt);_.push({bufferView:A(Ot(zt),ye),byteOffset:0,componentType:Ne,count:U,type:"VEC3",min:Br.min,max:Br.max});let zr={POSITION:_.length-1},mn=vt?.normalDeltas;if(mn){if(!(mn instanceof Float32Array)||mn.length!==O.positions.length)throw new Error(`writeGlb: morph target ${ze} has ${mn.length} normal deltas for ${O.positions.length/3} vertices`);_.push({bufferView:A(Ot(mn),ye),byteOffset:0,componentType:Ne,count:U,type:"VEC3"}),zr.NORMAL=_.length-1}return zr})||null;b.push(_d(z?"#ffffff":E?.color,E?.materialName||E?.name,E?.opacity??null,E?.material??null));let be={attributes:{POSITION:Qt,NORMAL:Pt,...pt===null?{}:{COLOR_0:pt}},indices:oe,material:b.length-1,mode:ud,...wt?{targets:wt}:{}},Xt=E?.node===void 0||E?.node===null?`\0primitive:${T.size}`:String(E.node),Nt=T.get(Xt);if(!Nt)Nt={key:Xt,input:E,primitives:[],quantization:null,targetCount:wt?wt.length:0},T.set(Xt,Nt);else{if(Nt.targetCount!==(wt?wt.length:0))throw new Error(`writeGlb: node ${JSON.stringify(Xt)} mixes primitives with ${Nt.targetCount} and ${wt?wt.length:0} morph targets, and glTF weights are per MESH`);if(p)throw new Error(`writeGlb: preset 'render' cannot put two primitives on node ${JSON.stringify(Xt)}: each quantized primitive owns its node's transform`)}Nt.primitives.push(be),$&&(Nt.quantization={scale:$,translation:tt})}let C=new Map,N=new Map;for(let E of T.values()){N.set(E.key,E.targetCount),v.push({primitives:E.primitives,...E.targetCount?{weights:new Array(E.targetCount).fill(0)}:{}});let D={mesh:v.length-1,name:Pe(E.input?.name||i,i),extras:{cadOccurrenceId:String(E.input?.occurrenceId||`${f}:${y.length}`),cadSourceKind:t.sourceKind||"mesh",cadUnits:s,cadUpAxis:h}};E.quantization&&(D.scale=E.quantization.scale,D.translation=E.quantization.translation);let F=u instanceof Map?u.get(E.key):null;F&&(F.translation&&(D.translation=[...F.translation]),F.rotation&&(D.rotation=[...F.rotation]),F.scale&&(D.scale=[...F.scale])),C.set(E.key,y.length),y.push(D)}let R=vd(l,{nodeIndexByKey:C,targetCountByKey:N,accessors:_,pushView:A}),w=p?["KHR_mesh_quantization","EXT_meshopt_compression"]:[],P=[...w];b.some(E=>E.extensions?.KHR_materials_clearcoat)&&P.push("KHR_materials_clearcoat");let L={asset:{version:"2.0",generator:"cadgen-js writeGlb"},scene:0,scenes:[{nodes:y.map((E,D)=>D)}],nodes:y,meshes:v,materials:b,bufferViews:x,accessors:_,...R.length?{animations:R}:{}};return P.length&&(L.extensionsUsed=P),w.length&&(L.extensionsRequired=w),pa(L,g)}d(Ma,"writeGlb");var hr=["stl","glb","3mf"],Md=4194304,Sa="#d4d4d8",Aa=["roughness","metalness","clearcoat","clearcoatRoughness","opacity"];function fr(n){if(!n||typeof n!="object"||Array.isArray(n))return null;let t={};for(let e of Aa){let i=Number(n[e]);Number.isFinite(i)&&(t[e]=Math.min(1,Math.max(0,i)))}return Object.keys(t).length?t:null}d(fr,"occurrenceMaterial");function bd(n,t){let e=fr(n),i=Array.isArray(t)&&t.length>=4&&Number.isFinite(Number(t[3]))?Math.min(1,Math.max(0,Number(t[3]))):1;if(i>=.999)return e;let s=e&&Number.isFinite(Number(e.opacity))?e.opacity:1;return{...e||{},opacity:i*s}}d(bd,"occurrenceMaterialWithSourceAlpha");function ba(n){return n?`|${Aa.map(t=>t in n?n[t]:"").join(",")}`:""}d(ba,"materialKey");function Ta(n,t,e,i=Sa){let s=String(t?.component||""),r=/^#[0-9a-fA-F]{6}$/.test(String(t?.baseColor||""))?String(t.baseColor).toUpperCase():se(t?.color),o=se(n?.components?.[s]?.color)||null,a=se(e?.partColor)||null,c=r||o||a||i;return(e?.faceRanges||[]).map(l=>se(l.color)||c)}d(Ta,"occurrenceFaceRangeColors");function dr(n,t,e,i,s,r){s[r]=n[0]*t+n[1]*e+n[2]*i+n[3],s[r+1]=n[4]*t+n[5]*e+n[6]*i+n[7],s[r+2]=n[8]*t+n[9]*e+n[10]*i+n[11]}d(dr,"transformPoint");function pr(n){return n[0]*(n[5]*n[10]-n[6]*n[9])-n[1]*(n[4]*n[10]-n[6]*n[8])+n[2]*(n[4]*n[9]-n[5]*n[8])}d(pr,"determinant3");function mr(n){let t=n[0],e=n[1],i=n[2],s=n[4],r=n[5],o=n[6],a=n[8],c=n[9],l=n[10],u=r*l-o*c,h=o*a-s*l,f=s*c-r*a,p=t*u+e*h+i*f;if(!Number.isFinite(p)||Math.abs(p)<1e-30)return null;let m=1/p;return[u*m,h*m,f*m,(i*c-e*l)*m,(t*l-i*a)*m,(e*a-t*c)*m,(e*o-i*r)*m,(i*s-t*o)*m,(t*r-e*s)*m]}d(mr,"normalMatrix3");function gr(n){return!Array.isArray(n)||n.length<12?!0:[1,0,0,0,0,1,0,0,0,0,1,0].every((e,i)=>n[i]===e)}d(gr,"identityTransform");function xr(n,t,e={}){let i=e.defaultColor||Sa,s=new Map(Object.entries(n.components||{}).map(([g,x])=>[g,se(x?.color)])),r=Math.max(1,Math.floor(Number(e.maxPrimitiveTriangles)||Md)),o=e.perOccurrence===!0,a=e.hiddenOccurrenceIds instanceof Set?e.hiddenOccurrenceIds:null,c=e.occurrenceOpacity instanceof Map?e.occurrenceOpacity:null,l=e.occurrenceOverrides instanceof Map?e.occurrenceOverrides:null;if(l&&!o)throw new Error("buildPackageMeshPrimitives: occurrenceOverrides needs perOccurrence \u2014 an override is keyed by occurrence, and the flat soup has no occurrence to key it to");let u=[],h=new Map,f=-1;for(let g of n.occurrences||[]){f+=1;let x=String(g.component||""),_=t.get(x);if(!_)continue;let v=String(g.id||x);if(a?.has(v))continue;let y=/^#[0-9a-fA-F]{6}$/.test(String(g?.baseColor||""))?String(g.baseColor).toUpperCase():se(g.color),b=s.get(x)||null,T=se(_.partColor)||null,S=y||b||T||i,M=c?.has(v)?c.get(v):null,A=bd(g.material,g.color),I=String(g.materialId||"").trim(),C=String(g.materialName||I).trim(),N=ba(A)+(I?`|material:${I}`:""),R=l?.get(v);if(R){R.forEach((D,F)=>{let O=`${String(f).padStart(8,"0")}|${D.color}${ba(D.material||null)}|${String(F).padStart(4,"0")}`;h.set(O,{override:{...D,node:v,name:String(g.name||v),occurrenceId:v,...I?{materialId:I}:{},...C?{materialName:C}:{},...M==null?{}:{opacity:M}}})});continue}let w=Array.isArray(g.transform)?g.transform:null,P=w===null||gr(w),L=!P&&pr(w)<0,E=P?null:mr(w);for(let D of _.faceRanges||[]){let F=Number(D.indexCount)||0,O=Math.max(0,Math.ceil(F/3));if(!O)continue;let U=se(D.color)||S,B=(o?`${String(f).padStart(8,"0")}|${U}`:U)+N,z=h.get(B);z||h.set(B,z={color:U,material:A,materialId:I,materialName:C,chunks:[],node:o?v:null,name:o?String(g.name||v):null,occurrenceId:o?v:null,opacity:M});let G=z.chunks[z.chunks.length-1];(!G||G.triangles+O>r)&&(G={triangles:0,floatCount:0,positions:null,normals:null,offset:0},z.chunks.push(G)),G.triangles+=O,G.floatCount+=O*9,u.push({tessellation:_,range:D,color:U,chunk:G,transform:P?null:w,mirrored:L,nm:E})}}for(let g of h.values())for(let x of g.chunks||[])x.positions=new Float32Array(x.floatCount),x.normals=new Float32Array(x.floatCount);for(let g of u){let{positions:x,normals:_,indices:v}=g.tessellation,{range:y,transform:b,mirrored:T,nm:S}=g,M=g.chunk,A=M.positions,I=M.normals,C=M.offset,N=T?[0,2,1]:[0,1,2];for(let R=y.indexStart;R<y.indexStart+y.indexCount;R+=3)for(let w of N){let P=v[R+w],L=x[P*3],E=x[P*3+1],D=x[P*3+2];b===null?(A[C]=L,A[C+1]=E,A[C+2]=D):dr(b,L,E,D,A,C);let F=_[P*3],O=_[P*3+1],U=_[P*3+2],B=F,z=O,G=U;S&&(B=S[0]*F+S[1]*O+S[2]*U,z=S[3]*F+S[4]*O+S[5]*U,G=S[6]*F+S[7]*O+S[8]*U);let X=Math.sqrt(B*B+z*z+G*G)||1;I[C]=B/X,I[C+1]=z/X,I[C+2]=G/X,C+=3}M.offset=C}let p=[...h.entries()].sort(([g],[x])=>g<x?-1:1).flatMap(([,g])=>g.override?[g.override]:g.chunks.map(x=>({color:g.color,positions:x.positions,normals:x.normals,...g.node===null?{}:{node:g.node,name:g.name,occurrenceId:g.occurrenceId},...g.opacity===null||g.opacity===void 0?{}:{opacity:g.opacity},...g.material===null?{}:{material:g.material},...g.materialId?{materialId:g.materialId}:{},...g.materialName?{materialName:g.materialName}:{}}))).filter(g=>g.indices?g.indices.length>=3:g.positions.length>=9),m=p.reduce((g,x)=>g+(x.indices?x.indices.length/3:x.positions.length/9),0);return{primitives:p,triangleCount:m}}d(xr,"buildPackageMeshPrimitives");function Sd({primitives:n},{name:t="model"}={}){let e=0;for(let r of n)e+=r.positions.length;let i=new Float32Array(e),s=0;for(let r of n)i.set(r.positions,s),s+=r.positions.length;return ma({positions:i},{name:t})}d(Sd,"packageMeshToStl");var Gn=.001;function Oi(n,t){let e=new Float32Array(n.length);for(let i=0;i<n.length;i+=3)e[i]=n[i]*t,e[i+1]=n[i+2]*t,e[i+2]=-n[i+1]*t;return e}d(Oi,"rotateToYUp");function Ad(n){return n.map(t=>({positionDeltas:Oi(t.positionDeltas,Gn),...t.normalDeltas?{normalDeltas:Oi(t.normalDeltas,1)}:{}}))}d(Ad,"yUpTargets");function Td(n){let t=n.verify;if(!t)return;let{vertexIds:e,posed:i}=t;for(let s=0;s<i.length;s+=1){let r=n.targets[s].positionDeltas;for(let o=0;o<e.length;o+=1){let a=e[o]*3,c=[i[s][o*3]*Gn,i[s][o*3+2]*Gn,-i[s][o*3+1]*Gn];for(let l=0;l<3;l+=1){let u=n.positions[a+l]+r[a+l];if(Math.abs(u-c[l])>wd)throw new Error(`packageMeshExport: morph target ${s} of ${n.occurrenceId||n.node} rebuilds vertex ${e[o]} as ${u} where the posed tube is ${c[l]} (axis ${l}) \u2014 base and deltas are not in the same space`)}}}}d(Td,"verifyMorphReconstruction");var wd=1e-6;function Ed(n){return n.map(t=>{let e={...t,positions:Oi(t.positions,Gn),normals:Oi(t.normals,1),...t.targets?{targets:Ad(t.targets)}:{}};return e.targets&&(Td(e),delete e.verify),e})}d(Ed,"yUpPrimitives");function Cd({primitives:n},{name:t="model",animation:e=null}={}){return Ma({primitives:Ed(n)},{preset:"export",name:t,sourceKind:"step",units:"m",upAxis:"y",...e?{animations:[e],nodeTransforms:e.rest||null}:{}})}d(Cd,"packageMeshToGlb");function Rd({primitives:n},{name:t="model"}={}){let e=n.map((c,l)=>`      <base name="material-${l}" displaycolor="${cr(c.color.toUpperCase())}FF"/>`).join(`
`),i=[],s=[];n.forEach((c,l)=>{let u=[],h=[],f=new Map,p=c.positions,m=d((x,_,v)=>{let y=`${x}:${_}:${v}`,b=f.get(y);return b===void 0&&(b=f.size,f.set(y,b),u.push(`        <vertex x="${x}" y="${_}" z="${v}"/>`)),b},"vertexId");for(let x=0;x<p.length;x+=9){let _=m(p[x],p[x+1],p[x+2]),v=m(p[x+3],p[x+4],p[x+5]),y=m(p[x+6],p[x+7],p[x+8]);_!==v&&v!==y&&y!==_&&h.push(`        <triangle v1="${_}" v2="${v}" v3="${y}"/>`)}let g=l+2;i.push(`    <object id="${g}" type="model" pid="1" pindex="${l}">
      <mesh>
        <vertices>
${u.join(`
`)}
        </vertices>
        <triangles>
${h.join(`
`)}
        </triangles>
      </mesh>
    </object>`),s.push(`    <item objectid="${g}"/>`)});let r=`<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:m="http://schemas.microsoft.com/3dmanufacturing/material/2015/02">
  <metadata name="Title">${cr(t)}</metadata>
  <resources>
    <basematerials id="1">
${e}
    </basematerials>
${i.join(`
`)}
  </resources>
  <build>
${s.join(`
`)}
  </build>
</model>
`;return ga([{name:"[Content_Types].xml",body:`<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>
`},{name:"_rels/.rels",body:`<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
`},{name:"3D/3dmodel.model",body:r}])}d(Rd,"packageMeshTo3mf");function wa(n,t,e={}){let i=String(t||"").toLowerCase();if(e.animation&&i!=="glb")throw new Error(`${i||"(no format)"} carries no animation: only glb does \u2014 export the clip as .glb, or drop the animation for a static mesh`);if(i==="stl")return{body:Sd(n,e),contentType:"model/stl",extension:".stl"};if(i==="glb")return{body:Cd(n,e),contentType:"model/gltf-binary",extension:".glb"};if(i==="3mf")return{body:Rd(n,e),contentType:"model/3mf",extension:".3mf"};throw new Error(`Unsupported package mesh export format: ${t}`)}d(wa,"packageMeshToFormat");var hn=null,Wi=null;function Za(){return hn?Promise.resolve(hn):(Wi||(Wi=Promise.resolve().then(()=>(Hi(),Ya)).then(n=>(hn=n,hn)).catch(n=>{throw Wi=null,n})),Wi)}d(Za,"loadTubeDeformation");function Ja(n="a tube deformation"){if(!hn)throw new Error(`${n} needs the tube runtime, which is loaded with the document's animation. Compile clips through compileAnimationSource/loadSourceAnimation, or await loadTubeDeformation() first.`);return hn}d(Ja,"requireTubeDeformation");function Ka(n){return!!n&&typeof n=="object"&&!Array.isArray(n)}d(Ka,"isObject");var sp=Math.PI/180;function ja(n){let t={};for(let[e,i]of Object.entries(Ka(n)?n:{})){if(!Ka(i)||typeof i.update!="function")continue;let s=Number(i.duration);t[String(e)]={id:String(e),label:String(i.label||e),duration:Number.isFinite(s)&&s>0?s:1,loop:i.loop!==!1,update:i.update}}return t}d(ja,"normalizeAnimationClips");function rp(n){let t=new Map;for(let e of n?.parts||[]){let i=String(e.label||e.name||"").trim();i&&(t.has(i)||t.set(i,[]),t.get(i).push(String(e.id)))}return t}d(rp,"partIdsByLabel");function op(n,t){let e=String(t).replace(/^#/,"").split(",").map(s=>s.trim()).filter(Boolean);if(!e.length||!e.every(s=>/^o[\d.]+$/.test(s)))return null;let i=[];for(let s of n?.parts||[]){let r=String(s.id);e.some(o=>r===o||r.startsWith(`${o}.`))&&i.push(r)}return i.length?i:null}d(op,"partIdsForOccurrenceRefs");function ap(n,t){let e=rp(t),i=new Map,s=new Map,r=new Map;return{model:{get:d(c=>{let l=e.get(String(c).replace(/^#/,""))||e.get(String(c))||op(t,c);if(!l||!l.length){let f=[...e.keys()].sort().join(", ")||"(none)";throw new Error(`animation: no occurrence labeled ${JSON.stringify(c)}; labels: ${f}`)}let u=d(f=>{for(let p of l){let m=i.get(p);i.set(p,m?new n.Matrix4().multiplyMatrices(f,m):f.clone())}},"applyMatrix"),h=d((f,p)=>{for(let m of l){let g=s.get(m)||{};g[f]=p,s.set(m,g)}},"setStyle");return{deformTube(f){let p=Ja("deformTube").normalizeTubeDeformation(f);for(let m of l)r.set(m,p);return this},rotate(f,p,m=[0,0,0]){let g=new n.Vector3(f[0],f[1],f[2]).normalize(),x=new n.Matrix4().makeRotationAxis(g,(Number(p)||0)*sp),_=new n.Matrix4().makeTranslation(-m[0],-m[1],-m[2]),v=new n.Matrix4().makeTranslation(m[0],m[1],m[2]);return u(new n.Matrix4().multiplyMatrices(v,new n.Matrix4().multiplyMatrices(x,_))),this},translate(f){return u(new n.Matrix4().makeTranslation(Number(f[0])||0,Number(f[1])||0,Number(f[2])||0)),this},opacity(f){return h("opacity",Math.max(0,Math.min(1,Number(f)))),this},visible(f){return h("visible",!!f),this}}},"handleFor"),labels:d(()=>[...e.keys()].sort(),"labels")},matrices:i,styles:s,deformations:r}}d(ap,"createAnimationFrame");function Ir(n,t,e,i){let s=ap(n,t),r=e.duration||1,o=Math.max(0,Number(i)||0);return e.loop!==!1?o=o%r:o=Math.min(o,r),e.update(o,s.model),{matrices:s.matrices,styles:s.styles,deformations:s.deformations}}d(Ir,"evaluateAnimationClip");function cp(n){return String(n??"").trim()}d(cp,"normalizeString");function Pr(n){return Math.max(Number(n?.duration)||0,.001)}d(Pr,"animationClipDuration");function Qa(n){return!n||typeof n!="object"?[]:Object.values(n).filter(t=>t&&typeof t.update=="function").map(t=>({id:String(t.id),label:String(t.label||t.id),duration:Pr(t),loop:t.loop!==!1}))}d(Qa,"animationClipList");function tc(n,t){let e=cp(t);if(!e||!n||typeof n!="object")return null;let i=n[e];return i&&typeof i.update=="function"?i:null}d(tc,"findAnimationClip");var ec=1,nc=120,ic=7200;function fn(n){return`${Number(n.toFixed(3))}s`}d(fn,"formatSeconds");function sc(n,t,{label:e="frame"}={}){let i=n&&typeof n=="object"?n:{},s=Number(i.fps??30);if(!Number.isInteger(s)||s<ec||s>nc)throw new Error(`${e} fps must be a whole number ${ec}..${nc}, got ${JSON.stringify(i.fps)}`);let r=i.start===void 0||i.start===null?0:Number(i.start);if(!Number.isFinite(r)||r<0)throw new Error(`${e} start must be seconds >= 0, got ${JSON.stringify(i.start)}`);let o=Pr(t);if(r>=o)throw new Error(`${e} start ${fn(r)} is at or past the end of a ${fn(o)} clip: every frame would be the same one`);let a=t?.loop!==!1,c=i.seconds===void 0||i.seconds===null?a?o:o-r:Number(i.seconds);if(!Number.isFinite(c)||c<=0)throw new Error(`${e} seconds must be a positive number, got ${JSON.stringify(i.seconds)}`);let l=Math.max(1,Math.round(c*s));if(l>ic)throw new Error(`${e} ${fn(c)} at ${s} fps schedules ${l} frames, past the ${ic}-frame ceiling`);let u=[];return!a&&r+c-o>1e-9&&u.push(`${e} covers ${fn(r)}..${fn(r+c)} of a ${fn(o)} clip that does not loop: every frame past its end is the same final pose`),{fps:s,seconds:c,start:r,frameCount:l,warnings:u}}d(sc,"resolveFramePlan");function rc(n,t){return n.start+t/n.fps}d(rc,"framePlanElapsedSec");Hi();var lp={Matrix4:_t,Vector3:k},Nr=Object.freeze(["opacity","visible"]),oc=Object.freeze(["refuse","morph","rest"]),up=4,hp=96;function fp(n){let t=Math.max(up,Math.ceil(hp/n.fps));return{multiple:t,hz:n.fps*t,count:(n.frameCount-1)*t+1}}d(fp,"morphFitGrid");var Xi=.001;function dp(){return new _t().set(Xi,0,0,0,0,0,Xi,0,0,-Xi,0,0,0,0,0,1)}d(dp,"cadToGlbBasis");function pp(){let n=1/Xi;return new _t().set(n,0,0,0,0,0,-n,0,0,n,0,0,0,0,0,1)}d(pp,"glbToCadBasis");var mp=1e-12,gp=new _t().elements;function xp(n){let t=n.elements;for(let e=0;e<16;e+=1)if(Math.abs(t[e]-gp[e])>mp)return!1;return!0}d(xp,"isIdentityMatrix");function _p(n){let t=[];for(let e of n?.occurrences||[]){let i=String(e?.id||"").trim(),s=String(e?.component||"").trim(),r=i||s;if(!r)continue;let o=String(e?.name||i||s).trim();t.push({id:r,occurrenceId:r,componentId:s,name:o,label:o})}return{parts:t}}d(_p,"animationTargetsFromDescriptor");function Oe(n,t=6){let e=[...n].sort();return e.length<=t?e.join(", "):`${e.slice(0,t).join(", ")} (and ${e.length-t} more)`}d(Oe,"summarize");function yp(n){let t={translations:[],rotations:[],scales:[],count:0};for(let e=0;e<n;e+=1)Dr(t,null);return t}d(yp,"newTrack");var ac=new k,cc=new Yt,lc=new k;function Dr(n,t){let e=0,i=0,s=0,r=0,o=0,a=0,c=1,l=1,u=1,h=1;if(t!==null&&(t.decompose(ac,cc,lc),{x:e,y:i,z:s}=ac,{x:r,y:o,z:a,w:c}=cc,{x:l,y:u,z:h}=lc),n.count>0){let f=(n.count-1)*4;n.rotations[f]*r+n.rotations[f+1]*o+n.rotations[f+2]*a+n.rotations[f+3]*c<0&&(r=-r,o=-o,a=-a,c=-c)}n.translations.push(e,i,s),n.rotations.push(r,o,a,c),n.scales.push(l,u,h),n.count+=1}d(Dr,"appendSample");function Lr(n,t,e){for(let i=1;i<e;i+=1)for(let s=0;s<t;s+=1)if(Math.fround(n[i*t+s])!==Math.fround(n[s]))return!0;return!1}d(Lr,"varies");function vp(n,t){for(let e=0;e<t*3;e+=1)if(Math.fround(n[e])!==1)return!1;return!0}d(vp,"scaleIsUnit");function uc(n,t,e,{drop:i=[],deform:s="refuse"}={}){let r=new Set(i.map(C=>String(C).trim())),o=[...r].filter(C=>!Nr.includes(C));if(o.length)throw new Error(`animation drop names ${o.sort().join(", ")}, which is not an effect this export can bake static; droppable effects: ${Nr.join(", ")}`);let a=String(s||"refuse");if(!oc.includes(a))throw new Error(`animation deform must be one of ${oc.join(", ")}, got ${JSON.stringify(s)}`);let c=_p(n),l=dp(),u=pp(),h=new _t,f=new Map,p=new Map,m=new Set,g=new Set,x=new Set,_=new Set,v=new Map,y=new Set,b=a==="morph"?fp(e):{multiple:1,hz:e.fps,count:e.frameCount};for(let C=0;C<b.count;C+=1){let N=rc(e,C/b.multiple),R=Ir(lp,c,t,N),w=C%b.multiple===0?C/b.multiple:-1;if(w>=0){for(let[P,L]of R.matrices){let E=f.get(P);if(!E){if(xp(L))continue;E=yp(w),f.set(P,E)}h.multiplyMatrices(l,L).multiply(u),Dr(E,h)}for(let P of f.values())P.count===w&&Dr(P,null);for(let[P,L]of R.styles)L&&Object.hasOwn(L,"opacity")&&(g.add(P),w===0&&p.set(P,L.opacity)),L&&Object.hasOwn(L,"visible")&&(x.add(P),w===0&&L.visible===!1&&m.add(P))}for(let[P,L]of R.deformations){if(_.add(P),L.braid&&y.add(P),a!=="morph")continue;let E=v.get(P);if(!E)E={rest:L,samples:[]},v.set(P,E);else if(!wr(E.rest,L))throw new Error(`clip ${t.id} changes the REST path of ${P} at ${N.toFixed(4)}s, so its geometry has no single base mesh for morph targets to be deltas against. Author one rest path per tube for the whole clip (move the tube with .translate/.rotate instead), or export the clip as video (cadgen step snapshot --animation ${t.id} --video)`);E.samples.push({index:C,timeSec:C/b.hz,deformation:L===E.rest?L:{...L,restSpec:E.rest.restSpec}})}}let T=[];for(let C of Nr){let N=C==="opacity"?g:x;if(N.size){if(!r.has(C))throw new Error(`clip ${t.id} animates .${C}() on ${Oe(N)}, and glTF has no standard animated channel for it. Pass drop: ["${C}"] to bake the value at start into the file instead, or animate the occurrence's transform rather than its appearance`);T.push(`.${C}() is not an animated glTF channel: ${Oe(N)} carries its value at start, frozen for the whole clip`)}}if(_.size){if(a==="refuse")throw new Error(`clip ${t.id} deforms tube geometry on ${Oe(_)}: that is per-vertex motion, which a node transform cannot carry. Pass deform: "morph" to bake it as morph targets (bigger file, deformTolerance sets how close they track), deform: "rest" to ship those tubes at their rest shape knowing they do not move, or export the clip as video (cadgen step snapshot --animation ${t.id} --video)`);a==="morph"?y.size&&T.push(`${Oe(y)} carries a braid: the strand pattern is a shader, not geometry, so the exported cord has the right shape and motion and a smooth surface`):T.push(`deform: "rest" ships ${Oe(_)} at rest shape: the clip's tube deformation is per-vertex motion this file does not carry`)}let S=[...m].filter(C=>f.has(C));if(S.length){for(let C of S)f.delete(C);T.push(`${Oe(S)} moves in this clip and is hidden at start: dropping .visible() omits the occurrence from the file, and a node that is not there carries no motion`)}let M=new Float32Array(e.frameCount);for(let C=0;C<e.frameCount;C+=1)M[C]=C/e.fps;let A=[],I=new Map;for(let[C,N]of f){let R=new Float32Array(N.translations),w=new Float32Array(N.rotations),P=new Float32Array(N.scales),L=vp(P,N.count);I.set(C,{translation:[R[0],R[1],R[2]],rotation:[w[0],w[1],w[2],w[3]],scale:L?null:[P[0],P[1],P[2]]});let E={node:C};Lr(R,3,N.count)&&(E.translation=R),Lr(w,4,N.count)&&(E.rotation=w),!L&&Lr(P,3,N.count)&&(E.scale=P),(E.translation||E.rotation||E.scale)&&A.push(E)}return A.sort(hc),{name:t.id,times:M,channels:A,rest:I,statics:{opacity:p,hidden:m},deformations:v,grid:b,warnings:T}}d(uc,"sampleClipAnimation");function hc(n,t){return n.node!==t.node?n.node<t.node?-1:1:(n.weights?1:0)-(t.weights?1:0)}d(hc,"compareChannels");function fc(n,t){return t?.length?{...n,channels:[...n.channels,...t].sort(hc)}:n}d(fc,"withMorphChannels");function dc(n,t){let e=n.channels.map(s=>s.node).filter(s=>!t.has(s));if(!e.length)return n;let i=new Map;for(let[s,r]of n.rest)t.has(s)&&i.set(s,r);return{...n,channels:n.channels.filter(s=>t.has(s.node)),rest:i,warnings:[...n.warnings,`${Oe(e)} moves in this clip but has no geometry in the export, so the file carries no node to animate for it`]}}d(dc,"restrictAnimationToNodes");Hi();Un();var qi={BufferGeometry:Ke,Float32BufferAttribute:de,Matrix3:Y,Vector3:k},Mp=1,Ur=512*1024*1024,pc=16,mc=5,bp=128,Sp=512,$i=new _t;function gc(n,t=6){let e=[...n].sort();return e.length<=t?e.join(", "):`${e.slice(0,t).join(", ")} (and ${e.length-t} more)`}d(gc,"summarize");function xc(n){return n>=1024**3?`${(n/1024**3).toFixed(2)} GiB`:`${(n/1024**2).toFixed(1)} MiB`}d(xc,"formatBytes");function Ap(n,t){let e=Array.isArray(n.transform)?n.transform:null,i=e===null||gr(e),s=!i&&pr(e)<0,r=i?null:mr(e),o=t.positions,a=t.normals,c=Math.floor(o.length/3),l=new Float32Array(o.length),u=new Float32Array(o.length);for(let v=0;v<c;v+=1){let y=v*3;i?(l[y]=o[y],l[y+1]=o[y+1],l[y+2]=o[y+2]):dr(e,o[y],o[y+1],o[y+2],l,y);let b=a[y],T=a[y+1],S=a[y+2],M=b,A=T,I=S;r&&(M=r[0]*b+r[1]*T+r[2]*S,A=r[3]*b+r[4]*T+r[5]*S,I=r[6]*b+r[7]*T+r[8]*S);let C=Math.sqrt(M*M+A*A+I*I)||1;u[y]=M/C,u[y+1]=A/C,u[y+2]=I/C}let h=t.faceRanges||[],f=0;for(let v of h)f+=Math.floor((Number(v.indexCount)||0)/3);let p=new Uint32Array(f*3),m=new Uint32Array(f),g=s?[0,2,1]:[0,1,2],x=0;h.forEach((v,y)=>{let b=Number(v.indexStart)||0,T=Number(v.indexCount)||0;for(let S=b;S+2<b+T;S+=3)p[x*3]=t.indices[S+g[0]],p[x*3+1]=t.indices[S+g[1]],p[x*3+2]=t.indices[S+g[2]],m[x]=y,x+=1});let _=new Ke;return _.setAttribute("position",new Ut(l,3)),_.setAttribute("normal",new Ut(u,3)),_.setIndex(new Ut(p,1)),{geometry:_,triangleRange:m}}d(Ap,"occurrenceWorldGeometry");function Tp(n){let t=n.values,e=Math.floor(t.length/8),i=new Map;for(let a=0;a<e;a+=1){let c=a*8,l=t[c],u=i.get(l);if(!u){i.set(l,[t[c+1],t[c+1],t[c+2],t[c+2],t[c+3],t[c+3]]);continue}for(let h=0;h<3;h+=1){let f=t[c+1+h];f<u[h*2]&&(u[h*2]=f),f>u[h*2+1]&&(u[h*2+1]=f)}}let s=[...i.keys()].sort((a,c)=>a-c),r=new Uint32Array(s.length+1),o=[];return s.forEach((a,c)=>{let l=i.get(a),u=[0,1,2].map(h=>l[h*2]===l[h*2+1]?[l[h*2]]:[l[h*2],l[h*2+1]]);for(let h of u[0])for(let f of u[1])for(let p of u[2])o.push(h,f,p);r[c+1]=o.length/3}),{fractions:Float64Array.from(s),cornerOffset:r,uva:Float64Array.from(o)}}d(Tp,"boundsForFractions");function _c(n,t,e){let i=t.path,s=(t.twistDeg||0)*Math.PI/180,r=rt(s),o=ht(s);for(let a=0;a<n.fractions.length;a+=1){let c=un(i,n.fractions[a]*i.length),l=c.point,u=c.normal,h=c.binormal,f=c.tangent;for(let p=n.cornerOffset[a];p<n.cornerOffset[a+1];p+=1){let m=p*3,g=n.uva[m],x=n.uva[m+1],_=n.uva[m+2],v=r*g-o*x,y=o*g+r*x;e[m]=l[0]+u[0]*v+h[0]*y+f[0]*_,e[m+1]=l[1]+u[1]*v+h[1]*y+f[1]*_,e[m+2]=l[2]+u[2]*v+h[2]*y+f[2]*_}}return e}d(_c,"poseCorners");function wp(n,t,e,i){let s=0;for(let r=0;r<e.length;r+=3){let o=e[r]-(n[r]+(t[r]-n[r])*i),a=e[r+1]-(n[r+1]+(t[r+1]-n[r+1])*i),c=e[r+2]-(n[r+2]+(t[r+2]-n[r+2])*i),l=o*o+a*a+c*c;l>s&&(s=l)}return Math.sqrt(s)}d(wp,"blendDeviation");function Ep(n,t,e){let i=n.length,s=[0];if(i<2)return s;let r=0,o=_c(t,jt(n[0]),new Float64Array(t.uva.length)),a=o,c=[],l=!0;for(let u=1;u<i;u+=1){let h=Fe(n[u],n[u-1])?a:_c(t,jt(n[u]),new Float64Array(t.uva.length));a=h,c.push({index:u,pose:h}),l=l&&Fe(n[u],n[r]);let f=!1;if(!l){let g=u-r;for(let x of c){if(x.index===u)continue;let _=(x.index-r)/g;if(wp(o,h,x.pose,_)>e){f=!0;break}}}if(!f&&c.length<bp)continue;let p=f?u-1:u,m=c.find(g=>g.index===p);s.push(p),r=p,o=m.pose,c=c.filter(g=>g.index>p),l=c.every(g=>Fe(n[g.index],n[r]))}return s[s.length-1]!==i-1&&s.push(i-1),s}d(Ep,"fitTargetTimes");function Cp(n,t,e){let i=n.geometry.index,s=Math.floor(i.count/3),r=n.sourceTriangles,o=new Map;for(let a=0;a<s;a+=1){let c=r?r[a]:a,l=e[t[c]]||e[0],u=o.get(l);u||o.set(l,u=[]),u.push(a)}return[...o.entries()].map(([a,c])=>{let l=new Uint32Array(c.length*3),u=new Map,h=0;c.forEach((p,m)=>{for(let g=0;g<3;g+=1){let x=i.getX(p*3+g),_=u.get(x);_===void 0&&(_=h,h+=1,u.set(x,_)),l[m*3+g]=_}});let f=new Uint32Array(h);for(let[p,m]of u)f[m]=p;return{color:a,indices:l,vertexIds:f,slotOf:u}})}d(Cp,"partitionByColor");function Zn(n,t){let e=new Float32Array(t.length*3);for(let i=0;i<t.length;i+=1){let s=t[i]*3;e[i*3]=n[s],e[i*3+1]=n[s+1],e[i*3+2]=n[s+2]}return e}d(Zn,"gather");function Rp(n){let t=Math.max(1,Math.min(n,Sp)),e=new Uint32Array(t);for(let i=0;i<t;i+=1)e[i]=Math.floor(i*n/t);return e}d(Rp,"verifySampleIds");function Ip(n,t){let e=0;for(let i=0;i<n.length;i+=3){let s=n[i],r=n[i+1],o=n[i+2],a=t[i],c=t[i+1],l=t[i+2],u=Math.sqrt(s*s+r*r+o*o)*Math.sqrt(a*a+c*c+l*l);if(u<1e-12)continue;let h=Math.min(1,Math.max(-1,(s*a+r*c+o*l)/u)),f=No(h)*180/Math.PI;f>e&&(e=f)}return e}d(Ip,"maxNormalDegrees");function yc(n,t,e,i={}){let{toleranceMm:s=Mp,grid:r,defaultColor:o=null,clipId:a="clip",maxRuntimeBytes:c=Ur}=i,l=Number(s);if(!(l>0))throw new Error(`morph deformTolerance must be a positive number of millimetres, got ${s}`);let u=[],h=new Map,f=[];if(!e?.size)return{overrides:h,channels:f,warnings:u,stats:null};let p=[],m=[];for(let v of n.occurrences||[]){let y=String(v.component||""),b=String(v.id||y),T=e.get(b);if(!T)continue;let S=t.get(y);if(!S||!S.positions?.length){m.push(b);continue}p.push({occurrence:v,occurrenceId:b,tessellation:S,entry:T})}if(m.length&&u.push(`${gc(m)} deforms in this clip but tessellated to nothing, so the file carries no geometry to morph for it`),!p.length)return{overrides:h,channels:f,warnings:u,stats:null};let g=[],x=0;for(let v of p){let y=v.entry.samples[0].deformation,{geometry:b,triangleRange:T}=Ap(v.occurrence,v.tessellation),S=Rr(qi,b,jt(y),$i),M={restSpec:y.restSpec,pathSpec:y.restSpec,twistDeg:0,maxSegmentLength:y.maxSegmentLength,braid:y.braid},A=new Array(r.count).fill(M);for(let R of v.entry.samples)A[R.index]=R.deformation;let I=Tp(S.mapping),C=Ep(A,I,l),N=S.vertexCount;g.push({...v,bake:S,model:I,poses:A,keys:C,triangleRange:T,vertexCount:N}),x+=N*Math.max(0,C.length-1)*2*pc}if(x>Math.min(c,Ur)){let v=g.reduce((b,T)=>b+Math.max(0,T.keys.length-1),0),y=g.reduce((b,T)=>b+T.vertexCount,0);throw new Error(`clip ${a} needs ${v} morph targets over ${g.length} tubes (${y} refined vertices) to hold ${l}mm, which is ${xc(x)} of morph texture at playback \u2014 past the ${xc(Math.min(c,Ur))} ceiling, and it is the GPU number rather than the file size that decides whether the file opens. Raise deformTolerance (the target count falls as its square root), shorten seconds, coarsen --mesh-tolerance so the tubes carry fewer vertices, or coarsen the clip's own maxSegmentLength`)}let _={toleranceMm:l,nodes:0,targets:0,bytes:0,runtimeBytes:0,refinedTriangles:0,deviationMm:0,normalsOmitted:[]};for(let v of g){let{bake:y,poses:b,keys:T,vertexCount:S,occurrenceId:M}=v,A=new de(new Float32Array(S*3),3),I=new de(new Float32Array(S*3),3);Yn(qi,y,jt(b[T[0]]),$i,A,I);let C=Float32Array.from(A.array),N=Float32Array.from(I.array),R=Rp(S),w=[],P=[],L=[],E=0;for(let V=1;V<T.length;V+=1){Yn(qi,y,jt(b[T[V]]),$i,A,I);let W=new Float32Array(S*3),q=new Float32Array(S*3);for(let $=0;$<W.length;$+=1)W[$]=A.array[$]-C[$],q[$]=I.array[$]-N[$];w.push(W),P.push(q),L.push(Zn(A.array,R)),E=Math.max(E,Ip(N,I.array))}let D=E>=mc;!D&&w.length&&_.normalsOmitted.push(M);let F=new Int32Array(T.length).fill(-1),O=[];for(let V=1;V<T.length;V+=1){let W=w[V-1],q=!1;for(let $=0;$<W.length;$+=1)if(W[$]!==0){q=!0;break}q&&(F[V]=O.length,O.push(V-1))}let U=Pp(v,{basePositions:C,deltaPositions:w,grid:r,tolerance:l,posed:A,posedNormals:I});_.deviationMm=Math.max(_.deviationMm,U);let B=Ta(n,v.occurrence,v.tessellation,o||void 0),z=fr(v.occurrence.material),X=Cp(y,v.triangleRange,B).map(V=>{let W=V.vertexIds,q=O.map(J=>({positionDeltas:Zn(w[J],W),...D?{normalDeltas:Zn(P[J],W)}:{}})),$=[],tt=[];return R.forEach((J,j)=>{let nt=V.slotOf.get(J);nt!==void 0&&($.push(nt),tt.push(j))}),{color:V.color,positions:Zn(C,W),normals:Zn(N,W),indices:V.indices,...z===null?{}:{material:z},...q.length?{targets:q}:{},...q.length&&$.length?{verify:{vertexIds:Uint32Array.from($),posed:O.map(J=>{let j=L[J],nt=new Float32Array(tt.length*3);return tt.forEach((Mt,Qt)=>{nt[Qt*3]=j[Mt*3],nt[Qt*3+1]=j[Mt*3+1],nt[Qt*3+2]=j[Mt*3+2]}),nt})}}:{}}});h.set(M,X),_.nodes+=1,_.targets+=O.length,_.refinedTriangles+=Math.floor(y.geometry.index.count/3);for(let V of X){let W=V.positions.length/3;_.bytes+=W*O.length*(D?24:12),_.runtimeBytes+=W*O.length*(D?2:1)*pc}if(O.length){let V=new Float32Array(T.length),W=new Float32Array(T.length*O.length);for(let q=0;q<T.length;q+=1)V[q]=T[q]/r.hz,F[q]>=0&&(W[q*O.length+F[q]]=1);f.push({node:M,times:V,weights:W,targetCount:O.length})}}return _.normalsOmitted.length&&u.push(`${gc(_.normalsOmitted)} turns by less than ${mc}\xB0 over this clip, so its morph targets carry positions only and its shading rides the base normals`),{overrides:h,channels:f,warnings:u,stats:_}}d(yc,"buildTubeMorphTargets");function Pp(n,{basePositions:t,deltaPositions:e,grid:i,tolerance:s,posed:r,posedNormals:o}){let{bake:a,poses:c,keys:l,occurrenceId:u}=n;if(l.length<2)return 0;let h=0,f=0;for(let p=0;p<c.length;p+=i.multiple){for(;f+2<l.length&&l[f+1]<=p;)f+=1;let m=l[f],g=l[f+1],x=g===m?0:(p-m)/(g-m);Yn(qi,a,jt(c[p]),$i,r,o);let _=f>=1?e[f-1]:null,v=e[f];for(let y=0;y<t.length;y+=3){let b=0;for(let T=0;T<3;T+=1){let S=t[y+T]+(_?_[y+T]*(1-x):0)+(v?v[y+T]*x:0),M=r.array[y+T]-S;b+=M*M}b>h&&(h=b)}}if(h=Math.sqrt(h),h>s+.001)throw new Error(`morph fit for ${u} leaves ${h.toFixed(4)}mm between the baked targets and the clip's own deformation, past the ${s}mm it was fitted to`);return h}d(Pp,"verifyMorphFit");var Fr=Object.freeze(["clips"]);function Np(n){if(typeof Buffer<"u")return Buffer.from(n,"utf8").toString("base64");let t=new TextEncoder().encode(n),e="";for(let i of t)e+=String.fromCharCode(i);return btoa(e)}d(Np,"base64Utf8");async function Lp(n,{name:t="embedded animation"}={}){let e=String(n||""),i=`data:text/javascript;base64,${Np(e)}`;try{return await import(i)}catch(s){let r=s instanceof Error?s.message:String(s);throw new Error(`${t}: ${r}`)}}d(Lp,"importAnimationModule");function Dp(n,{name:t="embedded animation"}={}){let i=Object.keys(n||{}).filter(s=>s!=="default").filter(s=>!Fr.includes(s));if(i.length)throw new Error(`${t}: unknown export${i.length===1?"":"s"} ${i.join(", ")} \u2014 the renderer understands: ${Fr.join(", ")}`);if("default"in(n||{}))throw new Error(`${t}: a default export is not an animation-module export \u2014 use named exports (${Fr.join(", ")})`);return{clips:ja(n?.clips)}}d(Dp,"compileAnimationModule");async function vc(n,t={}){let[e]=await Promise.all([Lp(n,t),Za()]);return Dp(e,t)}d(vc,"compileAnimationSource");function Up(n){let t={},e=[],i=[],s=[],r=[],o={chord:void 0,angle:void 0};for(let a=0;a<n.length;a+=1){let c=n[a];if(!c.startsWith("--"))continue;let l=n[a+1],u=l===void 0||l.startsWith("--")?"true":l;u!=="true"&&(a+=1),c==="--format"?(e.push(u),s.push({chord:void 0,angle:void 0}),r.push(void 0)):c==="--out"?i.push(u):c==="--chord-tolerance"?(s.length?s[s.length-1]:o).chord=u:c==="--angle-tolerance"?(s.length?s[s.length-1]:o).angle=u:c==="--animation"?(r.length||It("--animation must follow the --format/--out pair it animates"),r[r.length-1]=u):t[c.slice(2)]=u}return{args:t,formats:e,outs:i,pairTolerances:s,pairAnimations:r,defaults:o}}d(Up,"parseArgs");function It(n){process.stdout.write(`${JSON.stringify({ok:!1,error:String(n)})}
`),process.exit(1)}d(It,"fail");function Fp(n,t,e,i){let s=String(e?.surfaceInput||""),r=String(e?.surfaceObject||""),o=Ie(s,i),a=ia(ir(o),{surfaceInput:s,surfaceObject:r,tessellationInput:o,tessellation:i});if(a)return{...a.component,partColor:a.partColor};let c=String(e?.surf||"");if(!c)throw new Error(`component ${t} has no surf payload`);let l=dn.readFileSync(pn.join(n,c)),{index:u,floats:h}=Vr(l.buffer.slice(l.byteOffset,l.byteOffset+l.byteLength)),f=Go(u,h,i),p=Array.isArray(u.partColor)?u.partColor:null;return ua(o,ta(f,{surfaceInput:s,surfaceObject:r,tessellation:i,partColor:p,edgeClasses:Qo(u)})),{...f,partColor:p}}d(Fp,"tessellationForComponent");var{args:Jn,formats:Or,outs:Ac,pairTolerances:Mc,pairAnimations:bc,defaults:Sc}=Up(process.argv.slice(2)),Yi=String(Jn["package-dir"]||"");(!Yi||!pn.isAbsolute(Yi))&&It("--package-dir must be an absolute render-package directory");(!Or.length||Or.length!==Ac.length)&&It("--format and --out must be given as one or more ordered pairs");var Be=Or.map((n,t)=>{let e=Mc[t].chord??Sc.chord,i=Mc[t].angle??Sc.angle,s={...Ct};e!==void 0&&(s.chordTolerance=Number(e)),i!==void 0&&(s.angleTolerance=Number(i));let r=null;if(bc[t]!==void 0){try{r=JSON.parse(String(bc[t]))}catch(o){It(`--animation must be a JSON object: ${o?.message||o}`)}(!r||typeof r!="object"||Array.isArray(r))&&It("--animation must be a JSON object")}return{format:String(n).toLowerCase(),out:String(Ac[t]),options:s,animation:r,groupKey:`${s.chordTolerance}:${s.angleTolerance}`}});for(let n of Be)(!n.out||!pn.isAbsolute(n.out))&&It("--out must be an absolute output path"),hr.includes(n.format)||It(`--format must be one of ${hr.join(", ")}`),(!(n.options.chordTolerance>0)||!(n.options.angleTolerance>0))&&It("tolerances must be positive numbers"),n.animation&&n.format!=="glb"&&It(`${n.format} carries no animation: only glb does`),n.animation&&!String(n.animation.clip||"").trim()&&It("--animation must name a clip");new Set(Be.map(n=>n.out)).size!==Be.length&&It("--out paths must be distinct");var Op=String(Jn.name||pn.basename(Be[0].out).replace(/\.[^.]+$/,"")||"model"),Zi=Jn["default-color"]?String(Jn["default-color"]):null;Zi!==null&&!/^#[0-9a-fA-F]{6}$/.test(Zi)&&It("--default-color must be #rrggbb");var Tc=String(Jn["animation-source"]||"");Be.some(n=>n.animation)&&!Tc&&It("--animation needs --animation-source: the clips live in the document sidecar");async function Bp(n){let t=dn.readFileSync(n,"utf8");return(await vc(t,{name:"embedded animation"})).clips}d(Bp,"loadClips");function zp(n,t,e){let i=String(n.animation.clip),s=tc(t,i);if(!s){let a=Qa(t).map(c=>c.id);throw new Error(a.length?`Unknown animation clip: ${i}. This model declares: ${a.join(", ")}`:`Unknown animation clip: ${i}. This model declares no animation clips`)}let r=sc(n.animation,s,{label:"animation"}),o=uc(e,s,r,{drop:Array.isArray(n.animation.drop)?n.animation.drop:[],deform:n.animation.deform});return{clip:s,plan:r,sampled:o}}d(zp,"sampleJobAnimation");try{let n=JSON.parse(dn.readFileSync(pn.join(Yi,"assembly.json"),"utf8")),t=n.components||{},e=new Set((n.occurrences||[]).map(o=>String(o.component||""))),i=Be.some(o=>o.animation)?await Bp(Tc):null,s=new Map;Be.forEach((o,a)=>{s.has(o.groupKey)||s.set(o.groupKey,{options:o.options,members:[]}),s.get(o.groupKey).members.push({job:o,index:a})});let r=[];for(let o of s.values()){let a=new Map;for(let u of e){if(!t[u])throw new Error(`descriptor names unknown component ${u}`);a.set(u,Fp(Yi,u,t[u],o.options))}let c=Zi?{defaultColor:Zi.toLowerCase()}:{},l=null;for(let{job:u,index:h}of o.members){let f,p=null,m=null;if(u.animation){let{plan:_,sampled:v}=zp(u,i,n),y=yc(n,a,v.deformations,{toleranceMm:u.animation.deformTolerance,grid:v.grid,clipId:v.name,...c.defaultColor?{defaultColor:c.defaultColor}:{}});f=xr(n,a,{...c,perOccurrence:!0,hiddenOccurrenceIds:v.statics.hidden,occurrenceOpacity:v.statics.opacity,occurrenceOverrides:y.overrides}),p=dc(fc(v,y.channels),new Set(f.primitives.map(b=>b.node).filter(Boolean))),m={clip:p.name,fps:_.fps,samples:_.frameCount,seconds:_.seconds,start:_.start,channels:p.channels.length,...y.stats?{deform:{mode:"morph",nodes:y.stats.nodes,targets:y.stats.targets,bytes:y.stats.bytes,runtimeBytes:y.stats.runtimeBytes,refinedTriangles:y.stats.refinedTriangles,deviationMm:Number(y.stats.deviationMm.toFixed(4)),toleranceMm:y.stats.toleranceMm,fitGridHz:v.grid.hz}}:{},warnings:[..._.warnings,...p.warnings,...y.warnings]}}else l=l||xr(n,a,c),f=l;if(!f.triangleCount)throw new Error("tree produced no triangles");let{body:g}=wa(f,u.format,{name:Op,animation:p});dn.mkdirSync(pn.dirname(u.out),{recursive:!0});let x=`${u.out}.${process.pid}.tmp`;dn.writeFileSync(x,g),dn.renameSync(x,u.out),r[h]={path:u.out,format:u.format,triangleCount:f.triangleCount,...m?{animation:m}:{}}}}process.stdout.write(`${JSON.stringify({ok:!0,files:r})}
`)}catch(n){It(n?.message||n)}
/*! Bundled license information:

three/build/three.core.js:
three/build/three.module.js:
  (**
   * @license
   * Copyright 2010-2026 Three.js Authors
   * SPDX-License-Identifier: MIT
   *)
*/
