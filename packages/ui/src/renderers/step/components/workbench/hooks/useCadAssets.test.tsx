import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { createHttpCadResourceProvider, SurfaceResolutionError } from '@text-to-cad/core/client';
import { entryHasMesh, entryHasReferences } from '@text-to-cad/core/lib/entryAssets.js';
import { renderAssetCacheStats } from '@text-to-cad/core/lib/renderAssetClient.js';
import { MESH_INDEX_SCHEMA, createTessellationCache, tessellationPayloadFacts,
  tessellationCacheKey, validateTessellationProbeRow } from '@text-to-cad/core/lib/surf/tessellationCache.js';
import { encodeMeshFixture } from '@text-to-cad/core/lib/surf/testing.js';
import { lodTessellationForLevel } from '@text-to-cad/core/lib/surf/lodPolicy.js';
import { completedPackages } from '../../../render/completedPackageCache.js';
import { lodPayloadRequest } from '../../../render/lodPayloadRequest.js';
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

// A 317-component STEP whose every component has a warm standard entry: its descriptor, served
// by a stubbed fetch, and the encoded entries by tessellation key.
function warmLargeStep() {
  const client = { origin: 'https://cad-assets.test' };
  const model = { ...entry('warm-large-step', 'assembly'), sourceFormat: 'step',
    file: 'warm-large-step.step', url: 'https://cad-assets.test/__cad/asset?file=/warm-large-step&v=one', documentHash: 'document-one' };
  const tessellation = lodTessellationForLevel(1);
  const encoded = new Map();
  const components = {}, occurrences = [];
  for (let i = 0; i < 317; i++) {
    const cid = `c${i}`;
    const surfaceInput = createHash('sha256').update(`317-component-${cid}`).digest('hex');
    const surfaceObject = 'a'.repeat(64);
    const bytes = encodeMeshFixture({
      positions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]),
      normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]),
      indices: new Uint32Array([0, 1, 2]),
      faceRanges: [{ ord: 1, color: null, indexStart: 0, indexCount: 3 }],
      edges: [], bounds: { min: [0, 0, 0], max: [1, 1, 0] }, scale: 1,
    }, { surfaceInput, surfaceObject, tessellation });
    const row = validateTessellationProbeRow({ schemaVersion: MESH_INDEX_SCHEMA,
      object: createHash('sha256').update(bytes).digest('hex'), ...tessellationPayloadFacts(bytes) });
    encoded.set(tessellationCacheKey(surfaceInput, tessellation), { bytes, row });
    components[cid] = { surfaceInput };
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

it('restores all 317 STEP components after remount without a descriptor, SURF or mesh read', async () => {
  const { client, model, encoded, fetch } = warmLargeStep();
  const probe = vi.fn(async keys => keys.map(key => encoded.get(key)?.row || null));
  const bodies = vi.fn(async row => encoded.get(row.tessellationInput)?.bytes.slice() || null);
  const owner = createTessellationCache({ provider: { probeMany: probe, getProbed: bodies } });
  try {
    const session = owner.createSession();
    const first = renderHook(() => assets(model, client, session));
    await act(() => first.result.current.loadMeshForEntry(model));
    expect(first.result.current.error).toBe('');
    expect(first.result.current.meshState.assemblyInteractionReady).toBe(true);
    expect(first.result.current.meshState.meshData.parts).toHaveLength(317);
    expect(first.result.current.lodPackage.components).toHaveLength(317);
    const firstVertices = first.result.current.meshState.meshData.parts[0].sourceMesh.vertices;
    expect(bodies).toHaveBeenCalledTimes(317);
    expect(renderAssetCacheStats().surfLeash.limit).toBe(24);
    expect(renderAssetCacheStats().surfLeash.entries).toBeLessThanOrEqual(24);
    first.unmount();
    session.dispose();
    expect(completedPackages.stats().entries).toBe(1);
    const before = { fetch: fetch.mock.calls.length, probes: probe.mock.calls.length, bodies: bodies.mock.calls.length };
    const reopenSession = owner.createSession();
    const reopen = renderHook(() => assets(model, { ...client }, reopenSession));
    expect(reopen.result.current.meshState.meshData.parts).toHaveLength(317);
    expect(reopen.result.current.meshState.meshData.parts[0].sourceMesh.vertices).toBe(firstVertices);
    expect(reopen.result.current.lodPackage.components).toHaveLength(317);
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
    expect(changed.result.current.lodPackage).toBeNull();
    changed.unmount();
  } finally { owner.dispose(); }
});

