import assert from 'node:assert/strict';
import test from 'node:test';
import { fetchXbfElementFacts, fetchXbfPartGroups } from '../lib/xbf/xbfDocument.js';
import { connectViewCoreWorkers, createViewCoreExports, createViewCoreFetch, VIEW_CORE_TESSELLATION, viewCoreStructure } from './viewcore.js';

// A core made here, answering as the view core's Worker does (`hosts/web/worker.js`): an assembly of a plate and two
// pegs of one geometry, by the prototypes' indices. A part's "mesh" is no XBM2 buffer: this reads routes, it draws nothing.
const CORE_STRUCTURE = {
  name: 'bracket',
  units: 'mm',
  tessellation: VIEW_CORE_TESSELLATION,
  prototypes: [
    { index: 0, key: 'aa11', name: 'plate', color: [1, 0, 0, 1], faceNames: { 1: 'f:plate.top' }, edgeNames: {}, vertexNames: {}, faceColors: {} },
    { index: 1, key: 'bb22', name: 'peg', color: null, faceNames: {}, edgeNames: {}, vertexNames: {}, faceColors: {} },
  ],
  instances: [
    { prototype: 0, path: 'bracket/plate', matrix: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], color: null },
    { prototype: 1, path: 'bracket/pegs/peg', matrix: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 5, 0, 0, 1], color: null },
    { prototype: 1, path: 'bracket/pegs/peg', matrix: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 9, 0, 0, 1], color: null },
  ],
  tree: { name: 'bracket', children: [
    { name: 'plate', prototype: 0, instance: 0 },
    { name: 'pegs', children: [{ name: 'peg', prototype: 1, instance: 1 }, { name: 'peg', prototype: 1, instance: 2 }] },
  ] },
  kinematics: { schema: 'cadgen.kinematics/2', name: 'bracket', ground: 0, links: [], pairs: [] },
  parameters: [{ name: 'wall', value: 2, kind: 'float', min: 1, max: 5, step: null, unit: null }],
  closure: null,
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

