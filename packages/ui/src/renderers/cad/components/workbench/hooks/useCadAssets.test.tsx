import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { entryHasDisplayEdges, entryHasMesh, entryHasReferences } from '@hardcore/core/lib/entryAssets.js';
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

function assets(initialEntry: ReturnType<typeof entry>) {
  return useCadAssets({ initialEntry, client: {}, tessellationCache: {},
    entryHasMesh, entryHasReferences, entryHasDisplayEdges,
    buildNormalizedReferenceState: () => null });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it('publishes the cached mesh on the first render after A → B → A without a fetch', async () => {
  const fetch = vi.fn(async () => new Response(triangle));
  vi.stubGlobal('fetch', fetch);
  const first = entry('warm-a');
  const second = entry('warm-b');
  const a = renderHook(() => assets(first));
  expect(a.result.current.meshState).toBeNull();
  await act(() => a.result.current.loadMeshForEntry(first));
  const mesh = a.result.current.meshState.meshData;
  expect(mesh.vertices.length).toBe(9);
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

it('restores a complete cached robot before any loading effect runs', async () => {
  const robot = entry('warm-robot', 'urdf');
  const fetch = vi.fn(async (url: string) => new Response(url.endsWith('.stl') ? triangle :
    '<robot name="warm"><link name="base"><visual><geometry><mesh filename="warm-robot-link.stl"/></geometry></visual></link></robot>'));
  vi.stubGlobal('fetch', fetch);
  const first = renderHook(() => assets(robot));
  await act(() => first.result.current.loadUrdfForEntry(robot));
  const data = first.result.current.urdfState.urdfData;
  first.unmount();
  const reopen = renderHook(() => assets(robot));
  expect(reopen.result.current.urdfState.urdfData).toBe(data);
  expect(reopen.result.current.urdfState.meshesByUrl.size).toBe(1);
  expect(reopen.result.current.urdfLoadProgress).toBeNull();
  expect(fetch).toHaveBeenCalledTimes(2);
});
