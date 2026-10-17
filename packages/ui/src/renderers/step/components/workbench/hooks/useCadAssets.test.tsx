import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { createHttpCadResourceProvider, PartResolutionError } from '@text-to-cad/core/client';
import { entryHasMesh, entryHasReferences } from '@text-to-cad/core/lib/entryAssets.js';
import { renderAssetCacheStats } from '@text-to-cad/core/lib/renderAssetClient.js';
import { createTessellationCache, partRow } from '@text-to-cad/core/lib/parts/tessellationCache.js';
import { encodeMeshFixture, partMeshFacts, partSelectorFacts } from '@text-to-cad/core/lib/parts/testing.js';
import { completedPackages } from '../../../render/completedPackageCache.js';
import { viewerMemoryPolicy } from '../../../render/viewerMemoryPolicy.js';
import { useCadAssets } from './useCadAssets.js';

const triangle = `solid test
facet normal 0 0 1
outer loop
vertex 0 0 0
vertex 1 0 0
vertex 0 1 0
endloop
endfacet
endsolid test`;

function entry(name: string, kind = 'stl') {
  return { file: `${name}.${kind}`, kind, hash: name, url: `https://cad-assets.test/${name}.${kind}` };
}

let defaultClient = {};
function assets(initialEntry: ReturnType<typeof entry>, client = defaultClient, tessellationCache = {}) {
  client.resources ||= createHttpCadResourceProvider();
  return useCadAssets({ initialEntry, client, tessellationCache,
    entryHasMesh, entryHasReferences,
    buildNormalizedReferenceState: () => null });
}

afterEach(() => {
  cleanup();
  defaultClient = {};
  completedPackages.clear();
  viewerMemoryPolicy.reset();
  vi.unstubAllGlobals();
});

const sha256 = (bytes: Uint8Array | string) => createHash('sha256').update(bytes).digest('hex');
// One triangle, as a part's display mesh.
const TRIANGLE = {
  positions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]),
  normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]),
  indices: new Uint32Array([0, 1, 2]),
  faceRanges: [{ ord: 1, color: null, indexStart: 0, indexCount: 3 }],
  edges: [], bounds: { min: [0, 0, 0], max: [1, 1, 0] },
};
// A selector table, which a part's record names beside its mesh (these loads draw; none reads it).
const TABLE = new TextEncoder().encode(JSON.stringify({ stats: { faceCount: 1, edgeCount: 0, vertexCount: 3 } }));

// A part's row: its key, and the record naming its display mesh and its selector table.
function rowFor(part: string, bytes: Uint8Array, table: Uint8Array) {
  return partRow(part, { glb: { object: sha256(bytes), ...partMeshFacts(bytes) },
    selectors: { object: sha256(table), ...partSelectorFacts(table) } });
}

// A part as cadgen stores it: its display mesh, its selector table and its row.
function storedPart(part: string, mesh = TRIANGLE) {
  const bytes = encodeMeshFixture(mesh, { part });
  return { part, bytes, table: TABLE, row: rowFor(part, bytes, TABLE) };
}

const partOf = (cid: string) => `${sha256(`317-component-${cid}`)}-v1`;

// A 317-component STEP whose every part the store holds: its descriptor, served by a stubbed
// fetch, and each part's stored mesh and row, by its key.
function warmLargeStep() {
  const client = { origin: 'https://cad-assets.test' };
  const model = { ...entry('warm-large-step', 'assembly'), sourceFormat: 'step',
    file: 'warm-large-step.step', url: 'https://cad-assets.test/__cad/asset?file=/warm-large-step&v=one', documentHash: 'document-one' };
  const encoded = new Map();
  const components = {}, occurrences = [];
  for (let i = 0; i < 317; i++) {
    const cid = `c${i}`;
    const stored = storedPart(partOf(cid));
    encoded.set(stored.part, stored);
    components[cid] = { part: stored.part };
    occurrences.push({ id: `o${i}`, name: cid, component: cid,
      transform: [1, 0, 0, i * 2, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] });
  }
  const descriptor = { kind: 'assembly-package', viewId: 'large-step-view', components, occurrences,
    assembly: { root: { id: 'root', nodeType: 'assembly', children: occurrences.map(({ id }) => ({ id, nodeType: 'part', children: [] })) } } };
  const fetch = vi.fn(async (url: string) => {
    expect(url).toContain('assembly.json');
    return new Response(JSON.stringify(descriptor));
  });
  vi.stubGlobal('fetch', fetch);
  return { client, model, encoded, fetch };
}

