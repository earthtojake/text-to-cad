import { StrictMode, useState } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createCadClient } from '@cad/core/client';
import { pageToScreen } from '@cad/core/lib/plot2d/plot.js';
import { FileViewer } from '../../../dist/file-viewer/index.js';
import { createBoardRenderer } from '../../../dist/renderers/board/index.js';
// Loaded with the file, not inside the first test: the registration imports it lazily.
import '../../../dist/renderers/board/BoardRenderer.js';
import BOARD from './__fixtures__/board.plot.json';

// The board tab's chrome and its answers to the host, mounted the way a host mounts it: the
// FileViewer over the real registration and a real CAD client, whose backend is a fetch that
// answers with the committed the board's `plot` payload (`__fixtures__/README.md`: J1 at (5, 15), R1 at
// (35, 15), D1 at (20, 24), in KiCad's millimetres, which are the sheet's here). The pixels are the
// browser suite's; what the tab offers, what it picks and what a host is told are decided here.

// Every frame the pane paints places its rasters with `drawPlotImages` under the view's transform;
// the rasters themselves are `drawPlot`, which jsdom cannot draw and the pixels are not its to check.
const frames = vi.hoisted(() => [] as Array<{ scale: number; offsetX: number; offsetY: number }>);
const drawn = vi.hoisted(() => [] as Array<{ layers: string[]; side: string; poured: boolean }>);
vi.mock('@cad/core/lib/plot2d/index.js', async (importOriginal) => {
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
  const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    if (url.pathname.endsWith('/api/v1/documents') && init?.method === 'POST') {
      return json({ id: 'board', kind: 'kicad_pcb', api: '/api/v1/documents/kicad_pcb/board' }, 201);
    }
    if (url.pathname.endsWith('/api/v1/documents')) {
      return json({ documents: [{ entry: { kind: 'kicad_pcb', file, url: `/${name}`, hash: 'one', bytes: 4096 }, revision: 'one' }] });
    }
    if (url.pathname.endsWith('/api/v1/server')) return json({ backend: 'cadgen' });
    if (url.pathname.endsWith('/api/v1/documents/kicad_pcb/board/plot')) return readPlot();
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
/** Select's filter menu, opened from its chevron when a press on the board has put it away. */
const filterMenu = async (pane: HTMLElement, user: ReturnType<typeof userEvent.setup>) => {
  const shown = menuShown('Selection filter') as HTMLElement | null;
  if (shown) return shown;
  await user.click(within(strip(pane)).getByRole('button', { name: /^Selection filter:/ }));
  return openMenu('Selection filter');
};
/** Ticks or unticks one of the filter's boxes, the menu opened first. */
const toggleBox = async (pane: HTMLElement, user: ReturnType<typeof userEvent.setup>, name: string) => {
  await user.click(within(await filterMenu(pane, user)).getByRole('menuitemcheckbox', { name }));
};

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
  // The sidebar's tabs: the Circuit and its Layers, each its own glyph. Nothing is picked yet: no Quick Edit.
  const tiles = within(pane.querySelector<HTMLElement>('[data-file-sidebar-tools]')!).getAllByRole('button');
  expect(tiles.map(button => button.getAttribute('aria-label'))).toEqual(['Circuit', 'Layers']);
  expect(tiles[0].querySelector('svg.lucide-circuit-board')).not.toBeNull();
  expect(tiles[1].querySelector('svg.lucide-layers')).not.toBeNull();
  expect(box(pane)).toBeNull();
  dispose();
});

