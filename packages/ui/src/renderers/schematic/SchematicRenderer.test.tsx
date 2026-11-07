import { useState } from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createCadClient } from '@cad/core/client';
import { pageToScreen } from '@cad/core/lib/plot2d/plot.js';
import { exportChoices } from '../../export/formats.js';
import { FileViewer } from '../../../dist/file-viewer/index.js';
import { createSchematicRenderer } from '../../../dist/renderers/schematic/index.js';
// Loaded with the file, not inside the first test: the registration imports it lazily.
import '../../../dist/renderers/schematic/SchematicRenderer.js';
import SCHEMATIC from './__fixtures__/schematic.plot.json';

// The schematic tab's chrome and its answers to the host, mounted as a host mounts it: the FileViewer over
// the real registration and a real CAD client, whose backend answers the committed payload a sheet at a
// time, as the route does (`__fixtures__/schematic.plot.json`: the Python suite's divider — the root sheet,
// R1 and R2 between +5V and GND, the MID net, J1 on VOUT, the sheet Load at (127, 57.15), 31.75 x 19.05;
// Load holds C1 and R3). The pixels are the browser suite's; what the tab offers, what it reads, picks and
// shows are decided here.

const frames = vi.hoisted(() => [] as Array<{ scale: number; offsetX: number; offsetY: number }>);
const drawn = vi.hoisted(() => [] as Array<string>);
vi.mock('@cad/core/lib/plot2d/index.js', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    drawPlot: (_ctx: unknown, _layout: unknown, { theme }: { theme: string }) => { drawn.push(theme); },
    drawPlotImages: (_ctx: unknown, _layout: unknown, { transform }: { transform: any }) => { frames.push({ ...transform }); }
  };
});

const noop = () => {};
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const context2d = new Proxy({}, { get: (_target, key) => (key === 'canvas' ? undefined : key === 'measureText' ? (text: string) => ({ width: text.length * 7 }) : noop), set: () => true });
let reads: string[] = [];
const DESTINATION = { kind: 'clipboard', available: true };

/** What the route answers for `?sheet=` and `index=0`: the one page, with or without the hierarchy's index. */
function sheetPayload(url: URL) {
  const sheet = url.searchParams.get('sheet') || '/';
  const page = SCHEMATIC.sheets.find(one => one.path === sheet);
  if (!page) return json({ error: `divider.kicad_sch has no sheet ${sheet}` }, 400);
  const { schematic, ...rest } = SCHEMATIC;
  return json({ ...rest, sheets: [page], ...(url.searchParams.get('index') === '0' ? {} : { schematic }) });
}

beforeEach(() => {
  frames.length = 0;
  drawn.length = 0;
  reads = [];
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => setTimeout(() => callback(performance.now()), 0));
  vi.stubGlobal('cancelAnimationFrame', (handle: number) => clearTimeout(handle));
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: false, media: query, addEventListener: noop, removeEventListener: noop, addListener: noop, removeListener: noop }));
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

async function open({ colorScheme = 'light' } = {}) {
  const file = '/models/divider.kicad_sch';
  const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    if (url.pathname.endsWith('/api/v1/documents') && init?.method === 'POST') {
      return json({ id: 'sch', kind: 'kicad_sch', api: '/api/v1/documents/kicad_sch/sch' }, 201);
    }
    if (url.pathname.endsWith('/api/v1/documents')) {
      return json({ documents: [{ entry: { kind: 'kicad_sch', file, url: '/divider.kicad_sch', hash: 'one', bytes: 4096 }, revision: 'one' }] });
    }
    if (url.pathname.endsWith('/api/v1/server')) return json({ backend: 'cadgen' });
    if (url.pathname.endsWith('/api/v1/documents/kicad_sch/sch/plot')) { reads.push(url.search); return sheetPayload(url); }
    return new Response('', { status: 404 });
  });
  const client = createCadClient({ origin: 'http://viewer.test/one', pollIntervalMs: 0, fetch: fetch as typeof globalThis.fetch });
  await client.refresh();
  let controller: any = null;
  const live = { bind(next: unknown) { controller = next; return () => { controller = null; }; } };
  const renderers = [createSchematicRenderer({ client, live })];
  const host = {
    files: { id: 'one', stat: async (path: string) => ({ path, name: path.split('/').pop(), kind: 'file', size: 400, extension: 'kicad_sch' }) },
    navigation: { openFile: noop },
    environment: { colorScheme, locale: 'en' },
    clipboard: { writeText: async () => {}, readText: async () => '', writeImage: async () => {} },
    promptContext: { getSnapshot: () => DESTINATION, subscribe: () => noop, deliver: async () => ({ status: 'copied', partIds: [] }) },
  };
  let latest: any = { renderers: {} };
  function Pane() {
    const [state, setState] = useState<any>(latest);
    latest = state;
    return <section data-testid="pane"><FileViewer file={file} host={host as any} renderers={renderers} state={state} onStateChange={setState} /></section>;
  }
  render(<Pane />);
  const pane = screen.getByTestId('pane');
  return { pane, get controller() { return controller; }, get state() { return latest; }, dispose: () => client.dispose() };
}