it('restores all 317 STEP components after remount without a descriptor, probe or mesh read', async () => {
  const { client, model, encoded, fetch } = warmLargeStep();
  const probe = vi.fn(async parts => parts.map(part => encoded.get(part)?.row || null));
  const bodies = vi.fn(async row => encoded.get(row.part)?.bytes.slice() || null);
  const owner = createTessellationCache({ provider: { probeMany: probe, getProbed: bodies } });
  try {
    const session = owner.createSession();
    const first = renderHook(() => assets(model, client, session));
    await act(() => first.result.current.loadMeshForEntry(model));
    expect(first.result.current.error).toBe('');
    expect(first.result.current.meshState.assemblyInteractionReady).toBe(true);
    expect(first.result.current.meshState.meshData.parts).toHaveLength(317);
    const firstVertices = first.result.current.meshState.meshData.parts[0].sourceMesh.vertices;
    expect(bodies).toHaveBeenCalledTimes(317);
    expect(renderAssetCacheStats().partLeash.limit).toBe(24);
    expect(renderAssetCacheStats().partLeash.entries).toBeLessThanOrEqual(24);
    first.unmount();
    session.dispose();
    expect(completedPackages.stats().entries).toBe(1);
    const before = { fetch: fetch.mock.calls.length, probes: probe.mock.calls.length, bodies: bodies.mock.calls.length };
    const reopenSession = owner.createSession();
    const reopen = renderHook(() => assets(model, { ...client }, reopenSession));
    expect(reopen.result.current.meshState.meshData.parts).toHaveLength(317);
    expect(reopen.result.current.meshState.meshData.parts[0].sourceMesh.vertices).toBe(firstVertices);
    expect(reopen.result.current.meshLoadInProgress).toBe(false);
    expect(reopen.result.current.meshLoadProgress).toBeNull();
    await act(() => reopen.result.current.loadMeshForEntry(model));
    expect(fetch).toHaveBeenCalledTimes(before.fetch);
    expect(probe).toHaveBeenCalledTimes(before.probes);
    expect(bodies).toHaveBeenCalledTimes(before.bodies);
    reopen.unmount();
    reopenSession.dispose();
    const changed = renderHook(() => assets({ ...model, hash: 'new-document' }, client, owner.createSession()));
    expect(changed.result.current.meshState).toBeNull();
    changed.unmount();
  } finally { owner.dispose(); }
});

// The open itself: where each component probed its part and read its mesh alone, a chunk of
// components shares one probe and a batch of them one read, growing from the first publish's eight.
it('opens a warm 317-component STEP with a probe per chunk and its bodies in batches, none read alone', async () => {
  const { client, model, encoded } = warmLargeStep();
  const probe = vi.fn(async parts => parts.map(part => encoded.get(part)?.row || null));
  const single = vi.fn(async row => encoded.get(row.part)?.bytes.slice() || null);
  const many = vi.fn(async rows => rows.map(row => encoded.get(row.part)?.bytes.slice() || null));
  const owner = createTessellationCache({ provider: { probeMany: probe, getProbed: single, getManyProbed: many } });
  try {
    const opened = renderHook(() => assets(model, client, owner.createSession()));
    await act(() => opened.result.current.loadMeshForEntry(model));
    expect(opened.result.current.error).toBe('');
    expect(opened.result.current.meshState.assemblyInteractionReady).toBe(true);
    expect(opened.result.current.meshState.meshData.parts).toHaveLength(317);
    expect(probe.mock.calls.map(([parts]) => parts.length)).toEqual([8, 16, 32, 64, 128, 69]);
    expect(many.mock.calls.map(([rows]) => rows.length)).toEqual([8, 16, 32, 64, 128, 69]);
    expect(single).not.toHaveBeenCalled();
    expect(viewerMemoryPolicy.snapshot().inFlightBytes).toBe(0);
    opened.unmount();
  } finally { owner.dispose(); }
});

