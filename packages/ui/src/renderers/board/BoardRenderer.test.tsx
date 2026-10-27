import { StrictMode, useState } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createCadClient } from '@text-to-cad/core/client';
import { pageToScreen } from '@text-to-cad/core/lib/plot2d/plot.js';
import { FileViewer } from '../../../dist/file-viewer/index.js';
import { createBoardRenderer } from '../../../dist/renderers/board/index.js';
// Loaded with the file, not inside the first test: the registration imports it lazily.
import '../../../dist/renderers/board/BoardRenderer.js';
import BOARD from './__fixtures__/board.plot.json';

// The board tab's chrome and its answers to the host, mounted the way a host mounts it: the
// FileViewer over the real registration and a real CAD client, whose backend is a fetch that
// answers with the committed `/__cad/plot` payload (`__fixtures__/README.md`: J1 at (5, 15), R1 at
// (35, 15), D1 at (20, 24), in KiCad's millimetres, which are the sheet's here). The pixels are the
// browser suite's; what the tab offers, what it picks and what a host is told are decided here.

// Every frame the pane paints places its rasters with `drawPlotImages` under the view's transform;
// the rasters themselves are `drawPlot`, which jsdom cannot draw and the pixels are not its to check.
const frames = vi.hoisted(() => [] as Array<{ scale: number; offsetX: number; offsetY: number }>);
const drawn = vi.hoisted(() => [] as Array<{ layers: string[]; side: string; poured: boolean }>);
vi.mock('@text-to-cad/core/lib/plot2d/index.js', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    drawPlot: (_ctx: unknown, _layout: unknown, { view }: { view: any }) => { if (view) drawn.push(view); },
    drawPlotImages: (_ctx: unknown, _layout: unknown, { transform }: { transform: any }) => { frames.push({ ...transform }); }
  };
});

const noop = () => {};
const FILE = '/models/blinky.kicad_pcb';
const KEY = JSON.stringify([FILE, 'board']);
let copied: string[] = [];
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const UNREADABLE = 'broken.kicad_pcb is not a KiCad board: a .kicad_pcb starts with (kicad_pcb ...)';
let readPlot: () => Response | Promise<Response> = () => json(BOARD);
const DESTINATION = { kind: 'clipboard', available: true };
const context2d = new Proxy({}, { get: (_target, key) => (key === 'canvas' ? undefined : key === 'measureText' ? (text: string) => ({ width: text.length * 7 }) : noop), set: () => true });

