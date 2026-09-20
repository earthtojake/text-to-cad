import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { createHash } from 'node:crypto';
import { createHttpCadResourceProvider } from '@hardcore/core/client';
import { entryHasDisplayEdges, entryHasMesh, entryHasReferences } from '@hardcore/core/lib/entryAssets.js';
import { renderAssetCacheStats } from '@hardcore/core/lib/renderAssetClient.js';
import { createTessellationCache, encodeComponentTessellation, tessellationPayloadFacts,
  tessellationCacheKey, validateTessellationProbeRow } from '@hardcore/core/lib/surf/tessellationCache.js';
import { lodTessellationForLevel } from '@hardcore/core/lib/surf/lodPolicy.js';
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
    entryHasMesh, entryHasReferences, entryHasDisplayEdges,
    buildNormalizedReferenceState: () => null });
}

afterEach(() => {
  cleanup();
  defaultClient = {};
  completedPackages.clear();
  viewerMemoryPolicy.reset();
  vi.unstubAllGlobals();
});

it('restores all 317 STEP components after remount without a descriptor, SURF or TESS read', async () => {
  const client = { workspaceId: 'large-step-root', origin: 'https://cad-assets.test' };
  const model = { ...entry('warm-large-step', 'assembly'), sourceFormat: 'step',
    file: 'warm-large-step.step', url: 'https://cad-assets.test/__cad/asset?file=/warm-large-step&v=one', documentHash: 'document-one' };
  const tessellation = lodTessellationForLevel(1);
  const encoded = new Map();
  const components = {}, occurrences = [];
  for (let i = 0; i < 317; i++) {
    const cid = `c${i}`;
    const surfaceInput = createHash('sha256').update(`317-component-${cid}`).digest('hex');
    const surfaceObject = 'a'.repeat(64);
    const bytes = encodeComponentTessellation({
      positions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]),
      normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]),
      faceOrds: new Float32Array([1, 1, 1]), indices: new Uint32Array([0, 1, 2]),
      sideOrds: new Uint32Array([1, 2, 3]),
      faceRanges: [{ ord: 1, color: null, indexStart: 0, indexCount: 3 }],
      edges: [], bounds: { min: [0, 0, 0], max: [1, 1, 0] }, scale: 1,
    }, { surfaceInput, surfaceObject, tessellation, edgeClasses: [] });
    const row = validateTessellationProbeRow({ schemaVersion: 1,
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

// The one model this hook still loads as a single file is a drawing's prism: a
// triangle mesh and a GLB have their own renderers and never reach it.
const plate = ['0', 'SECTION', '2', 'ENTITIES', '0', 'LWPOLYLINE', '8', 'CUT', '90', '4', '70', '1',
  '10', '0', '20', '0', '10', '10', '20', '0', '10', '10', '20', '10', '10', '0', '20', '10', '0', 'ENDSEC', '0', 'EOF', ''].join('\n');

it('publishes the cached drawing mesh on the first render after A → B → A without a fetch', async () => {
  const fetch = vi.fn(async () => new Response(plate));
  vi.stubGlobal('fetch', fetch);
  const first = entry('warm-a', 'dxf');
  const second = entry('warm-b', 'dxf');
  const a = renderHook(() => assets(first));
  expect(a.result.current.meshState).toBeNull();
  await act(() => a.result.current.loadMeshForEntry(first));
  const mesh = a.result.current.meshState.meshData;
  expect(mesh.vertices.length).toBeGreaterThan(0);
  a.unmount();
  const b = renderHook(() => assets(second));
  await act(() => b.result.current.loadMeshForEntry(second));
  b.unmount();
  const reopen = renderHook(() => assets(first));
  expect(reopen.result.current.meshState.meshData).toBe(mesh);
  expect(reopen.result.current.meshLoadInProgress).toBe(false);
  expect(reopen.result.current.meshLoadProgress).toBeNull();
  expect(fetch).toHaveBeenCalledTimes(2);
  reopen.unmount();
  const changed = renderHook(() => assets({ ...first, hash: 'r2', url: `${first.url}?r2` }));
  expect(changed.result.current.meshState).toBeNull();
  expect(fetch).toHaveBeenCalledTimes(2);
});
