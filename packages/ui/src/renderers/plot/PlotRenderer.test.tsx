import { StrictMode, useState } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createCadClient } from '@text-to-cad/core/client';
import { FileViewer } from '../../../dist/file-viewer/index.js';
import { createPlotRenderer } from '../../../dist/renderers/plot/index.js';
import { pageToScreen } from '@text-to-cad/core/lib/plot2d/plot.js';
// Loaded with the file, not inside the first test: the registration imports it lazily.
import '../../../dist/renderers/plot/PlotRenderer.js';
import BOARD from './__fixtures__/board.plot.json';

// The plot tab's states and its answers to the host, mounted the way a host mounts it: the
// FileViewer over the real registration and a real CAD client, whose backend is a fetch that
// answers with the committed `/__cad/plot` payload (`__fixtures__/README.md`: J1 at (5, 15), R1 at
// (35, 15), D1 at (20, 24), in KiCad's millimetres, which are the sheet's here). The pixels are the
// browser suite's; what is decided here is what the tab shows when, and what a host is told.

// Every frame the pane paints places its rasters with `drawPlotImages` under the view's transform;
// the rasters themselves are `drawPlot`, which jsdom cannot draw and the pixels are not its to check.
const frames = vi.hoisted(() => [] as Array<{ scale: number; offsetX: number; offsetY: number }>);
vi.mock('@text-to-cad/core/lib/plot2d/index.js', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    drawPlot: () => {},
    drawPlotImages: (_ctx: unknown, _layout: unknown, { transform }: { transform: any }) => { frames.push({ ...transform }); }
  };
});

const noop = () => {};
const copied: string[] = [];
// A clipboard that refuses, as a browser does without the page's focus.
let refuseCopy: Error | null = null;
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const UNREADABLE = 'broken.kicad_pcb is not a KiCad board: a .kicad_pcb starts with (kicad_pcb ...)';
let readPlot: (file: string) => Response | Promise<Response> = () => json(BOARD);
const DESTINATION = { kind: 'clipboard', available: true };
const context2d = new Proxy({}, { get: (_target, key) => (key === 'canvas' ? undefined : noop), set: () => true });

beforeEach(() => {
  frames.length = 0;
  copied.length = 0;
  refuseCopy = null;
  readPlot = () => json(BOARD);
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => setTimeout(() => callback(performance.now()), 0));
  vi.stubGlobal('cancelAnimationFrame', (handle: number) => clearTimeout(handle));
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: false, media: query, addEventListener: noop, removeEventListener: noop, addListener: noop, removeListener: noop }));
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(
    { x: 0, y: 0, left: 0, top: 0, right: 1200, bottom: 700, width: 1200, height: 700, toJSON: noop } as DOMRect);
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context2d as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(function (callback, type) {
    setTimeout(() => callback(new Blob(['png'], { type: type || 'image/png' })), 0);
  });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

/** One pane: a host, a workspace with one board (`name`, under `/models`), a live binding, and the tab. */
async function open(name: string, { strict = false } = {}) {
  const file = `/models/${name}`;
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    if (url.pathname.endsWith('/__cad/catalog')) return json({ entries: [{ kind: 'kicad_pcb', file, url: `/${name}`, hash: 'one', bytes: 4096 }] });
    if (url.pathname.endsWith('/__cad/server')) return json({ backend: 'cadgen' });
    if (url.pathname.endsWith('/__cad/plot')) return readPlot(url.searchParams.get('file') || '');
    return new Response('', { status: 404 });
  });
  const client = createCadClient({ origin: 'http://viewer.test/one', pollIntervalMs: 0, fetch: fetch as typeof globalThis.fetch });
  await client.refresh();
  let controller: any = null;
  const live = { bind(next: unknown) { controller = next; return () => { controller = null; }; } };
  const renderers = [createPlotRenderer({ client, live })];
  const host = {
    files: { id: 'one', stat: async (path: string) => ({ path, name: path.split('/').pop(), kind: 'file', size: 400, extension: path.split('.').pop() }) },
    navigation: { openFile: noop },
    environment: { colorScheme: 'light' },
    clipboard: { writeText: async (text: string | Promise<string>) => { if (refuseCopy) throw refuseCopy; copied.push(await text); }, readText: async () => '', writeImage: async () => {} },
    promptContext: { getSnapshot: () => DESTINATION, subscribe: () => noop, deliver: async () => ({ status: 'copied', partIds: [] }) },
  };
  let latest: any = { renderers: {} };
  function Pane() {
    const [state, setState] = useState<any>(latest);
    latest = state;
    return <section data-testid="pane"><FileViewer file={file} host={host as any} renderers={renderers} state={state} onStateChange={setState} /></section>;
  }
  render(strict ? <StrictMode><Pane /></StrictMode> : <Pane />);
  const pane = screen.getByTestId('pane');
  return { pane, get controller() { return controller; }, get state() { return latest; }, dispose: () => client.dispose() };
}

