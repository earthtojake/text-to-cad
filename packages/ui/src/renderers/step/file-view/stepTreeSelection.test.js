import assert from 'node:assert/strict';
import test from 'node:test';
import { STEP_MODEL_ROOT_ID } from '@hardcore/core/lib/step/stepTree.js';
import { selectableViewerNodeIdsForExpandedTree } from '../workbench/assemblyIsolation.js';
import {
  collectStepTreeRevealExpansionIds,
  expandedVisibleStepTreeTopologyNodeIds,
  referencesForExpandedStepTree,
  stepTreeTopologyOwnersForSelectors,
} from './stepTreeSelection.js';

const root = { id: 'o1', nodeType: 'assembly', children: [
  { id: 'o1.1', nodeType: 'assembly', children: [
    { id: 'o1.1.1', nodeType: 'part', name: 'Bracket', children: [] },
    { id: 'o1.1.2', nodeType: 'part', children: [] },
  ] },
  { id: 'o1.2', nodeType: 'part', children: [] },
] };

test('only visible expanded leaf parts request topology, never all assembly descendants', () => {
  assert.deepEqual(expandedVisibleStepTreeTopologyNodeIds(root, []), []);
  assert.deepEqual(expandedVisibleStepTreeTopologyNodeIds(root, ['o1.1']), []);
  assert.deepEqual(expandedVisibleStepTreeTopologyNodeIds(root, ['o1.1.1']), []);
  assert.deepEqual(expandedVisibleStepTreeTopologyNodeIds(root, ['o1.1', 'o1.1.1']), ['o1.1.1']);
  assert.deepEqual(expandedVisibleStepTreeTopologyNodeIds(root, ['o1.1', 'o1.1.1', 'o1.2'], {
    hiddenPartIds: ['o1.1.1'],
  }), ['o1.2']);
});

test('isolation starts its own frontier without inheriting collapsed outside ancestors', () => {
  const expanded = ['o1.1.1', 'o1.2'];
  assert.deepEqual(expandedVisibleStepTreeTopologyNodeIds(root, expanded, {
    isolatedNodeIds: ['o1.1.1'],
  }), ['o1.1.1']);
  assert.deepEqual(selectableViewerNodeIdsForExpandedTree(root, [], {
    isolatedNodeIds: ['o1.1.1'],
  }), ['o1.1.1'], 'isolated leaves remain pickable');
  assert.deepEqual(selectableViewerNodeIdsForExpandedTree(root, [], {
    isolatedNodeIds: ['o1.1'],
  }), ['o1.1'], 'collapsing an isolated assembly picks that assembly');
  assert.deepEqual(selectableViewerNodeIdsForExpandedTree(root, ['o1.1'], {
    isolatedNodeIds: ['o1.1'],
  }), ['o1.1.1', 'o1.1.2']);
});

test('sidecar-loaded and collapsed part topology cannot leak into viewport picking', () => {
  const references = [
    { id: 'o1.1.1.f1', partId: 'o1.1.1' },
    { id: 'o1.1.2.f1', partId: 'o1.1.2' },
    { id: 'o1.2.f1', partId: 'o1.2' },
  ];
  assert.deepEqual(referencesForExpandedStepTree(references, ['o1.1.1'], ref => ref.partId), [references[0]]);
  assert.deepEqual(referencesForExpandedStepTree(references, [], ref => ref.partId), []);
});

test('external reference requests reveal an unloaded owner and ancestors without opening siblings', () => {
  assert.deepEqual(stepTreeTopologyOwnersForSelectors(root, ['o1.1.1.f2', 'Bracket.e4']), ['o1.1.1']);
  assert.deepEqual(stepTreeTopologyOwnersForSelectors(root, ['o1.1', 'Bracket']), []);
  assert.deepEqual(collectStepTreeRevealExpansionIds(root, 'o1.1.1', { expandSelf: true }), ['o1', 'o1.1', 'o1.1.1']);
  const single = { id: STEP_MODEL_ROOT_ID, nodeType: 'part', children: [] };
  assert.deepEqual(collectStepTreeRevealExpansionIds(single, STEP_MODEL_ROOT_ID, { expandSelf: true }), [STEP_MODEL_ROOT_ID]);
  assert.deepEqual(stepTreeTopologyOwnersForSelectors(single, ['f2'], { isAssemblyView: false }), [STEP_MODEL_ROOT_ID]);
  assert.deepEqual(expandedVisibleStepTreeTopologyNodeIds(single, [STEP_MODEL_ROOT_ID], { isAssemblyView: false }), [STEP_MODEL_ROOT_ID]);
});
