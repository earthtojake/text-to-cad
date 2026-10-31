import { useState, type ReactNode } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createCadClient } from '@text-to-cad/core/client';
import { FileViewer } from '../../../dist/file-viewer/index.js';
import { createDxfRenderer } from '../../../dist/renderers/dxf/index.js';
// Loaded with the file, not inside the first test: the registration imports it lazily.
import '../../../dist/renderers/dxf/DxfRenderer.js';
import SAMPLE from './__fixtures__/sample.drawing.json';
import LAYERED from './__fixtures__/layered.drawing.json';

// The DXF tab's chrome and its answers to the host, mounted the way a host mounts it: the
// FileViewer over the real DXF registration and a real CAD client, whose backend is a fetch that
// answers with the committed `/__cad/drawing` payload. Only the canvas's 2D context and PNG
// encoder are stand-ins — what is PAINTED is the browser suite's; what the tab offers, what the
// cursor says and what a host is told are decided here, above the pixels.

const FILE = '/models/sample.dxf';

// Every transform the drawing is painted at, and the layers it was painted without: the picture
// itself is not jsdom's to draw.
const painted = vi.hoisted(() => [] as Array<{ scale: number; offsetX: number; offsetY: number; hidden?: string[] }>);
vi.mock('@text-to-cad/core/lib/drawing2d/index.js', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, drawDrawing: (_ctx: unknown, _drawing: unknown, { transform, hiddenLayers }: { transform: any, hiddenLayers?: Set<string> }) => {
    painted.push({ ...transform, hidden: [...(hiddenLayers || [])] });
  } };
});

const noop = () => {};
const json = (body: unknown) => new Response(JSON.stringify(body), { headers: { 'content-type': 'application/json' } });

// The file as the backend serves it: a test rewrites it, and decides how its next read answers.
let revision = 'one-sample';
let readDrawing: () => Response | Promise<Response> = () => json(SAMPLE);
let copied: Promise<string> | string = '';
const context2d = new Proxy({}, { get: (_target, key) => (key === 'canvas' ? undefined : key === 'measureText' ? (text: string) => ({ width: text.length * 7 }) : noop), set: () => true });

beforeEach(() => {
  painted.length = 0;
  revision = 'one-sample';
  readDrawing = () => json(SAMPLE);
  copied = '';
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => setTimeout(() => callback(performance.now()), 0));
  vi.stubGlobal('cancelAnimationFrame', (handle: number) => clearTimeout(handle));
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: false, media: query, addEventListener: noop, removeEventListener: noop, addListener: noop, removeListener: noop }));
  // jsdom has no Path2D: the drawing's paths are prepared into these, and painted by the stand-in above.
  vi.stubGlobal('Path2D', class { constructor() { return new Proxy(this, { get: (target, key) => (key in target ? (target as any)[key] : noop) }); } });
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(
    { x: 0, y: 0, left: 0, top: 0, right: 1200, bottom: 700, width: 1200, height: 700, toJSON: noop } as DOMRect);
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context2d as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(function (callback, type) {
    setTimeout(() => callback(new Blob(['png'], { type: type || 'image/png' })), 0);
  });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

