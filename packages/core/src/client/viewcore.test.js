import assert from 'node:assert/strict';
import test from 'node:test';
import { fetchXbfElementFacts, fetchXbfPartGroups } from '../lib/xbf/xbfDocument.js';
import { createViewCoreFetch, VIEW_CORE_TESSELLATION, viewCoreStructure, viewCoreTree } from './viewcore.js';

// A core made here, answering as the view core's Worker does (`hosts/web/worker.js`): an assembly of a plate and two
// pegs of one geometry, by the prototypes' indices. A part's "mesh" is no XBM2 buffer: this reads routes, it draws nothing.
const CORE_STRUCTURE = {
  prototypes: [
    { index: 0, key: 'aa11', name: 'plate', color: [1, 0, 0, 1], faceNames: { 1: 'f:plate.top' }, edgeNames: {}, vertexNames: {}, faceColors: {} },
    { index: 1, key: 'bb22', name: 'peg', color: null, faceNames: {}, edgeNames: {}, vertexNames: {}, faceColors: {} },
  ],
  instances: [
    { prototype: 0, path: 'bracket/plate', matrix: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], color: null },
    { prototype: 1, path: 'bracket/pegs/peg', matrix: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 5, 0, 0, 1], color: null },
    { prototype: 1, path: 'bracket/pegs/peg', matrix: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 9, 0, 0, 1], color: null },
  ],
};
const URL_ = 'http://cad.local/api/v1/documents/xbf/doc1';

function fakeCore() {
  const asked = [];
  return {
    asked,
    async call(op, args = {}) {
      asked.push([op, args]);
      const result = {
        structure: () => CORE_STRUCTURE,
        mesh: () => new Uint8Array([88, 66, 77, 50, args.part]),
        fact: () => (args.ordinal > 3 ? (() => { throw new Error('no face 9'); })() : { kind: args.kind, ordinal: args.ordinal, part: args.part }),
        groups: () => ({ faces: { 1: 1 }, edges: {}, part: args.part }),
        elements: () => ({ faces: {}, part: args.part }),
        measure: () => ({ volume: 10 + args.part }),
      }[op]();
      return { result, ms: 1 };
    },
  };
}

test('the tree is rebuilt from the instances\' paths, as the engine walks it', () => {
  assert.deepEqual(viewCoreTree(CORE_STRUCTURE.instances), { name: 'bracket', children: [
    { name: 'plate', prototype: 0, instance: 0 },
    { name: 'pegs', children: [{ name: 'peg', prototype: 1, instance: 1 }, { name: 'peg', prototype: 1, instance: 2 }] },
  ] });
  // One part alone is the tree; several roots hang under the document's name.
  assert.deepEqual(viewCoreTree([{ prototype: 0, path: 'solo' }]), { name: 'solo', prototype: 0, instance: 0 });
  assert.deepEqual(viewCoreTree([{ prototype: 0, path: 'a' }, { prototype: 1, path: 'b/c' }], 'file'),
    { name: 'file', children: [{ name: 'a', prototype: 0, instance: 0 }, { name: 'b', children: [{ name: 'c', prototype: 1, instance: 1 }] }] });
});

test('the structure is the engine\'s: the core\'s prototypes and instances, and what the core does not give made here', () => {
  const found = viewCoreStructure(CORE_STRUCTURE, { id: 'doc1', name: 'model', version: 'v7' });
  assert.equal(found.name, 'bracket');
  assert.equal(found.path, 'doc1');
  assert.equal(found.version, 'v7');
  assert.equal(found.units, 'mm');
  assert.equal(found.tessellation, VIEW_CORE_TESSELLATION);
  assert.deepEqual(found.parameters, []);
  assert.equal(found.prototypes[0].material, null);
  assert.deepEqual(found.prototypes[0].faceMaterials, {});
  assert.deepEqual(found.prototypes[0].faceNames, { 1: 'f:plate.top' });
  assert.equal(found.instances, CORE_STRUCTURE.instances);
  assert.equal('kinematics' in found, false);
});

