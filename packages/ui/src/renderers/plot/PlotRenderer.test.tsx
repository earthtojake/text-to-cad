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
const copied: string[] = [];
// A clipboard that refuses, as a browser does without the page's focus.
let refuseCopy: Error | null = null;
// A 40 x 30 mm board's index, in sheet millimetres (y down), its script origin at sheet (5, 25).
const square = (cx: number, cy: number, w: number, h: number) => [[cx - w / 2, cy - h / 2], [cx + w / 2, cy - h / 2], [cx + w / 2, cy + h / 2], [cx - w / 2, cy + h / 2]];
const INDEX = {
  origin: [5, 25],
  nets: [{ name: 'VIN', class: 'Default' }, { name: 'GND', class: 'Default' }],
  parts: [
    { ref: 'R1', value: '10k', footprint: 'Resistor_SMD:R_0603_1608Metric', side: 'top', at: [15, 20], rotation: 0, fields: { MPN: 'RC0603' }, script: 'blinky.py:12', outline: square(15, 20, 3, 1.4) },
    { ref: 'J1', value: 'Conn', footprint: 'Connector:PinHeader_1x02', side: 'top', at: [30, 10], rotation: 90, fields: {}, outline: square(30, 10, 3, 6) },
  ],
  pads: [
    { part: 'R1', number: '1', name: '~', net: 'VIN', type: 'passive', side: 'top', at: [14.175, 20], polygon: square(14.175, 20, 0.8, 0.95) },
    { part: 'R1', number: '2', name: '~', net: 'GND', type: 'passive', side: 'top', at: [15.825, 20], polygon: square(15.825, 20, 0.8, 0.95) },
    { part: 'J1', number: '1', name: '', net: 'VIN', type: 'passive', side: 'both', at: [30, 8.73], polygon: square(30, 8.73, 1.7, 1.7) },
    { part: 'J1', number: '2', name: '', net: 'GND', type: 'passive', side: 'both', at: [30, 11.27], polygon: square(30, 11.27, 1.7, 1.7) },
  ],
  tracks: [{ net: 'VIN', layer: 'F.Cu', width: 0.5, points: [[14.175, 20], [14.175, 8.73], [30, 8.73]] }],
  vias: [], zones: [], holes: [], outline: [[[0, 0], [40, 0], [40, 30], [0, 30], [0, 0]]],
  findings: [{ check: 'drc', severity: 'warning', type: 'silk_overlap', description: 'Silkscreen clearance', items: [{ text: 'Reference field of R1', ref: '#R1', at: [15, 20] }] }],
};
// A two-sheet schematic's index, in each sheet's millimetres: R1 and U1's first unit on the root,
// U1's second unit (and its common pin 4) on "power".
const SCHEMATIC_INDEX = {
  sheets: [{ name: 'blinky', path: '/', file: 'blinky.kicad_sch', title: 'Blinky' }, { name: 'power', path: '/power/', file: 'power.kicad_sch', title: '' }],
  parts: [
    { ref: 'R1', value: '10k', lib: 'Device:R', footprint: 'Resistor_SMD:R_0603_1608Metric', fields: { MPN: 'RC0603' }, script: 'blinky.py:12', dnp: false,
      units: [{ unit: 1, sheet: 0, at: [50, 50], rotation: 0, mirror: null, outline: square(50, 50, 2, 5) }] },
    { ref: 'U1', value: 'LM358', lib: 'Amplifier_Operational:LM358', footprint: 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm', fields: {}, script: 'blinky.py:20', dnp: false,
      units: [{ unit: 1, sheet: 0, at: [80, 50], rotation: 0, mirror: null, outline: square(80, 50, 10, 10) },
        { unit: 3, sheet: 1, at: [30, 30], rotation: 0, mirror: null, outline: square(30, 30, 6, 6) }] },
  ],
  pins: [
    { part: 'R1', number: '1', name: '~', type: 'passive', unit: 1, sheet: 0, net: 'VIN', at: [50, 46.19], end: [50, 47.5], hidden: false },
    { part: 'R1', number: '2', name: '~', type: 'passive', unit: 1, sheet: 0, net: 'GND', at: [50, 53.81], end: [50, 52.5], hidden: false },
    { part: 'U1', number: '3', name: '+', type: 'input', unit: 1, sheet: 0, net: 'VIN', at: [72.38, 50], end: [75, 50], hidden: false },
    { part: 'U1', number: '8', name: 'V+', type: 'power_in', unit: 3, sheet: 1, net: 'VIN', at: [30, 24.92], end: [30, 27], hidden: false },
  ],
  wires: [{ net: 'VIN', sheet: 0, points: [[50, 46.19], [50, 43.18], [72.38, 43.18], [72.38, 50]] }],
  labels: [{ net: 'VIN', sheet: 1, text: 'VIN', kind: 'global', at: [30, 20], outline: [[30, 19.3], [36, 19.3], [36, 20.7], [30, 20.7]] }],
  junctions: [], noConnects: [],
  nets: [{ name: 'GND', class: 'Default' }, { name: 'VIN', class: 'Power' }],
};
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const INSTALL = "KiCad's command line, kicad-cli, was not found: install KiCad 10 from https://www.kicad.org/download/.";
let readPlot: (file: string) => Response | Promise<Response> = () => json(BOARD);
const DESTINATION = { kind: 'clipboard', available: true };
const context2d = new Proxy({}, { get: (_target, key) => (key === 'canvas' ? undefined : noop), set: () => true });