// The open itself: where each component probed its cache and read its body alone, a chunk of
// components shares one probe and a batch of them one read, growing from the first publish's eight.
it('opens a warm 317-component STEP with a probe per chunk and its bodies in batches, none read alone', async () => {
  const { client, model, encoded } = warmLargeStep();
  const probe = vi.fn(async keys => keys.map(key => encoded.get(key)?.row || null));
  const single = vi.fn(async row => encoded.get(row.tessellationInput)?.bytes.slice() || null);
  const many = vi.fn(async rows => rows.map(row => encoded.get(row.tessellationInput)?.bytes.slice() || null));
  const owner = createTessellationCache({ provider: { probeMany: probe, getProbed: single, getManyProbed: many } });
  try {
    const opened = renderHook(() => assets(model, client, owner.createSession()));
    await act(() => opened.result.current.loadMeshForEntry(model));
    expect(opened.result.current.error).toBe('');
    expect(opened.result.current.meshState.assemblyInteractionReady).toBe(true);
    expect(opened.result.current.meshState.meshData.parts).toHaveLength(317);
    expect(probe.mock.calls.map(([keys]) => keys.length)).toEqual([8, 16, 32, 64, 128, 69]);
    expect(many.mock.calls.map(([rows]) => rows.length)).toEqual([8, 16, 32, 64, 128, 69]);
    expect(single).not.toHaveBeenCalled();
    expect(viewerMemoryPolicy.snapshot().inFlightBytes).toBe(0);
    opened.unmount();
  } finally { owner.dispose(); }
});

// A load that fails part way leaves its model partly on screen with the failure attached, and the
// viewport's detail scheduler goes on refining what is there. A swap it publishes then must not
// stand the model up as complete: that took the alert away and left "Updating model…" for good.
it('keeps a failed load\'s error, and its model partial, through a detail swap', async () => {
  const { client, model, encoded } = warmLargeStep();
  // One component past the first publishes is cold, and its surface cannot be derived.
  const cold = createHash('sha256').update('317-component-c200').digest('hex');
  const probe = vi.fn(async keys => keys.map(key => (key.startsWith(cold) ? null : encoded.get(key)?.row || null)));
  const many = vi.fn(async rows => rows.map(row => encoded.get(row.tessellationInput)?.bytes.slice() || null));
  const owner = createTessellationCache({ provider: { probeMany: probe, getProbed: vi.fn(), getManyProbed: many } });
  const failing = { ...client, resolveSurfaceComponents: vi.fn(async () => {
    throw new SurfaceResolutionError('artifact request failed: cadgen-daemon: could not start a worker');
  }) };
  try {
    const opened = renderHook(() => assets(model, failing, owner.createSession()));
    await act(() => opened.result.current.loadMeshForEntry(model));
    const failed = opened.result.current.meshState;
    expect(failed.assemblyBackgroundError).toContain('could not start a worker');
    expect(failed.assemblyInteractionReady).toBe(false);
    expect(failed.meshData.missingComponentIds.length).toBeGreaterThan(0);
    const component = opened.result.current.lodPackage.components[0];
    const payload = { meshData: component.meshData, lodRequest: lodPayloadRequest(component, 0) };
    act(() => { void opened.result.current.applyComponentLodBatch([{ cid: component.cid, level: 0, payload }]); });
    const swapped = opened.result.current.meshState;
    expect(swapped.meshData).not.toBe(failed.meshData);
    expect(swapped.assemblyBackgroundError).toBe(failed.assemblyBackgroundError);
    expect(swapped.assemblyBackgroundErrorMeshHash).toBe(failed.assemblyBackgroundErrorMeshHash);
    expect(swapped.assemblyInteractionReady).toBe(false);
    opened.unmount();
  } finally { owner.dispose(); }
});