const canvasOf = (pane: HTMLElement) => pane.querySelector<HTMLCanvasElement>('[data-schematic-surface] canvas[data-schematic-sheet]')!;
const onSheet = (pane: HTMLElement, sheet: string) => waitFor(() => {
  expect(canvasOf(pane).dataset.schematicSheet).toBe(sheet);
  expect(pane.querySelector('[data-schematic-surface] [aria-busy="false"]')).not.toBeNull();
});
const point = (at: [number, number]) => {
  const [clientX, clientY] = pageToScreen(frames.at(-1)!, at[0], at[1]);
  return { pointerId: 1, pointerType: 'mouse', button: 0, clientX, clientY };
};
const tap = (pane: HTMLElement, at: [number, number], init: Record<string, unknown> = {}) => {
  const event = { ...point(at), ...init };
  fireEvent.pointerDown(canvasOf(pane), event);
  fireEvent.pointerUp(canvasOf(pane), event);
};
/** Zoom in about the pane's middle (jsdom's pane fits the page small): a pick's reach is a few pixels, in millimetres. */
const zoomIn = async (pane: HTMLElement) => {
  const before = frames.at(-1)!.scale;
  fireEvent.wheel(canvasOf(pane), { deltaY: -700, clientX: 600, clientY: 350 });
  await waitFor(() => expect(frames.at(-1)!.scale).toBeGreaterThan(before * 2));
};
const selected = (controller: any) => controller.readState().selection.map((reference: any) => reference.target.selectors[0]);
const controllerOf = (view: { controller: any }) => waitFor(() => { expect(view.controller).not.toBeNull(); return view.controller; });

it('opens on the root sheet, read with the index, drawn in the theme, its panel the Parts, the Nets, then the Hierarchy, and its zoom the corner pill', async () => {
  const view = await open();
  const { pane } = view;
  await onSheet(pane, '/');
  expect(reads).toEqual(['?sheet=%2F']);
  await waitFor(() => expect(drawn.includes('light')).toBe(true));
  const tools = within(pane).getByRole('group', { name: 'Interaction tools' });
  expect([...tools.querySelectorAll(':scope button[aria-pressed]')].map(button => button.getAttribute('aria-label'))).toEqual(['Select', 'Pencil', 'Shapes', 'Measure']);
  // No view controls on the strip: its zoom is the corner's pill.
  expect(tools.querySelector('[data-view-controls]')).toBeNull();
  expect(pane.querySelector('[data-zoom-pill] [data-zoom-control]')!.textContent).toBe('100%');
  // The panel: one search over every tab, the Parts open first.
  const panel = pane.querySelector<HTMLElement>('[data-flat-panel]')!;
  expect((within(panel).getByRole('textbox', { name: 'Search the schematic' }) as HTMLInputElement).placeholder).toBe('Search');
  expect(within(panel).getAllByRole('tab').map(tab => [tab.querySelector('[data-flat-panel-tab-name]')!.textContent, tab.getAttribute('aria-selected')])).toEqual([['Parts', 'true'], ['Nets', 'false'], ['Hierarchy', 'false']]);
  fireEvent.click(within(panel).getByRole('tab', { name: 'Hierarchy' }));
  // The Hierarchy: the root by its file's name, Load under it, the root shown.
  const rows = [...pane.querySelectorAll<HTMLElement>('[data-schematic-sheet-row]')];
  expect(rows.map(row => [row.dataset.schematicSheetRow, row.textContent])).toEqual([['/', 'divider1'], ['/Load/', 'Load2']]);
  expect(within(rows[0]).getByRole('button', { name: 'Show sheet divider' }).getAttribute('aria-current')).toBe('page');
  // The Parts: a block per sheet, shut while it holds several parts; the Nets a list of their own.
  const blocks = [...pane.querySelectorAll<HTMLElement>('[data-flat-panel-section="parts"] [data-schematic-row]')].map(row => row.dataset.schematicRow);
  expect(blocks).toEqual(['sheet:/', 'sheet:/Load/']);
  expect([...pane.querySelectorAll<HTMLElement>('[data-flat-panel-section="nets"] [data-schematic-row]')].map(row => row.dataset.schematicRow))
    .toEqual(['net:/MID', 'net:+5V', 'net:GND', 'net:VOUT', 'group:unconnected']);
  expect(pane.querySelector('[data-schematic-row="part:R1"]')).toBeNull();
  // Its Export is KiCad's: the PDF, the SVGs, the netlist and the BOM.
  expect(exportChoices({ file: '/models/divider.kicad_sch', planar: false }).map(choice => choice.format)).toEqual(['pdf', 'svg', 'netlist', 'bom']);
  expect((await controllerOf(view)).readState().schematicDisplay).toEqual({ sheet: '/', border: false });
  view.dispose();
});