beforeEach(() => {
  frames.length = 0;
  copied.length = 0;
  refuseCopy = null;
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

/** One pane: a host, a workspace with one KiCad file (`name`, under `/models`), a live binding, and the tab. */
async function open(name: string, { strict = false, crossProbe = undefined as unknown } = {}) {
  const file = `/models/${name}`;
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    if (url.pathname.endsWith('/__cad/catalog')) {
      const kind = name.endsWith('.harness.yml') ? 'harness' : name.split('.').pop();
      return json({ entries: [{ kind, file, url: `/${name}`, hash: 'one', bytes: 4096 }] });
    }
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
    ...(crossProbe ? { crossProbe } : {})
  };
  function Pane() {
    const [state, setState] = useState<any>({ renderers: {} });
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

it('a plot with no index (a harness) opens as a picture and nothing else: no panel, no tools, no preview, no Quick Edit', async () => {
  const { pane, dispose } = await open('cable.harness.yml');
  await opened(pane);
  expect(pane.querySelector('canvas')?.getAttribute('aria-label')).toBe('Harness: cable.harness.yml');
  const inPane = within(pane);
  expect(inPane.queryByRole('group', { name: 'Interaction tools' })).toBeNull();
  for (const name of ['Orbit', 'Draw', 'Select', 'Measure', 'Preview', 'Display', 'Zoom in', 'Reset Zoom', 'Take snapshot']) {
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

it('a board with its index has Select and Measure, its parts and nets, and hands references to Quick Edit', async () => {
  readPlot = (file) => (file.endsWith('.kicad_pcb') ? json({ ...BOARD, board: INDEX }) : json(SCHEMATIC));
  const { pane, dispose } = await open('blinky.kicad_pcb');
  await opened(pane);
  const inPane = within(pane);
  const tools = await inPane.findByRole('group', { name: 'Interaction tools' });
  expect(within(tools).getByRole('button', { name: 'Select' }).getAttribute('aria-pressed')).toBe('true');
  expect(within(tools).getAllByRole('button').map((button) => button.getAttribute('aria-label'))).toEqual(['Select', 'Draw', 'Measure']);
  for (const name of ['Orbit', 'Explode', 'Clip', 'Position', 'Preview']) expect(inPane.queryByRole('button', { name }), name).toBeNull();
  // A board drawn layer by layer has its Display dropdown in the bottom-left corner, where a 3D view's sits on its cube.
  expect(inPane.getByRole('button', { name: 'Display' })).not.toBeNull();
  // The tree: parts by kind, then nets; what KiCad reported is the alert card's.
  expect(inPane.getByRole('button', { name: 'Parts' })).not.toBeNull();
  expect(inPane.getByRole('button', { name: 'Nets' })).not.toBeNull();
  expect(inPane.queryByRole('button', { name: 'Checks' })).toBeNull();
  await act(async () => { inPane.getByRole('button', { name: 'Expand Resistors' }).click(); });
  await act(async () => { inPane.getByRole('button', { name: 'Select R1' }).click(); });
  const reference = pane.querySelector('[data-board-reference]')!;
  expect(reference.textContent).toContain('R_0603_1608Metric');
  expect(reference.textContent).toContain('x 10, y 5');
  expect(reference.textContent).toContain('blinky.py:12');
  expect(reference.textContent).toContain('#R1');
  expect(pane.querySelector('[data-quick-edit]')?.textContent).toContain('1 ref');
  await act(async () => { inPane.getByRole('button', { name: 'Copy' }).click(); });
  await waitFor(() => expect(copied).toEqual(['/models/blinky.kicad_pcb#R1']));
  dispose();
});

it('a copy the clipboard refuses says it was a copy that failed, and why', async () => {
  readPlot = (file) => (file.endsWith('.kicad_pcb') ? json({ ...BOARD, board: INDEX }) : json(SCHEMATIC));
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
  await act(async () => { release(json({ ...BOARD, board: INDEX })); });
  await opened(view.pane);
  const state = await view.controller.select({ selectors: ['#R1'] });
  expect(state.selection[0].target.selectors).toEqual(['#R1']);
  view.dispose();
});

it('the live controller selects board references, reads them back, and refuses what the board lacks', async () => {
  readPlot = (file) => (file.endsWith('.kicad_pcb') ? json({ ...BOARD, board: INDEX }) : json(SCHEMATIC));
  const view = await open('blinky.kicad_pcb');
  const { pane, dispose } = view;
  await opened(pane);
  const controller = await waitFor(() => { expect(view.controller).not.toBeNull(); return view.controller; });
  const state = await controller.select({ selectors: ['#J1.2', '#net:VIN'] });
  expect(state.selection).toEqual([expect.objectContaining({ target: { kind: 'cad-selector', selectors: ['#J1.2', '#net:VIN'] } })]);
  expect(pane.querySelector('[data-quick-edit]')?.textContent).toContain('2 refs');
  await expect(controller.select({ selectors: ['#U9'] })).rejects.toThrow(/Not on this board: #U9/);
  const cleared = await controller.clearSelection();
  expect(cleared.selection).toEqual([]);
  dispose();
});

/** A cross-probe channel as a host's: what this view tells (`told`), and a way to tell it as another view would. */
function probeChannel() {
  const listeners = new Set<(message: any) => void>();
  const told: any[] = [];
  return {
    port: { publish: (message: any) => { told.push(message); }, subscribe: (listener: (message: any) => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; } },
    told,
    tell: (message: any) => act(() => { for (const listener of listeners) listener(message); }),
  };
}

it('cross-probing: a board selects what its schematic tells it, and tells what it selects', async () => {
  readPlot = (file) => (file.endsWith('.kicad_pcb') ? json({ ...BOARD, board: INDEX }) : json(SCHEMATIC));
  const channel = probeChannel();
  const view = await open('blinky.kicad_pcb', { crossProbe: channel.port });
  await opened(view.pane);
  const controller = await waitFor(() => { expect(view.controller).not.toBeNull(); return view.controller; });
  const selected = () => controller.readState().selection[0]?.target.selectors ?? [];
  expect(channel.told).toEqual([], 'opening tells nothing');

  // The schematic selects R1 and U1: the board has R1, and is not told it back.
  await channel.tell({ project: '/models/blinky', from: 'schematic', selectors: ['#R1', '#U1'] });
  await waitFor(() => expect(selected()).toEqual(['#R1']));
  expect(channel.told).toEqual([]);
  // Another project's selection, and one naming nothing on this board, leave it as it is.
  await channel.tell({ project: '/models/other', from: 'schematic', selectors: ['#J1'] });
  await channel.tell({ project: '/models/blinky', from: 'schematic', selectors: ['#U1'] });
  expect(selected()).toEqual(['#R1']);

  // What the board selects (a person, or the agent), it tells, as its project's.
  await controller.select({ selectors: ['#J1.2'] });
  await waitFor(() => expect(channel.told.at(-1)).toMatchObject({ project: '/models/blinky', selectors: ['#J1.2'] }));
  expect(channel.told.at(-1).from).not.toBe('schematic');
  // The schematic clearing clears it, and that is not told back either.
  const count = channel.told.length;
  await channel.tell({ project: '/models/blinky', from: 'schematic', selectors: [] });
  await waitFor(() => expect(selected()).toEqual([]));
  expect(channel.told).toHaveLength(count);
  view.dispose();
});

// What KiCad and the review found, as the plot hands it: one error and two suggestions.
const FINDINGS = [
  { check: 'review', severity: 'warning', type: 'decoupling_far', description: 'Decoupling capacitor far from its pin', summary: 'R1 is 9.1 mm from J1 (aim for under 3 mm)', items: [{ text: 'R1', ref: '#R1', at: null }] },
  { check: 'drc', severity: 'error', type: 'clearance', description: 'Clearance violation', summary: 'The VIN track and the GND pad of J1 are 0.15 mm apart; the rules need 0.2 mm',
    items: [{ text: 'Track', ref: '#net:VIN', at: [20, 8.73] }, { text: 'Pad 2 of J1', ref: '#J1.2', at: [30, 11.27] }] },
  { check: 'drc', severity: 'warning', type: 'silk_overlap', description: 'Silkscreen clearance', items: [{ text: 'Reference field of R1', ref: '#R1', at: [15, 20] }] },
];
const boardWith = (findings: unknown[]) => (file: string) => (file.endsWith('.kicad_pcb') ? json({ ...BOARD, board: { ...INDEX, findings } }) : json(SCHEMATIC));
const navbarAction = (pane: HTMLElement, name: string) => within(pane).queryByRole('button', { name });

it('a board with nothing to report has no card and no icon in the navbar', async () => {
  readPlot = boardWith([]);
  const { pane, dispose } = await open('blinky.kicad_pcb');
  await opened(pane);
  await within(pane).findByRole('group', { name: 'Interaction tools' });
  expect(within(pane).queryByRole('alert')).toBeNull();
  expect(pane.querySelector('svg.text-amber-500, svg.text-destructive')).toBeNull();
  dispose();
});

it('a board with suggestions alone puts its card away: an amber icon in the navbar says how many, and brings it back', async () => {
  readPlot = boardWith(FINDINGS.filter((finding) => finding.severity === 'warning'));
  const { pane, dispose } = await open('blinky.kicad_pcb');
  await opened(pane);
  const icon = await waitFor(() => { const found = navbarAction(pane, '2 suggestions'); expect(found).not.toBeNull(); return found!; });
  expect(icon.querySelector('svg')!.getAttribute('class')).toMatch(/text-amber-500/);
  expect(within(pane).queryByRole('alert')).toBeNull();
  await act(async () => { icon.click(); });
  const card = within(within(pane).getByRole('alert'));
  expect(card.getByRole('heading', { name: '2 suggestions' })).not.toBeNull();
  expect(card.queryByRole('heading', { name: 'Fix before ordering' })).toBeNull();
  expect(card.getByRole('heading', { name: 'Suggestions' })).not.toBeNull();
  expect(card.getByRole('button', { name: 'R1 is 9.1 mm from J1 (aim for under 3 mm)' })).not.toBeNull();
  // A finding without a sentence of its own reads as KiCad wrote it.
  expect(card.getByRole('button', { name: 'Silkscreen clearance' })).not.toBeNull();
  expect(card.queryByRole('link', { name: 'Report Issue' })).toBeNull();
  dispose();
});

it('a board with something to fix opens its card over the board, what to fix first', async () => {
  readPlot = boardWith(FINDINGS);
  const { pane, dispose } = await open('blinky.kicad_pcb');
  await opened(pane);
  const alert = await within(pane).findByRole('alert');
  const card = within(alert);
  expect(card.getByRole('heading', { name: '1 to fix, 2 suggestions' })).not.toBeNull();
  expect(card.getAllByRole('heading').map((heading) => heading.textContent)).toEqual(['1 to fix, 2 suggestions', 'Fix before ordering', 'Suggestions']);
  expect(card.getAllByRole('button').map((button) => button.textContent).filter((text) => text !== '')).toEqual([
    'The VIN track and the GND pad of J1 are 0.15 mm apart; the rules need 0.2 mm',
    'R1 is 9.1 mm from J1 (aim for under 3 mm)',
    'Silkscreen clearance',
  ]);
  expect(navbarAction(pane, '1 to fix, 2 suggestions')).toBeNull();
  dispose();
});

it('a finding in the card selects what it names, puts the card away and heads the Reference with its sentence', async () => {
  readPlot = boardWith(FINDINGS);
  const view = await open('blinky.kicad_pcb');
  const { pane, dispose } = view;
  await opened(pane);
  const sentence = 'The VIN track and the GND pad of J1 are 0.15 mm apart; the rules need 0.2 mm';
  const row = within(await within(pane).findByRole('alert')).getByRole('button', { name: sentence });
  await act(async () => { row.click(); });
  expect(view.controller.readState().selection[0]).toMatchObject({ target: { selectors: ['#net:VIN', '#J1.2'] }, summary: sentence });
  expect(within(pane).queryByRole('alert')).toBeNull();
  await waitFor(() => expect(navbarAction(pane, '1 to fix, 2 suggestions')?.querySelector('svg')!.getAttribute('class')).toMatch(/text-destructive/));
  expect(pane.querySelector('[data-tool-panel-id="reference"] [data-tool-panel-heading] h3')!.textContent).toBe(sentence);
  const reference = pane.querySelector('[data-board-reference]')!;
  expect(reference.textContent).toContain('Clearance violation');
  expect(reference.textContent).toContain('#net:VIN, #J1.2');
  // The heading may be cut short: the sentence is read in full in the first row, which wraps.
  const rowOf = (label: string) => [...reference.querySelectorAll('[data-info-row]')].find((element) => element.firstElementChild?.textContent === label);
  const sentenceRow = rowOf('Finding')!;
  expect(sentenceRow.lastElementChild!.textContent).toBe(sentence);
  for (const element of [sentenceRow, ...sentenceRow.querySelectorAll('*')]) expect(element.getAttribute('class') || '').not.toMatch(/\btruncate\b/);
  expect(reference.querySelector('[data-info-row]')).toBe(sentenceRow);
  dispose();
});

it('a finding naming several things reads its own rows, then a picker over what it names', async () => {
  readPlot = boardWith(FINDINGS);
  const { pane, dispose } = await open('blinky.kicad_pcb');
  await opened(pane);
  const sentence = 'The VIN track and the GND pad of J1 are 0.15 mm apart; the rules need 0.2 mm';
  await act(async () => { within(await within(pane).findByRole('alert')).getByRole('button', { name: sentence }).click(); });
  const reference = pane.querySelector('[data-board-reference]')!;
  const labels = () => [...reference.querySelectorAll('[data-info-row]')].map((element) => element.firstElementChild!.textContent);
  // The finding's rows, then the picker, then the browsed thing's: the last named, J1's pad 2.
  expect(labels().slice(0, 5)).toEqual(['Finding', 'Check', 'Severity', 'Message', 'Items']);
  const picker = within(reference as HTMLElement).getByRole('button', { name: 'Choose a reference' });
  expect(picker.textContent).toContain('J1 · pad 2');
  expect(picker.textContent).toContain('2/2');
  expect(labels()).toContain('Side');
  expect(labels()).not.toContain('Tracks');
  await act(async () => { fireEvent.pointerDown(picker, { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
  await act(async () => { (await screen.findByRole('menuitemradio', { name: 'net VIN' })).click(); });
  await waitFor(() => expect(labels()).toContain('Tracks'));
  expect(labels()).not.toContain('Side');
  expect(labels().slice(0, 5)).toEqual(['Finding', 'Check', 'Severity', 'Message', 'Items']);
  expect(pane.querySelector('[data-tool-panel-id="reference"] [data-tool-panel-heading] h3')!.textContent).toBe(sentence);
  dispose();
});

it('a schematic\'s ERC findings are its card\'s, not its tree\'s', async () => {
  readPlot = (file) => (file.endsWith('.kicad_sch') ? json({ ...SCHEMATIC, schematic: { ...SCHEMATIC_INDEX, findings: [
    { check: 'erc', severity: 'error', type: 'pin_not_connected', description: 'Pin not connected', summary: 'U1 pin 8 (V+) isn\'t connected to anything', items: [{ text: 'Symbol U1 Pin 8', ref: '#U1.8', at: null }] },
  ] } }) : json(BOARD));
  const { pane, dispose } = await open('blinky.kicad_sch');
  await opened(pane);
  const card = within(await within(pane).findByRole('alert'));
  expect(card.getByRole('heading', { name: '1 to fix' })).not.toBeNull();
  expect(within(pane).getByRole('list', { name: 'Schematic' })).not.toBeNull();
  expect(within(pane).queryByRole('button', { name: 'Checks' })).toBeNull();
  dispose();
});

it('a schematic with its index has Select alone, its symbols and nets, and hands references to Quick Edit', async () => {
  readPlot = (file) => (file.endsWith('.kicad_sch') ? json({ ...SCHEMATIC, schematic: SCHEMATIC_INDEX }) : json(BOARD));
  const { pane, dispose } = await open('blinky.kicad_sch');
  await opened(pane);
  const inPane = within(pane);
  const tools = await inPane.findByRole('group', { name: 'Interaction tools' });
  // A distance or a sketch on a schematic's layout means nothing to the design: no Measure, no Draw.
  expect(within(tools).getAllByRole('button').map((button) => button.getAttribute('aria-label'))).toEqual(['Select']);
  expect(inPane.queryByRole('button', { name: 'Display' })).toBeNull();
  expect(inPane.getByRole('list', { name: 'Schematic' })).not.toBeNull();
  expect(inPane.queryByRole('button', { name: 'Checks' })).toBeNull();
  await act(async () => { inPane.getByRole('button', { name: 'Expand ICs' }).click(); });
  await act(async () => { inPane.getByRole('button', { name: 'Select U1' }).click(); });
  const reference = pane.querySelector('[data-board-reference]')!;
  expect(reference.textContent).toContain('Amplifier_Operational:LM358');
  expect(reference.textContent).toContain('SOIC-8_3.9x4.9mm_P1.27mm');
  expect(reference.textContent).toContain('blinky, power');
  expect(reference.textContent).toContain('blinky.py:20');
  expect(reference.textContent).not.toContain('Position');
  await act(async () => { inPane.getByRole('button', { name: 'Expand U1' }).click(); });
  await act(async () => { inPane.getByRole('button', { name: 'Select 8' }).click(); });
  expect(inPane.getByText('U1 · pin 8 V+')).not.toBeNull();
  expect(pane.querySelector('[data-board-reference]')!.textContent).toContain('power in');
  await act(async () => { inPane.getByRole('button', { name: 'Copy' }).click(); });
  await waitFor(() => expect(copied).toEqual(['/models/blinky.kicad_sch#U1.8']));
  dispose();
});

it('the live controller selects schematic references and refuses a board’s points', async () => {
  readPlot = (file) => (file.endsWith('.kicad_sch') ? json({ ...SCHEMATIC, schematic: SCHEMATIC_INDEX }) : json(BOARD));
  const view = await open('blinky.kicad_sch');
  const { pane, dispose } = view;
  await opened(pane);
  const controller = await waitFor(() => { expect(view.controller).not.toBeNull(); return view.controller; });
  const state = await controller.select('#R1.1,#net:VIN');
  expect(state.selection).toEqual([expect.objectContaining({ target: { kind: 'cad-selector', selectors: ['#R1.1', '#net:VIN'] } })]);
  expect(pane.querySelector('[data-quick-edit]')?.textContent).toContain('2 refs');
  await expect(controller.select({ selectors: ['#@x1y2'] })).rejects.toThrow(/Not on this schematic: #@x1y2.*points are a board/);
  dispose();
});

// A press on the picture, where page point `at` is on screen in the last frame painted.
const press = async (pane: HTMLElement, at: [number, number], { double = false } = {}) => {
  const canvas = pane.querySelector('canvas')!;
  const [clientX, clientY] = pageToScreen(frames.at(-1), at[0], at[1]);
  await act(async () => {
    canvas.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, clientX, clientY, button: 0 }));
    canvas.dispatchEvent(new MouseEvent('pointerup', { bubbles: true, clientX, clientY, button: 0 }));
    if (double) canvas.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, clientX, clientY }));
  });
};

it('a press on a pad selects it, a shift-press adds its neighbour, and a double-click copies one', async () => {
  readPlot = (file) => (file.endsWith('.kicad_pcb') ? json({ ...BOARD, board: INDEX }) : json(SCHEMATIC));
  const view = await open('blinky.kicad_pcb');
  const { pane, dispose } = view;
  await opened(pane);
  const controller = await waitFor(() => { expect(view.controller).not.toBeNull(); return view.controller; });
  await press(pane, [14.175, 20]);
  expect(controller.readState().selection[0].target.selectors).toEqual(['#R1.1']);
  const canvas = pane.querySelector('canvas')!;
  const [x, y] = pageToScreen(frames.at(-1), 15.825, 20);
  await act(async () => {
    canvas.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, clientX: x, clientY: y, button: 0, shiftKey: true }));
    canvas.dispatchEvent(new MouseEvent('pointerup', { bubbles: true, clientX: x, clientY: y, button: 0, shiftKey: true }));
  });
  expect(controller.readState().selection[0].target.selectors).toEqual(['#R1.1', '#R1.2']);
  await press(pane, [30, 8.73], { double: true });
  await waitFor(() => expect(copied).toEqual(['/models/blinky.kicad_pcb#J1.1']));
  // Bare board clears.
  await press(pane, [36, 26]);
  expect(controller.readState().selection).toEqual([]);
  dispose();
});

it('a press on a schematic wire selects its net', async () => {
  readPlot = (file) => (file.endsWith('.kicad_sch') ? json({ ...SCHEMATIC, schematic: SCHEMATIC_INDEX }) : json(BOARD));
  const view = await open('blinky.kicad_sch');
  const { pane, dispose } = view;
  await opened(pane);
  const controller = await waitFor(() => { expect(view.controller).not.toBeNull(); return view.controller; });
  await press(pane, [60, 43.18]);
  expect(controller.readState().selection[0].target.selectors).toEqual(['#net:VIN']);
  dispose();
});
