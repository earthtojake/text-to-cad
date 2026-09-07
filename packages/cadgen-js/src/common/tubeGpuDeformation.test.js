import assert from 'node:assert/strict';
import {test} from 'node:test';
import * as THREE from 'three';
import {buildGpuTubeFrames} from './tubeGpuDeformation.js';
import {compileTubePath,sampleTubePath,normalizeTubeDeformation,applyRecordTubeDeformation} from './tubeDeformation.js';

test('GPU frame positions stay within one micron of analytic paths at display samples',()=>{
  const paths=[
    {segments:[{kind:'line',start:[0,0,0],end:[40,0,0]}]},
    {segments:[{kind:'arc',center:[0,3.5,0],axis:[0,0,1],start:[0,0,0],sweepDeg:280}]},
    {normal:[0,0,1],segments:[{kind:'bezier',points:[[0,0,0],[20,0,0],[5,25,8],[30,30,20]]}]}
  ];
  for(const raw of paths){
    const path=compileTubePath(raw),{data,count}=buildGpuTubeFrames(path,sampleTubePath);
    for(let i=0;i<=2000;i++){
      const f=i/2000*(count-1),lo=Math.floor(f),hi=Math.min(lo+1,count-1),u=f-lo;
      const expected=sampleTubePath(path,path.length*i/2000);
      const actual=[0,1,2].map(k=>data[lo*16+k]*(1-u)+data[hi*16+k]*u);
      assert.ok(Math.hypot(...actual.map((v,k)=>v-expected.point[k]))<.001);
      const tangent=[0,1,2].map(k=>data[lo*16+4+k]*(1-u)+data[hi*16+4+k]*u);
      assert.ok(Math.hypot(...tangent.map((v,k)=>v-expected.tangent[k]))<.001);
    }
  }
});

test('GPU display preserves source buffers, materializes exact picking, and updates late highlight materials',()=>{
  const source=new THREE.CylinderGeometry(.3,.3,10,16,10,false);source.rotateZ(-Math.PI/2);source.translate(5,0,0);
  const mesh=new THREE.Mesh(source,new THREE.MeshStandardMaterial());mesh.updateMatrixWorld();
  const record={mesh,geometry:source,gpuTubeDeformationAllowed:true,partBounds:{min:[0,-.3,-.3],max:[10,.3,.3]}};
  const rest={normal:[0,0,1],segments:[{kind:'line',start:[0,0,0],end:[10,0,0]}]};
  const path={normal:[0,0,1],segments:[{kind:'arc',center:[0,5,0],axis:[0,0,1],start:[0,0,0],sweepDeg:90}]};
  const spec=normalizeTubeDeformation({rest,path}),saved=source.attributes.position.array.slice();
  applyRecordTubeDeformation(THREE,record,spec);
  assert.ok(record.tubeGpuState.active);assert.ok(mesh.customDepthMaterial.userData.cadGpuTube);
  assert.ok(record.tubeDeformationState.mapping.values instanceof Float32Array);
  assert.equal(record.tubeGpuState.mappingTexture.image.data,record.tubeDeformationState.mapping.values);
  assert.equal(record.geometry.attributes.cadTubeMappingIndex.array,record.tubeDeformationState.mapping.indices);
  assert.equal(record.geometry.attributes.cadTubeMaterial,undefined);
  const away=new THREE.Raycaster(new THREE.Vector3(100,100,100),new THREE.Vector3(0,0,-1));
  assert.equal(mesh.userData.cadTubeBeforeRaycast(away),false);assert.equal(record.tubeGpuState.cpuKey,null);
  const near=new THREE.Raycaster(new THREE.Vector3(3.535,1.465,10),new THREE.Vector3(0,0,-1));
  assert.equal(mesh.userData.cadTubeBeforeRaycast(near),true);assert.equal(record.tubeGpuState.cpuKey,spec.key);
  const cpu={mesh:new THREE.Mesh(source),geometry:source};applyRecordTubeDeformation(THREE,cpu,spec);
  assert.deepEqual(record.geometry.attributes.position.array,cpu.geometry.attributes.position.array);
  assert.deepEqual(source.attributes.position.array,saved);
  record.ghostMesh=new THREE.Mesh(record.geometry,new THREE.MeshBasicMaterial());applyRecordTubeDeformation(THREE,record,spec);
  assert.equal(record.ghostMesh.material.userData.cadGpuTube.uniforms,record.tubeGpuState.uniforms);
  const shader={uniforms:{},vertexShader:'#include <common>\n#include <beginnormal_vertex>\n#include <begin_vertex>'};
  mesh.material.onBeforeCompile(shader);assert.ok(shader.vertexShader.includes('transformed=cadGpuPoint'));assert.ok(shader.uniforms.cadTubeFrameTexture.value);
  applyRecordTubeDeformation(THREE,record,null);assert.equal(record.tubeGpuState.uniforms.cadTubeGpuEnabled.value,0);assert.equal(mesh.userData.cadTubeBeforeRaycast,null);
});