// A part that opened warm has no SURF URL until a refinement resolves its surface, mid-load as often
// as not. The next progressive publish put the loader's identity back, without it: the refinement's
// payload then failed its own request, and the scheduler parked that as a failed load (the part left
// coarse; a warm reopen of the w16 never reached standard detail, its quality state "error").
it('keeps a surface a refinement resolved through the next progressive publish', async () => {
  const { client, model, encoded } = warmLargeStep();
  const probe = vi.fn(async keys => keys.map(key => encoded.get(key)?.row || null));
  // The first batch of bodies arrives; the second waits until the refinement has resolved.
  const held = [];
  let reads = 0;
  const many = vi.fn(rows => {
    reads += 1;
    const read = () => rows.map(row => encoded.get(row.tessellationInput)?.bytes.slice() || null);
    return reads === 2 ? new Promise(resolve => held.push(() => resolve(read()))) : Promise.resolve(read());
  });
  const owner = createTessellationCache({ provider: { probeMany: probe, getProbed: vi.fn(), getManyProbed: many } });
  const resolving = { ...client, resolveSurfaceComponents: vi.fn(async (_descriptor, requested) => new Map(
    requested.map(({ cid, surfaceInput }) => [cid, { surfaceInput, surfaceObject: 'a'.repeat(64),
      surfUrl: `https://cad-assets.test/__cad/store?surfaceInput=${surfaceInput}`, byteLength: 100,
      selectorsUrl: `https://cad-assets.test/__cad/store?surfaceInput=${surfaceInput}&selectors=1` }]))) };
  try {
    const opened = renderHook(() => assets(model, resolving, owner.createSession()));
    let loading;
    act(() => { loading = opened.result.current.loadMeshForEntry(model); });
    await waitFor(() => expect(opened.result.current.lodPackage?.components).toHaveLength(8));
    await waitFor(() => expect(held).toHaveLength(1));
    const component = opened.result.current.lodPackage.components[0];
    expect(component.selectorsUrl).toBe('');
    // What the viewport's refinement does with an empty URL (`useViewportLod`): resolve, then ask.
    const resolved = await act(() => component.resolveSurface(new AbortController().signal));
    const request = lodPayloadRequest({ ...component, identity: resolved.identity, selectorsUrl: resolved.selectorsUrl }, 0);
    act(() => held.splice(0).forEach(release => release()));
    await waitFor(() => expect(opened.result.current.lodPackage.components.length).toBeGreaterThan(8));
    const payload = { meshData: component.meshData, lodRequest: request };
    expect(opened.result.current.prepareComponentLodPayload(component.cid, 0, payload)).toBe(payload);
    await act(() => loading);
    expect(opened.result.current.meshState.meshData.parts).toHaveLength(317);
    opened.unmount();
  } finally { owner.dispose(); }
});