it('a native board uses the host language for its controls, tree and accessible canvas', async () => {
  const { pane, dispose } = await open('blinky.kicad_pcb', { locale: 'zh-CN' });
  await opened(pane);
  expect(pane.querySelector('canvas')?.getAttribute('aria-label')).toBe('电路板：blinky.kicad_pcb');
  expect(within(pane).getByRole('button', { name: '电路' })).toBeTruthy();
  fireEvent.click(within(pane).getByRole('button', { name: '电路' }));
  expect(within(pane).getByRole('textbox', { name: '筛选电路' })).toBeTruthy();
  expect(within(pane).getByRole('button', { name: '选择', exact: true })).toBeTruthy();
  expect(within(pane).getByText('电阻')).toBeTruthy();
  expect(within(pane).queryByText('Resistors')).toBeNull();
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
  // A press on the track takes the track, by the uuid KiCad saved it with; bare board lets go.
  tap(pane, [30, 15]);
  expect(selected(controller)).toEqual(['#track:7a1c0000-0000-4000-8000-000000000001']);
  await waitFor(() => expect([...box(pane)!.querySelectorAll('[data-quick-edit-ref] button[aria-label]')].map(button => button.getAttribute('aria-label')))
    .toEqual(['VBUS · track', 'Remove VBUS · track']));
  // The text over the board, and the via in the pour; under All, bare board inside the pour is nothing.
  tap(pane, [20, 5]);
  expect(selected(controller)).toEqual(['#text:7a1c0000-0000-4000-8000-000000000005']);
  tap(pane, [18, 27]);
  expect(selected(controller)).toEqual(['#via:7a1c0000-0000-4000-8000-000000000003']);
  tap(pane, [36, 26]);
  expect(selected(controller)).toEqual([]);
  dispose();
});

it("Select's filter is KiCad's grid of boxes: they tick what a click takes, All items ticks them all, and the menu stays up", async () => {
  const user = userEvent.setup({ skipHover: true, pointerEventsCheck: 0 });
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  const controller = await controllerOf(view);
  await user.click(within(strip(pane)).getByRole('button', { name: 'Selection filter: everything' }));
  const menu = await openMenu('Selection filter');
  const boxes = () => within(menu).getAllByRole('menuitemcheckbox').map(item => [item.textContent, item.getAttribute('aria-checked')]);
  // KiCad's two columns, row by row, each box its name alone; every kind ticked and no locked items as a board opens.
  expect(menu.querySelectorAll('[data-select-filter] > svg')).toHaveLength(0);
  expect(boxes()).toEqual([['All items', 'true'], ['Locked items', 'false'], ['Footprints', 'true'], ['Text', 'true'], ['Tracks', 'true'],
    ['Vias', 'true'], ['Pads', 'true'], ['Graphics', 'true'], ['Zones', 'true'], ['Rule Areas', 'true'], ['Dimensions', 'true']]);
  // All items unticks every kind, and the menu stays up for the next box.
  await user.click(within(menu).getByRole('menuitemcheckbox', { name: 'All items' }));
  expect(boxes().filter(([, checked]) => checked === 'true')).toEqual([]);
  await user.click(within(menu).getByRole('menuitemcheckbox', { name: 'Footprints' }));
  expect(menuShown('Selection filter')).not.toBeNull();
  expect(boxes()[0]).toEqual(['All items', 'mixed']);
  expect(within(strip(pane)).getByRole('button', { name: 'Selection filter: Footprints' })).toBeTruthy();
  // R1.1, under the VBUS track's end: the part, not the pad or the copper.
  tap(pane, [34.175, 15]);
  expect(selected(controller)).toEqual(['#R1']);
  // A press on the board puts the menu away, as any dropdown's outside press does.
  expect(menuShown('Selection filter')).toBeNull();
  // Zones alone takes the pour anywhere inside it; Graphics without Footprints a part's own silkscreen line.
  await toggleBox(pane, user, 'Footprints');
  await toggleBox(pane, user, 'Zones');
  tap(pane, [10, 20]);
  expect(selected(controller)).toEqual(['#zone:7a1c0000-0000-4000-8000-000000000004']);
  await toggleBox(pane, user, 'Zones');
  await toggleBox(pane, user, 'Graphics');
  tap(pane, [5.6, 16.27]);  // J1's silkscreen line between its pins, from (3.62, 16.27) to (6.38, 16.27)
  expect(selected(controller)).toEqual([`#shape:${(BOARD as any).sheets[0].layers.find((layer: any) => layer.id === 'F.SilkS').items
    .find((item: any) => item.ref === '#J1' && item.pts?.every((point: number[]) => point[1] === 16.27)).id}`]);
  // Nothing ticked takes nothing: a click clears.
  await toggleBox(pane, user, 'Graphics');
  tap(pane, [34.175, 15]);
  expect(selected(controller)).toEqual([]);
  dispose();
});

