import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { createCadClient } from '@hardcore/core/client';
import { useModelingRecognition as useRecognition } from './useModelingRecognition.js';
import { useStepModeling as useStepModelingHook } from './useStepModeling.js';
import { completedPackages } from '../render/completedPackageCache.js';
import { entryMeshAssetSignature } from '@hardcore/core/lib/entryAssets.js';
import { completedModelingRecognition, modelingRecognitionKey } from './modelingRecognitionCache.js';
import { installRuntimePackageDescriptor } from '../components/workbench/hooks/packageDescriptorCache.js';

let fixtureClient;
let fixtureOccurrenceIds: string[] = [];
function useModelingRecognition(url, enabled, options = {}) {
  return useRecognition(url, enabled, { client: fixtureClient, requestedOccurrenceIds: fixtureOccurrenceIds, ...options });
}
function useStepModeling(entry, enabled, options = {}) {
  return useStepModelingHook(entry, enabled, { requestedOccurrenceIds: fixtureOccurrenceIds, ...options });
}
class RecognitionWorker {
  static instances: RecognitionWorker[] = [];
  terminate = vi.fn();
  postMessage = vi.fn();
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onerror: (() => void) | null = null;
  constructor() { RecognitionWorker.instances.push(this); }
}
const tree = [{ id: 'feature', label: 'Base extrude', faces: [1], edges: [] }];
let fixture = 0;
function setup() {
  fixtureOccurrenceIds = ['o1', 'o2', 'o3'];
  const version = ++fixture;
  vi.stubGlobal('Worker', RecognitionWorker);
  const document = (name: string, object = 'exact', cid = 'c') => ({
    kind: 'assembly-package', components: {
      [cid]: { surfaceInput: `input-${version}`, surfaceObject: `${object}-${version}`, surf: 'component.surf' },
    }, occurrences: [{ id: name, component: cid }],
  });
  const urls = { a: `https://recognition.test/__cad/store?file=/${version}/a`, b: `https://recognition.test/__cad/store?file=/${version}/b`, c: `https://recognition.test/__cad/store?file=/${version}/c` };
  const fetch = vi.fn(async (url: string) => {
    const file = new URL(url).searchParams.get('file') || '';
    return new Response(JSON.stringify(file.includes('/b/') ? document('o2', 'exact', 'other') : file.includes('/c/') ? document('o3', 'changed') : document('o1')),
      { headers: { 'content-type': 'application/json' } });
  });
  vi.stubGlobal('fetch', fetch);
  fixtureClient = createCadClient();
  return { urls, fetch };
}
async function respond(data: unknown, index: number) {
  await waitFor(() => expect(RecognitionWorker.instances.length).toBeGreaterThan(index));
  await act(async () => { RecognitionWorker.instances[index].onmessage?.({ data }); });
}
afterEach(() => { cleanup(); completedPackages.clear(); vi.restoreAllMocks(); vi.unstubAllGlobals(); RecognitionWorker.instances = []; });