// A cold component is never tessellated here: the surface request that derives its surface names
// the standard tier, cadgen meshes it there, and the ticket's mesh row is read as a warm component's
// probe row is.
it('has cadgen mesh a cold component in its surface request, then reads that mesh', async () => {
  const { client, model, encoded } = warmLargeStep();
  const cold = new Set(['c3', 'c250'].map(cid => createHash('sha256').update(`317-component-${cid}`).digest('hex')));
  const coldKey = key => [...cold].some(input => key.startsWith(input));
  const probe = vi.fn(async keys => keys.map(key => (coldKey(key) ? null : encoded.get(key)?.row || null)));
  const single = vi.fn(async row => encoded.get(row.tessellationInput)?.bytes.slice() || null);
  const many = vi.fn(async rows => rows.map(row => encoded.get(row.tessellationInput)?.bytes.slice() || null));
  const owner = createTessellationCache({ provider: { probeMany: probe, getProbed: single, getManyProbed: many } });
  const requests = [];
  const meshing = { ...client, resolveSurfaceComponents: vi.fn(async (_descriptor, requested, options) => {
    requests.push({ cids: requested.map(({ cid }) => cid), tessellation: options.tessellation });
    return new Map(requested.map(({ cid, surfaceInput }) => {
      // What cadgen does with the request: meshes the component at that tier and stores it.
      const bytes = encodeMeshFixture({
        positions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]), normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]),
        indices: new Uint32Array([0, 1, 2]),
        faceRanges: [{ ord: 1, color: null, indexStart: 0, indexCount: 3 }],
        edges: [], bounds: { min: [0, 0, 0], max: [1, 1, 0] }, scale: 1,
      }, { surfaceInput, surfaceObject: 'a'.repeat(64), tessellation: options.tessellation });
      const mesh = validateTessellationProbeRow({ schemaVersion: MESH_INDEX_SCHEMA,
        object: createHash('sha256').update(bytes).digest('hex'), ...tessellationPayloadFacts(bytes) });
      encoded.set(mesh.tessellationInput, { bytes, row: mesh });
      return [cid, { surfaceInput, surfaceObject: 'a'.repeat(64), byteLength: 100, mesh,
        surfUrl: `https://cad-assets.test/__cad/store?surfaceInput=${surfaceInput}`,
        selectorsUrl: `https://cad-assets.test/__cad/store?surfaceInput=${surfaceInput}&selectors=1` }];
    }));
  }) };
  try {
    const opened = renderHook(() => assets(model, meshing, owner.createSession()));
    await act(() => opened.result.current.loadMeshForEntry(model));
    expect(opened.result.current.error).toBe('');
    expect(opened.result.current.meshState.meshData.parts).toHaveLength(317);
    // Even a 317-component package opens at the standard level, so that is the tier cadgen was asked for.
    expect(requests.flatMap(({ cids }) => cids).sort()).toEqual(['c250', 'c3']);
    expect(requests.every(({ tessellation }) => tessellationCacheKey('0'.repeat(64), tessellation)
      === tessellationCacheKey('0'.repeat(64), lodTessellationForLevel(1)))).toBe(true);
    // Their bodies were read by the rows the surface request answered, alone.
    expect(single.mock.calls.map(([row]) => row.surfaceInput).sort()).toEqual([...cold].sort());
    opened.unmount();
  } finally { owner.dispose(); }
});