it('a locked footprint is no pick until Locked items is ticked, but for its pads, as KiCad lets a click take one', async () => {
  const user = userEvent.setup({ skipHover: true, pointerEventsCheck: 0 });
  const board = JSON.parse(JSON.stringify(BOARD));
  board.board.parts.find((part: any) => part.ref === 'R1').locked = true;
  readPlot = () => json(board);
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  const controller = await controllerOf(view);
  tap(pane, [34.175, 15]);
  expect(selected(controller)).toEqual(['#R1.1']);
  await toggleBox(pane, user, 'All items');
  await toggleBox(pane, user, 'Footprints');
  tap(pane, [34.175, 15]);
  expect(selected(controller)).toEqual([]);
  await toggleBox(pane, user, 'Locked items');
  tap(pane, [34.175, 15]);
  expect(selected(controller)).toEqual(['#R1']);
  dispose();
});

it("a drag under Select draws the box and names the area on the working layer; the other drags pan as the 3D views' do; a jittered click is a click", async () => {
  const promptFiles = { create: vi.fn(async () => ({ snapshot: '/tmp/board.snapshot.json' })), read: vi.fn(), save: vi.fn() };
  const view = await open('blinky.kicad_pcb', { promptFiles });
  const { pane, dispose } = view;
  await opened(pane);
  const controller = await controllerOf(view);
  const canvas = pane.querySelector<HTMLCanvasElement>('[data-board-surface] canvas')!;
  const at = ([x, y]: [number, number]) => { const [clientX, clientY] = pageToScreen(frames.at(-1)!, x, y); return { clientX, clientY }; };
  const press = { pointerId: 1, pointerType: 'mouse', button: 0 };
  // A click that wavers a pixel or two is still a click: R1.1.
  const r11 = at([34.175, 15]);
  fireEvent.pointerDown(canvas, { ...press, ...r11 });
  fireEvent.pointerMove(canvas, { ...press, clientX: r11.clientX + 2, clientY: r11.clientY + 1 });
  fireEvent.pointerUp(canvas, { ...press, clientX: r11.clientX + 2, clientY: r11.clientY + 1 });
  expect(selected(controller)).toEqual(['#R1.1']);
  // A drag is the box between its ends, on F.Cu, the copper seen from the top; Shift adds it; it does not pan.
  const before = { ...frames.at(-1)! };
  fireEvent.pointerDown(canvas, { ...press, ...at([30, 10]) });
  fireEvent.pointerMove(canvas, { ...press, ...at([34, 14]) });
  fireEvent.pointerMove(canvas, { ...press, ...at([40, 20]) });
  fireEvent.pointerUp(canvas, { ...press, ...at([40, 20]), shiftKey: true });
  expect(selected(controller)).toEqual(['#R1.1', '#F.Cu@x30y10..x40y20']);
  expect(frames.at(-1)).toEqual(before);
  // The middle button pans, as KiCad's does, and picks nothing.
  const middle = { pointerId: 2, pointerType: 'mouse', button: 1 };
  fireEvent.pointerDown(canvas, { ...middle, ...at([20, 15]) });
  fireEvent.pointerMove(canvas, { ...middle, ...at([25, 15]) });
  fireEvent.pointerUp(canvas, { ...middle, ...at([25, 15]) });
  await waitFor(() => expect(frames.at(-1)!.offsetX).toBeGreaterThan(before.offsetX));
  // The 3D views' drags: the right button's (a trackpad's two-finger click and drag) pans, and keeps the
  // browser's menu off; a left drag with Ctrl, Cmd or Shift pans; a right press that does not travel picks nothing.
  const pans = async (init: Record<string, unknown>, [dx, dy]: [number, number]) => {
    const was = { ...frames.at(-1)! };
    fireEvent.pointerDown(canvas, { ...press, ...init, ...at([20, 15]) });
    fireEvent.pointerMove(canvas, { ...press, ...init, ...at([20 + dx, 15 + dy]) });
    fireEvent.pointerUp(canvas, { ...press, ...init, ...at([20 + dx, 15 + dy]) });
    await waitFor(() => expect([frames.at(-1)!.offsetX, frames.at(-1)!.offsetY]).not.toEqual([was.offsetX, was.offsetY]));
  };
  expect(fireEvent.contextMenu(canvas)).toBe(false);
  await pans({ button: 2, pointerId: 3 }, [0, 5]);
  await pans({ ctrlKey: true }, [5, 0]);
  await pans({ metaKey: true }, [0, -5]);
  await pans({ shiftKey: true }, [-5, 0]);
  fireEvent.pointerDown(canvas, { ...press, button: 2, pointerId: 3, ...at([36, 26]) });
  fireEvent.pointerUp(canvas, { ...press, button: 2, pointerId: 3, ...at([36, 26]) });
  expect(selected(controller)).toEqual(['#R1.1', '#F.Cu@x30y10..x40y20']);
  const quickEdit = await waitFor(() => { expect(box(pane)).not.toBeNull(); return box(pane)!; });
  expect([...quickEdit.querySelectorAll('[data-quick-edit-ref] button[aria-label]')].map(button => button.getAttribute('aria-label')))
    .toEqual(['R1.1', 'Remove R1.1', 'area 10 × 10 mm', 'Remove area 10 × 10 mm']);
  // The note's packet names them, for a snapshot to light them where the person put them.
  const note = within(quickEdit).getByRole('textbox', { name: 'Describe your changes' });
  note.textContent = 'Keep this clear.';
  fireEvent.input(note);
  fireEvent.click(within(quickEdit).getByRole('button', { name: 'Copy Prompt' }));
  await waitFor(() => expect(promptFiles.create).toHaveBeenCalledTimes(1));
  expect((promptFiles.create.mock.calls[0] as any)[0].references).toEqual(['#R1.1', '#F.Cu@x30y10..x40y20']);
  await waitFor(() => expect(copied.at(-1)).toContain(`${FILE}#F.Cu@x30y10..x40y20`));
  // A click on bare board lets go of it all, as KiCad's does.
  tap(pane, [36, 26]);
  expect(selected(controller)).toEqual([]);
  dispose();
});

