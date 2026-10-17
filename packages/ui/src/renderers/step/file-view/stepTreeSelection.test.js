import assert from 'node:assert/strict';
import test from 'node:test';
import { STEP_MODEL_ROOT_ID } from '@text-to-cad/core/lib/step/stepTree.js';
import { selectableViewerNodeIdsForExpandedTree } from '../workbench/assemblyIsolation.js';
import {
  collectStepTreeRevealExpansionIds,
  expandedVisibleStepTreeTopologyNodeIds,
  referencesForExpandedStepTree,
  stepTreeTopologyOwnersForSelectors,
} from './stepTreeSelection.js';

// The tree's node ids are occurrence tokens (`o:` + 12 hex), as a view's are; an element ref
// is `<occurrence token>/<element name>`.
const ROOT = 'o:1a2b3c4d5e6f';
const SUB = 'o:2b3c4d5e6f70';
const BRACKET = 'o:3f2a9c1d7e5b';
const PIN = 'o:a1b2c3d4e5f6';
const PLATE = 'o:0f1e2d3c4b5a';
const F1 = 'f:bracket.extrude1.3';
const F2 = 'f:bracket.hole1.1';
const E4 = 'e:bracket.fillet1.4';

const root = { id: ROOT, nodeType: 'assembly', children: [
  { id: SUB, nodeType: 'assembly', children: [
    { id: BRACKET, nodeType: 'part', name: 'Bracket', children: [] },
    { id: PIN, nodeType: 'part', children: [] },
  ] },
  { id: PLATE, nodeType: 'part', children: [] },
] };

test('only visible expanded leaf parts request topology, never all assembly descendants', () => {
  assert.deepEqual(expandedVisibleStepTreeTopologyNodeIds(root, []), []);
  assert.deepEqual(expandedVisibleStepTreeTopologyNodeIds(root, [SUB]), []);
  assert.deepEqual(expandedVisibleStepTreeTopologyNodeIds(root, [BRACKET]), []);
  assert.deepEqual(expandedVisibleStepTreeTopologyNodeIds(root, [SUB, BRACKET]), [BRACKET]);
  assert.deepEqual(expandedVisibleStepTreeTopologyNodeIds(root, [SUB, BRACKET, PLATE], {
    hiddenPartIds: [BRACKET],
  }), [PLATE]);
});

test('isolation starts its own frontier without inheriting collapsed outside ancestors', () => {
  const expanded = [BRACKET, PLATE];
  assert.deepEqual(expandedVisibleStepTreeTopologyNodeIds(root, expanded, {
    isolatedNodeIds: [BRACKET],
  }), [BRACKET]);
  assert.deepEqual(selectableViewerNodeIdsForExpandedTree(root, [], {
    isolatedNodeIds: [BRACKET],
  }), [BRACKET], 'isolated leaves remain pickable');
  assert.deepEqual(selectableViewerNodeIdsForExpandedTree(root, [], {
    isolatedNodeIds: [SUB],
  }), [SUB], 'collapsing an isolated assembly picks that assembly');
  assert.deepEqual(selectableViewerNodeIdsForExpandedTree(root, [SUB], {
    isolatedNodeIds: [SUB],
  }), [BRACKET, PIN]);
});

test('sidecar-loaded and collapsed part topology cannot leak into viewport picking', () => {
  const references = [
    { id: `${BRACKET}/${F1}`, partId: BRACKET },
    { id: `${PIN}/${F1}`, partId: PIN },
    { id: `${PLATE}/${F1}`, partId: PLATE },
  ];
  assert.deepEqual(referencesForExpandedStepTree(references, [BRACKET], ref => ref.partId), [references[0]]);
  assert.deepEqual(referencesForExpandedStepTree(references, [], ref => ref.partId), []);
});

test('external reference requests reveal an unloaded owner and ancestors without opening siblings', () => {
  // By token or by label: both name the bracket; an occurrence or a label alone opens nothing.
  assert.deepEqual(stepTreeTopologyOwnersForSelectors(root, [`${BRACKET}/${F2}`, `Bracket/${E4}`]), [BRACKET]);
  assert.deepEqual(stepTreeTopologyOwnersForSelectors(root, [SUB, 'Bracket']), []);
  assert.deepEqual(collectStepTreeRevealExpansionIds(root, BRACKET, { expandSelf: true }), [ROOT, SUB, BRACKET]);
  const single = { id: STEP_MODEL_ROOT_ID, nodeType: 'part', children: [] };
  assert.deepEqual(collectStepTreeRevealExpansionIds(single, STEP_MODEL_ROOT_ID, { expandSelf: true }), [STEP_MODEL_ROOT_ID]);
  // A single-leaf document resolves a bare element name.
  assert.deepEqual(stepTreeTopologyOwnersForSelectors(single, [F2], { isAssemblyView: false }), [STEP_MODEL_ROOT_ID]);
  assert.deepEqual(expandedVisibleStepTreeTopologyNodeIds(single, [STEP_MODEL_ROOT_ID], { isAssemblyView: false }), [STEP_MODEL_ROOT_ID]);
});