// A load that fails part way leaves its model partly on screen with the failure attached, never
// stood up as complete.
it('keeps a failed load\'s error, and its model partial', async () => {
  const { client, model, encoded } = warmLargeStep();
  // One part past the first publishes is not stored, and cadgen cannot derive it.
  const cold = partOf('c200');
  const probe = vi.fn(async parts => parts.map(part => (part === cold ? null : encoded.get(part)?.row || null)));
  const many = vi.fn(async rows => rows.map(row => encoded.get(row.part)?.bytes.slice() || null));
  const owner = createTessellationCache({ provider: { probeMany: probe, getProbed: vi.fn(), getManyProbed: many } });
  const failing = { ...client, resolveParts: vi.fn(async () => {
    throw new PartResolutionError('artifact request failed: cadgen-daemon: could not start a worker');
  }) };
  try {
    const opened = renderHook(() => assets(model, failing, owner.createSession()));
    await act(() => opened.result.current.loadMeshForEntry(model));
    const failed = opened.result.current.meshState;
    expect(failed.assemblyBackgroundError).toContain('could not start a worker');
    expect(failed.assemblyInteractionReady).toBe(false);
    expect(failed.meshData.missingComponentIds.length).toBeGreaterThan(0);
    opened.unmount();
  } finally { owner.dispose(); }
});

// A cold part is never meshed here: the request that names it has cadgen derive it, and the record
// it answers is read as a warm part's probe row is.
it('has cadgen derive a part the store lacks in its request, then reads its mesh by the record it answered', async () => {
  const { client, model, encoded } = warmLargeStep();
  // Two parts the store lacks until a request names them.
  const lacking = new Map(['c3', 'c250'].map(cid => [partOf(cid), encoded.get(partOf(cid))]));
  for (const part of lacking.keys()) encoded.delete(part);
  const probe = vi.fn(async parts => parts.map(part => encoded.get(part)?.row || null));
  const single = vi.fn(async row => encoded.get(row.part)?.bytes.slice() || null);
  const many = vi.fn(async rows => rows.map(row => encoded.get(row.part)?.bytes.slice() || null));
  const owner = createTessellationCache({ provider: { probeMany: probe, getProbed: single, getManyProbed: many } });
  const requested = [];
  const deriving = { ...client, resolveParts: vi.fn(async (_descriptor, components) => {
    requested.push(...components);
    // What cadgen does with the request: derives each part and stores it.
    return new Map(components.map(({ cid, part }) => {
      encoded.set(part, lacking.get(part));
      return [cid, encoded.get(part).row];
    }));
  }) };
  try {
    const opened = renderHook(() => assets(model, deriving, owner.createSession()));
    await act(() => opened.result.current.loadMeshForEntry(model));
    expect(opened.result.current.error).toBe('');
    expect(opened.result.current.meshState.meshData.parts).toHaveLength(317);
    // Each asked for by its part alone.
    expect(requested.sort((a, b) => a.cid.localeCompare(b.cid))).toEqual([
      { cid: 'c250', part: partOf('c250') }, { cid: 'c3', part: partOf('c3') }]);
    // Their meshes were read by the records the request answered, alone.
    expect(single.mock.calls.map(([row]) => row.part).sort()).toEqual([...lacking.keys()].sort());
    opened.unmount();
  } finally { owner.dispose(); }
});

// One part cadgen cannot derive is that component's failure: the rest of the model is drawn and
// interactive, and its failure is the load's background error, as a load that stopped part-way
// reports one, with the parts it would have drawn. Missing a component, the model is not kept as
// complete: a reopen asks again.
it('draws the rest of a model when cadgen cannot mesh one component, and reports that one', async () => {
  const { client, model, encoded } = warmLargeStep();
  const cold = ['c3', 'c250'].map(partOf);
  const read = row => encoded.get(row.part)?.bytes.slice() || null;
  const owner = createTessellationCache({ provider: {
    probeMany: async parts => parts.map(part => (cold.includes(part) ? null : encoded.get(part)?.row || null)),
    getProbed: async row => read(row), getManyProbed: async rows => rows.map(read) } });
  const failure = 'component c250: OCCT did not mesh 1 face(s) of the component: f2';
  const meshing = { ...client, resolveParts: vi.fn(async (_descriptor, requested, options) => {
    const ready = new Map();
    for (const { cid, part } of requested) {
      if (cid === 'c250') {
        const error = new PartResolutionError(failure, { cid });
        if (!options.onFailed) throw error;
        options.onFailed(cid, error);
        continue;
      }
      ready.set(cid, encoded.get(part).row);
    }
    return ready;
  }) };
  try {
    const opened = renderHook(() => assets(model, meshing, owner.createSession()));
    await act(() => opened.result.current.loadMeshForEntry(model));
    const state = opened.result.current.meshState;
    expect([opened.result.current.error, opened.result.current.status]).toEqual(['', 'ready']);
    expect(state.meshData.parts).toHaveLength(316);
    expect(state.meshData.missingComponentIds).toEqual(['c250']);
    expect(state.assemblyInteractionReady).toBe(true);
    expect(state.assemblyBackgroundError).toBe(failure);
    // Named as the tree names it, for the viewport's warning.
    expect(state.assemblyFailedParts).toEqual(['c250']);
    opened.unmount();
    expect(completedPackages.stats().entries).toBe(0);
  } finally { owner.dispose(); }
});

