import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import test from 'node:test';
import { fetchXbfElementFacts, fetchXbfPartGroups, xbfDocumentSource } from '../lib/xbf/xbfDocument.js';
import { openViewBundle, viewBundleMemorySource, viewBundleSegment, viewBundleUrlSource, VIEW_BUNDLE_ORIGIN } from './bundle.js';

// A view bundle made here, file by file, as the layout writes one (the engine's documentation, "View bundle"):
// a STEP's two parts, one of them keyed as a STEP's are (a key with `:` in it), each with its buffer and its
// table; the document's structure, measures, mechanism and look. A buffer's bytes are no mesh: this reads
// them, it draws nothing.
const ID = '1024a2f2-2b65-5151-8299-282973f2a9fc';
const TESSELLATION = '0.25-28.5';
const PLATE = 'step-f8f4-0:1:2';
const PEG = '0a1b2c';
const encode = value => new TextEncoder().encode(typeof value === 'string' ? value : JSON.stringify(value));
const table = (name, faces) => ({ faces: Object.fromEntries(faces.map((area, index) => [String(index + 1),
  { kind: 'face', ordinal: index + 1, area, surface: 'plane', name }])), edges: { 1: { kind: 'edge', ordinal: 1, length: 4 } },
vertices: { 1: { kind: 'vertex', ordinal: 1, position: [0, 0, 0] } }, groups: { faces: { 1: 1, 2: 1 }, edges: { 1: 1 } } });
const FILES = {
  'structure.json': encode({ name: 'pair.step', path: 'pair.step', version: 'v1', tessellation: TESSELLATION,
    prototypes: [{ key: PLATE }, { key: PEG }], instances: [{ prototype: 0 }, { prototype: 1 }] }),
  [`parts/step-f8f4-0~3A1~3A2/${TESSELLATION}.xbm`]: new Uint8Array([88, 66, 77, 50, 1, 2, 3]),
  [`parts/${PEG}/${TESSELLATION}.xbm`]: new Uint8Array([88, 66, 77, 50, 4]),
  'parts/step-f8f4-0~3A1~3A2/elements.json': encode(table('plate', [12, 20])),
  [`parts/${PEG}/elements.json`]: encode(table('peg', [3])),
  'measure.json': encode({ [PLATE]: { volume: 240, solids: 1 }, [PEG]: { volume: 12, solids: 1 } }),
  'kinematics.json': encode({ pairs: [] }),
  'look.json': encode({ version: 4, environment: { url: '/api/v1/look/environment', intensity: 0.5 } }),
  'look/environment.hdr': new Uint8Array([35, 63, 82, 65]),
};
function manifestOf(files, document = { id: ID, kind: 'step', name: 'pair.step', version: 'v1' }) {
  const listed = Object.fromEntries(Object.entries(files).map(([path, bytes]) => [path, {
    bytes: bytes.byteLength, sha256: createHash('sha256').update(bytes).digest('hex'),
    type: path.endsWith('.json') ? 'application/json' : 'application/octet-stream' }]));
  return encode({ format: 'view-bundle/1', document, made: { tool: 'cad', release: '0.11.17' }, files: listed });
}
const STEP_BUNDLE = { ...FILES, 'manifest.json': manifestOf(FILES) };

/** The same files on a plain static file server: what it was asked for, by path, and with which cache mode. */
function staticServer(files, base = 'https://files.test/bundles/pair.view/') {
  const asked = [];
  const fetch = async (url, init = {}) => {
    asked.push({ path: url.slice(base.length), cache: init.cache });
    if (!url.startsWith(base) || !Object.hasOwn(files, url.slice(base.length))) return new Response('no', { status: 404 });
    return new Response(files[url.slice(base.length)]);
  };
  return { source: viewBundleUrlSource(base.replace(/\/$/, ''), { fetch }), asked };
}
const SOURCES = {
  'a folder on a static file server': () => staticServer(STEP_BUNDLE),
  'files held in the page': () => ({ source: viewBundleMemorySource(new Map(Object.entries(STEP_BUNDLE))), asked: null }),
};
const bytesOf = async response => new Uint8Array(await response.arrayBuffer());

test('a key is spelled as one path segment as the layout spells it', () => {
  assert.equal(viewBundleSegment('step-0a1b-0:1:2'), 'step-0a1b-0~3A1~3A2');
  assert.equal(viewBundleSegment('0.25-28.5'), '0.25-28.5');
  assert.equal(viewBundleSegment('pé'), 'p~C3~A9');
  for (const name of ['', '.', '..']) assert.throws(() => viewBundleSegment(name), /names no file/);
});