test('the document\'s routes are answered by the core, a part by its key\'s prototype; anything else by the fallback', async () => {
  const core = fakeCore();
  const passed = [];
  const fallback = async (input) => { passed.push(String(input)); return new Response('{}', { headers: { 'content-type': 'application/json' } }); };
  const fetch = createViewCoreFetch({ core, url: URL_, document: { id: 'doc1', version: 'v7' }, fallback });
  const structure = await (await fetch(`${URL_}/structure`)).json();
  assert.equal(structure.version, 'v7');
  assert.equal(structure.tree.name, 'bracket');
  const part = await fetch(`${URL_}/parts/bb22?tessellation=${VIEW_CORE_TESSELLATION}`);
  assert.deepEqual([...new Uint8Array(await part.arrayBuffer())], [88, 66, 77, 50, 1]);
  assert.equal((await fetch(`${URL_}/parts/bb22?tessellation=0.5-20`)).status, 404);
  assert.equal((await fetch(`${URL_}/parts/zz99`)).status, 404);
  // A pick's facts and groups, read as the viewer reads them.
  const facts = await fetchXbfElementFacts(URL_, 'bb22', 'face', 2, { fetch });
  assert.deepEqual(facts, { kind: 'face', ordinal: 2, part: 1, meshed: null, made_by: null });
  const edge = await fetchXbfElementFacts(URL_, 'aa11', 'edge', 3, { fetch });
  assert.deepEqual(edge, { kind: 'edge', ordinal: 3, part: 0, made_by: null });
  await assert.rejects(fetchXbfElementFacts(URL_, 'aa11', 'face', 9, { fetch }), /404/);
  assert.deepEqual(await fetchXbfPartGroups(URL_, 'aa11', { fetch }), { faces: { 1: 1 }, edges: {}, part: 0 });
  assert.deepEqual(await (await fetch(`${URL_}/measure`)).json(), { aa11: { volume: 10 }, bb22: { volume: 11 } });
  assert.deepEqual(await (await fetch(`${URL_}/parts/aa11/volume`)).json(), { volume: 10 });
  assert.equal((await fetch(`${URL_}/kinematics`)).status, 404);
  // The structure is asked of the core once; a part's mesh once, however often it is read.
  await fetch(`${URL_}/parts/bb22`);
  assert.equal(core.asked.filter(([op]) => op === 'structure').length, 1);
  assert.equal(core.asked.filter(([op]) => op === 'mesh').length, 1);
  // Another document (a preview), the version and the look without static copies: the engine's.
  await fetch('http://cad.local/api/v1/documents/xbf/doc1~preview-x/structure');
  await fetch('http://cad.local/api/v1/documents/doc1/version?after=v7');
  await fetch('http://cad.local/api/v1/look');
  assert.deepEqual(passed, ['http://cad.local/api/v1/documents/xbf/doc1~preview-x/structure',
    'http://cad.local/api/v1/documents/doc1/version?after=v7', 'http://cad.local/api/v1/look']);
  assert.equal(fetch.stats.passthrough.length, 3);
  assert.equal(fetch.stats.parts, 1);
});

test('the look is read from its static copies where it has them', async () => {
  const read = [];
  const fetchStatic = async (url) => { read.push(url); return new Response('look'); };
  const fetch = createViewCoreFetch({ core: fakeCore(), url: URL_, look: { json: '/vc/look.json', environment: '/vc/env.hdr' }, fetch: fetchStatic });
  assert.equal(await (await fetch('http://cad.local/api/v1/look')).text(), 'look');
  await fetch('http://cad.local/api/v1/look/environment');
  assert.deepEqual(read, ['/vc/look.json', '/vc/env.hdr']);
  // No fallback: a route it does not answer is a 404, never a request elsewhere.
  assert.equal((await fetch('http://cad.local/api/v1/documents/other/version')).status, 404);
});
