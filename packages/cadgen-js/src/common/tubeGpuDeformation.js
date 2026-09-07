// Dense native STEP tubes keep their exact CPU mapping for picking, while the
// display transports vertices on the GPU. No new geometry replaces the STEP.
// Frame-table interpolation is a rendering approximation, not a mechanics gate.
export function buildGpuTubeFrames(path, sample) {
  const knots=[];
  for(const segment of path.segments) {
    const entries=segment.kind==='bezier'?segment.table:null;
    const count=entries?.length ?? (segment.kind==='line'?2:Math.ceil(segment.length/segment.radius/.01)+1);
    for(let i=0;i<count;i++) {
      const entry=entries?.[i],distance=entry?entry.s:segment.length*i/(count-1),s=segment.offset+distance;
      const frame=entry?.curvature?entry:sample(path,s);
      const knot={s,point:frame.point,tangent:frame.tangent,normal:frame.normal,curvature:frame.curvature};
      if(knots.length && s<=knots.at(-1).s+1e-12)knots[knots.length-1]=knot;else knots.push(knot);
    }
  }
  const count=Math.max(2,Math.ceil(path.length/.1)+1),data=new Float32Array(count*16);let k=0;
  for(let i=0;i<count;i++) {
    const s=path.length*i/(count-1);while(k<knots.length-2&&knots[k+1].s<s)k++;
    const a=knots[k],b=knots[k+1],h=b.s-a.s,u=Math.max(0,Math.min(1,(s-a.s)/h)),v=1-u;
    const h00=2*u*u*u-3*u*u+1,h10=u*u*u-2*u*u+u,h01=-2*u*u*u+3*u*u,h11=u*u*u-u*u;
    let t0=v*a.tangent[0]+u*b.tangent[0],t1=v*a.tangent[1]+u*b.tangent[1],t2=v*a.tangent[2]+u*b.tangent[2];
    const tn=Math.hypot(t0,t1,t2);t0/=tn;t1/=tn;t2/=tn;
    let n0=v*a.normal[0]+u*b.normal[0],n1=v*a.normal[1]+u*b.normal[1],n2=v*a.normal[2]+u*b.normal[2];
    const d=n0*t0+n1*t1+n2*t2;n0-=d*t0;n1-=d*t1;n2-=d*t2;const nn=Math.hypot(n0,n1,n2);n0/=nn;n1/=nn;n2/=nn;
    const offset=i*16;
    for(let j=0;j<3;j++){data[offset+j]=h00*a.point[j]+h10*h*a.tangent[j]+h01*b.point[j]+h11*h*b.tangent[j];data[offset+12+j]=v*a.curvature[j]+u*b.curvature[j];}
    data.set([t0,t1,t2],offset+4);data.set([n0,n1,n2],offset+8);
  }
  return {data,count};
}
const PARS=`
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
vec3 cadGpuPoint; vec3 cadGpuNormal; bool cadGpuEvaluated=false;
vec4 cadMapping(float index){return texture2D(cadTubeMappingTexture,(vec2(mod(index,cadTubeMappingSize.x),floor(index/cadTubeMappingSize.x))+.5)/cadTubeMappingSize);}
vec3 cadFrame(float row,float column){return texture2D(cadTubeFrameTexture,vec2((column+.5)/4.,(row+.5)/cadTubeFrameCount)).xyz;}
void cadEvaluateTube(){
 if(cadGpuEvaluated||cadTubeGpuEnabled<.5)return;cadGpuEvaluated=true;
 vec4 a=cadMapping(2.*cadTubeMappingIndex),b=cadMapping(2.*cadTubeMappingIndex+1.);
 float f=clamp(a.x,0.,1.)*(cadTubeFrameCount-1.),lo=floor(f),hi=min(lo+1.,cadTubeFrameCount-1.),u=f-lo;
 vec3 p=mix(cadFrame(lo,0.),cadFrame(hi,0.),u),t=normalize(mix(cadFrame(lo,1.),cadFrame(hi,1.),u));
 vec3 n=mix(cadFrame(lo,2.),cadFrame(hi,2.),u);n=normalize(n-t*dot(n,t));vec3 v=cross(t,n);
 vec3 curvature=mix(cadFrame(lo,3.),cadFrame(hi,3.),u);
 float c=cos(cadTubeGpuParameters.x),s=sin(cadTubeGpuParameters.x);
 vec2 transverse=mat2(c,s,-s,c)*a.yz;vec3 offset=n*transverse.x+v*transverse.y;
 float metric=1.-dot(curvature,offset);
 vec2 normalPair=mat2(c,s,-s,c)*b.xy;
 vec3 normalValue=n*normalPair.x+v*normalPair.y+t*b.z*b.w/(metric*cadTubeGpuParameters.y);
 cadGpuPoint=(cadTubeGpuInverse*vec4(p+offset+a.w*t,1.)).xyz;
 cadGpuNormal=normalize(cadTubeGpuNormalMatrix*normalValue);
}
`;
function patchMaterial(material,uniforms) {
  if(!material)return;
  let state=material.userData.cadGpuTube;
  if(!state) {
    const compile=material.onBeforeCompile,key=material.customProgramCacheKey;
    state=material.userData.cadGpuTube={uniforms};
    material.onBeforeCompile=function(shader,renderer){
      compile.call(this,shader,renderer);Object.assign(shader.uniforms,state.uniforms);
      shader.vertexShader=shader.vertexShader.replace('#include <common>','#include <common>\n'+PARS)
        .replace('#include <beginnormal_vertex>','#include <beginnormal_vertex>\ncadEvaluateTube();if(cadTubeGpuEnabled>.5)objectNormal=cadGpuNormal;')
        .replace('#include <begin_vertex>','#include <begin_vertex>\ncadEvaluateTube();if(cadTubeGpuEnabled>.5)transformed=cadGpuPoint;')
        .replace('vCadTubeMaterial = cadTubeMaterial;', 'vec4 cadBraidMapping=cadMapping(2.*cadTubeMappingIndex);vCadTubeMaterial=vec3(cadBraidMapping.x*cadTubeRestLength,cadBraidMapping.yz);');
    };
    material.customProgramCacheKey=function(){return `${key.call(this)}:cad-gpu-tube-v1`;};material.needsUpdate=true;
  } else {
    for(const [name,uniform] of Object.entries(uniforms)){
      if(state.uniforms[name]){state.uniforms[name].value=uniform.value;uniforms[name]=state.uniforms[name];}
      else {state.uniforms[name]=uniform;material.needsUpdate=true;}
    }
  }
}
export function disableGpuTube(record) {
  const state=record?.tubeGpuState;if(!state)return;
  state.uniforms.cadTubeGpuEnabled.value=0;state.active=false;
  record.mesh.userData.cadTubeBeforeRaycast=null;
}
export function syncGpuTubeMaterials(record) {
  const state=record?.tubeGpuState;if(!state?.active)return;
  for(const object of [record.mesh,record.silhouette,record.ghostMesh])if(object)patchMaterial(object.material,state.uniforms);
}
export function applyGpuTube(THREE,record,restState,deformation,inverse,sample,materialize) {
  if(!record.gpuTubeDeformationAllowed||deformation.path.length>819.1)return false;
  let state=record.tubeGpuState;
  if(!state||state.mapping!==restState.mapping) {
    state?.mappingTexture.dispose();state?.frameTexture?.dispose();
    const mapping=restState.mapping,width=1024,height=Math.ceil(mapping.values.length/4/width),data=mapping.gpu?mapping.values:new Float32Array(width*height*4);if(!mapping.gpu)data.set(mapping.values);
    const mappingTexture=new THREE.DataTexture(data,width,height,THREE.RGBAFormat,THREE.FloatType);mappingTexture.needsUpdate=true;
    const indices=mapping.gpu?mapping.indices:new Float32Array(mapping.indices);restState.geometry.setAttribute('cadTubeMappingIndex',new THREE.BufferAttribute(indices,1));
    let radius=0;for(let j=0;j<mapping.values.length;j+=8)radius=Math.max(radius,Math.hypot(mapping.values[j+1],mapping.values[j+2],mapping.values[j+3]));
    state=record.tubeGpuState={mapping,mappingTexture,radius,active:true,uniforms:{
      cadTubeMappingTexture:{value:mappingTexture},cadTubeFrameTexture:{value:null},cadTubeMappingSize:{value:new THREE.Vector2(width,height)},cadTubeFrameCount:{value:0},cadTubeRestLength:{value:deformation.rest.length},cadTubeGpuEnabled:{value:1},cadTubeGpuParameters:{value:new THREE.Vector3()},cadTubeGpuInverse:{value:inverse.clone()},cadTubeGpuNormalMatrix:{value:new THREE.Matrix3().getNormalMatrix(inverse)}
    }};
  }
  if(!state.cleanupInstalled){restState.geometry.addEventListener('dispose',()=>{state.mappingTexture.dispose();state.frameTexture?.dispose();});state.cleanupInstalled=true;}
  const frames=buildGpuTubeFrames(deformation.path,sample);
  if(!state.frameTexture||state.frameTexture.image.height!==frames.count){state.frameTexture?.dispose();state.frameTexture=new THREE.DataTexture(frames.data,4,frames.count,THREE.RGBAFormat,THREE.FloatType);}
  else state.frameTexture.image.data.set(frames.data);
  state.frameTexture.needsUpdate=true;state.frames=frames;state.active=true;state.cpuKey=null;
  const u=state.uniforms;u.cadTubeFrameTexture.value=state.frameTexture;u.cadTubeFrameCount.value=frames.count;u.cadTubeGpuEnabled.value=1;
  u.cadTubeGpuParameters.value.set(deformation.twistDeg*Math.PI/180,deformation.path.length/deformation.rest.length,0);u.cadTubeGpuInverse.value.copy(inverse);u.cadTubeGpuNormalMatrix.value.getNormalMatrix(inverse);
  syncGpuTubeMaterials(record);
  if(!record.mesh.customDepthMaterial){
    record.mesh.customDepthMaterial=new THREE.MeshDepthMaterial({depthPacking:THREE.RGBADepthPacking});
    record.mesh.customDistanceMaterial=new THREE.MeshDistanceMaterial();
    record.mesh.material.addEventListener('dispose',()=>{record.mesh.customDepthMaterial?.dispose();record.mesh.customDistanceMaterial?.dispose();});
  }
  patchMaterial(record.mesh.customDepthMaterial,u);patchMaterial(record.mesh.customDistanceMaterial,u);
  const box=new THREE.Box3();for(const segment of deformation.path.segments){box.expandByPoint(new THREE.Vector3().fromArray(segment.bounds.min));box.expandByPoint(new THREE.Vector3().fromArray(segment.bounds.max));}
  box.expandByScalar(state.radius+1e-4);record.partBounds={min:box.min.toArray(),max:box.max.toArray()};
  restState.geometry.boundingBox=box.clone().applyMatrix4(inverse);restState.geometry.boundingSphere=restState.geometry.boundingBox.getBoundingSphere(new THREE.Sphere());
  record.mesh.userData.cadTubeBeforeRaycast=(raycaster)=>{
    if(!state.active)return true;
    const localRay=raycaster.ray.clone().applyMatrix4(record.mesh.matrixWorld.clone().invert());
    if(!localRay.intersectsBox(restState.geometry.boundingBox))return false;
    // A one-mm chord capsule with half-arc-length reserve is conservative.
    const worldRay=localRay.clone().applyMatrix4(inverse.clone().invert()),a=new THREE.Vector3(),b=new THREE.Vector3();let near=false;
    const stride=Math.max(1,Math.floor((frames.count-1)/deformation.path.length));
    for(let i=0;i<frames.count-1;i+=stride){const j=Math.min(i+stride,frames.count-1);a.fromArray(frames.data,i*16);b.fromArray(frames.data,j*16);const reserve=state.radius+(j-i)*deformation.path.length/(frames.count-1)/2+1e-4;if(worldRay.distanceSqToSegment(a,b)<=reserve*reserve){near=true;break;}}
    if(!near)return false;
    if(state.cpuKey!==deformation.key){materialize();state.cpuKey=deformation.key;}
    return true;
  };
  return true;
}
