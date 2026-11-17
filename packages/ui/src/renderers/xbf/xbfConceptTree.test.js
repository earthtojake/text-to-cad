import assert from 'node:assert/strict';
import test from 'node:test';

import { presentXbfTree } from '../../../dist/renderers/xbf/xbfTree.js';
import { xbfPartMenu } from '../../../dist/renderers/xbf/xbfMenus.js';
import { assemblyPartMenuEntries } from '../../../dist/renderers/xbf/xbfMenuItems.js';
import { rowActionsLayout } from '../../../dist/renderers/xbf/XbfPartActions.js';

// A document with an exact part, a part baked from a concept and a part that is a concept, as the Model
// tree, its rows' actions and its menus show them.
const structure = {
  prototypes: [{ key: 'a', name: 'board' }, { key: 'b', name: 'knob', concept: { gsl: '/work/knob.gsl', role: 'baked', digest: 'x' } },
    { key: 'c', name: 'enclosure', concept: { gsl: '/work/enclosure.gsl', role: 'body', digest: 'y' } }],
  instances: [{ prototype: 0, path: 'device/board' }, { prototype: 1, path: 'device/knob' }, { prototype: 2, path: 'device/enclosure' }],
  tree: { name: 'device', children: [{ name: 'board', prototype: 0, instance: 0 }, { name: 'knob', prototype: 1, instance: 1 },
    { name: 'enclosure', prototype: 2, instance: 2 }] }
};
const concepts = [{ id: 'i1', name: 'knob', role: 'baked', representation: 'exact', parameters: [] },
  { id: 'i2', name: 'enclosure', role: 'body', representation: 'concept', parameters: [] }];
const words = entries => entries.map(entry => `${entry.separatorBefore ? '| ' : ''}${entry.label.props.children}`);
const menu = (tree, nodeId, given = concepts) => xbfPartMenu({ tree, nodeId, assembly: true, hiddenIds: [], isolatedIds: [], selectedNodeIds: [],
  expandedIds: [], copyText: '', zoomSelectionAvailable: false, concepts: given });

test("a tree's part says what it is to a concept: the concept itself, baked from one, or neither", () => {
  const tree = presentXbfTree(structure);
  assert.deepEqual(['i0', 'i1', 'i2'].map(id => tree.nodes.get(id).concept), [null, 'baked', 'body']);
});

test("a baked part's menu offers the other ways to show it, and a concept's to make it exact", () => {
  const tree = presentXbfTree(structure);
  const shows = entries => words(entries).filter(word => /Show |Convert/.test(word));
  assert.deepEqual(shows(assemblyPartMenuEntries(menu(tree, 'i0'))), []);
  assert.deepEqual(shows(assemblyPartMenuEntries(menu(tree, 'i1'))), ['| Show concept', 'Show both']);
  const asConcept = concepts.map(concept => (concept.id === 'i1' ? { ...concept, representation: 'concept' } : concept));
  assert.deepEqual(shows(assemblyPartMenuEntries(menu(tree, 'i1', asConcept))), ['| Show exact', 'Show both']);
  assert.deepEqual(shows(assemblyPartMenuEntries(menu(tree, 'i2'))), ['| Convert to B-rep']);
  // A document with no concept read (a field not loaded) offers neither way to show a baked part.
  assert.deepEqual(shows(assemblyPartMenuEntries(menu(tree, 'i1', []))), []);
});

test("a baked part's row has one more action, which stays in view while it is not shown as its exact body", () => {
  const tree = presentXbfTree(structure);
  const controls = shown => ({ isAssemblyView: true, onFocusTreeNode() {}, hiddenPartIds: [], focusedNodeIds: [],
    representationOf: node => (node.concept === 'baked' ? shown : null) });
  assert.deepEqual(rowActionsLayout(tree.nodes.get('i0'), controls('exact')), { shown: false, count: 2 });
  assert.deepEqual(rowActionsLayout(tree.nodes.get('i1'), controls('exact')), { shown: false, count: 3 });
  assert.deepEqual(rowActionsLayout(tree.nodes.get('i1'), controls('both')), { shown: true, count: 3 });
  assert.deepEqual(rowActionsLayout(tree.nodes.get('i2'), controls('exact')), { shown: false, count: 2 });
});
