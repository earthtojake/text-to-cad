import{J as e,Q as t,X as n,Y as r,at as i,ct as a,et as o,ft as s,it as c,lt as l,mt as u,nt as d,ot as f,pt as p,rt as m,st as h,tt as g}from"./sharedGeometry-DYv4uiUO.js";var _=`
uniform mat4 uProjectionInverse;
uniform mat4 uCameraWorld;
varying vec3 vRay;
varying vec2 vScreen;
void main() {
  vScreen = position.xy;
  // The view ray through this corner, in the world: affine across the screen, so the
  // corners' rays interpolate exactly.
  vec4 nearPoint = uProjectionInverse * vec4(position.xy, -1.0, 1.0);
  vec4 farPoint = uProjectionInverse * vec4(position.xy, 1.0, 1.0);
  vRay = mat3(uCameraWorld) * (farPoint.xyz / farPoint.w - nearPoint.xyz / nearPoint.w);
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`,v=`
uniform vec3 uColor;
uniform float uAlpha;
uniform vec3 uShape;
uniform float uAspect;
uniform float uPremultiply;
uniform float uLinear;
varying vec3 vRay;
varying vec2 vScreen;

float ditherNoise(vec2 uv) {
  highp float dt = mod(dot(uv, vec2(12.9898, 78.233)), 3.141592653589793);
  return fract(sin(dt) * 43758.5453);
}

vec3 srgbToLinear(vec3 c) {
  return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(vec3(0.04045), c));
}

void main() {
  // 0 in the middle of the frame (a little above it, where a product's mass sits), 1 at a corner.
  vec2 at = vec2(vScreen.x * uAspect, vScreen.y - 0.12);
  float reach = clamp(length(at) / length(vec2(uAspect, 1.12)), 0.0, 1.0);
  float glow = 1.0 - smoothstep(0.0, 0.75, reach);
  float corner = smoothstep(0.3, 1.0, reach);
  float wall = smoothstep(0.0, 0.55, vRay.z * inversesqrt(dot(vRay, vRay)));
  vec3 color = mix(uColor, vec3(1.0), uShape.x * glow * glow);
  color *= 1.0 - uShape.y * clamp(corner + uShape.z * wall, 0.0, 1.0);
  // A dark sweep spans few of the canvas's 8-bit levels: a level of noise turns the
  // rounding's contour rings into grain too fine to see.
#ifdef STUDIO_DITHER_SCALE
  color += (ditherNoise(gl_FragCoord.xy) - 0.5) * STUDIO_DITHER_SCALE / 255.0;
#else
  color += (ditherNoise(gl_FragCoord.xy) - 0.5) / 255.0;
#endif
  color = clamp(color, 0.0, 1.0);
  // Into the canvas (or a target three draws as it) in display colour, as a clear writes;
  // into any other target in linear light.
  if (uLinear > 0.5) color = srgbToLinear(color);
  gl_FragColor = vec4(color * mix(1.0, uAlpha, uPremultiply), uAlpha);
}
`;function y(e,t){let n={uColor:{value:new e.Vector3(1,1,1)},uAlpha:{value:1},uShape:{value:new e.Vector3(0,0,0)},uAspect:{value:1},uPremultiply:{value:1},uLinear:{value:0},uProjectionInverse:{value:new e.Matrix4},uCameraWorld:{value:new e.Matrix4}},r=new e.ShaderMaterial({uniforms:n,vertexShader:_,fragmentShader:v,depthTest:!1,depthWrite:!1,blending:e.NoBlending,toneMapped:!1}),i=new e.Mesh(new e.PlaneGeometry(2,2),r);i.name=`studio-backdrop`,i.frustumCulled=!1,i.castShadow=!1,i.receiveShadow=!1,i.renderOrder=-1e9,i.raycast=()=>{};let a={alpha:1},o={r:1,g:1,b:1};return i.onBeforeRender=(e,t,i)=>{let o=t.background?a.alpha:Math.min(a.alpha,e.getClearAlpha()),s=e.getRenderTarget();n.uAlpha.value=o,n.uPremultiply.value=e.getContextAttributes?.()?.premultipliedAlpha===!1?0:1,n.uLinear.value=s&&s.isXRRenderTarget!==!0?1:0,n.uProjectionInverse.value.copy(i.projectionMatrixInverse),n.uCameraWorld.value.copy(i.matrixWorld);let c=i.projectionMatrix.elements;n.uAspect.value=Math.abs(c[0])>1e-12?Math.abs(c[5]/c[0]):1,r.uniformsNeedUpdate=!0},{object:i,uniforms:n,update({color:r,opacity:s}){new e.Color(r).getRGB(o,e.SRGBColorSpace),n.uColor.value.set(o.r,o.g,o.b),a.alpha=s,i.visible=s>0;let c=.2126*o.r+.7152*o.g+.0722*o.b;n.uShape.value.set(t.lift,t.shade.dark+(t.shade.light-t.shade.dark)*c,t.wall)},dispose(){i.removeFromParent(),i.geometry.dispose(),r.dispose()}}}var b=`
uniform sampler2D uContactDepth;
uniform mat4 uContactMatrix;
uniform float uFloorDepth;
uniform sampler2DShadow uKeyMap;
uniform mat4 uKeyMatrix;
uniform float uKeyBias;
uniform float uKeyNormalBias;
uniform float uKeyEnabled;
uniform vec4 uRect;
varying vec2 vUv;

void main() {
  vec3 world = vec3(uRect.xy + (vUv * 2.0 - 1.0) * uRect.z, uRect.w);
  // How close the lowest surface above this floor point is: 1 at the floor, 0 at
  // the top of the contact range or where nothing is above it.
  vec4 contact = uContactMatrix * vec4(world, 1.0);
  float depth = texture2D(uContactDepth, contact.xy).r;
  float near = 1.0 - clamp((depth - uFloorDepth) / max(1.0 - uFloorDepth, 1e-6), 0.0, 1.0);
  // Whether the key light reaches this floor point.
  float blocked = 0.0;
  if (uKeyEnabled > 0.5) {
    vec4 key = uKeyMatrix * vec4(world + vec3(0.0, 0.0, uKeyNormalBias), 1.0);
    key.xyz /= key.w;
    key.z += uKeyBias;
    if (key.x >= 0.0 && key.x <= 1.0 && key.y >= 0.0 && key.y <= 1.0 && key.z <= 1.0) {
      blocked = 1.0 - texture(uKeyMap, key.xyz);
    }
  }
  // R: contact (tight), G: occlusion (broad), B and A: the key's shadow, blurred
  // narrow (B, near the model) and wide (A, away from it).
  gl_FragColor = vec4(near * near * near, near, blocked, blocked);
}
`,x=`
uniform sampler2D uInput;
uniform vec2 uAxis;
uniform vec3 uSigma;
varying vec2 vUv;

void main() {
  vec2 narrow = vec2(0.0);
  float narrowWeight = 0.0;
  for (int i = -6; i <= 6; i++) {
    float t = float(i) / 3.0;
    float w = exp(-0.5 * t * t);
    narrow += w * texture2D(uInput, vUv + uAxis * t * uSigma.x).rb;
    narrowWeight += w;
  }
  float medium = 0.0;
  float mediumWeight = 0.0;
  for (int i = -12; i <= 12; i++) {
    float t = float(i) / 6.0;
    float w = exp(-0.5 * t * t);
    medium += w * texture2D(uInput, vUv + uAxis * t * uSigma.y).a;
    mediumWeight += w;
  }
  float wide = 0.0;
  float wideWeight = 0.0;
  for (int i = -24; i <= 24; i++) {
    float t = float(i) / 12.0;
    float w = exp(-0.5 * t * t);
    wide += w * texture2D(uInput, vUv + uAxis * t * uSigma.z).g;
    wideWeight += w;
  }
  narrow /= narrowWeight;
  gl_FragColor = vec4(narrow.x, wide / wideWeight, narrow.y, medium / mediumWeight);
}
`,S=`
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`,C=`
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`,w=`
uniform sampler2D uShadow;
uniform float uOpacity;
uniform float uReady;
uniform vec4 uStrength;
varying vec2 vUv;

// Up to one 8-bit level of noise per pixel (three's rand hash). Spread STUDIO_DITHER_SCALE
// times wider about the same mean where each kept pixel averages that scale squared of these.
float ditherNoise(vec2 uv) {
  highp float dt = mod(dot(uv, vec2(12.9898, 78.233)), 3.141592653589793);
#ifdef STUDIO_DITHER_SCALE
  return max((fract(sin(dt) * 43758.5453) - 0.5) * STUDIO_DITHER_SCALE + 0.5, 0.0) / 255.0;
#else
  return fract(sin(dt) * 43758.5453) / 255.0;
#endif
}

void main() {
  vec4 s = texture2D(uShadow, vUv);
  // Occlusion: a tight dark line at contact under a broad, light falloff.
  float occlusion = 1.0 - (1.0 - uStrength.x * s.r) * (1.0 - uStrength.y * s.g);
  // The key's shadow is crisp and full close to the model, soft and light away from it.
  float proximity = smoothstep(0.0, 0.5, s.g);
  float key = mix(s.a, s.b, proximity) * mix(uStrength.w, uStrength.z, proximity);
  float darkness = 1.0 - (1.0 - occlusion) * (1.0 - key);
  // Fade out inside the baked square, so its edge never shows.
  vec2 edge = min(vUv, 1.0 - vUv);
  darkness *= smoothstep(0.0, 0.08, min(edge.x, edge.y));
  float alpha = darkness * uOpacity * uReady;
  // Darkening the floor rounds it to 8 bits again, and a shallow shadow on a dark
  // floor bands. The colour, divided by alpha, is what the blend adds over the floor
  // whatever its colour: exactly this noise, which dithers that rounding (and lifts
  // the shadow by half a level on average).
  gl_FragColor = vec4(vec3(min(ditherNoise(gl_FragCoord.xy + 7.31) / max(alpha, 1e-4), 1.0)), alpha);
}
`;function T(e,t,n){let r=new e.Mesh(new e.PlaneGeometry(2,2),new e.ShaderMaterial({uniforms:n,vertexShader:S,fragmentShader:t,depthTest:!1,depthWrite:!1,blending:e.NoBlending,toneMapped:!1}));r.frustumCulled=!1;let i=new e.Scene;return i.add(r),{mesh:r,scene:i,uniforms:r.material.uniforms}}function E(e,t){let n=new e.WebGLRenderTarget(t,t,{type:e.HalfFloatType,minFilter:e.LinearFilter,magFilter:e.LinearFilter,depthBuffer:!1,generateMipmaps:!1});return n.texture.name=`studio-contact-shadow`,n}function D(e,t){let n=Array.isArray(e.material)?e.material:[e.material];for(let e of n)e&&t(e)}var O=()=>typeof performance<`u`&&typeof performance.now==`function`?performance.now():Date.now();function k(e,t){let n=Number(t)>1&&Number.isFinite(Number(t))?Number(t).toFixed(4):null;if((e.defines?.STUDIO_DITHER_SCALE??null)===n)return;let r={...e.defines};delete r.STUDIO_DITHER_SCALE,n&&(r.STUDIO_DITHER_SCALE=n),e.defines=r,e.needsUpdate=!0}function A({interval:e=0,requestFrame:t=null,now:n=O,setTimer:r=(e,t)=>setTimeout(e,t),clearTimer:i=e=>clearTimeout(e)}={}){let a=Math.max(0,Number(e)||0),o=-1/0,s=null;return{due(){let e=o+a-n();return e<1||(s===null&&typeof t==`function`&&(s=r(()=>{s=null,t()},e)),!1)},rendered(){o=n(),s!==null&&i(s),s=null},reset(){o=-1/0},dispose(){s!==null&&i(s),s=null}}}function j(e,t,{size:n=512,strength:r={contact:.75,occlusion:.5,key:.75,keyFar:.35},blur:i={narrow:.012,medium:.03,wide:.06},heightInterval:a=0,requestFrame:o=null,now:s,setTimer:c,clearTimer:l}={}){let u=new e.Group;u.name=`studio-contact-shadow`;let d=new e.DirectionalLight(16777215,0);d.name=`studio-contact-shadow-probe`,d.castShadow=!0,d.shadow.bias=0,d.shadow.normalBias=0,d.shadow.mapSize.set(n,n),d.target=new e.Object3D;let f=new e.WebGLRenderTarget(n,n,{depthBuffer:!0,generateMipmaps:!1});f.depthTexture=new e.DepthTexture(n,n,e.UnsignedIntType),f.depthTexture.minFilter=e.NearestFilter,f.depthTexture.magFilter=e.NearestFilter,d.shadow.map=f;let p=[E(e,n),E(e,n)],m=new e.OrthographicCamera(-1,1,1,-1,0,1),h=T(e,b,{uContactDepth:{value:f.depthTexture},uContactMatrix:{value:new e.Matrix4},uFloorDepth:{value:0},uKeyMap:{value:null},uKeyMatrix:{value:new e.Matrix4},uKeyBias:{value:0},uKeyNormalBias:{value:0},uKeyEnabled:{value:0},uRect:{value:new e.Vector4(0,0,1,0)}}),g=T(e,x,{uInput:{value:null},uAxis:{value:new e.Vector2},uSigma:{value:new e.Vector3(i.narrow*n,i.medium*n,i.wide*n)}}),_=new e.Mesh(new e.PlaneGeometry(1,1),new e.ShaderMaterial({uniforms:{uShadow:{value:p[0].texture},uOpacity:{value:1},uReady:{value:0},uStrength:{value:new e.Vector4(r.contact,r.occlusion,r.key,r.keyFar)}},vertexShader:C,fragmentShader:w,transparent:!0,depthWrite:!1,side:e.DoubleSide,forceSinglePass:!0,polygonOffset:!0,polygonOffsetFactor:1,polygonOffsetUnits:1}));_.name=`studio-contact-shadow-layer`,_.renderOrder=-2,u.add(_);let v=new e.BufferGeometry;v.setAttribute(`position`,new e.BufferAttribute(new Float32Array(9),3));let y=new e.Mesh(v,new e.MeshBasicMaterial({colorWrite:!1,depthWrite:!1}));y.name=`studio-contact-shadow-sentinel`,y.castShadow=!0,y.frustumCulled=!1,u.add(y);let S=A({interval:a,requestFrame:o,now:s,setTimer:c,clearTimer:l}),O={heightsStale:!0,compositeStale:!0,heightsReady:!1,heightsFloorDepth:0,enabled:!0,opacity:1,rect:null,floorDepth:0,placement:``,holdHeights:!1},j=()=>{O.heightsStale=!0,O.compositeStale=!0};y.onBeforeShadow=(e,t,n,r)=>{r!==d.shadow.camera&&(O.holdHeights?O.compositeStale=!0:j())};function M(t,n,r){let i=[];n.traverse(t=>{t.castShadow&&t.material&&D(t,t=>{t.side!==e.DoubleSide&&t.shadowSide!==e.DoubleSide&&(i.push([t,t.shadowSide]),t.shadowSide=e.DoubleSide)})});let{needsUpdate:a}=t;t.needsUpdate=!0;try{t.render([d],n,r)}finally{for(let[e,t]of i)e.shadowSide=t;t.needsUpdate=a}O.heightsFloorDepth=O.floorDepth,O.heightsReady=!0}function N(e,r){let i=h.uniforms;i.uContactMatrix.value.copy(d.shadow.matrix),i.uFloorDepth.value=O.heightsFloorDepth;let a=t.shadow?.map?.depthTexture||null;i.uKeyEnabled.value=t.visible&&t.castShadow&&a?1:0,i.uKeyMap.value=a,i.uKeyMatrix.value.copy(t.shadow.matrix),i.uKeyBias.value=t.shadow.bias,i.uKeyNormalBias.value=t.shadow.normalBias,i.uRect.value.set(...O.rect);let o=e.getRenderTarget(),s=e.autoClear,c=r.autoUpdate;e.autoClear=!1,r.autoUpdate=!1;try{e.setRenderTarget(p[0]),e.render(h.scene,m);for(let[t,r,i]of[[0,1,[1/n,0]],[1,0,[0,1/n]]])g.uniforms.uInput.value=p[t].texture,g.uniforms.uAxis.value.set(...i),e.setRenderTarget(p[r]),e.render(g.scene,m)}finally{e.setRenderTarget(o),e.autoClear=s,r.autoUpdate=c}O.compositeStale=!1,_.material.uniforms.uReady.value=1}_.onBeforeRender=(e,t,n)=>{if(!O.heightsStale&&!O.compositeStale)return;let r=e.shadowMap;O.rect&&r?.enabled&&(O.heightsStale&&S.due()&&(M(r,t,n),S.rendered(),O.heightsStale=!1,O.compositeStale=!0),O.compositeStale&&O.heightsReady&&N(e,r))};function P(){let e=O.enabled&&O.opacity>0;e&&!_.visible&&(j(),S.reset()),_.visible=e}return{object:u,layer:_,sentinel:y,probe:d,place({center:e,half:t,floorZ:n,height:r}){let i=[e[0],e[1],t,n,r].join(`,`);if(i===O.placement)return;O.placement=i;let a=t*1.12,o=Math.max(r,1e-6),s=o*.004;O.rect=[e[0],e[1],a,n],d.position.set(e[0],e[1],n-s),d.target.position.set(e[0],e[1],n+o),d.updateMatrixWorld(!0),d.target.updateMatrixWorld(!0);let c=d.shadow.camera;c.left=-a,c.right=a,c.top=a,c.bottom=-a,c.near=0,c.far=s+o,c.updateProjectionMatrix(),O.floorDepth=s/(s+o),_.position.set(e[0],e[1],n),_.scale.set(2*a,2*a,1),_.updateMatrixWorld(!0),j()},setOpacity(e){_.material.uniforms.uOpacity.value=e,O.opacity=e,P()},setEnabled(e){O.enabled=e,P()},holdHeights(e){O.holdHeights=e===!0},setDitherScale(e){k(_.material,e)},get stale(){return O.heightsStale||O.compositeStale},dispose(){S.dispose(),u.removeFromParent(),f.depthTexture?.dispose(),f.dispose();for(let e of p)e.dispose();for(let e of[h.mesh,g.mesh,_,y])e.geometry.dispose(),e.material.dispose()}}}var M=`
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`,N=`
uniform sampler2D uDepth;
uniform mat4 uInverse;
uniform float uFloorZ;
float reflectedHeight(vec2 uv) {
  float depth = texture2D(uDepth, uv).r;
  if (depth >= 0.99999) return 1e20;
  vec4 point = uInverse * vec4(uv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
  return max(point.z / point.w - uFloorZ, 0.0);
}
`,P=`
uniform sampler2D uColor;
uniform float uFadeHeight;
varying vec2 vUv;
${N}
void main() {
  vec4 color = texture2D(uColor, vUv);
  float weight = color.a * (1.0 - smoothstep(0.0, uFadeHeight, reflectedHeight(vUv)));
  gl_FragColor = vec4(color.rgb * weight, weight);
}
`,F=`
uniform sampler2D uInput;
uniform vec2 uStep;
vec4 gaussian(vec2 uv) {
  vec4 sum = vec4(0.0);
  float total = 0.0;
  for (int i = -8; i <= 8; i++) {
    float t = float(i) / 4.0;
    float w = exp(-0.5 * t * t);
    sum += w * texture2D(uInput, uv + uStep * float(i));
    total += w;
  }
  return sum / total;
}
`,ee=`
varying vec2 vUv;
${F}
void main() {
  gl_FragColor = gaussian(vUv);
}
`,te=`
uniform sampler2D uSharp;
uniform float uBlurHeight;
varying vec2 vUv;
${N}
${F}
void main() {
  gl_FragColor = mix(texture2D(uSharp, vUv), gaussian(vUv),
    smoothstep(0.0, uBlurHeight, reflectedHeight(vUv)));
}
`,ne=`
varying vec3 vStudioFloorWorld;
`,re=`
vStudioFloorWorld = (modelMatrix * vec4(transformed, 1.0)).xyz;
`,ie=`
uniform sampler2D uReflection;
uniform mat4 uReflectionMatrix;
uniform vec3 uReflectionShape;
uniform float uReflectionReady;
varying vec3 vStudioFloorWorld;
`,ae=`
if (uReflectionReady > 0.5) {
  vec4 clip = uReflectionMatrix * vec4(vStudioFloorWorld, 1.0);
  vec2 ruv = clip.xy / clip.w * 0.5 + 0.5;
  if (clip.w > 0.0 && all(greaterThanEqual(ruv, vec2(0.0))) && all(lessThanEqual(ruv, vec2(1.0)))) {
    vec4 reflected = texture2D(uReflection, ruv);
    vec3 toEye = normalize(cameraPosition - vStudioFloorWorld);
    float grazing = 1.0 - abs(toEye.z);
    float weight = clamp(reflected.a * uReflectionShape.x
      * mix(uReflectionShape.y, 1.0, grazing * grazing * grazing), 0.0, 1.0);
    vec3 color = reflected.rgb / max(reflected.a, 1e-4);
    // Over the floor and whatever shows through it: the reflection covers both.
    float alpha = gl_FragColor.a + weight * (1.0 - gl_FragColor.a);
    gl_FragColor.rgb = (gl_FragColor.a * (1.0 - weight) * gl_FragColor.rgb + weight * color) / max(alpha, 1e-4);
    gl_FragColor.a = alpha;
  }
}
`;function I(e,t,n){let r=new e.Mesh(new e.PlaneGeometry(2,2),new e.ShaderMaterial({uniforms:n,vertexShader:M,fragmentShader:t,depthTest:!1,depthWrite:!1,blending:e.NoBlending,toneMapped:!1}));r.frustumCulled=!1;let i=new e.Scene;return i.add(r),{mesh:r,scene:i,uniforms:r.material.uniforms}}function L(e,t,n=null){let r=new e.WebGLRenderTarget(1,1,{type:e.HalfFloatType,minFilter:e.LinearFilter,magFilter:e.LinearFilter,depthBuffer:!!n,depthTexture:n,generateMipmaps:!1});return r.texture.name=t,r}function R(e,{resolution:t=.5,blur:n=2,sharpBlur:r=0,strength:i=.75,normalWeight:a=.45,blurHeight:o=.8,fadeHeight:s=1,interval:c=400,requestFrame:l=null,now:u,setTimer:d,clearTimer:f}={}){let p=new e.DepthTexture(1,1,e.UnsignedIntType),m=L(e,`studio-floor-reflection`,p),h=L(e,`studio-floor-reflection-sharp`),g=L(e,`studio-floor-reflection-combined`),_=new e.OrthographicCamera(-1,1,1,-1,0,1),v=()=>({uDepth:{value:p},uInverse:{value:y},uFloorZ:{value:0}}),y=new e.Matrix4,b=I(e,P,{...v(),uColor:{value:m.texture},uFadeHeight:{value:1}}),x=I(e,ee,{uInput:{value:null},uStep:{value:new e.Vector2}}),S=I(e,te,{...v(),uSharp:{value:h.texture},uInput:{value:null},uStep:{value:new e.Vector2},uBlurHeight:{value:1}}),C={uReflection:{value:g.texture},uReflectionMatrix:{value:new e.Matrix4},uReflectionShape:{value:new e.Vector3(i,a,0)},uReflectionReady:{value:0}},w={sceneChanged:!0,lastView:[],floorZ:0,height:1,width:0,heightPx:0,ready:!1},T=A({interval:c,requestFrame:l,now:u,setTimer:d,clearTimer:f}),E=new Map,D=new e.Plane,O=new e.Vector3(0,0,1),k=new e.Vector3,j=new e.Vector3,M=new e.Vector3,N=new e.Vector3,F=new e.Vector3,R=new e.Matrix4,z=new e.Vector4,B=new e.Vector4,V=new e.Matrix4,H=new e.Vector2,U=new e.Color;function W(e){let t=e.isOrthographicCamera?`orthographic`:`perspective`,n=E.get(t);return n||(n=e.clone(),E.set(t,n)),n}function G(e){return[...e.matrixWorld.elements,...e.projectionMatrix.elements,w.width,w.heightPx,w.floorZ]}function K(e){let t=w.lastView;if(t.length!==e.length)return!1;for(let n=0;n<e.length;n+=1)if(t[n]!==e[n])return!1;return!0}function q(e){e.getDrawingBufferSize(H);let n=Math.max(1,Math.round(H.x*t)),r=Math.max(1,Math.round(H.y*t));if(n!==w.width||r!==w.heightPx){w.width=n,w.heightPx=r;for(let e of[m,h,g])e.setSize(n,r)}}function J(e){let t=W(e);t.copy(e,!1),k.set(0,0,w.floorZ),j.setFromMatrixPosition(e.matrixWorld),R.extractRotation(e.matrixWorld),N.set(0,0,-1).applyMatrix4(R).add(j),M.subVectors(k,j).reflect(O).negate().add(k),F.subVectors(k,N).reflect(O).negate().add(k),t.position.copy(M),t.up.set(0,1,0).applyMatrix4(R).reflect(O),t.lookAt(F),t.updateMatrixWorld(!0),t.projectionMatrix.copy(e.projectionMatrix),t.layers.mask=e.layers.mask,D.setFromNormalAndCoplanarPoint(O,k).applyMatrix4(t.matrixWorldInverse),z.set(D.normal.x,D.normal.y,D.normal.z,D.constant);let n=t.projectionMatrix.elements;return t.isOrthographicCamera?B.set((Math.sign(z.x)+n[8])/n[0],(Math.sign(z.y)+n[9])/n[5],-t.far,1):B.set((Math.sign(z.x)+n[8])/n[0],(Math.sign(z.y)+n[9])/n[5],-1,(1+n[10])/n[14]),z.multiplyScalar(2/z.dot(B)),n[2]=z.x,n[6]=z.y,t.isOrthographicCamera?(n[10]=z.z,n[14]=z.w-1):(n[10]=z.z+1,n[14]=z.w),t.projectionMatrixInverse.copy(t.projectionMatrix).invert(),t}function Y(e,t,n){e.setRenderTarget(n),e.render(t.scene,_)}function X(e,t,n,r){e.uniforms.uInput.value=t.texture,e.uniforms.uStep.value.set(r?0:n/4/w.width,r?n/4/w.heightPx:0)}function Z(e,t,n,r,i){X(x,t,i,!1),Y(e,x,n),X(x,n,i,!0),Y(e,x,r)}function Q(e,t,i,a){let c=J(i);V.multiplyMatrices(c.projectionMatrix,c.matrixWorldInverse),C.uReflectionMatrix.value.copy(V),y.copy(V).invert();for(let e of[b,S])e.uniforms.uFloorZ.value=w.floorZ;b.uniforms.uFadeHeight.value=Math.max(w.height*s,1e-6),S.uniforms.uBlurHeight.value=Math.max(w.height*o,1e-6);let l=e.shadowMap,u={target:e.getRenderTarget(),autoClear:e.autoClear,clearAlpha:e.getClearAlpha(),background:t.background,matrixAuto:t.matrixWorldAutoUpdate,visible:a.map(e=>e.visible)};e.getClearColor(U);for(let e of a)e.visible=!1;t.background=null,t.matrixWorldAutoUpdate=!1;try{e.setRenderTarget(m),e.setClearColor(0,0),e.autoClear=!1,e.state.buffers.depth.setMask(!0),e.clear(!0,!0,!1),m.isXRRenderTarget=u.target===null||u.target.isXRRenderTarget===!0,m.texture.colorSpace=u.target?u.target.texture.colorSpace:e.outputColorSpace,e.render(t,c),m.isXRRenderTarget=!1,l.needsUpdate=!1,Y(e,b,h),r>0&&Z(e,h,m,h,r),X(x,h,n,!1),Y(e,x,m),X(S,m,n,!0),Y(e,S,g)}finally{m.isXRRenderTarget=!1,a.forEach((e,t)=>{e.visible=u.visible[t]}),t.background=u.background,t.matrixWorldAutoUpdate=u.matrixAuto,e.setClearColor(U,u.clearAlpha),e.autoClear=u.autoClear,e.setRenderTarget(u.target),i.viewport&&e.state.viewport(i.viewport)}C.uReflectionReady.value=1,w.ready=!0}return{uniforms:C,patch(e){Object.assign(e.uniforms,C),e.vertexShader=e.vertexShader.replace(`#include <common>`,`#include <common>
${ne}`).replace(`#include <fog_vertex>`,`#include <fog_vertex>
${re}`),e.fragmentShader=e.fragmentShader.replace(`#include <common>`,`#include <common>
${ie}`).replace(`#include <dithering_fragment>`,`${ae}
#include <dithering_fragment>`)},place({floorZ:e,height:t}){(e!==w.floorZ||t!==w.height)&&(w.sceneChanged=!0),w.floorZ=e,w.height=Math.max(t,1e-6)},beforeRender(e,t,n,r=[]){if(j.setFromMatrixPosition(n.matrixWorld),j.z<=w.floorZ){C.uReflectionReady.value=0;return}q(e);let i=G(n),a=e.shadowMap,o=a.enabled===!0&&(a.autoUpdate===!0||a.needsUpdate===!0),s=!K(i)||w.sceneChanged||o;(!w.ready||s||T.due())&&(w.lastView=i,w.sceneChanged=!1,Q(e,t,n,r),T.rendered())},get memoryBytes(){return w.width*w.heightPx*28},dispose(){T.dispose(),p.dispose();for(let e of[m,h,g])e.dispose();for(let e of[b,x,S])e.mesh.geometry.dispose(),e.mesh.material.dispose()}}}var z=`
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`,B=`
uniform highp sampler2D uDepth;
uniform mat4 uProjectionInverse;
vec3 viewAt(vec2 uv, float depth) {
  vec4 point = uProjectionInverse * vec4(vec3(uv, depth) * 2.0 - 1.0, 1.0);
  return point.xyz / point.w;
}
float depthAt(vec2 uv) {
  return textureLod(uDepth, uv, 0.0).x;
}
`,V=`
#define SLICES 3
#define STEPS 4
uniform mat4 uProjection;
uniform vec2 uSize;
uniform float uRadius;
uniform float uMaxPixels;
uniform float uFrame;
uniform float uOrthographic;
varying vec2 vUv;
${B}
const float PI = 3.141592653589793;
const float HALF_PI = 1.5707963267948966;

// Interleaved gradient noise (Jimenez 2014), moved on each sample of an accumulation.
float noiseAt(vec2 pixel, float frame) {
  pixel += 5.588238 * frame;
  return fract(52.9829189 * fract(dot(pixel, vec2(0.06711056, 0.00583715))));
}

// A full-resolution pixel's centre: a depth is read from one pixel, and the point it places
// must be that pixel's own, or a sloped surface reads as a staircase of false horizons.
vec2 pixelCentre(vec2 uv) {
  return (floor(uv * uSize) + 0.5) / uSize;
}

void main() {
  vec2 uv = pixelCentre(vUv);
  float depth = depthAt(uv);
  if (depth >= 1.0) {
    gl_FragColor = vec4(1.0, 0.0, 0.0, 1.0);
    return;
  }
  vec3 center = viewAt(uv, depth);
  // The surface's normal from its depth: on each axis, the neighbour on the same surface (the
  // nearer depth), so a silhouette never tilts it.
  vec2 texel = 1.0 / uSize;
  float left = depthAt(uv - vec2(texel.x, 0.0));
  float right = depthAt(uv + vec2(texel.x, 0.0));
  float below = depthAt(uv - vec2(0.0, texel.y));
  float above = depthAt(uv + vec2(0.0, texel.y));
  vec3 alongX = abs(left - depth) < abs(right - depth)
    ? center - viewAt(uv - vec2(texel.x, 0.0), left) : viewAt(uv + vec2(texel.x, 0.0), right) - center;
  vec3 alongY = abs(below - depth) < abs(above - depth)
    ? center - viewAt(uv - vec2(0.0, texel.y), below) : viewAt(uv + vec2(0.0, texel.y), above) - center;
  vec3 viewVec = uOrthographic > 0.5 ? vec3(0.0, 0.0, 1.0) : normalize(-center);
  vec3 normal = normalize(cross(alongX, alongY));
  if (dot(normal, viewVec) < 0.0) normal = -normal;

  // The radius on screen at this depth, held to a share of the view so a close-up's samples
  // stay coherent; the falloff follows the radius actually searched.
  float pixelSize = (uOrthographic > 0.5 ? 1.0 : -center.z) * 2.0 / (uProjection[1][1] * uSize.y);
  float radiusPixels = min(uRadius / pixelSize, uMaxPixels);
  if (radiusPixels < 2.0) {
    gl_FragColor = vec4(1.0, -center.z, 0.0, 1.0);
    return;
  }
  float radius = radiusPixels * pixelSize;
  float falloffRange = 0.615 * radius;
  float falloffMul = -1.0 / falloffRange;
  float falloffAdd = (radius - falloffRange) / falloffRange + 1.0;

  float sliceNoise = noiseAt(gl_FragCoord.xy, uFrame);
  float stepNoise = noiseAt(gl_FragCoord.yx + vec2(13.0, 71.0), uFrame + 0.5);
  float visibility = 0.0;
  for (int slice = 0; slice < SLICES; slice++) {
    float phi = (float(slice) + sliceNoise) * PI / float(SLICES);
    vec2 omega = vec2(cos(phi), sin(phi));
    vec3 direction = vec3(omega, 0.0);
    vec3 orthoDirection = direction - dot(direction, viewVec) * viewVec;
    vec3 axis = normalize(cross(orthoDirection, viewVec));
    vec3 projectedNormal = normal - axis * dot(normal, axis);
    float projectedLength = length(projectedNormal);
    float cosNormal = clamp(dot(projectedNormal, viewVec) / max(projectedLength, 1e-5), 0.0, 1.0);
    float n = sign(dot(orthoDirection, projectedNormal)) * acos(cosNormal);
    float low0 = cos(n + HALF_PI);
    float low1 = cos(n - HALF_PI);
    float horizon0 = low0;
    float horizon1 = low1;
    for (int step = 0; step < STEPS; step++) {
      float jitter = fract(stepNoise + float(slice * STEPS + step) * 0.6180339887);
      float s = (float(step) + jitter) / float(STEPS);
      s = s * s + 1.5 / radiusPixels;
      vec2 offset = omega * (s * radiusPixels) * texel;
      vec2 uv0 = pixelCentre(uv + offset);
      vec2 uv1 = pixelCentre(uv - offset);
      vec3 delta0 = viewAt(uv0, depthAt(uv0)) - center;
      vec3 delta1 = viewAt(uv1, depthAt(uv1)) - center;
      float distance0 = max(length(delta0), 1e-6);
      float distance1 = max(length(delta1), 1e-6);
      float weight0 = clamp(distance0 * falloffMul + falloffAdd, 0.0, 1.0);
      float weight1 = clamp(distance1 * falloffMul + falloffAdd, 0.0, 1.0);
      horizon0 = max(horizon0, mix(low0, dot(delta0 / distance0, viewVec), weight0));
      horizon1 = max(horizon1, mix(low1, dot(delta1 / distance1, viewVec), weight1));
    }
    projectedLength = mix(projectedLength, 1.0, 0.05);
    float h0 = -acos(clamp(horizon1, -1.0, 1.0));
    float h1 = acos(clamp(horizon0, -1.0, 1.0));
    h0 = n + clamp(h0 - n, -HALF_PI, HALF_PI);
    h1 = n + clamp(h1 - n, -HALF_PI, HALF_PI);
    float arc0 = (cosNormal + 2.0 * h0 * sin(n) - cos(2.0 * h0 - n)) / 4.0;
    float arc1 = (cosNormal + 2.0 * h1 * sin(n) - cos(2.0 * h1 - n)) / 4.0;
    visibility += projectedLength * (arc0 + arc1);
  }
  gl_FragColor = vec4(clamp(visibility / float(SLICES), 0.0, 1.0), -center.z, 0.0, 1.0);
}
`,H=`
uniform sampler2D uInput;
uniform vec2 uStep;
varying vec2 vUv;
void main() {
  vec4 center = texture2D(uInput, vUv);
  if (center.g <= 0.0) {
    gl_FragColor = center;
    return;
  }
  float sum = center.r;
  float total = 1.0;
  for (int i = -4; i <= 4; i++) {
    if (i == 0) continue;
    vec4 tap = texture2D(uInput, vUv + uStep * float(i));
    float t = float(i) / 2.5;
    float weight = tap.g > 0.0 ? exp(-0.5 * t * t) * exp(-abs(tap.g - center.g) / (center.g * 0.02)) : 0.0;
    sum += tap.r * weight;
    total += weight;
  }
  gl_FragColor = vec4(sum / total, center.g, 0.0, 1.0);
}
`,U=`
uniform sampler2D uColor;
uniform sampler2D uOcclusion;
uniform vec2 uOcclusionSize;
uniform float uStrength;
uniform float uPower;
varying vec2 vUv;
${B}
vec3 toLinear(vec3 c) {
  return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(vec3(0.04045), c));
}
vec3 toDisplay(vec3 c) {
  return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(vec3(0.0031308), c));
}
void main() {
  vec4 color = texture2D(uColor, vUv);
  float depth = depthAt(vUv);
  float visibility = 1.0;
  if (depth < 1.0 && uStrength > 0.0) {
    float z = -viewAt(vUv, depth).z;
    vec2 at = vUv * uOcclusionSize - 0.5;
    vec2 f = fract(at);
    ivec2 base = ivec2(floor(at));
    ivec2 last = ivec2(uOcclusionSize) - 1;
    float sum = 0.0;
    float total = 0.0;
    for (int y = 0; y < 2; y++) {
      for (int x = 0; x < 2; x++) {
        vec4 tap = texelFetch(uOcclusion, clamp(base + ivec2(x, y), ivec2(0), last), 0);
        float bilinear = (x == 0 ? 1.0 - f.x : f.x) * (y == 0 ? 1.0 - f.y : f.y);
        float weight = tap.g > 0.0 ? (bilinear + 1e-3) * exp(-abs(tap.g - z) / (z * 0.02)) : 0.0;
        sum += tap.r * weight;
        total += weight;
      }
    }
    if (total > 1e-5) visibility = pow(sum / total, uPower);
    visibility = mix(1.0, visibility, uStrength);
  }
  gl_FragColor = vec4(toDisplay(toLinear(color.rgb) * visibility), color.a);
}
`,W=`
uniform sampler2D uAccumulation;
varying vec2 vUv;
float hash(vec2 p) {
  return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}
void main() {
  vec4 color = texture2D(uAccumulation, vUv);
  float noise = (hash(gl_FragCoord.xy) + hash(gl_FragCoord.yx + 19.19) - 1.0) / 255.0;
  gl_FragColor = vec4(color.rgb + noise * color.a, color.a);
}
`;function G(e,t){let n=0,r=1/t,i=e;for(;i>0;)n+=i%t*r,i=Math.floor(i/t),r/=t;return n}function K(e){return e>0?[G(e,2)-.5,G(e,3)-.5]:[0,0]}function q(e,t,n,r={}){let i=new e.BufferGeometry;i.setAttribute(`position`,new e.Float32BufferAttribute([-1,-1,0,3,-1,0,-1,3,0],3)),i.setAttribute(`uv`,new e.Float32BufferAttribute([0,0,2,0,0,2],2));let a=new e.Mesh(i,new e.ShaderMaterial({uniforms:n,vertexShader:z,fragmentShader:t,depthTest:!1,depthWrite:!1,blending:e.NoBlending,toneMapped:!1,...r}));a.frustumCulled=!1;let o=new e.Scene;return o.add(a),{mesh:a,scene:o,uniforms:a.material.uniforms}}function J(e,t){let n=new e.WebGLRenderTarget(1,1,{type:e.HalfFloatType,minFilter:e.NearestFilter,magFilter:e.NearestFilter,depthBuffer:!1,generateMipmaps:!1});return n.texture.name=t,n}function Y(e,{samples:t=32,multisample:n=4,occlusion:r={},onSample:i=null,afterSample:a=null}={}){let o={samples:Math.max(1,Math.round(t)),strength:1,radius:.1,power:2,maxScreen:.2,modelRadius:1,...r},s=new e.DepthTexture(1,1,e.UnsignedInt248Type);s.format=e.DepthStencilFormat,s.minFilter=e.NearestFilter,s.magFilter=e.NearestFilter;let c=new e.WebGLRenderTarget(1,1,{type:e.UnsignedByteType,minFilter:e.NearestFilter,magFilter:e.NearestFilter,depthBuffer:!0,stencilBuffer:!0,depthTexture:s,samples:Math.max(0,Math.round(n)),generateMipmaps:!1});c.texture.name=`studio-frame-scene`,c.texture.internalFormat=`RGBA8`,c.isXRRenderTarget=!0;let l=[J(e,`studio-frame-occlusion`),J(e,`studio-frame-occlusion-smooth`)],u=J(e,`studio-frame-accumulation`),d=new e.OrthographicCamera(-1,1,1,-1,0,1),f=new e.Matrix4,p=new e.Matrix4,m=q(e,V,{uDepth:{value:s},uProjection:{value:f},uProjectionInverse:{value:p},uSize:{value:new e.Vector2(1,1)},uRadius:{value:1},uMaxPixels:{value:64},uFrame:{value:0},uOrthographic:{value:0}}),h=q(e,H,{uInput:{value:null},uStep:{value:new e.Vector2}}),g=q(e,U,{uColor:{value:c.texture},uDepth:{value:s},uProjectionInverse:{value:p},uOcclusion:{value:l[0].texture},uOcclusionSize:{value:new e.Vector2(1,1)},uStrength:{value:1},uPower:{value:1}},{blending:e.CustomBlending,blendEquation:e.AddEquation,blendSrc:e.ConstantAlphaFactor,blendDst:e.OneMinusConstantAlphaFactor,blendEquationAlpha:e.AddEquation,blendSrcAlpha:e.ConstantAlphaFactor,blendDstAlpha:e.OneMinusConstantAlphaFactor,blendAlpha:1}),_=q(e,W,{uAccumulation:{value:u.texture}}),v={index:0,width:0,height:0,disposed:!1},y=new e.Vector2,b=new e.Matrix4,x=new e.Matrix4,S=[],C=new e.Vector4,w=new e.Vector4;T([0,0,0],1);function T(t,n){S.length=0;let r=n/Math.sqrt(3);S.push(new e.Vector4(t[0],t[1],t[2],1));for(let n of[-1,1])for(let i of[-1,1])for(let a of[-1,1])S.push(new e.Vector4(t[0]+n*r,t[1]+i*r,t[2]+a*r,1))}function E(){let e=0,t=0;for(let n of S)C.copy(n).applyMatrix4(b),w.copy(n).applyMatrix4(x),C.w>0&&w.w>0&&(t+=1,e=Math.max(e,Math.abs(w.x/w.w-C.x/C.w)*v.width/2,Math.abs(w.y/w.w-C.y/C.w)*v.height/2));return t>0?e:x.equals(b)?0:1/0}function D(e){e.getDrawingBufferSize(y);let t=Math.max(1,Math.round(y.x)),n=Math.max(1,Math.round(y.y));if(t===v.width&&n===v.height)return!1;v.width=t,v.height=n,c.setSize(t,n);let r=Math.max(1,Math.ceil(t/2)),i=Math.max(1,Math.ceil(n/2));for(let e of l)e.setSize(r,i);return u.setSize(t,n),m.uniforms.uSize.value.set(t,n),g.uniforms.uOcclusionSize.value.set(r,i),!0}function O(e,t,n){e.setRenderTarget(n),e.render(t.scene,d)}function k(e,t,n,r){let[i,a]=K(r),o=n.view?{...n.view}:null;r>0&&n.setViewOffset(v.width,v.height,i,a,v.width,v.height);try{c.texture.colorSpace=e.outputColorSpace,e.setRenderTarget(c),e.render(t,n),f.copy(n.projectionMatrix),p.copy(n.projectionMatrixInverse)}finally{r>0&&(o?.enabled?n.setViewOffset(o.fullWidth,o.fullHeight,o.offsetX,o.offsetY,o.width,o.height):n.clearViewOffset())}}function A(e,t,n){let r=m.uniforms;r.uRadius.value=Math.max(o.modelRadius*o.radius,1e-9),r.uMaxPixels.value=Math.max(v.height*o.maxScreen,4),r.uFrame.value=n%64,r.uOrthographic.value=+!!t.isOrthographicCamera,O(e,m,l[0]);let[i,a]=l;h.uniforms.uInput.value=i.texture,h.uniforms.uStep.value.set(1/i.width,0),O(e,h,a),h.uniforms.uInput.value=a.texture,h.uniforms.uStep.value.set(0,1/i.height),O(e,h,i)}function j(e,t){e.setRenderTarget(t),e.render(_.scene,d)}return{get samples(){return o.samples},get sample(){return v.index},get converged(){return v.index>=o.samples},place({radius:e,center:t=[0,0,0]}){let n=Math.max(Number(e)||0,1e-9);n!==o.modelRadius&&(v.index=0),o.modelRadius=n,T(t.map(e=>Number(e)||0),n)},configure({samples:e,occlusion:t}={}){e!=null&&(o.samples=Math.max(1,Math.round(e))),t&&Object.assign(o,t),v.index=0},reset(){v.index=0},render(e,t,n,{still:r=!1,present:s=!0}={}){if(v.disposed)throw Error(`The studio frame was disposed`);let c=e.getRenderTarget(),l=e.autoClear,d=D(e);if(n.updateMatrixWorld(),x.multiplyMatrices(n.projectionMatrix,n.matrixWorldInverse),(!r||d||E()>.25)&&(v.index=0),v.index===0&&b.copy(x),v.index>=o.samples)return s&&j(e,c),{refining:!1,sample:v.index};let f=v.index,p=e.shadowMap;i?.(f,e,{castersChanged:!r&&!!(p?.enabled&&(p.autoUpdate||p.needsUpdate))});try{e.autoClear=!0,k(e,t,n,f)}finally{a?.(f)}try{e.autoClear=!1,o.strength>0&&A(e,n,f),g.uniforms.uStrength.value=o.strength,g.uniforms.uPower.value=o.power,g.mesh.material.blendAlpha=1/(f+1),O(e,g,u),s&&j(e,c)}finally{e.autoClear=l,e.setRenderTarget(c)}return v.index=f+1,{refining:v.index<o.samples,sample:f}},renderStill(e,t,n,{samples:r=o.samples}={}){let i=Math.max(1,Math.round(r)),a=o.samples,s=e.shadowMap,c=s?.autoUpdate;o.samples=i;try{for(let r=0;r<i;r+=1)r===1&&s&&(s.autoUpdate=!1),this.render(e,t,n,{still:r>0,present:r===i-1})}finally{o.samples=a,s&&(s.autoUpdate=c)}},get memoryBytes(){let e=v.width*v.height,t=Math.max(1,c.samples),n=l[0].width*l[0].height;return e*8*(t+ +(c.samples>0))+n*8*2+e*8},dispose(){if(!v.disposed){v.disposed=!0,s.dispose(),c.dispose(),u.dispose();for(let e of l)e.dispose();for(let e of[m,h,g,_])e.mesh.geometry.dispose(),e.mesh.material.dispose()}}}}function X(e,t,n){if(Array.isArray(e))return u(e[t],n);let r=[`x`,`y`,`z`][t];return u(e?.[r],n)}function Z(e,t=1){let n=Math.max(u(t,1),1e-6),r=[0,1,2].map(t=>X(e?.min,t,-n)),i=[0,1,2].map(t=>X(e?.max,t,n));return r.every(Number.isFinite)&&i.every(Number.isFinite)&&i.every((e,t)=>e>=r[t])?{min:r,max:i,center:r.map((e,t)=>(e+i[t])/2),radius:Math.max(Math.hypot(...i.map((e,t)=>(e-r[t])/2)),1e-6)}:{min:[-n,-n,-n],max:[n,n,n],center:[0,0,0],radius:n}}function Q(t={}){let n=t.lighting||{},i=t.backdrop||{};return{exposure:p(u(t.exposure,0),-5,5),lighting:{enabled:n.enabled!==!1,rotation:p(u(n.rotation,r.rotation),-180,180),size:p(u(n.size,r.size),.25,3),fill:p(u(n.fill,r.fill),0,1)},backdrop:{...Object.hasOwn(i,`opacity`)?{opacity:p(u(i.opacity,1),0,1)}:{},color:typeof i.color==`string`?i.color:`#ffffff`,transparent:typeof i.transparent==`boolean`?i.transparent:e.transparent,ground:typeof i.ground==`boolean`?i.ground:e.ground,groundPlacement:i.groundPlacement??e.groundPlacement,groundColor:i.groundColor??i.color??`#e7e7e5`,groundOpacity:p(u(i.groundOpacity,e.groundOpacity),0,1),groundFinish:i.groundFinish===`glossy`?`glossy`:`matte`}}}function oe(e){Array.isArray(e)?e.forEach(e=>e?.dispose?.()):e?.dispose?.()}function $(e){e.ground&&(e.group.remove(e.ground),e.ground.geometry?.dispose?.(),oe(e.ground.material),e.contactShadow?.dispose(),he(e),e.ground=null,e.contactShadow=null,e.groundKind=null)}function se(e,t){e.color.set(t).multiplyScalar(m),e.emissive.set(t);let{r:n,g:r,b:a}=e.emissive,o=.2126*n+.7152*r+.0722*a,s=f*Math.max(0,1-o/i);e.emissive.r+=(1-n)*s,e.emissive.g+=(1-r)*s,e.emissive.b+=(1-a)*s}var ce=`
gl_FragColor.a *= studioFloorFade();
#ifdef STUDIO_DITHER_SCALE
gl_FragColor.rgb += (rand(gl_FragCoord.xy) + rand(gl_FragCoord.yx + 17.0) - 1.0) * STUDIO_DITHER_SCALE
  / (255.0 * max(gl_FragColor.a, 0.05));
#else
gl_FragColor.rgb += (rand(gl_FragCoord.xy) + rand(gl_FragCoord.yx + 17.0) - 1.0)
  / (255.0 * max(gl_FragColor.a, 0.05));
#endif
`,le=`
varying vec2 vStudioFloorPlane;
`,ue=`
uniform float uStudioFloorFade;
varying vec2 vStudioFloorPlane;
float studioFloorFade() {
  float fade = 1.0 - smoothstep(uStudioFloorFade, 1.0, length(vStudioFloorPlane) * 2.0);
  return fade * fade;
}
`;function de(e,t,n){e.onBeforeCompile=e=>{t?.patch(e),e.uniforms.uStudioFloorFade=n,e.vertexShader=e.vertexShader.replace(`#include <common>`,`#include <common>
${le}`).replace(`#include <begin_vertex>`,`#include <begin_vertex>
vStudioFloorPlane = position.xy;`),e.fragmentShader=e.fragmentShader.replace(`#include <common>`,`#include <common>
${ue}`).replace(`#include <dithering_fragment>`,ce)},e.customProgramCacheKey=()=>t?`studio-floor-reflection`:`studio-floor-dither`}function fe(e,t){let n=new e.Group;n.name=`cadgen-photographic-studio`;let r=new e.SpotLight(16777215,1);r.name=`studio-key-softbox`,r.decay=2,r.castShadow=!0;let i=new e.Object3D;i.name=`studio-key-target`,r.target=i,n.add(r,i),t.scene.add(n);let a=new e.Color;return t.renderer.getClearColor?.(a),{group:n,keyLight:r,target:i,shadowMapSize:null,ground:null,floorFade:{value:0},backdrop:null,contactShadow:null,reflection:null,reflectionHidden:null,restoreSceneHook:null,reflecting:!1,scene:t.scene,groundKind:null,frame:null,keyRest:new e.Vector3,keyAcross:new e.Vector3,keyUp:new e.Vector3,keySample:0,original:{toneMapping:t.renderer.toneMapping,toneMappingExposure:t.renderer.toneMappingExposure,outputColorSpace:t.renderer.outputColorSpace,shadowEnabled:t.renderer.shadowMap?.enabled,shadowType:t.renderer.shadowMap?.type,background:t.scene.background,environmentIntensity:t.scene.environmentIntensity,environmentRotation:t.scene.environmentRotation?.clone?.(),clearColor:a,clearAlpha:t.renderer.getClearAlpha?.()}}}function pe(e,t,n,r){let i=e.ground;if(e.reflection&&!e.reflecting&&i?.visible&&i.material.opacity>0){e.reflecting=!0;try{e.reflection.beforeRender(t,n,r,e.reflectionHidden())}finally{e.reflecting=!1}}}function me(e){let t=e.scene,n=Object.hasOwn(t,`onBeforeRender`),r=t.onBeforeRender;t.onBeforeRender=function(t,n,i,a){r.call(this,t,n,i,a),pe(e,t,n,i)},e.restoreSceneHook=()=>{n?t.onBeforeRender=r:delete t.onBeforeRender}}function he(e){e.reflection&&(e.restoreSceneHook?.(),e.reflection.dispose(),e.reflection=null,e.reflectionHidden=null,e.restoreSceneHook=null)}function ge(e,t,n,{contactShadow:r,softwareRendering:i,guides:a}){let o=g[n.backdrop.groundFinish],s=t.ground.material;s.roughness=o.roughness,s.envMapIntensity=o.envMapIntensity;let c=!!o.reflection&&n.lighting.enabled&&!i;c!==!!t.reflection&&(c?(t.reflection=R(e,{...o.reflection,requestFrame:r.requestFrame||null}),t.reflectionHidden=()=>[t.ground,t.contactShadow?.layer,t.backdrop?.object,...a()].filter(Boolean),me(t)):he(t),de(s,t.reflection,t.floorFade),s.needsUpdate=!0)}function _e(e,n,r,i,a=i,{contactShadow:s={},softwareRendering:l=!1,guides:u=()=>[],ditherScale:d=1}={}){if(!r.backdrop.ground){$(n);return}let f=r.backdrop.transparent&&!Object.hasOwn(r.backdrop,`opacity`)?`shadow`:`physical`;if(!n.ground||n.groundKind!==f){$(n);let t=f===`shadow`?new e.ShadowMaterial({color:0,opacity:.3,transparent:!0}):new e.MeshStandardMaterial({color:r.backdrop.color,emissive:r.backdrop.color,emissiveIntensity:c,roughness:g.matte.roughness,metalness:0,envMapIntensity:g.matte.envMapIntensity,transparent:!0,opacity:r.backdrop.groundOpacity});t.depthWrite=!1,t.side=e.DoubleSide,t.forceSinglePass=!0,t.polygonOffset=!0,t.polygonOffsetFactor=1,t.polygonOffsetUnits=1,f===`physical`&&de(t,null,n.floorFade);let i=new e.Mesh(new e.PlaneGeometry(1,1),t);i.name=`studio-ground`,i.receiveShadow=f===`shadow`,i.renderOrder=-3,n.group.add(i),n.ground=i,f===`physical`&&!l&&(n.contactShadow=j(e,n.keyLight,s),n.group.add(n.contactShadow.object)),n.groundKind=f}n.groundKind===`physical`&&(se(n.ground.material,r.backdrop.groundColor),ge(e,n,r,{contactShadow:s,softwareRendering:l,guides:u}),k(n.ground.material,d),n.contactShadow?.setDitherScale(d)),n.ground.material.opacity=r.backdrop.groundOpacity;let p=a.max[0]-a.min[0],m=a.max[1]-a.min[1],h=2*Math.max(a.radius,Math.hypot(p,m)/2)*o.outer;n.floorFade.value=o.inner/o.outer;let _=r.backdrop.groundPlacement===`origin`?0:i.min[2];n.ground.scale.set(h,h,1),n.ground.position.set(a.center[0],a.center[1],_),n.ground.updateMatrixWorld(!0);let v=Math.max(a.max[2]-_,a.radius*.05);if(n.reflection?.place({floorZ:_,height:v}),n.contactShadow){let e=Math.max(p,m)/2;n.contactShadow.place({center:a.center,half:e+v*t.reach,floorZ:_,height:Math.max(v,e*.5)*t.height}),n.contactShadow.setOpacity(r.backdrop.groundOpacity),n.contactShadow.setEnabled(r.lighting.enabled)}}function ve(e,t,n,r,i,o){let c=e.MathUtils.degToRad(n.lighting.rotation),d=new e.Vector3(...a).normalize();d.applyAxisAngle(new e.Vector3(0,0,1),c);let f=Math.max(r.radius*5,1e-4),m=new e.Vector3(...r.center);t.keyLight.position.copy(m).addScaledVector(d,f),t.target.position.copy(m),t.keyLight.angle=p(Math.atan2(r.radius*1.35,f),.18,.65),t.keyLight.penumbra=p(.48+n.lighting.size*.1,.5,.78),t.keyLight.intensity=l*f*f,t.keyLight.castShadow=!o;let g=Math.round(p(u(i,2048),256,4096));t.shadowMapSize!==g&&(t.keyLight.shadow.map?.dispose?.(),t.keyLight.shadow.map=null,t.keyLight.shadow.mapPass?.dispose?.(),t.keyLight.shadow.mapPass=null,t.shadowMapSize=g),t.keyLight.shadow.mapSize.set(g,g),t.keyLight.shadow.camera.near=Math.max(f-r.radius*2,f*.05,1e-5),t.keyLight.shadow.camera.far=Math.max(f+r.radius*3,t.keyLight.shadow.camera.near*2),t.keyLight.shadow.camera.fov=e.MathUtils.radToDeg(t.keyLight.angle*2);let _=2*f*Math.tan(t.keyLight.angle);t.keyLight.shadow.bias=-12e-5,t.keyLight.shadow.normalBias=Math.max(_/g,1e-6),t.keyLight.shadow.radius=p(.65+n.lighting.size*.45,.75,2),t.keyLight.shadow.camera.updateProjectionMatrix?.(),t.keyLight.shadow.needsUpdate=!0,t.keyLight.updateMatrixWorld(!0),t.target.updateMatrixWorld(!0),t.keyRest.copy(t.keyLight.position),t.keyAcross.crossVectors(d,new e.Vector3(0,0,1)),t.keyAcross.lengthSq()<1e-8&&t.keyAcross.set(1,0,0),t.keyAcross.normalize(),t.keyUp.crossVectors(t.keyAcross,d).normalize();let v=f*n.lighting.size*s.spread/6;t.keyAcross.multiplyScalar(v*h.width/2),t.keyUp.multiplyScalar(v*h.height/2),t.keySample=0}function ye(e,t){let n=t>0?t:0;if(n===e.keySample)return!1;if(e.keySample=n,e.keyLight.position.copy(e.keyRest),n>0){let[t,r]=be(n);e.keyLight.position.addScaledVector(e.keyAcross,t).addScaledVector(e.keyUp,r)}return e.keyLight.updateMatrixWorld(!0),!0}function be(e){return[2*((.5+e*.7548776662466927)%1)-1,2*((.5+e*.5698402909980532)%1)-1]}function xe(e,t,r,i,a){let{renderer:o,scene:s}=t;o.toneMapping=i.lighting.enabled?e.NeutralToneMapping:r.original.toneMapping,o.toneMappingExposure=i.lighting.enabled?2**i.exposure:r.original.toneMappingExposure,o.outputColorSpace=e.SRGBColorSpace,o.shadowMap&&(o.shadowMap.enabled=i.lighting.enabled,o.shadowMap.type=e.PCFShadowMap),i.lighting.enabled?(s.environmentIntensity=1,s.environmentRotation?.set?.(0,0,e.MathUtils.degToRad(i.lighting.rotation))):r.original.environmentRotation&&s.environmentRotation?.copy?.(r.original.environmentRotation);let c=i.backdrop.opacity??+!i.backdrop.transparent,l=new e.Color(i.backdrop.color);s.background=c<1?null:l,o.setClearColor?.(l,c),r.backdrop||(r.backdrop=y(e,n),r.group.add(r.backdrop.object)),r.backdrop.update({color:l,opacity:c}),k(r.backdrop.object.material,a),r.keyLight.visible=i.lighting.enabled}function Se(e,t,n,r,i,a,o){if(!(a!==!1&&r.lighting.enabled&&t.softwareRendering!==!0)){n.frame?.dispose(),n.frame=null;return}if(!n.frame){let r=t.renderer.getContext?.()?.getContextAttributes?.()?.antialias!==!1,i=(t.renderer.getPixelRatio?.()??1)>=2;n.frame=Y(e,{multisample:a?.multisample??(r?i?2:4:0),occlusion:d.occlusion,onSample(e,t,{castersChanged:r}){n.keyLight.castShadow&&n.keyLight.visible&&(ye(n,e)&&t.shadowMap&&(t.shadowMap.needsUpdate=!0),n.contactShadow?.holdHeights(!r))},afterSample(){n.contactShadow?.holdHeights(!1)}})}let s=a?.samples??d.samples[o===`final`?`final`:`preview`];n.frame.samples!==s&&n.frame.configure({samples:s}),n.frame.place({radius:i.radius,center:i.center})}function Ce(e,t,n={},{bounds:r=t?.modelBounds,groundBounds:i=null,shadowMapSize:a=2048,contactShadow:o={},ditherScale:s=1,frame:c={}}={}){if(!e||!t?.scene||!t?.renderer)throw Error(`applyPhotographicStudio requires THREE and a runtime with scene and renderer`);if(n.lighting?.enabled!==!1&&t.renderer.capabilities?.logarithmicDepthBuffer===!0)throw Error(`Photographic Render requires a renderer created without logarithmicDepthBuffer so contact shadows remain visible`);let l=Q(n),u=t.photographicStudio||fe(e,t);t.photographicStudio=u;let d=Z(r,t.modelRadius);xe(e,t,u,l,s),l.lighting.enabled&&ve(e,u,l,d,a,t.softwareRendering===!0);let f=i?Z(i,t.modelRadius):d;return _e(e,u,l,d,f,{contactShadow:o,softwareRendering:t.softwareRendering===!0,guides:()=>[t.gridHelper,t.originAxis],ditherScale:s}),Se(e,t,u,l,f,c,n.quality),t.invalidateShadows?.(),t.requestRender?.(),u}function we(e){let t=e?.photographicStudio;if(!t)return;$(t),t.backdrop?.dispose(),t.backdrop=null,t.frame?.dispose(),t.frame=null,t.keyLight.shadow?.map?.dispose?.(),t.keyLight.shadow.map=null,e.scene?.remove?.(t.group);let n=t.original;e.renderer&&(e.renderer.toneMapping=n.toneMapping,e.renderer.toneMappingExposure=n.toneMappingExposure,e.renderer.outputColorSpace=n.outputColorSpace,e.renderer.shadowMap&&(e.renderer.shadowMap.enabled=n.shadowEnabled,e.renderer.shadowMap.type=n.shadowType),n.clearColor&&typeof n.clearAlpha==`number`&&e.renderer.setClearColor?.(n.clearColor,n.clearAlpha)),e.scene&&(e.scene.background=n.background,e.scene.environmentIntensity=n.environmentIntensity,n.environmentRotation&&e.scene.environmentRotation?.copy&&e.scene.environmentRotation.copy(n.environmentRotation)),e.photographicStudio=null}export{Ce as applyPhotographicStudio,we as disposePhotographicStudio,ye as sampleKey,be as softboxPoint};
//# debugId=6e91b845-46e7-4210-8103-520a95a5de63