function acceptedPackage(count = 1) {
  const { urls, fetch } = setup();
  const digest = (value: number) => (fixture * 10000 + value).toString(16).padStart(64, '0');
  const components = {}, identities = {}, meshes = {}, levels = {}, occurrences = [];
  for (let i = 0; i < count; i++) {
    const cid = `c${i}`, surfaceInput = digest(i), surfaceObject = digest(1000 + i);
    components[cid] = { surfaceInput };
    identities[cid] = { surfaceInput, surfaceObject };
    levels[cid] = 1;
    meshes[cid] = { vertices: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]),
      normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]), indices: new Uint32Array([0, 1, 2]),
      bounds: { min: [0, 0, 0], max: [1, 1, 0] }, lodLevel: 1,
      parts: [{ id: 'part', triangleOffset: 0, triangleCount: 1 }] };
    occurrences.push({ id: `o${i}`, component: cid });
    expect(completedModelingRecognition.set(modelingRecognitionKey(identities[cid], "", {resources:fixtureClient.resources}), { tree })).toBe(true);
  }
  const descriptor = { kind: 'assembly-package', tree: digest(2000), viewId: digest(2001),
    surfaceProducer: { kind: 'fixture' }, components, occurrences };
  fixtureOccurrenceIds = occurrences.flatMap(row => [row.id, `b-${row.id}`]);
  fetch.mockImplementation(async () => new Response(JSON.stringify(descriptor)));
  const entry = { file: 'assembly.step', kind: 'assembly', sourceFormat: 'step', hash: `file-${fixture}`,
    documentHash: `document-${fixture}`, url: urls.a };
  const context = { descriptor, runtimeDescriptor: descriptor, componentMeshDataByCid: meshes,
    componentIdentityByCid: identities, componentLodLevelByCid: levels,
    meshHash: entryMeshAssetSignature(entry), complete: true };
  const client = Object.assign(fixtureClient, { requestSurfaces: vi.fn(async request => ({
    viewId: request.viewId, components: Object.fromEntries(request.components.map(({ cid, surfaceInput }) => {
      const surfaceObject = identities[cid].surfaceObject;
      return [cid, { state: 'ready', surfaceInput, surfaceObject, byteLength: 64,
        url: `/__cad/store?tree=${request.tree}&surfaceInput=${surfaceInput}&object=${surfaceObject}` }];
    })),
  })) });
  expect(completedPackages.set(client, entry, context)).toBe(true);
  return { client, entry, context, descriptor, identities, urls, fetch, digest };
}

it('reuses all 317 accepted component identities through A → B → A without surface requests, workers or geometry cloning', async () => {
  const { client, entry, context, descriptor, urls, fetch } = acceptedPackage(317);
  const b = { ...entry, file: 'b.step', hash: 'file-b', url: urls.b };
  const bDescriptor = { ...descriptor, occurrences: descriptor.occurrences.map(row => ({ ...row, id: `b-${row.id}` })) };
  expect(completedPackages.set(client, b, { ...context, descriptor: bDescriptor, runtimeDescriptor: bDescriptor,
    meshHash: entryMeshAssetSignature(b) })).toBe(true);
  fetch.mockImplementation(async url => new Response(JSON.stringify(
    new URL(url).searchParams.get('file')?.includes('/b/') ? bDescriptor : descriptor)));
  const identityReads = vi.spyOn(completedPackages, 'peekComponentIdentities');
  const geometryReads = vi.spyOn(completedPackages, 'get');
  for (const model of [entry, b, entry]) {
    const view = renderHook(() => useStepModeling(model, true, { client }));
    await waitFor(() => expect(Object.keys(view.result.current.results)).toHaveLength(317));
    expect(view.result.current.results.c316.tree).toEqual(tree);
    expect(view.result.current.descriptor.occurrences[0].id).toBe(model === b ? 'b-o0' : 'o0');
    expect(view.result.current.error).toBe('');
    view.unmount();
  }
  expect(identityReads).toHaveBeenCalledTimes(3);
  expect(geometryReads).not.toHaveBeenCalled();
  expect(client.requestSurfaces).not.toHaveBeenCalled();
  expect(RecognitionWorker.instances).toHaveLength(0);
  expect(fetch).toHaveBeenCalledTimes(2);
});

it('resolves identities again after a same-URL entry revision or runtime view changes', async () => {
  const { client, entry, context, descriptor, digest } = acceptedPackage();
  const view = renderHook(({ model }) => useStepModeling(model, true, { client }), { initialProps: { model: entry } });
  await waitFor(() => expect(view.result.current.results.c0?.tree).toEqual(tree));
  expect(client.requestSurfaces).not.toHaveBeenCalled();
  view.rerender({ model: { ...entry, hash: 'changed-with-same-url' } });
  await waitFor(() => expect(client.requestSurfaces).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(view.result.current.results.c0?.tree).toEqual(tree));
  view.unmount();
  expect(completedPackages.set(client, entry, context)).toBe(true);
  const replacement = { ...descriptor, viewId: digest(2002) };
  installRuntimePackageDescriptor(entry.url, replacement, { resources: client.resources });
  const reopened = renderHook(() => useStepModeling(entry, true, { client }));
  await waitFor(() => expect(reopened.result.current.results.c0?.tree).toEqual(tree));
  expect(client.requestSurfaces).toHaveBeenCalledTimes(2);
  expect(client.requestSurfaces.mock.calls[1][0].viewId).toBe(replacement.viewId);
  expect(RecognitionWorker.instances).toHaveLength(0);
});