beforeEach(() => {
  frames.length = 0;
  drawn.length = 0;
  copied = [];
  readPlot = () => json(BOARD);
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

/** One pane: a host, a workspace with one board, a live binding, and the tab. */
async function open(name = 'blinky.kicad_pcb', { strict = false, promptFiles = undefined as any, locale = "en" } = {}) {
  const file = `/models/${name}`;
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    if (url.pathname.endsWith('/__cad/catalog')) return json({ entries: [{ kind: 'kicad_pcb', file, url: `/${name}`, hash: 'one', bytes: 4096 }] });
    if (url.pathname.endsWith('/__cad/server')) return json({ backend: 'cadgen' });
    if (url.pathname.endsWith('/__cad/plot')) return readPlot();
    return new Response('', { status: 404 });
  });
  const client = createCadClient({ origin: 'http://viewer.test/one', pollIntervalMs: 0, fetch: fetch as typeof globalThis.fetch });
  await client.refresh();
  let controller: any = null;
  const live = { bind(next: unknown) { controller = next; return () => { controller = null; }; } };
  const renderers = [createBoardRenderer({ client, live })];
  const host = {
    promptFiles,
    files: { id: 'one', stat: async (path: string) => ({ path, name: path.split('/').pop(), kind: 'file', size: 400, extension: 'kicad_pcb' }) },
    navigation: { openFile: noop },
    environment: { colorScheme: 'light', locale },
    clipboard: { writeText: async (text: string | Promise<string>) => { copied.push(await text); }, readText: async () => '', writeImage: async () => {} },
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

const opened = async (pane: HTMLElement) => {
  await waitFor(() => expect(pane.querySelector('[data-board-surface] [aria-busy="false"]')).not.toBeNull());
  await waitFor(() => expect(frames.length).toBeGreaterThan(0));
};
const strip = (pane: HTMLElement) => within(pane).getByRole('group', { name: 'Interaction tools' });
const box = (pane: HTMLElement) => pane.querySelector<HTMLElement>('[data-quick-edit-box]');
const controllerOf = (view: { controller: any }) => waitFor(() => { expect(view.controller).not.toBeNull(); return view.controller; });
// An open menu, by its accessible name (portalled under the body, as every dropdown is).
const openMenu = (name: string) => waitFor(() => { const found = document.querySelector<HTMLElement>(`[role=menu][aria-label="${name}"]`); expect(found).not.toBeNull(); return found!; });
const menuShown = (name: string) => document.querySelector(`[role=menu][aria-label="${name}"]`);
const selected = (controller: any) => controller.readState().selection.map((reference: any) => reference.target.selectors[0]);

/** A tap on the board where sheet point `at` is on screen in the last frame painted. */
const tap = (pane: HTMLElement, at: [number, number], init: Record<string, unknown> = {}) => {
  const canvas = pane.querySelector<HTMLCanvasElement>('[data-board-surface] canvas')!;
  const [clientX, clientY] = pageToScreen(frames.at(-1)!, at[0], at[1]);
  const event = { pointerId: 1, pointerType: 'mouse', button: 0, clientX, clientY, ...init };
  fireEvent.pointerDown(canvas, event);
  fireEvent.pointerUp(canvas, event);
};

it("a board's strip is a drawing's — Select (in hand), Pencil, Shapes, Measure — then its Display after the rule, and no Preview", async () => {
  const { pane, dispose } = await open();
  await opened(pane);
  const tools = strip(pane);
  expect([...tools.querySelectorAll(':scope button[aria-pressed]')].map(button => button.getAttribute('aria-label'))).toEqual(['Select', 'Pencil', 'Shapes', 'Measure']);
  expect(within(tools).getByRole('button', { name: 'Select' }).getAttribute('aria-pressed')).toBe('true');
  expect(within(tools).getByRole('button', { name: 'Selection filter: everything' })).toBeTruthy();
  expect(tools.querySelector('[data-strip-rule] + [data-view-controls]')).not.toBeNull();
  expect([...tools.querySelectorAll('[data-view-controls] button')].map(button => button.getAttribute('aria-label'))).toEqual(['Display mode: Board']);
  for (const name of ['Preview', 'Projection', 'Explode', 'Clip', 'Orbit', 'Position', 'Animation']) {
    expect(within(pane).queryByRole('button', { name }), name).toBeNull();
  }
  // The sidebar's tiles: the Board and its Layers. Nothing is picked yet: no Quick Edit.
  expect(within(pane.querySelector<HTMLElement>('[data-file-sidebar-tools]')!).getAllByRole('button').map(button => button.getAttribute('aria-label')))
    .toEqual(['Board', 'Layers']);
  expect(box(pane)).toBeNull();
  dispose();
});

it('a native board uses the host language for its controls, tree and accessible canvas', async () => {
  const { pane, dispose } = await open('blinky.kicad_pcb', { locale: 'zh-CN' });
  await opened(pane);
  expect(pane.querySelector('canvas')?.getAttribute('aria-label')).toBe('电路板：blinky.kicad_pcb');
  expect(within(pane).getByRole('button', { name: '电路板' })).toBeTruthy();
  fireEvent.click(within(pane).getByRole('button', { name: '电路板' }));
  expect(within(pane).getByRole('textbox', { name: '筛选电路板' })).toBeTruthy();
  expect(within(pane).getByRole('button', { name: '选择', exact: true })).toBeTruthy();
  expect(within(pane).getByText('元件')).toBeTruthy();
  expect(within(pane).queryByText('Parts')).toBeNull();
  dispose();
});

it('a board without its index is the picture and its Display alone: no tools, no Board, no Quick Edit', async () => {
  const { board: _index, ...picture } = BOARD as any;
  readPlot = () => json(picture);
  const { pane, dispose } = await open();
  await opened(pane);
  expect(pane.querySelector('canvas')?.getAttribute('aria-label')).toBe('Board: blinky.kicad_pcb');
  expect([...strip(pane).querySelectorAll('button')].map(button => button.getAttribute('aria-label'))).toEqual(['Display mode: Board']);
  expect(within(pane.querySelector<HTMLElement>('[data-file-sidebar-tools]')!).getAllByRole('button').map(button => button.getAttribute('aria-label'))).toEqual(['Layers']);
  tap(pane, [34.175, 15]);
  expect(box(pane)).toBeNull();
  dispose();
});

it('none of the chrome while the board loads, or once it failed to: the card, with the server’s own sentence', async () => {
  let answer: ((response: Response) => void) | null = null;
  readPlot = () => new Promise<Response>((resolve) => { answer = resolve; });
  const { pane, dispose } = await open('broken.kicad_pcb');
  await waitFor(() => expect(answer).not.toBeNull());
  expect(within(pane).queryByRole('group', { name: 'Interaction tools' })).toBeNull();
  expect(pane.querySelector('[data-file-sidebar-tools]')).toBeNull();
  await act(async () => { answer!(json({ error: UNREADABLE }, 400)); });
  const alert = await within(pane).findByRole('alert');
  expect(alert.textContent).toContain('is not a KiCad board');
  expect(within(pane).queryByRole('group', { name: 'Interaction tools' })).toBeNull();
  expect(pane.querySelector('[data-file-sidebar-tools]')).toBeNull();
  expect(pane.querySelector('[data-viewer-loading]')).toBeNull();
  dispose();
});

it('a tap picks the most specific thing: a pad, then copper, then nothing; Shift adds; a chip names it and copies it', async () => {
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  const controller = await controllerOf(view);
  tap(pane, [34.175, 15]);
  expect(selected(controller)).toEqual(['#R1.1']);
  tap(pane, [35.825, 15], { shiftKey: true });
  expect(selected(controller)).toEqual(['#R1.1', '#R1.2']);
  const quickEdit = await waitFor(() => { expect(box(pane)).not.toBeNull(); return box(pane)!; });
  expect([...quickEdit.querySelectorAll('[data-quick-edit-ref] button[aria-label]')].map(button => button.getAttribute('aria-label')))
    .toEqual(['R1.1', 'Remove R1.1', 'R1.2', 'Remove R1.2']);
  // A click on a chip copies its reference, the file's absolute path and the pick, as a copied reference is.
  fireEvent.click(within(quickEdit).getByRole('button', { name: 'R1.1' }));
  await waitFor(() => expect(copied).toEqual([`${FILE}#R1.1`]));
  // The copy key copies the selection, comma-joined after the file.
  const canvas = pane.querySelector<HTMLCanvasElement>('[data-board-surface] canvas')!;
  fireEvent.keyDown(canvas, { key: 'c', metaKey: true });
  await waitFor(() => expect(copied.at(-1)).toBe(`${FILE}#R1.1,R1.2`));
  // A press on the track takes its net's copper there, in KiCad's frame; bare board lets go.
  tap(pane, [30, 15]);
  expect(selected(controller)).toEqual(['#net:VBUS@x30y15']);
  tap(pane, [36, 26]);
  expect(selected(controller)).toEqual([]);
  dispose();
});

it("Select's filter is one choice of what a press takes: Parts takes the part, over copper too; Nets takes the whole net", async () => {
  const user = userEvent.setup({ skipHover: true, pointerEventsCheck: 0 });
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  const controller = await controllerOf(view);
  await user.click(within(strip(pane)).getByRole('button', { name: 'Selection filter: everything' }));
  const menu = await openMenu('Selection filter');
  expect(within(menu).getAllByRole('menuitemradio').map(item => item.textContent)).toEqual(['All', 'Parts', 'Pads', 'Nets']);
  await user.click(within(menu).getByRole('menuitemradio', { name: 'Parts' }));
  // Choosing one puts the menu away.
  await waitFor(() => expect(menuShown('Selection filter')).toBeNull());
  // R1.1, under the VBUS track's end: the part, not the pad or the copper.
  tap(pane, [34.175, 15]);
  expect(selected(controller)).toEqual(['#R1']);
  await user.click(within(strip(pane)).getByRole('button', { name: 'Selection filter: Parts' }));
  await user.click(within(await openMenu('Selection filter')).getByRole('menuitemradio', { name: 'Nets' }));
  expect(within(strip(pane)).getByRole('button', { name: 'Selection filter: Nets' })).toBeTruthy();
  tap(pane, [34.175, 15]);
  expect(selected(controller)).toEqual(['#net:VBUS']);
  dispose();
});

it('the Board section lists parts by kind and nets: a row selects, its eye isolates, and the isolation is the file’s', async () => {
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  const controller = await controllerOf(view);
  fireEvent.click(within(pane.querySelector<HTMLElement>('[data-file-sidebar-tools]')!).getByRole('button', { name: 'Board' }));
  const section = await waitFor(() => { const found = pane.querySelector<HTMLElement>('[data-tool-panel-id="board"]'); expect(found).not.toBeNull(); return found!; });
  const inSection = within(section);
  expect(inSection.getByRole('textbox', { name: 'Filter board' })).toBeTruthy();
  // It opens until there is a choice: Parts and Nets, each kind on its one part; a part's pads and a net's stay shut.
  expect([...section.querySelectorAll('[data-board-row]')].map(row => row.getAttribute('data-board-row'))).toEqual([
    'group:parts', 'kind:Diodes', 'part:D1', 'kind:Resistors', 'part:R1', 'kind:Connectors', 'part:J1', 'group:nets', 'net:GND', 'net:LED', 'net:VBUS']);
  fireEvent.click(inSection.getByRole('button', { name: 'Select R1' }));
  expect(selected(controller)).toEqual(['#R1']);
  // The part's card is what the board says of it, in KiCad's millimetres, y down.
  expect(box(pane)!.textContent).toContain('R1');
  fireEvent.click(inSection.getByRole('button', { name: 'Isolate R1' }));
  expect(inSection.getByRole('button', { name: 'Exit isolate R1' }).getAttribute('aria-pressed')).toBe('true');
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.isolated?.value).toEqual({ selectors: ['#R1'] }));
  dispose();
});

