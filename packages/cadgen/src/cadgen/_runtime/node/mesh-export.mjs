#!/usr/bin/env node
var kr=Object.defineProperty;var d=(n,t)=>kr(n,"name",{value:t,configurable:!0});var _n=(n,t)=>()=>(n&&(t=n(n=0)),t);var Rc=(n,t)=>{for(var e in t)kr(n,e,{get:t[e],enumerable:!0})};function Ln(n,t,e){let i=n*n,s=i*i,r=nf+i*(sf+i*rf)+i*s*(of+i*af),o=i*n;return e?n-(i*(.5*t-o*r)-t-o*Co):n+o*(Co+i*r)}function Dn(n,t){let e=n*n,i=e*e,s=e*(cf+e*(lf+e*uf))+i*i*(hf+e*(ff+e*df)),r=.5*e,o=1-r;return o+(1-o-r+(e*s-n*t))}function Lo(n){let t=Math.trunc(n*pf+(n>0?.5:-.5)),e=t,i=n-e*mf,s=e*gf,r=i;s=e*_f,i=r-s,s=e*xf-(r-i-s),r=i,s=e*yf,i=r-s,s=e*vf-(r-i-s);let o=i-s;return Ci.n=t,Ci.r=o,Ci.tail=i-o-s,Ci}function Do(n){throw new RangeError(`deterministic sin/cos is defined for |x| < ${qs} radians, got ${n}`)}function ht(n){let t=Math.abs(n);if(!Number.isFinite(n))return NaN;if(t<=en)return t<No?n:Ln(n,0,!1);t<qs||Do(n);let{n:e,r:i,tail:s}=Lo(n);switch(e&3){case 0:return Ln(i,s,!0);case 1:return Dn(i,s);case 2:return-Ln(i,s,!0);default:return-Dn(i,s)}}function rt(n){let t=Math.abs(n);if(!Number.isFinite(n))return NaN;if(t<=en)return t<No?1:Dn(n,0);t<qs||Do(n);let{n:e,r:i,tail:s}=Lo(n);switch(e&3){case 0:return Dn(i,s);case 1:return-Ln(i,s,!0);case 2:return-Dn(i,s);default:return Ln(i,s,!0)}}function Xs(n){return Un.setFloat64(0,n),Un.getInt32(0)}function tn(n){return Xs(n)>>>31===1}function Sf(n){return Un.setFloat64(0,n),Un.setUint32(4,0),Un.getFloat64(0)}function Ws(n){let t=n*(Mf+n*(bf+n*(wf+n*(Af+n*(Tf+n*Ef))))),e=1+n*(Cf+n*(Rf+n*(If+n*Pf)));return t/e}function Uo(n){let t=Math.abs(n);if(!(t<=1))return NaN;if(t===1)return n>0?0:_e+2*Ri;if(t<.5)return t<6938893903907228e-33?Ce+Ri:Ce-(n-(Ri-n*Ws(n*n)));if(n<0){let o=(1+n)*.5,a=Math.sqrt(o);return _e-2*(a+(Ws(o)*a-Ri))}let e=(1-n)*.5,i=Math.sqrt(e),s=Sf(i),r=(e-s*s)/(i+s);return 2*(s+(Ws(e)*i+r))}function Po(n){if(Number.isNaN(n))return NaN;let t=tn(n),e=Math.abs(n),i;if(e>=7378697629483821e4){let l=Ro[3]+Io[3];return t?-l:l}if(e<.4375){if(e<1862645149230957e-24)return n;i=-1,e=n}else e<.6875?(i=0,e=(2*e-1)/(2+e)):e<1.1875?(i=1,e=(e-1)/(e+1)):e<2.4375?(i=2,e=(e-1.5)/(1+1.5*e)):(i=3,e=-1/e);let s=e*e,r=s*s,o=s*(Zt[0]+r*(Zt[2]+r*(Zt[4]+r*(Zt[6]+r*(Zt[8]+r*Zt[10]))))),a=r*(Zt[1]+r*(Zt[3]+r*(Zt[5]+r*(Zt[7]+r*Zt[9]))));if(i<0)return e-e*(o+a);let c=Ro[i]-(e*(o+a)-Io[i]-e);return t?-c:c}function $s(n,t){if(Number.isNaN(t)||Number.isNaN(n))return NaN;if(t===1)return Po(n);let e=(tn(n)?1:0)|(tn(t)?2:0);if(n===0)return e<2?n:e===2?_e:-_e;if(t===0)return tn(n)?-Ce:Ce;if(!Number.isFinite(t))return Number.isFinite(n)?[0,-0,_e,-_e][e]:[en,-en,3*en,-3*en][e];if(!Number.isFinite(n))return tn(n)?-Ce:Ce;let i=(Xs(n)&2147483647)-(Xs(t)&2147483647)>>20,s;switch(i>60?s=Ce+.5*Hs:tn(t)&&i<-60?s=0:s=Po(Math.abs(n/t)),e){case 0:return s;case 1:return-s;case 2:return _e-(s-Hs);default:return s-Hs-_e}}var Co,nf,sf,rf,of,af,cf,lf,uf,hf,ff,df,en,pf,mf,gf,_f,xf,yf,vf,No,qs,Ci,Un,_e,Hs,Ce,Ri,Mf,bf,wf,Af,Tf,Ef,Cf,Rf,If,Pf,Ro,Io,Zt,Fn=_n(()=>{Co=-.16666666666666632,nf=.00833333333332249,sf=-.0001984126982985795,rf=27557313707070068e-22,of=-25050760253406863e-24,af=158969099521155e-24,cf=.0416666666666666,lf=-.001388888888887411,uf=2480158728947673e-20,hf=-27557314351390663e-23,ff=2087572321298175e-24,df=-11359647557788195e-27,en=.7853981633974483,pf=.6366197723675814,mf=1.5707963267341256,gf=6077100506506192e-26,_f=6077100506303966e-26,xf=20222662487959506e-37,yf=20222662487111665e-37,vf=84784276603689e-45,No=3725290298461914e-24,qs=524288;d(Ln,"kernelSin");d(Dn,"kernelCos");Ci={n:0,r:0,tail:0};d(Lo,"reducePio2");d(Do,"outOfRange");d(ht,"sin");d(rt,"cos");Un=new DataView(new ArrayBuffer(8));d(Xs,"highWord");d(tn,"signBit");d(Sf,"dropLowWord");_e=3.141592653589793,Hs=12246467991473532e-32,Ce=1.5707963267948966,Ri=6123233995736766e-32,Mf=.16666666666666666,bf=-.3255658186224009,wf=.20121253213486293,Af=-.04005553450067941,Tf=.0007915349942898145,Ef=3479331075960212e-20,Cf=-2.403394911734414,Rf=2.0209457602335057,If=-.6882839716054533,Pf=.07703815055590194;d(Ws,"acosR");d(Uo,"acos");Ro=[.4636476090008061,.7853981633974483,.982793723247329,1.5707963267948966],Io=[22698777452961687e-33,3061616997868383e-32,13903311031230998e-33,6123233995736766e-32],Zt=[.3333333333333293,-.19999999999876483,.14285714272503466,-.11111110405462356,.09090887133436507,-.0769187620504483,.06661073137387531,-.058335701337905735,.049768779946159324,-.036531572744216916,.016285820115365782];d(Po,"atan");d($s,"atan2")});function zi(n,t,e){if(!n)return null;let i=n.userData.cadTubeShader;if(!i){let r=n.onBeforeCompile,o=n.customProgramCacheKey;i=n.userData.cadTubeShader={stages:{}},n.onBeforeCompile=function(a,c){r.call(this,a,c);for(let u of Ia){let h=i.stages[u];h&&(Object.assign(a.uniforms,h.uniforms),h.apply(a,i.stages))}let l=`#include <common>
varying vec3 ${ve};`;a.vertexShader=a.vertexShader.replace("#include <common>",l),a.fragmentShader=a.fragmentShader.replace("#include <common>",l)},n.customProgramCacheKey=function(){let a=Ia.filter(c=>i.stages[c]).join("+");return`${o.call(this)}:cad-tube:${a}`},n.needsUpdate=!0}let s=i.stages[t];return s||(s=i.stages[t]=e(),n.needsUpdate=!0),s}var ve,Wn,Bi,Ia,ki=_n(()=>{ve="vCadTubeMaterial",Wn="cadTubeMaterial",Bi="braid",Ia=["gpu",Bi];d(zi,"ensureTubeMaterialStage")});function Fd(n,t){t["gpu"]||(n.vertexShader=n.vertexShader.replace("#include <common>",`#include <common>
attribute vec3 ${Wn};`).replace("#include <begin_vertex>",`#include <begin_vertex>
${ve} = ${Wn};`)),n.fragmentShader=n.fragmentShader.replace("#include <common>",`#include <common>
${Ud}`).replace("#include <color_fragment>",`#include <color_fragment>
float cadBraidRelief = cadBraidHeight();
diffuseColor.rgb *= 1.0 + 0.22 * cadBraidRelief / max(cadBraidParameters.y, 0.000001);`).replace("#include <normal_fragment_maps>",`#include <normal_fragment_maps>
if (cadBraidEnabled > 0.5) normal = cadBraidNormal(-vViewPosition, normal, cadBraidRelief);`)}function Pa(n,t,e){if(!t||!e&&!t.userData.cadTubeShader?.stages[Bi])return;let i=zi(t,Bi,()=>({uniforms:{cadBraidParameters:{value:new n.Vector3(1,0,8)},cadBraidEnabled:{value:0}},apply:Fd}));i.uniforms.cadBraidEnabled.value=e?1:0,e&&i.uniforms.cadBraidParameters.value.set(e.pitch,e.depth,e.strands)}var Ud,Na=_n(()=>{ki();Ud=`
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
`;d(Fd,"applyBraidStage");d(Pa,"applyTubeBraidMaterial")});function kd(n,t){let e=[];for(let o of n.segments){let a=o.kind==="bezier"?o.table:null,c=a?.length??(o.kind==="line"?2:Math.ceil(o.length/o.radius/Bd)+1);for(let l=0;l<c;l++){let u=a?.[l],h=u?u.s:o.length*l/(c-1),f=o.offset+h,p=u?.curvature?u:t(n,f),m={s:f,point:p.point,tangent:p.tangent,normal:p.normal,curvature:p.curvature};e.length&&f<=e.at(-1).s+1e-12?e[e.length-1]=m:e.push(m)}}let i=Math.max(2,Math.ceil(n.length/Od)+1),s=new Float32Array(i*16),r=0;for(let o=0;o<i;o++){let a=n.length*o/(i-1);for(;r<e.length-2&&e[r+1].s<a;)r++;let c=e[r],l=e[r+1],u=l.s-c.s,h=Math.max(0,Math.min(1,(a-c.s)/u)),f=1-h,p=2*h*h*h-3*h*h+1,m=h*h*h-2*h*h+h,g=-2*h*h*h+3*h*h,_=h*h*h-h*h,x=f*c.tangent[0]+h*l.tangent[0],v=f*c.tangent[1]+h*l.tangent[1],y=f*c.tangent[2]+h*l.tangent[2],M=Math.sqrt(x*x+v*v+y*y);x/=M,v/=M,y/=M;let A=f*c.normal[0]+h*l.normal[0],b=f*c.normal[1]+h*l.normal[1],S=f*c.normal[2]+h*l.normal[2],w=A*x+b*v+S*y;A-=w*x,b-=w*v,S-=w*y;let R=Math.sqrt(A*A+b*b+S*S);A/=R,b/=R,S/=R;let I=o*16;for(let N=0;N<3;N++)s[I+N]=p*c.point[N]+m*u*c.tangent[N]+g*l.point[N]+_*u*l.tangent[N],s[I+12+N]=f*c.curvature[N]+h*l.curvature[N];s.set([x,v,y],I+4),s.set([A,b,S],I+8)}return{data:s,count:i}}function Gd(n){n.vertexShader=n.vertexShader.replace("#include <common>",`#include <common>
${Vd}`).replace("#include <beginnormal_vertex>",`#include <beginnormal_vertex>
cadEvaluateTube();
if (cadTubeGpuEnabled > 0.5) objectNormal = cadGpuNormal;`).replace("#include <begin_vertex>",`#include <begin_vertex>
cadEvaluateTube();
if (cadTubeGpuEnabled > 0.5) transformed = cadGpuPoint;
${ve} = cadTubeMaterialCoordinates();`)}function yr(n,t){if(!n)return;let e=zi(n,"gpu",()=>({uniforms:t,apply:Gd}));if(e.uniforms!==t)for(let[i,s]of Object.entries(t))e.uniforms[i]?e.uniforms[i].value=s.value:(e.uniforms[i]=s,n.needsUpdate=!0)}function Sr(n){let t=n?.tubeGpuState;t&&(t.uniforms.cadTubeGpuEnabled.value=0,t.active=!1,n.mesh.userData.cadBeforeRaycast=null)}function Mr(n){let t=n?.tubeGpuState;if(t?.active)for(let e of[n.mesh,n.silhouette,n.ghostMesh])e&&yr(e.material,t.uniforms)}function Hd(n,t,e,i,s){let r=e.mapping,o=zd,a=Math.ceil(r.values.length/4/o),c=r.values;r.gpu||(c=new Float32Array(o*a*4),c.set(r.values));let l=new n.DataTexture(c,o,a,n.RGBAFormat,n.FloatType);l.needsUpdate=!0;let u=r.gpu?r.indices:new Float32Array(r.indices);e.geometry.setAttribute("cadTubeMappingIndex",new n.BufferAttribute(u,1));let h=0;for(let f=0;f<r.values.length;f+=8){let p=r.values[f+1],m=r.values[f+2],g=r.values[f+3];h=Math.max(h,Math.sqrt(p*p+m*m+g*g))}return{mapping:r,mappingTexture:l,radius:h,active:!0,uniforms:{cadTubeMappingTexture:{value:l},cadTubeFrameTexture:{value:null},cadTubeMappingSize:{value:new n.Vector2(o,a)},cadTubeFrameCount:{value:0},cadTubeRestLength:{value:i.rest.length},cadTubeGpuEnabled:{value:1},cadTubeGpuParameters:{value:new n.Vector3},cadTubeGpuInverse:{value:s.clone()},cadTubeGpuNormalMatrix:{value:new n.Matrix3().getNormalMatrix(s)}}}}function Wd(n,t,e,i,s,r,o){let a=i.frames;t.mesh.userData.cadBeforeRaycast=c=>{if(!i.active)return!0;let l=c.ray.clone().applyMatrix4(t.mesh.matrixWorld.clone().invert());if(!l.intersectsBox(e.geometry.boundingBox))return!1;let u=l.clone().applyMatrix4(r.clone().invert()),h=new n.Vector3,f=new n.Vector3,p=Math.max(1,Math.floor((a.count-1)/s.path.length)),m=!1;for(let g=0;g<a.count-1;g+=p){let _=Math.min(g+p,a.count-1);h.fromArray(a.data,g*16),f.fromArray(a.data,_*16);let x=i.radius+(_-g)*s.path.length/(a.count-1)/2+1e-4;if(u.distanceSqToSegment(h,f)<=x*x){m=!0;break}}return m?(i.cpuSpec!==s.pathSpec&&(o(),i.cpuSpec=s.pathSpec),!0):!1}}function La(n,t,e,i,s,r,o){if(!t.gpuTubeDeformationAllowed||i.path.length>vr)return!1;let a=t.tubeGpuState;(!a||a.mapping!==e.mapping)&&(a?.mappingTexture.dispose(),a?.frameTexture?.dispose(),a=t.tubeGpuState=Hd(n,t,e,i,s)),a.cleanupInstalled||(e.geometry.addEventListener("dispose",()=>{a.mappingTexture.dispose(),a.frameTexture?.dispose()}),a.cleanupInstalled=!0);let c=kd(i.path,r);!a.frameTexture||a.frameTexture.image.height!==c.count?(a.frameTexture?.dispose(),a.frameTexture=new n.DataTexture(c.data,4,c.count,n.RGBAFormat,n.FloatType)):a.frameTexture.image.data.set(c.data),a.frameTexture.needsUpdate=!0,a.frames=c,a.active=!0,a.cpuSpec=null;let l=a.uniforms;l.cadTubeFrameTexture.value=a.frameTexture,l.cadTubeFrameCount.value=c.count,l.cadTubeGpuEnabled.value=1,l.cadTubeGpuParameters.value.set(i.twistDeg*Math.PI/180,i.path.length/i.rest.length,0),l.cadTubeGpuInverse.value.copy(s),l.cadTubeGpuNormalMatrix.value.getNormalMatrix(s),Mr(t),t.mesh.customDepthMaterial||(t.mesh.customDepthMaterial=new n.MeshDepthMaterial({depthPacking:n.RGBADepthPacking}),t.mesh.customDistanceMaterial=new n.MeshDistanceMaterial,t.mesh.material.addEventListener("dispose",()=>{t.mesh.customDepthMaterial?.dispose(),t.mesh.customDistanceMaterial?.dispose()})),yr(t.mesh.customDepthMaterial,l),yr(t.mesh.customDistanceMaterial,l);let u=new n.Box3;for(let h of i.path.segments)u.expandByPoint(new n.Vector3().fromArray(h.bounds.min)),u.expandByPoint(new n.Vector3().fromArray(h.bounds.max));return u.expandByScalar(a.radius+1e-4),t.partBounds={min:u.min.toArray(),max:u.max.toArray()},e.geometry.boundingBox=u.clone().applyMatrix4(s),e.geometry.boundingSphere=e.geometry.boundingBox.getBoundingSphere(new n.Sphere),Wd(n,t,e,a,i,s,o),!0}var vr,Od,Bd,zd,Vd,Da=_n(()=>{ki();vr=819.1,Od=.1,Bd=.01,zd=1024;d(kd,"buildGpuTubeFrames");Vd=`
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
`;d(Gd,"applyGpuStage");d(yr,"patchMaterial");d(Sr,"disableGpuTube");d(Mr,"syncGpuTubeMaterials");d(Hd,"createGpuState");d(Wd,"installRaycastGuard");d(La,"applyGpuTube")});var Ka={};Rc(Ka,{applyRecordTubeDeformation:()=>cp,applyTubeDeformationToLineObject:()=>Cr,compileDeformation:()=>jt,compileTubePath:()=>Ya,normalizeTubeDeformation:()=>np,poseTubeBake:()=>Zn,prepareTubeBake:()=>Rr,projectTubePath:()=>$n,restMappingKey:()=>Yn,sameTubeDeformation:()=>Fe,sameTubeRestShape:()=>Tr,sampleTubePath:()=>hn});function qd(n,t){let e=0;for(let i=0;i<3;i++)e+=Math.max(n.min[i]-t[i],0,t[i]-n.max[i])**2;return e}function ft(n){throw new Error(`animation deformTube: ${n}`)}function De(n,t){return(!Array.isArray(n)||n.length!==3||!n.every(Number.isFinite))&&ft(`${t} must be a finite vec3`),n.slice()}function an(n,t){let e=Wt(n);return e<Ue&&ft(`${t} must be nonzero`),At(n,1/e)}function Vi(n,t,e){(!n||typeof n!="object"||Array.isArray(n))&&ft(`${e} must be an object`);for(let i of Object.keys(n))t.includes(i)||ft(`unknown ${e} key ${JSON.stringify(i)}; expected ${t.join(", ")}`)}function Gi(n,t,e){let i=rt(e),s=ht(e);return ln(ln(At(n,i),At(Se(t,n),s)),At(t,dt(t,n)*(1-i)))}function qn(n,t){let e=1-t;return[0,1,2].map(i=>e*e*e*n[0][i]+3*e*e*t*n[1][i]+3*e*t*t*n[2][i]+t*t*t*n[3][i])}function un(n,t){let e=1-t;return[0,1,2].map(i=>3*e*e*(n[1][i]-n[0][i])+6*e*t*(n[2][i]-n[1][i])+3*t*t*(n[3][i]-n[2][i]))}function Ga(n,t){return[0,1,2].map(e=>6*(1-t)*(n[2][e]-2*n[1][e]+n[0][e])+6*t*(n[3][e]-2*n[2][e]+n[1][e]))}function Xn(n,t,e){let i=(t+e)/2,s=(e-t)/2,r=0;for(let o=0;o<5;o++){let a=i+s*$d[o],c=1-a,l=3*c*c,u=6*c*a,h=3*a*a,f=l*(n[1][0]-n[0][0])+u*(n[2][0]-n[1][0])+h*(n[3][0]-n[2][0]),p=l*(n[1][1]-n[0][1])+u*(n[2][1]-n[1][1])+h*(n[3][1]-n[2][1]),m=l*(n[1][2]-n[0][2])+u*(n[2][2]-n[1][2])+h*(n[3][2]-n[2][2]);r+=Yd[o]*Math.sqrt(f*f+p*p+m*m)}return s*r}function Ha(n,t,e){let i=Se(t,e),s=Wt(i),r=dt(t,e);return s<Ue?(r<0&&ft("path tangent reverses"),n.slice()):Gi(n,At(i,1/s),$s(s,r))}function Zd(n){let t=[{t:0,s:0,tangent:n.tangent,normal:n.normal}],e=d((i,s,r=0)=>{let o=(i+s)/2,a=Xn(n.points,i,s),c=Xn(n.points,i,o),l=Xn(n.points,o,s),u=an(un(n.points,i),"Bezier tangent"),h=an(un(n.points,s),"Bezier tangent");if(r<20&&(s-i>1/128||Math.abs(a-c-l)>1e-9||dt(u,h)<.9999)){e(i,o,r+1),e(o,s,r+1);return}dt(u,h)<.99&&ft("Bezier has a cusp or unresolved tangent");let f=t.at(-1);t.push({t:s,s:f.s+c+l,tangent:h,normal:Ha(f.normal,f.tangent,h)})},"append");e(0,1),n.table=t,n.length=t.at(-1).s}function Wa(n,t){let e=n.table,i=0,s=e.length-1;for(;s-i>1;){let c=i+s>>1;e[c].s<t?i=c:s=c}let r=e[i],o=e[s],a=r.t+(o.t-r.t)*(t-r.s)/(o.s-r.s);for(let c=0;c<3;c++){let l=r.s+Xn(n.points,r.t,a)-t;if(Math.abs(l)<1e-11)break;a=Math.max(r.t,Math.min(o.t,a-l/Wt(un(n.points,a))))}return{t:a,lower:r}}function Xa(n,t){return n.kind==="line"?ln(n.start,At(n.tangent,t)):n.kind==="bezier"?qn(n.points,Wa(n,t).t):ln(n.center,Gi(n.radial,n.axis,t/n.radius*n.sign))}function Ar(n,t){if(n.kind==="bezier"){let{t:a,lower:c}=Wa(n,t),l=un(n.points,a),u=Wt(l),h=At(l,1/u),f=Ha(c.normal,c.tangent,h),p=Ga(n.points,a),m=At(Bt(p,At(h,dt(p,h))),1/(u*u));return{point:qn(n.points,a),tangent:h,normal:f,binormal:Se(h,f),curvature:m}}let e=n.kind==="arc"?t/n.radius*n.sign:0,i=e?Gi(n.tangent,n.axis,e):n.tangent,s=e?Gi(n.normal,n.axis,e):n.normal,r=Xa(n,t),o=n.kind==="arc"?At(Bt(n.center,r),1/(n.radius*n.radius)):[0,0,0];return{point:r,tangent:i,normal:s,binormal:Se(i,s),curvature:o}}function qa(n){return Vi(n,["segments","normal"],"path"),(!Array.isArray(n.segments)||!n.segments.length)&&ft("path needs at least one segment"),n.normal===void 0&&ft("path normal is required: give both the rest and the posed path an explicit transverse normal seed"),De(n.normal,"normal")}function $a(n,t){return Vi(n,Oa[n.kind]||Oa.arc,`segment ${t}`),n.kind==="line"?{kind:"line",start:De(n.start,"start"),end:De(n.end,"end")}:n.kind==="arc"?{kind:"arc",center:De(n.center,"center"),axis:De(n.axis,"axis"),start:De(n.start,"start"),sweepDeg:n.sweepDeg}:n.kind==="bezier"?((!Array.isArray(n.points)||n.points.length!==4)&&ft("Bezier points must contain four vec3 control points"),{kind:"bezier",points:n.points.map(e=>De(e,"Bezier point"))}):ft(`unknown segment kind ${JSON.stringify(n.kind)}; expected line, arc, bezier`)}function Jd(n,t){let e=$a(n,t);if(e.kind==="line"){let{start:s,end:r}=e,o=Bt(r,s);return{kind:"line",start:s,end:r,tangent:an(o,"line"),length:Wt(o),radius:1/0}}if(e.kind==="arc"){let{center:s,start:r}=e,o=an(e.axis,"axis"),a=Bt(r,s),c=Wt(a),l=e.sweepDeg*Math.PI/180;(!Number.isFinite(l)||Math.abs(l)<Ue||Math.abs(l)>2*Math.PI+Ue)&&ft("arc sweepDeg must be nonzero and at most 360 degrees"),(c<Ue||Math.abs(dt(a,o))>Ue*Math.max(1,c))&&ft("arc start must be in its normal plane with nonzero radius");let u=Math.sign(l),h=At(Se(o,a),u/c),f={kind:"arc",center:s,start:r,axis:o,radial:a,radius:c,sign:u,tangent:h,length:c*Math.abs(l)};return f.end=Xa(f,f.length),f}let i=e.points;return{kind:"bezier",points:i,start:i[0],end:i[3],tangent:an(un(i,0),"Bezier tangent"),radius:1/0}}function Kd(n){return Math.min(...n.table.map(t=>{let e=un(n.points,t.t),i=Ga(n.points,t.t),s=Wt(e);return s*s*s/Wt(Se(e,i))}))}function jd(n){if(n.kind==="arc")return{min:n.center.map(e=>e-n.radius),max:n.center.map(e=>e+n.radius)};let t=n.kind==="bezier"?n.points:[n.start,n.end];return{min:[0,1,2].map(e=>Math.min(...t.map(i=>i[e]))),max:[0,1,2].map(e=>Math.max(...t.map(i=>i[e])))}}function Ya(n){let t=qa(n),e=0,i=null,s=n.segments.map((o,a)=>{let c=Jd(o,a);if(i){Wt(Bt(i.end,c.start))>1e-5&&ft(`path discontinuity before segment ${a}`);let l=Ar(i,i.length);dt(l.tangent,c.tangent)<1-1e-7&&ft(`path is not tangent-continuous before segment ${a}`),c.normal=l.normal}else c.normal=an(Bt(t,At(c.tangent,dt(t,c.tangent))),"path normal transverse to first tangent");return c.kind==="bezier"&&Zd(c),c.offset=e,c.bounds=jd(c),e+=c.length,i=c,c}),r={segments:s,length:e};return Object.defineProperty(r,"minRadius",{get(){for(let o of s)o.kind==="bezier"&&o.radius===1/0&&(o.radius=Kd(o));return Math.min(...s.map(o=>o.radius))}}),r}function hn(n,t){Number.isFinite(t)||ft("path distance must be finite");let e=t<=0?n.segments[0]:n.segments.find(o=>t<=o.offset+o.length)||n.segments.at(-1),i=t-e.offset,s=Math.max(0,Math.min(e.length,i)),r=Ar(e,s);return i!==s&&(r.point=ln(r.point,At(r.tangent,i-s))),r}function Qd(n){if(!n.tablePoints){let t=new Float64Array(n.table.length*3);n.table.forEach((e,i)=>{let s=qn(n.points,e.t);t[i*3]=s[0],t[i*3+1]=s[1],t[i*3+2]=s[2]}),n.tablePoints=t}return n.tablePoints}function tp(n,t){let e=Qd(n),i=0,s=1/0;for(let l=0;l<n.table.length;l++){let u=(t[0]-e[l*3])**2+(t[1]-e[l*3+1])**2+(t[2]-e[l*3+2])**2;u<s&&(s=u,i=l)}let r=n.table[Math.max(0,i-1)].t,o=n.table[Math.min(n.table.length-1,i+1)].t;for(let l=0;l<35;l++){let u=r+(o-r)/3,h=o-(o-r)/3;Fa(t,qn(n.points,u))<Fa(t,qn(n.points,h))?o=h:r=u}let a=(r+o)/2,c=n.table.findLast(l=>l.t<=a)||n.table[0];return c.s+Xn(n.points,c.t,a)}function ep(n,t){let e=Bt(t,n.center),i=$s(dt(Se(n.radial,e),n.axis),dt(n.radial,e))*n.sign;i<0&&(i+=2*Math.PI);let s=i*n.radius;return s>n.length?Wt(Bt(t,n.start))<Wt(Bt(t,n.end))?0:n.length:s}function $n(n,t){let e=null,i=n.segments.map(s=>({segment:s,bound:qd(s.bounds,t)})).sort((s,r)=>s.bound-r.bound);for(let{segment:s,bound:r}of i){if(e&&r>e.distanceSq+1e-12)break;let o;s.kind==="line"?o=dt(Bt(t,s.start),s.tangent):s.kind==="bezier"?o=tp(s,t):o=ep(s,t),o=Math.max(0,Math.min(s.length,o));let a=Ar(s,o),c=Bt(t,a.point),l=dt(c,c);(!e||l<e.distanceSq)&&(e={distance:s.offset+o,distanceSq:l,transverse:[dt(c,a.normal),dt(c,a.binormal)],axial:dt(c,a.tangent)})}return e}function Ba(n){let t=JSON.stringify(n),e=on.get(t);return e?on.delete(t):e=Ya(n),on.set(t,e),on.size>Xd&&on.delete(on.keys().next().value),e}function za(n){return{normal:qa(n),segments:n.segments.map((t,e)=>$a(t,e))}}function cn(n,t){if(n===t)return!0;if(Array.isArray(n))return!Array.isArray(t)||n.length!==t.length?!1:n.every((e,i)=>cn(e,t[i]));if(n&&typeof n=="object"){if(!t||typeof t!="object"||Array.isArray(t))return!1;let e=Object.keys(n);return e.length===Object.keys(t).length&&e.every(i=>cn(n[i],t[i]))}return!1}function Fe(n,t){return n===t?!0:!n||!t?!1:n.twistDeg===t.twistDeg&&n.maxSegmentLength===t.maxSegmentLength&&cn(n.braid,t.braid)&&cn(n.restSpec,t.restSpec)&&cn(n.pathSpec,t.pathSpec)}function Tr(n,t){return n.maxSegmentLength===t.maxSegmentLength&&cn(n.restSpec,t.restSpec)}function jt(n){return{...n,rest:Ba(n.restSpec),path:Ba(n.pathSpec)}}function np(n){Vi(n,["rest","path","twistDeg","maxSegmentLength","braid"],"deformation");let t=n.twistDeg??0;Number.isFinite(t)||ft("twistDeg must be finite");let e=n.maxSegmentLength??1;(!Number.isFinite(e)||e<.05)&&ft("maxSegmentLength must be at least 0.05 mm");let i=null;if(n.braid){Vi(n.braid,["pitch","depth","strands"],"braid");let{pitch:s,depth:r,strands:o}=n.braid;Number.isFinite(s)&&s>0&&Number.isFinite(r)&&r>=0&&Number.isInteger(o)&&o>=2&&o<=64&&o%2===0||ft("braid needs positive pitch, nonnegative depth, and an even strand count from 2 to 64"),i={pitch:s,depth:r,strands:o}}return{restSpec:za(n.rest),pathSpec:za(n.path),twistDeg:t,maxSegmentLength:e,braid:i}}function ka(n,t,e){let i=[];for(let s=0;s<n.length;s++){let r=n[s],o=n[(s+1)%n.length],a=e?r[0]>=t:r[0]<=t,c=e?o[0]>=t:o[0]<=t;if(a&&i.push(r),a!==c){let l=(t-r[0])/(o[0]-r[0]);i.push(r.map((u,h)=>u+l*(o[h]-u)))}}return i.filter((s,r)=>!r||Math.abs(s[1]-i[r-1][1])+Math.abs(s[2]-i[r-1][2])+Math.abs(s[3]-i[r-1][3])>1e-10)}function ip(n,t,e,i,s){if(s>=e.length)return{geometry:t,sourceTriangles:null};let r=t.attributes.position,o=new n.Vector3,a=new Float64Array(r.count),c=new Map;for(let x=0;x<r.count;x++){let v=[r.getX(x),r.getY(x),r.getZ(x)].join(","),y=c.get(v);y===void 0&&(o.fromBufferAttribute(r,x).applyMatrix4(i),y=$n(e,o.toArray()).distance,c.set(v,y)),a[x]=y}c.clear();let l=t.index?.count??r.count;if(l%3)return{geometry:t.clone(),sourceTriangles:null};let u=Object.entries(t.attributes),h=Object.fromEntries(u.map(([x])=>[x,[]])),f=[],p=[],m=new Map,g=d(x=>t.index?t.index.getX(x):x,"index");for(let x=0;x<l;x+=3){let v=[g(x),g(x+1),g(x+2)],y=v.map(S=>a[S]),M=y.map((S,w)=>[S,...[0,1,2].map(R=>w===R?1:0)]),A=Math.floor(Math.min(...y)/s),b=Math.floor(Math.max(...y)/s);for(let S=A;S<=b;S++){let w=ka(ka(M,S*s,!0),(S+1)*s,!1);for(let R=1;R<w.length-1;R++){let I=[w[0],w[R],w[R+1]],N=Bt(I[1].slice(1),I[0].slice(1)),C=Bt(I[2].slice(1),I[0].slice(1));if(!(Wt(Se(N,C))<1e-12)){f.push(x/3),f.length>Ua&&ft(`refined tube exceeds ${Ua} triangles; increase maxSegmentLength`);for(let T of I){let P=v.map((E,L)=>[E,Math.round(T[L+1]*1e10)]).filter(([,E])=>E).sort((E,L)=>E[0]-L[0]).map(E=>E.join(":")).join(","),D=m.get(P);if(D===void 0){D=m.size,m.set(P,D);for(let[E,L]of u)for(let F=0;F<L.itemSize;F++)h[E].push(v.reduce((O,U,B)=>O+T[B+1]*L.getComponent(U,F),0))}p.push(D)}}}}}let _=t.clone();for(let[x,v]of u)_.setAttribute(x,new n.Float32BufferAttribute(h[x],v.itemSize));return _.setIndex(p),_.clearGroups(),{geometry:_,sourceTriangles:new Uint32Array(f)}}function Za(n,t,e,i,s,r=!1){let o=[],a=r?new Float32Array(t.count):new Uint32Array(t.count),c=new Map,l=new n.Vector3,u=new n.Matrix3().getNormalMatrix(s),h=new n.Vector3;for(let p=0;p<t.count;p++){let m=[t.getX(p),t.getY(p),t.getZ(p),...e?[e.getX(p),e.getY(p),e.getZ(p)]:[]].join(","),g=c.get(m);if(g!==void 0){a[p]=g;continue}let _=o.length/8;c.set(m,_),a[p]=_,l.fromBufferAttribute(t,p).applyMatrix4(s);let x=$n(i,[l.x,l.y,l.z]),v=hn(i,x.distance),y=ln(At(v.normal,x.transverse[0]),At(v.binormal,x.transverse[1])),M=1-dt(v.curvature,y);M<=Ue&&ft("rest mesh crosses the centerline curvature radius");let A=[0,0,0];if(e){h.fromBufferAttribute(e,p).applyNormalMatrix(u);let b=[h.x,h.y,h.z];A=[dt(b,v.normal),dt(b,v.binormal),dt(b,v.tangent)]}o.push(x.distance/i.length,...x.transverse,x.axial,...A,M)}let f=r?new Float32Array(Math.ceil(o.length/4096)*4096):new Float64Array(o.length);return f.set(o),{values:f,indices:a,gpu:r}}function Er(n,t,e,i,s,r){let{path:o,rest:a}=s,c=new n.Vector3,l=new n.Vector3,u=new n.Matrix3().getNormalMatrix(r),h=s.twistDeg*Math.PI/180,f=rt(h),p=ht(h),m=o.length/a.length,g=new Map,_=i.values,x=new Map;for(let v=0;v<t.count;v++){let y=i.indices[v],M=x.get(y);if(M!==void 0){t.setXYZ(v,t.getX(M),t.getY(M),t.getZ(M)),e&&e.setXYZ(v,e.getX(M),e.getY(M),e.getZ(M));continue}x.set(y,v);let A=y*8,b=_[A],S=g.get(b);S||(S=hn(o,b*o.length),g.set(b,S));let w=f*_[A+1]-p*_[A+2],R=p*_[A+1]+f*_[A+2],I=S.normal[0]*w+S.binormal[0]*R,N=S.normal[1]*w+S.binormal[1]*R,C=S.normal[2]*w+S.binormal[2]*R,T=S.curvature[0]*I+S.curvature[1]*N+S.curvature[2]*C;if(1-T<=br){let D=(1-br)/T;I*=D,N*=D,C*=D,T=1-br}let P=1-T;if(c.set(S.point[0]+I+_[A+3]*S.tangent[0],S.point[1]+N+_[A+3]*S.tangent[1],S.point[2]+C+_[A+3]*S.tangent[2]).applyMatrix4(r),t.setXYZ(v,c.x,c.y,c.z),e){let D=f*_[A+4]-p*_[A+5],E=p*_[A+4]+f*_[A+5],L=_[A+6]*_[A+7]/(P*m);l.set(D*S.normal[0]+E*S.binormal[0]+L*S.tangent[0],D*S.normal[1]+E*S.binormal[1]+L*S.tangent[1],D*S.normal[2]+E*S.binormal[2]+L*S.tangent[2]).applyNormalMatrix(u),e.setXYZ(v,l.x,l.y,l.z)}}t.needsUpdate=!0,e&&(e.needsUpdate=!0)}function sp(n,t,e,i,s,r){let o=e.clone(),a=e.attributes.instanceStart,c=e.attributes.instanceEnd,l=e.attributes.position;if(!a&&!l)return o;let u=a?null:e.index,h=a?a.count:u?u.count/2:t.isLineSegments?l.count/2:l.count-1,f=d((y,M)=>u?u.getX(y*2+M):t.isLineSegments?y*2+M:y+M,"vertexOf"),p=a?[]:Object.entries(e.attributes).filter(([y])=>y!=="position"),m=Object.fromEntries(p.map(([y])=>[y,[]])),g=new n.Vector3,_=new n.Vector3,x=new n.Vector3,v=[];for(let y=0;y<h;y++){let M=a?y:f(y,0),A=c?y:f(y,1);g.fromBufferAttribute(a||l,M),_.fromBufferAttribute(c||l,A);let b=$n(i,x.copy(g).applyMatrix4(s).toArray()).distance,S=$n(i,x.copy(_).applyMatrix4(s).toArray()).distance,w=Math.max(1,Math.ceil(Math.abs(S-b)/r));for(let R=0;R<w;R++)for(let I of[R/w,(R+1)/w]){v.push(g.x+(_.x-g.x)*I,g.y+(_.y-g.y)*I,g.z+(_.z-g.z)*I);for(let[N,C]of p){let T=I<1?M:A;for(let P=0;P<C.itemSize;P++)m[N].push(C.array[T*C.itemSize+P])}}}if(a)o.setPositions(v);else{o.setAttribute("position",new n.Float32BufferAttribute(v,3));for(let[y,M]of p)o.setAttribute(y,new n.BufferAttribute(new M.array.constructor(m[y]),M.itemSize,M.normalized));o.setIndex(null)}return o}function Cr(n,t,e,i=new n.Matrix4){if(!t)return;for(let c of t.children||[])Cr(n,c,e,i);if(!t.geometry)return;let s=t.tubeLineDeformationState;if(!e&&!s?.active||e&&s?.active&&Fe(s.lastSpec,e))return;let r=e?jt(e):null,o=e?Yn(e):s?.restKey;if(!s||e&&o!==s.restKey){let c=s?.original||t.geometry,l=sp(n,t,c,r.rest,i,r.maxSegmentLength),u=l.clone();s?.geometry.dispose(),u.userData={...u.userData,cadSceneCachedGeometry:!1};let h=l.attributes.instanceStart?["instanceStart","instanceEnd"]:["position"];s=t.tubeLineDeformationState={original:c,source:l,geometry:u,names:h,mappings:{},restKey:null,active:!1},t.geometry=u}if(!e){for(let c of s.names){let l=s.geometry.attributes[c],u=s.source.attributes[c];for(let h=0;h<u.count;h++)l.setXYZ(h,u.getX(h),u.getY(h),u.getZ(h));l.needsUpdate=!0}s.geometry.computeBoundingBox(),s.geometry.computeBoundingSphere(),s.active=!1;return}let a=i.clone().invert();for(let c of s.names)o!==s.restKey&&(s.mappings[c]=Za(n,s.source.attributes[c],null,r.rest,i)),Er(n,s.geometry.attributes[c],null,s.mappings[c],r,a);s.restKey=o,s.active=!0,s.lastSpec=e,s.geometry.computeBoundingBox(),s.geometry.computeBoundingSphere()}function rp(n,t){return`${Yn(n)}|${t.elements.map(e=>Number(e).toPrecision(9)).join(",")}`}function Ja(n,t,e,i){let s=Va.get(t);s||(s=new Map,Va.set(t,s));let r=rp(e,i),o=s.get(r);if(!o){let a=ip(n,t,e.rest,i,e.maxSegmentLength);o={restSource:a.geometry,sourceTriangles:a.sourceTriangles,mappings:new Map},s.set(r,o)}return o}function wr(n,t,e,i,s){let r=s?"gpu":"exact",o=t.mappings.get(r);return o||(o=Za(n,t.restSource.attributes.position,t.restSource.attributes.normal,e.rest,i,s),t.mappings.set(r,o)),o}function Rr(n,t,e,i){let s=Ja(n,t,e,i);return{geometry:s.restSource,sourceTriangles:s.sourceTriangles,mapping:wr(n,s,e,i,!1),vertexCount:s.restSource.attributes.position.count}}function Zn(n,t,e,i,s,r=null){Er(n,s,r,t.mapping,e,i)}function op(n,t,e,i,s){let r=e?.original||t.mesh.geometry,o=e?.originalFaceIds||t.mesh.userData?.faceIds,a=Ja(n,r,i,s),c=a.restSource,l=new n.BufferGeometry;l.setIndex(c.index);for(let[h,f]of Object.entries(c.attributes)){let p=!t.gpuTubeDeformationAllowed&&(h==="position"||h==="normal");l.setAttribute(h,p?f.clone():f)}l.userData={...l.userData,cadSceneCachedGeometry:!1,__bvhSkipped:!0},l.boundsTree=null,e?.geometry.dispose();let u={original:r,originalFaceIds:o,source:c,prepared:a,geometry:l,active:!1,restKey:Yn(i),mapping:null,partBounds:e?.partBounds||t.partBounds};return t.mesh.geometry=l,o&&a.sourceTriangles&&(t.mesh.userData.faceIds=new Uint32Array(a.sourceTriangles.map(h=>o[h]))),t.geometry=l,t.silhouette&&(t.silhouette.geometry=l),t.ghostMesh&&(t.ghostMesh.geometry=l),u}function ap(n,t){t.geometry.attributes.position.copy(t.source.attributes.position),t.geometry.attributes.position.needsUpdate=!0,t.source.attributes.normal&&(t.geometry.attributes.normal.copy(t.source.attributes.normal),t.geometry.attributes.normal.needsUpdate=!0),t.geometry.computeBoundingBox(),t.geometry.computeBoundingSphere(),n.partBounds=t.partBounds,t.active=!1}function cp(n,t,e){if(!t?.mesh?.geometry)return;t.effectDeformation=e||null,Pa(n,t.material||t.mesh.material,e?.braid||null),e&&t.edgeInstance&&t.detachEdgeInstance?.();let i=new n.Matrix4;t.baseTransform&&i.fromArray(t.baseTransform).transpose(),(!e||t.edges?.visible!==!1)&&Cr(n,t.edges,e,i);let s=t.tubeDeformationState;if(e&&s?.active&&Fe(s.lastSpec,e)){Mr(t);return}if(!e&&!s?.active)return;let r=e?jt(e):null;if(e||Sr(t),(!s||e&&Yn(e)!==s.restKey)&&(s=t.tubeDeformationState=op(n,t,s,r,i)),!e){ap(t,s);return}let o=i.clone().invert(),a=t.gpuTubeDeformationAllowed&&r.path.length<=vr;if(!s.mapping&&(s.mapping=wr(n,s.prepared,r,i,a),!s.mapping.gpu)){let u=new Float32Array(s.geometry.attributes.position.count*3);for(let h=0;h<u.length/3;h++){let f=s.mapping.indices[h]*8,p=s.mapping.values;u.set([p[f]*r.rest.length,p[f+1],p[f+2]],h*3)}s.geometry.setAttribute(Wn,new n.BufferAttribute(u,3))}let c=d(()=>{for(let u of["position","normal"])s.geometry.attributes[u]===s.source.attributes[u]&&s.geometry.setAttribute(u,s.source.attributes[u].clone());s.exactMapping??=s.mapping.gpu?wr(n,s.prepared,r,i,!1):s.mapping,Er(n,s.geometry.attributes.position,s.geometry.attributes.normal,s.exactMapping,r,o),s.geometry.computeBoundingBox(),s.geometry.computeBoundingSphere()},"materialize");if(La(n,t,s,r,o,hn,c)){s.active=!0,s.lastSpec=e;return}Sr(t),c();let l=s.geometry.boundingBox.clone().applyMatrix4(i);t.partBounds={min:l.min.toArray(),max:l.max.toArray()},s.active=!0,s.lastSpec=e}var Ue,br,Ua,Xd,ln,Bt,At,dt,Se,Wt,Fa,$d,Yd,Oa,on,Yn,Va,Hi=_n(()=>{Na();Da();ki();Fn();Ue=1e-7,br=.05,Ua=7e5,Xd=128,ln=d((n,t)=>n.map((e,i)=>e+t[i]),"add"),Bt=d((n,t)=>n.map((e,i)=>e-t[i]),"sub"),At=d((n,t)=>n.map(e=>e*t),"mul"),dt=d((n,t)=>n.reduce((e,i,s)=>e+i*t[s],0),"dot"),Se=d((n,t)=>[n[1]*t[2]-n[2]*t[1],n[2]*t[0]-n[0]*t[2],n[0]*t[1]-n[1]*t[0]],"cross"),Wt=d(n=>Math.sqrt(n.reduce((t,e)=>t+e*e,0)),"length"),Fa=d((n,t)=>(n[0]-t[0])**2+(n[1]-t[1])**2+(n[2]-t[2])**2,"distanceSq");d(qd,"boundsDistanceSq");d(ft,"fail");d(De,"vector");d(an,"unit");d(Vi,"keys");d(Gi,"rotate");d(qn,"bezierAt");d(un,"bezierDerivative");d(Ga,"bezierSecond");$d=[0,.5384693101056831,-.5384693101056831,.906179845938664,-.906179845938664],Yd=[.5688888888888889,.4786286704993665,.4786286704993665,.2369268850561891,.2369268850561891];d(Xn,"bezierLength");d(Ha,"transport");d(Zd,"buildBezierTable");d(Wa,"bezierParameter");d(Xa,"segmentPoint");d(Ar,"segmentFrame");Oa={line:["kind","start","end"],arc:["kind","center","axis","start","sweepDeg"],bezier:["kind","points"]};d(qa,"pathSpecNormal");d($a,"canonicalSegment");d(Jd,"compileSegment");d(Kd,"sampledBezierRadius");d(jd,"segmentBounds");d(Ya,"compileTubePath");d(hn,"sampleTubePath");d(Qd,"tablePoints");d(tp,"closestBezierDistance");d(ep,"closestArcDistance");d($n,"projectTubePath");on=new Map;d(Ba,"cachedCompile");d(za,"canonicalPathSpec");d(cn,"sameNumbers");d(Fe,"sameTubeDeformation");d(Tr,"sameTubeRestShape");d(jt,"compileDeformation");d(np,"normalizeTubeDeformation");Yn=d(n=>JSON.stringify([n.restSpec,n.maxSegmentLength]),"restMappingKey");d(ka,"clipPolygon");d(ip,"refineRestMesh");d(Za,"mappingFor");d(Er,"updateAttribute");d(sp,"refineLineGeometry");d(Cr,"applyTubeDeformationToLineObject");Va=new WeakMap;d(rp,"restPreparationKey");d(Ja,"prepareRestSurface");d(wr,"preparedMapping");d(Rr,"prepareTubeBake");d(Zn,"poseTubeBake");d(op,"createDeformationState");d(ap,"restoreRestSurface");d(cp,"applyRecordTubeDeformation")});import pn from"node:fs";import mn from"node:path";function Vr(n){let t=new DataView(n,0,12);if(t.getUint32(0,!0)!==1179800915)throw new Error("not a SURF container");let e=t.getUint32(4,!0);if(e!==2)throw new Error(`unsupported SURF version ${e}`);let i=t.getUint32(8,!0),s=new Uint8Array(n,12,i),r=JSON.parse(new TextDecoder().decode(s)),o=12+i,a=new Float32Array(n.slice(o,o+(n.byteLength-o>>2<<2)));return{index:r,floats:a}}d(Vr,"parseSurf");function ae(n,t){let[e,i]=t;return n.subarray(e,e+i)}d(ae,"floatSpan");var so=1;var ro=3;var as=0,cs=1,ls=2,us=3,hs=4,fs=5,ds=6,ps=7,oo=0,ao=1,co=2;var Ps=1,Ns=2,Ls=3,Ds=4,Us=5,Fs=6,Os=7;var Bs=300,lo=301,zs=302;var uo=306,ms=1e3,bn=1001,gs=1002;var ho=1006;var fo=1008;var po=1009;var mo=1015;var go=1023;var Tn=2300,li=2301,ai=2302,_s=2303,xs=2400,ys=2401,vs=2402;var ks="",Gt="srgb",Ss="srgb-linear",Ms="linear",ci="srgb";var _o=35044;var wn=2e3,bs=2001;function Ic(n){for(let t=n.length-1;t>=0;--t)if(n[t]>=65535)return!0;return!1}d(Ic,"arrayNeedsUint32");function Pc(n){return ArrayBuffer.isView(n)&&!(n instanceof DataView)}d(Pc,"isTypedArray");function ws(n){return document.createElementNS("http://www.w3.org/1999/xhtml",n)}d(ws,"createElementNS");var Gr={},ui=null;function xo(n){let t=n[0];if(typeof t=="string"&&t.startsWith("TSL:")){let e=n[1];e&&e.isStackTrace?n[0]+=" "+e.getLocation():n[1]='Stack trace not available. Enable "THREE.Node.captureStackTrace" to capture stack traces.'}return n}d(xo,"enhanceLogMessage");function gt(...n){n=xo(n);let t="THREE."+n.shift();if(ui)ui("warn",t,...n);else{let e=n[0];e&&e.isStackTrace?console.warn(e.getError(t)):console.warn(t,...n)}}d(gt,"warn");function ot(...n){n=xo(n);let t="THREE."+n.shift();if(ui)ui("error",t,...n);else{let e=n[0];e&&e.isStackTrace?console.error(e.getError(t)):console.error(t,...n)}}d(ot,"error");function Ze(...n){let t=n.join(" ");t in Gr||(Gr[t]=!0,gt(...n))}d(Ze,"warnOnce");var Nc={[as]:cs,[ls]:ds,[hs]:ps,[us]:fs,[cs]:as,[ds]:ls,[ps]:hs,[fs]:us},Ae=class{static{d(this,"EventDispatcher")}addEventListener(t,e){this._listeners===void 0&&(this._listeners={});let i=this._listeners;i[t]===void 0&&(i[t]=[]),i[t].indexOf(e)===-1&&i[t].push(e)}hasEventListener(t,e){let i=this._listeners;return i===void 0?!1:i[t]!==void 0&&i[t].indexOf(e)!==-1}removeEventListener(t,e){let i=this._listeners;if(i===void 0)return;let s=i[t];if(s!==void 0){let r=s.indexOf(e);r!==-1&&s.splice(r,1)}}dispatchEvent(t){let e=this._listeners;if(e===void 0)return;let i=e[t.type];if(i!==void 0){t.target=this;let s=i.slice(0);for(let r=0,o=s.length;r<o;r++)s[r].call(this,t);t.target=null}}},Mt=["00","01","02","03","04","05","06","07","08","09","0a","0b","0c","0d","0e","0f","10","11","12","13","14","15","16","17","18","19","1a","1b","1c","1d","1e","1f","20","21","22","23","24","25","26","27","28","29","2a","2b","2c","2d","2e","2f","30","31","32","33","34","35","36","37","38","39","3a","3b","3c","3d","3e","3f","40","41","42","43","44","45","46","47","48","49","4a","4b","4c","4d","4e","4f","50","51","52","53","54","55","56","57","58","59","5a","5b","5c","5d","5e","5f","60","61","62","63","64","65","66","67","68","69","6a","6b","6c","6d","6e","6f","70","71","72","73","74","75","76","77","78","79","7a","7b","7c","7d","7e","7f","80","81","82","83","84","85","86","87","88","89","8a","8b","8c","8d","8e","8f","90","91","92","93","94","95","96","97","98","99","9a","9b","9c","9d","9e","9f","a0","a1","a2","a3","a4","a5","a6","a7","a8","a9","aa","ab","ac","ad","ae","af","b0","b1","b2","b3","b4","b5","b6","b7","b8","b9","ba","bb","bc","bd","be","bf","c0","c1","c2","c3","c4","c5","c6","c7","c8","c9","ca","cb","cc","cd","ce","cf","d0","d1","d2","d3","d4","d5","d6","d7","d8","d9","da","db","dc","dd","de","df","e0","e1","e2","e3","e4","e5","e6","e7","e8","e9","ea","eb","ec","ed","ee","ef","f0","f1","f2","f3","f4","f5","f6","f7","f8","f9","fa","fb","fc","fd","fe","ff"];var Yp=Math.PI/180,Lc=180/Math.PI;function Ei(){let n=Math.random()*4294967295|0,t=Math.random()*4294967295|0,e=Math.random()*4294967295|0,i=Math.random()*4294967295|0;return(Mt[n&255]+Mt[n>>8&255]+Mt[n>>16&255]+Mt[n>>24&255]+"-"+Mt[t&255]+Mt[t>>8&255]+"-"+Mt[t>>16&15|64]+Mt[t>>24&255]+"-"+Mt[e&63|128]+Mt[e>>8&255]+"-"+Mt[e>>16&255]+Mt[e>>24&255]+Mt[i&255]+Mt[i>>8&255]+Mt[i>>16&255]+Mt[i>>24&255]).toLowerCase()}d(Ei,"generateUUID");function K(n,t,e){return Math.max(t,Math.min(e,n))}d(K,"clamp");function Dc(n,t){return(n%t+t)%t}d(Dc,"euclideanModulo");function Ji(n,t,e){return(1-e)*n+e*t}d(Ji,"lerp");function xn(n,t){switch(t.constructor){case Float32Array:return n;case Uint32Array:return n/4294967295;case Uint16Array:return n/65535;case Uint8Array:case Uint8ClampedArray:return n/255;case Int32Array:return Math.max(n/2147483647,-1);case Int16Array:return Math.max(n/32767,-1);case Int8Array:return Math.max(n/127,-1);default:throw new Error("THREE.MathUtils: Invalid component type.")}}d(xn,"denormalize");function Et(n,t){switch(t.constructor){case Float32Array:return n;case Uint32Array:return Math.round(n*4294967295);case Uint16Array:return Math.round(n*65535);case Uint8Array:case Uint8ClampedArray:return Math.round(n*255);case Int32Array:return Math.round(n*2147483647);case Int16Array:return Math.round(n*32767);case Int8Array:return Math.round(n*127);default:throw new Error("THREE.MathUtils: Invalid component type.")}}d(Et,"normalize");var _t=class n{static{d(this,"Vector2")}static{n.prototype.isVector2=!0}constructor(t=0,e=0){this.x=t,this.y=e}get width(){return this.x}set width(t){this.x=t}get height(){return this.y}set height(t){this.y=t}set(t,e){return this.x=t,this.y=e,this}setScalar(t){return this.x=t,this.y=t,this}setX(t){return this.x=t,this}setY(t){return this.y=t,this}setComponent(t,e){switch(t){case 0:this.x=e;break;case 1:this.y=e;break;default:throw new Error("THREE.Vector2: index is out of range: "+t)}return this}getComponent(t){switch(t){case 0:return this.x;case 1:return this.y;default:throw new Error("THREE.Vector2: index is out of range: "+t)}}clone(){return new this.constructor(this.x,this.y)}copy(t){return this.x=t.x,this.y=t.y,this}add(t){return this.x+=t.x,this.y+=t.y,this}addScalar(t){return this.x+=t,this.y+=t,this}addVectors(t,e){return this.x=t.x+e.x,this.y=t.y+e.y,this}addScaledVector(t,e){return this.x+=t.x*e,this.y+=t.y*e,this}sub(t){return this.x-=t.x,this.y-=t.y,this}subScalar(t){return this.x-=t,this.y-=t,this}subVectors(t,e){return this.x=t.x-e.x,this.y=t.y-e.y,this}multiply(t){return this.x*=t.x,this.y*=t.y,this}multiplyScalar(t){return this.x*=t,this.y*=t,this}divide(t){return this.x/=t.x,this.y/=t.y,this}divideScalar(t){return this.multiplyScalar(1/t)}applyMatrix3(t){let e=this.x,i=this.y,s=t.elements;return this.x=s[0]*e+s[3]*i+s[6],this.y=s[1]*e+s[4]*i+s[7],this}min(t){return this.x=Math.min(this.x,t.x),this.y=Math.min(this.y,t.y),this}max(t){return this.x=Math.max(this.x,t.x),this.y=Math.max(this.y,t.y),this}clamp(t,e){return this.x=K(this.x,t.x,e.x),this.y=K(this.y,t.y,e.y),this}clampScalar(t,e){return this.x=K(this.x,t,e),this.y=K(this.y,t,e),this}clampLength(t,e){let i=this.length();return this.divideScalar(i||1).multiplyScalar(K(i,t,e))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this}negate(){return this.x=-this.x,this.y=-this.y,this}dot(t){return this.x*t.x+this.y*t.y}cross(t){return this.x*t.y-this.y*t.x}lengthSq(){return this.x*this.x+this.y*this.y}length(){return Math.sqrt(this.x*this.x+this.y*this.y)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)}normalize(){return this.divideScalar(this.length()||1)}angle(){return Math.atan2(-this.y,-this.x)+Math.PI}angleTo(t){let e=Math.sqrt(this.lengthSq()*t.lengthSq());if(e===0)return Math.PI/2;let i=this.dot(t)/e;return Math.acos(K(i,-1,1))}distanceTo(t){return Math.sqrt(this.distanceToSquared(t))}distanceToSquared(t){let e=this.x-t.x,i=this.y-t.y;return e*e+i*i}manhattanDistanceTo(t){return Math.abs(this.x-t.x)+Math.abs(this.y-t.y)}setLength(t){return this.normalize().multiplyScalar(t)}lerp(t,e){return this.x+=(t.x-this.x)*e,this.y+=(t.y-this.y)*e,this}lerpVectors(t,e,i){return this.x=t.x+(e.x-t.x)*i,this.y=t.y+(e.y-t.y)*i,this}equals(t){return t.x===this.x&&t.y===this.y}fromArray(t,e=0){return this.x=t[e],this.y=t[e+1],this}toArray(t=[],e=0){return t[e]=this.x,t[e+1]=this.y,t}fromBufferAttribute(t,e){return this.x=t.getX(e),this.y=t.getY(e),this}rotateAround(t,e){let i=Math.cos(e),s=Math.sin(e),r=this.x-t.x,o=this.y-t.y;return this.x=r*i-o*s+t.x,this.y=r*s+o*i+t.y,this}random(){return this.x=Math.random(),this.y=Math.random(),this}*[Symbol.iterator](){yield this.x,yield this.y}},Yt=class{static{d(this,"Quaternion")}constructor(t=0,e=0,i=0,s=1){this.isQuaternion=!0,this._x=t,this._y=e,this._z=i,this._w=s}static slerpFlat(t,e,i,s,r,o,a){let c=i[s+0],l=i[s+1],u=i[s+2],h=i[s+3],f=r[o+0],p=r[o+1],m=r[o+2],g=r[o+3];if(h!==g||c!==f||l!==p||u!==m){let _=c*f+l*p+u*m+h*g;_<0&&(f=-f,p=-p,m=-m,g=-g,_=-_);let x=1-a;if(_<.9995){let v=Math.acos(_),y=Math.sin(v);x=Math.sin(x*v)/y,a=Math.sin(a*v)/y,c=c*x+f*a,l=l*x+p*a,u=u*x+m*a,h=h*x+g*a}else{c=c*x+f*a,l=l*x+p*a,u=u*x+m*a,h=h*x+g*a;let v=1/Math.sqrt(c*c+l*l+u*u+h*h);c*=v,l*=v,u*=v,h*=v}}t[e]=c,t[e+1]=l,t[e+2]=u,t[e+3]=h}static multiplyQuaternionsFlat(t,e,i,s,r,o){let a=i[s],c=i[s+1],l=i[s+2],u=i[s+3],h=r[o],f=r[o+1],p=r[o+2],m=r[o+3];return t[e]=a*m+u*h+c*p-l*f,t[e+1]=c*m+u*f+l*h-a*p,t[e+2]=l*m+u*p+a*f-c*h,t[e+3]=u*m-a*h-c*f-l*p,t}get x(){return this._x}set x(t){this._x=t,this._onChangeCallback()}get y(){return this._y}set y(t){this._y=t,this._onChangeCallback()}get z(){return this._z}set z(t){this._z=t,this._onChangeCallback()}get w(){return this._w}set w(t){this._w=t,this._onChangeCallback()}set(t,e,i,s){return this._x=t,this._y=e,this._z=i,this._w=s,this._onChangeCallback(),this}clone(){return new this.constructor(this._x,this._y,this._z,this._w)}copy(t){return this._x=t.x,this._y=t.y,this._z=t.z,this._w=t.w,this._onChangeCallback(),this}setFromEuler(t,e=!0){let i=t._x,s=t._y,r=t._z,o=t._order,a=Math.cos,c=Math.sin,l=a(i/2),u=a(s/2),h=a(r/2),f=c(i/2),p=c(s/2),m=c(r/2);switch(o){case"XYZ":this._x=f*u*h+l*p*m,this._y=l*p*h-f*u*m,this._z=l*u*m+f*p*h,this._w=l*u*h-f*p*m;break;case"YXZ":this._x=f*u*h+l*p*m,this._y=l*p*h-f*u*m,this._z=l*u*m-f*p*h,this._w=l*u*h+f*p*m;break;case"ZXY":this._x=f*u*h-l*p*m,this._y=l*p*h+f*u*m,this._z=l*u*m+f*p*h,this._w=l*u*h-f*p*m;break;case"ZYX":this._x=f*u*h-l*p*m,this._y=l*p*h+f*u*m,this._z=l*u*m-f*p*h,this._w=l*u*h+f*p*m;break;case"YZX":this._x=f*u*h+l*p*m,this._y=l*p*h+f*u*m,this._z=l*u*m-f*p*h,this._w=l*u*h-f*p*m;break;case"XZY":this._x=f*u*h-l*p*m,this._y=l*p*h-f*u*m,this._z=l*u*m+f*p*h,this._w=l*u*h+f*p*m;break;default:gt("Quaternion: .setFromEuler() encountered an unknown order: "+o)}return e===!0&&this._onChangeCallback(),this}setFromAxisAngle(t,e){let i=e/2,s=Math.sin(i);return this._x=t.x*s,this._y=t.y*s,this._z=t.z*s,this._w=Math.cos(i),this._onChangeCallback(),this}setFromRotationMatrix(t){let e=t.elements,i=e[0],s=e[4],r=e[8],o=e[1],a=e[5],c=e[9],l=e[2],u=e[6],h=e[10],f=i+a+h;if(f>0){let p=.5/Math.sqrt(f+1);this._w=.25/p,this._x=(u-c)*p,this._y=(r-l)*p,this._z=(o-s)*p}else if(i>a&&i>h){let p=2*Math.sqrt(1+i-a-h);this._w=(u-c)/p,this._x=.25*p,this._y=(s+o)/p,this._z=(r+l)/p}else if(a>h){let p=2*Math.sqrt(1+a-i-h);this._w=(r-l)/p,this._x=(s+o)/p,this._y=.25*p,this._z=(c+u)/p}else{let p=2*Math.sqrt(1+h-i-a);this._w=(o-s)/p,this._x=(r+l)/p,this._y=(c+u)/p,this._z=.25*p}return this._onChangeCallback(),this}setFromUnitVectors(t,e){let i=t.dot(e)+1;return i<1e-8?(i=0,Math.abs(t.x)>Math.abs(t.z)?(this._x=-t.y,this._y=t.x,this._z=0,this._w=i):(this._x=0,this._y=-t.z,this._z=t.y,this._w=i)):(this._x=t.y*e.z-t.z*e.y,this._y=t.z*e.x-t.x*e.z,this._z=t.x*e.y-t.y*e.x,this._w=i),this.normalize()}angleTo(t){return 2*Math.acos(Math.abs(K(this.dot(t),-1,1)))}rotateTowards(t,e){let i=this.angleTo(t);if(i===0)return this;let s=Math.min(1,e/i);return this.slerp(t,s),this}identity(){return this.set(0,0,0,1)}invert(){return this.conjugate()}conjugate(){return this._x*=-1,this._y*=-1,this._z*=-1,this._onChangeCallback(),this}dot(t){return this._x*t._x+this._y*t._y+this._z*t._z+this._w*t._w}lengthSq(){return this._x*this._x+this._y*this._y+this._z*this._z+this._w*this._w}length(){return Math.sqrt(this._x*this._x+this._y*this._y+this._z*this._z+this._w*this._w)}normalize(){let t=this.length();return t===0?(this._x=0,this._y=0,this._z=0,this._w=1):(t=1/t,this._x=this._x*t,this._y=this._y*t,this._z=this._z*t,this._w=this._w*t),this._onChangeCallback(),this}multiply(t){return this.multiplyQuaternions(this,t)}premultiply(t){return this.multiplyQuaternions(t,this)}multiplyQuaternions(t,e){let i=t._x,s=t._y,r=t._z,o=t._w,a=e._x,c=e._y,l=e._z,u=e._w;return this._x=i*u+o*a+s*l-r*c,this._y=s*u+o*c+r*a-i*l,this._z=r*u+o*l+i*c-s*a,this._w=o*u-i*a-s*c-r*l,this._onChangeCallback(),this}slerp(t,e){let i=t._x,s=t._y,r=t._z,o=t._w,a=this.dot(t);a<0&&(i=-i,s=-s,r=-r,o=-o,a=-a);let c=1-e;if(a<.9995){let l=Math.acos(a),u=Math.sin(l);c=Math.sin(c*l)/u,e=Math.sin(e*l)/u,this._x=this._x*c+i*e,this._y=this._y*c+s*e,this._z=this._z*c+r*e,this._w=this._w*c+o*e,this._onChangeCallback()}else this._x=this._x*c+i*e,this._y=this._y*c+s*e,this._z=this._z*c+r*e,this._w=this._w*c+o*e,this.normalize();return this}slerpQuaternions(t,e,i){return this.copy(t).slerp(e,i)}random(){let t=2*Math.PI*Math.random(),e=2*Math.PI*Math.random(),i=Math.random(),s=Math.sqrt(1-i),r=Math.sqrt(i);return this.set(s*Math.sin(t),s*Math.cos(t),r*Math.sin(e),r*Math.cos(e))}equals(t){return t._x===this._x&&t._y===this._y&&t._z===this._z&&t._w===this._w}fromArray(t,e=0){return this._x=t[e],this._y=t[e+1],this._z=t[e+2],this._w=t[e+3],this._onChangeCallback(),this}toArray(t=[],e=0){return t[e]=this._x,t[e+1]=this._y,t[e+2]=this._z,t[e+3]=this._w,t}fromBufferAttribute(t,e){return this._x=t.getX(e),this._y=t.getY(e),this._z=t.getZ(e),this._w=t.getW(e),this._onChangeCallback(),this}toJSON(){return this.toArray()}_onChange(t){return this._onChangeCallback=t,this}_onChangeCallback(){}*[Symbol.iterator](){yield this._x,yield this._y,yield this._z,yield this._w}},k=class n{static{d(this,"Vector3")}static{n.prototype.isVector3=!0}constructor(t=0,e=0,i=0){this.x=t,this.y=e,this.z=i}set(t,e,i){return i===void 0&&(i=this.z),this.x=t,this.y=e,this.z=i,this}setScalar(t){return this.x=t,this.y=t,this.z=t,this}setX(t){return this.x=t,this}setY(t){return this.y=t,this}setZ(t){return this.z=t,this}setComponent(t,e){switch(t){case 0:this.x=e;break;case 1:this.y=e;break;case 2:this.z=e;break;default:throw new Error("THREE.Vector3: index is out of range: "+t)}return this}getComponent(t){switch(t){case 0:return this.x;case 1:return this.y;case 2:return this.z;default:throw new Error("THREE.Vector3: index is out of range: "+t)}}clone(){return new this.constructor(this.x,this.y,this.z)}copy(t){return this.x=t.x,this.y=t.y,this.z=t.z,this}add(t){return this.x+=t.x,this.y+=t.y,this.z+=t.z,this}addScalar(t){return this.x+=t,this.y+=t,this.z+=t,this}addVectors(t,e){return this.x=t.x+e.x,this.y=t.y+e.y,this.z=t.z+e.z,this}addScaledVector(t,e){return this.x+=t.x*e,this.y+=t.y*e,this.z+=t.z*e,this}sub(t){return this.x-=t.x,this.y-=t.y,this.z-=t.z,this}subScalar(t){return this.x-=t,this.y-=t,this.z-=t,this}subVectors(t,e){return this.x=t.x-e.x,this.y=t.y-e.y,this.z=t.z-e.z,this}multiply(t){return this.x*=t.x,this.y*=t.y,this.z*=t.z,this}multiplyScalar(t){return this.x*=t,this.y*=t,this.z*=t,this}multiplyVectors(t,e){return this.x=t.x*e.x,this.y=t.y*e.y,this.z=t.z*e.z,this}applyEuler(t){return this.applyQuaternion(Hr.setFromEuler(t))}applyAxisAngle(t,e){return this.applyQuaternion(Hr.setFromAxisAngle(t,e))}applyMatrix3(t){let e=this.x,i=this.y,s=this.z,r=t.elements;return this.x=r[0]*e+r[3]*i+r[6]*s,this.y=r[1]*e+r[4]*i+r[7]*s,this.z=r[2]*e+r[5]*i+r[8]*s,this}applyNormalMatrix(t){return this.applyMatrix3(t).normalize()}applyMatrix4(t){let e=this.x,i=this.y,s=this.z,r=t.elements,o=1/(r[3]*e+r[7]*i+r[11]*s+r[15]);return this.x=(r[0]*e+r[4]*i+r[8]*s+r[12])*o,this.y=(r[1]*e+r[5]*i+r[9]*s+r[13])*o,this.z=(r[2]*e+r[6]*i+r[10]*s+r[14])*o,this}applyQuaternion(t){let e=this.x,i=this.y,s=this.z,r=t.x,o=t.y,a=t.z,c=t.w,l=2*(o*s-a*i),u=2*(a*e-r*s),h=2*(r*i-o*e);return this.x=e+c*l+o*h-a*u,this.y=i+c*u+a*l-r*h,this.z=s+c*h+r*u-o*l,this}project(t){return this.applyMatrix4(t.matrixWorldInverse).applyMatrix4(t.projectionMatrix)}unproject(t){return this.applyMatrix4(t.projectionMatrixInverse).applyMatrix4(t.matrixWorld)}transformDirection(t){let e=this.x,i=this.y,s=this.z,r=t.elements;return this.x=r[0]*e+r[4]*i+r[8]*s,this.y=r[1]*e+r[5]*i+r[9]*s,this.z=r[2]*e+r[6]*i+r[10]*s,this.normalize()}divide(t){return this.x/=t.x,this.y/=t.y,this.z/=t.z,this}divideScalar(t){return this.multiplyScalar(1/t)}min(t){return this.x=Math.min(this.x,t.x),this.y=Math.min(this.y,t.y),this.z=Math.min(this.z,t.z),this}max(t){return this.x=Math.max(this.x,t.x),this.y=Math.max(this.y,t.y),this.z=Math.max(this.z,t.z),this}clamp(t,e){return this.x=K(this.x,t.x,e.x),this.y=K(this.y,t.y,e.y),this.z=K(this.z,t.z,e.z),this}clampScalar(t,e){return this.x=K(this.x,t,e),this.y=K(this.y,t,e),this.z=K(this.z,t,e),this}clampLength(t,e){let i=this.length();return this.divideScalar(i||1).multiplyScalar(K(i,t,e))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this.z=Math.floor(this.z),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this.z=Math.ceil(this.z),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this.z=Math.round(this.z),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this.z=Math.trunc(this.z),this}negate(){return this.x=-this.x,this.y=-this.y,this.z=-this.z,this}dot(t){return this.x*t.x+this.y*t.y+this.z*t.z}lengthSq(){return this.x*this.x+this.y*this.y+this.z*this.z}length(){return Math.sqrt(this.x*this.x+this.y*this.y+this.z*this.z)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)+Math.abs(this.z)}normalize(){return this.divideScalar(this.length()||1)}setLength(t){return this.normalize().multiplyScalar(t)}lerp(t,e){return this.x+=(t.x-this.x)*e,this.y+=(t.y-this.y)*e,this.z+=(t.z-this.z)*e,this}lerpVectors(t,e,i){return this.x=t.x+(e.x-t.x)*i,this.y=t.y+(e.y-t.y)*i,this.z=t.z+(e.z-t.z)*i,this}cross(t){return this.crossVectors(this,t)}crossVectors(t,e){let i=t.x,s=t.y,r=t.z,o=e.x,a=e.y,c=e.z;return this.x=s*c-r*a,this.y=r*o-i*c,this.z=i*a-s*o,this}projectOnVector(t){let e=t.lengthSq();if(e===0)return this.set(0,0,0);let i=t.dot(this)/e;return this.copy(t).multiplyScalar(i)}projectOnPlane(t){return Ki.copy(this).projectOnVector(t),this.sub(Ki)}reflect(t){return this.sub(Ki.copy(t).multiplyScalar(2*this.dot(t)))}angleTo(t){let e=Math.sqrt(this.lengthSq()*t.lengthSq());if(e===0)return Math.PI/2;let i=this.dot(t)/e;return Math.acos(K(i,-1,1))}distanceTo(t){return Math.sqrt(this.distanceToSquared(t))}distanceToSquared(t){let e=this.x-t.x,i=this.y-t.y,s=this.z-t.z;return e*e+i*i+s*s}manhattanDistanceTo(t){return Math.abs(this.x-t.x)+Math.abs(this.y-t.y)+Math.abs(this.z-t.z)}setFromSpherical(t){return this.setFromSphericalCoords(t.radius,t.phi,t.theta)}setFromSphericalCoords(t,e,i){let s=Math.sin(e)*t;return this.x=s*Math.sin(i),this.y=Math.cos(e)*t,this.z=s*Math.cos(i),this}setFromCylindrical(t){return this.setFromCylindricalCoords(t.radius,t.theta,t.y)}setFromCylindricalCoords(t,e,i){return this.x=t*Math.sin(e),this.y=i,this.z=t*Math.cos(e),this}setFromMatrixPosition(t){let e=t.elements;return this.x=e[12],this.y=e[13],this.z=e[14],this}setFromMatrixScale(t){let e=this.setFromMatrixColumn(t,0).length(),i=this.setFromMatrixColumn(t,1).length(),s=this.setFromMatrixColumn(t,2).length();return this.x=e,this.y=i,this.z=s,this}setFromMatrixColumn(t,e){return this.fromArray(t.elements,e*4)}setFromMatrix3Column(t,e){return this.fromArray(t.elements,e*3)}setFromEuler(t){return this.x=t._x,this.y=t._y,this.z=t._z,this}setFromColor(t){return this.x=t.r,this.y=t.g,this.z=t.b,this}equals(t){return t.x===this.x&&t.y===this.y&&t.z===this.z}fromArray(t,e=0){return this.x=t[e],this.y=t[e+1],this.z=t[e+2],this}toArray(t=[],e=0){return t[e]=this.x,t[e+1]=this.y,t[e+2]=this.z,t}fromBufferAttribute(t,e){return this.x=t.getX(e),this.y=t.getY(e),this.z=t.getZ(e),this}random(){return this.x=Math.random(),this.y=Math.random(),this.z=Math.random(),this}randomDirection(){let t=Math.random()*Math.PI*2,e=Math.random()*2-1,i=Math.sqrt(1-e*e);return this.x=i*Math.cos(t),this.y=e,this.z=i*Math.sin(t),this}*[Symbol.iterator](){yield this.x,yield this.y,yield this.z}},Ki=new k,Hr=new Yt,Y=class n{static{d(this,"Matrix3")}static{n.prototype.isMatrix3=!0}constructor(t,e,i,s,r,o,a,c,l){this.elements=[1,0,0,0,1,0,0,0,1],t!==void 0&&this.set(t,e,i,s,r,o,a,c,l)}set(t,e,i,s,r,o,a,c,l){let u=this.elements;return u[0]=t,u[1]=s,u[2]=a,u[3]=e,u[4]=r,u[5]=c,u[6]=i,u[7]=o,u[8]=l,this}identity(){return this.set(1,0,0,0,1,0,0,0,1),this}copy(t){let e=this.elements,i=t.elements;return e[0]=i[0],e[1]=i[1],e[2]=i[2],e[3]=i[3],e[4]=i[4],e[5]=i[5],e[6]=i[6],e[7]=i[7],e[8]=i[8],this}extractBasis(t,e,i){return t.setFromMatrix3Column(this,0),e.setFromMatrix3Column(this,1),i.setFromMatrix3Column(this,2),this}setFromMatrix4(t){let e=t.elements;return this.set(e[0],e[4],e[8],e[1],e[5],e[9],e[2],e[6],e[10]),this}multiply(t){return this.multiplyMatrices(this,t)}premultiply(t){return this.multiplyMatrices(t,this)}multiplyMatrices(t,e){let i=t.elements,s=e.elements,r=this.elements,o=i[0],a=i[3],c=i[6],l=i[1],u=i[4],h=i[7],f=i[2],p=i[5],m=i[8],g=s[0],_=s[3],x=s[6],v=s[1],y=s[4],M=s[7],A=s[2],b=s[5],S=s[8];return r[0]=o*g+a*v+c*A,r[3]=o*_+a*y+c*b,r[6]=o*x+a*M+c*S,r[1]=l*g+u*v+h*A,r[4]=l*_+u*y+h*b,r[7]=l*x+u*M+h*S,r[2]=f*g+p*v+m*A,r[5]=f*_+p*y+m*b,r[8]=f*x+p*M+m*S,this}multiplyScalar(t){let e=this.elements;return e[0]*=t,e[3]*=t,e[6]*=t,e[1]*=t,e[4]*=t,e[7]*=t,e[2]*=t,e[5]*=t,e[8]*=t,this}determinant(){let t=this.elements,e=t[0],i=t[1],s=t[2],r=t[3],o=t[4],a=t[5],c=t[6],l=t[7],u=t[8];return e*o*u-e*a*l-i*r*u+i*a*c+s*r*l-s*o*c}invert(){let t=this.elements,e=t[0],i=t[1],s=t[2],r=t[3],o=t[4],a=t[5],c=t[6],l=t[7],u=t[8],h=u*o-a*l,f=a*c-u*r,p=l*r-o*c,m=e*h+i*f+s*p;if(m===0)return this.set(0,0,0,0,0,0,0,0,0);let g=1/m;return t[0]=h*g,t[1]=(s*l-u*i)*g,t[2]=(a*i-s*o)*g,t[3]=f*g,t[4]=(u*e-s*c)*g,t[5]=(s*r-a*e)*g,t[6]=p*g,t[7]=(i*c-l*e)*g,t[8]=(o*e-i*r)*g,this}transpose(){let t,e=this.elements;return t=e[1],e[1]=e[3],e[3]=t,t=e[2],e[2]=e[6],e[6]=t,t=e[5],e[5]=e[7],e[7]=t,this}getNormalMatrix(t){return this.setFromMatrix4(t).invert().transpose()}transposeIntoArray(t){let e=this.elements;return t[0]=e[0],t[1]=e[3],t[2]=e[6],t[3]=e[1],t[4]=e[4],t[5]=e[7],t[6]=e[2],t[7]=e[5],t[8]=e[8],this}setUvTransform(t,e,i,s,r,o,a){let c=Math.cos(r),l=Math.sin(r);return this.set(i*c,i*l,-i*(c*o+l*a)+o+t,-s*l,s*c,-s*(-l*o+c*a)+a+e,0,0,1),this}scale(t,e){return Ze("Matrix3: .scale() is deprecated. Use .makeScale() instead."),this.premultiply(ji.makeScale(t,e)),this}rotate(t){return Ze("Matrix3: .rotate() is deprecated. Use .makeRotation() instead."),this.premultiply(ji.makeRotation(-t)),this}translate(t,e){return Ze("Matrix3: .translate() is deprecated. Use .makeTranslation() instead."),this.premultiply(ji.makeTranslation(t,e)),this}makeTranslation(t,e){return t.isVector2?this.set(1,0,t.x,0,1,t.y,0,0,1):this.set(1,0,t,0,1,e,0,0,1),this}makeRotation(t){let e=Math.cos(t),i=Math.sin(t);return this.set(e,-i,0,i,e,0,0,0,1),this}makeScale(t,e){return this.set(t,0,0,0,e,0,0,0,1),this}equals(t){let e=this.elements,i=t.elements;for(let s=0;s<9;s++)if(e[s]!==i[s])return!1;return!0}fromArray(t,e=0){for(let i=0;i<9;i++)this.elements[i]=t[i+e];return this}toArray(t=[],e=0){let i=this.elements;return t[e]=i[0],t[e+1]=i[1],t[e+2]=i[2],t[e+3]=i[3],t[e+4]=i[4],t[e+5]=i[5],t[e+6]=i[6],t[e+7]=i[7],t[e+8]=i[8],t}clone(){return new this.constructor().fromArray(this.elements)}},ji=new Y,Wr=new Y().set(.4123908,.3575843,.1804808,.212639,.7151687,.0721923,.0193308,.1191948,.9505322),Xr=new Y().set(3.2409699,-1.5373832,-.4986108,-.9692436,1.8759675,.0415551,.0556301,-.203977,1.0569715);function Uc(){let n={enabled:!0,workingColorSpace:Ss,spaces:{},convert:d(function(s,r,o){return this.enabled===!1||r===o||!r||!o||(this.spaces[r].transfer===ci&&(s.r=ne(s.r),s.g=ne(s.g),s.b=ne(s.b)),this.spaces[r].primaries!==this.spaces[o].primaries&&(s.applyMatrix3(this.spaces[r].toXYZ),s.applyMatrix3(this.spaces[o].fromXYZ)),this.spaces[o].transfer===ci&&(s.r=Je(s.r),s.g=Je(s.g),s.b=Je(s.b))),s},"convert"),workingToColorSpace:d(function(s,r){return this.convert(s,this.workingColorSpace,r)},"workingToColorSpace"),colorSpaceToWorking:d(function(s,r){return this.convert(s,r,this.workingColorSpace)},"colorSpaceToWorking"),getPrimaries:d(function(s){return this.spaces[s].primaries},"getPrimaries"),getTransfer:d(function(s){return s===ks?Ms:this.spaces[s].transfer},"getTransfer"),getToneMappingMode:d(function(s){return this.spaces[s].outputColorSpaceConfig.toneMappingMode||"standard"},"getToneMappingMode"),getLuminanceCoefficients:d(function(s,r=this.workingColorSpace){return s.fromArray(this.spaces[r].luminanceCoefficients)},"getLuminanceCoefficients"),define:d(function(s){Object.assign(this.spaces,s)},"define"),_getMatrix:d(function(s,r,o){return s.copy(this.spaces[r].toXYZ).multiply(this.spaces[o].fromXYZ)},"_getMatrix"),_getDrawingBufferColorSpace:d(function(s){return this.spaces[s].outputColorSpaceConfig.drawingBufferColorSpace},"_getDrawingBufferColorSpace"),_getUnpackColorSpace:d(function(s=this.workingColorSpace){return this.spaces[s].workingColorSpaceConfig.unpackColorSpace},"_getUnpackColorSpace"),fromWorkingColorSpace:d(function(s,r){return Ze("ColorManagement: .fromWorkingColorSpace() has been renamed to .workingToColorSpace()."),n.workingToColorSpace(s,r)},"fromWorkingColorSpace"),toWorkingColorSpace:d(function(s,r){return Ze("ColorManagement: .toWorkingColorSpace() has been renamed to .colorSpaceToWorking()."),n.colorSpaceToWorking(s,r)},"toWorkingColorSpace")},t=[.64,.33,.3,.6,.15,.06],e=[.2126,.7152,.0722],i=[.3127,.329];return n.define({[Ss]:{primaries:t,whitePoint:i,transfer:Ms,toXYZ:Wr,fromXYZ:Xr,luminanceCoefficients:e,workingColorSpaceConfig:{unpackColorSpace:Gt},outputColorSpaceConfig:{drawingBufferColorSpace:Gt}},[Gt]:{primaries:t,whitePoint:i,transfer:ci,toXYZ:Wr,fromXYZ:Xr,luminanceCoefficients:e,outputColorSpaceConfig:{drawingBufferColorSpace:Gt}}}),n}d(Uc,"createColorManagement");var Vt=Uc();function ne(n){return n<.04045?n*.0773993808:Math.pow(n*.9478672986+.0521327014,2.4)}d(ne,"SRGBToLinear");function Je(n){return n<.0031308?n*12.92:1.055*Math.pow(n,.41666)-.055}d(Je,"LinearToSRGB");var ke,hi=class{static{d(this,"ImageUtils")}static getDataURL(t,e="image/png"){if(/^data:/i.test(t.src)||typeof HTMLCanvasElement>"u")return t.src;let i;if(t instanceof HTMLCanvasElement)i=t;else{ke===void 0&&(ke=ws("canvas")),ke.width=t.width,ke.height=t.height;let s=ke.getContext("2d");t instanceof ImageData?s.putImageData(t,0,0):s.drawImage(t,0,0,t.width,t.height),i=ke}return i.toDataURL(e)}static sRGBToLinear(t){if(typeof HTMLImageElement<"u"&&t instanceof HTMLImageElement||typeof HTMLCanvasElement<"u"&&t instanceof HTMLCanvasElement||typeof ImageBitmap<"u"&&t instanceof ImageBitmap){let e=ws("canvas");e.width=t.width,e.height=t.height;let i=e.getContext("2d");i.drawImage(t,0,0,t.width,t.height);let s=i.getImageData(0,0,t.width,t.height),r=s.data;for(let o=0;o<r.length;o++)r[o]=ne(r[o]/255)*255;return i.putImageData(s,0,0),e}else if(t.data){let e=t.data.slice(0);for(let i=0;i<e.length;i++)e instanceof Uint8Array||e instanceof Uint8ClampedArray?e[i]=Math.floor(ne(e[i]/255)*255):e[i]=ne(e[i]);return{data:e,width:t.width,height:t.height}}else return gt("ImageUtils.sRGBToLinear(): Unsupported image type. No color space conversion applied."),t}},Fc=0,fi=class{static{d(this,"TextureSource")}constructor(t=null){this.isTextureSource=!0,Object.defineProperty(this,"id",{value:Fc++}),this.uuid=Ei(),this.data=t,this.dataReady=!0,this.version=0}getSize(t){let e=this.data;return typeof HTMLVideoElement<"u"&&e instanceof HTMLVideoElement?t.set(e.videoWidth,e.videoHeight,0):typeof VideoFrame<"u"&&e instanceof VideoFrame?t.set(e.displayWidth,e.displayHeight,0):e!==null?t.set(e.width,e.height,e.depth||0):t.set(0,0,0),t}set needsUpdate(t){t===!0&&this.version++}toJSON(t){let e=t===void 0||typeof t=="string";if(!e&&t.images[this.uuid]!==void 0)return t.images[this.uuid];let i={uuid:this.uuid,url:""},s=this.data;if(s!==null){let r;if(Array.isArray(s)){r=[];for(let o=0,a=s.length;o<a;o++)s[o].isDataTexture?r.push(Qi(s[o].image)):r.push(Qi(s[o]))}else r=Qi(s);i.url=r}return e||(t.images[this.uuid]=i),i}};function Qi(n){return typeof HTMLImageElement<"u"&&n instanceof HTMLImageElement||typeof HTMLCanvasElement<"u"&&n instanceof HTMLCanvasElement||typeof ImageBitmap<"u"&&n instanceof ImageBitmap?hi.getDataURL(n):n.data?{data:Array.from(n.data),width:n.width,height:n.height,type:n.data.constructor.name}:(gt("Texture: Unable to serialize Texture."),{})}d(Qi,"serializeImage");var Oc=0,ts=new k,Ke=class n extends Ae{static{d(this,"Texture")}constructor(t=n.DEFAULT_IMAGE,e=n.DEFAULT_MAPPING,i=bn,s=bn,r=ho,o=fo,a=go,c=po,l=n.DEFAULT_ANISOTROPY,u=ks){super(),this.isTexture=!0,Object.defineProperty(this,"id",{value:Oc++}),this.uuid=Ei(),this.name="",this.source=new fi(t),this.mipmaps=[],this.mapping=e,this.channel=0,this.wrapS=i,this.wrapT=s,this.magFilter=r,this.minFilter=o,this.anisotropy=l,this.format=a,this.internalFormat=null,this.type=c,this.offset=new _t(0,0),this.repeat=new _t(1,1),this.center=new _t(0,0),this.rotation=0,this.matrixAutoUpdate=!0,this.matrix=new Y,this.generateMipmaps=!0,this.premultiplyAlpha=!1,this.flipY=!0,this.unpackAlignment=4,this.colorSpace=u,this.userData={},this.updateRanges=[],this.version=0,this.onUpdate=null,this.renderTarget=null,this.isRenderTargetTexture=!1,this.isArrayTexture=!!(t&&t.depth&&t.depth>1),this.pmremVersion=0,this.normalized=!1}get width(){return this.source.getSize(ts).x}get height(){return this.source.getSize(ts).y}get depth(){return this.source.getSize(ts).z}get image(){return this.source.data}set image(t){this.source.data=t}updateMatrix(){this.matrix.setUvTransform(this.offset.x,this.offset.y,this.repeat.x,this.repeat.y,this.rotation,this.center.x,this.center.y)}addUpdateRange(t,e){this.updateRanges.push({start:t,count:e})}clearUpdateRanges(){this.updateRanges.length=0}clone(){return new this.constructor().copy(this)}copy(t){return this.name=t.name,this.source=t.source,this.mipmaps=t.mipmaps.slice(0),this.mapping=t.mapping,this.channel=t.channel,this.wrapS=t.wrapS,this.wrapT=t.wrapT,this.magFilter=t.magFilter,this.minFilter=t.minFilter,this.anisotropy=t.anisotropy,this.format=t.format,this.internalFormat=t.internalFormat,this.type=t.type,this.normalized=t.normalized,this.offset.copy(t.offset),this.repeat.copy(t.repeat),this.center.copy(t.center),this.rotation=t.rotation,this.matrixAutoUpdate=t.matrixAutoUpdate,this.matrix.copy(t.matrix),this.generateMipmaps=t.generateMipmaps,this.premultiplyAlpha=t.premultiplyAlpha,this.flipY=t.flipY,this.unpackAlignment=t.unpackAlignment,this.colorSpace=t.colorSpace,this.renderTarget=t.renderTarget,this.isRenderTargetTexture=t.isRenderTargetTexture,this.isArrayTexture=t.isArrayTexture,this.userData=JSON.parse(JSON.stringify(t.userData)),this.needsUpdate=!0,this}setValues(t){for(let e in t){let i=t[e];if(i===void 0){gt(`Texture.setValues(): parameter '${e}' has value of undefined.`);continue}let s=this[e];if(s===void 0){gt(`Texture.setValues(): property '${e}' does not exist.`);continue}s&&i&&s.isVector2&&i.isVector2||s&&i&&s.isVector3&&i.isVector3||s&&i&&s.isMatrix3&&i.isMatrix3?s.copy(i):this[e]=i}}toJSON(t){let e=t===void 0||typeof t=="string";if(!e&&t.textures[this.uuid]!==void 0)return t.textures[this.uuid];let i={metadata:{version:4.7,type:"Texture",generator:"Texture.toJSON"},uuid:this.uuid,name:this.name,image:this.source.toJSON(t).uuid,mapping:this.mapping,channel:this.channel,repeat:[this.repeat.x,this.repeat.y],offset:[this.offset.x,this.offset.y],center:[this.center.x,this.center.y],rotation:this.rotation,wrap:[this.wrapS,this.wrapT],format:this.format,internalFormat:this.internalFormat,type:this.type,normalized:this.normalized,colorSpace:this.colorSpace,minFilter:this.minFilter,magFilter:this.magFilter,anisotropy:this.anisotropy,flipY:this.flipY,generateMipmaps:this.generateMipmaps,premultiplyAlpha:this.premultiplyAlpha,unpackAlignment:this.unpackAlignment};return Object.keys(this.userData).length>0&&(i.userData=this.userData),e||(t.textures[this.uuid]=i),i}dispose(){this.dispatchEvent({type:"dispose"})}transformUv(t){if(this.mapping!==Bs)return t;if(t.applyMatrix3(this.matrix),t.x<0||t.x>1)switch(this.wrapS){case ms:t.x=t.x-Math.floor(t.x);break;case bn:t.x=t.x<0?0:1;break;case gs:Math.abs(Math.floor(t.x)%2)===1?t.x=Math.ceil(t.x)-t.x:t.x=t.x-Math.floor(t.x);break}if(t.y<0||t.y>1)switch(this.wrapT){case ms:t.y=t.y-Math.floor(t.y);break;case bn:t.y=t.y<0?0:1;break;case gs:Math.abs(Math.floor(t.y)%2)===1?t.y=Math.ceil(t.y)-t.y:t.y=t.y-Math.floor(t.y);break}return this.flipY&&(t.y=1-t.y),t}set needsUpdate(t){t===!0&&(this.version++,this.source.needsUpdate=!0)}set needsPMREMUpdate(t){t===!0&&this.pmremVersion++}};Ke.DEFAULT_IMAGE=null;Ke.DEFAULT_MAPPING=Bs;Ke.DEFAULT_ANISOTROPY=1;var As=class n{static{d(this,"Vector4")}static{n.prototype.isVector4=!0}constructor(t=0,e=0,i=0,s=1){this.x=t,this.y=e,this.z=i,this.w=s}get width(){return this.z}set width(t){this.z=t}get height(){return this.w}set height(t){this.w=t}set(t,e,i,s){return this.x=t,this.y=e,this.z=i,this.w=s,this}setScalar(t){return this.x=t,this.y=t,this.z=t,this.w=t,this}setX(t){return this.x=t,this}setY(t){return this.y=t,this}setZ(t){return this.z=t,this}setW(t){return this.w=t,this}setComponent(t,e){switch(t){case 0:this.x=e;break;case 1:this.y=e;break;case 2:this.z=e;break;case 3:this.w=e;break;default:throw new Error("THREE.Vector4: index is out of range: "+t)}return this}getComponent(t){switch(t){case 0:return this.x;case 1:return this.y;case 2:return this.z;case 3:return this.w;default:throw new Error("THREE.Vector4: index is out of range: "+t)}}clone(){return new this.constructor(this.x,this.y,this.z,this.w)}copy(t){return this.x=t.x,this.y=t.y,this.z=t.z,this.w=t.w!==void 0?t.w:1,this}add(t){return this.x+=t.x,this.y+=t.y,this.z+=t.z,this.w+=t.w,this}addScalar(t){return this.x+=t,this.y+=t,this.z+=t,this.w+=t,this}addVectors(t,e){return this.x=t.x+e.x,this.y=t.y+e.y,this.z=t.z+e.z,this.w=t.w+e.w,this}addScaledVector(t,e){return this.x+=t.x*e,this.y+=t.y*e,this.z+=t.z*e,this.w+=t.w*e,this}sub(t){return this.x-=t.x,this.y-=t.y,this.z-=t.z,this.w-=t.w,this}subScalar(t){return this.x-=t,this.y-=t,this.z-=t,this.w-=t,this}subVectors(t,e){return this.x=t.x-e.x,this.y=t.y-e.y,this.z=t.z-e.z,this.w=t.w-e.w,this}multiply(t){return this.x*=t.x,this.y*=t.y,this.z*=t.z,this.w*=t.w,this}multiplyScalar(t){return this.x*=t,this.y*=t,this.z*=t,this.w*=t,this}applyMatrix4(t){let e=this.x,i=this.y,s=this.z,r=this.w,o=t.elements;return this.x=o[0]*e+o[4]*i+o[8]*s+o[12]*r,this.y=o[1]*e+o[5]*i+o[9]*s+o[13]*r,this.z=o[2]*e+o[6]*i+o[10]*s+o[14]*r,this.w=o[3]*e+o[7]*i+o[11]*s+o[15]*r,this}divide(t){return this.x/=t.x,this.y/=t.y,this.z/=t.z,this.w/=t.w,this}divideScalar(t){return this.multiplyScalar(1/t)}setAxisAngleFromQuaternion(t){this.w=2*Math.acos(t.w);let e=Math.sqrt(1-t.w*t.w);return e<1e-4?(this.x=1,this.y=0,this.z=0):(this.x=t.x/e,this.y=t.y/e,this.z=t.z/e),this}setAxisAngleFromRotationMatrix(t){let e,i,s,r,c=t.elements,l=c[0],u=c[4],h=c[8],f=c[1],p=c[5],m=c[9],g=c[2],_=c[6],x=c[10];if(Math.abs(u-f)<.01&&Math.abs(h-g)<.01&&Math.abs(m-_)<.01){if(Math.abs(u+f)<.1&&Math.abs(h+g)<.1&&Math.abs(m+_)<.1&&Math.abs(l+p+x-3)<.1)return this.set(1,0,0,0),this;e=Math.PI;let y=(l+1)/2,M=(p+1)/2,A=(x+1)/2,b=(u+f)/4,S=(h+g)/4,w=(m+_)/4;return y>M&&y>A?y<.01?(i=0,s=.707106781,r=.707106781):(i=Math.sqrt(y),s=b/i,r=S/i):M>A?M<.01?(i=.707106781,s=0,r=.707106781):(s=Math.sqrt(M),i=b/s,r=w/s):A<.01?(i=.707106781,s=.707106781,r=0):(r=Math.sqrt(A),i=S/r,s=w/r),this.set(i,s,r,e),this}let v=Math.sqrt((_-m)*(_-m)+(h-g)*(h-g)+(f-u)*(f-u));return Math.abs(v)<.001&&(v=1),this.x=(_-m)/v,this.y=(h-g)/v,this.z=(f-u)/v,this.w=Math.acos((l+p+x-1)/2),this}setFromMatrixPosition(t){let e=t.elements;return this.x=e[12],this.y=e[13],this.z=e[14],this.w=e[15],this}min(t){return this.x=Math.min(this.x,t.x),this.y=Math.min(this.y,t.y),this.z=Math.min(this.z,t.z),this.w=Math.min(this.w,t.w),this}max(t){return this.x=Math.max(this.x,t.x),this.y=Math.max(this.y,t.y),this.z=Math.max(this.z,t.z),this.w=Math.max(this.w,t.w),this}clamp(t,e){return this.x=K(this.x,t.x,e.x),this.y=K(this.y,t.y,e.y),this.z=K(this.z,t.z,e.z),this.w=K(this.w,t.w,e.w),this}clampScalar(t,e){return this.x=K(this.x,t,e),this.y=K(this.y,t,e),this.z=K(this.z,t,e),this.w=K(this.w,t,e),this}clampLength(t,e){let i=this.length();return this.divideScalar(i||1).multiplyScalar(K(i,t,e))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this.z=Math.floor(this.z),this.w=Math.floor(this.w),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this.z=Math.ceil(this.z),this.w=Math.ceil(this.w),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this.z=Math.round(this.z),this.w=Math.round(this.w),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this.z=Math.trunc(this.z),this.w=Math.trunc(this.w),this}negate(){return this.x=-this.x,this.y=-this.y,this.z=-this.z,this.w=-this.w,this}dot(t){return this.x*t.x+this.y*t.y+this.z*t.z+this.w*t.w}lengthSq(){return this.x*this.x+this.y*this.y+this.z*this.z+this.w*this.w}length(){return Math.sqrt(this.x*this.x+this.y*this.y+this.z*this.z+this.w*this.w)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)+Math.abs(this.z)+Math.abs(this.w)}normalize(){return this.divideScalar(this.length()||1)}setLength(t){return this.normalize().multiplyScalar(t)}lerp(t,e){return this.x+=(t.x-this.x)*e,this.y+=(t.y-this.y)*e,this.z+=(t.z-this.z)*e,this.w+=(t.w-this.w)*e,this}lerpVectors(t,e,i){return this.x=t.x+(e.x-t.x)*i,this.y=t.y+(e.y-t.y)*i,this.z=t.z+(e.z-t.z)*i,this.w=t.w+(e.w-t.w)*i,this}equals(t){return t.x===this.x&&t.y===this.y&&t.z===this.z&&t.w===this.w}fromArray(t,e=0){return this.x=t[e],this.y=t[e+1],this.z=t[e+2],this.w=t[e+3],this}toArray(t=[],e=0){return t[e]=this.x,t[e+1]=this.y,t[e+2]=this.z,t[e+3]=this.w,t}fromBufferAttribute(t,e){return this.x=t.getX(e),this.y=t.getY(e),this.z=t.getZ(e),this.w=t.getW(e),this}random(){return this.x=Math.random(),this.y=Math.random(),this.z=Math.random(),this.w=Math.random(),this}*[Symbol.iterator](){yield this.x,yield this.y,yield this.z,yield this.w}};var xt=class n{static{d(this,"Matrix4")}static{n.prototype.isMatrix4=!0}constructor(t,e,i,s,r,o,a,c,l,u,h,f,p,m,g,_){this.elements=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],t!==void 0&&this.set(t,e,i,s,r,o,a,c,l,u,h,f,p,m,g,_)}set(t,e,i,s,r,o,a,c,l,u,h,f,p,m,g,_){let x=this.elements;return x[0]=t,x[4]=e,x[8]=i,x[12]=s,x[1]=r,x[5]=o,x[9]=a,x[13]=c,x[2]=l,x[6]=u,x[10]=h,x[14]=f,x[3]=p,x[7]=m,x[11]=g,x[15]=_,this}identity(){return this.set(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1),this}clone(){return new n().fromArray(this.elements)}copy(t){let e=this.elements,i=t.elements;return e[0]=i[0],e[1]=i[1],e[2]=i[2],e[3]=i[3],e[4]=i[4],e[5]=i[5],e[6]=i[6],e[7]=i[7],e[8]=i[8],e[9]=i[9],e[10]=i[10],e[11]=i[11],e[12]=i[12],e[13]=i[13],e[14]=i[14],e[15]=i[15],this}copyPosition(t){let e=this.elements,i=t.elements;return e[12]=i[12],e[13]=i[13],e[14]=i[14],this}setFromMatrix3(t){let e=t.elements;return this.set(e[0],e[3],e[6],0,e[1],e[4],e[7],0,e[2],e[5],e[8],0,0,0,0,1),this}extractBasis(t,e,i){return this.determinantAffine()===0?(t.set(1,0,0),e.set(0,1,0),i.set(0,0,1),this):(t.setFromMatrixColumn(this,0),e.setFromMatrixColumn(this,1),i.setFromMatrixColumn(this,2),this)}makeBasis(t,e,i){return this.set(t.x,e.x,i.x,0,t.y,e.y,i.y,0,t.z,e.z,i.z,0,0,0,0,1),this}extractRotation(t){if(t.determinantAffine()===0)return this.identity();let e=this.elements,i=t.elements,s=1/Ve.setFromMatrixColumn(t,0).length(),r=1/Ve.setFromMatrixColumn(t,1).length(),o=1/Ve.setFromMatrixColumn(t,2).length();return e[0]=i[0]*s,e[1]=i[1]*s,e[2]=i[2]*s,e[3]=0,e[4]=i[4]*r,e[5]=i[5]*r,e[6]=i[6]*r,e[7]=0,e[8]=i[8]*o,e[9]=i[9]*o,e[10]=i[10]*o,e[11]=0,e[12]=0,e[13]=0,e[14]=0,e[15]=1,this}makeRotationFromEuler(t){let e=this.elements,i=t.x,s=t.y,r=t.z,o=Math.cos(i),a=Math.sin(i),c=Math.cos(s),l=Math.sin(s),u=Math.cos(r),h=Math.sin(r);if(t.order==="XYZ"){let f=o*u,p=o*h,m=a*u,g=a*h;e[0]=c*u,e[4]=-c*h,e[8]=l,e[1]=p+m*l,e[5]=f-g*l,e[9]=-a*c,e[2]=g-f*l,e[6]=m+p*l,e[10]=o*c}else if(t.order==="YXZ"){let f=c*u,p=c*h,m=l*u,g=l*h;e[0]=f+g*a,e[4]=m*a-p,e[8]=o*l,e[1]=o*h,e[5]=o*u,e[9]=-a,e[2]=p*a-m,e[6]=g+f*a,e[10]=o*c}else if(t.order==="ZXY"){let f=c*u,p=c*h,m=l*u,g=l*h;e[0]=f-g*a,e[4]=-o*h,e[8]=m+p*a,e[1]=p+m*a,e[5]=o*u,e[9]=g-f*a,e[2]=-o*l,e[6]=a,e[10]=o*c}else if(t.order==="ZYX"){let f=o*u,p=o*h,m=a*u,g=a*h;e[0]=c*u,e[4]=m*l-p,e[8]=f*l+g,e[1]=c*h,e[5]=g*l+f,e[9]=p*l-m,e[2]=-l,e[6]=a*c,e[10]=o*c}else if(t.order==="YZX"){let f=o*c,p=o*l,m=a*c,g=a*l;e[0]=c*u,e[4]=g-f*h,e[8]=m*h+p,e[1]=h,e[5]=o*u,e[9]=-a*u,e[2]=-l*u,e[6]=p*h+m,e[10]=f-g*h}else if(t.order==="XZY"){let f=o*c,p=o*l,m=a*c,g=a*l;e[0]=c*u,e[4]=-h,e[8]=l*u,e[1]=f*h+g,e[5]=o*u,e[9]=p*h-m,e[2]=m*h-p,e[6]=a*u,e[10]=g*h+f}return e[3]=0,e[7]=0,e[11]=0,e[12]=0,e[13]=0,e[14]=0,e[15]=1,this}makeRotationFromQuaternion(t){return this.compose(Bc,t,zc)}lookAt(t,e,i){let s=this.elements;return Lt.subVectors(t,e),Lt.lengthSq()===0&&(Lt.z=1),Lt.normalize(),ce.crossVectors(i,Lt),ce.lengthSq()===0&&(Math.abs(i.z)===1?Lt.x+=1e-4:Lt.z+=1e-4,Lt.normalize(),ce.crossVectors(i,Lt)),ce.normalize(),jn.crossVectors(Lt,ce),s[0]=ce.x,s[4]=jn.x,s[8]=Lt.x,s[1]=ce.y,s[5]=jn.y,s[9]=Lt.y,s[2]=ce.z,s[6]=jn.z,s[10]=Lt.z,this}multiply(t){return this.multiplyMatrices(this,t)}premultiply(t){return this.multiplyMatrices(t,this)}multiplyMatrices(t,e){let i=t.elements,s=e.elements,r=this.elements,o=i[0],a=i[4],c=i[8],l=i[12],u=i[1],h=i[5],f=i[9],p=i[13],m=i[2],g=i[6],_=i[10],x=i[14],v=i[3],y=i[7],M=i[11],A=i[15],b=s[0],S=s[4],w=s[8],R=s[12],I=s[1],N=s[5],C=s[9],T=s[13],P=s[2],D=s[6],E=s[10],L=s[14],F=s[3],O=s[7],U=s[11],B=s[15];return r[0]=o*b+a*I+c*P+l*F,r[4]=o*S+a*N+c*D+l*O,r[8]=o*w+a*C+c*E+l*U,r[12]=o*R+a*T+c*L+l*B,r[1]=u*b+h*I+f*P+p*F,r[5]=u*S+h*N+f*D+p*O,r[9]=u*w+h*C+f*E+p*U,r[13]=u*R+h*T+f*L+p*B,r[2]=m*b+g*I+_*P+x*F,r[6]=m*S+g*N+_*D+x*O,r[10]=m*w+g*C+_*E+x*U,r[14]=m*R+g*T+_*L+x*B,r[3]=v*b+y*I+M*P+A*F,r[7]=v*S+y*N+M*D+A*O,r[11]=v*w+y*C+M*E+A*U,r[15]=v*R+y*T+M*L+A*B,this}multiplyScalar(t){let e=this.elements;return e[0]*=t,e[4]*=t,e[8]*=t,e[12]*=t,e[1]*=t,e[5]*=t,e[9]*=t,e[13]*=t,e[2]*=t,e[6]*=t,e[10]*=t,e[14]*=t,e[3]*=t,e[7]*=t,e[11]*=t,e[15]*=t,this}determinant(){let t=this.elements,e=t[0],i=t[4],s=t[8],r=t[12],o=t[1],a=t[5],c=t[9],l=t[13],u=t[2],h=t[6],f=t[10],p=t[14],m=t[3],g=t[7],_=t[11],x=t[15],v=c*p-l*f,y=a*p-l*h,M=a*f-c*h,A=o*p-l*u,b=o*f-c*u,S=o*h-a*u;return e*(g*v-_*y+x*M)-i*(m*v-_*A+x*b)+s*(m*y-g*A+x*S)-r*(m*M-g*b+_*S)}determinantAffine(){let t=this.elements,e=t[0],i=t[4],s=t[8],r=t[1],o=t[5],a=t[9],c=t[2],l=t[6],u=t[10];return e*(o*u-a*l)-i*(r*u-a*c)+s*(r*l-o*c)}transpose(){let t=this.elements,e;return e=t[1],t[1]=t[4],t[4]=e,e=t[2],t[2]=t[8],t[8]=e,e=t[6],t[6]=t[9],t[9]=e,e=t[3],t[3]=t[12],t[12]=e,e=t[7],t[7]=t[13],t[13]=e,e=t[11],t[11]=t[14],t[14]=e,this}setPosition(t,e,i){let s=this.elements;return t.isVector3?(s[12]=t.x,s[13]=t.y,s[14]=t.z):(s[12]=t,s[13]=e,s[14]=i),this}invert(){let t=this.elements,e=t[0],i=t[1],s=t[2],r=t[3],o=t[4],a=t[5],c=t[6],l=t[7],u=t[8],h=t[9],f=t[10],p=t[11],m=t[12],g=t[13],_=t[14],x=t[15],v=e*a-i*o,y=e*c-s*o,M=e*l-r*o,A=i*c-s*a,b=i*l-r*a,S=s*l-r*c,w=u*g-h*m,R=u*_-f*m,I=u*x-p*m,N=h*_-f*g,C=h*x-p*g,T=f*x-p*_,P=v*T-y*C+M*N+A*I-b*R+S*w;if(P===0)return this.set(0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0);let D=1/P;return t[0]=(a*T-c*C+l*N)*D,t[1]=(s*C-i*T-r*N)*D,t[2]=(g*S-_*b+x*A)*D,t[3]=(f*b-h*S-p*A)*D,t[4]=(c*I-o*T-l*R)*D,t[5]=(e*T-s*I+r*R)*D,t[6]=(_*M-m*S-x*y)*D,t[7]=(u*S-f*M+p*y)*D,t[8]=(o*C-a*I+l*w)*D,t[9]=(i*I-e*C-r*w)*D,t[10]=(m*b-g*M+x*v)*D,t[11]=(h*M-u*b-p*v)*D,t[12]=(a*R-o*N-c*w)*D,t[13]=(e*N-i*R+s*w)*D,t[14]=(g*y-m*A-_*v)*D,t[15]=(u*A-h*y+f*v)*D,this}scale(t){let e=this.elements,i=t.x,s=t.y,r=t.z;return e[0]*=i,e[4]*=s,e[8]*=r,e[1]*=i,e[5]*=s,e[9]*=r,e[2]*=i,e[6]*=s,e[10]*=r,e[3]*=i,e[7]*=s,e[11]*=r,this}getMaxScaleOnAxis(){let t=this.elements,e=t[0]*t[0]+t[1]*t[1]+t[2]*t[2],i=t[4]*t[4]+t[5]*t[5]+t[6]*t[6],s=t[8]*t[8]+t[9]*t[9]+t[10]*t[10];return Math.sqrt(Math.max(e,i,s))}makeTranslation(t,e,i){return t.isVector3?this.set(1,0,0,t.x,0,1,0,t.y,0,0,1,t.z,0,0,0,1):this.set(1,0,0,t,0,1,0,e,0,0,1,i,0,0,0,1),this}makeRotationX(t){let e=Math.cos(t),i=Math.sin(t);return this.set(1,0,0,0,0,e,-i,0,0,i,e,0,0,0,0,1),this}makeRotationY(t){let e=Math.cos(t),i=Math.sin(t);return this.set(e,0,i,0,0,1,0,0,-i,0,e,0,0,0,0,1),this}makeRotationZ(t){let e=Math.cos(t),i=Math.sin(t);return this.set(e,-i,0,0,i,e,0,0,0,0,1,0,0,0,0,1),this}makeRotationAxis(t,e){let i=Math.cos(e),s=Math.sin(e),r=1-i,o=t.x,a=t.y,c=t.z,l=r*o,u=r*a;return this.set(l*o+i,l*a-s*c,l*c+s*a,0,l*a+s*c,u*a+i,u*c-s*o,0,l*c-s*a,u*c+s*o,r*c*c+i,0,0,0,0,1),this}makeScale(t,e,i){return this.set(t,0,0,0,0,e,0,0,0,0,i,0,0,0,0,1),this}makeShear(t,e,i,s,r,o){return this.set(1,i,r,0,t,1,o,0,e,s,1,0,0,0,0,1),this}compose(t,e,i){let s=this.elements,r=e._x,o=e._y,a=e._z,c=e._w,l=r+r,u=o+o,h=a+a,f=r*l,p=r*u,m=r*h,g=o*u,_=o*h,x=a*h,v=c*l,y=c*u,M=c*h,A=i.x,b=i.y,S=i.z;return s[0]=(1-(g+x))*A,s[1]=(p+M)*A,s[2]=(m-y)*A,s[3]=0,s[4]=(p-M)*b,s[5]=(1-(f+x))*b,s[6]=(_+v)*b,s[7]=0,s[8]=(m+y)*S,s[9]=(_-v)*S,s[10]=(1-(f+g))*S,s[11]=0,s[12]=t.x,s[13]=t.y,s[14]=t.z,s[15]=1,this}decompose(t,e,i){let s=this.elements;t.x=s[12],t.y=s[13],t.z=s[14];let r=this.determinantAffine();if(r===0)return i.set(1,1,1),e.identity(),this;let o=Ve.set(s[0],s[1],s[2]).length(),a=Ve.set(s[4],s[5],s[6]).length(),c=Ve.set(s[8],s[9],s[10]).length();r<0&&(o=-o),qt.copy(this);let l=1/o,u=1/a,h=1/c;return qt.elements[0]*=l,qt.elements[1]*=l,qt.elements[2]*=l,qt.elements[4]*=u,qt.elements[5]*=u,qt.elements[6]*=u,qt.elements[8]*=h,qt.elements[9]*=h,qt.elements[10]*=h,e.setFromRotationMatrix(qt),i.x=o,i.y=a,i.z=c,this}makePerspective(t,e,i,s,r,o,a=wn,c=!1){let l=this.elements,u=2*r/(e-t),h=2*r/(i-s),f=(e+t)/(e-t),p=(i+s)/(i-s),m,g;if(c)m=r/(o-r),g=o*r/(o-r);else if(a===wn)m=-(o+r)/(o-r),g=-2*o*r/(o-r);else if(a===bs)m=-o/(o-r),g=-o*r/(o-r);else throw new Error("THREE.Matrix4.makePerspective(): Invalid coordinate system: "+a);return l[0]=u,l[4]=0,l[8]=f,l[12]=0,l[1]=0,l[5]=h,l[9]=p,l[13]=0,l[2]=0,l[6]=0,l[10]=m,l[14]=g,l[3]=0,l[7]=0,l[11]=-1,l[15]=0,this}makeOrthographic(t,e,i,s,r,o,a=wn,c=!1){let l=this.elements,u=2/(e-t),h=2/(i-s),f=-(e+t)/(e-t),p=-(i+s)/(i-s),m,g;if(c)m=1/(o-r),g=o/(o-r);else if(a===wn)m=-2/(o-r),g=-(o+r)/(o-r);else if(a===bs)m=-1/(o-r),g=-r/(o-r);else throw new Error("THREE.Matrix4.makeOrthographic(): Invalid coordinate system: "+a);return l[0]=u,l[4]=0,l[8]=0,l[12]=f,l[1]=0,l[5]=h,l[9]=0,l[13]=p,l[2]=0,l[6]=0,l[10]=m,l[14]=g,l[3]=0,l[7]=0,l[11]=0,l[15]=1,this}equals(t){let e=this.elements,i=t.elements;for(let s=0;s<16;s++)if(e[s]!==i[s])return!1;return!0}fromArray(t,e=0){for(let i=0;i<16;i++)this.elements[i]=t[i+e];return this}toArray(t=[],e=0){let i=this.elements;return t[e]=i[0],t[e+1]=i[1],t[e+2]=i[2],t[e+3]=i[3],t[e+4]=i[4],t[e+5]=i[5],t[e+6]=i[6],t[e+7]=i[7],t[e+8]=i[8],t[e+9]=i[9],t[e+10]=i[10],t[e+11]=i[11],t[e+12]=i[12],t[e+13]=i[13],t[e+14]=i[14],t[e+15]=i[15],t}},Ve=new k,qt=new xt,Bc=new k(0,0,0),zc=new k(1,1,1),ce=new k,jn=new k,Lt=new k,qr=new xt,$r=new Yt,En=class n{static{d(this,"Euler")}constructor(t=0,e=0,i=0,s=n.DEFAULT_ORDER){this.isEuler=!0,this._x=t,this._y=e,this._z=i,this._order=s}get x(){return this._x}set x(t){this._x=t,this._onChangeCallback()}get y(){return this._y}set y(t){this._y=t,this._onChangeCallback()}get z(){return this._z}set z(t){this._z=t,this._onChangeCallback()}get order(){return this._order}set order(t){this._order=t,this._onChangeCallback()}set(t,e,i,s=this._order){return this._x=t,this._y=e,this._z=i,this._order=s,this._onChangeCallback(),this}clone(){return new this.constructor(this._x,this._y,this._z,this._order)}copy(t){return this._x=t._x,this._y=t._y,this._z=t._z,this._order=t._order,this._onChangeCallback(),this}setFromRotationMatrix(t,e=this._order,i=!0){let s=t.elements,r=s[0],o=s[4],a=s[8],c=s[1],l=s[5],u=s[9],h=s[2],f=s[6],p=s[10];switch(e){case"XYZ":this._y=Math.asin(K(a,-1,1)),Math.abs(a)<.9999999?(this._x=Math.atan2(-u,p),this._z=Math.atan2(-o,r)):(this._x=Math.atan2(f,l),this._z=0);break;case"YXZ":this._x=Math.asin(-K(u,-1,1)),Math.abs(u)<.9999999?(this._y=Math.atan2(a,p),this._z=Math.atan2(c,l)):(this._y=Math.atan2(-h,r),this._z=0);break;case"ZXY":this._x=Math.asin(K(f,-1,1)),Math.abs(f)<.9999999?(this._y=Math.atan2(-h,p),this._z=Math.atan2(-o,l)):(this._y=0,this._z=Math.atan2(c,r));break;case"ZYX":this._y=Math.asin(-K(h,-1,1)),Math.abs(h)<.9999999?(this._x=Math.atan2(f,p),this._z=Math.atan2(c,r)):(this._x=0,this._z=Math.atan2(-o,l));break;case"YZX":this._z=Math.asin(K(c,-1,1)),Math.abs(c)<.9999999?(this._x=Math.atan2(-u,l),this._y=Math.atan2(-h,r)):(this._x=0,this._y=Math.atan2(a,p));break;case"XZY":this._z=Math.asin(-K(o,-1,1)),Math.abs(o)<.9999999?(this._x=Math.atan2(f,l),this._y=Math.atan2(a,r)):(this._x=Math.atan2(-u,p),this._y=0);break;default:gt("Euler: .setFromRotationMatrix() encountered an unknown order: "+e)}return this._order=e,i===!0&&this._onChangeCallback(),this}setFromQuaternion(t,e,i){return qr.makeRotationFromQuaternion(t),this.setFromRotationMatrix(qr,e,i)}setFromVector3(t,e=this._order){return this.set(t.x,t.y,t.z,e)}reorder(t){return $r.setFromEuler(this),this.setFromQuaternion($r,t)}equals(t){return t._x===this._x&&t._y===this._y&&t._z===this._z&&t._order===this._order}fromArray(t){return this._x=t[0],this._y=t[1],this._z=t[2],t[3]!==void 0&&(this._order=t[3]),this._onChangeCallback(),this}toArray(t=[],e=0){return t[e]=this._x,t[e+1]=this._y,t[e+2]=this._z,t[e+3]=this._order,t}_onChange(t){return this._onChangeCallback=t,this}_onChangeCallback(){}*[Symbol.iterator](){yield this._x,yield this._y,yield this._z,yield this._order}};En.DEFAULT_ORDER="XYZ";var di=class{static{d(this,"Layers")}constructor(){this.mask=1}set(t){this.mask=(1<<t|0)>>>0}enable(t){this.mask|=1<<t|0}enableAll(){this.mask=-1}toggle(t){this.mask^=1<<t|0}disable(t){this.mask&=~(1<<t|0)}disableAll(){this.mask=0}test(t){return(this.mask&t.mask)!==0}isEnabled(t){return(this.mask&(1<<t|0))!==0}},kc=0,Yr=new k,Ge=new Yt,te=new xt,Qn=new k,yn=new k,Vc=new k,Gc=new Yt,Zr=new k(1,0,0),Jr=new k(0,1,0),Kr=new k(0,0,1),jr={type:"added"},Hc={type:"removed"},He={type:"childadded",child:null},es={type:"childremoved",child:null},Te=class n extends Ae{static{d(this,"Object3D")}constructor(){super(),this.isObject3D=!0,Object.defineProperty(this,"id",{value:kc++}),this.uuid=Ei(),this.name="",this.type="Object3D",this.parent=null,this.children=[],this.up=n.DEFAULT_UP.clone();let t=new k,e=new En,i=new Yt,s=new k(1,1,1);function r(){i.setFromEuler(e,!1)}d(r,"onRotationChange");function o(){e.setFromQuaternion(i,void 0,!1)}d(o,"onQuaternionChange"),e._onChange(r),i._onChange(o),Object.defineProperties(this,{position:{configurable:!0,enumerable:!0,value:t},rotation:{configurable:!0,enumerable:!0,value:e},quaternion:{configurable:!0,enumerable:!0,value:i},scale:{configurable:!0,enumerable:!0,value:s},modelViewMatrix:{value:new xt},normalMatrix:{value:new Y}}),this.matrix=new xt,this.matrixWorld=new xt,this.matrixAutoUpdate=n.DEFAULT_MATRIX_AUTO_UPDATE,this.matrixWorldAutoUpdate=n.DEFAULT_MATRIX_WORLD_AUTO_UPDATE,this.matrixWorldNeedsUpdate=!1,this.layers=new di,this.visible=!0,this.castShadow=!1,this.receiveShadow=!1,this.frustumCulled=!0,this.renderOrder=0,this.animations=[],this.customDepthMaterial=void 0,this.customDistanceMaterial=void 0,this.static=!1,this.userData={},this.pivot=null}onBeforeShadow(){}onAfterShadow(){}onBeforeRender(){}onAfterRender(){}applyMatrix4(t){this.matrixAutoUpdate&&this.updateMatrix(),this.matrix.premultiply(t),this.matrix.decompose(this.position,this.quaternion,this.scale)}applyQuaternion(t){return this.quaternion.premultiply(t),this}setRotationFromAxisAngle(t,e){this.quaternion.setFromAxisAngle(t,e)}setRotationFromEuler(t){this.quaternion.setFromEuler(t,!0)}setRotationFromMatrix(t){this.quaternion.setFromRotationMatrix(t)}setRotationFromQuaternion(t){this.quaternion.copy(t)}rotateOnAxis(t,e){return Ge.setFromAxisAngle(t,e),this.quaternion.multiply(Ge),this}rotateOnWorldAxis(t,e){return Ge.setFromAxisAngle(t,e),this.quaternion.premultiply(Ge),this}rotateX(t){return this.rotateOnAxis(Zr,t)}rotateY(t){return this.rotateOnAxis(Jr,t)}rotateZ(t){return this.rotateOnAxis(Kr,t)}translateOnAxis(t,e){return Yr.copy(t).applyQuaternion(this.quaternion),this.position.add(Yr.multiplyScalar(e)),this}translateX(t){return this.translateOnAxis(Zr,t)}translateY(t){return this.translateOnAxis(Jr,t)}translateZ(t){return this.translateOnAxis(Kr,t)}localToWorld(t){return this.updateWorldMatrix(!0,!1),t.applyMatrix4(this.matrixWorld)}worldToLocal(t){return this.updateWorldMatrix(!0,!1),t.applyMatrix4(te.copy(this.matrixWorld).invert())}lookAt(t,e,i){t.isVector3?Qn.copy(t):Qn.set(t,e,i);let s=this.parent;this.updateWorldMatrix(!0,!1),yn.setFromMatrixPosition(this.matrixWorld),this.isCamera||this.isLight?te.lookAt(yn,Qn,this.up):te.lookAt(Qn,yn,this.up),this.quaternion.setFromRotationMatrix(te),s&&(te.extractRotation(s.matrixWorld),Ge.setFromRotationMatrix(te),this.quaternion.premultiply(Ge.invert()))}add(t){if(arguments.length>1){for(let e=0;e<arguments.length;e++)this.add(arguments[e]);return this}return t===this?(ot("Object3D.add: object can't be added as a child of itself.",t),this):(t&&t.isObject3D?(t.removeFromParent(),t.parent=this,this.children.push(t),t.dispatchEvent(jr),He.child=t,this.dispatchEvent(He),He.child=null):ot("Object3D.add: object not an instance of THREE.Object3D.",t),this)}remove(t){if(arguments.length>1){for(let i=0;i<arguments.length;i++)this.remove(arguments[i]);return this}let e=this.children.indexOf(t);return e!==-1&&(t.parent=null,this.children.splice(e,1),t.dispatchEvent(Hc),es.child=t,this.dispatchEvent(es),es.child=null),this}removeFromParent(){let t=this.parent;return t!==null&&t.remove(this),this}clear(){return this.remove(...this.children)}attach(t){return this.updateWorldMatrix(!0,!1),te.copy(this.matrixWorld).invert(),t.parent!==null&&(t.parent.updateWorldMatrix(!0,!1),te.multiply(t.parent.matrixWorld)),t.applyMatrix4(te),t.removeFromParent(),t.parent=this,this.children.push(t),t.updateWorldMatrix(!1,!0),t.dispatchEvent(jr),He.child=t,this.dispatchEvent(He),He.child=null,this}getObjectById(t){return this.getObjectByProperty("id",t)}getObjectByName(t){return this.getObjectByProperty("name",t)}getObjectByProperty(t,e){if(this[t]===e)return this;for(let i=0,s=this.children.length;i<s;i++){let o=this.children[i].getObjectByProperty(t,e);if(o!==void 0)return o}}getObjectsByProperty(t,e,i=[]){this[t]===e&&i.push(this);let s=this.children;for(let r=0,o=s.length;r<o;r++)s[r].getObjectsByProperty(t,e,i);return i}getWorldPosition(t){return this.updateWorldMatrix(!0,!1),t.setFromMatrixPosition(this.matrixWorld)}getWorldQuaternion(t){return this.updateWorldMatrix(!0,!1),this.matrixWorld.decompose(yn,t,Vc),t}getWorldScale(t){return this.updateWorldMatrix(!0,!1),this.matrixWorld.decompose(yn,Gc,t),t}getWorldDirection(t){this.updateWorldMatrix(!0,!1);let e=this.matrixWorld.elements;return t.set(e[8],e[9],e[10]).normalize()}raycast(){}intersectsFrustum(){}traverse(t){t(this);let e=this.children;for(let i=0,s=e.length;i<s;i++)e[i].traverse(t)}traverseVisible(t){if(this.visible===!1)return;t(this);let e=this.children;for(let i=0,s=e.length;i<s;i++)e[i].traverseVisible(t)}traverseAncestors(t){let e=this.parent;e!==null&&(t(e),e.traverseAncestors(t))}updateMatrix(){this.matrix.compose(this.position,this.quaternion,this.scale);let t=this.pivot;if(t!==null){let e=t.x,i=t.y,s=t.z,r=this.matrix.elements;r[12]+=e-r[0]*e-r[4]*i-r[8]*s,r[13]+=i-r[1]*e-r[5]*i-r[9]*s,r[14]+=s-r[2]*e-r[6]*i-r[10]*s}this.matrixWorldNeedsUpdate=!0}updateMatrixWorld(t){this.matrixAutoUpdate&&this.updateMatrix(),(this.matrixWorldNeedsUpdate||t)&&(this.matrixWorldAutoUpdate===!0&&(this.parent===null?this.matrixWorld.copy(this.matrix):this.matrixWorld.multiplyMatrices(this.parent.matrixWorld,this.matrix)),this.matrixWorldNeedsUpdate=!1,t=!0);let e=this.children;for(let i=0,s=e.length;i<s;i++)e[i].updateMatrixWorld(t)}updateWorldMatrix(t,e,i=!1){let s=this.parent;if(t===!0&&s!==null&&s.updateWorldMatrix(!0,!1),this.matrixAutoUpdate&&this.updateMatrix(),(this.matrixWorldNeedsUpdate||i)&&(this.matrixWorldAutoUpdate===!0&&(this.parent===null?this.matrixWorld.copy(this.matrix):this.matrixWorld.multiplyMatrices(this.parent.matrixWorld,this.matrix)),this.matrixWorldNeedsUpdate=!1,i=!0),e===!0){let r=this.children;for(let o=0,a=r.length;o<a;o++)r[o].updateWorldMatrix(!1,!0,i)}}toJSON(t){let e=t===void 0||typeof t=="string",i={};e&&(t={geometries:{},materials:{},textures:{},images:{},shapes:{},skeletons:{},animations:{},nodes:{}},i.metadata={version:4.7,type:"Object",generator:"Object3D.toJSON"});let s={};s.uuid=this.uuid,s.type=this.type,s.name=this.name,s.castShadow=this.castShadow,s.receiveShadow=this.receiveShadow,s.visible=this.visible,s.frustumCulled=this.frustumCulled,s.renderOrder=this.renderOrder,s.static=this.static,s.matrixAutoUpdate=this.matrixAutoUpdate,Object.keys(this.userData).length>0&&(s.userData=this.userData),s.layers=this.layers.mask,s.matrix=this.matrix.toArray(),s.up=this.up.toArray(),this.pivot!==null&&(s.pivot=this.pivot.toArray()),this.morphTargetDictionary!==void 0&&(s.morphTargetDictionary=Object.assign({},this.morphTargetDictionary)),this.morphTargetInfluences!==void 0&&(s.morphTargetInfluences=this.morphTargetInfluences.slice()),this.isInstancedMesh&&(s.type="InstancedMesh",s.count=this.count,s.instanceMatrix=this.instanceMatrix.toJSON(),this.instanceColor!==null&&(s.instanceColor=this.instanceColor.toJSON())),this.isBatchedMesh&&(s.type="BatchedMesh",s.perObjectFrustumCulled=this.perObjectFrustumCulled,s.sortObjects=this.sortObjects,s.drawRanges=this._drawRanges,s.reservedRanges=this._reservedRanges,s.geometryInfo=this._geometryInfo.map(a=>({...a,boundingBox:a.boundingBox?a.boundingBox.toJSON():void 0,boundingSphere:a.boundingSphere?a.boundingSphere.toJSON():void 0})),s.instanceInfo=this._instanceInfo.map(a=>({...a})),s.availableInstanceIds=this._availableInstanceIds.slice(),s.availableGeometryIds=this._availableGeometryIds.slice(),s.nextIndexStart=this._nextIndexStart,s.nextVertexStart=this._nextVertexStart,s.geometryCount=this._geometryCount,s.maxInstanceCount=this._maxInstanceCount,s.maxVertexCount=this._maxVertexCount,s.maxIndexCount=this._maxIndexCount,s.geometryInitialized=this._geometryInitialized,s.matricesTexture=this._matricesTexture.toJSON(t),s.indirectTexture=this._indirectTexture.toJSON(t),this._colorsTexture!==null&&(s.colorsTexture=this._colorsTexture.toJSON(t)),this.boundingSphere!==null&&(s.boundingSphere=this.boundingSphere.toJSON()),this.boundingBox!==null&&(s.boundingBox=this.boundingBox.toJSON()));function r(a,c){return a[c.uuid]===void 0&&(a[c.uuid]=c.toJSON(t)),c.uuid}if(d(r,"serialize"),this.isScene)this.background&&(this.background.isColor?s.background=this.background.toJSON():this.background.isTexture&&(s.background=this.background.toJSON(t).uuid)),this.environment&&this.environment.isTexture&&this.environment.isRenderTargetTexture!==!0&&(s.environment=this.environment.toJSON(t).uuid);else if(this.isMesh||this.isLine||this.isPoints){s.geometry=r(t.geometries,this.geometry);let a=this.geometry.parameters;if(a!==void 0&&a.shapes!==void 0){let c=a.shapes;if(Array.isArray(c))for(let l=0,u=c.length;l<u;l++){let h=c[l];r(t.shapes,h)}else r(t.shapes,c)}}if(this.isSkinnedMesh&&(s.bindMode=this.bindMode,s.bindMatrix=this.bindMatrix.toArray(),this.skeleton!==void 0&&(r(t.skeletons,this.skeleton),s.skeleton=this.skeleton.uuid)),this.material!==void 0)if(Array.isArray(this.material)){let a=[];for(let c=0,l=this.material.length;c<l;c++)a.push(r(t.materials,this.material[c]));s.material=a}else s.material=r(t.materials,this.material);if(this.children.length>0){s.children=[];for(let a=0;a<this.children.length;a++)s.children.push(this.children[a].toJSON(t).object)}if(this.animations.length>0){s.animations=[];for(let a=0;a<this.animations.length;a++){let c=this.animations[a];s.animations.push(r(t.animations,c))}}if(e){let a=o(t.geometries),c=o(t.materials),l=o(t.textures),u=o(t.images),h=o(t.shapes),f=o(t.skeletons),p=o(t.animations),m=o(t.nodes);a.length>0&&(i.geometries=a),c.length>0&&(i.materials=c),l.length>0&&(i.textures=l),u.length>0&&(i.images=u),h.length>0&&(i.shapes=h),f.length>0&&(i.skeletons=f),p.length>0&&(i.animations=p),m.length>0&&(i.nodes=m)}return i.object=s,i;function o(a){let c=[];for(let l in a){let u=a[l];delete u.metadata,c.push(u)}return c}d(o,"extractFromCache")}clone(t){return new this.constructor().copy(this,t)}copy(t,e=!0){if(this.name=t.name,this.up.copy(t.up),this.position.copy(t.position),this.rotation.order=t.rotation.order,this.quaternion.copy(t.quaternion),this.scale.copy(t.scale),this.pivot=t.pivot!==null?t.pivot.clone():null,this.matrix.copy(t.matrix),this.matrixWorld.copy(t.matrixWorld),this.matrixAutoUpdate=t.matrixAutoUpdate,this.matrixWorldAutoUpdate=t.matrixWorldAutoUpdate,this.matrixWorldNeedsUpdate=t.matrixWorldNeedsUpdate,this.layers.mask=t.layers.mask,this.visible=t.visible,this.castShadow=t.castShadow,this.receiveShadow=t.receiveShadow,this.frustumCulled=t.frustumCulled,this.renderOrder=t.renderOrder,this.static=t.static,this.animations=t.animations.slice(),this.userData=JSON.parse(JSON.stringify(t.userData)),e===!0)for(let i=0;i<t.children.length;i++){let s=t.children[i];this.add(s.clone())}return this}dispose(){this.dispatchEvent({type:"dispose"})}};Te.DEFAULT_UP=new k(0,1,0);Te.DEFAULT_MATRIX_AUTO_UPDATE=!0;Te.DEFAULT_MATRIX_WORLD_AUTO_UPDATE=!0;var yo={aliceblue:15792383,antiquewhite:16444375,aqua:65535,aquamarine:8388564,azure:15794175,beige:16119260,bisque:16770244,black:0,blanchedalmond:16772045,blue:255,blueviolet:9055202,brown:10824234,burlywood:14596231,cadetblue:6266528,chartreuse:8388352,chocolate:13789470,coral:16744272,cornflowerblue:6591981,cornsilk:16775388,crimson:14423100,cyan:65535,darkblue:139,darkcyan:35723,darkgoldenrod:12092939,darkgray:11119017,darkgreen:25600,darkgrey:11119017,darkkhaki:12433259,darkmagenta:9109643,darkolivegreen:5597999,darkorange:16747520,darkorchid:10040012,darkred:9109504,darksalmon:15308410,darkseagreen:9419919,darkslateblue:4734347,darkslategray:3100495,darkslategrey:3100495,darkturquoise:52945,darkviolet:9699539,deeppink:16716947,deepskyblue:49151,dimgray:6908265,dimgrey:6908265,dodgerblue:2003199,firebrick:11674146,floralwhite:16775920,forestgreen:2263842,fuchsia:16711935,gainsboro:14474460,ghostwhite:16316671,gold:16766720,goldenrod:14329120,gray:8421504,green:32768,greenyellow:11403055,grey:8421504,honeydew:15794160,hotpink:16738740,indianred:13458524,indigo:4915330,ivory:16777200,khaki:15787660,lavender:15132410,lavenderblush:16773365,lawngreen:8190976,lemonchiffon:16775885,lightblue:11393254,lightcoral:15761536,lightcyan:14745599,lightgoldenrodyellow:16448210,lightgray:13882323,lightgreen:9498256,lightgrey:13882323,lightpink:16758465,lightsalmon:16752762,lightseagreen:2142890,lightskyblue:8900346,lightslategray:7833753,lightslategrey:7833753,lightsteelblue:11584734,lightyellow:16777184,lime:65280,limegreen:3329330,linen:16445670,magenta:16711935,maroon:8388608,mediumaquamarine:6737322,mediumblue:205,mediumorchid:12211667,mediumpurple:9662683,mediumseagreen:3978097,mediumslateblue:8087790,mediumspringgreen:64154,mediumturquoise:4772300,mediumvioletred:13047173,midnightblue:1644912,mintcream:16121850,mistyrose:16770273,moccasin:16770229,navajowhite:16768685,navy:128,oldlace:16643558,olive:8421376,olivedrab:7048739,orange:16753920,orangered:16729344,orchid:14315734,palegoldenrod:15657130,palegreen:10025880,paleturquoise:11529966,palevioletred:14381203,papayawhip:16773077,peachpuff:16767673,peru:13468991,pink:16761035,plum:14524637,powderblue:11591910,purple:8388736,rebeccapurple:6697881,red:16711680,rosybrown:12357519,royalblue:4286945,saddlebrown:9127187,salmon:16416882,sandybrown:16032864,seagreen:3050327,seashell:16774638,sienna:10506797,silver:12632256,skyblue:8900331,slateblue:6970061,slategray:7372944,slategrey:7372944,snow:16775930,springgreen:65407,steelblue:4620980,tan:13808780,teal:32896,thistle:14204888,tomato:16737095,turquoise:4251856,violet:15631086,wheat:16113331,white:16777215,whitesmoke:16119285,yellow:16776960,yellowgreen:10145074},le={h:0,s:0,l:0},ti={h:0,s:0,l:0};function ns(n,t,e){return e<0&&(e+=1),e>1&&(e-=1),e<1/6?n+(t-n)*6*e:e<1/2?t:e<2/3?n+(t-n)*6*(2/3-e):n}d(ns,"hue2rgb");var yt=class{static{d(this,"Color")}constructor(t,e,i){return this.isColor=!0,this.r=1,this.g=1,this.b=1,this.set(t,e,i)}set(t,e,i){if(e===void 0&&i===void 0){let s=t;s&&s.isColor?this.copy(s):typeof s=="number"?this.setHex(s):typeof s=="string"&&this.setStyle(s)}else this.setRGB(t,e,i);return this}setScalar(t){return this.r=t,this.g=t,this.b=t,this}setHex(t,e=Gt){return t=Math.floor(t),this.r=(t>>16&255)/255,this.g=(t>>8&255)/255,this.b=(t&255)/255,Vt.colorSpaceToWorking(this,e),this}setRGB(t,e,i,s=Vt.workingColorSpace){return this.r=t,this.g=e,this.b=i,Vt.colorSpaceToWorking(this,s),this}setHSL(t,e,i,s=Vt.workingColorSpace){if(t=Dc(t,1),e=K(e,0,1),i=K(i,0,1),e===0)this.r=this.g=this.b=i;else{let r=i<=.5?i*(1+e):i+e-i*e,o=2*i-r;this.r=ns(o,r,t+1/3),this.g=ns(o,r,t),this.b=ns(o,r,t-1/3)}return Vt.colorSpaceToWorking(this,s),this}setStyle(t,e=Gt){function i(r){r!==void 0&&parseFloat(r)<1&&gt("Color: Alpha component of "+t+" will be ignored.")}d(i,"handleAlpha");let s;if(s=/^(\w+)\(([^\)]*)\)/.exec(t)){let r,o=s[1],a=s[2];switch(o){case"rgb":case"rgba":if(r=/^\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(a))return i(r[4]),this.setRGB(Math.min(255,parseInt(r[1],10))/255,Math.min(255,parseInt(r[2],10))/255,Math.min(255,parseInt(r[3],10))/255,e);if(r=/^\s*(\d+)\%\s*,\s*(\d+)\%\s*,\s*(\d+)\%\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(a))return i(r[4]),this.setRGB(Math.min(100,parseInt(r[1],10))/100,Math.min(100,parseInt(r[2],10))/100,Math.min(100,parseInt(r[3],10))/100,e);break;case"hsl":case"hsla":if(r=/^\s*(\d*\.?\d+)\s*,\s*(\d*\.?\d+)\%\s*,\s*(\d*\.?\d+)\%\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(a))return i(r[4]),this.setHSL(parseFloat(r[1])/360,parseFloat(r[2])/100,parseFloat(r[3])/100,e);break;default:gt("Color: Unknown color model "+t)}}else if(s=/^\#([A-Fa-f\d]+)$/.exec(t)){let r=s[1],o=r.length;if(o===3)return this.setRGB(parseInt(r.charAt(0),16)/15,parseInt(r.charAt(1),16)/15,parseInt(r.charAt(2),16)/15,e);if(o===6)return this.setHex(parseInt(r,16),e);gt("Color: Invalid hex color "+t)}else if(t&&t.length>0)return this.setColorName(t,e);return this}setColorName(t,e=Gt){let i=yo[t.toLowerCase()];return i!==void 0?this.setHex(i,e):gt("Color: Unknown color "+t),this}clone(){return new this.constructor(this.r,this.g,this.b)}copy(t){return this.r=t.r,this.g=t.g,this.b=t.b,this}copySRGBToLinear(t){return this.r=ne(t.r),this.g=ne(t.g),this.b=ne(t.b),this}copyLinearToSRGB(t){return this.r=Je(t.r),this.g=Je(t.g),this.b=Je(t.b),this}convertSRGBToLinear(){return this.copySRGBToLinear(this),this}convertLinearToSRGB(){return this.copyLinearToSRGB(this),this}getHex(t=Gt){return Vt.workingToColorSpace(bt.copy(this),t),Math.round(K(bt.r*255,0,255))*65536+Math.round(K(bt.g*255,0,255))*256+Math.round(K(bt.b*255,0,255))}getHexString(t=Gt){return("000000"+this.getHex(t).toString(16)).slice(-6)}getHSL(t,e=Vt.workingColorSpace){Vt.workingToColorSpace(bt.copy(this),e);let i=bt.r,s=bt.g,r=bt.b,o=Math.max(i,s,r),a=Math.min(i,s,r),c,l,u=(a+o)/2;if(a===o)c=0,l=0;else{let h=o-a;switch(l=u<=.5?h/(o+a):h/(2-o-a),o){case i:c=(s-r)/h+(s<r?6:0);break;case s:c=(r-i)/h+2;break;case r:c=(i-s)/h+4;break}c/=6}return t.h=c,t.s=l,t.l=u,t}getRGB(t,e=Vt.workingColorSpace){return Vt.workingToColorSpace(bt.copy(this),e),t.r=bt.r,t.g=bt.g,t.b=bt.b,t}getStyle(t=Gt){Vt.workingToColorSpace(bt.copy(this),t);let e=bt.r,i=bt.g,s=bt.b;return t!==Gt?`color(${t} ${e.toFixed(3)} ${i.toFixed(3)} ${s.toFixed(3)})`:`rgb(${Math.round(e*255)},${Math.round(i*255)},${Math.round(s*255)})`}offsetHSL(t,e,i){return this.getHSL(le),this.setHSL(le.h+t,le.s+e,le.l+i)}add(t){return this.r+=t.r,this.g+=t.g,this.b+=t.b,this}addColors(t,e){return this.r=t.r+e.r,this.g=t.g+e.g,this.b=t.b+e.b,this}addScalar(t){return this.r+=t,this.g+=t,this.b+=t,this}sub(t){return this.r=Math.max(0,this.r-t.r),this.g=Math.max(0,this.g-t.g),this.b=Math.max(0,this.b-t.b),this}multiply(t){return this.r*=t.r,this.g*=t.g,this.b*=t.b,this}multiplyScalar(t){return this.r*=t,this.g*=t,this.b*=t,this}lerp(t,e){return this.r+=(t.r-this.r)*e,this.g+=(t.g-this.g)*e,this.b+=(t.b-this.b)*e,this}lerpColors(t,e,i){return this.r=t.r+(e.r-t.r)*i,this.g=t.g+(e.g-t.g)*i,this.b=t.b+(e.b-t.b)*i,this}lerpHSL(t,e){this.getHSL(le),t.getHSL(ti);let i=Ji(le.h,ti.h,e),s=Ji(le.s,ti.s,e),r=Ji(le.l,ti.l,e);return this.setHSL(i,s,r),this}setFromVector3(t){return this.r=t.x,this.g=t.y,this.b=t.z,this}applyMatrix3(t){let e=this.r,i=this.g,s=this.b,r=t.elements;return this.r=r[0]*e+r[3]*i+r[6]*s,this.g=r[1]*e+r[4]*i+r[7]*s,this.b=r[2]*e+r[5]*i+r[8]*s,this}equals(t){return t.r===this.r&&t.g===this.g&&t.b===this.b}fromArray(t,e=0){return this.r=t[e],this.g=t[e+1],this.b=t[e+2],this}toArray(t=[],e=0){return t[e]=this.r,t[e+1]=this.g,t[e+2]=this.b,t}fromBufferAttribute(t,e){return this.r=t.getX(e),this.g=t.getY(e),this.b=t.getZ(e),this}toJSON(){return this.getHex()}*[Symbol.iterator](){yield this.r,yield this.g,yield this.b}},bt=new yt;yt.NAMES=yo;var fe=class{static{d(this,"Box3")}constructor(t=new k(1/0,1/0,1/0),e=new k(-1/0,-1/0,-1/0)){this.isBox3=!0,this.min=t,this.max=e}set(t,e){return this.min.copy(t),this.max.copy(e),this}setFromArray(t){this.makeEmpty();for(let e=0,i=t.length;e<i;e+=3)this.expandByPoint($t.fromArray(t,e));return this}setFromBufferAttribute(t){this.makeEmpty();for(let e=0,i=t.count;e<i;e++)this.expandByPoint($t.fromBufferAttribute(t,e));return this}setFromPoints(t){this.makeEmpty();for(let e=0,i=t.length;e<i;e++)this.expandByPoint(t[e]);return this}setFromCenterAndSize(t,e){let i=$t.copy(e).multiplyScalar(.5);return this.min.copy(t).sub(i),this.max.copy(t).add(i),this}setFromObject(t,e=!1){return this.makeEmpty(),this.expandByObject(t,e)}clone(){return new this.constructor().copy(this)}copy(t){return this.min.copy(t.min),this.max.copy(t.max),this}makeEmpty(){return this.min.x=this.min.y=this.min.z=1/0,this.max.x=this.max.y=this.max.z=-1/0,this}isEmpty(){return this.max.x<this.min.x||this.max.y<this.min.y||this.max.z<this.min.z}getCenter(t){return this.isEmpty()?t.set(0,0,0):t.addVectors(this.min,this.max).multiplyScalar(.5)}getSize(t){return this.isEmpty()?t.set(0,0,0):t.subVectors(this.max,this.min)}expandByPoint(t){return this.min.min(t),this.max.max(t),this}expandByVector(t){return this.min.sub(t),this.max.add(t),this}expandByScalar(t){return this.min.addScalar(-t),this.max.addScalar(t),this}expandByObject(t,e=!1){t.updateWorldMatrix(!1,!1);let i=t.geometry;if(i!==void 0){let r=i.getAttribute("position");if(e===!0&&r!==void 0&&t.isInstancedMesh!==!0)for(let o=0,a=r.count;o<a;o++)t.isMesh===!0?t.getVertexPosition(o,$t):$t.fromBufferAttribute(r,o),$t.applyMatrix4(t.matrixWorld),this.expandByPoint($t);else t.boundingBox!==void 0?(t.boundingBox===null&&t.computeBoundingBox(),ei.copy(t.boundingBox)):(i.boundingBox===null&&i.computeBoundingBox(),ei.copy(i.boundingBox)),ei.applyMatrix4(t.matrixWorld),this.union(ei)}let s=t.children;for(let r=0,o=s.length;r<o;r++)this.expandByObject(s[r],e);return this}containsPoint(t){return t.x>=this.min.x&&t.x<=this.max.x&&t.y>=this.min.y&&t.y<=this.max.y&&t.z>=this.min.z&&t.z<=this.max.z}containsBox(t){return this.min.x<=t.min.x&&t.max.x<=this.max.x&&this.min.y<=t.min.y&&t.max.y<=this.max.y&&this.min.z<=t.min.z&&t.max.z<=this.max.z}getParameter(t,e){return e.set((t.x-this.min.x)/(this.max.x-this.min.x),(t.y-this.min.y)/(this.max.y-this.min.y),(t.z-this.min.z)/(this.max.z-this.min.z))}intersectsBox(t){return t.max.x>=this.min.x&&t.min.x<=this.max.x&&t.max.y>=this.min.y&&t.min.y<=this.max.y&&t.max.z>=this.min.z&&t.min.z<=this.max.z}intersectsSphere(t){return this.clampPoint(t.center,$t),$t.distanceToSquared(t.center)<=t.radius*t.radius}intersectsPlane(t){let e,i;return t.normal.x>0?(e=t.normal.x*this.min.x,i=t.normal.x*this.max.x):(e=t.normal.x*this.max.x,i=t.normal.x*this.min.x),t.normal.y>0?(e+=t.normal.y*this.min.y,i+=t.normal.y*this.max.y):(e+=t.normal.y*this.max.y,i+=t.normal.y*this.min.y),t.normal.z>0?(e+=t.normal.z*this.min.z,i+=t.normal.z*this.max.z):(e+=t.normal.z*this.max.z,i+=t.normal.z*this.min.z),e<=-t.constant&&i>=-t.constant}intersectsTriangle(t){if(this.isEmpty())return!1;this.getCenter(vn),ni.subVectors(this.max,vn),We.subVectors(t.a,vn),Xe.subVectors(t.b,vn),qe.subVectors(t.c,vn),ue.subVectors(Xe,We),he.subVectors(qe,Xe),be.subVectors(We,qe);let e=[0,-ue.z,ue.y,0,-he.z,he.y,0,-be.z,be.y,ue.z,0,-ue.x,he.z,0,-he.x,be.z,0,-be.x,-ue.y,ue.x,0,-he.y,he.x,0,-be.y,be.x,0];return!is(e,We,Xe,qe,ni)||(e=[1,0,0,0,1,0,0,0,1],!is(e,We,Xe,qe,ni))?!1:(ii.crossVectors(ue,he),e=[ii.x,ii.y,ii.z],is(e,We,Xe,qe,ni))}clampPoint(t,e){return e.copy(t).clamp(this.min,this.max)}distanceToPoint(t){return this.clampPoint(t,$t).distanceTo(t)}getBoundingSphere(t){return this.isEmpty()?t.makeEmpty():(this.getCenter(t.center),t.radius=this.getSize($t).length()*.5),t}intersect(t){return this.min.max(t.min),this.max.min(t.max),this.isEmpty()&&this.makeEmpty(),this}union(t){return this.min.min(t.min),this.max.max(t.max),this}applyMatrix4(t){return this.isEmpty()?this:(ee[0].set(this.min.x,this.min.y,this.min.z).applyMatrix4(t),ee[1].set(this.min.x,this.min.y,this.max.z).applyMatrix4(t),ee[2].set(this.min.x,this.max.y,this.min.z).applyMatrix4(t),ee[3].set(this.min.x,this.max.y,this.max.z).applyMatrix4(t),ee[4].set(this.max.x,this.min.y,this.min.z).applyMatrix4(t),ee[5].set(this.max.x,this.min.y,this.max.z).applyMatrix4(t),ee[6].set(this.max.x,this.max.y,this.min.z).applyMatrix4(t),ee[7].set(this.max.x,this.max.y,this.max.z).applyMatrix4(t),this.setFromPoints(ee),this)}translate(t){return this.min.add(t),this.max.add(t),this}equals(t){return t.min.equals(this.min)&&t.max.equals(this.max)}toJSON(){return{min:this.min.toArray(),max:this.max.toArray()}}fromJSON(t){return this.min.fromArray(t.min),this.max.fromArray(t.max),this}},ee=[new k,new k,new k,new k,new k,new k,new k,new k],$t=new k,ei=new fe,We=new k,Xe=new k,qe=new k,ue=new k,he=new k,be=new k,vn=new k,ni=new k,ii=new k,we=new k;function is(n,t,e,i,s){for(let r=0,o=n.length-3;r<=o;r+=3){we.fromArray(n,r);let a=s.x*Math.abs(we.x)+s.y*Math.abs(we.y)+s.z*Math.abs(we.z),c=t.dot(we),l=e.dot(we),u=i.dot(we);if(Math.max(-Math.max(c,l,u),Math.min(c,l,u))>a)return!1}return!0}d(is,"satForAxes");var ut=new k,si=new _t,Wc=0,Ut=class extends Ae{static{d(this,"BufferAttribute")}constructor(t,e,i=!1){if(super(),Array.isArray(t))throw new TypeError("THREE.BufferAttribute: array should be a Typed Array.");this.isBufferAttribute=!0,Object.defineProperty(this,"id",{value:Wc++}),this.name="",this.array=t,this.itemSize=e,this.count=t!==void 0?t.length/e:0,this.normalized=i,this.usage=_o,this.updateRanges=[],this.gpuType=mo,this.version=0}onUploadCallback(){}set needsUpdate(t){t===!0&&this.version++}setUsage(t){return this.usage=t,this}addUpdateRange(t,e){this.updateRanges.push({start:t,count:e})}clearUpdateRanges(){this.updateRanges.length=0}copy(t){return this.name=t.name,this.array=new t.array.constructor(t.array),this.itemSize=t.itemSize,this.count=t.count,this.normalized=t.normalized,this.usage=t.usage,this.gpuType=t.gpuType,this}copyAt(t,e,i){t*=this.itemSize,i*=e.itemSize;for(let s=0,r=this.itemSize;s<r;s++)this.array[t+s]=e.array[i+s];return this}copyArray(t){return this.array.set(t),this}applyMatrix3(t){if(this.itemSize===2)for(let e=0,i=this.count;e<i;e++)si.fromBufferAttribute(this,e),si.applyMatrix3(t),this.setXY(e,si.x,si.y);else if(this.itemSize===3)for(let e=0,i=this.count;e<i;e++)ut.fromBufferAttribute(this,e),ut.applyMatrix3(t),this.setXYZ(e,ut.x,ut.y,ut.z);return this}applyMatrix4(t){for(let e=0,i=this.count;e<i;e++)ut.fromBufferAttribute(this,e),ut.applyMatrix4(t),this.setXYZ(e,ut.x,ut.y,ut.z);return this}applyNormalMatrix(t){for(let e=0,i=this.count;e<i;e++)ut.fromBufferAttribute(this,e),ut.applyNormalMatrix(t),this.setXYZ(e,ut.x,ut.y,ut.z);return this}transformDirection(t){for(let e=0,i=this.count;e<i;e++)ut.fromBufferAttribute(this,e),ut.transformDirection(t),this.setXYZ(e,ut.x,ut.y,ut.z);return this}set(t,e=0){return this.array.set(t,e),this}getComponent(t,e){let i=this.array[t*this.itemSize+e];return this.normalized&&(i=xn(i,this.array)),i}setComponent(t,e,i){return this.normalized&&(i=Et(i,this.array)),this.array[t*this.itemSize+e]=i,this}getX(t){let e=this.array[t*this.itemSize];return this.normalized&&(e=xn(e,this.array)),e}setX(t,e){return this.normalized&&(e=Et(e,this.array)),this.array[t*this.itemSize]=e,this}getY(t){let e=this.array[t*this.itemSize+1];return this.normalized&&(e=xn(e,this.array)),e}setY(t,e){return this.normalized&&(e=Et(e,this.array)),this.array[t*this.itemSize+1]=e,this}getZ(t){let e=this.array[t*this.itemSize+2];return this.normalized&&(e=xn(e,this.array)),e}setZ(t,e){return this.normalized&&(e=Et(e,this.array)),this.array[t*this.itemSize+2]=e,this}getW(t){let e=this.array[t*this.itemSize+3];return this.normalized&&(e=xn(e,this.array)),e}setW(t,e){return this.normalized&&(e=Et(e,this.array)),this.array[t*this.itemSize+3]=e,this}setXY(t,e,i){return t*=this.itemSize,this.normalized&&(e=Et(e,this.array),i=Et(i,this.array)),this.array[t+0]=e,this.array[t+1]=i,this}setXYZ(t,e,i,s){return t*=this.itemSize,this.normalized&&(e=Et(e,this.array),i=Et(i,this.array),s=Et(s,this.array)),this.array[t+0]=e,this.array[t+1]=i,this.array[t+2]=s,this}setXYZW(t,e,i,s,r){return t*=this.itemSize,this.normalized&&(e=Et(e,this.array),i=Et(i,this.array),s=Et(s,this.array),r=Et(r,this.array)),this.array[t+0]=e,this.array[t+1]=i,this.array[t+2]=s,this.array[t+3]=r,this}onUpload(t){return this.onUploadCallback=t,this}clone(){return new this.constructor(this.array,this.itemSize).copy(this)}toJSON(){let t={itemSize:this.itemSize,type:this.array.constructor.name,array:Array.from(this.array),normalized:this.normalized};return t.name=this.name,t.usage=this.usage,t.gpuType=this.gpuType,t}dispose(){this.dispatchEvent({type:"dispose"})}};var pi=class extends Ut{static{d(this,"Uint16BufferAttribute")}constructor(t,e,i){super(new Uint16Array(t),e,i)}};var mi=class extends Ut{static{d(this,"Uint32BufferAttribute")}constructor(t,e,i){super(new Uint32Array(t),e,i)}};var de=class extends Ut{static{d(this,"Float32BufferAttribute")}constructor(t,e,i){super(new Float32Array(t),e,i)}},Xc=new fe,Sn=new k,ss=new k,gi=class{static{d(this,"Sphere")}constructor(t=new k,e=-1){this.isSphere=!0,this.center=t,this.radius=e}set(t,e){return this.center.copy(t),this.radius=e,this}setFromPoints(t,e){let i=this.center;e!==void 0?i.copy(e):Xc.setFromPoints(t).getCenter(i);let s=0;for(let r=0,o=t.length;r<o;r++)s=Math.max(s,i.distanceToSquared(t[r]));return this.radius=Math.sqrt(s),this}copy(t){return this.center.copy(t.center),this.radius=t.radius,this}isEmpty(){return this.radius<0}makeEmpty(){return this.center.set(0,0,0),this.radius=-1,this}containsPoint(t){return t.distanceToSquared(this.center)<=this.radius*this.radius}distanceToPoint(t){return t.distanceTo(this.center)-this.radius}intersectsSphere(t){let e=this.radius+t.radius;return t.center.distanceToSquared(this.center)<=e*e}intersectsBox(t){return t.intersectsSphere(this)}intersectsPlane(t){return Math.abs(t.distanceToPoint(this.center))<=this.radius}clampPoint(t,e){let i=this.center.distanceToSquared(t);return e.copy(t),i>this.radius*this.radius&&(e.sub(this.center).normalize(),e.multiplyScalar(this.radius).add(this.center)),e}getBoundingBox(t){return this.isEmpty()?(t.makeEmpty(),t):(t.set(this.center,this.center),t.expandByScalar(this.radius),t)}applyMatrix4(t){return this.center.applyMatrix4(t),this.radius=this.radius*t.getMaxScaleOnAxis(),this}translate(t){return this.center.add(t),this}expandByPoint(t){if(this.isEmpty())return this.center.copy(t),this.radius=0,this;Sn.subVectors(t,this.center);let e=Sn.lengthSq();if(e>this.radius*this.radius){let i=Math.sqrt(e),s=(i-this.radius)*.5;this.center.addScaledVector(Sn,s/i),this.radius+=s}return this}union(t){return t.isEmpty()?this:this.isEmpty()?(this.copy(t),this):(this.center.equals(t.center)===!0?this.radius=Math.max(this.radius,t.radius):(ss.subVectors(t.center,this.center).setLength(t.radius),this.expandByPoint(Sn.copy(t.center).add(ss)),this.expandByPoint(Sn.copy(t.center).sub(ss))),this)}equals(t){return t.center.equals(this.center)&&t.radius===this.radius}clone(){return new this.constructor().copy(this)}toJSON(){return{radius:this.radius,center:this.center.toArray()}}fromJSON(t){return this.radius=t.radius,this.center.fromArray(t.center),this}},qc=0,kt=new xt,rs=new Te,$e=new k,Dt=new fe,Mn=new fe,mt=new k,je=class n extends Ae{static{d(this,"BufferGeometry")}constructor(){super(),this.isBufferGeometry=!0,Object.defineProperty(this,"id",{value:qc++}),this.uuid=Ei(),this.name="",this.type="BufferGeometry",this.index=null,this.indirect=null,this.indirectOffset=0,this.attributes={},this.morphAttributes={},this.morphTargetsRelative=!1,this.groups=[],this.boundingBox=null,this.boundingSphere=null,this.drawRange={start:0,count:1/0},this.userData={},this._transformed=!1}getIndex(){return this.index}setIndex(t){return Array.isArray(t)?this.index=new(Ic(t)?mi:pi)(t,1):this.index=t,this}setIndirect(t,e=0){return this.indirect=t,this.indirectOffset=e,this}getIndirect(){return this.indirect}getAttribute(t){return this.attributes[t]}setAttribute(t,e){return this.attributes[t]=e,this}deleteAttribute(t){return delete this.attributes[t],this}hasAttribute(t){return this.attributes[t]!==void 0}addGroup(t,e,i=0){this.groups.push({start:t,count:e,materialIndex:i})}clearGroups(){this.groups=[]}setDrawRange(t,e){this.drawRange.start=t,this.drawRange.count=e}applyMatrix4(t){let e=this.attributes.position;e!==void 0&&(e.applyMatrix4(t),e.needsUpdate=!0);let i=this.attributes.normal;if(i!==void 0){let r=new Y().getNormalMatrix(t);i.applyNormalMatrix(r),i.needsUpdate=!0}let s=this.attributes.tangent;return s!==void 0&&(s.transformDirection(t),s.needsUpdate=!0),this.boundingBox!==null&&this.computeBoundingBox(),this.boundingSphere!==null&&this.computeBoundingSphere(),this._transformed=!0,this}applyQuaternion(t){return kt.makeRotationFromQuaternion(t),this.applyMatrix4(kt),this}rotateX(t){return kt.makeRotationX(t),this.applyMatrix4(kt),this}rotateY(t){return kt.makeRotationY(t),this.applyMatrix4(kt),this}rotateZ(t){return kt.makeRotationZ(t),this.applyMatrix4(kt),this}translate(t,e,i){return kt.makeTranslation(t,e,i),this.applyMatrix4(kt),this}scale(t,e,i){return kt.makeScale(t,e,i),this.applyMatrix4(kt),this}lookAt(t){return rs.lookAt(t),rs.updateMatrix(),this.applyMatrix4(rs.matrix),this}center(){return this.computeBoundingBox(),this.boundingBox.getCenter($e).negate(),this.translate($e.x,$e.y,$e.z),this}setFromPoints(t){let e=this.getAttribute("position");if(e===void 0){let i=[];for(let s=0,r=t.length;s<r;s++){let o=t[s];i.push(o.x,o.y,o.z||0)}this.setAttribute("position",new de(i,3))}else{let i=Math.min(t.length,e.count);for(let s=0;s<i;s++){let r=t[s];e.setXYZ(s,r.x,r.y,r.z||0)}t.length>e.count&&gt("BufferGeometry: Buffer size too small for points data. Use .dispose() and create a new geometry."),e.needsUpdate=!0}return this}computeBoundingBox(){this.boundingBox===null&&(this.boundingBox=new fe);let t=this.attributes.position,e=this.morphAttributes.position;if(t&&t.isGLBufferAttribute){ot("BufferGeometry.computeBoundingBox(): GLBufferAttribute requires a manual bounding box.",this),this.boundingBox.set(new k(-1/0,-1/0,-1/0),new k(1/0,1/0,1/0));return}if(t!==void 0){if(this.boundingBox.setFromBufferAttribute(t),e)for(let i=0,s=e.length;i<s;i++){let r=e[i];Dt.setFromBufferAttribute(r),this.morphTargetsRelative?(mt.addVectors(this.boundingBox.min,Dt.min),this.boundingBox.expandByPoint(mt),mt.addVectors(this.boundingBox.max,Dt.max),this.boundingBox.expandByPoint(mt)):(this.boundingBox.expandByPoint(Dt.min),this.boundingBox.expandByPoint(Dt.max))}}else this.boundingBox.makeEmpty();(isNaN(this.boundingBox.min.x)||isNaN(this.boundingBox.min.y)||isNaN(this.boundingBox.min.z))&&ot('BufferGeometry.computeBoundingBox(): Computed min/max have NaN values. The "position" attribute is likely to have NaN values.',this)}computeBoundingSphere(){this.boundingSphere===null&&(this.boundingSphere=new gi);let t=this.attributes.position,e=this.morphAttributes.position;if(t&&t.isGLBufferAttribute){ot("BufferGeometry.computeBoundingSphere(): GLBufferAttribute requires a manual bounding sphere.",this),this.boundingSphere.set(new k,1/0);return}if(t){let i=this.boundingSphere.center;if(Dt.setFromBufferAttribute(t),e)for(let r=0,o=e.length;r<o;r++){let a=e[r];Mn.setFromBufferAttribute(a),this.morphTargetsRelative?(mt.addVectors(Dt.min,Mn.min),Dt.expandByPoint(mt),mt.addVectors(Dt.max,Mn.max),Dt.expandByPoint(mt)):(Dt.expandByPoint(Mn.min),Dt.expandByPoint(Mn.max))}Dt.getCenter(i);let s=0;for(let r=0,o=t.count;r<o;r++)mt.fromBufferAttribute(t,r),s=Math.max(s,i.distanceToSquared(mt));if(e)for(let r=0,o=e.length;r<o;r++){let a=e[r],c=this.morphTargetsRelative;for(let l=0,u=a.count;l<u;l++)mt.fromBufferAttribute(a,l),c&&($e.fromBufferAttribute(t,l),mt.add($e)),s=Math.max(s,i.distanceToSquared(mt))}this.boundingSphere.radius=Math.sqrt(s),isNaN(this.boundingSphere.radius)&&ot('BufferGeometry.computeBoundingSphere(): Computed radius is NaN. The "position" attribute is likely to have NaN values.',this)}}computeTangents(){let t=this.index,e=this.attributes;if(t===null||e.position===void 0||e.normal===void 0||e.uv===void 0){ot("BufferGeometry: .computeTangents() failed. Missing required attributes (index, position, normal or uv)");return}let i=e.position,s=e.normal,r=e.uv,o=this.getAttribute("tangent");(o===void 0||o.count!==i.count)&&(o=new Ut(new Float32Array(4*i.count),4),this.setAttribute("tangent",o));let a=[],c=[];for(let w=0;w<i.count;w++)a[w]=new k,c[w]=new k;let l=new k,u=new k,h=new k,f=new _t,p=new _t,m=new _t,g=new k,_=new k;function x(w,R,I){l.fromBufferAttribute(i,w),u.fromBufferAttribute(i,R),h.fromBufferAttribute(i,I),f.fromBufferAttribute(r,w),p.fromBufferAttribute(r,R),m.fromBufferAttribute(r,I),u.sub(l),h.sub(l),p.sub(f),m.sub(f);let N=1/(p.x*m.y-m.x*p.y);isFinite(N)&&(g.copy(u).multiplyScalar(m.y).addScaledVector(h,-p.y).multiplyScalar(N),_.copy(h).multiplyScalar(p.x).addScaledVector(u,-m.x).multiplyScalar(N),a[w].add(g),a[R].add(g),a[I].add(g),c[w].add(_),c[R].add(_),c[I].add(_))}d(x,"handleTriangle");let v=this.groups;v.length===0&&(v=[{start:0,count:t.count}]);for(let w=0,R=v.length;w<R;++w){let I=v[w],N=I.start,C=I.count;for(let T=N,P=N+C;T<P;T+=3)x(t.getX(T+0),t.getX(T+1),t.getX(T+2))}let y=new k,M=new k,A=new k,b=new k;function S(w){A.fromBufferAttribute(s,w),b.copy(A);let R=a[w];y.copy(R),y.sub(A.multiplyScalar(A.dot(R))).normalize(),M.crossVectors(b,R);let N=M.dot(c[w])<0?-1:1;o.setXYZW(w,y.x,y.y,y.z,N)}d(S,"handleVertex");for(let w=0,R=v.length;w<R;++w){let I=v[w],N=I.start,C=I.count;for(let T=N,P=N+C;T<P;T+=3)S(t.getX(T+0)),S(t.getX(T+1)),S(t.getX(T+2))}this._transformed=!0}computeVertexNormals(){let t=this.index,e=this.getAttribute("position");if(e!==void 0){let i=this.getAttribute("normal");if(i===void 0||i.count!==e.count)i=new Ut(new Float32Array(e.count*3),3),this.setAttribute("normal",i);else for(let f=0,p=i.count;f<p;f++)i.setXYZ(f,0,0,0);let s=new k,r=new k,o=new k,a=new k,c=new k,l=new k,u=new k,h=new k;if(t)for(let f=0,p=t.count;f<p;f+=3){let m=t.getX(f+0),g=t.getX(f+1),_=t.getX(f+2);s.fromBufferAttribute(e,m),r.fromBufferAttribute(e,g),o.fromBufferAttribute(e,_),u.subVectors(o,r),h.subVectors(s,r),u.cross(h),a.fromBufferAttribute(i,m),c.fromBufferAttribute(i,g),l.fromBufferAttribute(i,_),a.add(u),c.add(u),l.add(u),i.setXYZ(m,a.x,a.y,a.z),i.setXYZ(g,c.x,c.y,c.z),i.setXYZ(_,l.x,l.y,l.z)}else for(let f=0,p=e.count;f<p;f+=3)s.fromBufferAttribute(e,f+0),r.fromBufferAttribute(e,f+1),o.fromBufferAttribute(e,f+2),u.subVectors(o,r),h.subVectors(s,r),u.cross(h),i.setXYZ(f+0,u.x,u.y,u.z),i.setXYZ(f+1,u.x,u.y,u.z),i.setXYZ(f+2,u.x,u.y,u.z);this.normalizeNormals(),i.needsUpdate=!0}}normalizeNormals(){let t=this.attributes.normal;for(let e=0,i=t.count;e<i;e++)mt.fromBufferAttribute(t,e),mt.normalize(),t.setXYZ(e,mt.x,mt.y,mt.z)}toNonIndexed(){function t(a,c){let l=a.array,u=a.itemSize,h=a.normalized,f=new l.constructor(c.length*u),p=0,m=0;for(let g=0,_=c.length;g<_;g++){a.isInterleavedBufferAttribute?p=c[g]*a.data.stride+a.offset:p=c[g]*u;for(let x=0;x<u;x++)f[m++]=l[p++]}return new Ut(f,u,h)}if(d(t,"convertBufferAttribute"),this.index===null)return gt("BufferGeometry.toNonIndexed(): BufferGeometry is already non-indexed."),this;let e=new n,i=this.index.array,s=this.attributes;for(let a in s){let c=s[a],l=t(c,i);e.setAttribute(a,l)}let r=this.morphAttributes;for(let a in r){let c=[],l=r[a];for(let u=0,h=l.length;u<h;u++){let f=l[u],p=t(f,i);c.push(p)}e.morphAttributes[a]=c}e.morphTargetsRelative=this.morphTargetsRelative;let o=this.groups;for(let a=0,c=o.length;a<c;a++){let l=o[a];e.addGroup(l.start,l.count,l.materialIndex)}return e}toJSON(){let t={metadata:{version:4.7,type:"BufferGeometry",generator:"BufferGeometry.toJSON"}};if(t.uuid=this.uuid,t.type=this.parameters!==void 0&&this._transformed===!0?"BufferGeometry":this.type,t.name=this.name,Object.keys(this.userData).length>0&&(t.userData=this.userData),this.parameters!==void 0&&this._transformed!==!0){let c=this.parameters;for(let l in c)c[l]!==void 0&&(t[l]=c[l]);return t}t.data={attributes:{}};let e=this.index;e!==null&&(t.data.index={type:e.array.constructor.name,array:Array.prototype.slice.call(e.array)});let i=this.attributes;for(let c in i){let l=i[c];t.data.attributes[c]=l.toJSON(t.data)}let s={},r=!1;for(let c in this.morphAttributes){let l=this.morphAttributes[c],u=[];for(let h=0,f=l.length;h<f;h++){let p=l[h];u.push(p.toJSON(t.data))}u.length>0&&(s[c]=u,r=!0)}r&&(t.data.morphAttributes=s,t.data.morphTargetsRelative=this.morphTargetsRelative);let o=this.groups;o.length>0&&(t.data.groups=JSON.parse(JSON.stringify(o)));let a=this.boundingSphere;return a!==null&&(t.data.boundingSphere=a.toJSON()),t}clone(){return new this.constructor().copy(this)}copy(t){this.index=null,this.attributes={},this.morphAttributes={},this.groups=[],this.boundingBox=null,this.boundingSphere=null;let e={};this.name=t.name;let i=t.index;i!==null&&this.setIndex(i.clone());let s=t.attributes;for(let l in s){let u=s[l];this.setAttribute(l,u.clone(e))}let r=t.morphAttributes;for(let l in r){let u=[],h=r[l];for(let f=0,p=h.length;f<p;f++)u.push(h[f].clone(e));this.morphAttributes[l]=u}this.morphTargetsRelative=t.morphTargetsRelative;let o=t.groups;for(let l=0,u=o.length;l<u;l++){let h=o[l];this.addGroup(h.start,h.count,h.materialIndex)}let a=t.boundingBox;a!==null&&(this.boundingBox=a.clone());let c=t.boundingSphere;return c!==null&&(this.boundingSphere=c.clone()),this.drawRange.start=t.drawRange.start,this.drawRange.count=t.drawRange.count,this.userData=t.userData,this._transformed=t._transformed,this}dispose(){this.dispatchEvent({type:"dispose"})}};function $c(n,t,e=2){let i=t&&t.length,s=i?t[0]*e:n.length,r=vo(n,0,s,e,!0),o=[];if(!r||r.next===r.prev)return o;let a,c,l;if(i&&(r=jc(n,t,r,e)),n.length>80*e){a=n[0],c=n[1];let u=a,h=c;for(let f=e;f<s;f+=e){let p=n[f],m=n[f+1];p<a&&(a=p),m<c&&(c=m),p>u&&(u=p),m>h&&(h=m)}l=Math.max(u-a,h-c),l=l!==0?32767/l:0}return Cn(r,o,e,a,c,l,0),o}d($c,"earcut");function vo(n,t,e,i,s){let r;if(s===ll(n,t,e,i)>0)for(let o=t;o<e;o+=i)r=Qr(o/i|0,n[o],n[o+1],r);else for(let o=e-i;o>=t;o-=i)r=Qr(o/i|0,n[o],n[o+1],r);return r&&Qe(r,r.next)&&(In(r),r=r.next),r}d(vo,"linkedList");function Ee(n,t){if(!n)return n;t||(t=n);let e=n,i;do if(i=!1,!e.steiner&&(Qe(e,e.next)||at(e.prev,e,e.next)===0)){if(In(e),e=t=e.prev,e===e.next)break;i=!0}else e=e.next;while(i||e!==t);return t}d(Ee,"filterPoints");function Cn(n,t,e,i,s,r,o){if(!n)return;!o&&r&&il(n,i,s,r);let a=n;for(;n.prev!==n.next;){let c=n.prev,l=n.next;if(r?Zc(n,i,s,r):Yc(n)){t.push(c.i,n.i,l.i),In(n),n=l.next,a=l.next;continue}if(n=l,n===a){o?o===1?(n=Jc(Ee(n),t),Cn(n,t,e,i,s,r,2)):o===2&&Kc(n,t,e,i,s,r):Cn(Ee(n),t,e,i,s,r,1);break}}}d(Cn,"earcutLinked");function Yc(n){let t=n.prev,e=n,i=n.next;if(at(t,e,i)>=0)return!1;let s=t.x,r=e.x,o=i.x,a=t.y,c=e.y,l=i.y,u=Math.min(s,r,o),h=Math.min(a,c,l),f=Math.max(s,r,o),p=Math.max(a,c,l),m=i.next;for(;m!==t;){if(m.x>=u&&m.x<=f&&m.y>=h&&m.y<=p&&An(s,a,r,c,o,l,m.x,m.y)&&at(m.prev,m,m.next)>=0)return!1;m=m.next}return!0}d(Yc,"isEar");function Zc(n,t,e,i){let s=n.prev,r=n,o=n.next;if(at(s,r,o)>=0)return!1;let a=s.x,c=r.x,l=o.x,u=s.y,h=r.y,f=o.y,p=Math.min(a,c,l),m=Math.min(u,h,f),g=Math.max(a,c,l),_=Math.max(u,h,f),x=Ts(p,m,t,e,i),v=Ts(g,_,t,e,i),y=n.prevZ,M=n.nextZ;for(;y&&y.z>=x&&M&&M.z<=v;){if(y.x>=p&&y.x<=g&&y.y>=m&&y.y<=_&&y!==s&&y!==o&&An(a,u,c,h,l,f,y.x,y.y)&&at(y.prev,y,y.next)>=0||(y=y.prevZ,M.x>=p&&M.x<=g&&M.y>=m&&M.y<=_&&M!==s&&M!==o&&An(a,u,c,h,l,f,M.x,M.y)&&at(M.prev,M,M.next)>=0))return!1;M=M.nextZ}for(;y&&y.z>=x;){if(y.x>=p&&y.x<=g&&y.y>=m&&y.y<=_&&y!==s&&y!==o&&An(a,u,c,h,l,f,y.x,y.y)&&at(y.prev,y,y.next)>=0)return!1;y=y.prevZ}for(;M&&M.z<=v;){if(M.x>=p&&M.x<=g&&M.y>=m&&M.y<=_&&M!==s&&M!==o&&An(a,u,c,h,l,f,M.x,M.y)&&at(M.prev,M,M.next)>=0)return!1;M=M.nextZ}return!0}d(Zc,"isEarHashed");function Jc(n,t){let e=n;do{let i=e.prev,s=e.next.next;!Qe(i,s)&&Mo(i,e,e.next,s)&&Rn(i,s)&&Rn(s,i)&&(t.push(i.i,e.i,s.i),In(e),In(e.next),e=n=s),e=e.next}while(e!==n);return Ee(e)}d(Jc,"cureLocalIntersections");function Kc(n,t,e,i,s,r){let o=n;do{let a=o.next.next;for(;a!==o.prev;){if(o.i!==a.i&&ol(o,a)){let c=bo(o,a);o=Ee(o,o.next),c=Ee(c,c.next),Cn(o,t,e,i,s,r,0),Cn(c,t,e,i,s,r,0);return}a=a.next}o=o.next}while(o!==n)}d(Kc,"splitEarcut");function jc(n,t,e,i){let s=[];for(let r=0,o=t.length;r<o;r++){let a=t[r]*i,c=r<o-1?t[r+1]*i:n.length,l=vo(n,a,c,i,!1);l===l.next&&(l.steiner=!0),s.push(rl(l))}s.sort(Qc);for(let r=0;r<s.length;r++)e=tl(s[r],e);return e}d(jc,"eliminateHoles");function Qc(n,t){let e=n.x-t.x;if(e===0&&(e=n.y-t.y,e===0)){let i=(n.next.y-n.y)/(n.next.x-n.x),s=(t.next.y-t.y)/(t.next.x-t.x);e=i-s}return e}d(Qc,"compareXYSlope");function tl(n,t){let e=el(n,t);if(!e)return t;let i=bo(e,n);return Ee(i,i.next),Ee(e,e.next)}d(tl,"eliminateHole");function el(n,t){let e=t,i=n.x,s=n.y,r=-1/0,o;if(Qe(n,e))return e;do{if(Qe(n,e.next))return e.next;if(s<=e.y&&s>=e.next.y&&e.next.y!==e.y){let h=e.x+(s-e.y)*(e.next.x-e.x)/(e.next.y-e.y);if(h<=i&&h>r&&(r=h,o=e.x<e.next.x?e:e.next,h===i))return o}e=e.next}while(e!==t);if(!o)return null;let a=o,c=o.x,l=o.y,u=1/0;e=o;do{if(i>=e.x&&e.x>=c&&i!==e.x&&So(s<l?i:r,s,c,l,s<l?r:i,s,e.x,e.y)){let h=Math.abs(s-e.y)/(i-e.x);Rn(e,n)&&(h<u||h===u&&(e.x>o.x||e.x===o.x&&nl(o,e)))&&(o=e,u=h)}e=e.next}while(e!==a);return o}d(el,"findHoleBridge");function nl(n,t){return at(n.prev,n,t.prev)<0&&at(t.next,n,n.next)<0}d(nl,"sectorContainsSector");function il(n,t,e,i){let s=n;do s.z===0&&(s.z=Ts(s.x,s.y,t,e,i)),s.prevZ=s.prev,s.nextZ=s.next,s=s.next;while(s!==n);s.prevZ.nextZ=null,s.prevZ=null,sl(s)}d(il,"indexCurve");function sl(n){let t,e=1;do{let i=n,s;n=null;let r=null;for(t=0;i;){t++;let o=i,a=0;for(let l=0;l<e&&(a++,o=o.nextZ,!!o);l++);let c=e;for(;a>0||c>0&&o;)a!==0&&(c===0||!o||i.z<=o.z)?(s=i,i=i.nextZ,a--):(s=o,o=o.nextZ,c--),r?r.nextZ=s:n=s,s.prevZ=r,r=s;i=o}r.nextZ=null,e*=2}while(t>1);return n}d(sl,"sortLinked");function Ts(n,t,e,i,s){return n=(n-e)*s|0,t=(t-i)*s|0,n=(n|n<<8)&16711935,n=(n|n<<4)&252645135,n=(n|n<<2)&858993459,n=(n|n<<1)&1431655765,t=(t|t<<8)&16711935,t=(t|t<<4)&252645135,t=(t|t<<2)&858993459,t=(t|t<<1)&1431655765,n|t<<1}d(Ts,"zOrder");function rl(n){let t=n,e=n;do(t.x<e.x||t.x===e.x&&t.y<e.y)&&(e=t),t=t.next;while(t!==n);return e}d(rl,"getLeftmost");function So(n,t,e,i,s,r,o,a){return(s-o)*(t-a)>=(n-o)*(r-a)&&(n-o)*(i-a)>=(e-o)*(t-a)&&(e-o)*(r-a)>=(s-o)*(i-a)}d(So,"pointInTriangle");function An(n,t,e,i,s,r,o,a){return!(n===o&&t===a)&&So(n,t,e,i,s,r,o,a)}d(An,"pointInTriangleExceptFirst");function ol(n,t){return n.next.i!==t.i&&n.prev.i!==t.i&&!al(n,t)&&(Rn(n,t)&&Rn(t,n)&&cl(n,t)&&(at(n.prev,n,t.prev)||at(n,t.prev,t))||Qe(n,t)&&at(n.prev,n,n.next)>0&&at(t.prev,t,t.next)>0)}d(ol,"isValidDiagonal");function at(n,t,e){return(t.y-n.y)*(e.x-t.x)-(t.x-n.x)*(e.y-t.y)}d(at,"area");function Qe(n,t){return n.x===t.x&&n.y===t.y}d(Qe,"equals");function Mo(n,t,e,i){let s=oi(at(n,t,e)),r=oi(at(n,t,i)),o=oi(at(e,i,n)),a=oi(at(e,i,t));return!!(s!==r&&o!==a||s===0&&ri(n,e,t)||r===0&&ri(n,i,t)||o===0&&ri(e,n,i)||a===0&&ri(e,t,i))}d(Mo,"intersects");function ri(n,t,e){return t.x<=Math.max(n.x,e.x)&&t.x>=Math.min(n.x,e.x)&&t.y<=Math.max(n.y,e.y)&&t.y>=Math.min(n.y,e.y)}d(ri,"onSegment");function oi(n){return n>0?1:n<0?-1:0}d(oi,"sign");function al(n,t){let e=n;do{if(e.i!==n.i&&e.next.i!==n.i&&e.i!==t.i&&e.next.i!==t.i&&Mo(e,e.next,n,t))return!0;e=e.next}while(e!==n);return!1}d(al,"intersectsPolygon");function Rn(n,t){return at(n.prev,n,n.next)<0?at(n,t,n.next)>=0&&at(n,n.prev,t)>=0:at(n,t,n.prev)<0||at(n,n.next,t)<0}d(Rn,"locallyInside");function cl(n,t){let e=n,i=!1,s=(n.x+t.x)/2,r=(n.y+t.y)/2;do e.y>r!=e.next.y>r&&e.next.y!==e.y&&s<(e.next.x-e.x)*(r-e.y)/(e.next.y-e.y)+e.x&&(i=!i),e=e.next;while(e!==n);return i}d(cl,"middleInside");function bo(n,t){let e=Es(n.i,n.x,n.y),i=Es(t.i,t.x,t.y),s=n.next,r=t.prev;return n.next=t,t.prev=n,e.next=s,s.prev=e,i.next=e,e.prev=i,r.next=i,i.prev=r,i}d(bo,"splitPolygon");function Qr(n,t,e,i){let s=Es(n,t,e);return i?(s.next=i.next,s.prev=i,i.next.prev=s,i.next=s):(s.prev=s,s.next=s),s}d(Qr,"insertNode");function In(n){n.next.prev=n.prev,n.prev.next=n.next,n.prevZ&&(n.prevZ.nextZ=n.nextZ),n.nextZ&&(n.nextZ.prevZ=n.prevZ)}d(In,"removeNode");function Es(n,t,e){return{i:n,x:t,y:e,prev:null,next:null,z:0,prevZ:null,nextZ:null,steiner:!1}}d(Es,"createNode");function ll(n,t,e,i){let s=0;for(let r=t,o=e-i;r<e;r+=i)s+=(n[o]-n[r])*(n[r+1]+n[o+1]),o=r;return s}d(ll,"signedArea");var Cs=class{static{d(this,"Earcut")}static triangulate(t,e,i=2){return $c(t,e,i)}},Pn=class n{static{d(this,"ShapeUtils")}static area(t){let e=t.length,i=0;for(let s=e-1,r=0;r<e;s=r++)i+=t[s].x*t[r].y-t[r].x*t[s].y;return i*.5}static isClockWise(t){return n.area(t)<0}static triangulateShape(t,e){let i=[],s=[],r=[];to(t),eo(i,t);let o=t.length;e.forEach(to);for(let c=0;c<e.length;c++)s.push(o),o+=e[c].length,eo(i,e[c]);let a=Cs.triangulate(i,s);for(let c=0;c<a.length;c+=3)r.push(a.slice(c,c+3));return r}};function to(n){let t=n.length;t>2&&n[t-1].equals(n[0])&&n.pop()}d(to,"removeDupEndPts");function eo(n,t){for(let e=0;e<t.length;e++)n.push(t[e].x),n.push(t[e].y)}d(eo,"addContour");function wo(n){let t={};for(let e in n){t[e]={};for(let i in n[e]){let s=n[e][i];if(no(s))s.isRenderTargetTexture?(gt("UniformsUtils: Textures of render targets cannot be cloned via cloneUniforms() or mergeUniforms()."),t[e][i]=null):t[e][i]=s.clone();else if(Array.isArray(s))if(no(s[0])){let r=[];for(let o=0,a=s.length;o<a;o++)r[o]=s[o].clone();t[e][i]=r}else t[e][i]=s.slice();else t[e][i]=s}}return t}d(wo,"cloneUniforms");function wt(n){let t={};for(let e=0;e<n.length;e++){let i=wo(n[e]);for(let s in i)t[s]=i[s]}return t}d(wt,"mergeUniforms");function no(n){return n&&(n.isColor||n.isMatrix3||n.isMatrix4||n.isVector2||n.isVector3||n.isVector4||n.isTexture||n.isQuaternion)}d(no,"isThreeObject");function Ye(n,t){return!n||n.constructor===t?n:typeof t.BYTES_PER_ELEMENT=="number"?new t(n):Array.prototype.slice.call(n)}d(Ye,"convertArray");function os(n){return n!==void 0&&n.inTangents!==void 0&&n.outTangents!==void 0}d(os,"hasTangents");var pe=class{static{d(this,"Interpolant")}constructor(t,e,i,s){this.parameterPositions=t,this._cachedIndex=0,this.resultBuffer=s!==void 0?s:new e.constructor(i),this.sampleValues=e,this.valueSize=i,this.settings=null,this.DefaultSettings_={}}evaluate(t){let e=this.parameterPositions,i=this._cachedIndex,s=e[i],r=e[i-1];n:{t:{let o;e:{i:if(!(t<s)){for(let a=i+2;;){if(s===void 0){if(t<r)break i;return i=e.length,this._cachedIndex=i,this.copySampleValue_(i-1)}if(i===a)break;if(r=s,s=e[++i],t<s)break t}o=e.length;break e}if(!(t>=r)){let a=e[1];t<a&&(i=2,r=a);for(let c=i-2;;){if(r===void 0)return this._cachedIndex=0,this.copySampleValue_(0);if(i===c)break;if(s=r,r=e[--i-1],t>=r)break t}o=i,i=0;break e}break n}for(;i<o;){let a=i+o>>>1;t<e[a]?o=a:i=a+1}if(s=e[i],r=e[i-1],r===void 0)return this._cachedIndex=0,this.copySampleValue_(0);if(s===void 0)return i=e.length,this._cachedIndex=i,this.copySampleValue_(i-1)}this._cachedIndex=i,this.intervalChanged_(i,r,s)}return this.interpolate_(i,r,t,s)}getSettings_(){return this.settings||this.DefaultSettings_}copySampleValue_(t){let e=this.resultBuffer,i=this.sampleValues,s=this.valueSize,r=t*s;for(let o=0;o!==s;++o)e[o]=i[r+o];return e}interpolate_(){throw new Error("THREE.Interpolant: Call to abstract method.")}intervalChanged_(){}},_i=class extends pe{static{d(this,"CubicInterpolant")}constructor(t,e,i,s){super(t,e,i,s),this._weightPrev=-0,this._offsetPrev=-0,this._weightNext=-0,this._offsetNext=-0,this.DefaultSettings_={endingStart:xs,endingEnd:xs}}intervalChanged_(t,e,i){let s=this.parameterPositions,r=t-2,o=t+1,a=s[r],c=s[o];if(a===void 0)switch(this.getSettings_().endingStart){case ys:r=t,a=2*e-i;break;case vs:r=s.length-2,a=e+s[r]-s[r+1];break;default:r=t,a=i}if(c===void 0)switch(this.getSettings_().endingEnd){case ys:o=t,c=2*i-e;break;case vs:o=1,c=i+s[1]-s[0];break;default:o=t-1,c=e}let l=(i-e)*.5,u=this.valueSize;this._weightPrev=l/(e-a),this._weightNext=l/(c-i),this._offsetPrev=r*u,this._offsetNext=o*u}interpolate_(t,e,i,s){let r=this.resultBuffer,o=this.sampleValues,a=this.valueSize,c=t*a,l=c-a,u=this._offsetPrev,h=this._offsetNext,f=this._weightPrev,p=this._weightNext,m=(i-e)/(s-e),g=m*m,_=g*m,x=-f*_+2*f*g-f*m,v=(1+f)*_+(-1.5-2*f)*g+(-.5+f)*m+1,y=(-1-p)*_+(1.5+p)*g+.5*m,M=p*_-p*g;for(let A=0;A!==a;++A)r[A]=x*o[u+A]+v*o[l+A]+y*o[c+A]+M*o[h+A];return r}},xi=class extends pe{static{d(this,"LinearInterpolant")}constructor(t,e,i,s){super(t,e,i,s)}interpolate_(t,e,i,s){let r=this.resultBuffer,o=this.sampleValues,a=this.valueSize,c=t*a,l=c-a,u=(i-e)/(s-e),h=1-u;for(let f=0;f!==a;++f)r[f]=o[l+f]*h+o[c+f]*u;return r}},yi=class extends pe{static{d(this,"DiscreteInterpolant")}constructor(t,e,i,s){super(t,e,i,s)}interpolate_(t){return this.copySampleValue_(t-1)}},vi=class extends pe{static{d(this,"BezierInterpolant")}interpolate_(t,e,i,s){let r=this.resultBuffer,o=this.sampleValues,a=this.valueSize,c=t*a,l=c-a,u=this.inTangents,h=this.outTangents;if(!u||!h){let m=(i-e)/(s-e),g=1-m;for(let _=0;_!==a;++_)r[_]=o[l+_]*g+o[c+_]*m;return r}let f=a*2,p=t-1;for(let m=0;m!==a;++m){let g=o[l+m],_=o[c+m],x=p*f+m*2,v=h[x],y=h[x+1],M=t*f+m*2,A=u[M],b=u[M+1],S=hl(i,e,v,A,s);r[m]=Ao(S,g,y,b,_)}return r}};function Ao(n,t,e,i,s){let r=1-n;return r*r*r*t+3*r*r*n*e+3*r*n*n*i+n*n*n*s}d(Ao,"cubicBezier");function ul(n,t,e,i,s){let r=1-n;return 3*r*r*(e-t)+6*r*n*(i-e)+3*n*n*(s-i)}d(ul,"cubicBezierSlope");function hl(n,t,e,i,s){let r=(n-t)/(s-t);for(let o=0;o<8;o++){let a=Ao(r,t,e,i,s)-n;if(Math.abs(a)<1e-10)break;let c=ul(r,t,e,i,s);if(Math.abs(c)<1e-10)break;r=Math.max(0,Math.min(1,r-a/c))}return r}d(hl,"solveBezierParameter");var Ft=class{static{d(this,"KeyframeTrack")}constructor(t,e,i,s){if(t===void 0)throw new Error("THREE.KeyframeTrack: track name is undefined");if(e===void 0||e.length===0)throw new Error("THREE.KeyframeTrack: no keyframes in track named "+t);this.name=t,this.times=Ye(e,this.TimeBufferType),this.values=Ye(i,this.ValueBufferType),this.setInterpolation(s||this.DefaultInterpolation)}static toJSON(t){let e=t.constructor,i;if(e.toJSON!==this.toJSON)i=e.toJSON(t);else{i={name:t.name,times:Ye(t.times,Array),values:Ye(t.values,Array)};let s=t.getInterpolation();s!==t.DefaultInterpolation&&(i.interpolation=s),os(t.settings)&&(i.settings={inTangents:Ye(t.settings.inTangents,Array),outTangents:Ye(t.settings.outTangents,Array)})}return i.type=t.ValueTypeName,i}InterpolantFactoryMethodDiscrete(t){return new yi(this.times,this.values,this.getValueSize(),t)}InterpolantFactoryMethodLinear(t){return new xi(this.times,this.values,this.getValueSize(),t)}InterpolantFactoryMethodSmooth(t){return new _i(this.times,this.values,this.getValueSize(),t)}InterpolantFactoryMethodBezier(t){let e=new vi(this.times,this.values,this.getValueSize(),t);return this.settings&&(e.inTangents=this.settings.inTangents,e.outTangents=this.settings.outTangents),e}setInterpolation(t){let e;switch(t){case Tn:e=this.InterpolantFactoryMethodDiscrete;break;case li:e=this.InterpolantFactoryMethodLinear;break;case ai:e=this.InterpolantFactoryMethodSmooth;break;case _s:e=this.InterpolantFactoryMethodBezier;break}if(e===void 0){let i="unsupported interpolation for "+this.ValueTypeName+" keyframe track named "+this.name;if(this.createInterpolant===void 0)if(t!==this.DefaultInterpolation)this.setInterpolation(this.DefaultInterpolation);else throw new Error(i);return gt("KeyframeTrack:",i),this}return this.createInterpolant=e,this}getInterpolation(){switch(this.createInterpolant){case this.InterpolantFactoryMethodDiscrete:return Tn;case this.InterpolantFactoryMethodLinear:return li;case this.InterpolantFactoryMethodSmooth:return ai;case this.InterpolantFactoryMethodBezier:return _s}}getValueSize(){return this.values.length/this.times.length}shift(t){if(t!==0){let e=this.times;for(let i=0,s=e.length;i!==s;++i)e[i]+=t}return this}scale(t){if(t!==1){let e=this.times;for(let i=0,s=e.length;i!==s;++i)e[i]*=t;os(this.settings)&&(io(this.settings.inTangents,t),io(this.settings.outTangents,t))}return this}trim(t,e){let i=this.times,s=i.length,r=0,o=s-1;for(;r!==s&&i[r]<t;)++r;for(;o!==-1&&i[o]>e;)--o;if(++o,r!==0||o!==s){r>=o&&(o=Math.max(o,1),r=o-1);let a=this.getValueSize();this.times=i.slice(r,o),this.values=this.values.slice(r*a,o*a)}return this}validate(){let t=!0,e=this.getValueSize();e-Math.floor(e)!==0&&(ot("KeyframeTrack: Invalid value size in track.",this),t=!1);let i=this.times,s=this.values,r=i.length;r===0&&(ot("KeyframeTrack: Track is empty.",this),t=!1);let o=null;for(let a=0;a!==r;a++){let c=i[a];if(typeof c=="number"&&isNaN(c)){ot("KeyframeTrack: Time is not a valid number.",this,a,c),t=!1;break}if(o!==null&&o>c){ot("KeyframeTrack: Out of order keys.",this,a,c,o),t=!1;break}o=c}if(s!==void 0&&Pc(s))for(let a=0,c=s.length;a!==c;++a){let l=s[a];if(isNaN(l)){ot("KeyframeTrack: Value is not a valid number.",this,a,l),t=!1;break}}return t}optimize(){let t=this.times.slice(),e=this.values.slice(),i=this.getValueSize(),s=this.getInterpolation()===ai,r=t.length-1,o=1;for(let a=1;a<r;++a){let c=!1,l=t[a],u=t[a+1];if(l!==u&&(a!==1||l!==t[0]))if(s)c=!0;else{let h=a*i,f=h-i,p=h+i;for(let m=0;m!==i;++m){let g=e[h+m];if(g!==e[f+m]||g!==e[p+m]){c=!0;break}}}if(c){if(a!==o){t[o]=t[a];let h=a*i,f=o*i;for(let p=0;p!==i;++p)e[f+p]=e[h+p]}++o}}if(r>0){t[o]=t[r];for(let a=r*i,c=o*i,l=0;l!==i;++l)e[c+l]=e[a+l];++o}return o!==t.length?(this.times=t.slice(0,o),this.values=e.slice(0,o*i)):(this.times=t,this.values=e),this}clone(){let t=this.times.slice(),e=this.values.slice(),i=this.constructor,s=new i(this.name,t,e);return s.createInterpolant=this.createInterpolant,os(this.settings)&&(s.settings={inTangents:this.settings.inTangents.slice(),outTangents:this.settings.outTangents.slice()}),s}};function io(n,t){for(let e=0,i=n.length;e!==i;e+=2)n[e]*=t}d(io,"scaleTangentTimes");Ft.prototype.ValueTypeName="";Ft.prototype.TimeBufferType=Float32Array;Ft.prototype.ValueBufferType=Float32Array;Ft.prototype.DefaultInterpolation=li;var me=class extends Ft{static{d(this,"BooleanKeyframeTrack")}constructor(t,e,i){super(t,e,i)}};me.prototype.ValueTypeName="bool";me.prototype.ValueBufferType=Array;me.prototype.DefaultInterpolation=Tn;me.prototype.InterpolantFactoryMethodLinear=void 0;me.prototype.InterpolantFactoryMethodSmooth=void 0;var Si=class extends Ft{static{d(this,"ColorKeyframeTrack")}constructor(t,e,i,s){super(t,e,i,s)}};Si.prototype.ValueTypeName="color";var Mi=class extends Ft{static{d(this,"NumberKeyframeTrack")}constructor(t,e,i,s){super(t,e,i,s)}};Mi.prototype.ValueTypeName="number";var bi=class extends pe{static{d(this,"QuaternionLinearInterpolant")}constructor(t,e,i,s){super(t,e,i,s)}interpolate_(t,e,i,s){let r=this.resultBuffer,o=this.sampleValues,a=this.valueSize,c=(i-e)/(s-e),l=t*a;for(let u=l+a;l!==u;l+=4)Yt.slerpFlat(r,0,o,l-a,o,l,c);return r}},Nn=class extends Ft{static{d(this,"QuaternionKeyframeTrack")}constructor(t,e,i,s){super(t,e,i,s)}InterpolantFactoryMethodLinear(t){return new bi(this.times,this.values,this.getValueSize(),t)}};Nn.prototype.ValueTypeName="quaternion";Nn.prototype.InterpolantFactoryMethodSmooth=void 0;var ge=class extends Ft{static{d(this,"StringKeyframeTrack")}constructor(t,e,i){super(t,e,i)}};ge.prototype.ValueTypeName="string";ge.prototype.ValueBufferType=Array;ge.prototype.DefaultInterpolation=Tn;ge.prototype.InterpolantFactoryMethodLinear=void 0;ge.prototype.InterpolantFactoryMethodSmooth=void 0;var wi=class extends Ft{static{d(this,"VectorKeyframeTrack")}constructor(t,e,i,s){super(t,e,i,s)}};wi.prototype.ValueTypeName="vector";var Ai=class{static{d(this,"LoadingManager")}constructor(t,e,i){let s=this,r=!1,o=0,a=0,c,l=[];this.onStart=void 0,this.onLoad=t,this.onProgress=e,this.onError=i,this._abortController=null,this.itemStart=function(u){a++,r===!1&&s.onStart!==void 0&&s.onStart(u,o,a),r=!0},this.itemEnd=function(u){o++,s.onProgress!==void 0&&s.onProgress(u,o,a),o===a&&(r=!1,s.onLoad!==void 0&&s.onLoad())},this.itemError=function(u){s.onError!==void 0&&s.onError(u)},this.resolveURL=function(u){return u=u.normalize("NFC"),c?c(u):u},this.setURLModifier=function(u){return c=u,this},this.addHandler=function(u,h){return l.push(u,h),this},this.removeHandler=function(u){let h=l.indexOf(u);return h!==-1&&l.splice(h,2),this},this.getHandler=function(u){for(let h=0,f=l.length;h<f;h+=2){let p=l[h],m=l[h+1];if(p.global&&(p.lastIndex=0),p.test(u))return m}return null},this.abort=function(){return this.abortController.abort(),this._abortController=null,this}}get abortController(){return this._abortController||(this._abortController=new AbortController),this._abortController}},To=new Ai,Ti=class{static{d(this,"Loader")}constructor(t){this.manager=t!==void 0?t:To,this.crossOrigin="anonymous",this.withCredentials=!1,this.path="",this.resourcePath="",this.requestHeader={},typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("observe",{detail:this}))}load(){}loadAsync(t,e){let i=this;return new Promise(function(s,r){i.load(t,s,e,r)})}parse(){}setCrossOrigin(t){return this.crossOrigin=t,this}setWithCredentials(t){return this.withCredentials=t,this}setPath(t){return this.path=t,this}setResourcePath(t){return this.resourcePath=t,this}setRequestHeader(t){return this.requestHeader=t,this}abort(){return this}};Ti.DEFAULT_MATERIAL_NAME="__DEFAULT";var Vs="\\[\\]\\.:\\/",fl=new RegExp("["+Vs+"]","g"),Gs="[^"+Vs+"]",dl="[^"+Vs.replace("\\.","")+"]",pl=/((?:WC+[\/:])*)/.source.replace("WC",Gs),ml=/(WCOD+)?/.source.replace("WCOD",dl),gl=/(?:\.(WC+)(?:\[(.+)\])?)?/.source.replace("WC",Gs),_l=/\.(WC+)(?:\[(.+)\])?/.source.replace("WC",Gs),xl=new RegExp("^"+pl+ml+gl+_l+"$"),yl=["material","materials","bones","map"],Rs=class{static{d(this,"Composite")}constructor(t,e,i){let s=i||it.parseTrackName(e);this._targetGroup=t,this._bindings=t.subscribe_(e,s)}getValue(t,e){this.bind();let i=this._targetGroup.nCachedObjects_,s=this._bindings[i];s!==void 0&&s.getValue(t,e)}setValue(t,e){let i=this._bindings;for(let s=this._targetGroup.nCachedObjects_,r=i.length;s!==r;++s)i[s].setValue(t,e)}bind(){let t=this._bindings;for(let e=this._targetGroup.nCachedObjects_,i=t.length;e!==i;++e)t[e].bind()}unbind(){let t=this._bindings;for(let e=this._targetGroup.nCachedObjects_,i=t.length;e!==i;++e)t[e].unbind()}},it=class n{static{d(this,"PropertyBinding")}constructor(t,e,i){this.path=e,this.parsedPath=i||n.parseTrackName(e),this.node=n.findNode(t,this.parsedPath.nodeName),this.rootNode=t,this.getValue=this._getValue_unbound,this.setValue=this._setValue_unbound}static create(t,e,i){return t&&t.isAnimationObjectGroup?new n.Composite(t,e,i):new n(t,e,i)}static sanitizeNodeName(t){return t.replace(/\s/g,"_").replace(fl,"")}static parseTrackName(t){let e=xl.exec(t);if(e===null)throw new Error("THREE.PropertyBinding: Cannot parse trackName: "+t);let i={nodeName:e[2],objectName:e[3],objectIndex:e[4],propertyName:e[5],propertyIndex:e[6]},s=i.nodeName&&i.nodeName.lastIndexOf(".");if(s!==void 0&&s!==-1){let r=i.nodeName.substring(s+1);yl.indexOf(r)!==-1&&(i.nodeName=i.nodeName.substring(0,s),i.objectName=r)}if(i.propertyName===null||i.propertyName.length===0)throw new Error("THREE.PropertyBinding: can not parse propertyName from trackName: "+t);return i}static findNode(t,e){if(e===void 0||e===""||e==="."||e===-1||e===t.name||e===t.uuid)return t;if(t.skeleton){let i=t.skeleton.getBoneByName(e);if(i!==void 0)return i}if(t.children){let i=d(function(r){for(let o=0;o<r.length;o++){let a=r[o];if(a.name===e||a.uuid===e)return a;let c=i(a.children);if(c)return c}return null},"searchNodeSubtree"),s=i(t.children);if(s)return s}return null}_getValue_unavailable(){}_setValue_unavailable(){}_getValue_direct(t,e){t[e]=this.targetObject[this.propertyName]}_getValue_array(t,e){let i=this.resolvedProperty;for(let s=0,r=i.length;s!==r;++s)t[e++]=i[s]}_getValue_arrayElement(t,e){t[e]=this.resolvedProperty[this.propertyIndex]}_getValue_toArray(t,e){this.resolvedProperty.toArray(t,e)}_setValue_direct(t,e){this.targetObject[this.propertyName]=t[e]}_setValue_direct_setNeedsUpdate(t,e){this.targetObject[this.propertyName]=t[e],this.targetObject.needsUpdate=!0}_setValue_direct_setMatrixWorldNeedsUpdate(t,e){this.targetObject[this.propertyName]=t[e],this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_array(t,e){let i=this.resolvedProperty;for(let s=0,r=i.length;s!==r;++s)i[s]=t[e++]}_setValue_array_setNeedsUpdate(t,e){let i=this.resolvedProperty;for(let s=0,r=i.length;s!==r;++s)i[s]=t[e++];this.targetObject.needsUpdate=!0}_setValue_array_setMatrixWorldNeedsUpdate(t,e){let i=this.resolvedProperty;for(let s=0,r=i.length;s!==r;++s)i[s]=t[e++];this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_arrayElement(t,e){this.resolvedProperty[this.propertyIndex]=t[e]}_setValue_arrayElement_setNeedsUpdate(t,e){this.resolvedProperty[this.propertyIndex]=t[e],this.targetObject.needsUpdate=!0}_setValue_arrayElement_setMatrixWorldNeedsUpdate(t,e){this.resolvedProperty[this.propertyIndex]=t[e],this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_fromArray(t,e){this.resolvedProperty.fromArray(t,e)}_setValue_fromArray_setNeedsUpdate(t,e){this.resolvedProperty.fromArray(t,e),this.targetObject.needsUpdate=!0}_setValue_fromArray_setMatrixWorldNeedsUpdate(t,e){this.resolvedProperty.fromArray(t,e),this.targetObject.matrixWorldNeedsUpdate=!0}_getValue_unbound(t,e){this.bind(),this.getValue(t,e)}_setValue_unbound(t,e){this.bind(),this.setValue(t,e)}bind(){let t=this.node,e=this.parsedPath,i=e.objectName,s=e.propertyName,r=e.propertyIndex;if(t||(t=n.findNode(this.rootNode,e.nodeName),this.node=t),this.getValue=this._getValue_unavailable,this.setValue=this._setValue_unavailable,!t){gt("PropertyBinding: No target node found for track: "+this.path+".");return}if(i){let l=e.objectIndex;switch(i){case"materials":if(!t.material){ot("PropertyBinding: Can not bind to material as node does not have a material.",this);return}if(!t.material.materials){ot("PropertyBinding: Can not bind to material.materials as node.material does not have a materials array.",this);return}t=t.material.materials;break;case"bones":if(!t.skeleton){ot("PropertyBinding: Can not bind to bones as node does not have a skeleton.",this);return}t=t.skeleton.bones;for(let u=0;u<t.length;u++)if(t[u].name===l){l=u;break}break;case"map":if("map"in t){t=t.map;break}if(!t.material){ot("PropertyBinding: Can not bind to material as node does not have a material.",this);return}if(!t.material.map){ot("PropertyBinding: Can not bind to material.map as node.material does not have a map.",this);return}t=t.material.map;break;default:if(t[i]===void 0){ot("PropertyBinding: Can not bind to objectName of node undefined.",this);return}t=t[i]}if(l!==void 0){if(t[l]===void 0){ot("PropertyBinding: Trying to bind to objectIndex of objectName, but is undefined.",this,t);return}t=t[l]}}let o=t[s];if(o===void 0){let l=e.nodeName;ot("PropertyBinding: Trying to update property for track: "+l+"."+s+" but it wasn't found.",t);return}let a=this.Versioning.None;this.targetObject=t,t.isMaterial===!0?a=this.Versioning.NeedsUpdate:t.isObject3D===!0&&(a=this.Versioning.MatrixWorldNeedsUpdate);let c=this.BindingType.Direct;if(r!==void 0){if(s==="morphTargetInfluences"){if(!t.geometry){ot("PropertyBinding: Can not bind to morphTargetInfluences because node does not have a geometry.",this);return}if(!t.geometry.morphAttributes){ot("PropertyBinding: Can not bind to morphTargetInfluences because node does not have a geometry.morphAttributes.",this);return}t.morphTargetDictionary[r]!==void 0&&(r=t.morphTargetDictionary[r])}c=this.BindingType.ArrayElement,this.resolvedProperty=o,this.propertyIndex=r}else o.fromArray!==void 0&&o.toArray!==void 0?(c=this.BindingType.HasFromToArray,this.resolvedProperty=o):Array.isArray(o)?(c=this.BindingType.EntireArray,this.resolvedProperty=o):this.propertyName=s;this.getValue=this.GetterByBindingType[c],this.setValue=this.SetterByBindingTypeAndVersioning[c][a]}unbind(){this.node=null,this.getValue=this._getValue_unbound,this.setValue=this._setValue_unbound}};it.Composite=Rs;it.prototype.BindingType={Direct:0,EntireArray:1,ArrayElement:2,HasFromToArray:3};it.prototype.Versioning={None:0,NeedsUpdate:1,MatrixWorldNeedsUpdate:2};it.prototype.GetterByBindingType=[it.prototype._getValue_direct,it.prototype._getValue_array,it.prototype._getValue_arrayElement,it.prototype._getValue_toArray];it.prototype.SetterByBindingTypeAndVersioning=[[it.prototype._setValue_direct,it.prototype._setValue_direct_setNeedsUpdate,it.prototype._setValue_direct_setMatrixWorldNeedsUpdate],[it.prototype._setValue_array,it.prototype._setValue_array_setNeedsUpdate,it.prototype._setValue_array_setMatrixWorldNeedsUpdate],[it.prototype._setValue_arrayElement,it.prototype._setValue_arrayElement_setNeedsUpdate,it.prototype._setValue_arrayElement_setMatrixWorldNeedsUpdate],[it.prototype._setValue_fromArray,it.prototype._setValue_fromArray_setNeedsUpdate,it.prototype._setValue_fromArray_setMatrixWorldNeedsUpdate]];var Zp=new Float32Array(1);var Is=class n{static{d(this,"Matrix2")}static{n.prototype.isMatrix2=!0}constructor(t,e,i,s){this.elements=[1,0,0,1],t!==void 0&&this.set(t,e,i,s)}identity(){return this.set(1,0,0,1),this}fromArray(t,e=0){for(let i=0;i<4;i++)this.elements[i]=t[i+e];return this}set(t,e,i,s){let r=this.elements;return r[0]=t,r[2]=e,r[1]=i,r[3]=s,this}};typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("register",{detail:{revision:"186"}}));typeof window<"u"&&(window.__THREE__?gt("WARNING: Multiple instances of Three.js being imported."):window.__THREE__="186");var vl=`#ifdef USE_ALPHAHASH
	if ( diffuseColor.a < getAlphaHashThreshold( vPosition ) ) discard;
#endif`,Sl=`#ifdef USE_ALPHAHASH
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
#endif`,Ml=`#ifdef USE_ALPHAMAP
	diffuseColor.a *= texture2D( alphaMap, vAlphaMapUv ).g;
#endif`,bl=`#ifdef USE_ALPHAMAP
	uniform sampler2D alphaMap;
#endif`,wl=`#ifdef USE_ALPHATEST
	#ifdef ALPHA_TO_COVERAGE
	diffuseColor.a = smoothstep( alphaTest, alphaTest + fwidth( diffuseColor.a ), diffuseColor.a );
	if ( diffuseColor.a == 0.0 ) discard;
	#else
	if ( diffuseColor.a < alphaTest ) discard;
	#endif
#endif`,Al=`#ifdef USE_ALPHATEST
	uniform float alphaTest;
#endif`,Tl=`#ifdef USE_AOMAP
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
#endif`,El=`#ifdef USE_AOMAP
	uniform sampler2D aoMap;
	uniform float aoMapIntensity;
#endif`,Cl=`#ifdef USE_BATCHING
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
#endif`,Rl=`#ifdef USE_BATCHING
	mat4 batchingMatrix = getBatchingMatrix( getIndirectIndex( gl_DrawID ) );
#endif`,Il=`vec3 transformed = vec3( position );
#ifdef USE_ALPHAHASH
	vPosition = vec3( position );
#endif`,Pl=`vec3 objectNormal = vec3( normal );
#ifdef USE_TANGENT
	vec3 objectTangent = vec3( tangent.xyz );
#endif`,Nl=`float G_BlinnPhong_Implicit( ) {
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
} // validated`,Ll=`#ifdef USE_IRIDESCENCE
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
#endif`,Dl=`#ifdef USE_BUMPMAP
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
#endif`,Ul=`#if NUM_CLIPPING_PLANES > 0
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
#endif`,Fl=`#if NUM_CLIPPING_PLANES > 0
	varying vec3 vClipPosition;
	uniform vec4 clippingPlanes[ NUM_CLIPPING_PLANES ];
#endif`,Ol=`#if NUM_CLIPPING_PLANES > 0
	varying vec3 vClipPosition;
#endif`,Bl=`#if NUM_CLIPPING_PLANES > 0
	vClipPosition = - mvPosition.xyz;
#endif`,zl=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA )
	diffuseColor *= vColor;
#endif`,kl=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA )
	varying vec4 vColor;
#endif`,Vl=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA ) || defined( USE_INSTANCING_COLOR ) || defined( USE_BATCHING_COLOR )
	varying vec4 vColor;
#endif`,Gl=`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA ) || defined( USE_INSTANCING_COLOR ) || defined( USE_BATCHING_COLOR )
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
#endif`,Hl=`#define PI 3.141592653589793
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
} // validated`,Wl=`#ifdef ENVMAP_TYPE_CUBE_UV
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
#endif`,Xl=`vec3 transformedNormal = objectNormal;
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
#endif`,ql=`#ifdef USE_DISPLACEMENTMAP
	uniform sampler2D displacementMap;
	uniform float displacementScale;
	uniform float displacementBias;
#endif`,$l=`#ifdef USE_DISPLACEMENTMAP
	transformed += normalize( objectNormal ) * ( texture2D( displacementMap, vDisplacementMapUv ).x * displacementScale + displacementBias );
#endif`,Yl=`#ifdef USE_EMISSIVEMAP
	vec4 emissiveColor = texture2D( emissiveMap, vEmissiveMapUv );
	#ifdef DECODE_VIDEO_TEXTURE_EMISSIVE
		emissiveColor = sRGBTransferEOTF( emissiveColor );
	#endif
	totalEmissiveRadiance *= emissiveColor.rgb;
#endif`,Zl=`#ifdef USE_EMISSIVEMAP
	uniform sampler2D emissiveMap;
#endif`,Jl="gl_FragColor = linearToOutputTexel( gl_FragColor );",Kl=`vec4 LinearTransferOETF( in vec4 value ) {
	return value;
}
vec4 sRGBTransferEOTF( in vec4 value ) {
	return vec4( mix( pow( value.rgb * 0.9478672986 + vec3( 0.0521327014 ), vec3( 2.4 ) ), value.rgb * 0.0773993808, vec3( lessThanEqual( value.rgb, vec3( 0.04045 ) ) ) ), value.a );
}
vec4 sRGBTransferOETF( in vec4 value ) {
	return vec4( mix( pow( value.rgb, vec3( 0.41666 ) ) * 1.055 - vec3( 0.055 ), value.rgb * 12.92, vec3( lessThanEqual( value.rgb, vec3( 0.0031308 ) ) ) ), value.a );
}`,jl=`#ifdef USE_ENVMAP
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
#endif`,Ql=`#ifdef USE_ENVMAP
	uniform float envMapIntensity;
	uniform mat3 envMapRotation;
	#ifdef ENVMAP_TYPE_CUBE
		uniform samplerCube envMap;
	#else
		uniform sampler2D envMap;
	#endif
#endif`,tu=`#ifdef USE_ENVMAP
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
#endif`,eu=`#ifdef USE_ENVMAP
	#if defined( USE_BUMPMAP ) || defined( USE_NORMALMAP ) || defined( PHONG ) || defined( LAMBERT )
		#define ENV_WORLDPOS
	#endif
	#ifdef ENV_WORLDPOS
		
		varying vec3 vWorldPosition;
	#else
		varying vec3 vReflect;
		uniform float refractionRatio;
	#endif
#endif`,nu=`#ifdef USE_ENVMAP
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
#endif`,iu=`#ifdef USE_FOG
	vFogDepth = - mvPosition.z;
#endif`,su=`#ifdef USE_FOG
	varying float vFogDepth;
#endif`,ru=`#ifdef USE_FOG
	#ifdef FOG_EXP2
		float fogFactor = 1.0 - exp( - fogDensity * fogDensity * vFogDepth * vFogDepth );
	#else
		float fogFactor = smoothstep( fogNear, fogFar, vFogDepth );
	#endif
	gl_FragColor.rgb = mix( gl_FragColor.rgb, fogColor, fogFactor );
#endif`,ou=`#ifdef USE_FOG
	uniform vec3 fogColor;
	varying float vFogDepth;
	#ifdef FOG_EXP2
		uniform float fogDensity;
	#else
		uniform float fogNear;
		uniform float fogFar;
	#endif
#endif`,au=`#ifdef USE_GRADIENTMAP
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
}`,cu=`#ifdef USE_LIGHTMAP
	uniform sampler2D lightMap;
	uniform float lightMapIntensity;
#endif`,lu=`LambertMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.specularStrength = specularStrength;`,uu=`varying vec3 vViewPosition;
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
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Lambert`,hu=`uniform bool receiveShadow;
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
#if NUM_SUN_LIGHTS > 0
	struct SunLight {
		vec3 direction;
		vec3 color;
	};
	uniform SunLight sunLights[ NUM_SUN_LIGHTS ];
	void getSunLightInfo( const in SunLight sunLight, out IncidentLight light ) {
		light.color = sunLight.color;
		light.direction = sunLight.direction;
		light.visible = true;
	}
#endif
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
#include <lightprobes_pars_fragment>`,fu=`#ifdef USE_ENVMAP
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
	#ifdef USE_RETROREFLECTION
		vec3 getIBLRetroRadiance( const in vec3 viewDir, const in vec3 normal, const in float roughness ) {
			#ifdef ENVMAP_TYPE_CUBE_UV
				vec3 retroVec = normalize( mix( viewDir, normal, pow4( roughness ) ) );
				retroVec = transformDirectionByInverseViewMatrix( retroVec, viewMatrix );
				vec4 envMapColor = textureCubeUV( envMap, envMapRotation * retroVec, roughness );
				return envMapColor.rgb * envMapIntensity;
			#else
				return vec3( 0.0 );
			#endif
		}
	#endif
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
		#ifdef USE_RETROREFLECTION
			vec3 getIBLAnisotropyRetroRadiance( const in vec3 viewDir, const in vec3 normal, const in float roughness, const in vec3 bitangent, const in float anisotropy ) {
				#ifdef ENVMAP_TYPE_CUBE_UV
					vec3 bentNormal = cross( bitangent, viewDir );
					bentNormal = normalize( cross( bentNormal, bitangent ) );
					bentNormal = normalize( mix( bentNormal, normal, pow2( pow2( 1.0 - anisotropy * ( 1.0 - roughness ) ) ) ) );
					return getIBLRetroRadiance( viewDir, bentNormal, roughness );
				#else
					return vec3( 0.0 );
				#endif
			}
		#endif
	#endif
#endif`,du=`ToonMaterial material;
material.diffuseColor = diffuseColor.rgb;`,pu=`varying vec3 vViewPosition;
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
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Toon`,mu=`BlinnPhongMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.specularColor = specular;
material.specularShininess = shininess;
material.specularStrength = specularStrength;`,gu=`varying vec3 vViewPosition;
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
#define RE_IndirectDiffuse		RE_IndirectDiffuse_BlinnPhong`,_u=`PhysicalMaterial material;
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
#ifdef USE_RETROREFLECTION
	material.retroreflectivity = retroreflectivity;
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
#endif`,xu=`uniform sampler2D dfgLUT;
struct PhysicalMaterial {
	vec3 diffuseColor;
	vec3 diffuseContribution;
	vec3 specularColor;
	vec3 specularColorBlended;
	float roughness;
	float metalness;
	float specularF90;
	float dispersion;
	vec2 dfg;
	vec3 multiScatteringCompensation;
	#ifdef USE_RETROREFLECTION
		float retroreflectivity;
	#endif
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
		vec3 iridescenceF0Dielectric;
		vec3 iridescenceF0Metallic;
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
void computeMultiscatteringIridescence( const in vec2 fab, const in vec3 specularColor, const in float specularF90, const in float iridescence, const in vec3 iridescenceF0, inout vec3 singleScatter, inout vec3 multiScatter ) {
#else
void computeMultiscattering( const in vec2 fab, const in vec3 specularColor, const in float specularF90, inout vec3 singleScatter, inout vec3 multiScatter ) {
#endif
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
	vec3 specularBRDF = BRDF_GGX( directLight.direction, geometryViewDir, geometryNormal, material );
	#ifdef USE_RETROREFLECTION
		vec3 retroViewDir = reflect( - geometryViewDir, geometryNormal );
		vec3 retroSpecularBRDF = BRDF_GGX( directLight.direction, retroViewDir, geometryNormal, material );
		specularBRDF = mix( specularBRDF, retroSpecularBRDF, saturate( material.retroreflectivity ) );
	#endif
	reflectedLight.directSpecular += irradiance * specularBRDF * material.multiScatteringCompensation;
	vec3 halfDir = normalize( directLight.direction + geometryViewDir );
	float dotVH = saturate( dot( geometryViewDir, halfDir ) );
	vec3 F = F_Schlick( material.specularColor, material.specularF90, dotVH );
	#ifdef USE_RETROREFLECTION
		vec3 retroHalfDir = normalize( directLight.direction + retroViewDir );
		float dotRetroVH = saturate( dot( retroViewDir, retroHalfDir ) );
		vec3 retroF = F_Schlick( material.specularColor, material.specularF90, dotRetroVH );
		F = mix( F, retroF, saturate( material.retroreflectivity ) );
	#endif
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseContribution ) * ( 1.0 - F );
}
void RE_IndirectDiffuse_Physical( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
	vec3 singleScattering = vec3( 0.0 );
	vec3 multiScattering = vec3( 0.0 );
	#ifdef USE_IRIDESCENCE
		computeMultiscatteringIridescence( material.dfg, material.specularColor, material.specularF90, material.iridescence, material.iridescenceF0Dielectric, singleScattering, multiScattering );
	#else
		computeMultiscattering( material.dfg, material.specularColor, material.specularF90, singleScattering, multiScattering );
	#endif
	vec3 diffuse = irradiance * BRDF_Lambert( material.diffuseContribution ) * ( 1.0 - singleScattering - multiScattering );
	#ifdef USE_SHEEN
		float sheenAlbedo = IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness );
		sheenSpecularIndirect += irradiance * material.sheenColor * sheenAlbedo * RECIPROCAL_PI;
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
		computeMultiscatteringIridescence( material.dfg, material.specularColor, material.specularF90, material.iridescence, material.iridescenceF0Dielectric, singleScatteringDielectric, multiScatteringDielectric );
		computeMultiscatteringIridescence( material.dfg, material.diffuseColor, material.specularF90, material.iridescence, material.iridescenceF0Metallic, singleScatteringMetallic, multiScatteringMetallic );
	#else
		computeMultiscattering( material.dfg, material.specularColor, material.specularF90, singleScatteringDielectric, multiScatteringDielectric );
		computeMultiscattering( material.dfg, material.diffuseColor, material.specularF90, singleScatteringMetallic, multiScatteringMetallic );
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
}`,yu=`
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
		vec3 iridescenceFresnelDielectric = evalIridescence( 1.0, material.iridescenceIOR, dotNVi, material.iridescenceThickness, material.specularColor );
		vec3 iridescenceFresnelMetallic = evalIridescence( 1.0, material.iridescenceIOR, dotNVi, material.iridescenceThickness, material.diffuseColor );
		material.iridescenceFresnel = mix( iridescenceFresnelDielectric, iridescenceFresnelMetallic, material.metalness );
		material.iridescenceF0Dielectric = Schlick_to_F0( iridescenceFresnelDielectric, 1.0, dotNVi );
		material.iridescenceF0Metallic = Schlick_to_F0( iridescenceFresnelMetallic, 1.0, dotNVi );
	}
#endif
#ifdef STANDARD
	float dotNVms = saturate( dot( geometryNormal, geometryViewDir ) );
	material.dfg = texture2D( dfgLUT, vec2( material.roughness, dotNVms ) ).rg;
	#if ( NUM_SUN_LIGHTS > 0 || NUM_DIR_LIGHTS > 0 || NUM_POINT_LIGHTS > 0 || NUM_SPOT_LIGHTS > 0 )
		float EssMs = material.dfg.x + material.dfg.y;
		material.multiScatteringCompensation = 1.0 + material.specularColorBlended * ( 1.0 / EssMs - 1.0 );
	#endif
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
#if ( NUM_SUN_LIGHTS > 0 ) && defined( RE_Direct )
	SunLight sunLight;
	#if defined( USE_SHADOWMAP ) && NUM_SUN_LIGHT_SHADOWS > 0
	SunLightShadow sunLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SUN_LIGHTS; i ++ ) {
		sunLight = sunLights[ i ];
		getSunLightInfo( sunLight, directLight );
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_SUN_LIGHT_SHADOWS )
		sunLightShadow = sunLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getSunShadow( sunShadowMap[ i ], sunLightShadow, UNROLLED_LOOP_INDEX ) : 1.0;
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
#endif`,vu=`#if defined( RE_IndirectDiffuse )
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
		vec3 iblRadiance = getIBLAnisotropyRadiance( geometryViewDir, geometryNormal, material.roughness, material.anisotropyB, material.anisotropy );
	#else
		vec3 iblRadiance = getIBLRadiance( geometryViewDir, geometryNormal, material.roughness );
	#endif
	#ifdef USE_RETROREFLECTION
		#ifdef USE_ANISOTROPY
			vec3 retroIBLRadiance = getIBLAnisotropyRetroRadiance( geometryViewDir, geometryNormal, material.roughness, material.anisotropyB, material.anisotropy );
		#else
			vec3 retroIBLRadiance = getIBLRetroRadiance( geometryViewDir, geometryNormal, material.roughness );
		#endif
		iblRadiance = mix( iblRadiance, retroIBLRadiance, saturate( material.retroreflectivity ) );
	#endif
	radiance += iblRadiance;
	#ifdef USE_CLEARCOAT
		clearcoatRadiance += getIBLRadiance( geometryViewDir, geometryClearcoatNormal, material.clearcoatRoughness );
	#endif
#endif`,Su=`#if defined( RE_IndirectDiffuse )
	#if defined( LAMBERT ) || defined( PHONG )
		irradiance += iblIrradiance;
	#endif
	RE_IndirectDiffuse( irradiance, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
#endif
#if defined( RE_IndirectSpecular )
	RE_IndirectSpecular( radiance, iblIrradiance, clearcoatRadiance, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
#endif`,Mu=`#ifdef USE_LIGHT_PROBES_GRID
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
#endif`,bu=`#if defined( USE_LOGARITHMIC_DEPTH_BUFFER )
	gl_FragDepth = vIsPerspective == 0.0 ? gl_FragCoord.z : log2( vFragDepth ) * logDepthBufFC * 0.5;
#endif`,wu=`#if defined( USE_LOGARITHMIC_DEPTH_BUFFER )
	uniform float logDepthBufFC;
	varying float vFragDepth;
	varying float vIsPerspective;
#endif`,Au=`#ifdef USE_LOGARITHMIC_DEPTH_BUFFER
	varying float vFragDepth;
	varying float vIsPerspective;
#endif`,Tu=`#ifdef USE_LOGARITHMIC_DEPTH_BUFFER
	vFragDepth = 1.0 + gl_Position.w;
	vIsPerspective = float( isPerspectiveMatrix( projectionMatrix ) );
#endif`,Eu=`#ifdef USE_MAP
	vec4 sampledDiffuseColor = texture2D( map, vMapUv );
	#ifdef DECODE_VIDEO_TEXTURE
		sampledDiffuseColor = sRGBTransferEOTF( sampledDiffuseColor );
	#endif
	diffuseColor *= sampledDiffuseColor;
#endif`,Cu=`#ifdef USE_MAP
	uniform sampler2D map;
#endif`,Ru=`#if defined( USE_MAP ) || defined( USE_ALPHAMAP )
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
#endif`,Iu=`#if defined( USE_POINTS_UV )
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
#endif`,Pu=`float metalnessFactor = metalness;
#ifdef USE_METALNESSMAP
	vec4 texelMetalness = texture2D( metalnessMap, vMetalnessMapUv );
	metalnessFactor *= texelMetalness.b;
#endif`,Nu=`#ifdef USE_METALNESSMAP
	uniform sampler2D metalnessMap;
#endif`,Lu=`#ifdef USE_INSTANCING_MORPH
	float morphTargetInfluences[ MORPHTARGETS_COUNT ];
	float morphTargetBaseInfluence = texelFetch( morphTexture, ivec2( 0, gl_InstanceID ), 0 ).r;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		morphTargetInfluences[i] =  texelFetch( morphTexture, ivec2( i + 1, gl_InstanceID ), 0 ).r;
	}
#endif`,Du=`#if defined( USE_MORPHCOLORS )
	vColor *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		#if defined( USE_COLOR_ALPHA )
			if ( morphTargetInfluences[ i ] != 0.0 ) vColor += getMorph( gl_VertexID, i, 2 ) * morphTargetInfluences[ i ];
		#elif defined( USE_COLOR )
			if ( morphTargetInfluences[ i ] != 0.0 ) vColor += getMorph( gl_VertexID, i, 2 ).rgb * morphTargetInfluences[ i ];
		#endif
	}
#endif`,Uu=`#ifdef USE_MORPHNORMALS
	objectNormal *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		if ( morphTargetInfluences[ i ] != 0.0 ) objectNormal += getMorph( gl_VertexID, i, 1 ).xyz * morphTargetInfluences[ i ];
	}
#endif`,Fu=`#ifdef USE_MORPHTARGETS
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
#endif`,Ou=`#ifdef USE_MORPHTARGETS
	transformed *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		if ( morphTargetInfluences[ i ] != 0.0 ) transformed += getMorph( gl_VertexID, i, 0 ).xyz * morphTargetInfluences[ i ];
	}
#endif`,Bu=`float faceDirection = gl_FrontFacing ? 1.0 : - 1.0;
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
vec3 nonPerturbedNormal = normal;`,zu=`#ifdef USE_NORMALMAP_OBJECTSPACE
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
#endif`,ku=`#ifndef FLAT_SHADED
	varying vec3 vNormal;
	#ifdef USE_TANGENT
		varying vec3 vTangent;
		varying vec3 vBitangent;
	#endif
#endif`,Vu=`#ifndef FLAT_SHADED
	varying vec3 vNormal;
	#ifdef USE_TANGENT
		varying vec3 vTangent;
		varying vec3 vBitangent;
	#endif
#endif`,Gu=`#ifndef FLAT_SHADED
	vNormal = normalize( transformedNormal );
	#ifdef USE_TANGENT
		vTangent = normalize( transformedTangent );
		vBitangent = normalize( cross( vNormal, vTangent ) * tangent.w );
		#ifdef FLIP_SIDED
			vBitangent = - vBitangent;
		#endif
	#endif
#endif`,Hu=`#ifdef USE_NORMALMAP
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
#endif`,Wu=`#ifdef USE_CLEARCOAT
	vec3 clearcoatNormal = nonPerturbedNormal;
#endif`,Xu=`#ifdef USE_CLEARCOAT_NORMALMAP
	vec3 clearcoatMapN = texture2D( clearcoatNormalMap, vClearcoatNormalMapUv ).xyz * 2.0 - 1.0;
	clearcoatMapN.xy *= clearcoatNormalScale;
	clearcoatNormal = normalize( tbn2 * clearcoatMapN );
#endif`,qu=`#ifdef USE_CLEARCOATMAP
	uniform sampler2D clearcoatMap;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	uniform sampler2D clearcoatNormalMap;
	uniform vec2 clearcoatNormalScale;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	uniform sampler2D clearcoatRoughnessMap;
#endif`,$u=`#ifdef USE_IRIDESCENCEMAP
	uniform sampler2D iridescenceMap;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	uniform sampler2D iridescenceThicknessMap;
#endif`,Yu=`#ifdef OPAQUE
diffuseColor.a = 1.0;
#endif
#ifdef USE_TRANSMISSION
diffuseColor.a *= material.transmissionAlpha;
#endif
gl_FragColor = vec4( outgoingLight, diffuseColor.a );`,Zu=`vec3 packNormalToRGB( const in vec3 normal ) {
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
}`,Ju=`#ifdef PREMULTIPLIED_ALPHA
	gl_FragColor.rgb *= gl_FragColor.a;
#endif`,Ku=`vec4 mvPosition = vec4( transformed, 1.0 );
#ifdef USE_BATCHING
	mvPosition = batchingMatrix * mvPosition;
#endif
#ifdef USE_INSTANCING
	mvPosition = instanceMatrix * mvPosition;
#endif
mvPosition = modelViewMatrix * mvPosition;
gl_Position = projectionMatrix * mvPosition;`,ju=`#ifdef DITHERING
	gl_FragColor.rgb = dithering( gl_FragColor.rgb );
#endif`,Qu=`#ifdef DITHERING
	vec3 dithering( vec3 color ) {
		float grid_position = rand( gl_FragCoord.xy );
		vec3 dither_shift_RGB = vec3( 0.25 / 255.0, -0.25 / 255.0, 0.25 / 255.0 );
		dither_shift_RGB = mix( 2.0 * dither_shift_RGB, -2.0 * dither_shift_RGB, grid_position );
		return color + dither_shift_RGB;
	}
#endif`,th=`float roughnessFactor = roughness;
#ifdef USE_ROUGHNESSMAP
	vec4 texelRoughness = texture2D( roughnessMap, vRoughnessMapUv );
	roughnessFactor *= texelRoughness.g;
#endif`,eh=`#ifdef USE_ROUGHNESSMAP
	uniform sampler2D roughnessMap;
#endif`,nh=`#if NUM_SPOT_LIGHT_COORDS > 0
	varying vec4 vSpotLightCoord[ NUM_SPOT_LIGHT_COORDS ];
#endif
#if NUM_SPOT_LIGHT_MAPS > 0
	uniform sampler2D spotLightMap[ NUM_SPOT_LIGHT_MAPS ];
#endif
#ifdef USE_SHADOWMAP
	#if NUM_SUN_LIGHT_SHADOWS > 0
		#define SUN_LIGHT_CASCADES 2
		#if defined( SHADOWMAP_TYPE_PCF )
			uniform sampler2DShadow sunShadowMap[ NUM_SUN_LIGHT_SHADOWS ];
		#else
			uniform sampler2D sunShadowMap[ NUM_SUN_LIGHT_SHADOWS ];
		#endif
		uniform mat4 sunShadowMatrix[ NUM_SUN_LIGHT_SHADOWS * SUN_LIGHT_CASCADES ];
		uniform vec4 sunShadowCascade[ NUM_SUN_LIGHT_SHADOWS * SUN_LIGHT_CASCADES ];
		varying vec4 vSunShadowWorldPosition;
		varying vec3 vSunShadowWorldNormal;
		struct SunLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform SunLightShadow sunLightShadows[ NUM_SUN_LIGHT_SHADOWS ];
	#endif
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
	#if NUM_SUN_LIGHT_SHADOWS > 0
		float getSunShadow(
			#if defined( SHADOWMAP_TYPE_PCF )
				sampler2DShadow shadowMap,
			#else
				sampler2D shadowMap,
			#endif
			SunLightShadow sunLightShadow,
			int shadowIndex
		) {
			vec4 shadowWorldPosition = vec4( vSunShadowWorldPosition.xyz + vSunShadowWorldNormal * sunLightShadow.shadowNormalBias, 1.0 );
			float viewDepth = vSunShadowWorldPosition.w;
			int cascadeOffset = shadowIndex * SUN_LIGHT_CASCADES;
			float shadow = 1.0;
			for ( int i = SUN_LIGHT_CASCADES - 1; i >= 0; i -- ) {
				vec4 cascade = sunShadowCascade[ cascadeOffset + i ];
				if ( viewDepth >= cascade.x && viewDepth < cascade.y ) {
					float cascadeShadow = getShadow(
						shadowMap,
						sunLightShadow.shadowMapSize,
						sunLightShadow.shadowIntensity,
						sunLightShadow.shadowBias,
						sunLightShadow.shadowRadius,
						sunShadowMatrix[ cascadeOffset + i ] * shadowWorldPosition
					);
					shadow = mix( cascadeShadow, shadow, smoothstep( cascade.z, cascade.y, viewDepth ) );
				}
			}
			return shadow;
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
#endif`,ih=`#if NUM_SPOT_LIGHT_COORDS > 0
	uniform mat4 spotLightMatrix[ NUM_SPOT_LIGHT_COORDS ];
	varying vec4 vSpotLightCoord[ NUM_SPOT_LIGHT_COORDS ];
#endif
#ifdef USE_SHADOWMAP
	#if NUM_SUN_LIGHT_SHADOWS > 0
		varying vec4 vSunShadowWorldPosition;
		varying vec3 vSunShadowWorldNormal;
	#endif
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
#endif`,sh=`#if ( defined( USE_SHADOWMAP ) && ( NUM_DIR_LIGHT_SHADOWS > 0 || NUM_SUN_LIGHT_SHADOWS > 0 || NUM_POINT_LIGHT_SHADOWS > 0 ) ) || ( NUM_SPOT_LIGHT_COORDS > 0 )
	#ifdef HAS_NORMAL
		vec3 shadowWorldNormal = transformNormalByInverseViewMatrix( transformedNormal, viewMatrix );
	#else
		vec3 shadowWorldNormal = vec3( 0.0 );
	#endif
	vec4 shadowWorldPosition;
#endif
#if defined( USE_SHADOWMAP )
	#if NUM_SUN_LIGHT_SHADOWS > 0
		vSunShadowWorldPosition = vec4( worldPosition.xyz, - mvPosition.z );
		vSunShadowWorldNormal = shadowWorldNormal;
	#endif
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
#endif`,rh=`float getShadowMask() {
	float shadow = 1.0;
	#ifdef USE_SHADOWMAP
	#if NUM_SUN_LIGHT_SHADOWS > 0
	SunLightShadow sunLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SUN_LIGHT_SHADOWS; i ++ ) {
		sunLight = sunLightShadows[ i ];
		shadow *= receiveShadow ? getSunShadow( sunShadowMap[ i ], sunLight, UNROLLED_LOOP_INDEX ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
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
}`,oh=`#ifdef USE_SKINNING
	mat4 boneMatX = getBoneMatrix( skinIndex.x );
	mat4 boneMatY = getBoneMatrix( skinIndex.y );
	mat4 boneMatZ = getBoneMatrix( skinIndex.z );
	mat4 boneMatW = getBoneMatrix( skinIndex.w );
#endif`,ah=`#ifdef USE_SKINNING
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
#endif`,ch=`#ifdef USE_SKINNING
	vec4 skinVertex = bindMatrix * vec4( transformed, 1.0 );
	vec4 skinned = vec4( 0.0 );
	skinned += boneMatX * skinVertex * skinWeight.x;
	skinned += boneMatY * skinVertex * skinWeight.y;
	skinned += boneMatZ * skinVertex * skinWeight.z;
	skinned += boneMatW * skinVertex * skinWeight.w;
	transformed = ( bindMatrixInverse * skinned ).xyz;
#endif`,lh=`#ifdef USE_SKINNING
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
#endif`,uh=`float specularStrength;
#ifdef USE_SPECULARMAP
	vec4 texelSpecular = texture2D( specularMap, vSpecularMapUv );
	specularStrength = texelSpecular.r;
#else
	specularStrength = 1.0;
#endif`,hh=`#ifdef USE_SPECULARMAP
	uniform sampler2D specularMap;
#endif`,fh=`#if defined( TONE_MAPPING )
	gl_FragColor.rgb = toneMapping( gl_FragColor.rgb );
#endif`,dh=`#ifndef saturate
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
vec3 CustomToneMapping( vec3 color ) { return color; }`,ph=`#ifdef USE_TRANSMISSION
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
#endif`,mh=`#ifdef USE_TRANSMISSION
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
#endif`,gh=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
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
#endif`,_h=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
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
#endif`,xh=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
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
#endif`,yh=`#if defined( USE_ENVMAP ) || defined( DISTANCE ) || defined ( USE_SHADOWMAP ) || defined ( USE_TRANSMISSION ) || NUM_SPOT_LIGHT_COORDS > 0
	vec4 worldPosition = vec4( transformed, 1.0 );
	#ifdef USE_BATCHING
		worldPosition = batchingMatrix * worldPosition;
	#endif
	#ifdef USE_INSTANCING
		worldPosition = instanceMatrix * worldPosition;
	#endif
	worldPosition = modelMatrix * worldPosition;
#endif`,vh=`varying vec2 vUv;
uniform mat3 uvTransform;
void main() {
	vUv = ( uvTransform * vec3( uv, 1 ) ).xy;
	gl_Position = vec4( position.xy, 1.0, 1.0 );
}`,Sh=`uniform sampler2D t2D;
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
}`,Mh=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
	gl_Position.z = gl_Position.w;
}`,bh=`#ifdef ENVMAP_TYPE_CUBE
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
}`,wh=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
	gl_Position.z = gl_Position.w;
}`,Ah=`uniform samplerCube tCube;
uniform float tFlip;
uniform float opacity;
varying vec3 vWorldDirection;
void main() {
	vec4 texColor = textureCube( tCube, vec3( tFlip * vWorldDirection.x, vWorldDirection.yz ) );
	gl_FragColor = texColor;
	gl_FragColor.a *= opacity;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,Th=`#include <common>
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
}`,Eh=`#if DEPTH_PACKING == 3200
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
}`,Ch=`#define DISTANCE
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
}`,Rh=`#define DISTANCE
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
}`,Ih=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
}`,Ph=`uniform sampler2D tEquirect;
varying vec3 vWorldDirection;
#include <common>
void main() {
	vec3 direction = normalize( vWorldDirection );
	vec2 sampleUV = equirectUv( direction );
	gl_FragColor = texture2D( tEquirect, sampleUV );
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,Nh=`uniform float scale;
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
}`,Lh=`uniform vec3 diffuse;
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
}`,Dh=`#include <common>
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
}`,Uh=`uniform vec3 diffuse;
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
}`,Fh=`#define LAMBERT
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
}`,Oh=`#define LAMBERT
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
}`,Bh=`#define MATCAP
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
}`,zh=`#define MATCAP
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
}`,kh=`#define NORMAL
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
}`,Vh=`#define NORMAL
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
}`,Gh=`#define PHONG
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
}`,Hh=`#define PHONG
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
}`,Wh=`#define STANDARD
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
}`,Xh=`#define STANDARD
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
#ifdef USE_RETROREFLECTION
	uniform float retroreflectivity;
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
}`,qh=`#define TOON
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
}`,$h=`#define TOON
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
}`,Yh=`uniform float size;
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
}`,Zh=`uniform vec3 diffuse;
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
}`,Jh=`#include <common>
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
}`,Kh=`uniform vec3 color;
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
}`,jh=`uniform float rotation;
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
}`,Qh=`uniform vec3 diffuse;
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
}`,Z={alphahash_fragment:vl,alphahash_pars_fragment:Sl,alphamap_fragment:Ml,alphamap_pars_fragment:bl,alphatest_fragment:wl,alphatest_pars_fragment:Al,aomap_fragment:Tl,aomap_pars_fragment:El,batching_pars_vertex:Cl,batching_vertex:Rl,begin_vertex:Il,beginnormal_vertex:Pl,bsdfs:Nl,iridescence_fragment:Ll,bumpmap_pars_fragment:Dl,clipping_planes_fragment:Ul,clipping_planes_pars_fragment:Fl,clipping_planes_pars_vertex:Ol,clipping_planes_vertex:Bl,color_fragment:zl,color_pars_fragment:kl,color_pars_vertex:Vl,color_vertex:Gl,common:Hl,cube_uv_reflection_fragment:Wl,defaultnormal_vertex:Xl,displacementmap_pars_vertex:ql,displacementmap_vertex:$l,emissivemap_fragment:Yl,emissivemap_pars_fragment:Zl,colorspace_fragment:Jl,colorspace_pars_fragment:Kl,envmap_fragment:jl,envmap_common_pars_fragment:Ql,envmap_pars_fragment:tu,envmap_pars_vertex:eu,envmap_physical_pars_fragment:fu,envmap_vertex:nu,fog_vertex:iu,fog_pars_vertex:su,fog_fragment:ru,fog_pars_fragment:ou,gradientmap_pars_fragment:au,lightmap_pars_fragment:cu,lights_lambert_fragment:lu,lights_lambert_pars_fragment:uu,lights_pars_begin:hu,lights_toon_fragment:du,lights_toon_pars_fragment:pu,lights_phong_fragment:mu,lights_phong_pars_fragment:gu,lights_physical_fragment:_u,lights_physical_pars_fragment:xu,lights_fragment_begin:yu,lights_fragment_maps:vu,lights_fragment_end:Su,lightprobes_pars_fragment:Mu,logdepthbuf_fragment:bu,logdepthbuf_pars_fragment:wu,logdepthbuf_pars_vertex:Au,logdepthbuf_vertex:Tu,map_fragment:Eu,map_pars_fragment:Cu,map_particle_fragment:Ru,map_particle_pars_fragment:Iu,metalnessmap_fragment:Pu,metalnessmap_pars_fragment:Nu,morphinstance_vertex:Lu,morphcolor_vertex:Du,morphnormal_vertex:Uu,morphtarget_pars_vertex:Fu,morphtarget_vertex:Ou,normal_fragment_begin:Bu,normal_fragment_maps:zu,normal_pars_fragment:ku,normal_pars_vertex:Vu,normal_vertex:Gu,normalmap_pars_fragment:Hu,clearcoat_normal_fragment_begin:Wu,clearcoat_normal_fragment_maps:Xu,clearcoat_pars_fragment:qu,iridescence_pars_fragment:$u,opaque_fragment:Yu,packing:Zu,premultiplied_alpha_fragment:Ju,project_vertex:Ku,dithering_fragment:ju,dithering_pars_fragment:Qu,roughnessmap_fragment:th,roughnessmap_pars_fragment:eh,shadowmap_pars_fragment:nh,shadowmap_pars_vertex:ih,shadowmap_vertex:sh,shadowmask_pars_fragment:rh,skinbase_vertex:oh,skinning_pars_vertex:ah,skinning_vertex:ch,skinnormal_vertex:lh,specularmap_fragment:uh,specularmap_pars_fragment:hh,tonemapping_fragment:fh,tonemapping_pars_fragment:dh,transmission_fragment:ph,transmission_pars_fragment:mh,uv_pars_fragment:gh,uv_pars_vertex:_h,uv_vertex:xh,worldpos_vertex:yh,background_vert:vh,background_frag:Sh,backgroundCube_vert:Mh,backgroundCube_frag:bh,cube_vert:wh,cube_frag:Ah,depth_vert:Th,depth_frag:Eh,distance_vert:Ch,distance_frag:Rh,equirect_vert:Ih,equirect_frag:Ph,linedashed_vert:Nh,linedashed_frag:Lh,meshbasic_vert:Dh,meshbasic_frag:Uh,meshlambert_vert:Fh,meshlambert_frag:Oh,meshmatcap_vert:Bh,meshmatcap_frag:zh,meshnormal_vert:kh,meshnormal_frag:Vh,meshphong_vert:Gh,meshphong_frag:Hh,meshphysical_vert:Wh,meshphysical_frag:Xh,meshtoon_vert:qh,meshtoon_frag:$h,points_vert:Yh,points_frag:Zh,shadow_vert:Jh,shadow_frag:Kh,sprite_vert:jh,sprite_frag:Qh},H={common:{diffuse:{value:new yt(16777215)},opacity:{value:1},map:{value:null},mapTransform:{value:new Y},alphaMap:{value:null},alphaMapTransform:{value:new Y},alphaTest:{value:0}},specularmap:{specularMap:{value:null},specularMapTransform:{value:new Y}},envmap:{envMap:{value:null},envMapRotation:{value:new Y},reflectivity:{value:1},ior:{value:1.5},refractionRatio:{value:.98},dfgLUT:{value:null}},aomap:{aoMap:{value:null},aoMapIntensity:{value:1},aoMapTransform:{value:new Y}},lightmap:{lightMap:{value:null},lightMapIntensity:{value:1},lightMapTransform:{value:new Y}},bumpmap:{bumpMap:{value:null},bumpMapTransform:{value:new Y},bumpScale:{value:1}},normalmap:{normalMap:{value:null},normalMapTransform:{value:new Y},normalScale:{value:new _t(1,1)}},displacementmap:{displacementMap:{value:null},displacementMapTransform:{value:new Y},displacementScale:{value:1},displacementBias:{value:0}},emissivemap:{emissiveMap:{value:null},emissiveMapTransform:{value:new Y}},metalnessmap:{metalnessMap:{value:null},metalnessMapTransform:{value:new Y}},roughnessmap:{roughnessMap:{value:null},roughnessMapTransform:{value:new Y}},gradientmap:{gradientMap:{value:null}},fog:{fogDensity:{value:25e-5},fogNear:{value:1},fogFar:{value:2e3},fogColor:{value:new yt(16777215)}},lights:{ambientLightColor:{value:[]},lightProbe:{value:[]},sunLights:{value:[],properties:{direction:{},color:{}}},sunLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},sunShadowMatrix:{value:[]},sunShadowCascade:{value:[]},directionalLights:{value:[],properties:{direction:{},color:{}}},directionalLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},directionalShadowMatrix:{value:[]},spotLights:{value:[],properties:{color:{},position:{},direction:{},distance:{},coneCos:{},penumbraCos:{},decay:{}}},spotLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},spotLightMap:{value:[]},spotLightMatrix:{value:[]},pointLights:{value:[],properties:{color:{},position:{},decay:{},distance:{}}},pointLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{},shadowCameraNear:{},shadowCameraFar:{}}},pointShadowMatrix:{value:[]},hemisphereLights:{value:[],properties:{direction:{},skyColor:{},groundColor:{}}},rectAreaLights:{value:[],properties:{color:{},position:{},width:{},height:{}}},ltc_1:{value:null},ltc_2:{value:null},probesSH:{value:null},probesMin:{value:new k},probesMax:{value:new k},probesResolution:{value:new k}},points:{diffuse:{value:new yt(16777215)},opacity:{value:1},size:{value:1},scale:{value:1},map:{value:null},alphaMap:{value:null},alphaMapTransform:{value:new Y},alphaTest:{value:0},uvTransform:{value:new Y}},sprite:{diffuse:{value:new yt(16777215)},opacity:{value:1},center:{value:new _t(.5,.5)},rotation:{value:0},map:{value:null},mapTransform:{value:new Y},alphaMap:{value:null},alphaMapTransform:{value:new Y},alphaTest:{value:0}}},Eo={basic:{uniforms:wt([H.common,H.specularmap,H.envmap,H.aomap,H.lightmap,H.fog]),vertexShader:Z.meshbasic_vert,fragmentShader:Z.meshbasic_frag},lambert:{uniforms:wt([H.common,H.specularmap,H.envmap,H.aomap,H.lightmap,H.emissivemap,H.bumpmap,H.normalmap,H.displacementmap,H.fog,H.lights,{emissive:{value:new yt(0)},envMapIntensity:{value:1}}]),vertexShader:Z.meshlambert_vert,fragmentShader:Z.meshlambert_frag},phong:{uniforms:wt([H.common,H.specularmap,H.envmap,H.aomap,H.lightmap,H.emissivemap,H.bumpmap,H.normalmap,H.displacementmap,H.fog,H.lights,{emissive:{value:new yt(0)},specular:{value:new yt(1118481)},shininess:{value:30},envMapIntensity:{value:1}}]),vertexShader:Z.meshphong_vert,fragmentShader:Z.meshphong_frag},standard:{uniforms:wt([H.common,H.envmap,H.aomap,H.lightmap,H.emissivemap,H.bumpmap,H.normalmap,H.displacementmap,H.roughnessmap,H.metalnessmap,H.fog,H.lights,{emissive:{value:new yt(0)},roughness:{value:1},metalness:{value:0},envMapIntensity:{value:1}}]),vertexShader:Z.meshphysical_vert,fragmentShader:Z.meshphysical_frag},toon:{uniforms:wt([H.common,H.aomap,H.lightmap,H.emissivemap,H.bumpmap,H.normalmap,H.displacementmap,H.gradientmap,H.fog,H.lights,{emissive:{value:new yt(0)}}]),vertexShader:Z.meshtoon_vert,fragmentShader:Z.meshtoon_frag},matcap:{uniforms:wt([H.common,H.bumpmap,H.normalmap,H.displacementmap,H.fog,{matcap:{value:null}}]),vertexShader:Z.meshmatcap_vert,fragmentShader:Z.meshmatcap_frag},points:{uniforms:wt([H.points,H.fog]),vertexShader:Z.points_vert,fragmentShader:Z.points_frag},dashed:{uniforms:wt([H.common,H.fog,{scale:{value:1},dashSize:{value:1},totalSize:{value:2}}]),vertexShader:Z.linedashed_vert,fragmentShader:Z.linedashed_frag},depth:{uniforms:wt([H.common,H.displacementmap]),vertexShader:Z.depth_vert,fragmentShader:Z.depth_frag},normal:{uniforms:wt([H.common,H.bumpmap,H.normalmap,H.displacementmap,{opacity:{value:1}}]),vertexShader:Z.meshnormal_vert,fragmentShader:Z.meshnormal_frag},sprite:{uniforms:wt([H.sprite,H.fog]),vertexShader:Z.sprite_vert,fragmentShader:Z.sprite_frag},background:{uniforms:{uvTransform:{value:new Y},t2D:{value:null},backgroundIntensity:{value:1}},vertexShader:Z.background_vert,fragmentShader:Z.background_frag},backgroundCube:{uniforms:{envMap:{value:null},backgroundBlurriness:{value:0},backgroundIntensity:{value:1},backgroundRotation:{value:new Y}},vertexShader:Z.backgroundCube_vert,fragmentShader:Z.backgroundCube_frag},cube:{uniforms:{tCube:{value:null},tFlip:{value:-1},opacity:{value:1}},vertexShader:Z.cube_vert,fragmentShader:Z.cube_frag},equirect:{uniforms:{tEquirect:{value:null}},vertexShader:Z.equirect_vert,fragmentShader:Z.equirect_frag},distance:{uniforms:wt([H.common,H.displacementmap,{referencePosition:{value:new k},nearDistance:{value:1},farDistance:{value:1e3}}]),vertexShader:Z.distance_vert,fragmentShader:Z.distance_frag},shadow:{uniforms:wt([H.lights,H.fog,{color:{value:new yt(0)},opacity:{value:1}}]),vertexShader:Z.shadow_vert,fragmentShader:Z.shadow_frag}};Eo.physical={uniforms:wt([Eo.standard.uniforms,{clearcoat:{value:0},clearcoatMap:{value:null},clearcoatMapTransform:{value:new Y},clearcoatNormalMap:{value:null},clearcoatNormalMapTransform:{value:new Y},clearcoatNormalScale:{value:new _t(1,1)},clearcoatRoughness:{value:0},clearcoatRoughnessMap:{value:null},clearcoatRoughnessMapTransform:{value:new Y},dispersion:{value:0},retroreflectivity:{value:0},iridescence:{value:0},iridescenceMap:{value:null},iridescenceMapTransform:{value:new Y},iridescenceIOR:{value:1.3},iridescenceThicknessMinimum:{value:100},iridescenceThicknessMaximum:{value:400},iridescenceThicknessMap:{value:null},iridescenceThicknessMapTransform:{value:new Y},sheen:{value:0},sheenColor:{value:new yt(0)},sheenColorMap:{value:null},sheenColorMapTransform:{value:new Y},sheenRoughness:{value:1},sheenRoughnessMap:{value:null},sheenRoughnessMapTransform:{value:new Y},transmission:{value:0},transmissionMap:{value:null},transmissionMapTransform:{value:new Y},transmissionSamplerSize:{value:new _t},transmissionSamplerMap:{value:null},thickness:{value:0},thicknessMap:{value:null},thicknessMapTransform:{value:new Y},attenuationDistance:{value:0},attenuationColor:{value:new yt(0)},specularColor:{value:new yt(1,1,1)},specularColorMap:{value:null},specularColorMapTransform:{value:new Y},specularIntensity:{value:1},specularIntensityMap:{value:null},specularIntensityMapTransform:{value:new Y},anisotropyVector:{value:new _t},anisotropyMap:{value:null},anisotropyMapTransform:{value:new Y}}]),vertexShader:Z.meshphysical_vert,fragmentShader:Z.meshphysical_frag};var tf=new Y;tf.set(-1,0,0,0,1,0,0,0,1);var wv={[Ps]:"LINEAR_TONE_MAPPING",[Ns]:"REINHARD_TONE_MAPPING",[Ls]:"CINEON_TONE_MAPPING",[Ds]:"ACES_FILMIC_TONE_MAPPING",[Fs]:"AGX_TONE_MAPPING",[Os]:"NEUTRAL_TONE_MAPPING",[Us]:"CUSTOM_TONE_MAPPING"};var Av=new Float32Array(16),Tv=new Float32Array(9),Ev=new Float32Array(4);var Cv={[Ps]:"Linear",[Ns]:"Reinhard",[Ls]:"Cineon",[Ds]:"ACESFilmic",[Fs]:"AgX",[Os]:"Neutral",[Us]:"Custom"};var Rv={[so]:"SHADOWMAP_TYPE_PCF",[ro]:"SHADOWMAP_TYPE_VSM"};var Iv={[lo]:"ENVMAP_TYPE_CUBE",[zs]:"ENVMAP_TYPE_CUBE",[uo]:"ENVMAP_TYPE_CUBE_UV"};var Pv={[zs]:"ENVMAP_MODE_REFRACTION"};var Nv={[oo]:"ENVMAP_BLENDING_MULTIPLY",[ao]:"ENVMAP_BLENDING_MIX",[co]:"ENVMAP_BLENDING_ADD"};var ef=new Y;ef.set(-1,0,0,0,1,0,0,0,1);var Lv=new Uint16Array([12469,15057,12620,14925,13266,14620,13807,14376,14323,13990,14545,13625,14713,13328,14840,12882,14931,12528,14996,12233,15039,11829,15066,11525,15080,11295,15085,10976,15082,10705,15073,10495,13880,14564,13898,14542,13977,14430,14158,14124,14393,13732,14556,13410,14702,12996,14814,12596,14891,12291,14937,11834,14957,11489,14958,11194,14943,10803,14921,10506,14893,10278,14858,9960,14484,14039,14487,14025,14499,13941,14524,13740,14574,13468,14654,13106,14743,12678,14818,12344,14867,11893,14889,11509,14893,11180,14881,10751,14852,10428,14812,10128,14765,9754,14712,9466,14764,13480,14764,13475,14766,13440,14766,13347,14769,13070,14786,12713,14816,12387,14844,11957,14860,11549,14868,11215,14855,10751,14825,10403,14782,10044,14729,9651,14666,9352,14599,9029,14967,12835,14966,12831,14963,12804,14954,12723,14936,12564,14917,12347,14900,11958,14886,11569,14878,11247,14859,10765,14828,10401,14784,10011,14727,9600,14660,9289,14586,8893,14508,8533,15111,12234,15110,12234,15104,12216,15092,12156,15067,12010,15028,11776,14981,11500,14942,11205,14902,10752,14861,10393,14812,9991,14752,9570,14682,9252,14603,8808,14519,8445,14431,8145,15209,11449,15208,11451,15202,11451,15190,11438,15163,11384,15117,11274,15055,10979,14994,10648,14932,10343,14871,9936,14803,9532,14729,9218,14645,8742,14556,8381,14461,8020,14365,7603,15273,10603,15272,10607,15267,10619,15256,10631,15231,10614,15182,10535,15118,10389,15042,10167,14963,9787,14883,9447,14800,9115,14710,8665,14615,8318,14514,7911,14411,7507,14279,7198,15314,9675,15313,9683,15309,9712,15298,9759,15277,9797,15229,9773,15166,9668,15084,9487,14995,9274,14898,8910,14800,8539,14697,8234,14590,7790,14479,7409,14367,7067,14178,6621,15337,8619,15337,8631,15333,8677,15325,8769,15305,8871,15264,8940,15202,8909,15119,8775,15022,8565,14916,8328,14804,8009,14688,7614,14569,7287,14448,6888,14321,6483,14088,6171,15350,7402,15350,7419,15347,7480,15340,7613,15322,7804,15287,7973,15229,8057,15148,8012,15046,7846,14933,7611,14810,7357,14682,7069,14552,6656,14421,6316,14251,5948,14007,5528,15356,5942,15356,5977,15353,6119,15348,6294,15332,6551,15302,6824,15249,7044,15171,7122,15070,7050,14949,6861,14818,6611,14679,6349,14538,6067,14398,5651,14189,5311,13935,4958,15359,4123,15359,4153,15356,4296,15353,4646,15338,5160,15311,5508,15263,5829,15188,6042,15088,6094,14966,6001,14826,5796,14678,5543,14527,5287,14377,4985,14133,4586,13869,4257,15360,1563,15360,1642,15358,2076,15354,2636,15341,3350,15317,4019,15273,4429,15203,4732,15105,4911,14981,4932,14836,4818,14679,4621,14517,4386,14359,4156,14083,3795,13808,3437,15360,122,15360,137,15358,285,15355,636,15344,1274,15322,2177,15281,2765,15215,3223,15120,3451,14995,3569,14846,3567,14681,3466,14511,3305,14344,3121,14037,2800,13753,2467,15360,0,15360,1,15359,21,15355,89,15346,253,15325,479,15287,796,15225,1148,15133,1492,15008,1749,14856,1882,14685,1886,14506,1783,14324,1608,13996,1398,13702,1183]);Fn();function Ys(n,t,e,i){let s=e;if(i>=n[s])return s-1;if(i<=n[t])return t;let r=t,o=s,a=r+o>>1;for(;i<n[a]||i>=n[a+1];)i<n[a]?o=a:r=a,a=r+o>>1;return a}d(Ys,"findSpan");var Fo=new Map;function On(n,t){let e=Fo.get(t);e||Fo.set(t,e=[]);let i=e[n];return i||(e[n]=i=new Float64Array(t)),i}d(On,"scratch");function Zs(n,t,e,i,s){let r=On(0,t+1),o=On(1,t+1);s[0]=1;for(let a=1;a<=t;a+=1){r[a]=i-n[e+1-a],o[a]=n[e+a]-i;let c=0;for(let l=0;l<a;l+=1){let u=s[l]/(o[l+1]+r[a-l]);s[l]=c+o[l+1]*u,c=r[a-l]*u}s[a]=c}return s}d(Zs,"basisFunctions");function Oo(n,t,e,i){let s=n.deg,r=ae(t,n.poles),o=ae(t,n.knots),a=n.weights?ae(t,n.weights):null;if(n.period){let[f,p]=n.range;(e>p||e<f)&&(e=f+((e-f)%n.period+n.period)%n.period)}let c=Ys(o,s,n.n,e),l=Zs(o,s,c,e,On(2,s+1)),u=[0,0,0],h=0;for(let f=0;f<=s;f+=1){let p=c-s+f,m=a?a[p]:1,g=l[f]*m;for(let _=0;_<i;_+=1)u[_]+=g*r[p*i+_];h+=g}for(let f=0;f<i;f+=1)u[f]/=h;return u.slice(0,i)}d(Oo,"evaluateBSplineCurve");var Nf={line(n,t){let{origin:e,dir:i}=n;return[e[0]+t*i[0],e[1]+t*i[1],e[2]+t*i[2]]},circle(n,t){let e=rt(t)*n.radius,i=ht(t)*n.radius;return Re(n,e,i,0)},ellipse(n,t){let e=rt(t)*n.majorRadius,i=ht(t)*n.minorRadius;return Re(n,e,i,0)}};function Jt(n,t,e){let i=Nf[n.kind];if(i)return i(n,e);if(n.kind==="bspline")return Oo(n,t,e,3);throw new Error(`unknown curve kind ${n.kind}`)}d(Jt,"evaluateCurve3");function Bn(n,t,e){return Oo(n,t,e,2)}d(Bn,"evaluatePCurve");function Re(n,t,e,i){let{origin:s,xdir:r,ydir:o,zdir:a}=n;return[s[0]+t*r[0]+e*o[0]+i*a[0],s[1]+t*r[1]+e*o[1]+i*a[1],s[2]+t*r[2]+e*o[2]+i*a[2]]}d(Re,"frameMix");function Lf(n,t,e,i){let{degU:s,degV:r,nu:o,nv:a}=n,c=ae(t,n.poles),l=ae(t,n.knotsU),u=ae(t,n.knotsV),h=n.weights?ae(t,n.weights):null,f=Ys(l,s,o,e),p=Ys(u,r,a,i),m=Zs(l,s,f,e,On(2,s+1)),g=Zs(u,r,p,i,On(3,r+1)),_=0,x=0,v=0,y=0;for(let M=0;M<=s;M+=1){let A=f-s+M;for(let b=0;b<=r;b+=1){let S=p-r+b,w=A*a+S,R=h?h[w]:1,I=m[M]*g[b]*R;_+=I*c[w*3],x+=I*c[w*3+1],v+=I*c[w*3+2],y+=I}}return[_/y,x/y,v/y]}d(Lf,"evaluateNurbsSurface");var Df={plane(n,t,e){return Re(n,t,e,0)},cylinder(n,t,e){let i=n.radius;return Re(n,i*rt(t),i*ht(t),e)},cone(n,t,e){let i=n.radius+e*ht(n.semiAngle);return Math.abs(i)<(Math.abs(n.radius)+Math.abs(e))*Number.EPSILON*4&&(i=0),Re(n,i*rt(t),i*ht(t),e*rt(n.semiAngle))},sphere(n,t,e){let i=n.radius,s=Math.abs(rt(e))<Number.EPSILON*4?0:rt(e);return Re(n,i*s*rt(t),i*s*ht(t),i*ht(e))},torus(n,t,e){let i=n.majorRadius+n.minorRadius*rt(e);return Re(n,i*rt(t),i*ht(t),n.minorRadius*ht(e))}};function lt(n,t,e,i){let s=Df[n.kind];if(s)return s(n,e,i);if(n.kind==="nurbs")return Lf(n,t,e,i);if(n.kind==="revolution"){let r=Jt(n.profile,t,i);return Uf(r,n.origin,n.dir,e)}if(n.kind==="extrusion"){let r=Jt(n.profile,t,e);return[r[0]+i*n.dir[0],r[1]+i*n.dir[1],r[2]+i*n.dir[2]]}throw new Error(`unknown surface kind ${n.kind}`)}d(lt,"evaluateSurface");function Uf(n,t,e,i){let s=n[0]-t[0],r=n[1]-t[1],o=n[2]-t[2],[a,c,l]=e,u=rt(i),h=ht(i),f=a*s+c*r+l*o,p=c*o-l*r,m=l*s-a*o,g=a*r-c*s;return[t[0]+s*u+p*h+a*f*(1-u),t[1]+r*u+m*h+c*f*(1-u),t[2]+o*u+g*h+l*f*(1-u)]}d(Uf,"rotateAroundAxis");function zn(n,t,e,i,s,r){if(["plane","cylinder","cone","sphere","torus"].includes(n.kind)){let{xdir:S,ydir:w,zdir:R}=n,I=[S[1]*w[2]-S[2]*w[1],S[2]*w[0]-S[0]*w[2],S[0]*w[1]-S[1]*w[0]],N=I[0]*R[0]+I[1]*R[1]+I[2]*R[2]<0?-1:1,C=0,T=0,P=1;if(n.kind!=="plane"){let E=n.kind==="cone"?-n.semiAngle:n.kind==="cylinder"?0:i;C=rt(e)*rt(E),T=ht(e)*rt(E),P=ht(E)}let D=(r?-1:1)*N;return[0,1,2].map(E=>D*(C*S[E]+T*w[E]+P*R[E]))}let[o,a,c,l]=s,u=Math.max((a-o)*1e-4,1e-7),h=Math.max((l-c)*1e-4,1e-7),f=lt(n,t,e-u,i),p=lt(n,t,e+u,i),m=lt(n,t,e,i-h),g=lt(n,t,e,i+h),_=[p[0]-f[0],p[1]-f[1],p[2]-f[2]],x=[g[0]-m[0],g[1]-m[1],g[2]-m[2]],v=_[1]*x[2]-_[2]*x[1],y=_[2]*x[0]-_[0]*x[2],M=_[0]*x[1]-_[1]*x[0],A=Math.sqrt(v*v+y*y+M*M)||1,b=r?-1:1;return v=v/A*b,y=y/A*b,M=M/A*b,[v,y,M]}d(zn,"evaluateSurfaceNormal");Fn();var xe=4,Ct={chordTolerance:.0015,loopTolerance:5e-4,angleTolerance:.35,maxRefineDepth:7,minLoopSegments:8};function Q(n,t){return[n[0]-t[0],n[1]-t[1],n[2]-t[2]]}d(Q,"sub");function et(n){return Math.sqrt(n[0]*n[0]+n[1]*n[1]+n[2]*n[2])}d(et,"length3");function kn(n,t){return n.kind==="sphere"?Math.abs(rt(t))<1e-12:n.kind==="cone"?Math.abs(n.radius+t*ht(n.semiAngle))<(Math.abs(n.radius)+Math.abs(t))*1e-12:!1}d(kn,"singularU");function Bo(n,t,e,i,s){let r=[],o=[],a=[],c=[];for(let l=0;n.surface.kind!=="plane"&&l<2;l+=1){let u=n.uv[l*2],h=n.uv[l*2+1];c.push({d:l,lo:u,hi:h,epsilon:Math.max(Math.abs(u),Math.abs(h),h-u,1e-12)*2**-23})}for(let l of t){let u=!l.reversed,h=l.edgeOrd?s?.get(l.edgeOrd):null,f=null,p=null;if(h&&h.points.length>=2){let m=Of(n,l,e,i,h);m&&(f=m.uvs,p=m.fractions)}f||(f=Ff(n,l,e,i));for(let m of f)for(let{d:g,lo:_,hi:x,epsilon:v}of c)Math.abs(m[g]-_)<=v?m[g]=_:Math.abs(m[g]-x)<=v&&(m[g]=x);u||(f.reverse(),p?.reverse());for(let m=0;m<f.length-1;m+=1)r.push(f[m]),o.push(l.edgeOrd||0),a.push(p?{ord:l.edgeOrd,f0:p[m],f1:p[m+1]}:null)}return r.segmentOrds=o,r.segmentMeta=a,r}d(Bo,"sampleLoopPolygon");function Ho(n,t,e,i){let[s,r]=t.range,o=n.surface,a=d(g=>Bn(t,e,g),"uvOf"),c=d(g=>lt(o,e,g[0],g[1]),"xyzOf"),l=c(a(s)),u=c(a(r)),h=et(Q(l,u))<=i,f=Math.max(h?Ct.minLoopSegments:2,t.n??2),p=[];for(let g=0;g<=f;g+=1)p.push(s+(r-s)*g/f);let m=0;for(;m<Ct.maxRefineDepth;){let g=!1,_=[p[0]];for(let x=0;x+1<p.length;x+=1){let v=p[x],y=p[x+1],M=(v+y)/2,A=c(a(v)),b=c(a(y)),S=c(a(M)),w=[(A[0]+b[0])/2,(A[1]+b[1])/2,(A[2]+b[2])/2];et(Q(S,w))>i&&(_.push(M),g=!0),_.push(y)}if(p.length=0,p.push(..._),!g)break;m+=1}return{params:p,uvs:p.map(a)}}d(Ho,"samplePCurveParams");function Ff(n,t,e,i){return Ho(n,t,e,i).uvs}d(Ff,"samplePCurveAdaptive");function Of(n,t,e,i,s){let r=Ho(n,t,e,i);if(r.uvs.length<2)return null;let o=n.surface,a=r.uvs.map(A=>lt(o,e,A[0],A[1])),c=[0];for(let A=1;A<a.length;A+=1)c.push(c[A-1]+et(Q(a[A],a[A-1])));let l=c[c.length-1];if(!(l>0))return null;for(let A=0;A<c.length;A+=1)c[A]/=l;let u=s.points[0],h=s.points[s.points.length-1],f=et(Q(u,a[0]))+et(Q(h,a[a.length-1])),m=et(Q(u,a[a.length-1]))+et(Q(h,a[0]))<f,g=[],_=[],x=[],v=s.boundarySubset||s.points.map((A,b)=>b),y=v.length,M=0;for(let A=0;A<y;A+=1){let b=v[m?y-1-A:A],S=s.fractions[b],w=m?1-S:S;for(;M+1<c.length-1&&c[M+1]<w;)M+=1;let R;if(A===0)R=r.params[0];else if(A===y-1)R=r.params[r.params.length-1];else{let T=c[M],P=c[M+1],D=P>T?(w-T)/(P-T):0;R=r.params[M]+D*(r.params[M+1]-r.params[M])}let I=Bn(t,e,R),N=s.points[b],C=lt(o,e,I[0],I[1]);if(et(Q(C,N))>i*2)return null;g.push(I),_.push(S),x.push(R)}if(o.kind!=="plane"){let A=g.map(b=>lt(o,e,b[0],b[1]));for(let b=0;b<4;b+=1){let S=!1,w=[g[0]],R=[_[0]],I=[x[0]],N=[A[0]];for(let C=0;C+1<g.length;C+=1){let T=A[C],P=A[C+1],D=(x[C]+x[C+1])/2,E=Bn(t,e,D),L=lt(o,e,E[0],E[1]),F=[(T[0]+P[0])/2,(T[1]+P[1])/2,(T[2]+P[2])/2];et(Q(L,F))>i&&(w.push(E),R.push((_[C]+_[C+1])/2),I.push(D),N.push(L),S=!0),w.push(g[C+1]),R.push(_[C+1]),I.push(x[C+1]),N.push(A[C+1])}if(g.length=0,_.length=0,x.length=0,A.length=0,g.push(...w),_.push(...R),x.push(...I),A.push(...N),!S)break}}return{uvs:g,fractions:_}}d(Of,"mapSharedEdgeToPCurve");function Ii(n,t,e){let i=n.fractions,s=i.length-1;if(t<=i[0])return n.points[0];if(t>=i[s])return n.points[s];let r=0,o=s;for(;r+1<o;){let f=r+o>>1;i[f]<=t?r=f:o=f}let a=i[r],c=i[r+1];if(t===a)return n.points[r];if(t===c)return n.points[r+1];let l=c>a?(t-a)/(c-a):0;if(n.curve&&e){let f=n.params[r]+l*(n.params[r+1]-n.params[r]);return Jt(n.curve,e,f)}let u=n.points[r],h=n.points[r+1];return[u[0]+l*(h[0]-u[0]),u[1]+l*(h[1]-u[1]),u[2]+l*(h[2]-u[2])]}d(Ii,"edgePointAt");function Bf(n,t,e){let[i,s]=n.range,r=Jt(n,t,i),o=Jt(n,t,s),a=!1;if(n.kind!=="line"){let g=et(Q(r,o));for(let _ of[.25,.5,.75])g=Math.max(g,et(Q(r,Jt(n,t,i+_*(s-i)))));a=et(Q(r,o))<=g*2**-21}let c=n.kind==="line"?1:Math.max(a?8:4,n.n??2),l=[];for(let g=0;g<=c;g+=1)l.push(i+(s-i)*g/c);let u=0;for(;u<Ct.maxRefineDepth;){let g=!1,_=[l[0]];for(let x=0;x+1<l.length;x+=1){let v=l[x],y=l[x+1],M=(v+y)/2,A=Jt(n,t,v),b=Jt(n,t,y),S=Jt(n,t,M),w=[(A[0]+b[0])/2,(A[1]+b[1])/2,(A[2]+b[2])/2];et(Q(S,w))>e&&(_.push(M),g=!0),_.push(y)}if(l.length=0,l.push(..._),!g)break;u+=1}let h=l.map(g=>Jt(n,t,g));a&&h.length>1&&(h[h.length-1]=h[0]);let f=[0];for(let g=1;g<h.length;g+=1)f.push(f[g-1]+et(Q(h[g],h[g-1])));let p=f[f.length-1];if(p>0){for(let g=0;g<f.length;g+=1)f[g]/=p;f[f.length-1]=1}let m=[0];{let g=e*(Ct.loopTolerance/Ct.chordTolerance),_=0;for(let x=1;x<h.length;x+=1){if(x===h.length-1){m.push(x);break}let v=h[_],y=h[x+1],M=0;for(let A=_+1;A<=x;A+=1){let b=Q(h[A],v),S=Q(y,v),w=S[0]*S[0]+S[1]*S[1]+S[2]*S[2],R=w>0?(b[0]*S[0]+b[1]*S[1]+b[2]*S[2])/w:0,I=Math.max(0,Math.min(1,R)),N=[v[0]+I*S[0],v[1]+I*S[1],v[2]+I*S[2]];if(M=Math.max(M,et(Q(h[A],N))),M>g)break}M>g&&(m.push(x),_=x)}}return{curve:n,params:l,points:h,fractions:f,closed:a,length:p,boundarySubset:m}}d(Bf,"sampleSharedEdge");function zf(n){let t=0;for(let e=0;e<n.length;e+=1){let[i,s]=n[e],[r,o]=n[(e+1)%n.length];t+=i*o-r*s}return t/2}d(zf,"polygonArea");function zo(n,t,e,i,s){let[r,o,a,c]=e,l=s===0?o-r:c-a;if(l<=0)return 1;let u=4,h=0;for(let p=0;p<=u;p+=1){let m=s===0?a+(c-a)*p/u:r+(o-r)*p/u;for(let g=0;g<u;g+=1){let _=(s===0?r:a)+l*g/u,x=_+l/u,v=(_+x)/2,y=d(w=>s===0?lt(n.surface,t,w,m):lt(n.surface,t,m,w),"at"),M=y(_),A=y(x),b=y(v),S=[(M[0]+A[0])/2,(M[1]+A[1])/2,(M[2]+A[2])/2];h=Math.max(h,et(Q(b,S)))}}if(h<=i)return 1;let f=Math.sqrt(h/i);return Math.min(256,Math.max(1,Math.ceil(u*f)))}d(zo,"gridStepsForDirection");function kf(n,t,e){let i=!1;for(let s of n)for(let r=0;r<s.length;r+=1){let[o,a]=s[r],[c,l]=s[(r+1)%s.length];a>e!=l>e&&t<(c-o)*(e-a)/(l-a)+o&&(i=!i)}return i}d(kf,"pointInLoopsEvenOdd");function Vf(n,t,e,i,s){let r=n;for(let[o,a,c]of[[0,t,!1],[0,e,!0],[1,i,!1],[1,s,!0]]){let l=r;r=[];for(let u=0;u<l.length;u+=1){let h=l[u],f=l[(u+l.length-1)%l.length],p=c?h[o]<=a:h[o]>=a,m=c?f[o]<=a:f[o]>=a;if(p!==m){let g=(a-f[o])/(h[o]-f[o]);r.push([f[0]+g*(h[0]-f[0]),f[1]+g*(h[1]-f[1])])}p&&r.push(h)}if(r.length<3)return[]}return r}d(Vf,"clipPolygonToCell");function Wo(n,t,e,i,s=1/0){let r=1/0,o=-1/0,a=1/0,c=-1/0;for(let N of e)for(let[C,T]of N)C<r&&(r=C),C>o&&(o=C),T<a&&(a=T),T>c&&(c=T);if(!(o>r)||!(c>a))return null;let l=[r,o,a,c],u=Math.min(256,Math.max(zo(n,t,l,i,0),Math.ceil((o-r)/s))),h=Math.min(256,Math.max(zo(n,t,l,i,1),n.surface.kind==="sphere"?Math.ceil((c-a)/s):1)),f=(o-r)/u,p=(c-a)/h,m=d((N,C)=>[Math.min(u-1,Math.max(0,Math.floor((N-r)/f))),Math.min(h-1,Math.max(0,Math.floor((C-a)/p)))],"cellOf"),g=new Set,_=[],x=new Map;for(let N of e){let C=N.segmentOrds||[],T=N.segmentMeta||[];for(let P=0;P<N.length;P+=1){let[D,E]=N[P],[L,F]=N[(P+1)%N.length],O=_.length;_.push([D,E,L,F,C[P]||0,T[P]||null]);let[U,B]=m(Math.min(D,L),Math.min(E,F)),[z,G]=m(Math.max(D,L),Math.max(E,F));for(let X=U;X<=z;X+=1)for(let V=B;V<=G;V+=1){let W=X*h+V;g.add(W);let q=x.get(W);q||x.set(W,q=[]),q.push(O)}}}let v=[],y=new Map,M=Math.max(Math.abs(r),Math.abs(o),o-r,1e-12)*2**-23,A=Math.max(Math.abs(a),Math.abs(c),c-a,1e-12)*2**-23,b=d((N,C)=>{let T=Math.round((N-r)/f),P=Math.round((C-a)/p),D=T===u?o:r+T*f,E=P===h?c:a+P*p;n.surface.kind!=="plane"&&(Math.abs(N-D)<=M&&(N=D),Math.abs(C-E)<=A&&(C=E));let L=`${N}:${C}`,F=y.get(L);return F===void 0&&(F=v.length,v.push([N,C]),y.set(L,F)),F},"vertexId"),S=[],w=Math.abs((o-r)*(c-a))*1e-12||1e-30,R=[],I=[];for(let N=0;N<=u;N+=1)R.push(N===u?o:r+N*f);for(let N=0;N<=h;N+=1)I.push(N===h?c:a+N*p);for(let N=0;N<u;N+=1)for(let C=0;C<h;C+=1){let T=R[N],P=R[N+1],D=I[C],E=I[C+1];if(!g.has(N*h+C)){if(!kf(e,(T+P)/2,(D+E)/2))continue;let V=b(T,D),W=b(P,D),q=b(P,E),$=b(T,E);S.push(V,W,q,V,q,$);continue}let L=e.map(V=>Vf(V,T,P,D,E)).filter(V=>V.length>=3);if(!L.length)continue;let F=0,O=0;for(let V=0;V<L.length;V+=1){let W=Math.abs(zf(L[V]));W>O&&(O=W,F=V)}if(O<=w)continue;let U=L[F].map(([V,W])=>new _t(V,W)),B=L.filter((V,W)=>W!==F).map(V=>V.map(([W,q])=>new _t(W,q))),z;try{z=Pn.triangulateShape(U,B)}catch{continue}let G=[...U,...B.flat()],X=G.map(({x:V,y:W})=>b(V,W));for(let[V,W,q]of z){let $=G[V],tt=G[W],J=G[q],j=(tt.x-$.x)*(J.y-$.y)-(J.x-$.x)*(tt.y-$.y);Math.abs(j)/2>w&&X[V]!==X[W]&&X[W]!==X[q]&&X[q]!==X[V]&&S.push(X[V],X[W],X[q])}}return{uvVerts:v,triangles:S,vertexIds:y,segmentIndex:{segments:_,segmentsByCell:x,cellOf:m,stepsV:h}}}d(Wo,"gridTriangulate");function Gf(n,t,e,i,s,r){let o=s-e,a=r-i,c=o*o+a*a,l=c>0?((n-e)*o+(t-i)*a)/c:0;l=Math.max(0,Math.min(1,l));let u=e+l*o,h=i+l*a;return{distSq:(n-u)*(n-u)+(t-h)*(t-h),t:l}}d(Gf,"projectToSegment");function ko(n,t,e,i,s,r){let o=s-e,a=r-i,c=o*o+a*a,l=c>0?((n-e)*o+(t-i)*a)/c:0;l=Math.max(0,Math.min(1,l));let u=e+l*o,h=i+l*a;return(n-u)*(n-u)+(t-h)*(t-h)}d(ko,"pointToSegmentDistanceSq");function Hf(n,t,e,i){let s=new Map,r=d((m,g)=>m<g?m*4294967296+g:g*4294967296+m,"keyOf");for(let m=0;m<n.length;m+=3){let[g,_,x]=[n[m],n[m+1],n[m+2]];for(let[v,y]of[[g,_],[_,x],[x,g]]){let M=r(v,y);s.set(M,(s.get(M)||0)+1)}}let{segments:o,segmentsByCell:a,cellOf:c,stepsV:l}=e,u=i*i,h=new Map,f=d((m,g)=>{let _=r(m,g);if(s.get(_)!==1)return 0;let x=h.get(_);if(x!==void 0)return x;x=0;let[v,y]=t[m],[M,A]=t[g],[b,S]=c((v+M)/2,(y+A)/2),w=a.get(b*l+S)||[];for(let R of w){let[I,N,C,T,P]=o[R];if(P&&ko(v,y,I,N,C,T)<u&&ko(M,A,I,N,C,T)<u){x=P;break}}return h.set(_,x),x},"ordOfMeshEdge"),p=new Uint32Array(n.length);for(let m=0;m<n.length;m+=3){let[g,_,x]=[n[m],n[m+1],n[m+2]];p[m]=f(_,x),p[m+1]=f(x,g),p[m+2]=f(g,_)}return p}d(Hf,"attributeBoundaryEdges");function Wf(n,t,e,i={},s=null){let{chordTolerance:r,loopTolerance:o,angleTolerance:a,maxRefineDepth:c}={...Ct,...i},l=o*e,u=n.loops.map(T=>Bo(n,T,t,l,s)).filter(T=>T.length>=3);if(!u.length)return null;let h=0;{let T=1/0,P=-1/0,D=1/0,E=-1/0;for(let F of u)for(let[O,U]of F)O<T&&(T=O),O>P&&(P=O),U<D&&(D=U),U>E&&(E=U);let L=[[T,D],[P,D],[T,E],[P,E],[(T+P)/2,(D+E)/2]].map(([F,O])=>lt(n.surface,t,F,O));for(let F=0;F<L.length;F+=1)for(let O=F+1;O<L.length;O+=1)h=Math.max(h,et(Q(L[F],L[O])))}let f=Math.max(Math.min(e,h*4),1e-9),p=r*f,m=o*f,g=m<l?n.loops.map(T=>Bo(n,T,t,m,s)).filter(T=>T.length>=3):u;if(!g.length)return null;let _=g.length===1&&(kn(n.surface,n.uv[2])||kn(n.surface,n.uv[3]))&&g[0].every(([T,P])=>T===n.uv[0]||T===n.uv[1]||P===n.uv[2]||P===n.uv[3]),x=Wo(n,t,g,_?p/3:p,_?a/Math.SQRT2:1/0);if(!x)return null;let{uvVerts:v,triangles:y,vertexIds:M,segmentIndex:A}=x,b=y;if(!b.length)return null;let S=v.map(([T,P])=>lt(n.surface,t,T,P));if(_){let T=new Map,P=new Map;for(let E=0;E<v.length;E+=1){if(!kn(n.surface,v[E][1]))continue;let L=v[E][1];T.has(L)?P.set(E,T.get(L)):T.set(L,E)}let D=[];for(let E=0;E<b.length;E+=3){let[L,F,O]=b.slice(E,E+3).map(U=>P.get(U)??U);et(Q(S[L],S[F]))<=e*1e-12||et(Q(S[F],S[O]))<=e*1e-12||et(Q(S[O],S[L]))<=e*1e-12||D.push(L,F,O)}b=D}let w=d(([T,P])=>zn(n.surface,t,T,P,n.uv,!1),"vertexNormal"),R=v.map(w),I=rt(a),N=d((T,P)=>T<P?`${T}_${P}`:`${P}_${T}`,"edgeKey");for(let T=0;T<(_?0:c);T+=1){let P=new Set,D=new Map,E=d((U,B)=>{let z=N(U,B),G=D.get(z);if(G===void 0){let X=(v[U][0]+v[B][0])/2,V=(v[U][1]+v[B][1])/2,W=lt(n.surface,t,X,V),q=[(S[U][0]+S[B][0])/2,(S[U][1]+S[B][1])/2,(S[U][2]+S[B][2])/2];G=et(Q(W,q))>p||R[U][0]*R[B][0]+R[U][1]*R[B][1]+R[U][2]*R[B][2]<I,D.set(z,G)}return G},"edgeChordBad");for(let U=0;U<b.length;U+=3){let B=b[U],z=b[U+1],G=b[U+2],X=!1;for(let[Pt,pt]of[[B,z],[z,G],[G,B]])E(Pt,pt)&&(P.add(N(Pt,pt)),X=!0);if(X)continue;let V=(v[B][0]+v[z][0]+v[G][0])/3,W=(v[B][1]+v[z][1]+v[G][1])/3,q=lt(n.surface,t,V,W),$=[(S[B][0]+S[z][0]+S[G][0])/3,(S[B][1]+S[z][1]+S[G][1])/3,(S[B][2]+S[z][2]+S[G][2])/3],tt=Q(S[z],S[B]),J=Q(S[G],S[B]),j=[tt[1]*J[2]-tt[2]*J[1],tt[2]*J[0]-tt[0]*J[2],tt[0]*J[1]-tt[1]*J[0]],nt=et(j),St=R[B];if(nt>1e-30&&Math.abs((j[0]*St[0]+j[1]*St[1]+j[2]*St[2])/nt)<I||et(Q(q,$))>p){let Pt=[B,z],pt=-1;for(let[oe,Tt]of[[B,z],[z,G],[G,B]]){let Me=v[oe][0]-v[Tt][0],Xt=v[oe][1]-v[Tt][1],Nt=Me*Me+Xt*Xt;Nt>pt&&(pt=Nt,Pt=[oe,Tt])}P.add(N(Pt[0],Pt[1]))}}if(!P.size)break;let L=new Map,F=d((U,B)=>{let z=N(U,B);if(!P.has(z))return-1;let G=L.get(z);if(G===void 0){let X=(v[U][0]+v[B][0])/2,V=(v[U][1]+v[B][1])/2;G=v.length,v.push([X,V]),S.push(lt(n.surface,t,X,V)),R.push(w([X,V])),L.set(z,G)}return G},"midpointOf"),O=[];for(let U=0;U<b.length;U+=3){let B=b[U],z=b[U+1],G=b[U+2],X=F(B,z),V=F(z,G),W=F(G,B),q=(X>=0)+(V>=0)+(W>=0);if(q===0){O.push(B,z,G);continue}if(q===3)O.push(B,X,W,X,z,V,W,V,G,X,V,W);else if(q===2){let[$,tt,J,j,nt]=X>=0&&V>=0?[B,z,G,X,V]:V>=0&&W>=0?[z,G,B,V,W]:[G,B,z,W,X];O.push($,j,nt,$,nt,J,j,tt,nt)}else{let[$,tt,J,j]=X>=0?[B,z,G,X]:V>=0?[z,G,B,V]:[G,B,z,W];O.push($,j,J,j,tt,J)}}b=O}let C=new Map;if(s){let T=0,P=0;for(let[U,B]of v)T=Math.max(T,Math.abs(U)),P=Math.max(P,Math.abs(B));let D=Math.max(T,P,1)*1e-7,{segments:E,segmentsByCell:L,cellOf:F,stepsV:O}=A;for(let U=0;U<v.length;U+=1){let[B,z]=v[U],[G,X]=F(B,z),V=L.get(G*O+X);if(!V)continue;let W=new Map;for(let tt of V){let[J,j,nt,St,Qt,Pt]=E[tt];if(!Pt)continue;let pt=Gf(B,z,J,j,nt,St);if(pt.distSq>=D*D){let Me=D*D*16,Xt=(B-J)*(B-J)+(z-j)*(z-j),Nt=(B-nt)*(B-nt)+(z-St)*(z-St);if(Xt<Me)pt={distSq:Xt,t:0};else if(Nt<Me)pt={distSq:Nt,t:1};else continue}let oe=W.get(Qt);if(oe&&oe.distSq<=pt.distSq)continue;let Tt=pt.t<1e-9?0:pt.t>1-1e-9?1:pt.t;W.set(Qt,{distSq:pt.distSq,f:Pt.f0+Tt*(Pt.f1-Pt.f0)})}if(!W.size)continue;let q=[],$=null;for(let[tt,{distSq:J,f:j}]of W){let nt=s.get(tt);if(!nt)continue;let St=nt.closed&&j>=1-1e-12?0:j;q.push({ord:tt,f:St}),(!$||J<$.distSq)&&($={distSq:J,ord:tt,f:St,shared:nt})}q.length&&(q.sort((tt,J)=>tt.ord===$.ord&&tt.f===$.f?-1:J.ord===$.ord&&J.f===$.f?1:0),C.set(U,q),S[U]=Ii($.shared,$.f,t))}}return{uvVerts:v,xyz:S,nrm:R,triangles:b,segmentIndex:A,boundary:C,loops:g,singularGrid:_}}d(Wf,"tessellateFaceRaw");function Xf(n,t,e,i={}){if(t.singularGrid)return;let{chordTolerance:s,angleTolerance:r,maxRefineDepth:o}={...Ct,...i},{uvVerts:a,xyz:c,nrm:l,boundary:u}=t,h=t.mintedVerts;if(!h?.size)return;let f=t.triangles,p=0;for(let y of c)p=Math.max(p,et(Q(y,c[0])));let m=s*Math.max(p,1e-9),g=d(([y,M])=>zn(n.surface,e,y,M,n.uv,!1),"vertexNormal"),_=rt(r),x=d((y,M)=>y<M?`${y}_${M}`:`${M}_${y}`,"edgeKey"),v=Math.min(3,o);for(let y=0;y<v;y+=1){let M=new Set;for(let w=0;w<f.length;w+=3){let[R,I,N]=[f[w],f[w+1],f[w+2]];if(!(!h.has(R)&&!h.has(I)&&!h.has(N)))for(let[C,T]of[[R,I],[I,N],[N,R]]){if(u.has(C)&&u.has(T))continue;let P=(a[C][0]+a[T][0])/2,D=(a[C][1]+a[T][1])/2,E=lt(n.surface,e,P,D);if(!E||!Number.isFinite(E[0]))continue;let L=[(c[C][0]+c[T][0])/2,(c[C][1]+c[T][1])/2,(c[C][2]+c[T][2])/2];et(Q(E,L))>m&&M.add(x(C,T))}}if(!M.size)break;let A=new Map,b=d((w,R)=>{let I=x(w,R);if(!M.has(I))return-1;let N=A.get(I);if(N===void 0){let C=(a[w][0]+a[R][0])/2,T=(a[w][1]+a[R][1])/2;N=a.length,a.push([C,T]),c.push(lt(n.surface,e,C,T)),l.push(g([C,T])),A.set(I,N)}return N},"midpointOf"),S=[];for(let w=0;w<f.length;w+=3){let R=f[w],I=f[w+1],N=f[w+2],C=b(R,I),T=b(I,N),P=b(N,R),D=(C>=0)+(T>=0)+(P>=0);if(D===0)S.push(R,I,N);else if(D===3)S.push(R,C,P,C,I,T,P,T,N,C,T,P);else if(D===2){let[E,L,F,O,U]=C>=0&&T>=0?[R,I,N,C,T]:T>=0&&P>=0?[I,N,R,T,P]:[N,R,I,P,C];S.push(E,O,U,E,U,F,O,L,U)}else{let[E,L,F,O]=C>=0?[R,I,N,C]:T>=0?[I,N,R,T]:[N,R,I,P];S.push(E,O,F,O,L,F)}}f=S}t.triangles=f}d(Xf,"refineInteriorPostConform");function qf(n,t){let{uvVerts:e,xyz:i,nrm:s,triangles:r,segmentIndex:o}=t,a=new Float32Array(i.length*3),c=new Float32Array(i.length*3),l=n.reversed?-1:1;for(let m=0;m<i.length;m+=1)a.set(i[m],m*3),c[m*3]=s[m][0]*l,c[m*3+1]=s[m][1]*l,c[m*3+2]=s[m][2]*l;let u=n.reversed?Yf(r):Uint32Array.from(r),h=0,f=0;for(let[m,g]of e)h=Math.max(h,Math.abs(m)),f=Math.max(f,Math.abs(g));let p=Hf(u,e,o,Math.max(h,f,1)*1e-7);return{positions:a,normals:c,indices:u,sideOrds:p,uv:e}}d(qf,"finalizeFaceMesh");function Vo(n,t){let[e,i,s,r]=n.uv,o=i-e,a=r-s,c=1-1e-9;return(l,u)=>o>0&&Math.abs(t[l][0]-t[u][0])>=o*c||a>0&&Math.abs(t[l][1]-t[u][1])>=a*c}d(Vo,"seamImagePredicate");function Go(n,t,e){let i=d((r,o)=>{if(r===o)return!0;let a=t[r],c=t[o];return a[0]===c[0]&&a[1]===c[1]&&a[2]===c[2]},"samePoint"),s=[];for(let r=0;r<n.length;r+=3){let o=e.get(n[r])??n[r],a=e.get(n[r+1])??n[r+1],c=e.get(n[r+2])??n[r+2];i(o,a)||i(a,c)||i(c,o)||s.push(o,a,c)}return s}d(Go,"compactCollapsedTriangles");function $f(n,t,e,i=0){let s=d(u=>{let h=t.get(u),f=h?.length?i*.5/h.length:0;return Math.min(.25,Math.max(1e-9,f))},"fractionEps"),r=1e-9,o=d((u,h)=>{let f=t.get(u),p=s(u);return h<=p?0:h>=1-p?f?.closed?0:1:h},"canonicalFraction"),a=new Map,c=d((u,h)=>{let f=a.get(u);f||a.set(u,f=[]),f.push(o(u,h))},"addFraction");for(let{raw:u}of n)for(let h of u.boundary.values())for(let{ord:f,f:p}of h)c(f,p);for(let[u,h]of a){let f=s(u);h.sort((g,_)=>g-_);let p=[];for(let g of h)(!p.length||g-p[p.length-1]>f)&&p.push(g);t.get(u)?.closed&&p.length>1&&1-p[p.length-1]<=f&&p.pop(),a.set(u,p)}let l=d((u,h)=>{let f=a.get(u);if(!f)return h;let p=0,m=f.length-1;for(;p<m;){let _=p+m>>1;f[_]<h?p=_+1:m=_}let g=[f[p],f[p-1]??f[p]];return Math.abs(g[0]-h)<=Math.abs(g[1]-h)?g[0]:g[1]},"representativeOf");for(let{face:u,raw:h}of n){if(u.surface.kind==="plane"){let{origin:g,xdir:_,ydir:x}=u.surface,v=new Map,y=h.loops.map(A=>{let b=[];b.segmentOrds=[],b.segmentMeta=[];for(let S=0;S<A.length;S+=1){let w=A.segmentMeta[S],R=w&&t.get(w.ord);if(!R){b.push(A[S]),b.segmentOrds.push(A.segmentOrds[S]),b.segmentMeta.push(null);continue}let I=d(L=>l(w.ord,o(w.ord,L)),"canonical"),N=d((L,F)=>R.closed&&L===0&&F>.5?1:L,"unwrap"),C=N(I(w.f0),w.f0),T=N(I(w.f1),w.f1),P=s(w.ord),D=a.get(w.ord).filter(L=>L>Math.min(C,T)+P&&L<Math.max(C,T)-P);T<C&&D.reverse();let E=[C,...D,T];for(let L=0;L<E.length;L+=1){if(L+1<E.length&&Math.abs(E[L+1]-E[L])<=P)continue;let F=o(w.ord,E[L]),O=Ii(R,F,e),U=Q(O,g),B=[U[0]*_[0]+U[1]*_[1]+U[2]*_[2],U[0]*x[0]+U[1]*x[1]+U[2]*x[2]];L+1<E.length&&(b.push(B),b.segmentOrds.push(w.ord),b.segmentMeta.push({ord:w.ord,f0:E[L],f1:E[L+1]}));let z=`${B[0]}:${B[1]}`,G=v.get(z);G?G.labels.push({ord:w.ord,f:F}):v.set(z,{xyz:O,labels:[{ord:w.ord,f:F}]})}}return b}),M=Wo(u,e,y,1/0);M?.triangles.length&&(Object.assign(h,M,{boundary:new Map,loops:y}),h.xyz=M.uvVerts.map(([A,b],S)=>{let w=v.get(`${A}:${b}`);return w&&h.boundary.set(S,w.labels),w?.xyz??lt(u.surface,e,A,b)}),h.nrm=M.uvVerts.map(([A,b])=>zn(u.surface,e,A,b,u.uv,!1)))}for(let[g,_]of h.boundary){for(let y of _)y.f=l(y.ord,o(y.ord,y.f));_.sort((y,M)=>y.ord-M.ord||y.f-M.f);let x=_[0],v=t.get(x.ord);v&&(h.xyz[g]=Ii(v,x.f,e))}let f=Vo(u,h.uvVerts),p=new Map,m=new Map;for(let g of h.boundary.keys()){let _=h.xyz[g],x=`${_[0]}:${_[1]}:${_[2]}`,v=p.get(x);if(v===void 0){p.set(x,[g]);continue}let y=v.find(M=>!f(M,g));y!==void 0?m.set(g,y):v.push(g)}h.triangles=Go(h.triangles,h.xyz,m);for(let g of m.keys())h.boundary.delete(g)}for(let{face:u,raw:h}of n){let{uvVerts:f,xyz:p,nrm:m,boundary:g}=h;if(!g.size)continue;let _=new Map,x=d((C,T)=>C<T?C*4294967296+T:T*4294967296+C,"pairKey");for(let C=0;C<h.triangles.length;C+=3){let[T,P,D]=[h.triangles[C],h.triangles[C+1],h.triangles[C+2]];for(let[E,L]of[[T,P],[P,D],[D,T]]){let F=x(E,L);_.set(F,(_.get(F)||0)+1)}}let v=d(([C,T])=>zn(u.surface,e,C,T,u.uv,!1),"vertexNormal"),y=new Map,M=d((C,T,P,D,E)=>{let L=`${C}:${T.toFixed(12)}:${Math.min(P,D)}:${Math.max(P,D)}`,F=y.get(L);if(F!==void 0)return F;let O=[kn(u.surface,f[P][1])?f[D][0]:kn(u.surface,f[D][1])?f[P][0]:f[P][0]+E*(f[D][0]-f[P][0]),f[P][1]+E*(f[D][1]-f[P][1])];F=f.length,f.push(O);let U=Ii(t.get(C),T,e);return p.push(U),m.push(v(O)),g.set(F,[{ord:C,f:T}]),(h.mintedVerts??=new Set).add(F),y.set(L,F),F},"vertexAt"),A=d((C,T)=>{let P=g.get(C),D=g.get(T);if(!P||!D||_.get(x(C,T))!==1)return null;let E=null,L=null;for(let z of P){let G=D.find(X=>X.ord===z.ord);if(G){E=z,L=G;break}}if(!E||!L)return null;let F=a.get(E.ord);if(!F)return null;let O=t.get(E.ord),U=s(E.ord),B=[];if(O?.closed){let z=(L.f-E.f+1)%1,G=z<=.5,X=G?E.f:L.f,V=G?z:(E.f-L.f+1)%1;if(V<=U*2)return null;for(let W of F){let q=(W-X+1)%1;q>U&&q<V-U&&B.push({f:W,s:G?q/V:1-q/V})}}else{let z=Math.min(E.f,L.f),G=Math.max(E.f,L.f);if(G-z<=U*2)return null;for(let X of F)X>z+U&&X<G-U&&B.push({f:X,s:(X-E.f)/(L.f-E.f)})}return B.length?(B.sort((z,G)=>z.s-G.s),{ord:E.ord,between:B}):null},"insertsFor"),b=[],S=d((C,T,P,D)=>{if(D>24){b.push(C,T,P);return}for(let[E,L,F]of[[C,T,P],[T,P,C],[P,C,T]]){let O=A(E,L);if(O){let U=E;for(let{f:B,s:z}of O.between){let G=M(O.ord,B,E,L,z);S(U,G,F,D+1),U=G}S(U,L,F,D+1);return}}b.push(C,T,P)},"emit"),w=h.triangles;for(let C=0;C<w.length;C+=3)S(w[C],w[C+1],w[C+2],0);h.triangles=b;let R=Vo(u,f),I=new Map,N=new Map;for(let C of g.keys()){let T=p[C],P=`${T[0]}:${T[1]}:${T[2]}`,D=I.get(P);if(D===void 0){I.set(P,[C]);continue}let E=D.find(L=>!R(L,C));E!==void 0?N.set(C,E):D.push(C)}h.triangles=Go(h.triangles,p,N);for(let[C,T]of N){let P=g.get(C),D=g.get(T);if(P&&D)for(let E of P)D.some(L=>L.ord===E.ord&&L.f===E.f)||D.push(E);g.delete(C)}}}d($f,"conformBoundaries");function Yf(n){let t=new Uint32Array(n.length);for(let e=0;e<n.length;e+=3)t[e]=n[e],t[e+1]=n[e+2],t[e+2]=n[e+1];return t}d(Yf,"flipWinding");function Xo(n,t,e={}){let i=[1/0,1/0,1/0],s=[-1/0,-1/0,-1/0],r=[],o=0,a=0;for(let b of n.faces)for(let S of b.loops)for(let w of S)for(let R of[w.range[0],(w.range[0]+w.range[1])/2,w.range[1]]){let[I,N]=Bn(w,t,R),C=lt(b.surface,t,I,N);for(let T=0;T<3;T+=1)C[T]<i[T]&&(i[T]=C[T]),C[T]>s[T]&&(s[T]=C[T])}let c=Math.max(et(Q(s,i)),1e-6),{chordTolerance:l}={...Ct,...e},u=new Map;for(let b of n.edges)b.curve&&u.set(b.ord,Bf(b.curve,t,l*c));{let b=c*476837158203125e-21,S=[],w=d(R=>{for(let I of S)if(et(Q(I,R))<=b)return I;return S.push(R),R},"canonicalCorner");for(let R of u.values()){if(R.closed){let I=w(R.points[0]);R.points[0]=I,R.points[R.points.length-1]=I;continue}R.points[0]=w(R.points[0]),R.points[R.points.length-1]=w(R.points[R.points.length-1])}}let h=[];for(let b of n.faces){let S=Wf(b,t,c,e,e.noSharedBoundaries?null:u);S&&h.push({face:b,raw:S})}if(!e.noSharedBoundaries&&!e.noConformPass){$f(h,u,t,l*c);for(let{face:b,raw:S}of h)Xf(b,S,t,e)}let f=e.collectBoundaryDebug?[]:null;for(let{face:b,raw:S}of h){f&&f.push({faceOrd:b.ord,reversed:!!b.reversed,xyz:S.xyz,triangles:S.triangles.slice(),boundaryByVert:new Map(S.boundary)});let w=qf(b,S);w&&(r.push({ord:b.ord,color:b.color??null,mesh:w}),o+=w.positions.length/3,a+=w.indices.length)}let p=new Float32Array(o*3),m=new Float32Array(o*3),g=new Float32Array(o),_=new Uint32Array(a),x=new Uint32Array(a),v=[],y=0,M=0;for(let{ord:b,color:S,mesh:w}of r){p.set(w.positions,y*3),m.set(w.normals,y*3),g.fill(b,y,y+w.positions.length/3);for(let R=0;R<w.indices.length;R+=1)_[M+R]=w.indices[R]+y;w.sideOrds&&x.set(w.sideOrds,M),v.push({ord:b,color:S,indexStart:M,indexCount:w.indices.length}),y+=w.positions.length/3,M+=w.indices.length}i=[1/0,1/0,1/0],s=[-1/0,-1/0,-1/0];for(let b=0;b<p.length;b+=3)for(let S=0;S<3;S+=1){let w=p[b+S];w<i[S]&&(i[S]=w),w>s[S]&&(s[S]=w)}let A=[];for(let b of n.edges){let S=u.get(b.ord);if(!S)continue;let w=new Float32Array(S.points.length*3);for(let R=0;R<S.points.length;R+=1)w.set(S.points[R],R*3);A.push({ord:b.ord,visibilityClass:b.class,polyline:w})}return{positions:p,normals:m,faceOrds:g,indices:_,sideOrds:x,faceRanges:v,edges:A,bounds:{min:i,max:s},scale:c,...f?{boundaryDebug:f,sharedEdges:u}:{}}}d(Xo,"tessellateComponent");var Zo=1397966164,ie=4,Ni=1,Jo=16*1024,Ko=4*1024*1024,Zf=/^[0-9a-f]{64}$/,qo=new Set(["chordTolerance","chordToleranceF64","angleTolerance","angleToleranceF64"]),jo=new Set(["none","feature","tangent","seam","degenerate","boundary","nonManifold","unknown"]);function Kt(n,t){let e=typeof n=="string"?n:"";if(!Zf.test(e))throw new TypeError(`${t} must be 64 lowercase hex characters`);return e}d(Kt,"requireDigest");function $o(n){if(typeof n!="number"||!Number.isFinite(n)||n<=0)throw new TypeError("tessellation tolerances must be positive finite binary64 values");let t=new Uint8Array(8);return new DataView(t.buffer).setFloat64(0,n,!1),[...t].map(e=>e.toString(16).padStart(2,"0")).join("")}d($o,"float64Hex");var Qo=Object.freeze(["chordTolerance","angleTolerance"]),Jf=Object.freeze(Object.keys(Ct).filter(n=>!Qo.includes(n)));function Li(n={}){let t=Jf.filter(r=>Object.hasOwn(n,r)&&n[r]!==Ct[r]);if(t.length)throw new TypeError(`tessellation options are not part of the cache key: ${t.join(", ")}. Keyed options: ${Qo.join(", ")}`);let e={...Ct,...n},i=e.chordTolerance,s=e.angleTolerance;return Object.freeze({chordTolerance:i,chordToleranceF64:$o(i),angleTolerance:s,angleToleranceF64:$o(s)})}d(Li,"tessellationQuality");function Ie(n,t={}){let e=Kt(n,"surfaceInput"),i=Li(t);return`${e}-t${xe}-p${ie}-l${i.chordToleranceF64}-a${i.angleToleranceF64}`}d(Ie,"tessellationCacheKey");function ta(n,t,e={}){return`${Ie(n,e)}-s${Kt(t,"surfaceObject")}`}d(ta,"resolvedTessellationIdentity");function Kf(n){return n+3&-4}d(Kf,"align4");function Js(n){return n!==null&&typeof n=="object"&&!Array.isArray(n)}d(Js,"isObject");function Pi(n,t){return Array.isArray(n)&&n.length===t&&n.every(e=>typeof e=="number"&&Number.isFinite(e))}d(Pi,"finiteTuple");function Ks(n){return Number.isSafeInteger(n)&&n>0}d(Ks,"validOrdinal");function jf(n){if(!Array.isArray(n))return null;let t=new Map;for(let e of n){if(!Array.isArray(e)||e.length!==2||!Ks(e[0])||!jo.has(e[1])||t.has(e[0]))return null;t.set(e[0],e[1])}return t}d(jf,"edgeClassMap");function ea(n){if(!Js(n?.bounds)||!Pi(n.bounds.min,3)||!Pi(n.bounds.max,3)||n.bounds.min.some((r,o)=>r>n.bounds.max[o])||typeof n.scale!="number"||!Number.isFinite(n.scale)||n.scale<=0||n.partColor!=null&&!Pi(n.partColor,4)||!Array.isArray(n.faceRanges)||!Array.isArray(n.edges))return!1;let t=new Set,e=0;for(let r of n.faceRanges)if(!Js(r)||!Ks(r.ord)||t.has(r.ord)||!nn(r.indexStart)||!nn(r.indexCount)||r.indexStart%3!==0||r.indexCount%3!==0||r.indexStart!==e||r.color!=null&&!Pi(r.color,4)||(t.add(r.ord),e+=r.indexCount,!Number.isSafeInteger(e)))return!1;if(e!==n.indexCount)return!1;let i=jf(n.edgeClasses);if(!i)return!1;let s=new Set;for(let r of n.edges){if(!Js(r)||!Ks(r.ord)||s.has(r.ord)||!nn(r.count)||r.count%3!==0||r.visibilityClass!=null&&!jo.has(r.visibilityClass)||!i.has(r.ord)||r.visibilityClass!=null&&i.get(r.ord)!==r.visibilityClass)return!1;s.add(r.ord)}return!0}d(ea,"validRenderingMetadata");function na(n){return(Array.isArray(n?.edges)?n.edges:[]).map(e=>[e.ord,String(e.class??"none")])}d(na,"edgeClassesFromSurfIndex");function ia(n,{partColor:t=null,edgeClasses:e=null,surfaceInput:i,surfaceObject:s,tessellation:r={}}={}){let o=Array.isArray(n.edges)?n.edges:[];if(!Array.isArray(n.faceRanges)||!Array.isArray(e))throw new TypeError("TESS v4 requires complete faceRanges and edgeClasses metadata");let a=Li(r),c=Ie(i,r),l=Kt(s,"surfaceObject"),u={tessellationInput:c,surfaceInput:Kt(i,"surfaceInput"),surfaceDigest:l,quality:a,tessellatorVersion:xe,payloadVersion:ie,partColor:t??null,edgeClasses:e,faceRanges:n.faceRanges,bounds:{min:[...n.bounds.min],max:[...n.bounds.max]},scale:n.scale,positionCount:n.positions.length,normalCount:n.normals.length,faceOrdCount:n.faceOrds.length,indexCount:n.indices.length,sideOrdCount:n.sideOrds.length,edges:o.map(y=>({ord:y.ord,visibilityClass:y.visibilityClass??null,count:y.polyline.length}))};if(!ea(u))throw new TypeError("TESS v4 requires valid complete rendering metadata");let h=JSON.stringify(u),f=new TextEncoder().encode(h),p=Kf(f.length),m=n.positions.length+n.normals.length+n.faceOrds.length+n.indices.length+n.sideOrds.length+o.reduce((y,M)=>y+M.polyline.length,0),g=new Uint8Array(12+p+m*4),_=new DataView(g.buffer);_.setUint32(0,Zo,!0),_.setUint32(4,ie,!0),_.setUint32(8,p,!0),g.set(f,12),g.fill(32,12+f.length,12+p);let x=12+p,v=d((y,M)=>{new M(g.buffer,x,y.length).set(y),x+=y.length*4},"append");v(n.positions,Float32Array),v(n.normals,Float32Array),v(n.faceOrds,Float32Array),v(n.indices,Uint32Array),v(n.sideOrds,Uint32Array);for(let y of o)v(y.polyline,Float32Array);return g}d(ia,"encodeComponentTessellation");function nn(n){return Number.isSafeInteger(n)&&n>=0}d(nn,"validCount");function sa({headerBytes:n,arrayBytes:t,faceRangeCount:e,edgeCount:i,edgeClassCount:s,edgeSegmentCount:r}){if(![n,t,e,i,s,r].every(nn)||n<=0||n>Ko||n%4!==0||t%4!==0)throw new TypeError("invalid tessellation size facts");let a=t+8*r+8*n+256*(e+i+s);if(!Number.isSafeInteger(a))throw new TypeError("tessellation decoded size exceeds the safe integer range");return a}d(sa,"tessellationDecodedBytes");function Qf(n,t={}){try{if(n?.tessellatorVersion!==xe||n?.payloadVersion!==ie)return null;let e=Kt(n.surfaceInput,"surfaceInput"),i=Kt(n.surfaceDigest,"surfaceDigest"),s=n.quality;if(!s||typeof s!="object"||Array.isArray(s)||Object.keys(s).length!==qo.size||Object.keys(s).some(l=>!qo.has(l)))return null;let r=Li({chordTolerance:s.chordTolerance,angleTolerance:s.angleTolerance});if(s.chordToleranceF64!==r.chordToleranceF64||s.angleToleranceF64!==r.angleToleranceF64)return null;let o=Ie(e,r);if(n.tessellationInput!==o)return null;let a=ta(e,i,r);if(t.surfaceInput!==void 0&&Kt(t.surfaceInput,"expected surfaceInput")!==e)return null;let c=t.surfaceObject??t.surfaceDigest;return c!==void 0&&Kt(c,"expected surfaceObject")!==i||t.tessellationInput!==void 0&&String(t.tessellationInput)!==o||t.renderIdentity!==void 0&&String(t.renderIdentity)!==a||t.tessellation!==void 0&&Ie(e,t.tessellation)!==o?null:Object.freeze({surfaceInput:e,surfaceObject:i,tessellationInput:o,renderIdentity:a,quality:r,tessellatorVersion:xe,payloadVersion:ie})}catch{return null}}d(Qf,"decodedIdentity");function ra(n,t={}){if(!(n instanceof Uint8Array)||n.length<12)return null;let e=new DataView(n.buffer,n.byteOffset,n.byteLength);if(e.getUint32(0,!0)!==Zo||e.getUint32(4,!0)!==ie)return null;let i=e.getUint32(8,!0);if(i===0||i>Ko||i%4!==0||12+i>n.length)return null;let s=JSON.parse(new TextDecoder().decode(n.subarray(12,12+i))),r=Qf(s,t);if(!r||!Array.isArray(s.edges)||!Array.isArray(s.faceRanges)||!Array.isArray(s.edgeClasses))return null;let o=[s.positionCount,s.normalCount,s.faceOrdCount,s.indexCount,s.sideOrdCount],a=s.edges.map(p=>p?.count),c=[...o,...a];if(!c.every(nn)||s.positionCount%3!==0||s.normalCount!==s.positionCount||s.faceOrdCount*3!==s.positionCount||s.indexCount%3!==0||s.sideOrdCount!==s.indexCount||a.some(p=>p%3!==0)||!ea(s))return null;let l=c.reduce((p,m)=>p+m,0);if(!Number.isSafeInteger(l)||l>Number.MAX_SAFE_INTEGER/4)return null;let u=l*4;if(n.length!==12+i+u)return null;let h=Object.freeze({headerBytes:i,arrayBytes:u,faceRangeCount:s.faceRanges.length,edgeCount:s.edges.length,edgeClassCount:s.edgeClasses.length,edgeSegmentCount:a.reduce((p,m)=>p+Math.max(0,m/3-1),0)}),f=sa(h);return{header:s,identity:r,sizes:h,decodedBytes:f}}d(ra,"decodeEnvelope");function js(n,t={}){try{let e=ra(n,t);if(!e)return null;let i=Object.freeze({byteLength:n.byteLength,decodedBytes:e.decodedBytes,surfaceInput:e.identity.surfaceInput,surfaceObject:e.identity.surfaceObject,tessellationInput:e.identity.tessellationInput,renderIdentity:e.identity.renderIdentity,quality:e.identity.quality,tessellatorVersion:xe,payloadVersion:ie,...e.sizes});for(let s of["byteLength","decodedBytes","surfaceInput","surfaceObject","tessellationInput","renderIdentity","tessellatorVersion","payloadVersion","headerBytes","arrayBytes","faceRangeCount","edgeCount","edgeClassCount","edgeSegmentCount"])if(t[s]!==void 0&&t[s]!==i[s])return null;return i}catch{return null}}d(js,"tessellationPayloadFacts");var Yo=new Set(["schemaVersion","object","byteLength","decodedBytes","surfaceInput","surfaceObject","tessellationInput","renderIdentity","quality","tessellatorVersion","payloadVersion","headerBytes","arrayBytes","faceRangeCount","edgeCount","edgeClassCount","edgeSegmentCount"]);function Qs(n,t={}){try{if(!n||typeof n!="object"||Array.isArray(n)||Object.keys(n).length!==Yo.size||Object.keys(n).some(l=>!Yo.has(l))||n.schemaVersion!==Ni||n.tessellatorVersion!==xe||n.payloadVersion!==ie)return null;let e=Kt(n.surfaceInput,"surfaceInput"),i=Kt(n.surfaceObject,"surfaceObject"),s=Kt(n.object,"object"),r=Li({chordTolerance:n.quality?.chordTolerance,angleTolerance:n.quality?.angleTolerance});if(n.quality?.chordToleranceF64!==r.chordToleranceF64||n.quality?.angleToleranceF64!==r.angleToleranceF64)return null;let o=Ie(e,r),a=ta(e,i,r);if(n.tessellationInput!==o||n.renderIdentity!==a)return null;let c={headerBytes:n.headerBytes,arrayBytes:n.arrayBytes,faceRangeCount:n.faceRangeCount,edgeCount:n.edgeCount,edgeClassCount:n.edgeClassCount,edgeSegmentCount:n.edgeSegmentCount};return!nn(n.byteLength)||n.byteLength<=0||n.byteLength!==12+n.headerBytes+n.arrayBytes||n.decodedBytes!==sa(c)||t.tessellationInput!==void 0&&t.tessellationInput!==o||t.object!==void 0&&t.object!==s||t.surfaceInput!==void 0&&t.surfaceInput!==e||t.surfaceObject!==void 0&&t.surfaceObject!==i?null:Object.freeze({schemaVersion:Ni,object:s,byteLength:n.byteLength,decodedBytes:n.decodedBytes,surfaceInput:e,surfaceObject:i,tessellationInput:o,renderIdentity:a,quality:r,tessellatorVersion:xe,payloadVersion:ie,...c})}catch{return null}}d(Qs,"validateTessellationProbeRow");function oa(n,t={}){try{let e=ra(n,t);if(!e)return null;let{header:i,identity:s}=e,r=n.byteOffset+12+e.sizes.headerBytes,o=r%4===0,a=d((m,g)=>{let _=o?new g(n.buffer,r,m):new g(n.buffer.slice(r,r+m*4));return r+=m*4,_},"take"),c=a(i.positionCount,Float32Array),l=a(i.normalCount,Float32Array),u=a(i.faceOrdCount,Float32Array),h=a(i.indexCount,Uint32Array),f=a(i.sideOrdCount,Uint32Array),p=i.edges.map(m=>({ord:m.ord,visibilityClass:m.visibilityClass,polyline:a(m.count,Float32Array)}));return{component:{positions:c,normals:l,faceOrds:u,indices:h,sideOrds:f,faceRanges:i.faceRanges,edges:p,bounds:i.bounds,scale:i.scale},partColor:i.partColor??null,edgeClasses:Array.isArray(i.edgeClasses)?i.edgeClasses:null,identity:s}}catch{return null}}d(oa,"decodeComponentTessellation");var Zv=32*1024*1024;import{createHash as td,randomUUID as ed}from"node:crypto";import Rt from"node:fs";import aa from"node:os";import Ht from"node:path";var tr=class extends Error{static{d(this,"TessellationMeshConflictError")}constructor(t="tessellation producer returned different bytes for the same immutable input"){super(t),this.name="TessellationMeshConflictError"}};function ca(n=process.env){return n.CADGEN_MESH_CACHE!=="0"}d(ca,"tessellationCacheEnabled");function la(n=process.env){let t=(n.CADGEN_CACHE_DIR||"").trim();if(t){let e=t.replace(/^~(?=$|[/\\])/,aa.homedir()),i=Ht.resolve(e);return Ht.isAbsolute(e)||(n.CADGEN_CACHE_DIR=i),i}if(process.platform==="win32"){let e=(n.LOCALAPPDATA||"").trim();if(e)return Ht.join(e,"cadgen")}else{let e=(n.XDG_CACHE_HOME||"").trim();if(e)return Ht.join(e,"cadgen")}return Ht.join(aa.homedir(),".cache","cadgen")}d(la,"cadgenCacheRootDir");function nd(n=process.env){return Ht.join(la(n),"index","mesh")}d(nd,"tessellationCacheDir");function Di(n){return td("sha256").update(n).digest("hex")}d(Di,"digestBytes");function nr(n,t=process.env){return Ht.join(la(t),"objects",n.slice(0,2),n.slice(2))}d(nr,"objectPath");function ua(n,t=process.env){return Ht.join(nd(t),n)}d(ua,"indexPath");function id(n){return Ht.join(Ht.dirname(n),`.${Ht.basename(n)}.${process.pid}.${ed()}.tmp`)}d(id,"tempPath");function ha(n,t){Rt.mkdirSync(Ht.dirname(n),{recursive:!0});let e=id(n);try{Rt.writeFileSync(e,t,{flag:"wx"}),Rt.renameSync(e,n)}finally{try{Rt.unlinkSync(e)}catch{}}}d(ha,"writeAtomic");function sd(n){let t=Rt.openSync(n,"r");try{let e=Rt.fstatSync(t);if(!e.isFile()||e.size<=0||e.size>Jo)return null;let i=Buffer.allocUnsafe(e.size);return Rt.readSync(t,i,0,i.length,0)!==i.length?null:JSON.parse(i.toString("utf8"))}finally{Rt.closeSync(t)}}d(sd,"readBoundedJson");function fa(n,t=process.env){if(!ca(t))return null;try{let e=Qs(sd(ua(n,t)),{tessellationInput:n});if(!e)return null;let i=Rt.statSync(nr(e.object,t));return i.isFile()&&i.size===e.byteLength?e:null}catch{return null}}d(fa,"probeCachedTessellation");function er(n,t,e=t){if(!Number.isSafeInteger(t)||t<=0||!Number.isSafeInteger(e)||e<t)return null;let i;try{i=Rt.openSync(n,"r");let s=Rt.fstatSync(i);if(!s.isFile()||s.size!==t||s.size>e)return null;let r=Buffer.allocUnsafe(t),o=0;for(;o<r.byteLength;){let c=Rt.readSync(i,r,o,r.byteLength-o,o);if(c<=0)return null;o+=c}let a=Rt.fstatSync(i);return!a.isFile()||a.size!==t?null:new Uint8Array(r.buffer,r.byteOffset,r.byteLength)}catch{return null}finally{if(i!==void 0)try{Rt.closeSync(i)}catch{}}}d(er,"readExactObjectBytes");function ir(n,{expectedObject:t,maxBytes:e,env:i=process.env}={}){let s=fa(n,i);if(!s||t!==void 0&&s.object!==t)return null;let r=e===void 0?s.byteLength:Number(e);if(!Number.isSafeInteger(r)||r<s.byteLength)return null;let o=er(nr(s.object,i),s.byteLength,r);return!o||Di(o)!==s.object||!js(o,s)?null:o}d(ir,"readCachedTessellationBytes");function rd(n,t){let e=js(t,{tessellationInput:n});if(!e)throw new TypeError("invalid TESS v4 payload");let i=Qs({schemaVersion:Ni,object:Di(t),...e},{tessellationInput:n});if(!i)throw new TypeError("invalid TESS v4 mesh record");return i}d(rd,"recordForPayload");function od(n,t,e){let i=nr(n.object,e),s=er(i,n.byteLength);if(s&&Di(s)===n.object)return;ha(i,t);let r=er(i,n.byteLength);if(!r||Di(r)!==n.object)throw new Error(`tessellation object address mismatch for ${n.object}`)}d(od,"putObject");function da(n,t,e=process.env){if(!ca(e))return null;let i=t instanceof Uint8Array?t:new Uint8Array(t),s=rd(n,i),r=fa(n,e);if(r&&(r.object!==s.object||r.surfaceObject!==s.surfaceObject)&&ir(n,{expectedObject:r.object,env:e}))throw new tr;return od(s,i,e),ha(ua(n,e),JSON.stringify(s)),s}d(da,"writeCachedTessellationBytes");function Ui(n){return n<=.04045?n/12.92:((n+.055)/1.055)**2.4}d(Ui,"srgbToLinear");function ad(n){return n<=.0031308?n*12.92:1.055*n**(1/2.4)-.055}d(ad,"linearToSrgb");function cd(n){let t=Math.min(1,Math.max(0,Number(n)||0));return Math.round(Math.min(1,Math.max(0,ad(t)))*255)}d(cd,"linearChannelToSrgbByte");function se(n){return!Array.isArray(n)||n.length<3?null:`#${n.slice(0,3).map(e=>cd(e).toString(16).padStart(2,"0")).join("")}`}d(se,"linearRgbToHex");var sn=globalThis.Buffer,ld=typeof TextEncoder<"u"?new TextEncoder:null;function ud(n,t=0){let e=Number(n);return Number.isFinite(e)?e:t}d(ud,"finiteNumber");function Vn(n){return Math.min(Math.max(ud(n),0),1)}d(Vn,"clamp01");function Fi(n,t="utf-8"){if(sn?.from)return sn.from(String(n),t);if(t!=="utf-8"&&t!=="utf8"){let e=String(n),i=new Uint8Array(e.length);for(let s=0;s<e.length;s+=1)i[s]=e.charCodeAt(s)&255;return i}return ld.encode(String(n))}d(Fi,"bytesFromString");function re(n,t=0){if(sn?.alloc)return sn.alloc(n,t);let e=new Uint8Array(n);return t&&e.fill(t),e}d(re,"allocBytes");function rn(n,t=void 0){if(sn?.concat)return sn.concat(n,t);let e=t??n.reduce((r,o)=>r+o.length,0),i=new Uint8Array(e),s=0;for(let r of n)i.set(r,s),s+=r.length;return i}d(rn,"concatBytes");function Ot(n){return new Uint8Array(n.buffer,n.byteOffset,n.byteLength)}d(Ot,"typedArrayBytes");function sr(n){return new DataView(n.buffer,n.byteOffset,n.byteLength)}d(sr,"viewFor");function st(n,t,e){sr(n).setUint16(t,e,!0)}d(st,"writeUInt16LE");function ct(n,t,e){sr(n).setUint32(t,e,!0)}d(ct,"writeUInt32LE");function rr(n,t,e){sr(n).setFloat32(t,e,!0)}d(rr,"writeFloatLE");function ma(n,t,e,i){let s=String(e).slice(0,i);for(let r=0;r<s.length;r+=1)n[t+r]=s.charCodeAt(r)&127}d(ma,"writeAscii");function pa(n,t=32){let e=(4-n.length%4)%4;return e?rn([n,re(e,t)]):n}d(pa,"align4Buffer");function Pe(n,t="model"){return String(n||t).trim().replace(/[\x00-\x1f<>:"/\\|?*]+/g,"-")||t}d(Pe,"sanitizeName");function or(n){let t=[1/0,1/0,1/0],e=[-1/0,-1/0,-1/0];for(let i=0;i<n.length;i+=3)t[0]=Math.min(t[0],n[i]),t[1]=Math.min(t[1],n[i+1]),t[2]=Math.min(t[2],n[i+2]),e[0]=Math.max(e[0],n[i]),e[1]=Math.max(e[1],n[i+1]),e[2]=Math.max(e[2],n[i+2]);return{min:t.map(i=>Number.isFinite(i)?i:0),max:e.map(i=>Number.isFinite(i)?i:0)}}d(or,"boundsForPositions");function ga(n,t="#d4d4d8"){let e=String(n||t).trim(),i=/^#(?:[0-9a-fA-F]{3}){1,2}$/.test(e)?e:t,s=i.length===4?`${i[1]}${i[1]}${i[2]}${i[2]}${i[3]}${i[3]}`:i.slice(1);return[parseInt(s.slice(0,2),16)/255,parseInt(s.slice(2,4),16)/255,parseInt(s.slice(4,6),16)/255]}d(ga,"hexToRgb01");function _a(n,t){let e=pa(rn(t),0);n.buffers=[{byteLength:e.length}];let i=pa(Fi(JSON.stringify(n)),32),s=20+i.length+8+e.length,r=re(12);ct(r,0,1179937895),ct(r,4,2),ct(r,8,s);let o=re(8);ct(o,0,i.length),ct(o,4,1313821514);let a=re(8);return ct(a,0,e.length),ct(a,4,5130562),rn([r,o,i,a,e],s)}d(_a,"buildGlb");function hd(n,t){let e=n[t],i=n[t+1],s=n[t+2],r=n[t+3],o=n[t+4],a=n[t+5],c=n[t+6],l=n[t+7],u=n[t+8],h=r-e,f=o-i,p=a-s,m=c-e,g=l-i,_=u-s,x=f*_-p*g,v=p*m-h*_,y=h*g-f*m,M=Math.sqrt(x*x+v*v+y*y);return M>1e-12?[x/M,v/M,y/M]:[0,0,1]}d(hd,"triangleNormal");function xa(n,{name:t="model"}={}){let e=n.positions||new Float32Array,i=Math.floor(e.length/9),s=re(84+i*50);ma(s,0,`cad ${Pe(t)}`,80),ct(s,80,i);let r=84;for(let o=0;o<i;o+=1){let a=o*9,c=hd(e,a);for(let l of c)rr(s,r,l),r+=4;for(let l=0;l<9;l+=1)rr(s,r,e[a+l]),r+=4;st(s,r,0),r+=2}return s}d(xa,"meshToBinaryStl");function cr(n){return String(n??"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}d(cr,"xmlEscape");function ar(n){let t=ar.table;if(!t){t=new Uint32Array(256);for(let i=0;i<256;i+=1){let s=i;for(let r=0;r<8;r+=1)s=s&1?3988292384^s>>>1:s>>>1;t[i]=s>>>0}ar.table=t}let e=4294967295;for(let i of n)e=t[(e^i)&255]^e>>>8;return(e^4294967295)>>>0}d(ar,"crc32");function ya(n){let t=[],e=[],i=0,s=0,r=33;for(let l of n){let u=Fi(l.name),h=l.body instanceof Uint8Array?l.body:Fi(String(l.body||"")),f=ar(h),p=re(30);ct(p,0,67324752),st(p,4,20),st(p,6,0),st(p,8,0),st(p,10,s),st(p,12,r),ct(p,14,f),ct(p,18,h.length),ct(p,22,h.length),st(p,26,u.length),st(p,28,0),t.push(p,u,h);let m=re(46);ct(m,0,33639248),st(m,4,20),st(m,6,20),st(m,8,0),st(m,10,0),st(m,12,s),st(m,14,r),ct(m,16,f),ct(m,20,h.length),ct(m,24,h.length),st(m,28,u.length),st(m,30,0),st(m,32,0),st(m,34,0),st(m,36,0),ct(m,38,0),ct(m,42,i),e.push(m,u),i+=p.length+u.length+h.length}let o=i,a=rn(e),c=re(22);return ct(c,0,101010256),st(c,4,0),st(c,6,0),st(c,8,n.length),st(c,10,n.length),ct(c,12,a.length),ct(c,16,o),st(c,20,0),rn([...t,a,c])}d(ya,"zipStore");var Ne=5126,fd=5122,dd=5120,va=5123,pd=5125,ye=34962,Sa=34963,md=4,gd=65535,Le=32767,lr=127;function ur(n){return n+3&-4}d(ur,"align4");function ba(n,t){if(n.length>=t)return n;let e=new Uint8Array(t);return e.set(n,0),e}d(ba,"padTo");function Ma(n,t,e,i){if(e===t)return ba(n,ur(n.length));let s=new Uint8Array(i*e);for(let r=0;r<i;r+=1)s.set(n.subarray(r*t,(r+1)*t),r*e);return s}d(Ma,"strideElements");function _d(n,t){let e=n[t],i=n[t+1],s=n[t+2],r=n[t+3],o=n[t+4],a=n[t+5],c=n[t+6],l=n[t+7],u=n[t+8],h=r-e,f=o-i,p=a-s,m=c-e,g=l-i,_=u-s,x=f*_-p*g,v=p*m-h*_,y=h*g-f*m,M=Math.sqrt(x*x+v*v+y*y);return M>1e-12?[x/M,v/M,y/M]:[0,0,1]}d(_d,"faceNormal");function xd(n,t,{weldDecimals:e=5}={}){let i=Math.floor(n.length/3),s=10**e,r=d(h=>Math.round(h*s)/s,"q"),o=[],a=[],c=new Uint32Array(i),l=new Map,u=t&&t.length===n.length;for(let h=0;h*9<n.length;h+=1){let f=h*9,p=u?null:_d(n,f);for(let m=0;m<3;m+=1){let g=f+m*3,_=n[g],x=n[g+1],v=n[g+2],y=u?t[g]:p[0],M=u?t[g+1]:p[1],A=u?t[g+2]:p[2],b=`${r(_)},${r(x)},${r(v)},${r(y)},${r(M)},${r(A)}`,S=l.get(b);S===void 0&&(S=o.length/3,l.set(b,S),o.push(_,x,v),a.push(y,M,A)),c[h*3+m]=S}}return{positions:new Float32Array(o),normals:new Float32Array(a),indices:c.subarray(0,Math.floor(n.length/3)*3)}}d(xd,"weldMesh");function yd(n,t){let e=n.length/3,i=new Int16Array(n.length),s=[Math.max(t.max[0]-t.min[0],1e-9),Math.max(t.max[1]-t.min[1],1e-9),Math.max(t.max[2]-t.min[2],1e-9)];for(let r=0;r<e;r+=1)for(let o=0;o<3;o+=1){let a=r*3+o,c=(n[a]-t.min[o])/s[o];i[a]=Math.max(-Le,Math.min(Le,Math.round(c*Le)))}return{array:i,scale:s.map(r=>r/Le),translation:[t.min[0],t.min[1],t.min[2]]}}d(yd,"quantizePositions");function vd(n){let t=new Int8Array(n.length);for(let e=0;e<n.length;e+=1)t[e]=Math.max(-lr,Math.min(lr,Math.round(n[e]*lr)));return t}d(vd,"quantizeNormals");var Sd=.42,Md=.03;function Gn(n,t){let e=Number(n?.[t]);return Number.isFinite(e)?Vn(e):null}d(Gn,"finishChannel");function bd(n,t,e=null,i=null){let s=ga(n).map(Vn).map(Ui).map(Math.fround),r=Gn(i,"opacity"),o=e==null?r===null?1:r:Vn(e),a=Gn(i,"roughness"),c=Gn(i,"metalness"),l=Gn(i,"clearcoat"),u=Gn(i,"clearcoatRoughness"),h={name:Pe(t||"material","material"),doubleSided:!0,extras:{cadSourceColor:!0},pbrMetallicRoughness:{baseColorFactor:[...s,o],roughnessFactor:a===null?Sd:a,metallicFactor:c===null?Md:c}};return o<1&&(h.alphaMode="BLEND"),l!==null&&l>0&&(h.extensions={KHR_materials_clearcoat:{clearcoatFactor:l,...u===null?{}:{clearcoatRoughnessFactor:u}}}),h}d(bd,"materialFor");var wd=[["translation",3,"VEC3"],["rotation",4,"VEC4"],["scale",3,"VEC3"]];function Ad(n,{nodeIndexByKey:t,targetCountByKey:e,accessors:i,pushView:s}){let r=[];for(let o of Array.isArray(n)?n:[]){let a=[],c=[],l=new Map,u=d(h=>{let f=l.get(h);if(f!==void 0)return f;if(!h||!h.length)throw new Error("writeGlb: an animation channel needs a non-empty times array");return i.push({bufferView:s(Ot(h)),byteOffset:0,componentType:Ne,count:h.length,type:"SCALAR",min:[h[0]],max:[h[h.length-1]]}),f=i.length-1,l.set(h,f),f},"timeAccessorFor");for(let h of o?.channels||[]){let f=t.get(String(h?.node));if(f===void 0)throw new Error(`writeGlb: animation channel targets node ${JSON.stringify(h?.node)}, which no primitive declared`);let p=u(h?.times||o?.times);if(h?.weights){let m=h?.times||o?.times,g=Number(h.targetCount),_=e.get(String(h.node))||0;if(!Number.isInteger(g)||g<1||g!==_)throw new Error(`writeGlb: weights channel on node ${JSON.stringify(h.node)} declares ${h.targetCount} morph targets, but its mesh has ${_}`);if(h.weights.length!==m.length*g)throw new Error(`writeGlb: weights channel on node ${JSON.stringify(h.node)} has ${h.weights.length} scalars for ${m.length} times x ${g} targets`);i.push({bufferView:s(Ot(h.weights)),byteOffset:0,componentType:Ne,count:h.weights.length,type:"SCALAR"}),a.push({input:p,output:i.length-1,interpolation:"LINEAR"}),c.push({sampler:a.length-1,target:{node:f,path:"weights"}})}for(let[m,g,_]of wd){let x=h?.[m];x&&(i.push({bufferView:s(Ot(x)),byteOffset:0,componentType:Ne,count:x.length/g,type:_}),a.push({input:p,output:i.length-1,interpolation:"LINEAR"}),c.push({sampler:a.length-1,target:{node:f,path:m}}))}}c.length&&r.push({name:Pe(o?.name||"clip","clip"),samplers:a,channels:c})}return r}d(Ad,"buildAnimations");function wa(n,t={}){let{preset:e="export",name:i="model",units:s="mm",weldDecimals:r=5,encoder:o=null,occurrenceIdPrefix:a=null,upAxis:c="y",animations:l=null,nodeTransforms:u=null}=t,h=String(c).trim().toLowerCase();if(h!=="y"&&h!=="z")throw new Error(`writeGlb: upAxis must be "y" (glTF) or "z" (CAD), got ${JSON.stringify(c)}`);let f=String(a||t.sourceKind||Pe(i,"model")),p=e==="render";if(p&&!o)throw new Error("writeGlb: preset 'render' requires meshoptimizer's MeshoptEncoder (await MeshoptEncoder.ready)");if(p&&(l||u))throw new Error("writeGlb: preset 'render' spends every node transform on dequantization, so it carries no animation or node TRS \u2014 use preset 'export' for an animated file");let m=Array.isArray(n?.primitives)&&n.primitives.length?n.primitives:[{positions:n?.positions,normals:n?.normals,color:t.color}],g=[],_=[],x=[],v=[],y=[],M=[],A=new Map,b=0,S=d(E=>{let L=ur(b);L>b&&(g.push(new Uint8Array(L-b)),b=L),g.push(E);let F=b;return b+=E.length,F},"appendBytes"),w=d((E,L)=>{let O={buffer:0,byteOffset:S(E),byteLength:E.length};return L&&(O.target=L),_.push(O),_.length-1},"pushView"),R=d((E,{count:L,stride:F,mode:O,target:U})=>{let B=S(E),z={byteLength:L*F,byteStride:F,extensions:{EXT_meshopt_compression:{buffer:0,byteOffset:B,byteLength:E.length,count:L,byteStride:F,mode:O}}};return U&&(z.target=U),_.push(z),_.length-1},"pushCompressedView");for(let E of m){let L=E?.positions instanceof Float32Array?E.positions:new Float32Array(E?.positions||[]);if(!L.length)continue;let F=Array.isArray(E?.targets)&&E.targets.length?E.targets:null;if(F){if(!E?.indices)throw new Error("writeGlb: morph targets need already-indexed input \u2014 a weld can merge two vertices a target moves apart, and the deltas would then be 1:1 with nothing");if(p)throw new Error("writeGlb: preset 'render' quantizes every attribute and carries no morph targets \u2014 use preset 'export' for a deforming file")}let O=E?.indices?{positions:L,normals:E.normals instanceof Float32Array&&E.normals.length===L.length?E.normals:new Float32Array(L.length),indices:E.indices}:xd(L,E?.normals,{weldDecimals:r}),U=O.positions.length/3,B=or(O.positions),z=null;if(typeof E?.colorAt=="function"){z=new Uint16Array(U*4);for(let vt=0;vt<U;vt+=1){let ze=E.colorAt(O.positions[vt*3],O.positions[vt*3+1],O.positions[vt*3+2],O.normals[vt*3],O.normals[vt*3+1],O.normals[vt*3+2]);for(let zt=0;zt<3;zt+=1)z[vt*4+zt]=Math.round(Ui(Vn(Number(ze?.[zt])||0))*65535);z[vt*4+3]=65535}}let G,X,V=null,W,q,$=null,tt=null;if(p){let vt=yd(O.positions,B),ze=Ma(Ot(vt.array),6,8,U),zt=Ma(Ot(vd(O.normals)),3,4,U);G=R(o.encodeVertexBuffer(ze,U,8),{count:U,stride:8,mode:"ATTRIBUTES",target:ye}),X=R(o.encodeVertexBuffer(zt,U,4),{count:U,stride:4,mode:"ATTRIBUTES",target:ye}),z&&(V=R(o.encodeVertexBuffer(Ot(z),U,8),{count:U,stride:8,mode:"ATTRIBUTES",target:ye})),$=vt.scale,tt=vt.translation,W={bufferView:G,byteOffset:0,componentType:fd,count:U,type:"VEC3",min:[0,0,0],max:[Le,Le,Le]},q={bufferView:X,byteOffset:0,componentType:dd,count:U,type:"VEC3",normalized:!0}}else G=w(Ot(O.positions),ye),X=w(Ot(O.normals),ye),z&&(V=w(Ot(z),ye)),W={bufferView:G,byteOffset:0,componentType:Ne,count:U,type:"VEC3",min:B.min,max:B.max},q={bufferView:X,byteOffset:0,componentType:Ne,count:U,type:"VEC3"};let J=U<=gd,j=J?new Uint16Array(O.indices):new Uint32Array(O.indices),nt=J?2:4,St=p?R(o.encodeIndexBuffer(new Uint8Array(j.buffer,j.byteOffset,j.byteLength),j.length,nt),{count:j.length,stride:nt,mode:"TRIANGLES",target:Sa}):w(ba(Ot(j),ur(j.byteLength)),Sa);x.push(W);let Qt=x.length-1;x.push(q);let Pt=x.length-1,pt=null;z&&(x.push({bufferView:V,byteOffset:0,componentType:va,count:U,type:"VEC4",normalized:!0}),pt=x.length-1),x.push({bufferView:St,byteOffset:0,componentType:J?va:pd,count:j.length,type:"SCALAR"});let oe=x.length-1,Tt=F?.map((vt,ze)=>{let zt=vt?.positionDeltas;if(!(zt instanceof Float32Array)||zt.length!==O.positions.length)throw new Error(`writeGlb: morph target ${ze} has ${zt?.length??"no"} position deltas for ${O.positions.length/3} vertices`);let Br=or(zt);x.push({bufferView:w(Ot(zt),ye),byteOffset:0,componentType:Ne,count:U,type:"VEC3",min:Br.min,max:Br.max});let zr={POSITION:x.length-1},gn=vt?.normalDeltas;if(gn){if(!(gn instanceof Float32Array)||gn.length!==O.positions.length)throw new Error(`writeGlb: morph target ${ze} has ${gn.length} normal deltas for ${O.positions.length/3} vertices`);x.push({bufferView:w(Ot(gn),ye),byteOffset:0,componentType:Ne,count:U,type:"VEC3"}),zr.NORMAL=x.length-1}return zr})||null;M.push(bd(z?"#ffffff":E?.color,E?.materialName||E?.name,E?.opacity??null,E?.material??null));let Me={attributes:{POSITION:Qt,NORMAL:Pt,...pt===null?{}:{COLOR_0:pt}},indices:oe,material:M.length-1,mode:md,...Tt?{targets:Tt}:{}},Xt=E?.node===void 0||E?.node===null?`\0primitive:${A.size}`:String(E.node),Nt=A.get(Xt);if(!Nt)Nt={key:Xt,input:E,primitives:[],quantization:null,targetCount:Tt?Tt.length:0},A.set(Xt,Nt);else{if(Nt.targetCount!==(Tt?Tt.length:0))throw new Error(`writeGlb: node ${JSON.stringify(Xt)} mixes primitives with ${Nt.targetCount} and ${Tt?Tt.length:0} morph targets, and glTF weights are per MESH`);if(p)throw new Error(`writeGlb: preset 'render' cannot put two primitives on node ${JSON.stringify(Xt)}: each quantized primitive owns its node's transform`)}Nt.primitives.push(Me),$&&(Nt.quantization={scale:$,translation:tt})}let I=new Map,N=new Map;for(let E of A.values()){N.set(E.key,E.targetCount),v.push({primitives:E.primitives,...E.targetCount?{weights:new Array(E.targetCount).fill(0)}:{}});let L={mesh:v.length-1,name:Pe(E.input?.name||i,i),extras:{cadOccurrenceId:String(E.input?.occurrenceId||`${f}:${y.length}`),cadSourceKind:t.sourceKind||"mesh",cadUnits:s,cadUpAxis:h}};E.quantization&&(L.scale=E.quantization.scale,L.translation=E.quantization.translation);let F=u instanceof Map?u.get(E.key):null;F&&(F.translation&&(L.translation=[...F.translation]),F.rotation&&(L.rotation=[...F.rotation]),F.scale&&(L.scale=[...F.scale])),I.set(E.key,y.length),y.push(L)}let C=Ad(l,{nodeIndexByKey:I,targetCountByKey:N,accessors:x,pushView:w}),T=p?["KHR_mesh_quantization","EXT_meshopt_compression"]:[],P=[...T];M.some(E=>E.extensions?.KHR_materials_clearcoat)&&P.push("KHR_materials_clearcoat");let D={asset:{version:"2.0",generator:"cadgen-js writeGlb"},scene:0,scenes:[{nodes:y.map((E,L)=>L)}],nodes:y,meshes:v,materials:M,bufferViews:_,accessors:x,...C.length?{animations:C}:{}};return P.length&&(D.extensionsUsed=P),T.length&&(D.extensionsRequired=T),_a(D,g)}d(wa,"writeGlb");var hr=["stl","glb","3mf"],Td=4194304,Ta="#d4d4d8",Ea=["roughness","metalness","clearcoat","clearcoatRoughness","opacity"];function fr(n){if(!n||typeof n!="object"||Array.isArray(n))return null;let t={};for(let e of Ea){let i=Number(n[e]);Number.isFinite(i)&&(t[e]=Math.min(1,Math.max(0,i)))}return Object.keys(t).length?t:null}d(fr,"occurrenceMaterial");function Ed(n,t){let e=fr(n),i=Array.isArray(t)&&t.length>=4&&Number.isFinite(Number(t[3]))?Math.min(1,Math.max(0,Number(t[3]))):1;if(i>=.999)return e;let s=e&&Number.isFinite(Number(e.opacity))?e.opacity:1;return{...e||{},opacity:i*s}}d(Ed,"occurrenceMaterialWithSourceAlpha");function Aa(n){return n?`|${Ea.map(t=>t in n?n[t]:"").join(",")}`:""}d(Aa,"materialKey");function Ca(n,t,e,i=Ta){let s=String(t?.component||""),r=/^#[0-9a-fA-F]{6}$/.test(String(t?.baseColor||""))?String(t.baseColor).toUpperCase():se(t?.color),o=se(n?.components?.[s]?.color)||null,a=se(e?.partColor)||null,c=r||o||a||i;return(e?.faceRanges||[]).map(l=>se(l.color)||c)}d(Ca,"occurrenceFaceRangeColors");function dr(n,t,e,i,s,r){s[r]=n[0]*t+n[1]*e+n[2]*i+n[3],s[r+1]=n[4]*t+n[5]*e+n[6]*i+n[7],s[r+2]=n[8]*t+n[9]*e+n[10]*i+n[11]}d(dr,"transformPoint");function pr(n){return n[0]*(n[5]*n[10]-n[6]*n[9])-n[1]*(n[4]*n[10]-n[6]*n[8])+n[2]*(n[4]*n[9]-n[5]*n[8])}d(pr,"determinant3");function mr(n){let t=n[0],e=n[1],i=n[2],s=n[4],r=n[5],o=n[6],a=n[8],c=n[9],l=n[10],u=r*l-o*c,h=o*a-s*l,f=s*c-r*a,p=t*u+e*h+i*f;if(!Number.isFinite(p)||Math.abs(p)<1e-30)return null;let m=1/p;return[u*m,h*m,f*m,(i*c-e*l)*m,(t*l-i*a)*m,(e*a-t*c)*m,(e*o-i*r)*m,(i*s-t*o)*m,(t*r-e*s)*m]}d(mr,"normalMatrix3");function gr(n){return!Array.isArray(n)||n.length<12?!0:[1,0,0,0,0,1,0,0,0,0,1,0].every((e,i)=>n[i]===e)}d(gr,"identityTransform");function _r(n,t,e={}){let i=e.defaultColor||Ta,s=new Map(Object.entries(n.components||{}).map(([g,_])=>[g,se(_?.color)])),r=Math.max(1,Math.floor(Number(e.maxPrimitiveTriangles)||Td)),o=e.perOccurrence===!0,a=e.hiddenOccurrenceIds instanceof Set?e.hiddenOccurrenceIds:null,c=e.occurrenceOpacity instanceof Map?e.occurrenceOpacity:null,l=e.occurrenceOverrides instanceof Map?e.occurrenceOverrides:null;if(l&&!o)throw new Error("buildPackageMeshPrimitives: occurrenceOverrides needs perOccurrence \u2014 an override is keyed by occurrence, and the flat soup has no occurrence to key it to");let u=[],h=new Map,f=-1;for(let g of n.occurrences||[]){f+=1;let _=String(g.component||""),x=t.get(_);if(!x)continue;let v=String(g.id||_);if(a?.has(v))continue;let y=/^#[0-9a-fA-F]{6}$/.test(String(g?.baseColor||""))?String(g.baseColor).toUpperCase():se(g.color),M=s.get(_)||null,A=se(x.partColor)||null,b=y||M||A||i,S=c?.has(v)?c.get(v):null,w=Ed(g.material,g.color),R=String(g.materialId||"").trim(),I=String(g.materialName||R).trim(),N=Aa(w)+(R?`|material:${R}`:""),C=l?.get(v);if(C){C.forEach((L,F)=>{let O=`${String(f).padStart(8,"0")}|${L.color}${Aa(L.material||null)}|${String(F).padStart(4,"0")}`;h.set(O,{override:{...L,node:v,name:String(g.name||v),occurrenceId:v,...R?{materialId:R}:{},...I?{materialName:I}:{},...S==null?{}:{opacity:S}}})});continue}let T=Array.isArray(g.transform)?g.transform:null,P=T===null||gr(T),D=!P&&pr(T)<0,E=P?null:mr(T);for(let L of x.faceRanges||[]){let F=Number(L.indexCount)||0,O=Math.max(0,Math.ceil(F/3));if(!O)continue;let U=se(L.color)||b,B=(o?`${String(f).padStart(8,"0")}|${U}`:U)+N,z=h.get(B);z||h.set(B,z={color:U,material:w,materialId:R,materialName:I,chunks:[],node:o?v:null,name:o?String(g.name||v):null,occurrenceId:o?v:null,opacity:S});let G=z.chunks[z.chunks.length-1];(!G||G.triangles+O>r)&&(G={triangles:0,floatCount:0,positions:null,normals:null,offset:0},z.chunks.push(G)),G.triangles+=O,G.floatCount+=O*9,u.push({tessellation:x,range:L,color:U,chunk:G,transform:P?null:T,mirrored:D,nm:E})}}for(let g of h.values())for(let _ of g.chunks||[])_.positions=new Float32Array(_.floatCount),_.normals=new Float32Array(_.floatCount);for(let g of u){let{positions:_,normals:x,indices:v}=g.tessellation,{range:y,transform:M,mirrored:A,nm:b}=g,S=g.chunk,w=S.positions,R=S.normals,I=S.offset,N=A?[0,2,1]:[0,1,2];for(let C=y.indexStart;C<y.indexStart+y.indexCount;C+=3)for(let T of N){let P=v[C+T],D=_[P*3],E=_[P*3+1],L=_[P*3+2];M===null?(w[I]=D,w[I+1]=E,w[I+2]=L):dr(M,D,E,L,w,I);let F=x[P*3],O=x[P*3+1],U=x[P*3+2],B=F,z=O,G=U;b&&(B=b[0]*F+b[1]*O+b[2]*U,z=b[3]*F+b[4]*O+b[5]*U,G=b[6]*F+b[7]*O+b[8]*U);let X=Math.sqrt(B*B+z*z+G*G)||1;R[I]=B/X,R[I+1]=z/X,R[I+2]=G/X,I+=3}S.offset=I}let p=[...h.entries()].sort(([g],[_])=>g<_?-1:1).flatMap(([,g])=>g.override?[g.override]:g.chunks.map(_=>({color:g.color,positions:_.positions,normals:_.normals,...g.node===null?{}:{node:g.node,name:g.name,occurrenceId:g.occurrenceId},...g.opacity===null||g.opacity===void 0?{}:{opacity:g.opacity},...g.material===null?{}:{material:g.material},...g.materialId?{materialId:g.materialId}:{},...g.materialName?{materialName:g.materialName}:{}}))).filter(g=>g.indices?g.indices.length>=3:g.positions.length>=9),m=p.reduce((g,_)=>g+(_.indices?_.indices.length/3:_.positions.length/9),0);return{primitives:p,triangleCount:m}}d(_r,"buildPackageMeshPrimitives");function Cd({primitives:n},{name:t="model"}={}){let e=0;for(let r of n)e+=r.positions.length;let i=new Float32Array(e),s=0;for(let r of n)i.set(r.positions,s),s+=r.positions.length;return xa({positions:i},{name:t})}d(Cd,"packageMeshToStl");var Hn=.001;function Oi(n,t){let e=new Float32Array(n.length);for(let i=0;i<n.length;i+=3)e[i]=n[i]*t,e[i+1]=n[i+2]*t,e[i+2]=-n[i+1]*t;return e}d(Oi,"rotateToYUp");function Rd(n){return n.map(t=>({positionDeltas:Oi(t.positionDeltas,Hn),...t.normalDeltas?{normalDeltas:Oi(t.normalDeltas,1)}:{}}))}d(Rd,"yUpTargets");function Id(n){let t=n.verify;if(!t)return;let{vertexIds:e,posed:i}=t;for(let s=0;s<i.length;s+=1){let r=n.targets[s].positionDeltas;for(let o=0;o<e.length;o+=1){let a=e[o]*3,c=[i[s][o*3]*Hn,i[s][o*3+2]*Hn,-i[s][o*3+1]*Hn];for(let l=0;l<3;l+=1){let u=n.positions[a+l]+r[a+l];if(Math.abs(u-c[l])>Pd)throw new Error(`packageMeshExport: morph target ${s} of ${n.occurrenceId||n.node} rebuilds vertex ${e[o]} as ${u} where the posed tube is ${c[l]} (axis ${l}) \u2014 base and deltas are not in the same space`)}}}}d(Id,"verifyMorphReconstruction");var Pd=1e-6;function Nd(n){return n.map(t=>{let e={...t,positions:Oi(t.positions,Hn),normals:Oi(t.normals,1),...t.targets?{targets:Rd(t.targets)}:{}};return e.targets&&(Id(e),delete e.verify),e})}d(Nd,"yUpPrimitives");function Ld({primitives:n},{name:t="model",animation:e=null}={}){return wa({primitives:Nd(n)},{preset:"export",name:t,sourceKind:"step",units:"m",upAxis:"y",...e?{animations:[e],nodeTransforms:e.rest||null}:{}})}d(Ld,"packageMeshToGlb");function Dd({primitives:n},{name:t="model"}={}){let e=n.map((c,l)=>`      <base name="material-${l}" displaycolor="${cr(c.color.toUpperCase())}FF"/>`).join(`
`),i=[],s=[];n.forEach((c,l)=>{let u=[],h=[],f=new Map,p=c.positions,m=d((_,x,v)=>{let y=`${_}:${x}:${v}`,M=f.get(y);return M===void 0&&(M=f.size,f.set(y,M),u.push(`        <vertex x="${_}" y="${x}" z="${v}"/>`)),M},"vertexId");for(let _=0;_<p.length;_+=9){let x=m(p[_],p[_+1],p[_+2]),v=m(p[_+3],p[_+4],p[_+5]),y=m(p[_+6],p[_+7],p[_+8]);x!==v&&v!==y&&y!==x&&h.push(`        <triangle v1="${x}" v2="${v}" v3="${y}"/>`)}let g=l+2;i.push(`    <object id="${g}" type="model" pid="1" pindex="${l}">
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
`;return ya([{name:"[Content_Types].xml",body:`<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>
`},{name:"_rels/.rels",body:`<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
`},{name:"3D/3dmodel.model",body:r}])}d(Dd,"packageMeshTo3mf");function Ra(n,t,e={}){let i=String(t||"").toLowerCase();if(e.animation&&i!=="glb")throw new Error(`${i||"(no format)"} carries no animation: only glb does \u2014 export the clip as .glb, or drop the animation for a static mesh`);if(i==="stl")return{body:Cd(n,e),contentType:"model/stl",extension:".stl"};if(i==="glb")return{body:Ld(n,e),contentType:"model/gltf-binary",extension:".glb"};if(i==="3mf")return{body:Dd(n,e),contentType:"model/3mf",extension:".3mf"};throw new Error(`Unsupported package mesh export format: ${t}`)}d(Ra,"packageMeshToFormat");var fn=null,Wi=null;function ja(){return fn?Promise.resolve(fn):(Wi||(Wi=Promise.resolve().then(()=>(Hi(),Ka)).then(n=>(fn=n,fn)).catch(n=>{throw Wi=null,n})),Wi)}d(ja,"loadTubeDeformation");function Qa(n="a tube deformation"){if(!fn)throw new Error(`${n} needs the tube runtime, which is loaded with the document's animation. Compile clips through compileAnimationSource/loadSourceAnimation, or await loadTubeDeformation() first.`);return fn}d(Qa,"requireTubeDeformation");function tc(n){return!!n&&typeof n=="object"&&!Array.isArray(n)}d(tc,"isObject");var lp=Math.PI/180;function ec(n){let t={};for(let[e,i]of Object.entries(tc(n)?n:{})){if(!tc(i)||typeof i.update!="function")continue;let s=Number(i.duration);t[String(e)]={id:String(e),label:String(i.label||e),duration:Number.isFinite(s)&&s>0?s:1,loop:i.loop!==!1,update:i.update}}return t}d(ec,"normalizeAnimationClips");function up(n){let t=new Map;for(let e of n?.parts||[]){let i=String(e.label||e.name||"").trim();i&&(t.has(i)||t.set(i,[]),t.get(i).push(String(e.id)))}return t}d(up,"partIdsByLabel");function hp(n,t){let e=String(t).replace(/^#/,"").split(",").map(s=>s.trim()).filter(Boolean);if(!e.length||!e.every(s=>/^o[\d.]+$/.test(s)))return null;let i=[];for(let s of n?.parts||[]){let r=String(s.id);e.some(o=>r===o||r.startsWith(`${o}.`))&&i.push(r)}return i.length?i:null}d(hp,"partIdsForOccurrenceRefs");function fp(n,t){let e=up(t),i=new Map,s=new Map,r=new Map;return{model:{get:d(c=>{let l=e.get(String(c).replace(/^#/,""))||e.get(String(c))||hp(t,c);if(!l||!l.length){let f=[...e.keys()].sort().join(", ")||"(none)";throw new Error(`animation: no occurrence labeled ${JSON.stringify(c)}; labels: ${f}`)}let u=d(f=>{for(let p of l){let m=i.get(p);i.set(p,m?new n.Matrix4().multiplyMatrices(f,m):f.clone())}},"applyMatrix"),h=d((f,p)=>{for(let m of l){let g=s.get(m)||{};g[f]=p,s.set(m,g)}},"setStyle");return{deformTube(f){let p=Qa("deformTube").normalizeTubeDeformation(f);for(let m of l)r.set(m,p);return this},rotate(f,p,m=[0,0,0]){let g=new n.Vector3(f[0],f[1],f[2]).normalize(),_=new n.Matrix4().makeRotationAxis(g,(Number(p)||0)*lp),x=new n.Matrix4().makeTranslation(-m[0],-m[1],-m[2]),v=new n.Matrix4().makeTranslation(m[0],m[1],m[2]);return u(new n.Matrix4().multiplyMatrices(v,new n.Matrix4().multiplyMatrices(_,x))),this},translate(f){return u(new n.Matrix4().makeTranslation(Number(f[0])||0,Number(f[1])||0,Number(f[2])||0)),this},opacity(f){return h("opacity",Math.max(0,Math.min(1,Number(f)))),this},visible(f){return h("visible",!!f),this}}},"handleFor"),labels:d(()=>[...e.keys()].sort(),"labels")},matrices:i,styles:s,deformations:r}}d(fp,"createAnimationFrame");function Ir(n,t,e,i){let s=fp(n,t),r=e.duration||1,o=Math.max(0,Number(i)||0);return e.loop!==!1?o=o%r:o=Math.min(o,r),e.update(o,s.model),{matrices:s.matrices,styles:s.styles,deformations:s.deformations}}d(Ir,"evaluateAnimationClip");function dp(n){return String(n??"").trim()}d(dp,"normalizeString");function Pr(n){return Math.max(Number(n?.duration)||0,.001)}d(Pr,"animationClipDuration");function nc(n){return!n||typeof n!="object"?[]:Object.values(n).filter(t=>t&&typeof t.update=="function").map(t=>({id:String(t.id),label:String(t.label||t.id),duration:Pr(t),loop:t.loop!==!1}))}d(nc,"animationClipList");function ic(n,t){let e=dp(t);if(!e||!n||typeof n!="object")return null;let i=n[e];return i&&typeof i.update=="function"?i:null}d(ic,"findAnimationClip");var sc=1,rc=120,oc=7200;function dn(n){return`${Number(n.toFixed(3))}s`}d(dn,"formatSeconds");function ac(n,t,{label:e="frame"}={}){let i=n&&typeof n=="object"?n:{},s=Number(i.fps??30);if(!Number.isInteger(s)||s<sc||s>rc)throw new Error(`${e} fps must be a whole number ${sc}..${rc}, got ${JSON.stringify(i.fps)}`);let r=i.start===void 0||i.start===null?0:Number(i.start);if(!Number.isFinite(r)||r<0)throw new Error(`${e} start must be seconds >= 0, got ${JSON.stringify(i.start)}`);let o=Pr(t);if(r>=o)throw new Error(`${e} start ${dn(r)} is at or past the end of a ${dn(o)} clip: every frame would be the same one`);let a=t?.loop!==!1,c=i.seconds===void 0||i.seconds===null?a?o:o-r:Number(i.seconds);if(!Number.isFinite(c)||c<=0)throw new Error(`${e} seconds must be a positive number, got ${JSON.stringify(i.seconds)}`);let l=Math.max(1,Math.round(c*s));if(l>oc)throw new Error(`${e} ${dn(c)} at ${s} fps schedules ${l} frames, past the ${oc}-frame ceiling`);let u=[];return!a&&r+c-o>1e-9&&u.push(`${e} covers ${dn(r)}..${dn(r+c)} of a ${dn(o)} clip that does not loop: every frame past its end is the same final pose`),{fps:s,seconds:c,start:r,frameCount:l,warnings:u}}d(ac,"resolveFramePlan");function cc(n,t){return n.start+t/n.fps}d(cc,"framePlanElapsedSec");Hi();var pp={Matrix4:xt,Vector3:k},Nr=Object.freeze(["opacity","visible"]),lc=Object.freeze(["refuse","morph","rest"]),mp=4,gp=96;function _p(n){let t=Math.max(mp,Math.ceil(gp/n.fps));return{multiple:t,hz:n.fps*t,count:(n.frameCount-1)*t+1}}d(_p,"morphFitGrid");var Xi=.001;function xp(){return new xt().set(Xi,0,0,0,0,0,Xi,0,0,-Xi,0,0,0,0,0,1)}d(xp,"cadToGlbBasis");function yp(){let n=1/Xi;return new xt().set(n,0,0,0,0,0,-n,0,0,n,0,0,0,0,0,1)}d(yp,"glbToCadBasis");var vp=1e-12,Sp=new xt().elements;function Mp(n){let t=n.elements;for(let e=0;e<16;e+=1)if(Math.abs(t[e]-Sp[e])>vp)return!1;return!0}d(Mp,"isIdentityMatrix");function bp(n){let t=[];for(let e of n?.occurrences||[]){let i=String(e?.id||"").trim(),s=String(e?.component||"").trim(),r=i||s;if(!r)continue;let o=String(e?.name||i||s).trim();t.push({id:r,occurrenceId:r,componentId:s,name:o,label:o})}return{parts:t}}d(bp,"animationTargetsFromDescriptor");function Oe(n,t=6){let e=[...n].sort();return e.length<=t?e.join(", "):`${e.slice(0,t).join(", ")} (and ${e.length-t} more)`}d(Oe,"summarize");function wp(n){let t={translations:[],rotations:[],scales:[],count:0};for(let e=0;e<n;e+=1)Dr(t,null);return t}d(wp,"newTrack");var uc=new k,hc=new Yt,fc=new k;function Dr(n,t){let e=0,i=0,s=0,r=0,o=0,a=0,c=1,l=1,u=1,h=1;if(t!==null&&(t.decompose(uc,hc,fc),{x:e,y:i,z:s}=uc,{x:r,y:o,z:a,w:c}=hc,{x:l,y:u,z:h}=fc),n.count>0){let f=(n.count-1)*4;n.rotations[f]*r+n.rotations[f+1]*o+n.rotations[f+2]*a+n.rotations[f+3]*c<0&&(r=-r,o=-o,a=-a,c=-c)}n.translations.push(e,i,s),n.rotations.push(r,o,a,c),n.scales.push(l,u,h),n.count+=1}d(Dr,"appendSample");function Lr(n,t,e){for(let i=1;i<e;i+=1)for(let s=0;s<t;s+=1)if(Math.fround(n[i*t+s])!==Math.fround(n[s]))return!0;return!1}d(Lr,"varies");function Ap(n,t){for(let e=0;e<t*3;e+=1)if(Math.fround(n[e])!==1)return!1;return!0}d(Ap,"scaleIsUnit");function dc(n,t,e,{drop:i=[],deform:s="refuse"}={}){let r=new Set(i.map(I=>String(I).trim())),o=[...r].filter(I=>!Nr.includes(I));if(o.length)throw new Error(`animation drop names ${o.sort().join(", ")}, which is not an effect this export can bake static; droppable effects: ${Nr.join(", ")}`);let a=String(s||"refuse");if(!lc.includes(a))throw new Error(`animation deform must be one of ${lc.join(", ")}, got ${JSON.stringify(s)}`);let c=bp(n),l=xp(),u=yp(),h=new xt,f=new Map,p=new Map,m=new Set,g=new Set,_=new Set,x=new Set,v=new Map,y=new Set,M=a==="morph"?_p(e):{multiple:1,hz:e.fps,count:e.frameCount};for(let I=0;I<M.count;I+=1){let N=cc(e,I/M.multiple),C=Ir(pp,c,t,N),T=I%M.multiple===0?I/M.multiple:-1;if(T>=0){for(let[P,D]of C.matrices){let E=f.get(P);if(!E){if(Mp(D))continue;E=wp(T),f.set(P,E)}h.multiplyMatrices(l,D).multiply(u),Dr(E,h)}for(let P of f.values())P.count===T&&Dr(P,null);for(let[P,D]of C.styles)D&&Object.hasOwn(D,"opacity")&&(g.add(P),T===0&&p.set(P,D.opacity)),D&&Object.hasOwn(D,"visible")&&(_.add(P),T===0&&D.visible===!1&&m.add(P))}for(let[P,D]of C.deformations){if(x.add(P),D.braid&&y.add(P),a!=="morph")continue;let E=v.get(P);if(!E)E={rest:D,samples:[]},v.set(P,E);else if(!Tr(E.rest,D))throw new Error(`clip ${t.id} changes the REST path of ${P} at ${N.toFixed(4)}s, so its geometry has no single base mesh for morph targets to be deltas against. Author one rest path per tube for the whole clip (move the tube with .translate/.rotate instead), or export the clip as video (cadgen step snapshot --animation ${t.id} --video)`);E.samples.push({index:I,timeSec:I/M.hz,deformation:D===E.rest?D:{...D,restSpec:E.rest.restSpec}})}}let A=[];for(let I of Nr){let N=I==="opacity"?g:_;if(N.size){if(!r.has(I))throw new Error(`clip ${t.id} animates .${I}() on ${Oe(N)}, and glTF has no standard animated channel for it. Pass drop: ["${I}"] to bake the value at start into the file instead, or animate the occurrence's transform rather than its appearance`);A.push(`.${I}() is not an animated glTF channel: ${Oe(N)} carries its value at start, frozen for the whole clip`)}}if(x.size){if(a==="refuse")throw new Error(`clip ${t.id} deforms tube geometry on ${Oe(x)}: that is per-vertex motion, which a node transform cannot carry. Pass deform: "morph" to bake it as morph targets (bigger file, deformTolerance sets how close they track), deform: "rest" to ship those tubes at their rest shape knowing they do not move, or export the clip as video (cadgen step snapshot --animation ${t.id} --video)`);a==="morph"?y.size&&A.push(`${Oe(y)} carries a braid: the strand pattern is a shader, not geometry, so the exported cord has the right shape and motion and a smooth surface`):A.push(`deform: "rest" ships ${Oe(x)} at rest shape: the clip's tube deformation is per-vertex motion this file does not carry`)}let b=[...m].filter(I=>f.has(I));if(b.length){for(let I of b)f.delete(I);A.push(`${Oe(b)} moves in this clip and is hidden at start: dropping .visible() omits the occurrence from the file, and a node that is not there carries no motion`)}let S=new Float32Array(e.frameCount);for(let I=0;I<e.frameCount;I+=1)S[I]=I/e.fps;let w=[],R=new Map;for(let[I,N]of f){let C=new Float32Array(N.translations),T=new Float32Array(N.rotations),P=new Float32Array(N.scales),D=Ap(P,N.count);R.set(I,{translation:[C[0],C[1],C[2]],rotation:[T[0],T[1],T[2],T[3]],scale:D?null:[P[0],P[1],P[2]]});let E={node:I};Lr(C,3,N.count)&&(E.translation=C),Lr(T,4,N.count)&&(E.rotation=T),!D&&Lr(P,3,N.count)&&(E.scale=P),(E.translation||E.rotation||E.scale)&&w.push(E)}return w.sort(pc),{name:t.id,times:S,channels:w,rest:R,statics:{opacity:p,hidden:m},deformations:v,grid:M,warnings:A}}d(dc,"sampleClipAnimation");function pc(n,t){return n.node!==t.node?n.node<t.node?-1:1:(n.weights?1:0)-(t.weights?1:0)}d(pc,"compareChannels");function mc(n,t){return t?.length?{...n,channels:[...n.channels,...t].sort(pc)}:n}d(mc,"withMorphChannels");function gc(n,t){let e=n.channels.map(s=>s.node).filter(s=>!t.has(s));if(!e.length)return n;let i=new Map;for(let[s,r]of n.rest)t.has(s)&&i.set(s,r);return{...n,channels:n.channels.filter(s=>t.has(s.node)),rest:i,warnings:[...n.warnings,`${Oe(e)} moves in this clip but has no geometry in the export, so the file carries no node to animate for it`]}}d(gc,"restrictAnimationToNodes");Hi();Fn();var qi={BufferGeometry:je,Float32BufferAttribute:de,Matrix3:Y,Vector3:k},Tp=1,Ur=512*1024*1024,_c=16,xc=5,Ep=128,Cp=512,$i=new xt;function yc(n,t=6){let e=[...n].sort();return e.length<=t?e.join(", "):`${e.slice(0,t).join(", ")} (and ${e.length-t} more)`}d(yc,"summarize");function vc(n){return n>=1024**3?`${(n/1024**3).toFixed(2)} GiB`:`${(n/1024**2).toFixed(1)} MiB`}d(vc,"formatBytes");function Rp(n,t){let e=Array.isArray(n.transform)?n.transform:null,i=e===null||gr(e),s=!i&&pr(e)<0,r=i?null:mr(e),o=t.positions,a=t.normals,c=Math.floor(o.length/3),l=new Float32Array(o.length),u=new Float32Array(o.length);for(let v=0;v<c;v+=1){let y=v*3;i?(l[y]=o[y],l[y+1]=o[y+1],l[y+2]=o[y+2]):dr(e,o[y],o[y+1],o[y+2],l,y);let M=a[y],A=a[y+1],b=a[y+2],S=M,w=A,R=b;r&&(S=r[0]*M+r[1]*A+r[2]*b,w=r[3]*M+r[4]*A+r[5]*b,R=r[6]*M+r[7]*A+r[8]*b);let I=Math.sqrt(S*S+w*w+R*R)||1;u[y]=S/I,u[y+1]=w/I,u[y+2]=R/I}let h=t.faceRanges||[],f=0;for(let v of h)f+=Math.floor((Number(v.indexCount)||0)/3);let p=new Uint32Array(f*3),m=new Uint32Array(f),g=s?[0,2,1]:[0,1,2],_=0;h.forEach((v,y)=>{let M=Number(v.indexStart)||0,A=Number(v.indexCount)||0;for(let b=M;b+2<M+A;b+=3)p[_*3]=t.indices[b+g[0]],p[_*3+1]=t.indices[b+g[1]],p[_*3+2]=t.indices[b+g[2]],m[_]=y,_+=1});let x=new je;return x.setAttribute("position",new Ut(l,3)),x.setAttribute("normal",new Ut(u,3)),x.setIndex(new Ut(p,1)),{geometry:x,triangleRange:m}}d(Rp,"occurrenceWorldGeometry");function Ip(n){let t=n.values,e=Math.floor(t.length/8),i=new Map;for(let a=0;a<e;a+=1){let c=a*8,l=t[c],u=i.get(l);if(!u){i.set(l,[t[c+1],t[c+1],t[c+2],t[c+2],t[c+3],t[c+3]]);continue}for(let h=0;h<3;h+=1){let f=t[c+1+h];f<u[h*2]&&(u[h*2]=f),f>u[h*2+1]&&(u[h*2+1]=f)}}let s=[...i.keys()].sort((a,c)=>a-c),r=new Uint32Array(s.length+1),o=[];return s.forEach((a,c)=>{let l=i.get(a),u=[0,1,2].map(h=>l[h*2]===l[h*2+1]?[l[h*2]]:[l[h*2],l[h*2+1]]);for(let h of u[0])for(let f of u[1])for(let p of u[2])o.push(h,f,p);r[c+1]=o.length/3}),{fractions:Float64Array.from(s),cornerOffset:r,uva:Float64Array.from(o)}}d(Ip,"boundsForFractions");function Sc(n,t,e){let i=t.path,s=(t.twistDeg||0)*Math.PI/180,r=rt(s),o=ht(s);for(let a=0;a<n.fractions.length;a+=1){let c=hn(i,n.fractions[a]*i.length),l=c.point,u=c.normal,h=c.binormal,f=c.tangent;for(let p=n.cornerOffset[a];p<n.cornerOffset[a+1];p+=1){let m=p*3,g=n.uva[m],_=n.uva[m+1],x=n.uva[m+2],v=r*g-o*_,y=o*g+r*_;e[m]=l[0]+u[0]*v+h[0]*y+f[0]*x,e[m+1]=l[1]+u[1]*v+h[1]*y+f[1]*x,e[m+2]=l[2]+u[2]*v+h[2]*y+f[2]*x}}return e}d(Sc,"poseCorners");function Pp(n,t,e,i){let s=0;for(let r=0;r<e.length;r+=3){let o=e[r]-(n[r]+(t[r]-n[r])*i),a=e[r+1]-(n[r+1]+(t[r+1]-n[r+1])*i),c=e[r+2]-(n[r+2]+(t[r+2]-n[r+2])*i),l=o*o+a*a+c*c;l>s&&(s=l)}return Math.sqrt(s)}d(Pp,"blendDeviation");function Np(n,t,e){let i=n.length,s=[0];if(i<2)return s;let r=0,o=Sc(t,jt(n[0]),new Float64Array(t.uva.length)),a=o,c=[],l=!0;for(let u=1;u<i;u+=1){let h=Fe(n[u],n[u-1])?a:Sc(t,jt(n[u]),new Float64Array(t.uva.length));a=h,c.push({index:u,pose:h}),l=l&&Fe(n[u],n[r]);let f=!1;if(!l){let g=u-r;for(let _ of c){if(_.index===u)continue;let x=(_.index-r)/g;if(Pp(o,h,_.pose,x)>e){f=!0;break}}}if(!f&&c.length<Ep)continue;let p=f?u-1:u,m=c.find(g=>g.index===p);s.push(p),r=p,o=m.pose,c=c.filter(g=>g.index>p),l=c.every(g=>Fe(n[g.index],n[r]))}return s[s.length-1]!==i-1&&s.push(i-1),s}d(Np,"fitTargetTimes");function Lp(n,t,e){let i=n.geometry.index,s=Math.floor(i.count/3),r=n.sourceTriangles,o=new Map;for(let a=0;a<s;a+=1){let c=r?r[a]:a,l=e[t[c]]||e[0],u=o.get(l);u||o.set(l,u=[]),u.push(a)}return[...o.entries()].map(([a,c])=>{let l=new Uint32Array(c.length*3),u=new Map,h=0;c.forEach((p,m)=>{for(let g=0;g<3;g+=1){let _=i.getX(p*3+g),x=u.get(_);x===void 0&&(x=h,h+=1,u.set(_,x)),l[m*3+g]=x}});let f=new Uint32Array(h);for(let[p,m]of u)f[m]=p;return{color:a,indices:l,vertexIds:f,slotOf:u}})}d(Lp,"partitionByColor");function Jn(n,t){let e=new Float32Array(t.length*3);for(let i=0;i<t.length;i+=1){let s=t[i]*3;e[i*3]=n[s],e[i*3+1]=n[s+1],e[i*3+2]=n[s+2]}return e}d(Jn,"gather");function Dp(n){let t=Math.max(1,Math.min(n,Cp)),e=new Uint32Array(t);for(let i=0;i<t;i+=1)e[i]=Math.floor(i*n/t);return e}d(Dp,"verifySampleIds");function Up(n,t){let e=0;for(let i=0;i<n.length;i+=3){let s=n[i],r=n[i+1],o=n[i+2],a=t[i],c=t[i+1],l=t[i+2],u=Math.sqrt(s*s+r*r+o*o)*Math.sqrt(a*a+c*c+l*l);if(u<1e-12)continue;let h=Math.min(1,Math.max(-1,(s*a+r*c+o*l)/u)),f=Uo(h)*180/Math.PI;f>e&&(e=f)}return e}d(Up,"maxNormalDegrees");function Mc(n,t,e,i={}){let{toleranceMm:s=Tp,grid:r,defaultColor:o=null,clipId:a="clip",maxRuntimeBytes:c=Ur}=i,l=Number(s);if(!(l>0))throw new Error(`morph deformTolerance must be a positive number of millimetres, got ${s}`);let u=[],h=new Map,f=[];if(!e?.size)return{overrides:h,channels:f,warnings:u,stats:null};let p=[],m=[];for(let v of n.occurrences||[]){let y=String(v.component||""),M=String(v.id||y),A=e.get(M);if(!A)continue;let b=t.get(y);if(!b||!b.positions?.length){m.push(M);continue}p.push({occurrence:v,occurrenceId:M,tessellation:b,entry:A})}if(m.length&&u.push(`${yc(m)} deforms in this clip but tessellated to nothing, so the file carries no geometry to morph for it`),!p.length)return{overrides:h,channels:f,warnings:u,stats:null};let g=[],_=0;for(let v of p){let y=v.entry.samples[0].deformation,{geometry:M,triangleRange:A}=Rp(v.occurrence,v.tessellation),b=Rr(qi,M,jt(y),$i),S={restSpec:y.restSpec,pathSpec:y.restSpec,twistDeg:0,maxSegmentLength:y.maxSegmentLength,braid:y.braid},w=new Array(r.count).fill(S);for(let C of v.entry.samples)w[C.index]=C.deformation;let R=Ip(b.mapping),I=Np(w,R,l),N=b.vertexCount;g.push({...v,bake:b,model:R,poses:w,keys:I,triangleRange:A,vertexCount:N}),_+=N*Math.max(0,I.length-1)*2*_c}if(_>Math.min(c,Ur)){let v=g.reduce((M,A)=>M+Math.max(0,A.keys.length-1),0),y=g.reduce((M,A)=>M+A.vertexCount,0);throw new Error(`clip ${a} needs ${v} morph targets over ${g.length} tubes (${y} refined vertices) to hold ${l}mm, which is ${vc(_)} of morph texture at playback \u2014 past the ${vc(Math.min(c,Ur))} ceiling, and it is the GPU number rather than the file size that decides whether the file opens. Raise deformTolerance (the target count falls as its square root), shorten seconds, coarsen --mesh-tolerance so the tubes carry fewer vertices, or coarsen the clip's own maxSegmentLength`)}let x={toleranceMm:l,nodes:0,targets:0,bytes:0,runtimeBytes:0,refinedTriangles:0,deviationMm:0,normalsOmitted:[]};for(let v of g){let{bake:y,poses:M,keys:A,vertexCount:b,occurrenceId:S}=v,w=new de(new Float32Array(b*3),3),R=new de(new Float32Array(b*3),3);Zn(qi,y,jt(M[A[0]]),$i,w,R);let I=Float32Array.from(w.array),N=Float32Array.from(R.array),C=Dp(b),T=[],P=[],D=[],E=0;for(let V=1;V<A.length;V+=1){Zn(qi,y,jt(M[A[V]]),$i,w,R);let W=new Float32Array(b*3),q=new Float32Array(b*3);for(let $=0;$<W.length;$+=1)W[$]=w.array[$]-I[$],q[$]=R.array[$]-N[$];T.push(W),P.push(q),D.push(Jn(w.array,C)),E=Math.max(E,Up(N,R.array))}let L=E>=xc;!L&&T.length&&x.normalsOmitted.push(S);let F=new Int32Array(A.length).fill(-1),O=[];for(let V=1;V<A.length;V+=1){let W=T[V-1],q=!1;for(let $=0;$<W.length;$+=1)if(W[$]!==0){q=!0;break}q&&(F[V]=O.length,O.push(V-1))}let U=Fp(v,{basePositions:I,deltaPositions:T,grid:r,tolerance:l,posed:w,posedNormals:R});x.deviationMm=Math.max(x.deviationMm,U);let B=Ca(n,v.occurrence,v.tessellation,o||void 0),z=fr(v.occurrence.material),X=Lp(y,v.triangleRange,B).map(V=>{let W=V.vertexIds,q=O.map(J=>({positionDeltas:Jn(T[J],W),...L?{normalDeltas:Jn(P[J],W)}:{}})),$=[],tt=[];return C.forEach((J,j)=>{let nt=V.slotOf.get(J);nt!==void 0&&($.push(nt),tt.push(j))}),{color:V.color,positions:Jn(I,W),normals:Jn(N,W),indices:V.indices,...z===null?{}:{material:z},...q.length?{targets:q}:{},...q.length&&$.length?{verify:{vertexIds:Uint32Array.from($),posed:O.map(J=>{let j=D[J],nt=new Float32Array(tt.length*3);return tt.forEach((St,Qt)=>{nt[Qt*3]=j[St*3],nt[Qt*3+1]=j[St*3+1],nt[Qt*3+2]=j[St*3+2]}),nt})}}:{}}});h.set(S,X),x.nodes+=1,x.targets+=O.length,x.refinedTriangles+=Math.floor(y.geometry.index.count/3);for(let V of X){let W=V.positions.length/3;x.bytes+=W*O.length*(L?24:12),x.runtimeBytes+=W*O.length*(L?2:1)*_c}if(O.length){let V=new Float32Array(A.length),W=new Float32Array(A.length*O.length);for(let q=0;q<A.length;q+=1)V[q]=A[q]/r.hz,F[q]>=0&&(W[q*O.length+F[q]]=1);f.push({node:S,times:V,weights:W,targetCount:O.length})}}return x.normalsOmitted.length&&u.push(`${yc(x.normalsOmitted)} turns by less than ${xc}\xB0 over this clip, so its morph targets carry positions only and its shading rides the base normals`),{overrides:h,channels:f,warnings:u,stats:x}}d(Mc,"buildTubeMorphTargets");function Fp(n,{basePositions:t,deltaPositions:e,grid:i,tolerance:s,posed:r,posedNormals:o}){let{bake:a,poses:c,keys:l,occurrenceId:u}=n;if(l.length<2)return 0;let h=0,f=0;for(let p=0;p<c.length;p+=i.multiple){for(;f+2<l.length&&l[f+1]<=p;)f+=1;let m=l[f],g=l[f+1],_=g===m?0:(p-m)/(g-m);Zn(qi,a,jt(c[p]),$i,r,o);let x=f>=1?e[f-1]:null,v=e[f];for(let y=0;y<t.length;y+=3){let M=0;for(let A=0;A<3;A+=1){let b=t[y+A]+(x?x[y+A]*(1-_):0)+(v?v[y+A]*_:0),S=r.array[y+A]-b;M+=S*S}M>h&&(h=M)}}if(h=Math.sqrt(h),h>s+.001)throw new Error(`morph fit for ${u} leaves ${h.toFixed(4)}mm between the baked targets and the clip's own deformation, past the ${s}mm it was fitted to`);return h}d(Fp,"verifyMorphFit");var Fr=Object.freeze(["clips"]);function Op(n){if(typeof Buffer<"u")return Buffer.from(n,"utf8").toString("base64");let t=new TextEncoder().encode(n),e="";for(let i of t)e+=String.fromCharCode(i);return btoa(e)}d(Op,"base64Utf8");async function Bp(n,{name:t="embedded animation"}={}){let e=String(n||""),i=`data:text/javascript;base64,${Op(e)}`;try{return await import(i)}catch(s){let r=s instanceof Error?s.message:String(s);throw new Error(`${t}: ${r}`)}}d(Bp,"importAnimationModule");function zp(n,{name:t="embedded animation"}={}){let i=Object.keys(n||{}).filter(s=>s!=="default").filter(s=>!Fr.includes(s));if(i.length)throw new Error(`${t}: unknown export${i.length===1?"":"s"} ${i.join(", ")} \u2014 the renderer understands: ${Fr.join(", ")}`);if("default"in(n||{}))throw new Error(`${t}: a default export is not an animation-module export \u2014 use named exports (${Fr.join(", ")})`);return{clips:ec(n?.clips)}}d(zp,"compileAnimationModule");async function bc(n,t={}){let[e]=await Promise.all([Bp(n,t),ja()]);return zp(e,t)}d(bc,"compileAnimationSource");function kp(n){let t={},e=[],i=[],s=[],r=[],o={chord:void 0,angle:void 0};for(let a=0;a<n.length;a+=1){let c=n[a];if(!c.startsWith("--"))continue;let l=n[a+1],u=l===void 0||l.startsWith("--")?"true":l;u!=="true"&&(a+=1),c==="--format"?(e.push(u),s.push({chord:void 0,angle:void 0}),r.push(void 0)):c==="--out"?i.push(u):c==="--chord-tolerance"?(s.length?s[s.length-1]:o).chord=u:c==="--angle-tolerance"?(s.length?s[s.length-1]:o).angle=u:c==="--animation"?(r.length||It("--animation must follow the --format/--out pair it animates"),r[r.length-1]=u):t[c.slice(2)]=u}return{args:t,formats:e,outs:i,pairTolerances:s,pairAnimations:r,defaults:o}}d(kp,"parseArgs");function It(n){process.stdout.write(`${JSON.stringify({ok:!1,error:String(n)})}
`),process.exit(1)}d(It,"fail");function Vp(n,t,e,i){let s=String(e?.surfaceInput||""),r=String(e?.surfaceObject||""),o=Ie(s,i),a=oa(ir(o),{surfaceInput:s,surfaceObject:r,tessellationInput:o,tessellation:i});if(a)return{...a.component,partColor:a.partColor};let c=String(e?.surf||"");if(!c)throw new Error(`component ${t} has no surf payload`);let l=pn.readFileSync(mn.join(n,c)),{index:u,floats:h}=Vr(l.buffer.slice(l.byteOffset,l.byteOffset+l.byteLength)),f=Xo(u,h,i),p=Array.isArray(u.partColor)?u.partColor:null;return da(o,ia(f,{surfaceInput:s,surfaceObject:r,tessellation:i,partColor:p,edgeClasses:na(u)})),{...f,partColor:p}}d(Vp,"tessellationForComponent");var{args:Kn,formats:Or,outs:Ec,pairTolerances:wc,pairAnimations:Ac,defaults:Tc}=kp(process.argv.slice(2)),Yi=String(Kn["package-dir"]||"");(!Yi||!mn.isAbsolute(Yi))&&It("--package-dir must be an absolute render-package directory");(!Or.length||Or.length!==Ec.length)&&It("--format and --out must be given as one or more ordered pairs");var Be=Or.map((n,t)=>{let e=wc[t].chord??Tc.chord,i=wc[t].angle??Tc.angle,s={...Ct};e!==void 0&&(s.chordTolerance=Number(e)),i!==void 0&&(s.angleTolerance=Number(i));let r=null;if(Ac[t]!==void 0){try{r=JSON.parse(String(Ac[t]))}catch(o){It(`--animation must be a JSON object: ${o?.message||o}`)}(!r||typeof r!="object"||Array.isArray(r))&&It("--animation must be a JSON object")}return{format:String(n).toLowerCase(),out:String(Ec[t]),options:s,animation:r,groupKey:`${s.chordTolerance}:${s.angleTolerance}`}});for(let n of Be)(!n.out||!mn.isAbsolute(n.out))&&It("--out must be an absolute output path"),hr.includes(n.format)||It(`--format must be one of ${hr.join(", ")}`),(!(n.options.chordTolerance>0)||!(n.options.angleTolerance>0))&&It("tolerances must be positive numbers"),n.animation&&n.format!=="glb"&&It(`${n.format} carries no animation: only glb does`),n.animation&&!String(n.animation.clip||"").trim()&&It("--animation must name a clip");new Set(Be.map(n=>n.out)).size!==Be.length&&It("--out paths must be distinct");var Gp=String(Kn.name||mn.basename(Be[0].out).replace(/\.[^.]+$/,"")||"model"),Zi=Kn["default-color"]?String(Kn["default-color"]):null;Zi!==null&&!/^#[0-9a-fA-F]{6}$/.test(Zi)&&It("--default-color must be #rrggbb");var Cc=String(Kn["animation-source"]||"");Be.some(n=>n.animation)&&!Cc&&It("--animation needs --animation-source: the clips live in the document sidecar");async function Hp(n){let t=pn.readFileSync(n,"utf8");return(await bc(t,{name:"embedded animation"})).clips}d(Hp,"loadClips");function Wp(n,t,e){let i=String(n.animation.clip),s=ic(t,i);if(!s){let a=nc(t).map(c=>c.id);throw new Error(a.length?`Unknown animation clip: ${i}. This model declares: ${a.join(", ")}`:`Unknown animation clip: ${i}. This model declares no animation clips`)}let r=ac(n.animation,s,{label:"animation"}),o=dc(e,s,r,{drop:Array.isArray(n.animation.drop)?n.animation.drop:[],deform:n.animation.deform});return{clip:s,plan:r,sampled:o}}d(Wp,"sampleJobAnimation");try{let n=JSON.parse(pn.readFileSync(mn.join(Yi,"assembly.json"),"utf8")),t=n.components||{},e=new Set((n.occurrences||[]).map(o=>String(o.component||""))),i=Be.some(o=>o.animation)?await Hp(Cc):null,s=new Map;Be.forEach((o,a)=>{s.has(o.groupKey)||s.set(o.groupKey,{options:o.options,members:[]}),s.get(o.groupKey).members.push({job:o,index:a})});let r=[];for(let o of s.values()){let a=new Map;for(let u of e){if(!t[u])throw new Error(`descriptor names unknown component ${u}`);a.set(u,Vp(Yi,u,t[u],o.options))}let c=Zi?{defaultColor:Zi.toLowerCase()}:{},l=null;for(let{job:u,index:h}of o.members){let f,p=null,m=null;if(u.animation){let{plan:x,sampled:v}=Wp(u,i,n),y=Mc(n,a,v.deformations,{toleranceMm:u.animation.deformTolerance,grid:v.grid,clipId:v.name,...c.defaultColor?{defaultColor:c.defaultColor}:{}});f=_r(n,a,{...c,perOccurrence:!0,hiddenOccurrenceIds:v.statics.hidden,occurrenceOpacity:v.statics.opacity,occurrenceOverrides:y.overrides}),p=gc(mc(v,y.channels),new Set(f.primitives.map(M=>M.node).filter(Boolean))),m={clip:p.name,fps:x.fps,samples:x.frameCount,seconds:x.seconds,start:x.start,channels:p.channels.length,...y.stats?{deform:{mode:"morph",nodes:y.stats.nodes,targets:y.stats.targets,bytes:y.stats.bytes,runtimeBytes:y.stats.runtimeBytes,refinedTriangles:y.stats.refinedTriangles,deviationMm:Number(y.stats.deviationMm.toFixed(4)),toleranceMm:y.stats.toleranceMm,fitGridHz:v.grid.hz}}:{},warnings:[...x.warnings,...p.warnings,...y.warnings]}}else l=l||_r(n,a,c),f=l;if(!f.triangleCount)throw new Error("tree produced no triangles");let{body:g}=Ra(f,u.format,{name:Gp,animation:p});pn.mkdirSync(mn.dirname(u.out),{recursive:!0});let _=`${u.out}.${process.pid}.tmp`;pn.writeFileSync(_,g),pn.renameSync(_,u.out),r[h]={path:u.out,format:u.format,triangleCount:f.triangleCount,...m?{animation:m}:{}}}}process.stdout.write(`${JSON.stringify({ok:!0,files:r})}
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
