import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { createHttpCadResourceProvider } from '@text-to-cad/core/client';
import { entryMeshAssetSignature } from '@text-to-cad/core/lib/entryAssets.js';
import { initialEditingPreview, reduceEditingPreview } from '../../../../../../dist/renderers/step/workbench/editingPreview.js';
import { usePreviewRevision } from '../../../../../../dist/renderers/step/components/workbench/hooks/usePreviewRevision.js';

afterEach(() => cleanup());

const FILE = '/models/hinge_block.step';
const TREE = 'p'.repeat(64);
const OBJECT = 'a'.repeat(64);
const PART = `${'1'.repeat(64)}-v6`;
const articulation = { controls: [{ id: 'hinge', min: 0, max: 90 }], poses: {} };
const display = { 'o:arm': { finish: 'brushed' } };
// The saved file on screen when the build begins, as the catalog lists it.
const saved = (hash: string) => ({ file: FILE, kind: 'assembly', url: `https://cad.test/__cad/store?file=${hash}`, hash, documentHash: `d-${hash}`,
  articulation, poseUrl: '/models/hinge_block.step.json?v=1', display, appearanceHash: 'e'.repeat(64) });
const A = saved('s'.repeat(64));
const B = saved('b'.repeat(64));
const descriptor = { kind: 'assembly-package', entryKind: 'assembly', tree: TREE, components: { c1: { part: PART } }, occurrences: [] };
const annotations = { kind: 'preview-annotations', schemaVersion: 1, tree: TREE, articulation, appearance: {}, display: { 'o:arm': { finish: 'matte' } }, animation: null };

// A client over a stubbed server: the preview's view at its tree, its annotations by object.
function client() {
  const requests: string[] = [];
  // The view's URL carries the tree's `assembly.json` path percent-encoded in its `file` param.
  const fetch = vi.fn(async (url: string) => {
    requests.push(decodeURIComponent(url));
    if (decodeURIComponent(url).includes('/assembly.json')) return { ok: true, status: 200, json: async () => descriptor };
    throw new Error(`unexpected ${url}`);
  });
  const resources = createHttpCadResourceProvider({ origin: 'https://cad.test', fetch: fetch as unknown as typeof globalThis.fetch });
  return {
    requests,
    resources,
    storeTreeUrl: (tree: string, { producer = null }: { producer?: object | null } = {}) =>
      `https://cad.test/__cad/store?file=${tree}${producer ? `&producer=${encodeURIComponent(JSON.stringify(producer))}` : ''}`,
    previewAnnotations: vi.fn(async (object: string) => { requests.push(`annotations:${object}`); return object === OBJECT ? annotations : null; }),
  };
}

// The feed's state, answer by answer (`reduceEditingPreview`).
const feed = (answers: object[]) => answers.reduce((state, answer) => reduceEditingPreview(state, answer), initialEditingPreview());
const building = (extra: object = {}) => ({ epoch: 'e1', revision: 3, state: 'building', ...extra });
const named = (extra: object = {}) => ({ tree: TREE, producer: { producerKey: 'k' }, parts: { c1: PART }, complete: false, annotations: null, ...extra });

function mount(service: ReturnType<typeof client>, initial: { editing: object; inHand: object; meshState?: object | null }) {
  return renderHook(({ editing, inHand, meshState }) => usePreviewRevision(editing, { client: service, file: FILE, inHand, meshState: meshState || null }),
    { initialProps: { meshState: null as object | null, ...initial } });
}

it('draws the preview the feed names once its view is read, with what is in hand until its annotations bind', async () => {
  const service = client();
  const hook = mount(service, { editing: feed([building()]), inHand: A });
  expect(hook.result.current.entry).toBeNull();
  expect(service.requests).toEqual([]);
  // The result exists: the view is read at the tree, keyed by the producer, and the entry drawn.
  hook.rerender({ editing: feed([building(), building({ preview: named() })]), inHand: A, meshState: null });
  await waitFor(() => expect(hook.result.current.entry).not.toBeNull());
  const entry = hook.result.current.entry!;
  expect(entry).toMatchObject({ file: FILE, kind: 'assembly', hash: TREE, preview: true, articulation, poseUrl: A.poseUrl, display, appearanceHash: A.appearanceHash });
  expect(entry.url).toContain(`file=${TREE}`);
  expect(service.requests).toHaveLength(1);
  expect(service.requests[0]).toMatch(/\/__cad\/store\?file=\/p{64}\/assembly\.json&producer=/);
  // Its parts, as the feed names them, through the gate its load waits on.
  expect(hook.result.current.gate!.has('c1')).toBe(true);
  expect(hook.result.current.gate!.complete).toBe(false);
  hook.rerender({ editing: feed([building(), building({ preview: named({ parts: { c1: PART, c2: PART }, complete: true }) })]), inHand: A, meshState: null });
  expect(hook.result.current.gate!.has('c2')).toBe(true);
  expect(hook.result.current.gate!.complete).toBe(true);
  expect(hook.result.current.entry!.hash).toBe(TREE);
});

