import { useState, type ReactNode } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createCadClient } from '@text-to-cad/core/client';
import { FileViewer } from '../../../dist/file-viewer/index.js';
import { createDxfRenderer } from '../../../dist/renderers/dxf/index.js';
// Loaded with the file, not inside the first test: the registration imports it lazily.
import '../../../dist/renderers/dxf/DxfRenderer.js';
import SAMPLE from './__fixtures__/sample.drawing.json';

// The DXF tab's chrome and its answers to the host, mounted the way a host mounts it: the
// FileViewer over the real DXF registration and a real CAD client, whose backend is a fetch that
// answers with the committed `/__cad/drawing` payload. Only the canvas's 2D context and PNG
// encoder are stand-ins — what is PAINTED is the browser suite's; what the tab offers, what the
// cursor says and what a host is told are decided here, above the pixels.

const FILE = 'sample.dxf';

// Every transform the drawing is painted at: the picture itself is not jsdom's to draw.
const painted = vi.hoisted(() => [] as Array<{ scale: number; offsetX: number; offsetY: number }>);
vi.mock('@text-to-cad/core/lib/drawing2d/index.js', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, drawDrawing: (_ctx: unknown, _drawing: unknown, { transform }: { transform: any }) => { painted.push({ ...transform }); } };
});

const noop = () => {};
const json = (body: unknown) => new Response(JSON.stringify(body), { headers: { 'content-type': 'application/json' } });

// The file as the backend serves it: a test rewrites it, and decides how its next read answers.
let revision = 'one-sample';
let readDrawing: () => Response | Promise<Response> = () => json(SAMPLE);
const context2d = new Proxy({}, { get: (_target, key) => (key === 'canvas' ? undefined : noop), set: () => true });

beforeEach(() => {
  painted.length = 0;
  revision = 'one-sample';
  readDrawing = () => json(SAMPLE);
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
async function openDrawing(destinationKind = 'composer', notice: ReactNode = null) {
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    if (url.pathname.endsWith('/__cad/catalog')) {
      return json({ rootId: 'one', entries: [{ kind: 'dxf', file: FILE, rootRelativeFile: FILE, url: `/${FILE}`, hash: revision, bytes: 4096 }] });
    }
    if (url.pathname.endsWith('/__cad/server')) return json({ rootId: 'one', rootPath: '/models', backend: 'cadgen' });
    if (url.pathname.endsWith('/__cad/drawing')) return readDrawing();
    return new Response('', { status: 404 });
  });
  const client = createCadClient({ origin: 'http://viewer.test/one', workspaceId: 'one', pollIntervalMs: 0, fetch: fetch as typeof globalThis.fetch });
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
    files: {
      id: 'one', rootName: 'one',
      stat: async (path: string) => ({ path, name: path, kind: 'file', size: 400, extension: 'dxf' }),
      list: async () => [{ path: FILE, name: FILE, kind: 'file' }]
    },
    navigation: { openFile: noop },
    environment: { colorScheme: 'light' },
    clipboard: { writeText: async () => {}, readText: async () => '', writeImage: async () => {} },
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
    const [state, setState] = useState<any>({ panel: null, renderers: {} });
    return <section data-testid="one"><FileViewer file={FILE} host={host as any} renderers={renderers} state={state} onStateChange={setState} notice={notice} /></section>;
  }
  render(<Pane />);
  const pane = screen.getByTestId('one');
  const canvas = await waitFor(() => {
    const element = pane.querySelector<HTMLCanvasElement>('[data-drawing-surface] canvas');
    expect(element).not.toBeNull();
    expect(pane.querySelector('[aria-busy="false"]')).not.toBeNull();
    return element!;
  });
  // The fitted picture is on the canvas.
  await waitFor(() => expect(painted.length).toBeGreaterThan(0));
  const refresh = () => act(async () => { await client.refresh(); });
  return { pane, canvas, commands, request, delivered, refresh, get controller() { return controller; }, dispose: () => client.dispose() };
}

