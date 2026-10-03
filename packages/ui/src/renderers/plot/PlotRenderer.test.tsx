import { StrictMode, useState } from 'react';
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createCadClient } from '@text-to-cad/core/client';
import { FileViewer } from '../../../dist/file-viewer/index.js';
import { createPlotRenderer } from '../../../dist/renderers/plot/index.js';
// Loaded with the file, not inside the first test: the registration imports it lazily.
import '../../../dist/renderers/plot/PlotRenderer.js';
import BOARD from './__fixtures__/board.plot.json';
import SCHEMATIC from './__fixtures__/schematic.plot.json';
import HARNESS from './__fixtures__/harness.plot.json';

// The plot tab's states and its answers to the host, mounted the way a host mounts it: the
// FileViewer over the real registration and a real CAD client, whose backend is a fetch that
// answers with a committed `/__cad/plot` payload. The pixels are the browser suite's; what is
// decided here is what the tab shows when, and what a host is told.

// Every frame the pane paints is a `drawPlot` with the view's transform: the picture itself is
// not jsdom's to draw. A frame of the pane carries a pixel ratio; a raster of the SVGs does not.
const frames = vi.hoisted(() => [] as Array<{ scale: number; offsetX: number; offsetY: number }>);
vi.mock('@text-to-cad/core/lib/plot2d/index.js', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, drawPlot: (_ctx: unknown, _layout: unknown, { transform, pixelRatio }: { transform: any; pixelRatio?: number }) => {
    if (pixelRatio !== undefined) frames.push({ ...transform });
  } };
});

const noop = () => {};
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const INSTALL = "KiCad's command line, kicad-cli, was not found: install KiCad 10 from https://www.kicad.org/download/.";
let readPlot: (file: string) => Response = () => json(BOARD);
const DESTINATION = { kind: 'clipboard', available: true };
const context2d = new Proxy({}, { get: (_target, key) => (key === 'canvas' ? undefined : noop), set: () => true });

beforeEach(() => {
  frames.length = 0;
  readPlot = (file) => (file.endsWith('.kicad_sch') ? json(SCHEMATIC) : file.endsWith('.harness.yml') ? json(HARNESS) : json(BOARD));
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => setTimeout(() => callback(performance.now()), 0));
  vi.stubGlobal('cancelAnimationFrame', (handle: number) => clearTimeout(handle));
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: false, media: query, addEventListener: noop, removeEventListener: noop, addListener: noop, removeListener: noop }));
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  // jsdom decodes no images and makes no object URLs: a sheet's SVG decodes at once.
  vi.stubGlobal('Image', class { decoding = ''; src = ''; decode() { return Promise.resolve(); } });
  Object.assign(URL, { createObjectURL: () => 'blob:sheet', revokeObjectURL: noop });
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(
    { x: 0, y: 0, left: 0, top: 0, right: 1200, bottom: 700, width: 1200, height: 700, toJSON: noop } as DOMRect);
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context2d as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(function (callback, type) {
    setTimeout(() => callback(new Blob(['png'], { type: type || 'image/png' })), 0);
  });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

/** One pane: a host, a workspace with one KiCad file, a live binding, and the tab. */
async function open(file: string, { strict = false } = {}) {
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    if (url.pathname.endsWith('/__cad/catalog')) {
      const kind = file.endsWith('.harness.yml') ? 'harness' : file.split('.').pop();
      return json({ rootId: 'one', entries: [{ kind, file, rootRelativeFile: file, url: `/${file}`, hash: 'one', bytes: 4096 }] });
    }
    if (url.pathname.endsWith('/__cad/server')) return json({ rootId: 'one', rootPath: '/models', backend: 'cadgen' });
    if (url.pathname.endsWith('/__cad/plot')) return readPlot(url.searchParams.get('file') || '');
    return new Response('', { status: 404 });
  });
  const client = createCadClient({ origin: 'http://viewer.test/one', workspaceId: 'one', pollIntervalMs: 0, fetch: fetch as typeof globalThis.fetch });
  await client.refresh();
  let controller: any = null;
  const live = { bind(next: unknown) { controller = next; return () => { controller = null; }; } };
  const renderers = [createPlotRenderer({ client, live })];
  const host = {
    files: { id: 'one', rootName: 'one', stat: async (path: string) => ({ path, name: path, kind: 'file', size: 400, extension: path.split('.').pop() }),
      list: async () => [{ path: file, name: file, kind: 'file' }] },
    navigation: { openFile: noop },
    environment: { colorScheme: 'light' },
    clipboard: { writeText: async () => {}, readText: async () => '', writeImage: async () => {} },
    promptContext: { getSnapshot: () => DESTINATION, subscribe: () => noop, deliver: async () => ({ status: 'copied', partIds: [] }) }
  };
  function Pane() {
    const [state, setState] = useState<any>({ panel: null, renderers: {} });
    return <section data-testid="pane"><FileViewer file={file} host={host as any} renderers={renderers} state={state} onStateChange={setState} /></section>;
  }
  render(strict ? <StrictMode><Pane /></StrictMode> : <Pane />);
  const pane = screen.getByTestId('pane');
  return { pane, get controller() { return controller; }, dispose: () => client.dispose() };
}

