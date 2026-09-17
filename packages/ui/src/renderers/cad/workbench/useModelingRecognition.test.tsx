import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useModelingRecognition } from './useModelingRecognition.js';

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
  return { urls, fetch };
}
async function respond(data: unknown, index: number) {
  await waitFor(() => expect(RecognitionWorker.instances.length).toBeGreaterThan(index));
  await act(async () => { RecognitionWorker.instances[index].onmessage?.({ data }); });
}
afterEach(() => { cleanup(); vi.unstubAllGlobals(); RecognitionWorker.instances = []; });

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
  const client = { origin: 'http://viewer.test', requestSurfaces: vi.fn(async () => ({
    viewId: descriptor.viewId, components: { c: { state: 'ready', surfaceInput: digest(103),
      surfaceObject: object, byteLength: 64,
      url: `/__cad/store?tree=${descriptor.tree}&surfaceInput=${digest(103)}&object=${object}` } },
  })) };
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