test('the structure is the core\'s, with where the document lives given by the caller', () => {
  const found = viewCoreStructure(CORE_STRUCTURE, { id: 'doc1', version: 'v7' });
  assert.equal(found.name, 'bracket');
  assert.equal(found.path, 'doc1');
  assert.equal(found.id, 'doc1');
  assert.equal(found.version, 'v7');
  assert.equal(found.units, 'mm');
  assert.equal(found.tessellation, VIEW_CORE_TESSELLATION);
  assert.equal(found.tree, CORE_STRUCTURE.tree);
  assert.equal(found.kinematics, CORE_STRUCTURE.kinematics);
  assert.equal(found.instances, CORE_STRUCTURE.instances);
  // A parameter's writability is the live worker's: read from the document alone, none is writable.
  assert.deepEqual(found.parameters, [{ ...CORE_STRUCTURE.parameters[0], writable: false, reason: 'no_worker', source: null }]);
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
  // The mechanism is the structure's own, as the engine's route answers it.
  assert.deepEqual(await (await fetch(`${URL_}/kinematics`)).json(), CORE_STRUCTURE.kinematics);
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

test('a document read by the core exports by the core, the .xbf as itself, and anything else by the engine', async () => {
  const asked = [];
  const core = { async call(op, args) { asked.push([op, args]); return { result: new TextEncoder().encode(`${args.format} file`), ms: 1 }; } };
  const engine = {
    epoch: async () => 'engine-epoch',
    create: async (request) => ({ id: 'engine-1', state: 'queued', requestId: request.requestId }),
    status: async (id) => ({ id, state: 'ready' }),
    fileUrl: (id) => `/api/v1/exports/${id}/file`,
  };
  const exports = createViewCoreExports({ core, bytes: new Uint8Array([1, 2, 3]), fallback: engine });
  const request = (format) => ({ requestId: `request-${format}-0123456789`, epoch: 'engine-epoch', source: { doc: 'd1', revision: 'v1' }, format });
  const step = await exports.create(request('step'));
  assert.deepEqual([step.state, step.filename, step.bytes], ['ready', 'export.step', 9]);
  assert.deepEqual(asked, [['exportBytes', { format: 'step' }]]);
  assert.equal(await (await fetch(exports.fileUrl(step.id))).text(), 'step file');
  assert.equal((await exports.status(step.id)).state, 'ready');
  const glb = await exports.create(request('threemf'));
  assert.equal(glb.filename, 'export.3mf');
  // The .xbf is the bytes the page read; nothing is asked of the core for it.
  const xbf = await exports.create(request('original'));
  assert.deepEqual([...new Uint8Array(await (await fetch(exports.fileUrl(xbf.id))).arrayBuffer())], [1, 2, 3]);
  assert.equal(asked.length, 2);
  // A DXF the core does not write is the engine's job, read from the engine.
  const dxf = await exports.create(request('dxf'));
  assert.equal(dxf.id, 'engine-1');
  assert.equal(exports.fileUrl('engine-1'), '/api/v1/exports/engine-1/file');
  assert.equal(await exports.epoch(), 'engine-epoch');
  exports.dispose();
  // With no engine, a format the core does not write is refused.
  await assert.rejects(createViewCoreExports({ core }).create(request('dxf')), /writes no dxf/);
});

// A stand-in for the view core's Worker (`hosts/web/worker.js`): it opens a document, meshes a part, and faults on a
// mesh as many times as `faults` says, letting its documents go each time as the worker does when its module faults.
function faultingWorker(faults, log) {
  return class {
    constructor() {
      this.docs = new Set();
      this.next = 1;
      queueMicrotask(() => this.onmessage({ data: { ready: true } }));
    }
    postMessage(message) {
      queueMicrotask(() => this.onmessage({ data: this.answer(message) }));
    }
    answer({ id, op, doc, bytes }) {
      log.push(op);
      if (op === 'init') return { id, ok: true, result: { occt: 'stand-in' } };
      if (op === 'open') {
        if (!bytes?.byteLength) return { id, ok: false, error: 'no bytes' };
        if (faults.open) return { id, ok: false, fault: true, error: 'the view core faulted (unreachable) and was started again' };
        const made = this.next++;
        this.docs.add(made);
        return { id, ok: true, result: { doc: made } };
      }
      if (!this.docs.has(doc)) return { id, ok: false, gone: true, error: `no such doc ${doc}` };
      if (op === 'mesh' && faults.left > 0) {
        faults.left -= 1;
        this.docs.clear();
        return { id, ok: false, fault: true, error: 'the view core faulted (memory access out of bounds) and was started again' };
      }
      return { id, ok: true, result: new Uint8Array([88, 66, 77, 50]), ms: 1 };
    }
    terminate() {}
  };
}


async function workersFaulting(faults, log) {
  const realFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(new Uint8Array([0, 97, 115, 109, 1, 0, 0, 0]));
  try {
    const core = connectViewCoreWorkers({ workerUrl: 'worker.js', wasmUrl: 'core.wasm', bytes: new Uint8Array([1, 2, 3]),
      stem: 'bracket', Worker: faultingWorker(faults, log) });
    await core.ready;
    return core;
  } finally {
    globalThis.fetch = realFetch;
  }
}

test('a request the view core faults on once is asked again of the document opened again, and answered', async () => {
  const log = [];
  const core = await workersFaulting({ left: 1 }, log);
  const reply = await core.call('mesh', { part: 0 });
  assert.deepEqual([...reply.result], [88, 66, 77, 50]);
  assert.deepEqual(log, ['init', 'open', 'mesh', 'open', 'mesh']);
  // And the next request is answered by the document opened again, with no further opening.
  assert.deepEqual([...(await core.call('mesh', { part: 1 })).result], [88, 66, 77, 50]);
  assert.equal(log.filter(op => op === 'open').length, 2);
  core.dispose();
});

test('a request the view core faults on twice is refused as the document being unreadable, without a loop', async () => {
  const log = [];
  const core = await workersFaulting({ left: 99 }, log);
  await assert.rejects(core.call('mesh', { part: 0 }), (error) => error.unreadable === true && /bracket cannot be read in this page/.test(error.message));
  assert.deepEqual(log, ['init', 'open', 'mesh', 'open', 'mesh']);
  // Another request is answered by the document opened again (it is its own request: one more try, no loop).
  assert.deepEqual((await core.call('structure')).result.length, 4);
  assert.deepEqual(log.slice(5), ['open', 'structure']);
  core.dispose();
});

test('a document the view core faults on as it opens is refused as unreadable', async () => {
  const log = [];
  await assert.rejects(workersFaulting({ left: 0, open: true }, log),
    (error) => error.unreadable === true && /faulted on it as it was opened/.test(error.message));
  assert.deepEqual(log, ['init', 'open']);
});

test('a document the worker let go (its module faulted on something else) is opened again and the request answered', async () => {
  const log = [];
  const core = await workersFaulting({ left: 0 }, log);
  core.workers[0].worker.docs.clear();  // as the worker does when its module faults
  assert.deepEqual([...(await core.call('mesh', { part: 0 })).result], [88, 66, 77, 50]);
  assert.deepEqual(log, ['init', 'open', 'mesh', 'open', 'mesh']);
  core.dispose();
});