for (const [kind, make] of Object.entries(SOURCES)) {
  test(`an engine document's every read is answered from the bundle, from ${kind}`, async () => {
    const { source, asked } = make();
    const client = await openViewBundle(source);
    // The bundle's one document, by the name it keeps: a file's own name, a model's id.
    assert.equal(client.file, '/pair.step');
    assert.equal((await client.resolveEntry('/pair.step')).id, ID);
    assert.equal(client.entryOf(ID)?.file, '/pair.step');
    await assert.rejects(client.resolveEntry('/elsewhere.step'), error => error.code === 'cad-file-missing');
    assert.equal(client.getSnapshot().entries.length, 1);

    const served = await client.engineDocument('/pair.step');
    assert.equal(served.final, true);
    assert.ok(served.url.startsWith(`${VIEW_BUNDLE_ORIGIN}/api/v1/documents/`), served.url);
    const where = xbfDocumentSource(served.url);
    // The structure and each part's buffer, at the tessellation the structure names, are the bundle's bytes.
    assert.deepEqual(await bytesOf(await served.fetch(`${where.url}/structure`)), STEP_BUNDLE['structure.json']);
    for (const [key, path] of [[PLATE, 'parts/step-f8f4-0~3A1~3A2'], [PEG, `parts/${PEG}`]]) {
      const part = await served.fetch(`${where.url}/parts/${encodeURIComponent(key)}?tessellation=${TESSELLATION}`);
      assert.deepEqual(await bytesOf(part), STEP_BUNDLE[`${path}/${TESSELLATION}.xbm`], key);
    }
    // The look, and its environment where the look names it, by the engine's path.
    assert.deepEqual(await bytesOf(await served.fetch(`${where.base}/api/v1/look`)), STEP_BUNDLE['look.json']);
    assert.deepEqual(await bytesOf(await served.fetch(`${where.base}/api/v1/look/environment`)), STEP_BUNDLE['look/environment.hdr']);
    assert.deepEqual(await (await served.fetch(`${where.url}/kinematics`)).json(), { pairs: [] });
    assert.deepEqual(await (await served.fetch(`${where.url}/parts/${encodeURIComponent(PLATE)}/volume`)).json(), { volume: 240, solids: 1 });

    // One element's facts, as a pick asks for them, and a part's groups, out of the part's one table: each
    // table is read once, however many elements are asked of it.
    const options = { fetch: served.fetch };
    assert.deepEqual(await fetchXbfElementFacts(served.url, PLATE, 'face', 2, options), { kind: 'face', ordinal: 2, area: 20, surface: 'plane', name: 'plate' });
    assert.deepEqual(await fetchXbfElementFacts(served.url, PLATE, 'face', 1, options), { kind: 'face', ordinal: 1, area: 12, surface: 'plane', name: 'plate' });
    assert.deepEqual(await fetchXbfElementFacts(served.url, PLATE, 'edge', 1, options), { kind: 'edge', ordinal: 1, length: 4 });
    assert.deepEqual(await fetchXbfElementFacts(served.url, PEG, 'vertex', 1, options), { kind: 'vertex', ordinal: 1, position: [0, 0, 0] });
    assert.deepEqual(await fetchXbfPartGroups(served.url, PLATE, options), { faces: { 1: 1, 2: 1 }, edges: { 1: 1 } });
    await assert.rejects(fetchXbfElementFacts(served.url, PLATE, 'face', 9, options), error => error.status === 404);
    if (asked) {
      assert.equal(asked.filter(read => read.path === 'parts/step-f8f4-0~3A1~3A2/elements.json').length, 1, JSON.stringify(asked));
      // The root's files are asked of the server again each time; the parts, named by their content, as cached.
      assert.equal(asked.find(read => read.path === 'structure.json').cache, 'no-cache');
      assert.equal(asked.find(read => read.path.endsWith('.xbm')).cache, 'default');
    }

    // What needs an engine has no answer: a next version to wait on, a mesh run, the page's local routes.
    for (const route of [`${where.base}/api/v1/documents/${ID}/version?after=v1`, `${where.url}/parameters`, `${where.base}/api/v1/local/link`]) {
      const answer = await served.fetch(route);
      assert.equal(answer.status, 404, route);
      assert.match((await answer.json()).error, /needs an engine/);
    }
    assert.equal(typeof client.setModelParameters, 'undefined');
    assert.equal(typeof client.previewModelParameters, 'undefined');
    assert.equal(client.exports, undefined);
    client.dispose();
  });
}

