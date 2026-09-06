import assert from 'node:assert/strict';
import { test } from 'node:test';
import * as THREE from 'three';
import { compileTubePath, sampleTubePath, projectTubePath, normalizeTubeDeformation, applyRecordTubeDeformation } from './tubeDeformation.js';
import { evaluateAnimationClip, applyAnimationFrameToEffects } from './animationRuntime.js';
import { applyStepModuleEffectsToRecords, resetStepModuleRecordEffects } from './stepModuleEffects.js';
const line=(a,b)=>({kind:'line',start:a,end:b});
const straight={normal:[0,0,1],segments:[line([0,0,0],[10,0,0])]};
const elbow={normal:[0,0,1],segments:[{kind:'arc',center:[0,5,0],axis:[0,0,1],start:[0,0,0],sweepDeg:90}]};
const near=(a,b,tol=1e-6)=>{assert.equal(a.length,b.length);a.forEach((v,i)=>assert.ok(Math.abs(v-b[i])<tol,`${a} != ${b}`));};
function record(source) {return {partId:'o1',mesh:new THREE.Mesh(source),geometry:source,partBounds:{min:[0,-1,-1],max:[10,1,1]}};}
function fixture() {
  const g=new THREE.BufferGeometry();
  g.setAttribute('position',new THREE.Float32BufferAttribute([0,0,1,5,0,1,10,0,1,5,1,0],3));
  g.setAttribute('normal',new THREE.Float32BufferAttribute([0,0,1,0,0,1,0,0,1,0,1,0],3));
  return g;
}
test('analytic line/arc lengths, tangent joins, signed arcs and nearest points',()=>{
  const path=compileTubePath({normal:[0,0,1],segments:[line([-10,0,0],[0,0,0]),...elbow.segments]});
  assert.ok(Math.abs(path.length-(10+2.5*Math.PI))<1e-12);
  assert.equal(path.minRadius,5);
  near(sampleTubePath(path,path.length).point,[5,5,0]);
  near(sampleTubePath(path,path.length).tangent,[0,1,0]);
  assert.ok(Math.abs(projectTubePath(path,[5,5,2]).distance-path.length)<1e-12);
  const negative=compileTubePath({segments:[{kind:'arc',center:[0,5,0],axis:[0,0,1],start:[0,0,0],sweepDeg:-90}]});
  near(sampleTubePath(negative,negative.length).point,[-5,5,0]);
});
test('continuous STEP mesh deforms in place, retains normals and never mutates shared source',()=>{
  const source=fixture(), first=record(source), other=record(source), saved=source.attributes.position.array.slice();
  const spec=normalizeTubeDeformation({rest:straight,path:elbow});
  applyRecordTubeDeformation(THREE,first,spec);
  near(Array.from(first.geometry.attributes.position.array.slice(0,3)),[0,0,1]);
  near(Array.from(first.geometry.attributes.position.array.slice(6,9)),[5,5,1]);
  near(Array.from(first.geometry.attributes.normal.array.slice(3,6)),[0,0,1]);
  assert.deepEqual(source.attributes.position.array,saved);
  assert.equal(other.mesh.geometry,source);
  const clone=first.geometry;
  applyRecordTubeDeformation(THREE,first,spec);
  assert.equal(first.geometry,clone);
  applyRecordTubeDeformation(THREE,first,null);
  assert.deepEqual(first.geometry.attributes.position.array,saved);
});
test('world-space paths respect an occurrence-local STEP geometry and rigid effects',()=>{
  const source=fixture(), r=record(source);
  r.baseTransform=[1,0,0,100,0,1,0,0,0,0,1,0,0,0,0,1];
  const rest={segments:[line([100,0,0],[110,0,0])],normal:[0,0,1]};
  const path={segments:[line([100,10,0],[110,10,0])],normal:[0,0,1]};
  const clip={duration:1,update(t,m){m.get('rope').deformTube({rest,path}).translate([0,0,5]);}};
  const frame=evaluateAnimationClip(THREE,{parts:[{id:'o1',label:'rope'}]},clip,.5),effects=new Map();
  applyAnimationFrameToEffects(THREE,effects,frame);
  applyStepModuleEffectsToRecords(THREE,[r],effects);
  near(Array.from(r.geometry.attributes.position.array.slice(0,3)),[0,10,1]);
  near(new THREE.Vector3().applyMatrix4(r.effectMatrix).toArray(),[0,0,5]);
  resetStepModuleRecordEffects([r],THREE);
  near(Array.from(r.geometry.attributes.position.array.slice(0,3)),[0,0,1]);
});
test('twist advects authored braid offsets without moving the centerline endpoints',()=>{
  const r=record(fixture());
  applyRecordTubeDeformation(THREE,r,normalizeTubeDeformation({rest:straight,path:straight,twistDeg:90}));
  near(Array.from(r.geometry.attributes.position.array.slice(0,3)),[0,-1,0]);
  near(Array.from(r.geometry.attributes.position.array.slice(6,9)),[10,-1,0]);
  near(Array.from(r.geometry.attributes.normal.array.slice(0,3)),[0,-1,0]);
});
test('seek order has no effect and skipping deformation restores the rest mesh',()=>{
  const r=record(fixture()), mesh={parts:[{id:'o1',label:'rope'}]};
  const clip={duration:1,loop:false,update(t,m){if(t>0)m.get('rope').deformTube({rest:straight,path:elbow,twistDeg:360*t});}};
  const frame=(t)=>{const effects=new Map();applyAnimationFrameToEffects(THREE,effects,evaluateAnimationClip(THREE,mesh,clip,t));applyStepModuleEffectsToRecords(THREE,[r],effects);return r.geometry.attributes.position.array.slice();};
  const expected=frame(.35);frame(.9);frame(.2);assert.deepEqual(frame(.35),expected);
  assert.deepEqual(frame(0),fixture().attributes.position.array);
});
test('cached paths honor reused mutable inputs and unchanged poses leave buffers untouched',()=>{
  const raw=structuredClone(straight),r=record(fixture());
  const first=normalizeTubeDeformation({rest:straight,path:raw});
  applyRecordTubeDeformation(THREE,r,first);
  const version=r.geometry.attributes.position.version;
  applyRecordTubeDeformation(THREE,r,normalizeTubeDeformation({rest:straight,path:structuredClone(raw)}));
  assert.equal(r.geometry.attributes.position.version,version);
  raw.segments[0].end[0]=20;
  const changed=normalizeTubeDeformation({rest:straight,path:raw});
  assert.equal(first.path.length,10);assert.equal(changed.path.length,20);
  applyRecordTubeDeformation(THREE,r,changed);
  near(Array.from(r.geometry.attributes.position.array.slice(6,9)),[20,0,1]);
});
test('Bezier integrates true curve length, provides continuous frames and closest projection',()=>{
  const spec={normal:[0,0,1],segments:[{kind:'bezier',points:[[0,0,0],[10,0,0],[10,10,0],[20,10,0]]}]};
  const path=compileTubePath(spec), middle=sampleTubePath(path,path.length/2);
  near(middle.point,[10,5,0],1e-8);
  near(middle.normal,[0,0,1],1e-9);
  assert.ok(path.length>Math.sqrt(500) && path.length<30);
  assert.ok(Math.abs(projectTubePath(path,[10,5,1]).distance-path.length/2)<1e-6);
  const r=record(fixture());
  applyRecordTubeDeformation(THREE,r,normalizeTubeDeformation({rest:straight,path:spec}));
  near(Array.from(r.geometry.attributes.position.array.slice(3,6)),[10,5,1]);
});
test('conservative projection pruning agrees with exhaustive segments on a multi-turn cubic helix',()=>{
  const segments=[],r=7,k=4/3*Math.tan(Math.PI/8);
  for(let j=0;j<16;j++) {
    const a=j*Math.PI/2,b=a+Math.PI/2,z=j*.2;
    segments.push({kind:'bezier',points:[[r*Math.cos(a),r*Math.sin(a),z],[r*(Math.cos(a)-k*Math.sin(a)),r*(Math.sin(a)+k*Math.cos(a)),z+.2/3],[r*(Math.cos(b)+k*Math.sin(b)),r*(Math.sin(b)-k*Math.cos(b)),z+.4/3],[r*Math.cos(b),r*Math.sin(b),z+.2]]});
  }
  const path=compileTubePath({segments});
  const exhaustive={...path,segments:path.segments.map(s=>({...s,bounds:{min:[-Infinity,-Infinity,-Infinity],max:[Infinity,Infinity,Infinity]}}))};
  for(let j=0;j<81;j++) {
    const frame=sampleTubePath(path,path.length*j/80),p=frame.point.map((v,i)=>v+.3*frame.normal[i]);
    const actual=projectTubePath(path,p),expected=projectTubePath(exhaustive,p);
    assert.ok(Math.abs(actual.distance-expected.distance)<1e-7);
    assert.ok(Math.abs(actual.distanceSq-expected.distanceSq)<1e-10);
  }
});
test('broken centerlines and unknown keys fail loudly rather than drawing plausible wrong ropes',()=>{
  assert.throws(()=>compileTubePath({segments:[line([0,0,0],[1,0,0]),line([2,0,0],[3,0,0])]}),/discontinuity/);
  assert.throws(()=>compileTubePath({segments:[line([0,0,0],[1,0,0]),line([1,0,0],[1,1,0])]}),/tangent-continuous/);
  assert.throws(()=>normalizeTubeDeformation({rest:straight,path:straight,typo:1}),/unknown deformation key/);
  assert.throws(()=>compileTubePath({segments:[{...elbow.segments[0],center:[0,5,1]}]}),/normal plane/);
  assert.throws(()=>compileTubePath({segments:[line([0,0,0],[0,0,0])]}),/nonzero/);
});
test('endpoint-only cylinder tessellation acquires continuous bend rings and remains watertight',()=>{
  const source=new THREE.CylinderGeometry(.2,.2,10,24,1,false);
  source.rotateZ(-Math.PI/2);source.translate(5,0,0);
  const r=record(source);
  r.mesh.userData.faceIds=new Uint32Array(source.index.count/3).fill(42);
  applyRecordTubeDeformation(THREE,r,normalizeTubeDeformation({rest:straight,path:elbow,maxSegmentLength:.5}));
  const g=r.geometry,p=g.attributes.position,edges=new Map(),unique=new Map();
  const id=(i)=>{const key=[p.getX(i),p.getY(i),p.getZ(i)].map((x)=>Math.round(x*1e5)).join(',');if(!unique.has(key))unique.set(key,unique.size);return unique.get(key);};
  const zs=new Set();
  for(let i=0;i<g.index.count;i+=3){
    const indices=[0,1,2].map((k)=>id(g.index.getX(i+k)));
    for(let k=0;k<3;k++){const a=indices[k],b=indices[(k+1)%3],key=[Math.min(a,b),Math.max(a,b)].join(':');edges.set(key,(edges.get(key)||0)+1);}
    assert.equal(r.mesh.userData.faceIds[i/3],42);
  }
  assert.ok(p.count>source.attributes.position.count*5);
  assert.ok([...edges.values()].every((count)=>count===2),'every welded surface edge has two incident triangles');
  let middleFound=false;
  for(let i=0;i<p.count;i++)if(Math.abs(p.getX(i)-5/Math.sqrt(2))<.21 && Math.abs(p.getY(i)-(5-5/Math.sqrt(2)))<.21)middleFound=true;
  assert.ok(middleFound,'the bent tube has a surface at the arc midpoint, not one endpoint chord');
});
test('both ordinary and screen-space edge seams bend with the surface and restore',async()=>{
  const {LineSegmentsGeometry}=await import('three/addons/lines/LineSegmentsGeometry.js');
  const {LineSegments2}=await import('three/addons/lines/LineSegments2.js');
  const ordinary=new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0,0,1),new THREE.Vector3(10,0,1)]));
  const screen=new LineSegments2(new LineSegmentsGeometry().setPositions([0,0,1,10,0,1]));
  for(const edge of [ordinary,screen]) {
    const r=record(fixture());r.edges=edge;
    const source=edge.geometry;
    applyRecordTubeDeformation(THREE,r,normalizeTubeDeformation({rest:straight,path:elbow}));
    const a=edge.geometry.attributes.instanceEnd||edge.geometry.attributes.position;
    assert.ok(a.count>=10);
    near([a.getX(a.count-1),a.getY(a.count-1),a.getZ(a.count-1)],[5,5,1]);
    assert.notEqual(edge.geometry,source);
    applyRecordTubeDeformation(THREE,r,null);
    near([a.getX(a.count-1),a.getY(a.count-1),a.getZ(a.count-1)],[10,0,1]);
  }
});
test('hidden edges defer initialization and acquire the current pose when shown',()=>{
  const edge=new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0,0,1),new THREE.Vector3(10,0,1)]));
  const r=record(fixture());r.edges=edge;edge.visible=false;
  const deformation=normalizeTubeDeformation({rest:straight,path:elbow});
  applyRecordTubeDeformation(THREE,r,deformation);
  assert.equal(edge.tubeLineDeformationState,undefined);
  edge.visible=true;applyRecordTubeDeformation(THREE,r,deformation);
  const p=edge.geometry.attributes.position;
  near([p.getX(p.count-1),p.getY(p.count-1),p.getZ(p.count-1)],[5,5,1]);
});
test('procedural braid keeps exact surface geometry and the original material hooks',()=>{
  const r=record(fixture()),material=new THREE.MeshStandardMaterial({color:0xdd7722});r.mesh.material=material;r.material=material;
  let originalCalled=false;
  material.onBeforeCompile=()=>{originalCalled=true;};
  const plain=normalizeTubeDeformation({rest:straight,path:elbow});
  applyRecordTubeDeformation(THREE,r,plain);
  const positions=r.geometry.attributes.position.array.slice();
  applyRecordTubeDeformation(THREE,r,normalizeTubeDeformation({rest:straight,path:elbow,braid:{pitch:.8,depth:.02,strands:8}}));
  assert.deepEqual(r.geometry.attributes.position.array,positions);
  assert.equal(r.geometry.attributes.cadTubeMaterial.count,r.geometry.attributes.position.count);
  const shader={vertexShader:THREE.ShaderLib.standard.vertexShader,fragmentShader:THREE.ShaderLib.standard.fragmentShader,uniforms:{}};
  material.onBeforeCompile(shader,{});
  assert.ok(originalCalled);
  assert.ok(shader.vertexShader.includes('vCadTubeMaterial = cadTubeMaterial'));
  assert.ok(shader.fragmentShader.includes('cadBraidNormal(-vViewPosition'));
  assert.equal(shader.uniforms.cadBraidEnabled.value,1);
  applyRecordTubeDeformation(THREE,r,plain);
  assert.equal(shader.uniforms.cadBraidEnabled.value,0);
  assert.throws(()=>normalizeTubeDeformation({rest:straight,path:straight,braid:{pitch:.8,depth:.02,strands:3}}),/even strand count/);
});
test('a constant-length tube stays closed with stable volume at all 0.02 bend samples',()=>{
  const source=new THREE.CylinderGeometry(.4,.4,10,32,1,false);source.rotateZ(-Math.PI/2);source.translate(5,0,0);
  const r=record(source),volumes=[];
  for(let step=0;step<=50;step++) {
    const angle=step/50*Math.PI/2;
    const path=step===0?straight:{normal:[0,0,1],segments:[{kind:'arc',start:[0,0,0],center:[0,10/angle,0],axis:[0,0,1],sweepDeg:angle*180/Math.PI}]};
    applyRecordTubeDeformation(THREE,r,normalizeTubeDeformation({rest:straight,path,maxSegmentLength:.25}));
    const g=r.geometry,p=g.attributes.position,a=new THREE.Vector3(),b=new THREE.Vector3(),c=new THREE.Vector3();let volume=0;
    for(let i=0;i<g.index.count;i+=3){a.fromBufferAttribute(p,g.index.getX(i));b.fromBufferAttribute(p,g.index.getX(i+1));c.fromBufferAttribute(p,g.index.getX(i+2));volume+=a.dot(b.cross(c))/6;}
    assert.ok(Number.isFinite(volume)&&volume>0);
    for(const value of g.attributes.normal.array)assert.ok(Number.isFinite(value));
    volumes.push(volume);
  }
  assert.ok(Math.max(...volumes)/Math.min(...volumes)<1.002);
});