it('binds the annotations once read, the finishes only once the preview is on screen whole, and keeps them bound', async () => {
  const service = client();
  const editing = feed([building(), building({ preview: named({ annotations: OBJECT }) })]);
  const hook = mount(service, { editing, inHand: A });
  await waitFor(() => expect(hook.result.current.entry?.poseUrl).toBe(`preview:${OBJECT}`));
  expect(service.previewAnnotations).toHaveBeenCalledWith(OBJECT, expect.anything());
  // The pose binds at once; the finishes in hand stay while the geometry loads.
  const undressed = hook.result.current.entry!;
  expect(undressed.display).toBe(display);
  expect(undressed.appearanceHash).toBe(A.appearanceHash);
  // The geometry whole on screen under that signature: the preview's own finishes bind.
  const whole = { file: FILE, meshHash: entryMeshAssetSignature(undressed), assemblyInteractionReady: true, meshData: { missingComponentIds: [] } };
  hook.rerender({ editing, inHand: A, meshState: whole });
  expect(hook.result.current.entry!.display).toEqual(annotations.display);
  expect(hook.result.current.entry!.appearanceHash).toBe(`preview:${OBJECT}`);
  // And stay bound while the re-dressed composition loads under its new signature.
  hook.rerender({ editing, inHand: A, meshState: { ...whole, assemblyInteractionReady: false } });
  expect(hook.result.current.entry!.appearanceHash).toBe(`preview:${OBJECT}`);
  expect(service.requests.filter(request => request.startsWith('annotations:'))).toHaveLength(1);
});

it('the save replaces the preview in place: the catalog naming a new revision retires it, as its own save unless the file moved past the build', async () => {
  const service = client();
  const editing = feed([building(), building({ preview: named({ complete: true }) })]);
  const hook = mount(service, { editing, inHand: A });
  await waitFor(() => expect(hook.result.current.entry).not.toBeNull());
  // The catalog still lists the file the build began over: the preview stays.
  hook.rerender({ editing: feed([building(), building({ preview: named({ complete: true }) }), building({ state: 'done', preview: named({ complete: true }) })]), inHand: A, meshState: null });
  expect(hook.result.current.entry).not.toBeNull();
  // The catalog names the saved revision: the preview goes, and the swap is its own save.
  const done = feed([building(), building({ state: 'done', preview: named({ complete: true }) })]);
  hook.rerender({ editing: done, inHand: B, meshState: null });
  expect(hook.result.current).toEqual({ entry: null, gate: null, saved: B.hash });
  // It does not come back for this build, whatever the catalog says next.
  hook.rerender({ editing: done, inHand: B, meshState: null });
  expect(hook.result.current.entry).toBeNull();
  // A file the build was moved past: the revision that retired the preview is nobody's save.
  const other = client();
  const moved = mount(other, { editing, inHand: A });
  await waitFor(() => expect(moved.result.current.entry).not.toBeNull());
  moved.rerender({ editing: feed([building(), building({ state: 'done', superseded: true, preview: null })]), inHand: B, meshState: null });
  expect(moved.result.current).toEqual({ entry: null, gate: null, saved: '' });
});

it('a build first seen already done is the file on disk, never its preview; a new build starts over', async () => {
  const service = client();
  const hook = mount(service, { editing: feed([building({ state: 'done', preview: named({ complete: true }) })]), inHand: B });
  await act(async () => {});
  expect(hook.result.current.entry).toBeNull();
  expect(service.requests).toEqual([]);
  // A failed build keeps its preview: first seen failed, it is drawn under the alert.
  hook.rerender({ editing: feed([building({ epoch: 'e1', revision: 4, state: 'failed', error: 'the save failed', preview: named({ complete: true }) })]), inHand: B, meshState: null });
  await waitFor(() => expect(hook.result.current.entry).not.toBeNull());
  // The next build names no preview until its result exists: the catalog's entry shows meanwhile.
  hook.rerender({ editing: feed([building({ revision: 5 })]), inHand: B, meshState: null });
  expect(hook.result.current).toEqual({ entry: null, gate: null, saved: '' });
});

it('a build that could not name its parts has no gate: the view keys them as for a saved file', async () => {
  const service = client();
  const hook = mount(service, { editing: feed([building(), building({ preview: named({ producer: null, parts: {} }) })]), inHand: A });
  await waitFor(() => expect(hook.result.current.entry).not.toBeNull());
  expect(hook.result.current.gate).toBeNull();
  expect(service.requests[0]).not.toContain('producer=');
});