test("a mesh file's bytes, a robot's meshes and a drawing are read through the service, from either source", async () => {
  const stl = new Uint8Array([115, 111, 108, 105, 100]);
  const glb = new Uint8Array([103, 108, 84, 70]);
  const robotFiles = { 'structure.json': encode({ schemaVersion: 2, kind: 'urdf', name: 'arm', visuals: [{ id: 'v0', mesh: { format: 'glb', url: 'parts/d6d2.glb' } }] }),
    'parts/d6d2.glb': glb };
  const bundles = {
    stl: { files: { 'source.stl': stl }, document: { id: ID, kind: 'stl', name: 'pair.stl', version: 'abc' } },
    urdf: { files: robotFiles, document: { id: ID, kind: 'urdf', name: 'arm.urdf', version: 'def' } },
    dxf: { files: { 'drawing.json': encode({ schemaVersion: 1, layers: [] }) }, document: { id: ID, kind: 'dxf', name: 'plate.dxf', version: 'g' } },
  };
  for (const [name, { files, document }] of Object.entries(bundles)) {
    const all = { ...files, 'manifest.json': manifestOf(files, document) };
    for (const source of [staticServer(all).source, viewBundleMemorySource(all)]) {
      const client = await openViewBundle(source);
      const entry = await client.resolveEntry(`/${document.name}`);
      if (name === 'stl') {
        // The catalog's row names its bytes by their path in the bundle, which the service's resources read.
        assert.equal(entry.url, 'source.stl');
        assert.deepEqual(new Uint8Array(await client.resources.readBytes(entry.url)), stl);
        assert.equal(await client.resources.byteLength(entry.url), stl.byteLength);
        // A worker is handed its own copy of the bytes: what it detaches is never the next read's.
        const ticket = await client.resources.workerTicket(entry.url);
        assert.equal(ticket.kind, 'bytes');
        structuredClone(ticket.bytes, { transfer: [ticket.bytes] });
        assert.deepEqual(new Uint8Array(await client.resources.readBytes(entry.url)), stl);
        await assert.rejects(client.engineDocument(entry.file), /no engine document/);
      } else if (name === 'urdf') {
        const robot = await client.robot(entry.file);
        assert.deepEqual(new Uint8Array(await client.resources.readBytes(robot.visuals[0].mesh.url)), glb);
        // A file a mesh names beside it is the bundle's own, never another host's.
        assert.equal(client.resources.resolveDependency('parts/d6d2.glb', 'skin.png'), 'parts/skin.png');
        assert.throws(() => client.resources.resolveDependency('parts/d6d2.glb', 'https://elsewhere.test/x.bin'), /only a file beside it/);
      } else {
        assert.deepEqual(await client.drawing(entry.file), { schemaVersion: 1, layers: [] });
      }
      await assert.rejects(client.resources.readBytes('parts/unlisted.glb'), error => error.status === 404);
      client.dispose();
    }
  }
});

test('a model is named by its id, and its parameters are read as a file document\'s', async () => {
  const files = { 'structure.json': FILES['structure.json'] };
  const client = await openViewBundle(viewBundleMemorySource({ ...files,
    'manifest.json': manifestOf(files, { id: ID, kind: 'model', name: 'pair', version: 'v1' }) }));
  assert.equal(client.file, ID);
  assert.deepEqual(await client.resolveEntry(ID), { id: ID, file: ID, name: 'pair', sourcePath: null, kind: 'xbf', sourceFormat: 'model',
    url: '', hash: 'model:v1', bytes: 0 });
  // The document written down, as an .xbf is: a page reads it as a file's.
  assert.equal(xbfDocumentSource((await client.engineDocument(ID)).url).kind, 'xbf');
});

test('what is no bundle this viewer reads, or a file not as its manifest says, is refused saying what', async () => {
  await assert.rejects(openViewBundle(viewBundleMemorySource({})), /no view bundle: it has no manifest\.json/);
  await assert.rejects(openViewBundle(viewBundleMemorySource({ 'manifest.json': encode('{') })), /not JSON/);
  await assert.rejects(openViewBundle(viewBundleMemorySource({ 'manifest.json': encode({ format: 'view-bundle/2', document: {}, files: {} }) })),
    /format is "view-bundle\/2"; this viewer reads view-bundle\/1/);
  await assert.rejects(openViewBundle(viewBundleMemorySource({ 'manifest.json': manifestOf({}, { id: ID, kind: 'kicad_pcb', name: 'b.kicad_pcb', version: '1' }) })),
    /no view bundle of a kicad_pcb/);
  // A file whose size is not what the manifest says: a bundle read while it was written over, said as such.
  const client = await openViewBundle(viewBundleMemorySource({ ...STEP_BUNDLE, 'structure.json': encode('{}') }));
  const served = await client.engineDocument('/pair.step');
  await assert.rejects(served.fetch(`${served.url}/structure`), /structure\.json is 2 bytes; its manifest says \d+/);
});
