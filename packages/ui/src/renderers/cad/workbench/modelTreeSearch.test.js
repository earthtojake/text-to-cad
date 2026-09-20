import assert from 'node:assert/strict';
import test from 'node:test';

import { buildModelTreeSearchIndex, modelTreeSearchChain, searchModelTree } from './modelTreeSearch.js';

/** The Model tree's `Filter model…` box: what it can find, and in what order. */

const part = (id, label, children = []) => ({ id: `model:${id}`, selectionId: id, kind: 'part', label, children });
const assembly = (id, label, children) => ({ id: `model:${id}`, selectionId: id, kind: 'assembly', label, children });
const feature = (id, kind, label, children = []) => ({ id, kind, label, faces: [1], children });
const tree = [
  assembly('o1', 'Gripper', [
    assembly('o1.1', 'Left finger', [part('o1.1.1', 'M3 Screw'), part('o1.1.2', 'Finger pad')]),
    part('o1.2', 'Motor mount 3', [feature('o1.2/hole:1', 'hole', 'Bore 1', [{ id: 'o1.2/curve', kind: 'curve', label: 'Bore curve' }])]),
  ]),
  part('o2', 'Base/plate'),
  part('o3', 'M3 Screw'),
];
const labels = (query, limit) => searchModelTree(buildModelTreeSearchIndex(tree), query, limit).matches.map(match => `${match.entry.prefix}${match.entry.label}`);

test('indexes every collapsed assembly, part and recognized feature, and never a curve', () => {
  const index = buildModelTreeSearchIndex(tree);
  assert.deepEqual(index.map(entry => entry.label), ['Gripper', 'Left finger', 'M3 Screw', 'Finger pad', 'Motor mount 3', 'Bore 1', 'Base/plate', 'M3 Screw']);
  assert.equal(index[2].prefix, 'Gripper/Left finger/');
  assert.equal(index[2].prefix, index[3].prefix);
});

test('names an entry\'s owners outermost first for availability', () => {
  const index = buildModelTreeSearchIndex(tree);
  assert.deepEqual(modelTreeSearchChain(index, 2).map(node => node.label), ['Gripper', 'Left finger', 'M3 Screw']);
  assert.deepEqual(modelTreeSearchChain(index, 6).map(node => node.label), ['Base/plate']);
});

test('finds a name from a subsequence and keeps repeated instances apart by their owners', () => {
  assert.deepEqual(labels('m3scr'), ['Gripper/Left finger/M3 Screw', 'M3 Screw']);
});

test('ranks the word being typed above letters scattered through a longer name', () => {
  assert.equal(labels('m3')[0], 'Gripper/Left finger/M3 Screw');
  assert.equal(labels('m3').at(-1), 'Gripper/Motor mount 3');
});

test('an owner\'s name narrows a search without returning everything it owns', () => {
  assert.deepEqual(labels('gripper'), ['Gripper']);
  assert.deepEqual(labels('finger m3'), ['Gripper/Left finger/M3 Screw']);
});

test('finds a recognized feature inside its part', () => {
  assert.deepEqual(labels('bore'), ['Gripper/Motor mount 3/Bore 1']);
});

test('a pasted reference names exactly its row first', () => {
  assert.equal(labels('#o1.1.2')[0], 'Gripper/Left finger/Finger pad');
  assert.equal(labels('O1.2')[0], 'Gripper/Motor mount 3');
});

test('highlights index the label, not the path', () => {
  const [match] = searchModelTree(buildModelTreeSearchIndex(tree), 'pad').matches;
  assert.deepEqual(match.indices.map(at => match.entry.label[at]).join(''), 'pad');
});

test('caps the rows and still counts every match', () => {
  const many = Array.from({ length: 500 }, (_, n) => part(`o${n}`, `Washer ${n}`));
  const found = searchModelTree(buildModelTreeSearchIndex(many), 'washer', 200);
  assert.equal(found.matches.length, 200);
  assert.equal(found.total, 500);
  assert.equal(found.matches[0].entry.label, 'Washer 0');
});

test('an empty query matches nothing', () => {
  assert.deepEqual(searchModelTree(buildModelTreeSearchIndex(tree), '  '), { matches: [], total: 0 });
});

test('a row also answers to its other names, behind a name that matches', () => {
  const robot = [{ id: 'link:base', kind: 'link', label: 'base_link', children: [
    { id: 'link:upper_arm', kind: 'link', label: 'upper_arm', searchAliases: ['shoulder_pitch'], children: [] },
    { id: 'link:shoulder_cover', kind: 'link', label: 'shoulder_cover', searchAliases: ['cover_mount'], children: [] },
  ] }];
  const found = searchModelTree(buildModelTreeSearchIndex(robot), 'shoulder');
  assert.deepEqual(found.matches.map(match => match.entry.label), ['shoulder_cover', 'upper_arm']);
  assert.equal(found.matches[0].alias, undefined);
  const { alias, indices } = found.matches[1];
  assert.equal(alias.text, 'shoulder_pitch');
  assert.equal(alias.indices.map(at => alias.text[at]).join(''), 'shoulder');
  assert.deepEqual(indices, []);
});