/** One pane of the harness: a host, a workspace, host commands and a live binding, and the tab. */
async function openDrawing(destinationKind = 'composer', notice: ReactNode = null, promptFiles?: any, { drawn = true } = {}) {
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    if (url.pathname.endsWith('/__cad/catalog')) {
      return json({ entries: [{ kind: 'dxf', file: FILE, url: '/sample.dxf', hash: revision, bytes: 4096 }] });
    }
    if (url.pathname.endsWith('/__cad/server')) return json({ backend: 'cadgen' });
    if (url.pathname.endsWith('/__cad/drawing')) return readDrawing();
    return new Response('', { status: 404 });
  });
  const client = createCadClient({ origin: 'http://viewer.test/one', pollIntervalMs: 0, fetch: fetch as typeof globalThis.fetch });
  await client.refresh();

  let commandSnapshot: Record<string, any> = {};
  const listeners = new Set<() => void>();
  const commands = {
    getSnapshot: () => commandSnapshot,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    acknowledge: vi.fn((kind: string, key: string | number) => {
      if (commandSnapshot[kind]?.key !== key) return;
      commandSnapshot = { ...commandSnapshot, [kind]: null };
      for (const listener of listeners) listener();
    })
  };
  const request = (next: Record<string, any>) => act(() => { commandSnapshot = next; for (const listener of listeners) listener(); });

  let controller: any = null;
  const live = { bind(next: unknown) { controller = next; return () => { controller = null; }; } };
  const renderers = [createDxfRenderer({ client, commands, live })];

  const destination = { kind: destinationKind, available: destinationKind !== 'unavailable' };
  const delivered: Array<{ type: string; parts: string[] }> = [];
  const host = {
    promptFiles,
    files: {
      id: 'one',
      stat: async (path: string) => ({ path, name: path.split('/').pop(), kind: 'file', size: 400, extension: 'dxf' })
    },
    navigation: { openFile: noop },
    environment: { colorScheme: 'light' },
    clipboard: { writeText: async (text: Promise<string> | string) => { copied = text; }, readText: async () => '', writeImage: async () => {} },
    promptContext: {
      getSnapshot: () => destination, subscribe: () => noop,
      deliver: async (context: any) => {
        const attachment = context.parts.find((part: any) => part.kind === 'attachment');
        const blob = attachment ? await attachment.content : null;
        delivered.push({ type: blob?.type ?? '', parts: context.parts.map((part: any) => part.kind) });
        return { status: 'added', partIds: context.parts.map((part: any) => part.id) };
      }
    }
  };
  function Pane() {
    const [state, setState] = useState<any>({ renderers: {} });
    // The host's Settings, as `CadViewer` hands it over: drawn by FileViewer over every file.
    return <section data-testid="one"><FileViewer file={FILE} host={host as any} renderers={renderers} state={state} onStateChange={setState} notice={notice}
      settings={<button type="button" aria-label="Settings" />} /></section>;
  }
  render(<Pane />);
  const pane = screen.getByTestId('one');
  if (!drawn) return { pane, dispose: () => client.dispose() };
  const canvas = await waitFor(() => {
    const element = pane.querySelector<HTMLCanvasElement>('[data-drawing-surface] canvas');
    expect(element).not.toBeNull();
    expect(pane.querySelector('[aria-busy="false"]')).not.toBeNull();
    return element!;
  });
  // The fitted picture is on the canvas.
  await waitFor(() => expect(painted.length).toBeGreaterThan(0));
  const refresh = () => act(async () => { await client.refresh(); });
  // A press that lets go where it went down, at a drawing point under the fitted view (the pane is
  // 1200 × 700 at the page's origin).
  const tap = (x: number, y: number, init: Record<string, unknown> = {}) => {
    const { scale, offsetX, offsetY } = painted.at(-1)!;
    const at = { pointerId: 1, pointerType: 'mouse', button: 0, clientX: x * scale + offsetX, clientY: offsetY - y * scale, ...init };
    fireEvent.pointerDown(canvas, at);
    fireEvent.pointerUp(canvas, at);
  };
  return { pane, canvas, commands, request, delivered, refresh, tap, get controller() { return controller; }, dispose: () => client.dispose() };
}

it('Select is the hand, with the 3D views\' cursor: a drag pans under the arrow, a tap does not move the view', async () => {
  const { canvas, dispose } = await openDrawing();
  const cursor = () => ['cursor-default', 'cursor-grab', 'cursor-grabbing', 'cursor-pointer'].filter(name => canvas.classList.contains(name));
  expect(cursor()).toEqual(['cursor-default']);
  // A secondary press is not a drag: it belongs to whatever the host puts on it.
  fireEvent.pointerDown(canvas, { pointerId: 2, pointerType: 'mouse', button: 2, clientX: 600, clientY: 350 });
  expect(cursor()).toEqual(['cursor-default']);
  const fitted = painted.at(-1)!;
  fireEvent.pointerDown(canvas, { pointerId: 1, pointerType: 'mouse', button: 0, clientX: 600, clientY: 350 });
  fireEvent.pointerMove(canvas, { pointerId: 1, pointerType: 'mouse', clientX: 602, clientY: 350 });
  expect(painted.at(-1)).toEqual(fitted);
  fireEvent.pointerMove(canvas, { pointerId: 1, pointerType: 'mouse', clientX: 630, clientY: 350 });
  expect(cursor()).toEqual(['cursor-default']);
  fireEvent.pointerUp(canvas, { pointerId: 1, pointerType: 'mouse', button: 0, clientX: 630, clientY: 350 });
  expect(cursor()).toEqual(['cursor-default']);
  await waitFor(() => expect(painted.at(-1)!.offsetX).toBeCloseTo(fitted.offsetX + 30, 6));
  // Resting on what a press would pick (the red circle's rim): the pointing hand, as over a part.
  const { scale, offsetX, offsetY } = painted.at(-1)!;
  fireEvent.pointerMove(canvas, { pointerId: 1, pointerType: 'mouse', clientX: 34 * scale + offsetX, clientY: offsetY - 40 * scale });
  await waitFor(() => expect(cursor()).toEqual(['cursor-pointer']));
  dispose();
});