it('a sheet is shown from the Hierarchy and by a double-click on its symbol, each read once, each kept where it was left', async () => {
  const user = userEvent.setup();
  const view = await open();
  const { pane } = view;
  await onSheet(pane, '/');
  // The root zoomed in before leaving it: coming back finds it as it was left.
  await zoomIn(pane);
  const left = { ...frames.at(-1)! };
  await user.click(within(pane).getByRole('tab', { name: 'Hierarchy' }));
  await user.click(within(pane).getByRole('button', { name: 'Show sheet Load' }));
  await onSheet(pane, '/Load/');
  expect(reads).toEqual(['?sheet=%2F', '?sheet=%2FLoad%2F&index=0']);
  // No trail under the strip: the Hierarchy is the way back up.
  expect(pane.querySelector('[data-schematic-trail]')).toBeNull();
  const fitted = { ...frames.at(-1)! };
  expect(fitted.scale).toBeLessThan(left.scale);
  // A sheet found by the panel's search is shown from its hit, the tree stepping aside.
  fireEvent.change(within(pane).getByRole('textbox', { name: 'Search the schematic' }), { target: { value: 'divid' } });
  await user.click(within(pane.querySelector<HTMLElement>('[data-flat-panel-section="hierarchy"] [data-flat-panel-hit]')!).getByRole('button', { name: 'Show sheet divider' }));
  await onSheet(pane, '/');
  await waitFor(() => expect(frames.at(-1)).toEqual(left));
  // The sheet's symbol, double-clicked, enters it: read before, so read no more.
  fireEvent.dblClick(canvasOf(pane), point([140, 66]));
  await onSheet(pane, '/Load/');
  expect(reads).toHaveLength(2);
  expect((await controllerOf(view)).readState().schematicDisplay.sheet).toBe('/Load/');
  // Each sheet's view is kept with the file, so a reopen finds the root where it was left.
  await waitFor(() => expect(JSON.stringify(view.state)).toContain(`"views":{"/":{"scale":${left.scale}`));
  // The menu over bare paper in a sheet entered goes up one; Zoom to fit is there too.
  const right = { ...point([20, 20]), button: 2, pointerId: 3 };
  fireEvent.pointerDown(canvasOf(pane), right);
  fireEvent.pointerUp(canvasOf(pane), right);
  const menu = await screen.findByRole('menu');
  expect(within(menu).getAllByRole('menuitem').map(item => item.textContent)).toEqual(['Up one sheet', 'Zoom to fit', 'Zoom to selection']);
  await user.click(within(menu).getByRole('menuitem', { name: 'Up one sheet' }));
  await onSheet(pane, '/');
  view.dispose();
});

// A double-click fits under Select alone, as in every view: under Measure (or Pencil, Shapes) it is the tool's.
it('a double-click on bare paper fits under Select, and under Measure leaves the view where it is', async () => {
  const user = userEvent.setup();
  const view = await open();
  const { pane } = view;
  await onSheet(pane, '/');
  const fitted = { ...frames.at(-1)! };
  await zoomIn(pane);
  const zoomed = { ...frames.at(-1)! };
  await user.click(within(pane.querySelector<HTMLElement>('[data-cad-toolbar]')!).getByRole('button', { name: /^Measure/ }));
  fireEvent.dblClick(canvasOf(pane), point([20, 20]));
  await new Promise(resolve => requestAnimationFrame(resolve));
  expect(frames.at(-1)!.scale).toBe(zoomed.scale);
  await user.click(within(pane.querySelector<HTMLElement>('[data-cad-toolbar]')!).getAllByRole('button', { name: /^Select/ })[0]);
  fireEvent.dblClick(canvasOf(pane), point([20, 20]));
  await waitFor(() => expect(frames.at(-1)!.scale).toBe(fitted.scale));
  view.dispose();
});