it('the cursor says the drawing can be dragged, and says so louder while it is', async () => {
  const { canvas, dispose } = await openDrawing();
  const cursor = () => ['cursor-grab', 'cursor-grabbing'].filter(name => canvas.classList.contains(name));
  expect(cursor()).toEqual(['cursor-grab']);
  // A secondary press is not a drag: it belongs to whatever the host puts on it.
  fireEvent.pointerDown(canvas, { pointerId: 2, pointerType: 'mouse', button: 2, clientX: 600, clientY: 350 });
  expect(cursor()).toEqual(['cursor-grab']);
  fireEvent.pointerDown(canvas, { pointerId: 1, pointerType: 'mouse', button: 0, clientX: 600, clientY: 350 });
  fireEvent.pointerMove(canvas, { pointerId: 1, pointerType: 'mouse', clientX: 630, clientY: 350 });
  expect(cursor()).toEqual(['cursor-grabbing']);
  fireEvent.pointerUp(canvas, { pointerId: 1, pointerType: 'mouse', button: 0, clientX: 630, clientY: 350 });
  expect(cursor()).toEqual(['cursor-grab']);
  dispose();
});

it("the host's notice shows at the top-right once the drawing is on screen", async () => {
  const { pane, dispose } = await openDrawing('composer', <div role="dialog" aria-label="Allow Analytics" />);
  expect(within(pane).getByRole('dialog', { name: 'Allow Analytics' }).closest('[data-viewport-top-right]')).not.toBeNull();
  dispose();
});

it('a DXF has no panels of its own, no tools and no preview', async () => {
  const { pane, delivered, dispose } = await openDrawing();
  // The nav row's only panel is the host's file tree, closed: a drawing declares none.
  const panels = [...pane.querySelectorAll('[data-file-panel]')]
    .map(button => `${button.getAttribute('aria-label')}:${button.getAttribute('aria-pressed')}`);
  expect(panels).toEqual(['Show files:false']);
  expect(pane.querySelectorAll('[data-tool-panel]')).toHaveLength(0);
  const inPane = within(pane);
  expect(inPane.queryByRole('group', { name: 'Interaction tools' })).toBeNull();
  for (const name of ['Orbit', 'Draw', 'Select', 'Measure', 'Position', 'Animate', 'Preview',
    'Switch to 2D view', 'Switch to 3D view', 'Display settings', 'Zoom in', 'Zoom out', 'Reset Zoom', 'Zoom to fit', 'Zoom controls']) {
    expect(inPane.queryByRole('button', { name }), name).toBeNull();
  }
  expect(inPane.queryAllByRole('tab')).toHaveLength(0);
  // A composer gets no snapshot from a drawing, and a drawing has nothing to pick: no Quick Edit,
  // which is a STEP file's.
  expect(inPane.queryByRole('button', { name: 'Take snapshot' })).toBeNull();
  expect(pane.querySelector('[data-viewport-bottom-actions]')).toBeNull();
  expect(pane.querySelector('[data-quick-edit]')).toBeNull();
  expect(delivered).toHaveLength(0);
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
  await expect(controller.select({ selectors: ['o1.f1'] })).rejects.toThrow(/A DXF is a 2D drawing without CAD references/);
  await expect(controller.clearSelection()).rejects.toThrow(/never has a selection to clear/);
  await expect(controller.setCamera({ position: [0, 0, 1], target: [0, 0, 0], up: [0, 1, 0] })).rejects.toThrow(/no camera to pose/);
  await expect(controller.setRenderMode(true)).rejects.toThrow(/no Display settings/);
  await expect(controller.setDisplaySettings({ edges: { enabled: false } })).rejects.toThrow(/no Display settings/);

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

it('a select-reference request is consumed without a notification', async () => {
  const { pane, commands, request, dispose } = await openDrawing();
  await request({ selectReference: { selector: 'o1.f1', key: 7 } });
  await waitFor(() => expect(commands.getSnapshot().selectReference ?? null).toBeNull());
  expect(commands.acknowledge).toHaveBeenCalledWith('selectReference', 7);
  // Declined silently: no alert, no status, and the drawing is still the drawing.
  expect(within(pane).queryByRole('alert')).toBeNull();
  expect(pane.querySelector('[data-drawing-surface] canvas')).not.toBeNull();
  dispose();
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