it("a layer's eye hides it: the Display contract's layers, which reads as Custom and is kept with the file's view", async () => {
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  fireEvent.click(within(pane.querySelector<HTMLElement>('[data-file-sidebar-tools]')!).getByRole('button', { name: 'Layers' }));
  const layers = await waitFor(() => { const found = pane.querySelector<HTMLElement>('[data-board-layers]'); expect(found).not.toBeNull(); return found!; });
  expect([...layers.querySelectorAll('[data-layer-group]')].map(group => group.getAttribute('data-layer-group'))).toEqual(['front', 'back', 'other']);
  expect([...layers.querySelectorAll('[data-layer-row]')].map(row => row.getAttribute('data-layer-row')))
    .toEqual(['F.CrtYd', 'F.Fab', 'F.SilkS', 'F.Paste', 'F.Mask', 'F.Cu', 'B.Cu', 'B.Mask', 'Edge.Cuts', 'vias', 'ratsnest', 'drills']);
  // One glyph a row: a layer has nothing under it, so its glyph is its colour, and nothing stands before it.
  for (const row of layers.querySelectorAll('[data-layer-row]')) {
    expect([...row.querySelectorAll('[data-layer-glyph]')].map(glyph => glyph.getAttribute('data-layer-glyph'))).toEqual(['swatch']);
    expect(row.firstElementChild!.getAttribute('data-layer-glyph')).toBe('swatch');
  }
  fireEvent.click(layers.querySelector('[data-layer-visibility="F.Cu"]')!);
  await waitFor(() => expect(drawn.at(-1)!.layers).not.toContain('F.Cu'));
  expect(within(strip(pane)).getByRole('button', { name: 'Display mode: Custom' })).toBeTruthy();
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board?.value?.layers).toEqual(
    ['B.Mask', 'B.Cu', 'F.Mask', 'F.Paste', 'F.SilkS', 'F.Fab', 'Edge.Cuts', 'vias', 'ratsnest', 'drills']));
  // Shown again, the set is the mode's own: stored as the mode's, so a rebuild's new layer follows it.
  fireEvent.click(layers.querySelector('[data-layer-visibility="F.Cu"]')!);
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board?.value).toEqual({ mode: 'board', side: 'top', poured: true, layers: null }));
  dispose();
});