it('a press picks what is under it and reveals its row; a net from the Nets lights, its pins under the lists; a part on another sheet shows that sheet', async () => {
  const user = userEvent.setup();
  const view = await open();
  const { pane } = view;
  await onSheet(pane, '/');
  const controller = await controllerOf(view);
  await zoomIn(pane);
  // R1's body, in the middle of its symbol: its part, said under the lists, its block opened and its row brought into view.
  tap(pane, [101.6, 59.69]);
  await waitFor(() => expect(selected(controller)).toEqual(['#R1']));
  expect(pane.querySelector('[data-schematic-detail-head]')!.textContent).toBe('R1');
  await waitFor(() => expect(pane.querySelector('[data-schematic-row="part:R1"] button[aria-pressed="true"]')).not.toBeNull());
  // The MID label's text, then its wire to the sheet: each by its uuid.
  tap(pane, [115.2, 63.4]);
  await waitFor(() => expect(selected(controller)).toEqual(['#label:5c4e0000-0000-4000-8000-0000000000a2']));
  tap(pane, [124, 64.77]);
  await waitFor(() => expect(selected(controller)).toEqual(['#wire:5c4e0000-0000-4000-8000-0000000000a1']));
  // Nothing: nothing.
  tap(pane, [20, 20]);
  await waitFor(() => expect(selected(controller)).toEqual([]));
  // /MID pressed in the Nets: the net selected, on the sheet shown, its pins under the lists.
  await user.click(within(pane).getByRole('tab', { name: 'Nets' }));
  await user.click(within(pane.querySelector<HTMLElement>('[data-schematic-row="net:/MID"]')!).getByRole('button', { name: 'Select /MID' }));
  expect(selected(controller)).toEqual(['#net:/MID']);
  expect(canvasOf(pane).dataset.schematicSheet).toBe('/');
  expect([...pane.querySelectorAll('[data-flat-panel-detail] [data-schematic-detail-row]')].map(row => row.textContent)).toEqual(['C1.1', 'R1.2', 'R2.1']);
  // C1 is on Load alone: pressed in the Parts, Load is shown, at its own view.
  await user.click(within(pane).getByRole('tab', { name: 'Parts' }));
  await user.click(within(pane.querySelector<HTMLElement>('[data-schematic-row="sheet:/Load/"]')!).getByRole('button', { name: 'Expand Load' }));
  await user.click(within(pane.querySelector<HTMLElement>('[data-schematic-row="part:C1"]')!).getByRole('button', { name: 'Select C1' }));
  await onSheet(pane, '/Load/');
  expect(selected(controller)).toEqual(['#C1']);
  // A double-click frames it there.
  const atView = { ...frames.at(-1)! };
  await user.dblClick(within(pane.querySelector<HTMLElement>('[data-schematic-row="part:C1"]')!).getByRole('button', { name: 'Select C1' }));
  await waitFor(() => expect(frames.at(-1)!.scale).toBeGreaterThan(atView.scale));
  // Selected from outside, it shows its sheet too.
  await controller.select('#R1');
  await onSheet(pane, '/');
  await controller.select('#C1');
  await onSheet(pane, '/Load/');
  expect(selected(controller)).toEqual(['#C1']);
  await expect(controller.select('#R99')).rejects.toThrow(/Not in this schematic: #R99/);
  view.dispose();
});

it("Select's filter is KiCad's boxes, each its name alone; without Pins a press on a pin inside its body takes the symbol", async () => {
  const user = userEvent.setup();
  const view = await open();
  const { pane } = view;
  await onSheet(pane, '/');
  const controller = await controllerOf(view);
  await user.click(within(pane).getByRole('button', { name: 'Selection filter: everything' }));
  const menu = await waitFor(() => { const found = document.querySelector<HTMLElement>('[role=menu][aria-label="Selection filter"]'); expect(found).not.toBeNull(); return found!; });
  const boxes = within(menu).getAllByRole('menuitemcheckbox');
  expect(boxes.map(box => box.textContent)).toEqual(['All items', 'Symbols', 'Pins', 'Wires', 'Labels', 'Sheets', 'Other items']);
  await user.click(within(menu).getByRole('menuitemcheckbox', { name: 'Pins' }));
  await user.keyboard('{Escape}');
  await zoomIn(pane);
  tap(pane, [101.6, 57.1]);
  await waitFor(() => expect(selected(controller)).toEqual(['#R1']));
  view.dispose();
});

it('in the dark theme the sheet is drawn dark, and the view a snapshot replays names no theme: it is drawn light', async () => {
  const view = await open({ colorScheme: 'dark' });
  await onSheet(view.pane, '/');
  await waitFor(() => expect(drawn.includes('dark')).toBe(true));
  expect((await controllerOf(view)).readState().schematicDisplay).toEqual({ sheet: '/', border: false });
  view.dispose();
});