it('resolves and recognizes again when a result exceeds the unchanged metadata budget', async () => {
  const { client, entry, identities } = acceptedPackage();
  const oversized = { tree: [{ ...tree[0], label: 'x'.repeat(4 * 1024 * 1024) }] };
  expect(completedModelingRecognition.set(modelingRecognitionKey(identities.c0, "", {resources:client.resources}), oversized)).toBe(false);
  const first = renderHook(() => useStepModeling(entry, true, { client }));
  await respond({ tree }, 0);
  expect(first.result.current.results.c0.tree).toEqual(tree);
  expect(client.requestSurfaces).toHaveBeenCalledTimes(1);
  expect(RecognitionWorker.instances[0].postMessage.mock.calls[0][0].resource.url).toContain(`object=${identities.c0.surfaceObject}`);
  first.unmount();
  const reopen = renderHook(() => useStepModeling(entry, true, { client }));
  await waitFor(() => expect(reopen.result.current.results.c0?.tree).toEqual(tree));
  expect(client.requestSurfaces).toHaveBeenCalledTimes(1);
  expect(RecognitionWorker.instances).toHaveLength(1);
});

it('reuses completed exact-component recognition through A → B → A and keeps occurrences file-owned', async () => {
  const { urls, fetch } = setup();
  const a = renderHook(() => useModelingRecognition(urls.a, true));
  await respond({ tree }, 0);
  expect(a.result.current.results.c.tree).toEqual(tree);
  a.unmount();
  const b = renderHook(() => useModelingRecognition(urls.b, true));
  await waitFor(() => expect(b.result.current.results.other?.tree).toEqual(tree));
  expect(b.result.current.descriptor.occurrences[0].id).toBe('o2');
  b.unmount();
  const reopen = renderHook(() => useModelingRecognition(urls.a, true));
  await waitFor(() => expect(reopen.result.current.results.c?.tree).toEqual(tree));
  expect(reopen.result.current.descriptor.occurrences[0].id).toBe('o1');
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(RecognitionWorker.instances).toHaveLength(1);
  expect(RecognitionWorker.instances[0].terminate).toHaveBeenCalledTimes(1);
  reopen.unmount();
  const changed = renderHook(() => useModelingRecognition(urls.c, true));
  await respond({ tree: [{ ...tree[0], label: 'Changed solid' }] }, 1);
  expect(changed.result.current.results.c.tree[0].label).toBe('Changed solid');
  expect(fetch).toHaveBeenCalledTimes(3);
  expect(RecognitionWorker.instances).toHaveLength(2);
});

it('does not reuse a failed recognition when the file reopens', async () => {
  const { urls, fetch } = setup();
  const first = renderHook(() => useModelingRecognition(urls.a, true));
  await respond({ error: 'Unavailable' }, 0);
  first.unmount();
  const reopen = renderHook(() => useModelingRecognition(urls.a, true));
  await respond({ tree }, 1);
  expect(reopen.result.current.results.c.tree).toEqual(tree);
  expect(fetch).toHaveBeenCalledTimes(1);
});

it('terminates an aborted worker and rejects its late result instead of caching it', async () => {
  const { urls } = setup();
  const first = renderHook(() => useModelingRecognition(urls.a, true));
  await waitFor(() => expect(RecognitionWorker.instances).toHaveLength(1));
  first.unmount();
  expect(RecognitionWorker.instances[0].terminate).toHaveBeenCalledTimes(1);
  await respond({ tree: [{ ...tree[0], label: 'Late' }] }, 0);
  const reopen = renderHook(() => useModelingRecognition(urls.a, true));
  await respond({ tree }, 1);
  expect(reopen.result.current.results.c.tree[0].label).toBe('Base extrude');
});