it('the Circuit tab is the parts in their schematic blocks, then the nets: a block selects its parts, a row selects and frames, an eye isolates', async () => {
  const board = JSON.parse(JSON.stringify(BOARD));
  const sheets: Record<string, string> = { J1: 'power', R1: 'led', D1: 'led' };
  for (const part of board.board.parts) part.sheet = sheets[part.ref];
  readPlot = () => json(board);
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  const controller = await controllerOf(view);
  fireEvent.click(within(pane.querySelector<HTMLElement>('[data-file-sidebar-tools]')!).getByRole('button', { name: 'Circuit' }));
  const section = await waitFor(() => { const found = pane.querySelector<HTMLElement>('[data-tool-panel-id="board"]'); expect(found).not.toBeNull(); return found!; });
  const inSection = within(section);
  expect(inSection.getByRole('textbox', { name: 'Filter circuit' })).toBeTruthy();
  const rows = () => [...section.querySelectorAll('[data-board-row]')].map(row => row.getAttribute('data-board-row'));
  // The blocks the footprints record, then the nets, open as a tree opens until there is a choice, a block of several
  // and the Nets shut: the tab opens as its blocks and "Nets (N)".
  expect(rows()).toEqual(['sheet:led', 'sheet:power', 'part:J1', 'group:nets']);
  const expandedOf = (id: string) => section.querySelector(`[data-board-row="${id}"] [aria-expanded]`)!.getAttribute('aria-expanded');
  expect(expandedOf('group:nets')).toBe('false');
  // Only a chevron opens or shuts a row: the Nets' name is a label, and a press on it does nothing.
  fireEvent.click(section.querySelector('[data-board-group="group:nets"]')!);
  expect(expandedOf('group:nets')).toBe('false');
  expect(inSection.queryByRole('button', { name: 'Nets' })).toBeNull();
  fireEvent.click(inSection.getByRole('button', { name: 'Expand Nets' }));
  expect(rows()).toEqual(['sheet:led', 'sheet:power', 'part:J1', 'group:nets', 'net:GND', 'net:LED', 'net:VBUS']);
  fireEvent.click(inSection.getByRole('button', { name: 'Collapse Nets' }));
  expect(rows()).toEqual(['sheet:led', 'sheet:power', 'part:J1', 'group:nets']);
  // A net picked on the board opens the Nets, its row brought into view.
  await act(async () => { await controller.select({ selectors: ['#net:LED'] }); });
  await waitFor(() => expect(rows()).toEqual(['sheet:led', 'sheet:power', 'part:J1', 'group:nets', 'net:GND', 'net:LED', 'net:VBUS']));
  await act(async () => { await controller.clearSelection(); });
  // A block's name selects every part in it, a chip each, and frames them; the block stays shut.
  const fitted = { ...frames.at(-1)! };
  fireEvent.click(inSection.getByRole('button', { name: 'Select led' }));
  expect(selected(controller)).toEqual(['#D1', '#R1']);
  await new Promise(resolve => setTimeout(resolve, 0));
  expect(expandedOf('sheet:led')).toBe('false');
  expect(rows()).not.toContain('part:R1');
  await waitFor(() => expect(frames.at(-1)!.scale).toBeGreaterThan(fitted.scale));
  await waitFor(() => expect([...box(pane)!.querySelectorAll('[data-quick-edit-ref] button[aria-label]')].map(b => b.getAttribute('aria-label'))
    .filter(label => !label!.startsWith('Remove'))).toEqual(['D1', 'R1']));
  expect(section.querySelector('[data-board-row="sheet:led"]')!.className).toContain('bg-accent');
  // A part selects as a click on the board does, and frames it.
  const before = { ...frames.at(-1)! };
  fireEvent.click(inSection.getByRole('button', { name: 'Select J1' }));
  expect(selected(controller)).toEqual(['#J1']);
  await waitFor(() => expect(frames.at(-1)!.offsetX).not.toBe(before.offsetX));
  // The filter finds a part by its value and a net by its name.
  fireEvent.change(inSection.getByRole('textbox', { name: 'Filter circuit' }), { target: { value: 'VBUS' } });
  await waitFor(() => expect(section.querySelector('[data-search-row="net:VBUS"]')).not.toBeNull());
  fireEvent.click(within(section.querySelector<HTMLElement>('[data-search-row="net:VBUS"]')!).getByRole('button', { name: 'Select VBUS' }));
  expect(selected(controller)).toEqual(['#net:VBUS']);
  fireEvent.change(inSection.getByRole('textbox', { name: 'Filter circuit' }), { target: { value: '' } });
  fireEvent.click(inSection.getByRole('button', { name: 'Isolate J1' }));
  expect(inSection.getByRole('button', { name: 'Exit isolate J1' }).getAttribute('aria-pressed')).toBe('true');
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.isolated?.value).toEqual({ selectors: ['#J1'] }));
  // A pad picked on the board opens its block and its part, and its row, below the panel's view, is scrolled to.
  const scrolled: string[] = [];
  const { scrollIntoView } = Element.prototype;
  Element.prototype.scrollIntoView = function (this: Element) { scrolled.push(this.getAttribute('data-virtual-row') || ''); };
  const page = { x: 0, y: 0, left: 0, top: 0, right: 1200, bottom: 700, width: 1200, height: 700, toJSON: noop };
  vi.mocked(HTMLElement.prototype.getBoundingClientRect).mockImplementation(function (this: HTMLElement) {
    return (this.getAttribute('data-virtual-row') === 'pad:R1.2' ? { ...page, top: 900, bottom: 924, height: 24 } : page) as DOMRect;
  });
  try {
    tap(pane, [35.825, 15]);
    expect(selected(controller)).toEqual(['#R1.2']);
    await waitFor(() => expect(expandedOf('sheet:led')).toBe('true'));
    expect(expandedOf('part:R1')).toBe('true');
    await waitFor(() => expect(scrolled).toEqual(['pad:R1.2']));
  } finally { Element.prototype.scrollIntoView = scrollIntoView; }
  dispose();
});

