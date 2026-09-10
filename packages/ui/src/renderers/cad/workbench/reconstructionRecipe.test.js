import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import { buildModelingTree } from './modelingTree.js';
import { reconstructionRecipe } from './reconstructionRecipe.js';
const fixture = name => JSON.parse(fs.readFileSync(new URL(`./__tests__/fixtures/${name}.json`, import.meta.url)));

test('recovered boundaries become numerical sketches with actual solid dependencies', () => {
  const index = fixture('annular'), recipe = reconstructionRecipe(index, buildModelingTree(index));
  assert.deepEqual(recipe.steps.map(s => s.kind), ['sketch', 'extrude', 'sketch', 'cut']);
  assert.deepEqual(recipe.steps[3].dependsOn, ['operation-1', 'sketch-2']);
  assert.equal(recipe.steps[0].profile.edges[0].curve.kind, 'circle');
  assert.ok(!JSON.stringify(recipe).includes('faceOrd'));
  assert.ok(!JSON.stringify(recipe).includes('edgeOrd'));
});
test('rotational solids yield an independent axial sketch and full revolve', () => {
  const index = fixture('revolved'), recipe = reconstructionRecipe(index, buildModelingTree(index));
  assert.equal(recipe.steps[0].profile.kind, 'axial');
  assert.equal(recipe.steps[1].angle, Math.PI * 2);
});
test('partial or multiple bodies and unsupported contours are never offered as complete recipes', () => {
  const phone = fixture('phoneCase');
  phone.faces[0].surfaceType = 'bsplinesurface';
  assert.equal(reconstructionRecipe(phone, buildModelingTree(phone)), null);
  const index = fixture('prismatic'), tree = buildModelingTree(index);
  assert.equal(reconstructionRecipe(index, [...tree, ...tree]), null);
  index.edges.forEach(e => { e.curve.kind = 'bspline'; });
  assert.equal(reconstructionRecipe(index, tree), null);
});