it('resolves an unknown exact object before reuse and misses when that object changes', async () => {
  const { urls, fetch } = setup();
  const digest = (value: number) => value.toString(16).padStart(64, '0');
  const descriptor = { kind: 'assembly-package', tree: digest(101), viewId: digest(102),
    surfaceProducer: { kind: 'fixture' }, components: { c: { surfaceInput: digest(103) } },
    occurrences: [{ id: 'o1', component: 'c' }] };
  fetch.mockImplementation(async () => new Response(JSON.stringify(descriptor)));
  let object = digest(104);
  const client = Object.assign(createCadClient({ origin: 'http://viewer.test' }), { requestSurfaces: vi.fn(async () => ({
    viewId: descriptor.viewId, components: { c: { state: 'ready', surfaceInput: digest(103),
      surfaceObject: object, byteLength: 64,
      url: `/__cad/store?tree=${descriptor.tree}&surfaceInput=${digest(103)}&object=${object}` } },
  })) });
  const first = renderHook(() => useModelingRecognition(urls.a, true, { client }));
  await respond({ tree }, 0);
  first.unmount();
  const reopen = renderHook(() => useModelingRecognition(urls.a, true, { client }));
  await waitFor(() => expect(reopen.result.current.results.c?.tree).toEqual(tree));
  expect(RecognitionWorker.instances).toHaveLength(1);
  expect(client.requestSurfaces).toHaveBeenCalledTimes(2);
  reopen.unmount();
  object = digest(105);
  const changed = renderHook(() => useModelingRecognition(urls.a, true, { client }));
  await respond({ tree: [{ ...tree[0], label: 'New exact object' }] }, 1);
  expect(changed.result.current.results.c.tree[0].label).toBe('New exact object');
  expect(client.requestSurfaces).toHaveBeenCalledTimes(3);
  expect(fetch).toHaveBeenCalledTimes(1);
});

it('retires an issued recognition ticket immediately when its resource generation is cancelled', async () => {
  const {urls}=setup();
  const generation=new AbortController();
  Object.defineProperty(fixtureClient.resources,'signal',{value:generation.signal,configurable:true});
  const view=renderHook(()=>useModelingRecognition(urls.a,true));
  await waitFor(()=>expect(RecognitionWorker.instances[0]?.postMessage).toHaveBeenCalled());
  const worker=RecognitionWorker.instances[0];
  await act(async()=>{generation.abort();});
  expect(worker.terminate).toHaveBeenCalled();
  await act(async()=>{worker.onmessage?.({data:{tree}});});
  expect(view.result.current.results).toEqual({});
  view.unmount();
  Object.defineProperty(fixtureClient.resources,'signal',{value:new AbortController().signal,configurable:true});
  const reopen=renderHook(()=>useModelingRecognition(urls.a,true));
  await waitFor(()=>expect(RecognitionWorker.instances).toHaveLength(2));
  expect(reopen.result.current.results).toEqual({});
});

