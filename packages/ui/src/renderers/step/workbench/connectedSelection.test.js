// Group edges and Group faces over cadgen's own data: the slot's selector table (core's surf
// fixtures, written by cadgen) joined to its stored mesh, composed into a runtime as the
// viewer composes an occurrence, and grown by the graphs StepSurface grows a pick with. The
// sets are the table's chains and tangent groups, decided from the exact BREP.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { createRequire } from 'node:module';

import { buildSelectorRuntime } from '@text-to-cad/core/lib/selectors/runtime.js';
import { joinSelectorTable, parseSelectorTable } from '@text-to-cad/core/lib/surf/selectorTable.js';
import { decodeComponentTessellation } from '@text-to-cad/core/lib/surf/tessellationCache.js';
import { buildEdgeChainGraph } from './edgeChainSelection.js';
import { connectedReferenceIds } from './selectionFilter.js';
import { buildTangentFaceGraph } from './tangentFaceSelection.js';

const FIXTURES = path.join(path.dirname(createRequire(import.meta.url).resolve('@text-to-cad/core/lib/surf/container.js')), 'fixtures');

function slotRuntime() {
  const table = parseSelectorTable(fs.readFileSync(path.join(FIXTURES, 'slot.selectors.json'), 'utf8'));
  const { component } = decodeComponentTessellation(new Uint8Array(fs.readFileSync(path.join(FIXTURES, 'slot.l1.glb'))));
  return buildSelectorRuntime(joinSelectorTable(table, component), { partId: 'o1.1', remapOccurrenceId: 'o1.1', copyCadPath: 'slot.step' });
}

test('a pick of one edge of the slot\'s cap grows to the whole loop: two lines and two arcs', () => {
  const runtime = slotRuntime();
  const references = [...runtime.referenceMap.values()];
  const edges = references.filter(reference => reference.selectorType === 'edge');
  // A line of the top cap: on the plane z = 5, with its bounds flat in z.
  const seed = edges.find(reference => reference.pickData.curveType === 'line'
    && reference.pickData.bbox.min[2] === 5 && reference.pickData.bbox.max[2] === 5);
  assert.ok(seed, 'the top cap has a straight edge');
  const grown = connectedReferenceIds(buildEdgeChainGraph(references), seed.id)
    .map(id => runtime.referenceMap.get(id));
  assert.equal(grown.length, 4);
  assert.deepEqual(grown.map(reference => reference.pickData.curveType).sort(), ['circle', 'circle', 'line', 'line']);
  assert.ok(grown.every(reference => reference.pickData.bbox.min[2] === 5 && reference.pickData.bbox.max[2] === 5), 'the loop lies in the cap');
  assert.ok(grown.every(reference => /^o1\.1\.e\d+$/.test(reference.displaySelector)), 'each ref is cadgen\'s local id under the occurrence');
  // A vertical edge meets the loop at a right angle: it is a chain of its own.
  const vertical = edges.find(reference => reference.pickData.curveType === 'line' && reference.pickData.bbox.max[2] - reference.pickData.bbox.min[2] > 4);
  assert.deepEqual(connectedReferenceIds(buildEdgeChainGraph(references), vertical.id), [vertical.id]);
});

test('a pick of one wall of the slot grows to the four tangent walls and never to a cap', () => {
  const runtime = slotRuntime();
  const references = [...runtime.referenceMap.values()];
  const faces = references.filter(reference => reference.selectorType === 'face');
  const wall = faces.find(reference => reference.pickData.surfaceType === 'cylinder');
  const grown = connectedReferenceIds(buildTangentFaceGraph(references), wall.id).map(id => runtime.referenceMap.get(id));
  assert.equal(grown.length, 4);
  assert.deepEqual(grown.map(reference => reference.pickData.surfaceType).sort(), ['cylinder', 'cylinder', 'plane', 'plane']);
  assert.ok(grown.every(reference => reference.pickData.normal === null || Math.abs(reference.pickData.normal[2]) < 1e-9), 'no cap: a cap\'s normal is along z');
  const cap = faces.find(reference => reference.pickData.normal && reference.pickData.normal[2] > 0.5);
  assert.deepEqual(connectedReferenceIds(buildTangentFaceGraph(references), cap.id), [cap.id]);
});