it("the host's notice shows at the top-right once the drawing is on screen", async () => {
  const { pane, dispose } = await openDrawing('composer', <div role="dialog" aria-label="A notice" />);
  expect(within(pane).getByRole('dialog', { name: 'A notice' }).closest('[data-viewport-top-right]')).not.toBeNull();
  dispose();
});

it("a DXF's strip is Select (in hand), Pencil, Shapes and Measure: no Display, no Preview, no view controls", async () => {
  const { pane, delivered, dispose } = await openDrawing();
  const inPane = within(pane);
  const strip = inPane.getByRole('group', { name: 'Interaction tools' });
  expect(within(strip).getAllByRole('button').map(button => button.getAttribute('aria-label'))).toEqual(['Select', 'Pencil', 'Shapes', 'Measure']);
  expect(within(strip).getByRole('button', { name: 'Select' }).getAttribute('aria-pressed')).toBe('true');
  expect(strip.querySelector('[data-strip-rule]')).toBeNull();
  for (const name of ['Orbit', 'Position', 'Animation', 'Preview', 'Display', 'Display settings', 'Projection', 'Explode', 'Clip']) {
    expect(inPane.queryByRole('button', { name }), name).toBeNull();
  }
  expect(pane.querySelectorAll('[data-view-controls] button')).toHaveLength(0);
  // A drawing of one layer and no blocks has nothing for a Layers section to say: no sidebar.
  expect(pane.querySelector('[data-file-sidebar-tools]')).toBeNull();
  // Nothing is picked, drawn or measured yet: Quick Edit is not there, and nothing went anywhere.
  expect(pane.querySelector('[data-quick-edit-box]')).toBeNull();
  expect(inPane.queryByRole('button', { name: 'Take snapshot' })).toBeNull();
  expect(delivered).toHaveLength(0);

  // Measure in hand hangs no row under the strip; the drawing row has no placement.
  fireEvent.click(within(strip).getByRole('button', { name: 'Measure' }));
  expect(pane.querySelector('[data-cad-sub-toolbar]')).toBeNull();
  fireEvent.click(within(strip).getByRole('button', { name: 'Pencil' }));
  expect(pane.querySelector('[data-annotation-controls]')).not.toBeNull();
  expect(inPane.queryByRole('button', { name: /Placement/ })).toBeNull();
  expect(pane.querySelector('[data-cad-annotation-overlay]')).not.toBeNull();
  dispose();
});

it('Select picks an entity by handle: lit, a Quick Edit chip by type and layer, and a reference into the file', async () => {
  const drawing = await openDrawing();
  const { pane, tap, dispose } = drawing;
  // The red circle (handle 33) at its rightmost point; Shift adds the bottom edge (handle 2F).
  tap(34, 40);
  const box = await waitFor(() => { const element = pane.querySelector('[data-quick-edit-box]'); expect(element).not.toBeNull(); return element as HTMLElement; });
  expect(within(box).getByText('Circle on 0')).toBeTruthy();
  tap(50, 0, { shiftKey: true });
  await waitFor(() => expect(within(box).getByText('Line on 0')).toBeTruthy());
  const controller = await waitFor(() => { expect(drawing.controller).not.toBeNull(); return drawing.controller; });
  const state = controller.readState();
  expect(state.selectedEntities).toEqual(['33', '2F']);
  expect(state.selection.map((reference: any) => reference.target.selectors)).toEqual([['h33'], ['h2F']]);
  // The note carries them as references into the drawing, by handle.
  const field = box.querySelector<HTMLElement>('[data-quick-edit-note]')!;
  field.textContent = 'Make this hole 6 mm.';
  fireEvent.input(field);
  fireEvent.click(within(box).getByRole('button', { name: 'Copy Prompt' }));
  await waitFor(() => expect(copied).not.toBe(''));
  const text = await copied;
  expect(text).toContain('/models/sample.dxf#h33');
  expect(text).toContain('/models/sample.dxf#h2F');
  // A tap on nothing lets go (the note, written, keeps the box).
  tap(80, 10);
  await waitFor(() => expect(controller.readState().selectedEntities).toEqual([]));
  expect(within(box).queryByText('Circle on 0')).toBeNull();
  dispose();
});