it('Display is a stock menu: a mode closes it; View from below and the pours leave it open, and are kept through a change of mode', async () => {
  const user = userEvent.setup({ skipHover: true, pointerEventsCheck: 0 });
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  await user.click(within(strip(pane)).getByRole('button', { name: 'Display mode: Board' }));
  const menu = await openMenu('Display');
  expect([...menu.querySelectorAll('[data-slot=dropdown-menu-label]')].map(label => label.textContent)).toEqual(['Display modes', 'Settings']);
  expect(within(menu).getAllByRole('menuitemradio').map(item => item.textContent)).toEqual(['Board', 'Copper', 'Assembly', 'Placement']);
  expect(within(menu).getAllByRole('menuitemcheckbox').map(item => item.textContent)).toEqual(['Copper pours', 'View from below']);
  await user.click(within(menu).getByRole('menuitemcheckbox', { name: 'View from below' }));
  await user.click(within(menu).getByRole('menuitemcheckbox', { name: 'Copper pours' }));
  expect(menuShown('Display')).not.toBeNull();
  // A switch is not a layer set: the mode is still the one on screen.
  expect(within(strip(pane)).getByRole('button', { name: 'Display mode: Board' })).toBeTruthy();
  await user.click(within(menu).getByRole('menuitemradio', { name: 'Copper' }));
  await waitFor(() => expect(menuShown('Display')).toBeNull());
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board?.value).toEqual({ mode: 'copper', side: 'bottom', poured: false, layers: null }));
  expect(drawn.at(-1)).toMatchObject({ side: 'bottom', layers: ['B.Cu', 'F.Cu', 'Edge.Cuts', 'vias', 'ratsnest', 'drills'] });
  dispose();
});