// A face no mesher could cover leaves its component drawn without it: the model is whole and
// interactive, with no failure, and names the parts drawn short of a face for the viewport's warning.
it('names the parts drawn without a face cadgen could not mesh', async () => {
  const { client, model, encoded } = warmLargeStep();
  const cold = partOf('c250');
  const read = row => encoded.get(row.part)?.bytes.slice() || null;
  const owner = createTessellationCache({ provider: {
    probeMany: async parts => parts.map(part => (part === cold ? null : encoded.get(part)?.row || null)),
    getProbed: async row => read(row), getManyProbed: async rows => rows.map(read) } });
  const meshing = { ...client, resolveParts: vi.fn(async (_descriptor, requested) => new Map(
    requested.map(({ cid, part }) => {
      // What cadgen stores for it: its first face drawn, its second, which no mesher covered, named.
      encoded.set(part, storedPart(part, { ...TRIANGLE, unmeshedFaces: [2],
        faceRanges: [{ ord: 1, color: null, indexStart: 0, indexCount: 3 }, { ord: 2, color: null, indexStart: 3, indexCount: 0 }] }));
      return [cid, encoded.get(part).row];
    }))) };
  try {
    const opened = renderHook(() => assets(model, meshing, owner.createSession()));
    await act(() => opened.result.current.loadMeshForEntry(model));
    const state = opened.result.current.meshState;
    expect([opened.result.current.error, opened.result.current.status]).toEqual(['', 'ready']);
    expect(state.meshData.parts).toHaveLength(317);
    expect([state.assemblyInteractionReady, state.assemblyBackgroundError, state.assemblyFailedParts]).toEqual([true, '', []]);
    expect(state.assemblyUnmeshedParts).toEqual(['c250']);
    opened.unmount();
  } finally { owner.dispose(); }
});

// The core fixture parts: cadgen's display mesh of each, its selector table and its row.
function fixtureParts(names: string[]) {
  const dir = path.join(path.dirname(createRequire(import.meta.url).resolve('@text-to-cad/core/lib/parts/tessellationCache.js')), 'fixtures');
  const manifest = JSON.parse(fs.readFileSync(path.join(dir, 'fixtures.json'), 'utf8'));
  return names.map((name) => {
    const bytes = new Uint8Array(fs.readFileSync(path.join(dir, `${name}.glb`)));
    const table = new Uint8Array(fs.readFileSync(path.join(dir, `${name}.selectors.json`)));
    return { part: manifest[name].part, bytes, table, row: rowFor(manifest[name].part, bytes, table) };
  });
}