test('triangle-local duplicate vertices reuse deformation coordinates without losing hard normals',()=>{
  const source=new THREE.CylinderGeometry(.3,.3,10,16,4,false).toNonIndexed();
  source.rotateZ(-Math.PI/2);source.translate(5,0,0);
  const r=record(source),spec=normalizeTubeDeformation({rest:straight,path:elbow,maxSegmentLength:.5});
  applyRecordTubeDeformation(THREE,r,spec);
  const state=r.tubeDeformationState;
  assert.ok(state.mapping.values.length/8 < state.geometry.attributes.position.count*.8);
  const original=source.attributes.position.array.slice();
  for(const value of state.geometry.attributes.position.array)assert.ok(Number.isFinite(value));
  for(let i=0;i<state.geometry.attributes.normal.count;i++){
    const n=new THREE.Vector3().fromBufferAttribute(state.geometry.attributes.normal,i);
    assert.ok(Math.abs(n.length()-1)<1e-6);
  }
  applyRecordTubeDeformation(THREE,r,null);
  assert.deepEqual(source.attributes.position.array,original);
});

test('an unsplit material-only rest surface retains its original triangle topology',()=>{
  const source=new THREE.CylinderGeometry(.3,.3,10,16,4,false).toNonIndexed();source.rotateZ(-Math.PI/2);source.translate(5,0,0);
  const r=record(source);applyRecordTubeDeformation(THREE,r,normalizeTubeDeformation({rest:straight,path:straight,maxSegmentLength:1000,braid:{pitch:1,depth:.02,strands:8}}));
  assert.equal(r.geometry.attributes.position.count,source.attributes.position.count);
  assert.ok(r.geometry.attributes.cadTubeMaterial);
  assert.equal(r.tubeDeformationState.mapping.indices.length,source.attributes.position.count);
});