it('loads only expanded occurrences, cancels collapsed work and reuses completed repeated components', async () => {
  const { urls, fetch } = setup();
  const descriptor = {
    components: { a: { surf: 'a.surf' }, b: { surf: 'b.surf' } },
    occurrences: [{ id: 'first', component: 'a' }, { id: 'repeat', component: 'a' }, { id: 'other', component: 'b' }],
  };
  fetch.mockImplementation(async () => new Response(JSON.stringify(descriptor)));
  const view = renderHook(({ requestedOccurrenceIds }) => useRecognition(urls.a, true, {
    client: fixtureClient, requestedOccurrenceIds,
  }), { initialProps: { requestedOccurrenceIds: [] as string[] } });
  await waitFor(() => expect(view.result.current.descriptor?.occurrences).toHaveLength(3));
  expect(RecognitionWorker.instances).toHaveLength(0);
  view.rerender({ requestedOccurrenceIds: ['first'] });
  await waitFor(() => expect(RecognitionWorker.instances[0]?.postMessage).toHaveBeenCalled());
  view.rerender({ requestedOccurrenceIds: [] });
  expect(RecognitionWorker.instances[0].terminate).toHaveBeenCalledTimes(1);
  await respond({ tree: [{ ...tree[0], label: 'Cancelled result' }] }, 0);
  expect(view.result.current.results).toEqual({});
  view.rerender({ requestedOccurrenceIds: ['first'] });
  await respond({ tree }, 1);
  expect(Object.keys(view.result.current.results)).toEqual(['a']);
  view.rerender({ requestedOccurrenceIds: ['repeat'] });
  expect(RecognitionWorker.instances).toHaveLength(2);
  view.rerender({ requestedOccurrenceIds: ['other'] });
  await waitFor(() => expect(RecognitionWorker.instances[2]?.postMessage).toHaveBeenCalled());
  expect(RecognitionWorker.instances[2].postMessage.mock.calls[0][0].resource.url).toContain('b.surf');
  await respond({ tree }, 2);
  view.rerender({ requestedOccurrenceIds: [] });
  view.rerender({ requestedOccurrenceIds: ['first', 'repeat', 'other'] });
  expect(Object.keys(view.result.current.results)).toEqual(['a', 'b']);
  expect(RecognitionWorker.instances).toHaveLength(3);
});

it('defaults to descriptor-only inspection until a consumer supplies an expansion frontier', async () => {
  const { urls } = setup();
  const view = renderHook(() => useRecognition(urls.a, true, { client: fixtureClient }));
  await waitFor(() => expect(view.result.current.descriptor?.occurrences).toHaveLength(1));
  expect(RecognitionWorker.instances).toHaveLength(0);
  expect(view.result.current.results).toEqual({});
});

function pendingAssembly() {
  const { urls, fetch } = setup();
  const descriptor = {
    components: { a: { surf: 'a.surf' }, b: { surf: 'b.surf' } },
    occurrences: [{ id: 'first', component: 'a' }, { id: 'repeat', component: 'a' }, { id: 'other', component: 'b' }],
  };
  fetch.mockImplementation(async () => new Response(JSON.stringify(descriptor)));
  const view = renderHook(({ requestedOccurrenceIds }) => useRecognition(urls.a, true, {
    client: fixtureClient, requestedOccurrenceIds,
  }), { initialProps: { requestedOccurrenceIds: ['first'] } });
  return view;
}

it('keeps the active component running when another part is expanded, then processes the new part', async () => {
  const view = pendingAssembly();
  await waitFor(() => expect(RecognitionWorker.instances[0]?.postMessage).toHaveBeenCalled());
  const first = RecognitionWorker.instances[0];
  view.rerender({ requestedOccurrenceIds: ['first', 'other'] });
  expect(first.terminate).not.toHaveBeenCalled();
  expect(RecognitionWorker.instances).toHaveLength(1);
  await respond({ tree }, 0);
  await waitFor(() => expect(RecognitionWorker.instances[1]?.postMessage).toHaveBeenCalled());
  expect(view.result.current.results.a.tree).toEqual(tree);
  expect(RecognitionWorker.instances[1].postMessage.mock.calls[0][0].resource.url).toContain('b.surf');
  await respond({ tree }, 1);
  expect(Object.keys(view.result.current.results).sort()).toEqual(['a', 'b']);
  expect(first.postMessage).toHaveBeenCalledTimes(1);
});

it('keeps pending recognition for a repeated instance and removes collapsed parts from the queue', async () => {
  const view = pendingAssembly();
  await waitFor(() => expect(RecognitionWorker.instances[0]?.postMessage).toHaveBeenCalled());
  const first = RecognitionWorker.instances[0];
  view.rerender({ requestedOccurrenceIds: ['first', 'other'] });
  view.rerender({ requestedOccurrenceIds: ['repeat'] });
  expect(first.terminate).not.toHaveBeenCalled();
  await respond({ tree }, 0);
  expect(view.result.current.results.a.tree).toEqual(tree);
  expect(view.result.current.results.b).toBeUndefined();
  expect(RecognitionWorker.instances).toHaveLength(1);
});

