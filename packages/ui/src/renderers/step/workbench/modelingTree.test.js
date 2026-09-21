import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import { buildModelingTree, modelingReferenceIds } from './modelingTree.js';
const fixture = name => JSON.parse(fs.readFileSync(new URL(`./__tests__/fixtures/${name}.json`,import.meta.url)));

test('an imported prismatic solid yields an extrusion with a recovered boundary profile',()=>{
  const index=fixture('prismatic'), [body]=buildModelingTree(index);
  assert.equal(body.complete,true);assert.deepEqual(body.children.map(n=>n.kind),['extrude']);
  const profile=body.children[0].children[0];
  assert.equal(profile.kind,'profile');assert.ok(profile.edges.length>=4);
  assert.deepEqual(new Set(body.faces),new Set(index.faces.map(f=>f.ord)));
  assert.ok(profile.children.every(n=>n.kind==='curve' && n.edges.length===1));
});
test('an annular extrusion separates the outside sketch from the cut sketch',()=>{
  const [body]=buildModelingTree(fixture('annular'));
  assert.equal(body.complete,true);assert.deepEqual(body.children.map(n=>n.kind),['extrude','cut']);
  assert.equal(body.children[0].children[0].edges.length,1);
  assert.equal(body.children[1].children[0].edges.length,1);
  assert.notDeepEqual(body.children[0].children[0].edges,body.children[1].children[0].edges);
  assert.equal(new Set(body.children.flatMap(n=>n.faces)).size,body.faces.length);
});
test('a stepped rotational solid yields a closed, measured axial profile',()=>{
  const [body]=buildModelingTree(fixture('revolved')), op=body.children[0];
  assert.equal(body.complete,true);assert.equal(op.kind,'revolve');
  assert.equal(op.reconstruction.profile.length,6);assert.equal(op.children[0].children.length,6);
  assert.deepEqual(new Set(op.faces),new Set(body.faces));
});
test('unsupported mixed surfaces remain partial and group tangent blends without fake chronology',()=>{
  const index=fixture('phoneCase');index.faces[0].surfaceType='bsplinesurface';
  const [body]=buildModelingTree(index);
  assert.equal(body.complete,false);assert.equal(body.label,'Imported body 1');
  assert.equal(body.children.filter(n=>n.kind==='cut').length,3);
  assert.equal(body.children.filter(n=>n.kind==='round').length,5);
  assert.ok(body.children.filter(n=>n.kind==='round').every(n=>n.faces.length===8));
  assert.ok(body.children.at(-1).faces.length>0);
  assert.equal(new Set(body.children.flatMap(n=>n.faces)).size,125);
  assert.equal(body.children.flatMap(n=>n.faces).length,125);
  assert.ok(!body.children.some(n=>['extrude','revolve'].includes(n.kind)));
});
test('volume disagreement, altered contour, unsupported surfaces and disconnected blends do not become complete histories',()=>{
  for(const change of [i=>{i.shapes[0].volume*=1.1;},i=>{i.edges.forEach(e=>{e.length+=1;});},i=>{i.faces[0].surfaceType='bsplinesurface';}]){
    const index=fixture('prismatic');change(index);assert.equal(buildModelingTree(index)[0].complete,false);
  }
  const rev=fixture('revolved');rev.shapes[0].volume*=1.1;assert.equal(buildModelingTree(rev)[0].complete,false);
  const blend=fixture('phoneCase');blend.faces[0].surfaceType='bsplinesurface';blend.edges.forEach(e=>{e.class='sharp';});
  assert.equal(buildModelingTree(blend)[0].children.filter(n=>n.kind==='round').length,0);
});
test('canonical profile edges and feature faces never cross occurrence boundaries or select partial sets',()=>{
  const refs=['o1','o2'].flatMap(o=>['f1','e2'].map(s=>({id:`id:${o}.${s}`,selectorType:s[0]==='f'?'face':'edge',occurrenceId:o,normalizedSelector:`${o}.${s}`})));
  const node={faces:[1],edges:[2]};
  assert.deepEqual(modelingReferenceIds(node,'o2',refs),['id:o2.f1','id:o2.e2']);
  assert.deepEqual(modelingReferenceIds(node,'o2',refs.slice(0,-1)),[]);
  assert.deepEqual(modelingReferenceIds(node,'o2',[...refs,refs.at(-1)]),[]);
});