// Topology asked for while a package still loads cold reaches a part not drawn yet: it asks for the
// part's record itself, and reads the part's selector table by it once cadgen has derived it. A part
// the store let go of is asked for again; one whose selectors still cannot be built is not
// published, and the next request asks for it again.
it('reads a cold part\'s topology by the record cadgen derives, and asks again for a part whose topology failed', async () => {
  const [gear, roller] = fixtureParts(['sun_gear', 'cam_follower_roller']);
  const byCid = { c0: gear, c1: roller };
  const occurrences = Object.keys(byCid).map((cid, i) => ({ id: `o${i}`, name: cid, component: cid,
    transform: [1, 0, 0, i * 100, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] }));
  const descriptor = { kind: 'assembly-package', viewId: 'cold-view', occurrences,
    components: Object.fromEntries(Object.entries(byCid).map(([cid, { part }]) => [cid, { part }])),
    assembly: { root: { id: 'root', nodeType: 'assembly', children: occurrences.map(({ id }) => ({ id, nodeType: 'part', children: [] })) } } };
  // The host's part store: empty until cadgen derives a part a request names.
  const stored = new Map();
  const read = row => (stored.get(row.part)?.row.glb.object === row.glb.object ? stored.get(row.part).bytes.slice() : null);
  const owner = createTessellationCache({ provider: {
    probeMany: async parts => parts.map(part => stored.get(part)?.row || null),
    getProbed: async row => read(row), getManyProbed: async rows => rows.map(read) } });
  // The view, and a stored part's selector table, read by its part and the object its record names.
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (String(url).includes('assembly.json')) return new Response(JSON.stringify(descriptor));
    const address = new URL(String(url));
    const named = /^\/__tess_cache\/([^/]+)\.selectors\.json$/.exec(address.pathname);
    const part = named && stored.get(decodeURIComponent(named[1]));
    if (!part || address.searchParams.get('object') !== part.row.selectors.object) return new Response(null, { status: 404 });
    return new Response(part.table.slice(), { headers: { 'content-length': String(part.table.byteLength) } });
  }));
  let derived;
  const deriving = new Promise(resolve => { derived = resolve; });
  const underivable = new Set();
  const asked = [];
  const client = { origin: 'https://cad-assets.test', resources: createHttpCadResourceProvider(),
    resolveParts: async (_view, requested, options = {}) => {
      asked.push(requested.map(({ cid }) => cid).join());
      // cadgen derives what a request names, once the test lets it.
      await deriving;
      const failed = requested.filter(({ cid }) => underivable.has(cid));
      for (const { cid } of failed) {
        const error = new PartResolutionError(`component ${cid}: OCCT did not mesh 1 face(s)`, { cid });
        if (!options.onFailed) throw error;
        options.onFailed(cid, error);
      }
      return new Map(requested.filter(request => !failed.includes(request)).map(({ cid, part }) => {
        const fixture = [gear, roller].find(candidate => candidate.part === part);
        stored.set(part, fixture);
        return [cid, fixture.row];
      }));
    } };
  const model = { ...entry('cold-step', 'assembly'), sourceFormat: 'step', file: 'cold-step.step',
    url: 'https://cad-assets.test/__cad/asset?file=/cold-step&v=one', documentHash: 'cold-document' };
  // Stable, as the renderer's are: a new identity each render would start a new topology session.
  const references = { entryHasReferences: () => true, buildNormalizedReferenceState: (_entry, _bundle, state) => state };
  const session = owner.createSession();
  try {
    const opened = renderHook(() => useCadAssets({ initialEntry: model, client, tessellationCache: session,
      entryHasMesh, ...references }));
    let loading, topology;
    // The load asks for both parts, which cadgen is still deriving...
    await act(async () => { loading = opened.result.current.loadMeshForEntry(model); await vi.waitFor(() => expect(asked).toHaveLength(2)); });
    // ...when topology is asked for: nothing is drawn yet, so it asks for its part itself.
    await act(async () => { topology = opened.result.current.loadReferencesForEntry(model, ['o0']); await vi.waitFor(() => expect(asked).toHaveLength(3)); });
    await act(async () => { derived(); await loading; await topology; });
    expect(opened.result.current.error).toBe('');
    expect(opened.result.current.meshState.meshData.parts).toHaveLength(2);
    expect(opened.result.current.referenceState.loadedTopologyIds).toEqual(['o0']);
    expect(opened.result.current.referenceState.selectorRuntime).toBeTruthy();
    expect([...asked].sort()).toEqual(['c0', 'c0', 'c1']);

    // c1's part gone from the store, and cadgen unable to derive it again: o1 is not published...
    stored.delete(roller.part);
    underivable.add('c1');
    await act(() => opened.result.current.loadReferencesForEntry(model, ['o0', 'o1']));
    expect(opened.result.current.referenceState.loadedTopologyIds).toEqual(['o0']);
    // ...and asked for again, once cadgen can derive it, it is.
    underivable.delete('c1');
    await act(() => opened.result.current.loadReferencesForEntry(model, ['o0', 'o1']));
    expect(opened.result.current.referenceState.loadedTopologyIds).toEqual(['o0', 'o1']);
    expect(asked.filter(cids => cids === 'c1')).toHaveLength(3);
    expect(asked.filter(cids => cids === 'c0')).toHaveLength(2);
    opened.unmount();
  } finally { session.dispose(); owner.dispose(); }
});