// One component cadgen cannot mesh is that component's failure: the rest of the model is drawn and
// interactive, and its failure is the load's background error, as a load that stopped part-way
// reports one, with the parts it would have drawn. Missing a component, the model is not kept as
// complete: a reopen asks again.
it('draws the rest of a model when cadgen cannot mesh one component, and reports that one', async () => {
  const { client, model, encoded } = warmLargeStep();
  const cold = ['c3', 'c250'].map(cid => createHash('sha256').update(`317-component-${cid}`).digest('hex'));
  const read = row => encoded.get(row.tessellationInput)?.bytes.slice() || null;
  const owner = createTessellationCache({ provider: {
    probeMany: async keys => keys.map(key => (cold.some(input => key.startsWith(input)) ? null : encoded.get(key)?.row || null)),
    getProbed: async row => read(row), getManyProbed: async rows => rows.map(read) } });
  const failure = 'component c250: OCCT did not mesh 1 face(s) of the component: f2';
  const meshing = { ...client, resolveSurfaceComponents: vi.fn(async (_descriptor, requested, options) => {
    const ready = new Map();
    for (const { cid, surfaceInput } of requested) {
      if (cid === 'c250') {
        const error = new SurfaceResolutionError(failure, { cid });
        if (!options.onFailed) throw error;
        options.onFailed(cid, error);
        continue;
      }
      ready.set(cid, { surfaceInput, surfaceObject: 'a'.repeat(64), byteLength: 100,
        mesh: encoded.get(tessellationCacheKey(surfaceInput, options.tessellation)).row,
        surfUrl: `https://cad-assets.test/__cad/store?surfaceInput=${surfaceInput}`,
        selectorsUrl: `https://cad-assets.test/__cad/store?surfaceInput=${surfaceInput}&selectors=1` });
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
  const cold = ['c250'].map(cid => createHash('sha256').update(`317-component-${cid}`).digest('hex'));
  const read = row => encoded.get(row.tessellationInput)?.bytes.slice() || null;
  const owner = createTessellationCache({ provider: {
    probeMany: async keys => keys.map(key => (cold.some(input => key.startsWith(input)) ? null : encoded.get(key)?.row || null)),
    getProbed: async row => read(row), getManyProbed: async rows => rows.map(read) } });
  const meshing = { ...client, resolveSurfaceComponents: vi.fn(async (_descriptor, requested, options) => new Map(
    requested.map(({ cid, surfaceInput }) => {
      // What cadgen stores for it: its first face drawn, its second, which no mesher covered, named.
      const bytes = encodeMeshFixture({
        positions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]), normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]),
        indices: new Uint32Array([0, 1, 2]),
        faceRanges: [{ ord: 1, color: null, indexStart: 0, indexCount: 3 }, { ord: 2, color: null, indexStart: 3, indexCount: 0 }],
        edges: [], bounds: { min: [0, 0, 0], max: [1, 1, 0] }, scale: 1, unmeshedFaces: [2],
      }, { surfaceInput, surfaceObject: 'a'.repeat(64), tessellation: options.tessellation });
      const mesh = validateTessellationProbeRow({ schemaVersion: MESH_INDEX_SCHEMA,
        object: createHash('sha256').update(bytes).digest('hex'), ...tessellationPayloadFacts(bytes) });
      encoded.set(mesh.tessellationInput, { bytes, row: mesh });
      return [cid, { surfaceInput, surfaceObject: 'a'.repeat(64), byteLength: 100, mesh,
        surfUrl: `https://cad-assets.test/__cad/store?surfaceInput=${surfaceInput}`,
        selectorsUrl: `https://cad-assets.test/__cad/store?surfaceInput=${surfaceInput}&selectors=1` }];
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

// The core surf fixtures: a component's SURF, cadgen's standard mesh of it and that mesh's probe row.
function surfFixtures(names: string[]) {
  const dir = path.join(path.dirname(createRequire(import.meta.url).resolve('@text-to-cad/core/lib/surf/container.js')), 'fixtures');
  const manifest = JSON.parse(fs.readFileSync(path.join(dir, 'fixtures.json'), 'utf8'));
  return names.map((name) => {
    const bytes = new Uint8Array(fs.readFileSync(path.join(dir, `${name}.l1.glb`)));
    const row = validateTessellationProbeRow({ schemaVersion: MESH_INDEX_SCHEMA,
      object: createHash('sha256').update(bytes).digest('hex'), ...tessellationPayloadFacts(bytes) });
    return { ...manifest[name], bytes, row, surf: new Uint8Array(fs.readFileSync(path.join(dir, `${name}.surf`))),
      selectors: new Uint8Array(fs.readFileSync(path.join(dir, `${name}.selectors.json`))) };
  });
}

// Topology asked for while a package still loads cold (a part's row restored open before the first
// paint) reaches a part cadgen has not meshed yet: its selectors' read misses, so the part's surface
// request names the level on screen, cadgen meshes it, and the read goes on. A part whose selectors
// still cannot be built is not published, and the next request asks for it again.
it('has cadgen mesh a cold part for its topology, and asks again for a part whose topology failed', async () => {
  const [gear, roller] = surfFixtures(['sun_gear', 'cam_follower_roller']);
  const parts = { c0: gear, c1: roller };
  const occurrences = Object.keys(parts).map((cid, i) => ({ id: `o${i}`, name: cid, component: cid,
    transform: [1, 0, 0, i * 100, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] }));
  const descriptor = { kind: 'assembly-package', viewId: 'cold-view', occurrences,
    components: Object.fromEntries(Object.entries(parts).map(([cid, part]) => [cid, { surfaceInput: part.surfaceInput }])),
    assembly: { root: { id: 'root', nodeType: 'assembly', children: occurrences.map(({ id }) => ({ id, nodeType: 'part', children: [] })) } } };
  const surfUrl = cid => `https://cad-assets.test/__cad/store?surfaceInput=${parts[cid].surfaceInput}`;
  const selectorsUrl = cid => `${surfUrl(cid)}&selectors=1`;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (String(url).includes('assembly.json')) return new Response(JSON.stringify(descriptor));
    const cid = Object.keys(parts).find(key => String(url).includes(parts[key].surfaceInput));
    if (!cid) return new Response(null, { status: 404 });
    // The selector table (what selectors read) or the SURF (what recognition reads).
    const bytes = String(url).includes('selectors=1') ? parts[cid].selectors : parts[cid].surf;
    return new Response(bytes.slice(), { headers: { 'content-length': String(bytes.byteLength) } });
  }));
  // The host's mesh store: empty until cadgen meshes a component in a surface request naming a tier.
  const stored = new Map();
  const read = row => stored.get(row.tessellationInput)?.bytes.slice() || null;
  const owner = createTessellationCache({ provider: {
    probeMany: async keys => keys.map(key => stored.get(key)?.row || null),
    getProbed: async row => read(row), getManyProbed: async rows => rows.map(read) } });
  let meshed;
  const meshing = new Promise(resolve => { meshed = resolve; });
  const unmeshable = new Set();
  const asked = [];
  const client = { origin: 'https://cad-assets.test', resources: createHttpCadResourceProvider(),
    resolveSurfaceComponents: async (_view, requested, options = {}) => {
      asked.push([requested.map(({ cid }) => cid).join(), options.tessellation ? 'mesh' : 'surface']);
      if (options.tessellation) await meshing;
      const failed = options.tessellation ? requested.filter(({ cid }) => unmeshable.has(cid)) : [];
      for (const { cid } of failed) {
        const error = new SurfaceResolutionError(`component ${cid}: OCCT did not mesh 1 face(s)`, { cid });
        if (!options.onFailed) throw error;
        options.onFailed(cid, error);
      }
      return new Map(requested.filter(request => !failed.includes(request)).map(({ cid }) => {
        if (options.tessellation) stored.set(parts[cid].row.tessellationInput, parts[cid]);
        return [cid, { surfaceInput: parts[cid].surfaceInput, surfaceObject: parts[cid].surfaceObject, surfUrl: surfUrl(cid),
          selectorsUrl: selectorsUrl(cid), byteLength: parts[cid].surf.byteLength,
          ...(options.tessellation ? { mesh: parts[cid].row } : {}) }];
      }));
    } };
  const model = { ...entry('cold-step', 'assembly'), sourceFormat: 'step', file: 'cold-step.step',
    url: 'https://cad-assets.test/__cad/asset?file=/cold-step&v=one', documentHash: 'cold-document' };
  // Stable, as the renderer's are: a new identity each render would start a new topology session.
  const references = { entryHasReferences: () => true, buildNormalizedReferenceState: (_entry, _bundle, state) => state };
  const session = owner.createSession();
  const settle = () => new Promise(resolve => setTimeout(resolve, 20));
  try {
    const opened = renderHook(() => useCadAssets({ initialEntry: model, client, tessellationCache: session,
      entryHasMesh, ...references }));
    let loading, topology;
    await act(async () => { loading = opened.result.current.loadMeshForEntry(model); await settle(); });
    await act(async () => { topology = opened.result.current.loadReferencesForEntry(model, ['o0']); await settle(); });
    await act(async () => { meshed(); await loading; await topology; });
    expect(opened.result.current.error).toBe('');
    expect(opened.result.current.meshState.meshData.parts).toHaveLength(2);
    expect(opened.result.current.referenceState.loadedTopologyIds).toEqual(['o0']);
    expect(opened.result.current.referenceState.selectorRuntime).toBeTruthy();
    // The load meshed c0; the topology derived its surface, missed its mesh, and had cadgen mesh it.
    expect(asked.filter(([cids]) => cids === 'c0')).toEqual([['c0', 'mesh'], ['c0', 'surface'], ['c0', 'mesh']]);

    // c1's mesh gone from the store, and cadgen unable to make it again: o1 is not published...
    stored.delete(roller.row.tessellationInput);
    unmeshable.add('c1');
    await act(() => opened.result.current.loadReferencesForEntry(model, ['o0', 'o1']));
    expect(opened.result.current.referenceState.loadedTopologyIds).toEqual(['o0']);
    // ...and asked for again, once cadgen can mesh it, it is.
    unmeshable.delete('c1');
    await act(() => opened.result.current.loadReferencesForEntry(model, ['o0', 'o1']));
    expect(opened.result.current.referenceState.loadedTopologyIds).toEqual(['o0', 'o1']);
    expect(asked.filter(([cids, kind]) => cids === 'c1' && kind === 'mesh')).toHaveLength(3);
    opened.unmount();
  } finally { session.dispose(); owner.dispose(); }
});