it("Measure snaps to pad centres, in millimetres, as its row's chip, and opens no Quick Edit; a note on a pick carries the view and its Display", async () => {
  const promptFiles = { create: vi.fn(async () => ({ snapshot: '/tmp/board.snapshot.json' })), read: vi.fn(), save: vi.fn() };
  const { pane, dispose } = await open('blinky.kicad_pcb', { promptFiles });
  await opened(pane);
  fireEvent.click(within(strip(pane)).getByRole('button', { name: 'Measure' }));
  // A little off each pad's centre: the ends land on the centres.
  tap(pane, [34.2, 15.1]);
  tap(pane, [35.8, 14.9]);
  const row = await within(pane).findByRole('toolbar', { name: 'Measurements' });
  expect(within(row).getByRole('button', { name: 'Measurement 1: 1.65 mm' })).toBeTruthy();
  expect(box(pane)).toBeNull();
  // Select takes a measurement first, so the note's pick is D1.1, off the measurement's ends.
  fireEvent.click(within(strip(pane)).getByRole('button', { name: 'Select' }));
  tap(pane, [20, 24.825]);
  const quickEdit = await waitFor(() => { expect(box(pane)).not.toBeNull(); return box(pane)!; });
  const note = within(quickEdit).getByRole('textbox', { name: 'Describe your changes' });
  note.textContent = 'Move this pad.';
  fireEvent.input(note);
  fireEvent.click(within(quickEdit).getByRole('button', { name: 'Copy Prompt' }));
  await waitFor(() => expect(promptFiles.create).toHaveBeenCalledTimes(1));
  const request = promptFiles.create.mock.calls[0][0] as any;
  expect(request).not.toHaveProperty('measurements');
  expect(request.views).toEqual([expect.objectContaining({ label: 'current view', display: { mode: 'board', side: 'top', poured: true } })]);
  expect(request.views[0].camera).toMatchObject({ up: [0, 1, 0] });
  dispose();
});

it('the live controller selects board references, declines a camera and a Display in words, fits and captures', async () => {
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  const controller = await controllerOf(view);
  const state = await controller.select({ selectors: ['#J1.2', '#net:VBUS'] });
  expect(state.selection.map((reference: any) => reference.target.selectors[0])).toEqual(['#J1.2', '#net:VBUS']);
  await expect(controller.select({ selectors: ['#U9'] })).rejects.toThrow(/Not on this board: #U9/);
  expect((await controller.clearSelection()).selection).toEqual([]);
  await expect(controller.setCamera({ position: [0, 0, 1], target: [0, 0, 0], up: [0, 1, 0] })).rejects.toThrow(/no camera to pose/);
  await expect(controller.setDisplaySettings({ mode: 'solid' })).rejects.toThrow(/Display .* is the person's/);
  expect(controller.readState()).toMatchObject({ active: true, loading: false, camera: null, boardDisplay: { mode: 'board', side: 'top', poured: true } });
  const fitted = frames.at(-1)!;
  await act(async () => { await controller.resetCamera(); });
  expect(frames.at(-1)).toEqual(fitted);
  expect((await controller.capture()).type).toBe('image/png');
  dispose();
});

it('paints after a StrictMode remount, as the development app mounts it', async () => {
  const { pane, dispose } = await open('blinky.kicad_pcb', { strict: true });
  await opened(pane);
  dispose();
});