it("Display holds KiCad's layer display options — Dim other layers, the zones' and tracks' opacity — and a Layers row's press makes it the active layer", async () => {
  const user = userEvent.setup({ skipHover: true, pointerEventsCheck: 0 });
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  fireEvent.click(within(pane.querySelector<HTMLElement>('[data-file-sidebar-tools]')!).getByRole('button', { name: 'Layers' }));
  const layers = await waitFor(() => { const found = pane.querySelector<HTMLElement>('[data-board-layers]'); expect(found).not.toBeNull(); return found!; });
  // The Layers tab is the layer list alone: how the layers are drawn is Display's.
  expect(pane.querySelector('[data-cad-file-sidebar] [role=checkbox], [data-cad-file-sidebar] [role=slider]')).toBeNull();
  // KiCad's own as a board opens: F.Cu active (its dot), nothing dimmed, the zones at 60%, the tracks at 100%.
  expect(layers.querySelector('[data-layer-row="F.Cu"] [data-layer-active]')).not.toBeNull();
  expect(drawn.at(-1)).toMatchObject({ active: null, dim: null, zones: 0.6, tracks: 1 });
  await user.click(within(strip(pane)).getByRole('button', { name: 'Display mode: Board' }));
  const menu = await openMenu('Display');
  expect(within(menu).getByRole('slider', { name: 'Zone opacity' }).getAttribute('aria-valuenow')).toBe('0.6');
  expect((within(menu).getByRole('textbox', { name: 'Track opacity value' }) as HTMLInputElement).value).toBe('100%');
  await user.click(within(menu).getByRole('menuitemcheckbox', { name: 'Dim other layers' }));
  await waitFor(() => expect(drawn.at(-1)).toMatchObject({ dim: 'F.Cu' }));
  // The zones' opacity, typed into its value: the menu stays up, the keys the field's.
  const zones = within(menu).getByRole('textbox', { name: 'Zone opacity value' });
  await user.clear(zones);
  await user.type(zones, '25{Enter}');
  await waitFor(() => expect(drawn.at(-1)).toMatchObject({ zones: 0.25 }));
  // Escape in a value puts its draft back and leaves the menu open.
  await user.type(zones, '9');
  await user.keyboard('{Escape}');
  expect(menuShown('Display')).not.toBeNull();
  expect((zones as HTMLInputElement).value).toBe('25%');
  // A row's press: B.Cu active, drawn on top, the rest dimmed round it.
  await user.click(within(layers).getByRole('button', { name: 'Make B.Cu the active layer' }));
  await waitFor(() => expect(drawn.at(-1)).toMatchObject({ active: 'B.Cu', dim: 'B.Cu' }));
  expect(layers.querySelector('[data-layer-row="B.Cu"] [data-layer-active]')).not.toBeNull();
  expect(layers.querySelector('[data-layer-row="F.Cu"] [data-layer-active]')).toBeNull();
  // The board's area and what goes through the board are no active layer.
  expect(within(layers.querySelector<HTMLElement>('[data-layer-row="vias"]')!).queryByRole('button', { name: /active layer/ })).toBeNull();
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board?.value)
    .toEqual({ mode: 'board', side: 'top', poured: true, layers: null, active: 'B.Cu', dim: true, zones: 0.25, tracks: 1 }));
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
    .toEqual(['F.CrtYd', 'F.Fab', 'F.SilkS', 'F.Paste', 'F.Mask', 'F.Cu', 'B.Cu', 'B.Mask', 'Edge.Cuts', 'area', 'vias', 'drills', 'ratsnest', 'names']);
  // One glyph a row: a layer has nothing under it, so its glyph is its colour, and nothing stands before it.
  for (const row of layers.querySelectorAll('[data-layer-row]')) {
    expect([...row.querySelectorAll('[data-layer-glyph]')].map(glyph => glyph.getAttribute('data-layer-glyph'))).toEqual(['swatch']);
    expect(row.firstElementChild!.getAttribute('data-layer-glyph')).toBe('swatch');
  }
  fireEvent.click(layers.querySelector('[data-layer-visibility="F.Cu"]')!);
  await waitFor(() => expect(drawn.at(-1)!.layers).not.toContain('F.Cu'));
  expect(within(strip(pane)).getByRole('button', { name: 'Display mode: Custom' })).toBeTruthy();
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board?.value?.layers).toEqual(
    ['area', 'B.Mask', 'B.Cu', 'Edge.Cuts', 'F.Fab', 'F.CrtYd', 'F.Paste', 'F.SilkS', 'F.Mask', 'drills', 'vias', 'ratsnest', 'names']));
  // Shown again, the set is the mode's own: stored as the mode's, so a rebuild's new layer follows it.
  fireEvent.click(layers.querySelector('[data-layer-visibility="F.Cu"]')!);
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board?.value).toEqual({ mode: 'board', side: 'top', poured: true, layers: null, active: null, dim: false, zones: 0.6, tracks: 1 }));
  dispose();
});