it('preserves a pending surface request through expansion changes', async () => {
  const { urls, fetch } = setup();
  const descriptor = {
    components: { a: { surfaceInput: 'input-a' }, b: { surf: 'b.surf' } },
    occurrences: [{ id: 'first', component: 'a' }, { id: 'repeat', component: 'a' }, { id: 'other', component: 'b' }],
  };
  fetch.mockImplementation(async () => new Response(JSON.stringify(descriptor)));
  let complete;
  const resolve = vi.spyOn(fixtureClient, 'resolveSurfaceComponents').mockImplementation(() => new Promise(done => { complete=done; }));
  const view = renderHook(({ requestedOccurrenceIds }) => useRecognition(urls.a, true, {
    client: fixtureClient, requestedOccurrenceIds,
  }), { initialProps: { requestedOccurrenceIds: ['first'] } });
  await waitFor(() => expect(resolve).toHaveBeenCalledTimes(1));
  const signal = resolve.mock.calls[0][2].signal;
  view.rerender({ requestedOccurrenceIds: ['first', 'other'] });
  view.rerender({ requestedOccurrenceIds: ['repeat'] });
  expect(resolve).toHaveBeenCalledTimes(1);
  expect(signal.aborted).toBe(false);
  await act(async () => complete(new Map([['a', {
    surfaceInput: 'input-a', surfaceObject: 'object-a', surfUrl: 'https://recognition.test/a.surf',
  }]])));
  await respond({ tree }, 0);
  expect(view.result.current.results.a.tree).toEqual(tree);
  expect(RecognitionWorker.instances).toHaveLength(1);
});

it('retries a failed component without restarting another component that is still running', async () => {
  const view = pendingAssembly();
  view.rerender({ requestedOccurrenceIds: ['first', 'other'] });
  await respond({ error: 'Unavailable' }, 0);
  await waitFor(() => expect(RecognitionWorker.instances[1]?.postMessage).toHaveBeenCalled());
  const other = RecognitionWorker.instances[1];
  act(() => view.result.current.retryFailed());
  expect(other.terminate).not.toHaveBeenCalled();
  expect(RecognitionWorker.instances).toHaveLength(2);
  await respond({ tree }, 1);
  await waitFor(() => expect(RecognitionWorker.instances[2]?.postMessage).toHaveBeenCalled());
  expect(RecognitionWorker.instances[2].postMessage.mock.calls[0][0].resource.url).toContain('a.surf');
  await respond({ tree }, 2);
  expect(view.result.current.results.a.tree).toEqual(tree);
  expect(view.result.current.results.b.tree).toEqual(tree);
});

it('cancels only the unwanted active part and ignores its late result while processing the remaining part', async () => {
  const view = pendingAssembly();
  await waitFor(() => expect(RecognitionWorker.instances[0]?.postMessage).toHaveBeenCalled());
  const first = RecognitionWorker.instances[0];
  view.rerender({ requestedOccurrenceIds: ['first', 'other'] });
  view.rerender({ requestedOccurrenceIds: ['other'] });
  expect(first.terminate).toHaveBeenCalledTimes(1);
  await waitFor(() => expect(RecognitionWorker.instances[1]?.postMessage).toHaveBeenCalled());
  await respond({ tree: [{ ...tree[0], label: 'Late' }] }, 0);
  expect(view.result.current.results.a).toBeUndefined();
  await respond({ tree }, 1);
  expect(Object.keys(view.result.current.results)).toEqual(['b']);
  view.rerender({ requestedOccurrenceIds: ['first', 'other'] });
  await waitFor(() => expect(RecognitionWorker.instances[2]?.postMessage).toHaveBeenCalled());
  await respond({ tree }, 2);
  expect(view.result.current.results.a.tree).toEqual(tree);
});