const opened = async (pane: HTMLElement) => {
  await waitFor(() => expect(pane.querySelector('[data-plot-surface] [aria-busy="false"]')).not.toBeNull());
  await waitFor(() => expect(frames.length).toBeGreaterThan(0));
};

it('a board opens as a picture and nothing else: no panel, no tools, no preview, no Quick Edit', async () => {
  const { pane, dispose } = await open('blinky.kicad_pcb');
  await opened(pane);
  expect(pane.querySelector('canvas')?.getAttribute('aria-label')).toBe('Board: blinky.kicad_pcb');
  const panels = [...pane.querySelectorAll('[data-file-panel]')].map(button => button.getAttribute('aria-label'));
  expect(panels).toEqual(['Show files']);
  const inPane = within(pane);
  expect(inPane.queryByRole('group', { name: 'Interaction tools' })).toBeNull();
  for (const name of ['Orbit', 'Draw', 'Select', 'Measure', 'Preview', 'Display settings', 'Zoom in', 'Reset Zoom', 'Take snapshot']) {
    expect(inPane.queryByRole('button', { name }), name).toBeNull();
  }
  expect(pane.querySelector('[data-quick-edit]')).toBeNull();
  expect(inPane.queryByRole('alert')).toBeNull();
  dispose();
});

it('paints after a StrictMode remount, as the development app mounts it', async () => {
  const { pane, dispose } = await open('blinky.kicad_pcb', { strict: true });
  await opened(pane);
  dispose();
});

it('a machine without KiCad gets the standard card, carrying the server’s install hint', async () => {
  readPlot = () => json({ error: INSTALL }, 400);
  const { pane, dispose } = await open('blinky.kicad_pcb');
  const alert = await within(pane).findByRole('alert');
  expect(alert.textContent).toContain('The viewer couldn’t complete the request');
  expect(alert.textContent).toContain('HTTP 400');
  expect(alert.textContent).toContain('install KiCad 10');
  expect(pane.querySelector('[data-viewer-loading]')).toBeNull();
  expect(frames).toHaveLength(0);
  dispose();
});

it('host commands a plot cannot answer are declined in its own words; it fits and captures', async () => {
  const schematic = await open('blinky.kicad_sch');
  await opened(schematic.pane);
  expect(schematic.pane.querySelector('canvas')?.getAttribute('aria-label')).toBe('Schematic: blinky.kicad_sch');
  const controller = await waitFor(() => { expect(schematic.controller).not.toBeNull(); return schematic.controller; });
  await expect(controller.select({ selectors: ['o1.f1'] })).rejects.toThrow(/A schematic is shown as the picture KiCad draws of it/);
  await expect(controller.clearSelection()).rejects.toThrow(/never has a selection to clear/);
  await expect(controller.setCamera({ position: [0, 0, 1], target: [0, 0, 0], up: [0, 1, 0] })).rejects.toThrow(/no camera to pose/);
  await expect(controller.setDisplaySettings({ edges: { enabled: false } })).rejects.toThrow(/no Display settings: it is drawn in KiCad’s own colours/);
  expect(controller.readState()).toMatchObject({ active: true, loading: false, camera: null, selection: [] });
  const fitted = frames.at(-1)!;
  await act(async () => { await controller.resetCamera(); });
  expect(frames.at(-1)).toEqual(fitted);
  const blob = await controller.capture();
  expect(blob.type).toBe('image/png');
  schematic.dispose();
});

it('a wiring harness opens in the same pane, and is called a harness drawn by WireViz', async () => {
  const harness = await open('cable.harness.yml');
  await opened(harness.pane);
  expect(harness.pane.querySelector('canvas')?.getAttribute('aria-label')).toBe('Harness: cable.harness.yml');
  const controller = await waitFor(() => { expect(harness.controller).not.toBeNull(); return harness.controller; });
  await expect(controller.select({ selectors: ['o1.f1'] })).rejects.toThrow(/A harness is shown as the picture WireViz draws of it/);
  await expect(controller.setRenderMode(true)).rejects.toThrow(/drawn in WireViz’s own colours/);
  harness.dispose();
});
