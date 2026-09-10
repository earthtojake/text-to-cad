import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import { buildModelingTree } from './modelingTree.js';
import { reconstructionRecipe } from './reconstructionRecipe.js';
const fixture = name => JSON.parse(fs.readFileSync(new URL(`./__tests__/fixtures/${name}.json`,import.meta.url)));
const recognize = ({index,floats}) => {const tree=buildModelingTree(index,Float32Array.from(floats));return {tree,recipe:reconstructionRecipe(index,tree)};};

test('rounded imported boxes produce a measured extrude and a dependent fillet',()=>{
  const {tree,recipe}=recognize(fixture('roundedBox'));
  assert.deepEqual(recipe.steps.map(s=>s.kind),['sketch','extrude','fillet']);
  assert.equal(recipe.steps[2].radius,1.3);
  assert.deepEqual(recipe.steps[2].dependsOn,['base']);
  assert.equal(tree[0].children[1].faces.length,20);
});
test('ruled cabin reconstructs through four sections despite its spline surface type',()=>{
  const {tree,recipe}=recognize(fixture('ruledCabin'));
  assert.deepEqual(recipe.steps.map(s=>s.kind),['sketch','sketch','sketch','sketch','loft']);
  assert.deepEqual(recipe.steps.at(-1).dependsOn,recipe.steps.slice(0,-1).map(s=>s.id));
  assert.equal(tree[0].children[0].kind,'loft');
  assert.deepEqual(recipe.steps.slice(0,-1).map(s=>s.profile.points[0][0]),[-43,-22,12,38]);
});
test('ruled body reconstructs nine sections and four capped cuts without cutting through its center',()=>{
  const {tree,recipe}=recognize(fixture('ruledBody'));
  const cuts=recipe.steps.filter(s=>s.kind==='cut');
  assert.equal(tree[0].children.length,5);
  assert.equal(recipe.steps.filter(s=>s.kind==='loft')[0].sketches.length,9);
  assert.equal(cuts.length,4);
  for(const cut of cuts){
    const curve=recipe.steps.find(s=>s.id===cut.sketch).profile.edges[0].curve;
    assert.equal(Math.abs(curve.origin[1]),27.5);
    assert.ok(curve.origin[1]*cut.direction[1]>0);
    assert.equal(curve.radius,17);
  }
});
test('unsupported spline degree, rational patches and mismatched blend radii do not get a full recipe',()=>{
  for(const mutate of [s=>s.degU=3,s=>s.weights=[0,4]]){
    const f=fixture('ruledCabin');mutate(f.index.faces.find(f=>f.surface.kind==='nurbs').surface);
    assert.equal(recognize(f).recipe,null);
  }
  const f=fixture('roundedBox');f.index.faces.find(f=>f.surface.kind==='sphere').surface.radius=1.6;
  assert.equal(recognize(f).recipe,null);
});
test('recipe contains coordinates and dependencies, never SURF handles or source references',()=>{
  const {recipe}=recognize(fixture('ruledBody'));
  assert.ok(!/edgeOrd|faceOrd|poles|\.py|brep/i.test(JSON.stringify(recipe)));
});

test('rounded shell discovers separate cavities, boss, slots and blends from connected STEP walls',()=>{
  const index=JSON.parse(fs.readFileSync(new URL('./__tests__/fixtures/phoneCase.json',import.meta.url)));
  const tree=buildModelingTree(index),recipe=reconstructionRecipe(index,tree);
  assert.equal(tree[0].complete,true);
  assert.equal(recipe.steps.filter(s=>s.kind==='add').length,1);
  assert.equal(recipe.steps.filter(s=>s.kind==='cut').length,8);
  assert.equal(recipe.steps.filter(s=>s.kind==='fillet').length,5);
  assert.equal(recipe.steps.length,34);
  assert.ok(recipe.steps.filter(s=>s.kind==='fillet').every(s=>s.edges.count===8));
  assert.ok(!/phone|iphone|camera|\.py|faceOrd|edgeOrd/i.test(JSON.stringify(recipe)));
  // Three nearby slots remain separate; they are not grouped just by radius.
  const tools=recipe.steps.filter(s=>s.kind==='cut').map(s=>recipe.steps.find(t=>t.id===s.tool));
  const sideSlots=tools.filter(s=>s.direction?.[1]>0);
  assert.equal(sideSlots.length,3);
});