it('a DXF has no snapshot in the navbar, whatever the destination: its note to the agent is Quick Edit\'s', async () => {
  const { pane, dispose } = await openDrawing('clipboard');
  await waitFor(() => expect(pane.querySelector('canvas')).not.toBeNull());
  expect(within(pane).queryByRole('button', { name: 'Take snapshot' })).toBeNull();
  dispose();
});

it('a DXF in a host with no prompt workflow has no snapshot', async () => {
  const { pane, dispose } = await openDrawing('unavailable');
  expect(within(pane).queryByRole('button', { name: 'Take snapshot' })).toBeNull();
  dispose();
});

it('host commands a flat drawing cannot answer are declined in words', async () => {
  const drawing = await openDrawing();
  const { canvas, dispose } = drawing;
  const controller = await waitFor(() => { expect(drawing.controller).not.toBeNull(); return drawing.controller; });
  await expect(controller.select({ selectors: ['h2F'] })).rejects.toThrow(/picked by a person in the viewer under Select/);
  await act(async () => { await controller.clearSelection(); });
  await expect(controller.setCamera({ position: [0, 0, 1], target: [0, 0, 0], up: [0, 1, 0] })).rejects.toThrow(/no camera to pose/);
  await expect(controller.setDisplaySettings({ mode: 'wireframe' })).rejects.toThrow(/no Display settings/);

  // What it CAN do: report itself, fit again, and hand over a PNG. No zoom command, no zoom readout.
  const state = controller.readState();
  expect(state).toMatchObject({ active: true, loading: false, camera: null, selection: [] });
  expect('zoomPercent' in state).toBe(false);
  expect(controller.setZoom).toBeUndefined();

  const fitted = painted.at(-1)!;
  fireEvent.wheel(canvas, { deltaY: -Math.log(0.5) / 0.0015, clientX: 300, clientY: 300 });
  await waitFor(() => expect(painted.at(-1)!.scale).toBeCloseTo(fitted.scale * 0.5, 6));
  await act(async () => { await controller.resetCamera(); });
  expect(painted.at(-1)).toEqual(fitted);

  const blob = await controller.capture();
  expect(blob.type).toBe('image/png');
  expect(HTMLCanvasElement.prototype.toBlob).toHaveBeenCalledWith(expect.any(Function), 'image/png');
  dispose();
});

it('a drawing with layers and blocks has a Layers section: a layer hidden is not drawn, a block reference is picked from it', async () => {
  readDrawing = () => json(LAYERED);
  const { pane, dispose } = await openDrawing();
  const tile = await waitFor(() => within(pane.querySelector('[data-file-sidebar-tools]') as HTMLElement).getByRole('button', { name: 'Layers' }));
  fireEvent.click(tile);
  const list = await waitFor(() => { const element = pane.querySelector('[data-drawing-layers]'); expect(element).not.toBeNull(); return element as HTMLElement; });
  expect([...list.querySelectorAll('[data-layer-row]')].map(row => row.getAttribute('data-layer-row')))
    .toEqual(['CUT', 'BEND', 'ENGRAVE', 'HARDWARE', 'CENTRE', '0']);
  fireEvent.click(list.querySelector('[data-layer-visibility="CENTRE"]')!);
  await waitFor(() => expect(painted.at(-1)!.hidden).toEqual(['CENTRE']));
  // HARDWARE holds the two M5_NUT references; a click picks one, as a tap on the drawing would.
  const inserts = [...list.querySelectorAll('[data-insert-row]')];
  expect(inserts.map(row => row.getAttribute('data-insert-row'))).toEqual(['99', '9B']);
  fireEvent.click(inserts[0]);
  await waitFor(() => expect(within(pane.querySelector('[data-quick-edit-box]') as HTMLElement).getByRole('button', { name: 'Block M5_NUT on HARDWARE' })).toBeTruthy());
  dispose();
});