it('Display is a stock menu: a mode closes it; View from below and the pours leave it open, and are kept through a change of mode', async () => {
  const user = userEvent.setup({ skipHover: true, pointerEventsCheck: 0 });
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  await user.click(within(strip(pane)).getByRole('button', { name: 'Display mode: Board' }));
  const menu = await openMenu('Display');
  expect([...menu.querySelectorAll('[data-slot=dropdown-menu-label]')].map(label => label.textContent)).toEqual(['Display modes', 'Settings', 'Opacity']);
  expect(within(menu).getAllByRole('menuitemradio').map(item => item.textContent)).toEqual(['Board', 'Copper', 'Assembly', 'Placement']);
  expect(within(menu).getAllByRole('menuitemcheckbox').map(item => item.textContent)).toEqual(['Copper pours', 'View from below', 'Dim other layers']);
  expect(within(menu).getAllByRole('slider').map(slider => slider.getAttribute('aria-label'))).toEqual(['Zone opacity', 'Track opacity']);
  await user.click(within(menu).getByRole('menuitemcheckbox', { name: 'View from below' }));
  await user.click(within(menu).getByRole('menuitemcheckbox', { name: 'Copper pours' }));
  expect(menuShown('Display')).not.toBeNull();
  // A switch is not a layer set: the mode is still the one on screen.
  expect(within(strip(pane)).getByRole('button', { name: 'Display mode: Board' })).toBeTruthy();
  await user.click(within(menu).getByRole('menuitemradio', { name: 'Copper' }));
  await waitFor(() => expect(menuShown('Display')).toBeNull());
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board?.value).toEqual({ mode: 'copper', side: 'bottom', poured: false, layers: null, active: null, dim: false, zones: 0.6, tracks: 1 }));
  expect(drawn.at(-1)).toMatchObject({ side: 'bottom', layers: ['area', 'B.Cu', 'Edge.Cuts', 'F.Cu', 'drills', 'vias', 'ratsnest', 'names'] });
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
  expect(request.views).toEqual([expect.objectContaining({ label: 'current view', display: { mode: 'board', side: 'top', poured: true, dim: false, zones: 0.6, tracks: 1 } })]);
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
