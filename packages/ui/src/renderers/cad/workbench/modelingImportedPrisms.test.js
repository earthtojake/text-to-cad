import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import { buildModelingTree } from './modelingTree.js';
import { reconstructionRecipe } from './reconstructionRecipe.js';
import { splitShaftReconstruction, transversePrismReconstruction } from './modelingImportedPrisms.js';
const fixture = name => JSON.parse(fs.readFileSync(new URL(`./__tests__/fixtures/${name}.json`, import.meta.url)));
const recognize = name => { const index = fixture(name); return reconstructionRecipe(index, buildModelingTree(index)); };

test('split imported shaft becomes one axial sketch and a full revolution', () => {
  const r = recognize('externalSplitShaft');
  assert.deepEqual(r.steps.map(s => s.kind), ['sketch', 'revolve']);
  assert.equal(r.steps[0].profile.profile.length, 6);
});
test('transverse holes cut a swept bracket in two directions', () => {
  const r = recognize('externalTransverseBracket'), cuts = r.steps.filter(s => s.kind === 'cut');
  assert.equal(cuts.length, 4);
  assert.equal(new Set(cuts.map(c => JSON.stringify(c.direction))).size, 2);
  for (const c of cuts) assert.deepEqual(c.dependsOn, [c.input, c.sketch]);
});
test('stock, recesses, local boss and tangent fillet reconstruct the imported feature sample', () => {
  const r = recognize('externalPocketBoss');
  assert.deepEqual(r.steps.map(s => s.kind), ['sketch','extrude','sketch','cut','sketch','cut','sketch','extrude','add','fillet']);
  assert.equal(r.steps.at(-1).edges.count, 1);
  assert.ok(!/faceOrd|edgeOrd|\.py|brep/i.test(JSON.stringify(r)));
});
test('a missing semicylinder or outward hole wall does not claim a full supported prism', () => {
  const shaft = fixture('externalSplitShaft'); shaft.faces = shaft.faces.filter(f => f.ord !== 3);
  assert.equal(splitShaftReconstruction(shaft.faces, new Map(shaft.edges.map(e => [e.ord, e]))), null);
  const bracket = fixture('externalTransverseBracket'); bracket.faces.find(f => f.surfaceType === 'cylinder').reversed = false;
  assert.equal(transversePrismReconstruction(bracket.faces, new Map(bracket.edges.map(e => [e.ord, e]))), null);
});