it('a select-reference request is consumed without a notification', async () => {
  const { pane, commands, request, dispose } = await openDrawing();
  await request({ selectReference: { selector: 'f:plate.make_box1.1', key: 7 } });
  await waitFor(() => expect(commands.getSnapshot().selectReference ?? null).toBeNull());
  expect(commands.acknowledge).toHaveBeenCalledWith('selectReference', 7);
  // Declined silently: no alert, no status, and the drawing is still the drawing.
  expect(within(pane).queryByRole('alert')).toBeNull();
  expect(pane.querySelector('[data-drawing-surface] canvas')).not.toBeNull();
  dispose();
});

it('an unreadable drawing shows the server\'s own sentence, and an empty one says it is empty', async () => {
  readDrawing = () => new Response(JSON.stringify({ error: 'broken.dxf is not a readable DXF document' }),
    { status: 400, headers: { 'content-type': 'application/json' } });
  const broken = await openDrawing('composer', null, undefined, { drawn: false });
  const text = (await within(broken.pane).findByRole('alert')).textContent;
  for (const said of [/The viewer couldn’t complete the request/, /HTTP 400/, /not a readable DXF document/, /Retry/]) expect(text).toMatch(said);
  expect(broken.pane.querySelector('[data-viewer-loading]')).toBeNull();
  broken.dispose();
  cleanup();

  readDrawing = () => json({ schemaVersion: SAMPLE.schemaVersion, units: SAMPLE.units, bounds: null, layers: [], entities: [], fonts: [], primitives: [] });
  const empty = await openDrawing('composer', null, undefined, { drawn: false });
  const said = await waitFor(() => { const found = empty.pane.querySelector('[data-drawing-empty]'); expect(found).not.toBeNull(); return found!; });
  expect(said.textContent).toMatch(/no geometry in its modelspace/);
  expect(within(empty.pane).queryByRole('alert')).toBeNull();
  empty.dispose();
});

it('a rewritten drawing stays on screen while its next revision is read, and after one that will not read', async () => {
  const { pane, canvas, refresh, dispose } = await openDrawing();
  let release = noop;
  readDrawing = () => new Promise(resolve => { release = () => resolve(json(SAMPLE)); });
  revision = 'two-sample';
  await refresh();
  // The same drawing on the same canvas, nothing covering it: the update is said top-centre.
  expect(await within(pane).findByText('Updating drawing…')).toBeTruthy();
  expect(pane.querySelector('[data-drawing-surface] canvas')).toBe(canvas);
  expect(pane.querySelector('[aria-busy="true"]')).not.toBeNull();
  expect(pane.textContent).not.toContain('Reading drawing');
  await act(async () => { release(); });
  await waitFor(() => expect(pane.querySelector('[aria-busy="false"]')).not.toBeNull());
  expect(within(pane).queryByText('Updating drawing…')).toBeNull();

  // A revision that will not read leaves the last drawing to use, with the failure beside it.
  readDrawing = () => new Response('the drawing is truncated', { status: 500 });
  revision = 'three-sample';
  await refresh();
  expect(await within(pane).findByText(/The existing drawing remains visible/)).toBeTruthy();
  expect(pane.querySelector('[data-drawing-surface] canvas')).toBe(canvas);
  expect(pane.textContent).not.toContain('Reading drawing');
  dispose();
});


it('a measurement on a drawing is Measure\'s row\'s chip, and opens no Quick Edit', async () => {
  const promptFiles = { create: vi.fn(async () => ({ snapshot: '/tmp/drawing.snapshot.json' })), read: vi.fn(), save: vi.fn() };
  const { tap, dispose } = await openDrawing('clipboard', null, promptFiles);
  fireEvent.click(screen.getByRole('button', { name: 'Measure', exact: true }));
  expect(screen.queryByRole('toolbar', { name: 'Measurements' })).toBeNull();
  tap(0, 0);
  tap(100, 0);
  const row = await screen.findByRole('toolbar', { name: 'Measurements' });
  expect(within(row).getByRole('button', { name: 'Measurement 1: 100.00 mm' })).toBeTruthy();
  expect(screen.queryByRole('region', { name: 'Quick Edit' })).toBeNull();
  expect(promptFiles.create).not.toHaveBeenCalled();
  dispose();
});