// The navbar's right end, in order: the alert's icon, then the view's controls (`data-view-controls`).
const navbarControls = (pane: HTMLElement) => [...pane.querySelectorAll('[data-viewer-navbar] > :last-child button')].map((button) => button.getAttribute('aria-label'));

const opened = async (pane: HTMLElement) => {
  await waitFor(() => expect(pane.querySelector('[data-plot-surface] [aria-busy="false"]')).not.toBeNull());
  await waitFor(() => expect(frames.length).toBeGreaterThan(0));
};

it('a plot without its index opens as the picture alone: no tools, no panel, no Quick Edit', async () => {
  const { board: _index, ...picture } = BOARD;
  readPlot = () => json(picture);
  const { pane, dispose } = await open('blinky.kicad_pcb');
  await opened(pane);
  expect(pane.querySelector('canvas')?.getAttribute('aria-label')).toBe('Board: blinky.kicad_pcb');
  const inPane = within(pane);
  expect(inPane.queryByRole('group', { name: 'Interaction tools' })).toBeNull();
  for (const name of ['Orbit', 'Draw', 'Select', 'Measure', 'Preview', 'Zoom in', 'Reset Zoom', 'Take snapshot']) {
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

it('a file that is no board gets the standard card, carrying the server’s own sentence', async () => {
  readPlot = () => json({ error: UNREADABLE }, 400);
  const { pane, dispose } = await open('broken.kicad_pcb');
  const alert = await within(pane).findByRole('alert');
  expect(alert.textContent).toContain('The viewer couldn’t complete the request');
  expect(alert.textContent).toContain('HTTP 400');
  expect(alert.textContent).toContain('is not a KiCad board');
  expect(pane.querySelector('[data-viewer-loading]')).toBeNull();
  expect(frames).toHaveLength(0);
  dispose();
});

it('a board has no Display while it loads or once it failed to, as a 3D view has none then', async () => {
  let answer: ((response: Response) => void) | null = null;
  readPlot = () => new Promise<Response>((resolve) => { answer = resolve; });
  const { pane, dispose } = await open('blinky.kicad_pcb');
  // The plot asked for and not yet answered: the board is loading.
  await waitFor(() => expect(answer).not.toBeNull());
  expect(pane.querySelector('[data-viewer-navbar] [data-view-controls]')).not.toBeNull();
  expect(within(pane).queryByRole('button', { name: 'Display' })).toBeNull();
  await act(async () => { answer!(json({ error: UNREADABLE }, 400)); });
  await within(pane).findByRole('alert');
  expect(within(pane).queryByRole('button', { name: 'Display' })).toBeNull();
  dispose();
});

it('host commands a plot cannot answer are declined in its own words; it fits and captures', async () => {
  const view = await open('blinky.kicad_pcb');
  await opened(view.pane);
  const controller = await waitFor(() => { expect(view.controller).not.toBeNull(); return view.controller; });
  await expect(controller.setCamera({ position: [0, 0, 1], target: [0, 0, 0], up: [0, 1, 0] })).rejects.toThrow(/no camera to pose/);
  await expect(controller.setDisplaySettings({ edges: { enabled: false } })).rejects.toThrow(/Display settings .* are set in the view’s Display menu/);
  expect(controller.readState()).toMatchObject({ active: true, loading: false, camera: null, selection: [] });
  const fitted = frames.at(-1)!;
  await act(async () => { await controller.resetCamera(); });
  expect(frames.at(-1)).toEqual(fitted);
  const blob = await controller.capture();
  expect(blob.type).toBe('image/png');
  view.dispose();
});

it('a board with its index has Select alone, its parts and nets, and hands references to Quick Edit', async () => {
  const { pane, dispose } = await open('blinky.kicad_pcb');
  await opened(pane);
  const inPane = within(pane);
  const tools = await inPane.findByRole('group', { name: 'Interaction tools' });
  expect(within(tools).getByRole('button', { name: 'Select' }).getAttribute('aria-pressed')).toBe('true');
  // Select only: neither Draw nor Measure is asked of the shell, and no Drawing panel can come up.
  expect(within(tools).getAllByRole('button').map((button) => button.getAttribute('aria-label'))).toEqual(['Select']);
  for (const name of ['Draw', 'Measure', 'Orbit', 'Explode', 'Clip', 'Position', 'Preview']) expect(inPane.queryByRole('button', { name }), name).toBeNull();
  // A board drawn layer by layer has its Display where a 3D view's is, the view's controls at the navbar's right end; no Preview.
  expect([...pane.querySelectorAll('[data-viewer-navbar] [data-view-controls] button')].map((button) => button.getAttribute('aria-label'))).toEqual(['Display']);
  expect(navbarControls(pane).at(-1)).toBe('Display');
  // The tree: parts by kind, then nets.
  expect(inPane.getByRole('button', { name: 'Parts' })).not.toBeNull();
  expect(inPane.getByRole('button', { name: 'Nets' })).not.toBeNull();
  await act(async () => { inPane.getByRole('button', { name: 'Expand Resistors' }).click(); });
  await act(async () => { inPane.getByRole('button', { name: 'Select R1' }).click(); });
  const reference = pane.querySelector('[data-board-reference]')!;
  expect(reference.textContent).toContain('R_0603_1608Metric');
  // Read back in KiCad's own millimetres, y down.
  expect(reference.textContent).toContain('x 35, y 15');
  expect(reference.textContent).toContain('#R1');
  expect(pane.querySelector('[data-quick-edit]')?.textContent).toContain('1 ref');
  await act(async () => { inPane.getByRole('button', { name: 'Copy' }).click(); });
  await waitFor(() => expect(copied).toEqual(['/models/blinky.kicad_pcb#R1']));
  dispose();
});

it('Display lists the board’s layers as checkboxes; one unticked reads as Custom and is kept with the file’s view', async () => {
  const view = await open('blinky.kicad_pcb');
  const { pane, dispose } = view;
  await opened(pane);
  const framesBefore = frames.length;
  fireEvent.click(within(pane.querySelector<HTMLElement>('[data-view-controls]')!).getByRole('button', { name: 'Display' }));
  const popover = await waitFor(() => { const found = document.querySelector<HTMLElement>('[data-display-popover]'); expect(found).not.toBeNull(); return found!; });
  const inPopover = within(popover);
  expect(inPopover.getAllByRole('heading').map((heading) => heading.textContent)).toEqual(['Display', 'Layers']);
  expect(inPopover.getAllByRole('group').map((group) => group.getAttribute('aria-label'))).toEqual(['Front layers', 'Back layers', 'Other layers']);
  const copper = inPopover.getByRole('checkbox', { name: 'F.Cu' }) as HTMLInputElement;
  expect(copper.checked).toBe(true);
  expect(inPopover.getByRole('combobox', { name: 'Mode' }).textContent).toContain('Board');
  await act(async () => { fireEvent.click(copper); });
  expect((inPopover.getByRole('checkbox', { name: 'F.Cu' }) as HTMLInputElement).checked).toBe(false);
  expect(inPopover.getByRole('combobox', { name: 'Mode' }).textContent).toContain('Custom');
  // The pane draws the board again for the new view, and the file's view keeps the set.
  await waitFor(() => expect(frames.length).toBeGreaterThan(framesBefore));
  const key = JSON.stringify(['/models/blinky.kicad_pcb', 'plot']);
  await waitFor(() => expect(view.state.renderers?.[key]?.renderer?.board?.value?.layers).toEqual(
    ['B.Mask', 'B.Cu', 'F.Mask', 'F.Paste', 'F.SilkS', 'F.Fab', 'Edge.Cuts', 'vias', 'ratsnest', 'drills']));
  // Ticked again, the set is the mode's own: stored as the mode's, so a rebuild's new layer follows it.
  await act(async () => { fireEvent.click(inPopover.getByRole('checkbox', { name: 'F.Cu' })); });
  expect(inPopover.getByRole('combobox', { name: 'Mode' }).textContent).toContain('Board');
  await waitFor(() => expect(view.state.renderers?.[key]?.renderer?.board?.value).toEqual({ mode: 'board', side: 'top', poured: true, layers: null }));
  dispose();
});

it('a copy the clipboard refuses says it was a copy that failed, and why', async () => {
  const { pane, dispose } = await open('blinky.kicad_pcb');
  await opened(pane);
  const inPane = within(pane);
  await act(async () => { inPane.getByRole('button', { name: 'Expand Resistors' }).click(); });
  await act(async () => { inPane.getByRole('button', { name: 'Select R1' }).click(); });
  refuseCopy = new Error('Document is not focused.');
  await act(async () => { inPane.getByRole('button', { name: 'Copy' }).click(); });
  const alert = await inPane.findByRole('alert');
  expect(alert.textContent).toContain('Couldn’t copy from the board');
  expect(alert.textContent).toContain('Document is not focused.');
  expect(alert.textContent).not.toContain('capture');
  dispose();
});

it('a board still loading tells a host selecting on it to wait, not that it has nothing to select', async () => {
  let release: (response: Response) => void = noop;
  readPlot = () => new Promise<Response>((resolve) => { release = resolve; });
  const view = await open('blinky.kicad_pcb');
  const controller = await waitFor(() => { expect(view.controller).not.toBeNull(); return view.controller; });
  await expect(controller.select({ selectors: ['#R1'] })).rejects.toThrow(/Wait for the displayed model revision to finish loading/);
  await act(async () => { release(json(BOARD)); });
  await opened(view.pane);
  const state = await view.controller.select({ selectors: ['#R1'] });
  expect(state.selection[0].target.selectors).toEqual(['#R1']);
  view.dispose();
});

it('the live controller selects board references, reads them back, and refuses what the board lacks', async () => {
  const view = await open('blinky.kicad_pcb');
  const { pane, dispose } = view;
  await opened(pane);
  const controller = await waitFor(() => { expect(view.controller).not.toBeNull(); return view.controller; });
  const state = await controller.select({ selectors: ['#J1.2', '#net:VBUS'] });
  expect(state.selection).toEqual([expect.objectContaining({ target: { kind: 'cad-selector', selectors: ['#J1.2', '#net:VBUS'] } })]);
  expect(pane.querySelector('[data-quick-edit]')?.textContent).toContain('2 refs');
  await expect(controller.select({ selectors: ['#U9'] })).rejects.toThrow(/Not on this board: #U9/);
  const cleared = await controller.clearSelection();
  expect(cleared.selection).toEqual([]);
  dispose();
});

// A press on the picture, where page point `at` is on screen in the last frame painted.
const press = async (pane: HTMLElement, at: [number, number], { double = false, shift = false } = {}) => {
  const canvas = pane.querySelector('canvas')!;
  const [clientX, clientY] = pageToScreen(frames.at(-1), at[0], at[1]);
  await act(async () => {
    canvas.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, clientX, clientY, button: 0, shiftKey: shift }));
    canvas.dispatchEvent(new MouseEvent('pointerup', { bubbles: true, clientX, clientY, button: 0, shiftKey: shift }));
    if (double) canvas.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, clientX, clientY }));
  });
};

it('a press on a pad selects it, a shift-press adds its neighbour, and a double-click copies one', async () => {
  const view = await open('blinky.kicad_pcb');
  const { pane, dispose } = view;
  await opened(pane);
  const controller = await waitFor(() => { expect(view.controller).not.toBeNull(); return view.controller; });
  await press(pane, [34.175, 15]);
  expect(controller.readState().selection[0].target.selectors).toEqual(['#R1.1']);
  await press(pane, [35.825, 15], { shift: true });
  expect(controller.readState().selection[0].target.selectors).toEqual(['#R1.1', '#R1.2']);
  await press(pane, [5, 17.54], { double: true });
  await waitFor(() => expect(copied).toEqual(['/models/blinky.kicad_pcb#J1.2']));
  // A press on the track takes its net's copper there, in KiCad's frame; bare board clears.
  await press(pane, [30, 15]);
  expect(controller.readState().selection[0].target.selectors).toEqual(['#net:VBUS@x30y15']);
  await press(pane, [36, 26]);
  expect(controller.readState().selection).toEqual([]);
  dispose();
});
