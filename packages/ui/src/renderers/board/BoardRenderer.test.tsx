import { StrictMode, useMemo, useState } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createCadClient } from '@cad/core/client';
import { APP_THEME_COLORS } from '@cad/core/lib/appTheme.js';
import { pageToScreen, screenToPage } from '@cad/core/lib/plot2d/plot.js';
import { FileViewer } from '../../../dist/file-viewer/index.js';
import { createBoardRenderer } from '../../../dist/renderers/board/index.js';
import { VIEW_CORNER_SURFACE_CLASS, VIEW_CORNER_TOOLBAR_CLASS } from '../../../dist/renderers/kit/shell/ViewCorner.js';
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
// The theme each raster and frame is drawn in, and the canvas each paint clears to.
const themes = vi.hoisted(() => [] as Array<string | null>);
const canvases = vi.hoisted(() => [] as Array<string | null>);
vi.mock('@cad/core/lib/plot2d/index.js', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    drawPlot: (_ctx: unknown, _layout: unknown, { view, theme }: { view: any, theme?: string }) => { if (view) drawn.push(view); themes.push(theme ?? null); },
    drawPlotImages: (_ctx: unknown, _layout: unknown, { transform }: { transform: any }) => { frames.push({ ...transform }); }
  };
});
// The board in 3D mounts the 3D views' viewport, which needs WebGL: a stand-in here, which says it has
// presented and answers the camera calls; the pixels and the picks through it are the browser suite's.
const viewport3d = vi.hoisted(() => ({ props: null as any, calls: [] as string[] }));
vi.mock('../../../dist/renderers/kit/shell/ShellViewport.js', async () => {
  const React = await import('react');
  return {
    default: React.forwardRef(function StandInViewport(props: any, ref) {
      viewport3d.props = props;
      React.useImperativeHandle(ref, () => ({
        captureScreenshotBlob: async () => new Blob(['pixels'], { type: 'image/png' }),
        getPerspective: () => ({ position: [10, -40, 30], target: [10, 0, 0], up: [0, 0, 1] }),
        setPerspective: (camera: any) => { viewport3d.calls.push(`setPerspective ${JSON.stringify(camera.position)}`); return true; },
        goHome: () => { viewport3d.calls.push('goHome'); return true; },
        resetZoom: () => { viewport3d.calls.push('resetZoom'); return true; },
        zoomToBounds: () => true, zoomPercent: () => 100, subscribeCamera: () => () => {}, zoomBy: () => true, zoomTo100: () => true
      }));
      const hostRef = React.useRef<HTMLDivElement | null>(null);
      const runtimeRef = React.useRef<any>(null);
      React.useEffect(() => { props.onPresentationChange?.({ key: props.modelKey, preparing: false }); }, [props.modelKey]);
      const context = { hostRef, runtimeRef, mountRef: hostRef, viewerReadyTick: 1, commitScene: () => true };
      return <div ref={hostRef} data-stand-in-viewport="">
        <canvas ref={canvas => { runtimeRef.current = canvas ? { renderer: { domElement: canvas, capabilities: { maxTextureSize: 4096 }, initTexture() {} }, requestRender() {} } : null; }} />
        {typeof props.children === 'function' ? props.children(context) : props.children}
      </div>;
    })
  };
});
vi.mock('@cad/core/lib/drawing2d/index.js', async (importOriginal) => {
  const actual = await importOriginal<Record<string, any>>();
  return { ...actual, clearSurface: (ctx: unknown, options: { background?: string }) => { canvases.push(options.background ?? null); return actual.clearSurface(ctx, options); } };
});

const noop = () => {};
const FILE = '/models/blinky.kicad_pcb';
const KEY = JSON.stringify([FILE, 'board']);
let copied: string[] = [];
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const UNREADABLE = 'broken.kicad_pcb is not a KiCad board: a .kicad_pcb starts with (kicad_pcb ...)';
let readPlot: () => Response | Promise<Response> = () => json(BOARD);
const DESTINATION = { kind: 'clipboard', available: true };
// A Select (the Layers tab's choices) asks the element under the pointer about its capture and scrolls its option in, which jsdom cannot.
const restores: (() => void)[] = [];
const context2d = new Proxy({}, { get: (_target, key) => (key === 'canvas' ? undefined : key === 'measureText' ? (text: string) => ({ width: text.length * 7 }) : noop), set: () => true });

beforeEach(() => {
  frames.length = 0;
  drawn.length = 0;
  themes.length = 0;
  canvases.length = 0;
  copied = [];
  readPlot = () => json(BOARD);
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => setTimeout(() => callback(performance.now()), 0));
  vi.stubGlobal('cancelAnimationFrame', (handle: number) => clearTimeout(handle));
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: false, media: query, addEventListener: noop, removeEventListener: noop, addListener: noop, removeListener: noop }));
  vi.stubGlobal('Path2D', class { constructor() { return new Proxy(this, { get: (target, key) => (key in target ? (target as any)[key] : noop) }); } });
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  for (const [name, value] of Object.entries({ scrollIntoView() {}, hasPointerCapture: () => false, setPointerCapture() {}, releasePointerCapture() {} })) {
    const previous = Object.getOwnPropertyDescriptor(Element.prototype, name);
    Object.defineProperty(Element.prototype, name, { configurable: true, writable: true, value });
    restores.push(() => previous ? Object.defineProperty(Element.prototype, name, previous) : delete (Element.prototype as any)[name]);
  }
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(
    { x: 0, y: 0, left: 0, top: 0, right: 1200, bottom: 700, width: 1200, height: 700, toJSON: noop } as DOMRect);
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context2d as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(function (callback, type) {
    setTimeout(() => callback(new Blob(['png'], { type: type || 'image/png' })), 0);
  });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); while (restores.length) restores.pop()!(); });

/** One pane: a host, a workspace with one board, a live binding, and the tab. */
async function open(name = 'blinky.kicad_pcb', { strict = false, promptFiles = undefined as any, locale = "en", state = { renderers: {} } as any, models = null as any } = {}) {
  const file = `/models/${name}`;
  let revision = 'one';
  const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    // A model the models table names, opened by its document id, and its (empty) structure.
    const opened = init?.method === 'POST' ? JSON.parse(String(init.body || '{}')).id : null;
    if (url.pathname.endsWith('/api/v1/documents') && opened) return json({ id: opened, kind: 'step', api: `/api/v1/documents/step/${opened}` }, 201);
    if (url.pathname.includes('/api/v1/documents/step/') && url.pathname.endsWith('/structure')) return json({ prototypes: [], instances: [] });
    if (url.pathname.endsWith('/api/v1/documents') && init?.method === 'POST') {
      return json({ id: 'board', kind: 'kicad_pcb', api: '/api/v1/documents/kicad_pcb/board' }, 201);
    }
    if (url.pathname.endsWith('/api/v1/documents')) {
      return json({ documents: [{ entry: { kind: 'kicad_pcb', file, url: `/${name}`, hash: revision, bytes: 4096 }, revision }] });
    }
    if (url.pathname.endsWith('/api/v1/server')) return json({ backend: 'cadgen' });
    if (url.pathname.endsWith('/api/v1/documents/kicad_pcb/board/plot')) return readPlot();
    if (models && url.pathname.endsWith('/api/v1/documents/kicad_pcb/board/models')) return json({ models });
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
  let latest: any = state;
  // The person's theme, switched as the app menu's Theme switches it: a new environment for the view.
  let setScheme: (scheme: 'light' | 'dark') => void = noop;
  function Pane() {
    const [state, setState] = useState<any>(latest);
    const [scheme, setSchemeState] = useState<'light' | 'dark'>('light');
    setScheme = setSchemeState;
    const themed = useMemo(() => ({ ...host, environment: { ...host.environment, colorScheme: scheme } }), [scheme]);
    latest = state;
    return <section data-testid="pane"><FileViewer file={file} host={themed as any} renderers={renderers} state={state} onStateChange={setState} /></section>;
  }
  render(strict ? <StrictMode><Pane /></StrictMode> : <Pane />);
  const pane = screen.getByTestId('pane');
  return { pane, get controller() { return controller; }, get state() { return latest; }, scheme: (next: 'light' | 'dark') => act(() => setScheme(next)),
    dispose: () => client.dispose(), fetch,
    // The board saved again: a new revision, read as the catalog's next answer says.
    saved: async () => { revision = `${revision}+`; await act(() => client.refresh()); } };
}

const opened = async (pane: HTMLElement) => {
  await waitFor(() => expect(pane.querySelector('[data-board-surface] [aria-busy="false"]')).not.toBeNull());
  await waitFor(() => expect(frames.length).toBeGreaterThan(0));
};
const strip = (pane: HTMLElement) => within(pane).getByRole('group', { name: 'Interaction tools' });
// The view's corner's column over the zoom pill (`ViewCorner.jsx`'s `ViewPillColumn`): Display, 2D/3D and Flip, from the top down.
const corner = (pane: HTMLElement) => pane.querySelector<HTMLElement>('[data-view-pill-column]')!;
const cornerButtons = (pane: HTMLElement) => [...corner(pane).querySelectorAll('button')].map(button => button.getAttribute('aria-label') || button.textContent);
// 2D/3D and Flip, each by what its name says it is ("View: 2D", "Side: Top").
const dimensionButton = (pane: HTMLElement) => within(corner(pane)).getByRole('button', { name: /^View: / });
const flipButton = (pane: HTMLElement) => within(corner(pane)).getByRole('button', { name: /^Side: / });
// A button's state as the screen shows it: its name, its Lucide icon, its fill (`secondary`: the strip's pressed fill).
const shown = (button: HTMLElement) => [button.getAttribute('aria-label'), [...button.querySelector('svg')!.classList].find(name => name.startsWith('lucide-')),
  button.getAttribute('data-variant')];
const box = (pane: HTMLElement) => pane.querySelector<HTMLElement>('[data-quick-edit-box]');
// The view's panel (`kit/shell/FlatPanel.jsx`), a tab of it by name, its search box, and one of its tabs' bodies.
const panel = (pane: HTMLElement) => pane.querySelector<HTMLElement>('[data-flat-panel]')!;
const showTab = (pane: HTMLElement, name: string) => fireEvent.click(within(panel(pane)).getByRole('tab', { name }));
const searchBox = (pane: HTMLElement) => within(panel(pane)).getByRole('textbox', { name: 'Search the board' }) as HTMLInputElement;
const tabBody = (pane: HTMLElement, id: string) => pane.querySelector<HTMLElement>(`[data-flat-panel-section="${id}"]`)!;
// The strip's Display popover, opened if it is not.
// How the board is drawn, now and then: the Layers tab's Preset over the layers and Layer display under them.
const displayMenu = async (user: ReturnType<typeof userEvent.setup>, pane: HTMLElement) => {
  const tab = within(pane.querySelector<HTMLElement>('[data-flat-panel]')!).queryByRole('tab', { name: 'Layers' });
  if (tab && tab.getAttribute('aria-selected') !== 'true') await user.click(tab);
  return waitFor(() => { const found = pane.querySelector<HTMLElement>('[data-flat-panel-section="layers"]'); expect(found?.querySelector('[data-board-display-settings]')).toBeTruthy(); return found!; });
};
/** A choice of Display's, by its accessible name: its Select opened, the option pressed. */
const choose = async (user: ReturnType<typeof userEvent.setup>, pane: HTMLElement, name: string, option: string) => {
  await user.click(within(await displayMenu(user, pane)).getByRole('combobox', { name }));
  await user.click(await screen.findByRole('option', { name: option }));
};
const choice = async (user: ReturnType<typeof userEvent.setup>, pane: HTMLElement, name: string) =>
  within(await displayMenu(user, pane)).getByRole('combobox', { name }).textContent;
/** The corner's Display: its menu of presets, opened (portalled, as every dropdown is). */
const presetMenu = async (user: ReturnType<typeof userEvent.setup>, pane: HTMLElement) => {
  if (!menuShown('Display')) await user.click(within(corner(pane)).getByRole('button', { name: /^Display mode:/ }));
  return openMenu('Display');
};
/** The preset Display has ticked (Custom while the eyes have left the preset's set), the menu put away again. */
const presetChoice = async (user: ReturnType<typeof userEvent.setup>, pane: HTMLElement) => {
  const menu = await presetMenu(user, pane);
  const ticked = menu.querySelector('[role=menuitemradio][aria-checked=true]')?.textContent ?? null;
  await user.keyboard('{Escape}');
  await waitFor(() => expect(menuShown('Display')).toBeNull());
  return ticked;
};
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

it("a board's strip is a drawing's — Select (in hand), Pencil, Shapes, Measure — then the side in the view's corner; its panel is docked, open, the Parts, the Nets, then the Layers", async () => {
  const { pane, dispose } = await open();
  await opened(pane);
  const tools = strip(pane);
  expect([...tools.querySelectorAll(':scope button[aria-pressed]')].filter(button => !button.closest('[data-view-controls]'))
    .map(button => button.getAttribute('aria-label'))).toEqual(['Select', 'Pencil', 'Shapes', 'Measure']);
  expect(within(tools).getByRole('button', { name: 'Select' }).getAttribute('aria-pressed')).toBe('true');
  expect(within(tools).getByRole('button', { name: 'Selection filter: everything' })).toBeTruthy();
  // Its view controls on the screen are the corner's column over the zoom pill: Display, 2D/3D and Flip; the strip has none.
  expect(tools.querySelector('[data-view-controls]')).toBeNull();
  expect(cornerButtons(pane)).toEqual(['Display mode: Board', 'View: 2D', 'Side: Top']);
  expect(pane.querySelector('[data-zoom-pill] [data-zoom-control]')!.textContent).toBe('100%');
  // Every corner control is the strip's own 24px button carrying the corner's one surface (`ViewCorner.jsx`), with
  // nothing round it and no border or shadow: Display, 2D/3D and Flip, the column's own children; the pill one
  // row of the same buttons on that surface.
  const classes = (element: Element) => [...element.classList];
  const surface = VIEW_CORNER_SURFACE_CLASS.split(' ');
  const column = [...corner(pane).children] as HTMLElement[];
  expect(column.map(element => element.tagName)).toEqual(['BUTTON', 'BUTTON', 'BUTTON']);
  const pill = pane.querySelector<HTMLElement>('[data-zoom-pill]')!;
  expect(VIEW_CORNER_TOOLBAR_CLASS.split(' ').every(name => pill.classList.contains(name))).toBe(true);
  for (const button of [...column, ...pill.querySelectorAll<HTMLElement>('button')]) expect(classes(button)).toContain('size-6');
  for (const control of [...column, pill]) {
    expect(surface.every(name => control.classList.contains(name)), control.getAttribute('aria-label') || 'pill').toBe(true);
    expect(classes(control).some(name => /^(border|shadow-(sm|md|lg))/.test(name))).toBe(false);
  }
  // The pill's buttons stand on its surface, not on a second one of their own.
  for (const button of pill.querySelectorAll('button')) expect(surface.some(name => button.classList.contains(name))).toBe(false);
  // 2D/3D and Flip are the view's state button, Projection's (`kit/shell/StateButton.jsx`), a tile like Display's.
  expect([...corner(pane).querySelectorAll('[data-state-button]')]).toEqual([dimensionButton(pane), flipButton(pane)]);
  const display = within(corner(pane)).getByRole('button', { name: /^Display mode:/ });
  for (const button of [dimensionButton(pane), flipButton(pane)]) expect(button.className).toBe(display.className);
  for (const name of ['Preview', 'Projection', 'Explode', 'Clip', 'Orbit', 'Position', 'Animation', 'Settings']) {
    expect(within(pane).queryByRole('button', { name }), name).toBeNull();
  }
  // The panel, docked at the left: the search over every tab, its collapse button after it, then the tabs, buttons.
  const aside = panel(pane);
  expect([aside.getAttribute('data-flat-panel'), aside.hidden]).toEqual(['docked', false]);
  const head = aside.querySelector<HTMLElement>('[data-flat-panel-head]')!;
  expect(head.firstElementChild!.hasAttribute('data-flat-panel-search')).toBe(true);
  expect(head.lastElementChild!.getAttribute('aria-label')).toBe('Hide panel');
  expect(head.lastElementChild!.getAttribute('aria-keyshortcuts')).toMatch(/\\$/);
  // The search field and the collapse button on the boxes' line, 8px in, as the tabs' buttons below them.
  expect(head.style.padding).toBe('8px 8px 6px');
  expect(searchBox(pane).placeholder).toBe('Search');
  expect(within(aside).getAllByRole('tab').map(tab => [tab.querySelector('[data-flat-panel-tab-name]')!.textContent, tab.getAttribute('aria-selected')])).toEqual([['Parts', 'true'], ['Nets', 'false'], ['Layers', 'false']]);
  expect(aside.querySelector('[role=tab] svg')).toBeNull();
  expect(tabBody(pane, 'parts').hidden).toBe(false);
  expect(tabBody(pane, 'nets').hidden).toBe(true);
  expect(tabBody(pane, 'layers').hidden).toBe(true);
  // The Layers tab is the layer list alone.
  expect(within(tabBody(pane, 'layers')).queryAllByRole('combobox')).toEqual([]);
  // Nothing is picked yet: no Quick Edit.
  expect(box(pane)).toBeNull();

  dispose();
});

it('a native board uses the host language for its controls, tree and accessible canvas', async () => {
  const { pane, dispose } = await open('blinky.kicad_pcb', { locale: 'zh-CN' });
  await opened(pane);
  expect(pane.querySelector('canvas')?.getAttribute('aria-label')).toBe('电路板：blinky.kicad_pcb');
  expect(within(panel(pane)).getByRole('tab', { name: '元件' }).getAttribute('aria-selected')).toBe('true');
  expect(within(panel(pane)).getByRole('textbox', { name: '搜索电路板' })).toBeTruthy();
  expect(within(pane).getByRole('button', { name: '选择', exact: true })).toBeTruthy();
  expect(within(pane).getByText('电阻')).toBeTruthy();
  expect(within(pane).queryByText('Resistors')).toBeNull();

  dispose();
});

it('a board without its index is the picture, its corner, and its Layers (with the layer display): no tools, no Parts or Nets, no Quick Edit', async () => {
  const { board: _index, ...picture } = BOARD as any;
  readPlot = () => json(picture);
  const { pane, dispose } = await open();
  await opened(pane);
  expect(pane.querySelector('canvas')?.getAttribute('aria-label')).toBe('Board: blinky.kicad_pcb');
  // No tools, so no strip; Display, 2D/3D and Flip in the corner's column over the zoom pill.
  expect(within(pane).queryByRole('group', { name: 'Interaction tools' })).toBeNull();
  expect(cornerButtons(pane)).toEqual(['Display mode: Board', 'View: 2D', 'Side: Top']);
  // Its one list, with no row of tabs over it.
  expect(within(panel(pane)).queryAllByRole('tab')).toEqual([]);
  expect(within(panel(pane)).getByRole('region', { name: 'Layers' })).toBeTruthy();
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
  expect(pane.querySelector('[data-flat-panel], [data-flat-panel-pill]')).toBeNull();
  await act(async () => { answer!(json({ error: UNREADABLE }, 400)); });
  const alert = await within(pane).findByRole('alert');
  expect(alert.textContent).toContain('is not a KiCad board');
  expect(within(pane).queryByRole('group', { name: 'Interaction tools' })).toBeNull();
  expect(pane.querySelector('[data-flat-panel], [data-flat-panel-pill]')).toBeNull();
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
  // A right press that does not travel picks nothing: it opens the view's menu, here over bare board.
  const menuAt = async (point: [number, number]) => {
    fireEvent.pointerDown(canvas, { ...press, button: 2, pointerId: 3, ...at(point) });
    fireEvent.pointerUp(canvas, { ...press, button: 2, pointerId: 3, ...at(point) });
    return within(await screen.findByRole('menu')).getAllByRole('menuitem').map(item => item.textContent);
  };
  const closeMenu = async () => { fireEvent.keyDown(screen.getByRole('menu'), { key: 'Escape' }); await waitFor(() => expect(screen.queryByRole('menu')).toBeNull()); };
  expect(await menuAt([36, 26])).toEqual(['Zoom to fit', 'Zoom to selection']);
  await closeMenu();
  expect(selected(controller)).toEqual(['#R1.1', '#F.Cu@x30y10..x40y20']);
  // Over a pad: its reference, Deselect (it is picked), its net, and the framing.
  const overPad = await menuAt([34.175, 15]);
  expect(overPad.slice(0, 2)).toEqual(['Copy Reference', 'Deselect']);
  expect(overPad.at(-2)).toBe('Zoom to fit');
  await closeMenu();
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

it('the Parts tab is the parts in their schematic blocks and the Nets tab the nets: a press selects, a double-click frames, an eye isolates', async () => {
  const board = JSON.parse(JSON.stringify(BOARD));
  const sheets: Record<string, string> = { J1: 'power', R1: 'led', D1: 'led' };
  for (const part of board.board.parts) part.sheet = sheets[part.ref];
  readPlot = () => json(board);
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  const controller = await controllerOf(view);
  const parts = await waitFor(() => { const found = tabBody(pane, 'parts'); expect(found).not.toBeNull(); return found!; });
  const nets = tabBody(pane, 'nets');
  const rows = (section: HTMLElement) => [...section.querySelectorAll('[data-board-row]')].map(row => row.getAttribute('data-board-row'));
  // The blocks the footprints record, a block of several shut; the nets, flat. A part is a row with no pads under it.
  expect(rows(parts)).toEqual(['sheet:led', 'sheet:power', 'part:J1']);
  expect(rows(nets)).toEqual(['net:GND', 'net:LED', 'net:VBUS']);
  fireEvent.click(within(parts).getByRole('button', { name: 'Expand led' }));
  expect(rows(parts)).toEqual(['sheet:led', 'part:D1', 'part:R1', 'sheet:power', 'part:J1']);
  expect(parts.querySelector('[data-board-row="part:R1"] [aria-expanded]')).toBeNull();
  fireEvent.click(within(parts).getByRole('button', { name: 'Collapse led' }));
  // Nothing picked: no detail under the lists.
  const detail = () => panel(pane).querySelector<HTMLElement>('[data-flat-panel-detail]');
  const detailRows = () => [...detail()!.querySelectorAll('[data-board-detail-row]')].map(row => [row.textContent, row.getAttribute('aria-pressed')]);
  expect(detail()).toBeNull();

  // A block's name opens and shuts it, as a folder's, and selects nothing; its row menu selects every part
  // in it, one chip for the block, leaving the view where it is, and frames them.
  const fitted = { ...frames.at(-1)! };
  const blockMenu = async () => {
    fireEvent.contextMenu(parts.querySelector('[data-board-row="sheet:led"]')!);
    return screen.findByRole('menu');
  };
  let menu = await blockMenu();
  expect(within(menu).getAllByRole('menuitem').map(item => item.textContent)).toEqual(['Select all 2 parts', 'Zoom to led']);
  fireEvent.click(within(menu).getByRole('menuitem', { name: 'Select all 2 parts' }));
  expect(selected(controller)).toEqual(['#D1', '#R1']);
  await waitFor(() => expect([...box(pane)!.querySelectorAll('[data-quick-edit-ref] button[aria-label]')].map(b => b.getAttribute('aria-label'))
    .filter(label => !label!.startsWith('Remove'))).toEqual(['led · 2 parts']));
  expect(parts.querySelector('[data-board-row="sheet:led"]')!.className).toContain('bg-accent');
  expect(frames.at(-1)).toEqual(fitted);
  menu = await blockMenu();
  fireEvent.click(within(menu).getByRole('menuitem', { name: 'Zoom to led' }));
  await waitFor(() => expect(frames.at(-1)!.scale).toBeGreaterThan(fitted.scale));

  // A part selects as a click on the board does; under the lists, what is selected: its name, its ID and
  // facts (a chip card's: the same component), then its pads, each its number and net.
  fireEvent.click(within(parts).getByRole('button', { name: 'Select J1' }));
  expect(selected(controller)).toEqual(['#J1']);
  expect(detail()!.querySelector('[data-board-detail-head]')!.textContent).toBe('J1');
  const facts = () => [...detail()!.querySelectorAll('[data-flat-panel-facts] [data-info-row]')].map(row => row.textContent);
  expect(facts().slice(0, 3)).toEqual(['IDJ1', 'ValueConn_01x02', 'FootprintPinHeader_1x02_P2.54mm_Vertical']);
  expect(detailRows()).toEqual([['1VBUS', 'false'], ['2GND', 'false']]);
  // Titled with whose pads they are, at a height of its own, its top edge the grip that sizes it.
  expect(detail()!.querySelector('[data-flat-panel-detail-title]')!.textContent).toBe('Pads of J12 pads');
  expect(within(detail()!).getByRole('separator', { name: 'Resize details' }).getAttribute('aria-orientation')).toBe('horizontal');
  // A net, from the Nets: its pads, each its part and number; one pressed is selected, lit, and the net's detail stays.
  fireEvent.click(within(panel(pane)).getByRole('tab', { name: 'Nets' }));
  fireEvent.click(within(nets).getByRole('button', { name: 'Select LED' }));
  expect(selected(controller)).toEqual(['#net:LED']);
  expect(detailRows()).toEqual([['D1.2', 'false'], ['R1.2', 'false']]);
  const framedNet = { ...frames.at(-1)! };
  fireEvent.click(detail()!.querySelector('[data-board-detail-row="netpad:R1.2"]')!);
  expect(selected(controller)).toEqual(['#R1.2']);
  // A pad: what it is, in words, and what it is connected to, the pads on its net, itself lit.
  expect([detail()!.querySelector('[data-board-detail-head]')!.textContent, detail()!.querySelector('[data-flat-panel-selected-what]')!.textContent,
    detail()!.querySelector('[data-flat-panel-detail-title]')!.textContent]).toEqual(['R1.2', expect.stringContaining('Pad of R1'), 'Connected to LED2 pads']);
  expect(detailRows()).toEqual([['D1.2', 'false'], ['R1.2', 'true']]);
  // A detail row's double-click frames its pad.
  fireEvent.doubleClick(detail()!.querySelector('[data-board-detail-row="netpad:R1.2"]')!);
  await waitFor(() => expect(frames.at(-1)).not.toEqual(framedNet));

  // The panel's search reads the parts with their pads and the nets: a pasted pad reference finds the pad,
  // and its press shows what it is connected to, the pad lit there.
  fireEvent.change(searchBox(pane), { target: { value: '#J1.2' } });
  await waitFor(() => expect(parts.querySelector('[data-search-row="pad:J1.2"]')).not.toBeNull());
  expect(within(panel(pane)).queryByRole('tablist')).toBeNull();
  fireEvent.click(within(parts.querySelector<HTMLElement>('[data-search-row="pad:J1.2"]')!).getByRole('button'));
  expect(selected(controller)).toEqual(['#J1.2']);
  expect(detail()!.querySelector('[data-flat-panel-detail-title]')!.textContent).toMatch(/^Connected to GND/);
  expect(detailRows().find(([label]) => label!.startsWith('J1.2'))?.[1]).toBe('true');
  // A net by its name, in the Nets' hits, no Layers (none matches).
  fireEvent.change(searchBox(pane), { target: { value: 'VBUS' } });
  await waitFor(() => expect(nets.querySelector('[data-search-row="net:VBUS"]')).not.toBeNull());
  expect(tabBody(pane, 'layers').querySelector('[data-flat-panel-hit]')).toBeNull();
  fireEvent.click(within(nets.querySelector<HTMLElement>('[data-search-row="net:VBUS"]')!).getByRole('button', { name: 'Select VBUS' }));
  expect(selected(controller)).toEqual(['#net:VBUS']);
  // A search that names a layer finds it in the Layers too; Escape in the box clears it, and the tabs come back.
  fireEvent.change(searchBox(pane), { target: { value: 'B.Cu' } });
  await waitFor(() => expect([...tabBody(pane, 'layers').querySelectorAll('[data-flat-panel-hit] [data-layer-row]')].map(row => row.getAttribute('data-layer-row'))).toEqual(['B.Cu']));
  fireEvent.keyDown(searchBox(pane), { key: 'Escape' });
  expect(searchBox(pane).value).toBe('');
  expect(within(panel(pane)).getByRole('tablist')).toBeTruthy();
  fireEvent.click(within(panel(pane)).getByRole('tab', { name: 'Parts' }));
  fireEvent.click(within(parts).getByRole('button', { name: 'Isolate J1' }));
  expect(within(parts).getByRole('button', { name: 'Exit isolate J1' }).getAttribute('aria-pressed')).toBe('true');
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.isolated?.value).toEqual({ selectors: ['#J1'] }));
  // A pad picked on the board opens its part's block and brings the part's row into view, and shows what it is connected to.
  await act(async () => { await controller.clearSelection(); });
  const scrolled: string[] = [];
  const { scrollIntoView } = Element.prototype;
  Element.prototype.scrollIntoView = function (this: Element) { scrolled.push(this.getAttribute('data-virtual-row') || ''); };
  const page = { x: 0, y: 0, left: 0, top: 0, right: 1200, bottom: 700, width: 1200, height: 700, toJSON: noop };
  vi.mocked(HTMLElement.prototype.getBoundingClientRect).mockImplementation(function (this: HTMLElement) {
    return (this.getAttribute('data-virtual-row') === 'part:R1' ? { ...page, top: 900, bottom: 924, height: 24 } : page) as DOMRect;
  });
  try {
    tap(pane, [35.825, 15]);
    expect(selected(controller)).toEqual(['#R1.2']);
    await waitFor(() => expect(parts.querySelector('[data-board-row="sheet:led"] [aria-expanded]')!.getAttribute('aria-expanded')).toBe('true'));
    await waitFor(() => expect(scrolled).toEqual(['part:R1']));
    // The part's row holds the pad picked without being it: tinted, not lit.
    const row = parts.querySelector<HTMLElement>('[data-board-row="part:R1"]')!;
    expect([row.hasAttribute('data-holds-selection'), within(row).getByRole('button', { name: 'Select R1' }).getAttribute('aria-pressed')]).toEqual([true, 'false']);
    expect(detailRows()).toEqual([['D1.2', 'false'], ['R1.2', 'true']]);
  } finally { Element.prototype.scrollIntoView = scrollIntoView; }
  dispose();
});

it('a pick on the board brings its row into view in the list on screen, one block following it; a list not on screen waits until it is', async () => {
  // Two blocks of two parts: led (D1, R1) and power (J1, and an R2 of no pads), both shut as the tab opens.
  const board = JSON.parse(JSON.stringify(BOARD));
  board.board.parts.push({ ...board.board.parts.find((part: any) => part.ref === 'R1'), ref: 'R2', at: [36, 5], outline: [[35, 4.5], [37, 4.5], [37, 5.5], [35, 5.5]] });
  const sheets: Record<string, string> = { J1: 'power', R2: 'power', R1: 'led', D1: 'led' };
  for (const part of board.board.parts) part.sheet = sheets[part.ref];
  readPlot = () => json(board);
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  const controller = await controllerOf(view);
  const parts = await waitFor(() => { const found = tabBody(pane, 'parts'); expect(found).not.toBeNull(); return found!; });
  const rows = () => [...parts.querySelectorAll('[data-board-row]')].map(row => row.getAttribute('data-board-row'));
  // Every row out of view, so each reveal scrolls.
  const scrolled: string[] = [];
  Element.prototype.scrollIntoView = function (this: Element) { scrolled.push(this.getAttribute('data-virtual-row') || ''); };
  const page = { x: 0, y: 0, left: 0, top: 0, right: 1200, bottom: 700, width: 1200, height: 700, toJSON: noop };
  vi.mocked(HTMLElement.prototype.getBoundingClientRect).mockImplementation(function (this: HTMLElement) {
    return (this.hasAttribute('data-virtual-row') ? { ...page, top: 900, bottom: 924, height: 24 } : page) as DOMRect;
  });
  expect(rows()).toEqual(['sheet:led', 'sheet:power']);
  // The person opens power. A pad of R1 opens led, the reveal's, and brings R1 into view.
  fireEvent.click(within(parts).getByRole('button', { name: 'Expand power' }));
  tap(pane, [35.825, 15]);
  await waitFor(() => expect(rows()).toEqual(['sheet:led', 'part:D1', 'part:R1', 'sheet:power', 'part:J1', 'part:R2']));
  await waitFor(() => expect(scrolled).toEqual(['part:R1']));
  // A pad of J1, in the block the person opened: led shuts again, power stays open.
  tap(pane, [5, 17.54]);
  await waitFor(() => expect(rows()).toEqual(['sheet:led', 'sheet:power', 'part:J1', 'part:R2']));
  await waitFor(() => expect(scrolled).toEqual(['part:R1', 'part:J1']));
  // D1's pad opens led again; nothing picked then shuts it, the block only the pick opened, and leaves
  // power, the one the person opened, open.
  tap(pane, [20, 23.175]);
  await waitFor(() => expect(rows()).toEqual(['sheet:led', 'part:D1', 'part:R1', 'sheet:power', 'part:J1', 'part:R2']));
  await waitFor(() => expect(scrolled.at(-1)).toBe('part:D1'));
  tap(pane, [36, 26]);
  expect(selected(controller)).toEqual([]);
  await waitFor(() => expect(rows()).toEqual(['sheet:led', 'sheet:power', 'part:J1', 'part:R2']));
  tap(pane, [20, 23.175]);
  await waitFor(() => expect(rows()).toEqual(['sheet:led', 'part:D1', 'part:R1', 'sheet:power', 'part:J1', 'part:R2']));
  await waitFor(() => expect(scrolled).toEqual(['part:R1', 'part:J1', 'part:D1', 'part:D1']));
  // A press in the list keeps what the reveal opened and scrolls nothing.
  fireEvent.click(within(parts).getByRole('button', { name: 'Select R2' }));
  expect(selected(controller)).toEqual(['#R2']);
  expect(rows()).toEqual(['sheet:led', 'part:D1', 'part:R1', 'sheet:power', 'part:J1', 'part:R2']);
  expect(scrolled).toEqual(['part:R1', 'part:J1', 'part:D1', 'part:D1']);
  // Shut by the person, led is theirs: a pick in power leaves it shut, and one in led opens it again.
  fireEvent.click(within(parts).getByRole('button', { name: 'Collapse led' }));
  tap(pane, [5, 17.54]);
  await waitFor(() => expect(scrolled.at(-1)).toBe('part:J1'));
  expect(rows()).toEqual(['sheet:led', 'sheet:power', 'part:J1', 'part:R2']);
  tap(pane, [35.825, 15]);
  await waitFor(() => expect(rows()).toEqual(['sheet:led', 'part:D1', 'part:R1', 'sheet:power', 'part:J1', 'part:R2']));
  await waitFor(() => expect(scrolled.at(-1)).toBe('part:R1'));
  // The Nets, not shown, have moved for none of it. A track picked: the Parts move nothing, and the Nets
  // wait, then, shown, bring its net into view.
  tap(pane, [30, 15]);
  expect(selected(controller)).toEqual(['#track:7a1c0000-0000-4000-8000-000000000001']);
  expect(rows()).toEqual(['sheet:led', 'part:D1', 'part:R1', 'sheet:power', 'part:J1', 'part:R2']);
  expect(scrolled.filter(id => id.startsWith('net:'))).toEqual([]);
  showTab(pane, 'Nets');
  await waitFor(() => expect(scrolled.at(-1)).toBe('net:VBUS'));
  // A via, while they are shown: its net. With the panel hidden, D1's pad waits for it to be shown.
  tap(pane, [18, 27]);
  await waitFor(() => expect(scrolled.at(-1)).toBe('net:GND'));
  fireEvent.click(within(panel(pane)).getByRole('button', { name: 'Hide panel' }));
  tap(pane, [20, 23.175]);
  expect(selected(controller)).toEqual(['#D1.2']);
  expect(scrolled.at(-1)).toBe('net:GND');
  fireEvent.click(within(pane.querySelector<HTMLElement>('[data-flat-panel-pill]')!).getByRole('button', { name: 'Show panel' }));
  await waitFor(() => expect(scrolled.at(-1)).toBe('net:LED'));
  dispose();
});

it("the Layers tab holds KiCad's layer display options — the others, the pours, the zones' and tracks' opacity — and a Layers row's press makes it the active layer", async () => {
  const user = userEvent.setup({ skipHover: true, pointerEventsCheck: 0 });
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  const menu = await displayMenu(user, pane);
  // The preset is the corner's Display, not the tab's: the tab has the layers and their display.
  expect([...menu.querySelectorAll('[data-settings-section]')].map(section => section.getAttribute('data-settings-section'))).toEqual(['board-layer-display']);
  expect(within(menu).getAllByRole('combobox').map(select => [select.getAttribute('aria-label'), select.textContent]))
    .toEqual([['Other layers', 'Shown']]);
  expect(within(menu).getByRole('slider', { name: 'Zone opacity' }).getAttribute('aria-valuenow')).toBe('0.6');
  expect((within(menu).getByRole('textbox', { name: 'Track opacity value' }) as HTMLInputElement).value).toBe('100%');
  // KiCad's own as a board opens: nothing dimmed, the zones at 60%, the tracks at 100%.
  expect(drawn.at(-1)).toMatchObject({ active: null, focus: null, zones: 0.6, tracks: 1 });
  await choose(user, pane, 'Other layers', 'Dimmed');
  await waitFor(() => expect(drawn.at(-1)).toMatchObject({ focus: { layer: 'F.Cu', others: 'dimmed' } }));
  // The zones' opacity, typed into its value; Escape in a value puts its draft back.
  const zones = within(await displayMenu(user, pane)).getByRole('textbox', { name: 'Zone opacity value' });
  await user.clear(zones);
  await user.type(zones, '25{Enter}');
  await waitFor(() => expect(drawn.at(-1)).toMatchObject({ zones: 0.25 }));
  await user.type(zones, '9');
  await user.keyboard('{Escape}');
  expect((zones as HTMLInputElement).value).toBe('25%');
  showTab(pane, 'Layers');
  const layers = await waitFor(() => { const found = pane.querySelector<HTMLElement>('[data-board-layers]'); expect(found).not.toBeNull(); return found!; });
  // F.Cu active as a board opens (its dot).
  expect(layers.querySelector('[data-layer-row="F.Cu"] [data-layer-active]')).not.toBeNull();
  // A row's press: B.Cu active, drawn on top, the rest dimmed round it.
  await user.click(within(layers).getByRole('button', { name: 'Make B.Cu the active layer' }));
  await waitFor(() => expect(drawn.at(-1)).toMatchObject({ active: 'B.Cu', focus: { layer: 'B.Cu', others: 'dimmed' } }));
  expect(layers.querySelector('[data-layer-row="B.Cu"] [data-layer-active]')).not.toBeNull();
  expect(layers.querySelector('[data-layer-row="F.Cu"] [data-layer-active]')).toBeNull();
  // The board's area and what goes through the board are no active layer.
  expect(within(layers.querySelector<HTMLElement>('[data-layer-row="vias"]')!).queryByRole('button', { name: /active layer/ })).toBeNull();
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board?.value)
    .toEqual({ mode: 'board', side: 'top', poured: true, layers: null, active: 'B.Cu', others: 'dimmed', zones: 0.25, tracks: 1 }));

  dispose();
});

it("a layer's eye hides it: the Display contract's layers, which reads as Custom and is kept with the file's view", async () => {
  const user = userEvent.setup({ skipHover: true, pointerEventsCheck: 0 });
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  showTab(pane, 'Layers');
  const layers = await waitFor(() => { const found = pane.querySelector<HTMLElement>('[data-board-layers]'); expect(found).not.toBeNull(); return found!; });
  expect([...layers.querySelectorAll('[data-layer-group]')].map(group => group.getAttribute('data-layer-group'))).toEqual(['front', 'back', 'other']);
  expect([...layers.querySelectorAll('[data-layer-row]:not([data-layer-row="models-3d"])')].map(row => row.getAttribute('data-layer-row')))
    .toEqual(['F.CrtYd', 'F.Fab', 'F.SilkS', 'F.Paste', 'F.Mask', 'F.Cu', 'B.Cu', 'B.Mask', 'Edge.Cuts', 'area', 'vias', 'drills', 'ratsnest', 'names']);
  // One glyph a row: a layer has nothing under it, so its glyph is its colour, and nothing stands before it.
  for (const row of layers.querySelectorAll('[data-layer-row]:not([data-layer-row="models-3d"])')) {
    expect([...row.querySelectorAll('[data-layer-glyph]')].map(glyph => glyph.getAttribute('data-layer-glyph'))).toEqual(['swatch']);
    expect(row.firstElementChild!.getAttribute('data-layer-glyph')).toBe('swatch');
  }
  fireEvent.click(layers.querySelector('[data-layer-visibility="F.Cu"]')!);
  await waitFor(() => expect(drawn.at(-1)!.layers).not.toContain('F.Cu'));
  expect(await presetChoice(user, pane)).toBe('Custom');
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board?.value?.layers).toEqual(
    ['area', 'B.Mask', 'B.Cu', 'Edge.Cuts', 'F.Fab', 'F.CrtYd', 'F.Paste', 'F.SilkS', 'F.Mask', 'drills', 'vias', 'ratsnest', 'names']));
  // Shown again, the set is the mode's own: stored as the mode's, so a rebuild's new layer follows it.
  fireEvent.click(layers.querySelector('[data-layer-visibility="F.Cu"]')!);
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board?.value).toEqual({ mode: 'board', side: 'top', poured: true, layers: null, active: null, others: 'shown', zones: 0.6, tracks: 1 }));
  dispose();
});

it("a switch of theme draws the board again in that theme's canvas and palette, from the payload it holds", async () => {
  let reads = 0;
  readPlot = () => { reads += 1; return json(BOARD); };
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  const plots = reads;
  const swatch = (id: string) => pane.querySelector<HTMLElement>(`[data-layer-row="${id}"] [data-layer-glyph] span`)!.style.backgroundColor;
  showTab(pane, 'Layers');
  await waitFor(() => expect(pane.querySelector('[data-layer-row="F.SilkS"]')).not.toBeNull());
  // Light: the app's light canvas, KiCad's silkscreen yellow darkened to read on it.
  expect(themes.at(-1)).toBe('light');
  expect(canvases.at(-1)).toBe(APP_THEME_COLORS.light.canvas);
  expect(swatch('F.SilkS')).toBe('rgb(156, 150, 77)');
  themes.length = 0;
  await view.scheme('dark');
  // Dark: drawn again here, KiCad's own colours on the neutral dark canvas, nothing asked of the server.
  await waitFor(() => expect(themes).toContain('dark'));
  await waitFor(() => expect(canvases.at(-1)).toBe(APP_THEME_COLORS.dark.canvas));
  expect(swatch('F.SilkS')).toBe('rgb(242, 237, 161)');
  expect(reads).toBe(plots);
  await view.scheme('light');
  await waitFor(() => expect(canvases.at(-1)).toBe(APP_THEME_COLORS.light.canvas));
  dispose();
});

it("a board's card picture is drawn in both themes, on nothing but the board, the dark one carried beside the light", async () => {
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  const controller = await controllerOf(view);
  themes.length = 0;
  const picture = await controller.thumbnail({ width: 480, height: 360 });
  expect(picture).toBeInstanceOf(Blob);
  expect(picture.dark).toBeInstanceOf(Blob);
  expect([...themes].sort()).toEqual(['dark', 'light']);
  dispose();
});

it('a preset chooses the layers; the side (Flip) and the pours are kept through a change of preset', async () => {
  const user = userEvent.setup({ skipHover: true, pointerEventsCheck: 0 });
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  // The side, Flip in the corner over the pill: the top shown, and a press turns the board over.
  expect(flipButton(pane).getAttribute('aria-label')).toBe('Side: Top');
  await user.click(flipButton(pane));
  expect(flipButton(pane).getAttribute('aria-label')).toBe('Side: Bottom');
  await user.click(within(await displayMenu(user, pane)).getByRole('checkbox', { name: 'Copper pours' }));
  // A switch is not a layer set: the preset is still the one on screen, the corner's Display ticks it.
  expect(await presetChoice(user, pane)).toBe('Board');
  const presets = await presetMenu(user, pane);
  expect(within(presets).getAllByRole('menuitemradio').map(option => option.textContent)).toEqual(['Board', 'Copper', 'Assembly', 'Placement']);
  await user.click(within(presets).getByRole('menuitemradio', { name: 'Copper' }));
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board?.value).toEqual({ mode: 'copper', side: 'bottom', poured: false, layers: null, active: null, others: 'shown', zones: 0.6, tracks: 1 }));
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
  expect(request.views).toEqual([expect.objectContaining({ label: 'current view', display: { mode: 'board', side: 'top', poured: true, others: 'shown', zones: 0.6, tracks: 1, appearance: 'light' } })]);
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
it("Other layers: Hidden from the Layers tab; Ctrl+H cycles the three while the board has the keyboard, and nowhere else", async () => {
  const user = userEvent.setup();
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  await choose(user, pane, 'Other layers', 'Hidden');
  await waitFor(() => expect(drawn.at(-1)).toMatchObject({ focus: { layer: 'F.Cu', others: 'hidden' } }));
  // The board's own key, KiCad's: hidden, shown, dimmed, and round.
  const canvas = pane.querySelector<HTMLCanvasElement>('canvas[data-board-tool]')!;
  canvas.focus();
  fireEvent.keyDown(canvas, { key: 'h', ctrlKey: true });
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board?.value?.others).toBe('shown'));
  expect(drawn.at(-1)).toMatchObject({ focus: null });
  expect(await choice(user, pane, 'Other layers')).toBe('Shown');
  fireEvent.keyDown(canvas, { key: 'h', metaKey: true });
  await waitFor(() => expect(drawn.at(-1)).toMatchObject({ focus: { layer: 'F.Cu', others: 'dimmed' } }));
  // Off the board (a text field outside it), the key is not the board's.
  const outside = document.createElement('input');
  document.body.append(outside);
  outside.focus();
  fireEvent.keyDown(outside, { key: 'h', ctrlKey: true });
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board?.value?.others).toBe('dimmed'));
  outside.remove();

  dispose();
});

it("a view saved with the earlier Dim switch opens Dimmed", async () => {
  const user = userEvent.setup({ skipHover: true, pointerEventsCheck: 0 });
  const saved = { version: 2, camera: null, display: null, preview: null, playback: null,
    renderer: { board: { signature: '1', value: { mode: 'board', side: 'top', poured: true, layers: null, active: null, dim: true, zones: 0.6, tracks: 1 } } } };
  const { pane, dispose } = await open('blinky.kicad_pcb', { state: { renderers: { [KEY]: saved } } });
  await opened(pane);
  expect(drawn.at(-1)).toMatchObject({ focus: { layer: 'F.Cu', others: 'dimmed' } });
  expect(await choice(user, pane, 'Other layers')).toBe('Dimmed');

  dispose();
});

it("the panel collapses whole to a pill at the canvas's top-left; ⌘\\ shows and hides it, / opens it on its search, and the tab is kept", async () => {
  const { pane, dispose } = await open();
  await opened(pane);
  showTab(pane, 'Layers');
  fireEvent.click(within(panel(pane)).getByRole('button', { name: 'Hide panel' }));
  expect(panel(pane).hidden).toBe(true);
  const pill = pane.querySelector<HTMLElement>('[data-flat-panel-pill]')!;
  expect(within(pill).getAllByRole('button').map(button => button.getAttribute('aria-label'))).toEqual(['Show panel']);
  expect([pill.style.top, pill.style.left]).toEqual(['8px', '8px']);
  fireEvent.click(within(pill).getByRole('button', { name: 'Show panel' }));
  expect(panel(pane).hidden).toBe(false);
  expect(pane.querySelector('[data-flat-panel-pill]')).toBeNull();
  expect(within(panel(pane)).getByRole('tab', { name: 'Layers' }).getAttribute('aria-selected')).toBe('true');
  // The keys, while the board has the keyboard.
  const canvas = pane.querySelector<HTMLCanvasElement>('canvas[data-board-tool]')!;
  fireEvent.keyDown(canvas, { key: '\\', metaKey: true });
  await waitFor(() => expect(panel(pane).hidden).toBe(true));
  fireEvent.keyDown(canvas, { key: '\\', ctrlKey: true });
  await waitFor(() => expect(panel(pane).hidden).toBe(false));
  fireEvent.click(within(panel(pane)).getByRole('button', { name: 'Hide panel' }));
  fireEvent.keyDown(canvas, { key: '/' });
  await waitFor(() => expect(document.activeElement).toBe(searchBox(pane)));
  expect(panel(pane).hidden).toBe(false);
  dispose();
});

it("under 1024px the panel starts collapsed and, opened, docks all the same; a phone has none", async () => {
  const sized = (width: number) => vi.mocked(HTMLElement.prototype.getBoundingClientRect).mockReturnValue(
    { x: 0, y: 0, left: 0, top: 0, right: width, bottom: 700, width, height: 700, toJSON: noop } as DOMRect);
  sized(900);
  const view = await open();
  await opened(view.pane);
  await waitFor(() => expect(panel(view.pane).hidden).toBe(true));
  expect(panel(view.pane).getAttribute('data-flat-panel')).toBe('docked');
  fireEvent.click(within(view.pane.querySelector<HTMLElement>('[data-flat-panel-pill]')!).getByRole('button', { name: 'Show panel' }));
  expect([panel(view.pane).getAttribute('data-flat-panel'), panel(view.pane).hidden]).toEqual(['docked', false]);
  expect(view.pane.querySelector('[data-flat-panel-scrim]')).toBeNull();
  view.dispose();
  cleanup();
  // A phone: no panel and no pill; the board, its strip and its corner's controls in More.
  sized(400);
  const phone = await open();
  await opened(phone.pane);
  expect([phone.pane.querySelector('[data-flat-panel]'), phone.pane.querySelector('[data-flat-panel-pill]')]).toEqual([null, null]);
  expect(phone.pane.querySelector('[data-view-pill-column]')).toBeNull();
  // More's rows: Display's and the zoom's submenus, and 3D view and View from bottom, ticked while they are,
  // each with the icon the corner shows for that state; a press on View from bottom turns the board over.
  const user = userEvent.setup({ skipHover: true, pointerEventsCheck: 0 });
  const more = async () => { await user.click(within(phone.pane).getByRole('button', { name: 'More tools' })); return openMenu('More tools'); };
  // A row's own icon: its Lucide glyph, not the menu's tick or submenu chevron.
  const glyph = (row: HTMLElement) => [...row.querySelectorAll('svg')].flatMap(svg => [...svg.classList])
    .find(name => name.startsWith('lucide-') && !['lucide-check', 'lucide-chevron-right'].includes(name)) ?? null;
  const rows = (menu: HTMLElement) => [...menu.querySelectorAll<HTMLElement>('[role^=menuitem]')]
    .map(row => [row.textContent, row.getAttribute('aria-checked'), glyph(row)]);
  expect(rows(await more())).toEqual([['Display', null, null], ['3D view', 'false', 'lucide-box'], ['View from bottom', 'false', 'lucide-arrow-up-to-line'],
    ['Zoom', null, 'lucide-scan-search']]);
  await user.click(within(await openMenu('More tools')).getByRole('menuitemcheckbox', { name: 'View from bottom' }));
  await waitFor(() => expect(drawn.at(-1)).toMatchObject({ side: 'bottom' }));
  expect(rows(await more())[2]).toEqual(['View from bottom', 'true', 'lucide-arrow-up-to-line']);
  phone.dispose();
});

it("a panel docking beside a board is a resize of its pane: a board still at its fit refits to the room left, one the person has moved keeps its zoom and the point at its centre", async () => {
  // The pane's observers, run by hand: the pane's box is what the test says it is.
  const observers: Array<() => void> = [];
  vi.stubGlobal('ResizeObserver', class { constructor(callback: () => void) { observers.push(callback); } observe() {} unobserve() {} disconnect() {} });
  const box = (left: number, width: number) => vi.mocked(HTMLElement.prototype.getBoundingClientRect).mockReturnValue(
    { x: left, y: 0, left, top: 0, right: left + width, bottom: 700, width, height: 700, toJSON: noop } as DOMRect);
  const { pane, dispose } = await open();
  await opened(pane);
  const resize = async (left: number, width: number) => { box(left, width); await act(async () => { for (const run of observers) run(); }); };
  // Still the fit: a panel 200px wide docks, and the board refits to the 400px left beside it.
  const fitted = { ...frames.at(-1)! };
  await resize(200, 400);
  await waitFor(() => expect(frames.at(-1)!.scale).toBeLessThan(fitted.scale));
  const narrow = { ...frames.at(-1)! };
  await resize(0, 1200);
  await waitFor(() => expect(frames.at(-1)!.scale).toBe(fitted.scale));
  // Moved (a middle-button pan): the panel docks, and the board keeps its zoom against the fit, and
  // what was at the pane's centre is at the centre of the room left; nothing is left under the panel.
  const canvas = pane.querySelector<HTMLCanvasElement>('[data-board-surface] canvas')!;
  const at = ([x, y]: [number, number]) => { const [clientX, clientY] = pageToScreen(frames.at(-1)!, x, y); return { clientX, clientY }; };
  const middle = { pointerId: 2, pointerType: 'mouse', button: 1 };
  fireEvent.pointerDown(canvas, { ...middle, ...at([20, 15]) });
  fireEvent.pointerMove(canvas, { ...middle, ...at([25, 15]) });
  fireEvent.pointerUp(canvas, { ...middle, ...at([25, 15]) });
  await waitFor(() => expect(frames.at(-1)!.offsetX).not.toBe(fitted.offsetX));
  const moved = { ...frames.at(-1)! };
  const held = screenToPage(moved, 600, 350);
  const centred = (x: number) => {
    const [cx, cy] = pageToScreen(frames.at(-1)!, held[0], held[1]);
    expect([cx, cy].map(value => Math.round(value * 1000) / 1000)).toEqual([x, 350]);
  };
  await resize(200, 400);
  await waitFor(() => expect(frames.at(-1)!.scale).toBeCloseTo(moved.scale / fitted.scale * narrow.scale, 9));
  centred(200);
  await resize(0, 1200);
  await waitFor(() => expect(frames.at(-1)!.scale).toBeCloseTo(moved.scale, 9));
  centred(600);
  dispose();
});

it("2D/3D is one view: the strip, the panel and the corner stay the same mounted controls, Projection is Display's in 3D, and what is picked and measured stays; 3 switches; the file keeps it", async () => {
  const user = userEvent.setup({ skipHover: true, pointerEventsCheck: 0 });
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  // A pick and a measurement in 2D.
  tap(pane, [35.825, 15]);
  fireEvent.click(within(strip(pane)).getByRole('button', { name: 'Measure' }));
  tap(pane, [34.2, 15.1]);
  tap(pane, [35.8, 14.9]);
  await within(pane).findByRole('button', { name: 'Measurement 1: 1.65 mm' });
  fireEvent.click(within(strip(pane)).getByRole('button', { name: 'Select' }));
  const controller = await controllerOf(view);
  expect(selected(controller)).toEqual(['#R1.2']);
  // What the strip, the panel and the corner (its column and its pill) are, by their names and by the elements themselves.
  const controls = () => ({
    strip: strip(pane), panel: panel(pane), column: corner(pane), pill: pane.querySelector<HTMLElement>('[data-zoom-pill]'),
    names: [...pane.querySelectorAll<HTMLElement>('[data-cad-tool-groups] button, [data-flat-panel] [role=tab], [data-view-pill-column] button, [data-zoom-pill] button')]
      .map(button => button.getAttribute('aria-label') || button.textContent)
  });
  const flat = controls();
  expect(flat.pill).not.toBeNull();
  // In 2D Display's menu is the presets alone: a flat board has no projection.
  expect((await presetMenu(user, pane)).querySelector('[data-display-projection]')).toBeNull();
  await user.keyboard('{Escape}');
  await waitFor(() => expect(menuShown('Display')).toBeNull());

  const dimension = dimensionButton(pane);
  expect(shown(dimension)).toEqual(['View: 2D', 'lucide-square', 'ghost']);
  await user.click(dimension);
  await waitFor(() => expect(pane.querySelector('[data-board-3d]')).not.toBeNull());
  // Its first frame up, the flat canvas is put away (and lets its rasters go); the camera eases to Home.
  await waitFor(() => expect(pane.querySelector('[data-board-surface] canvas[role=img]')!.classList.contains('invisible')).toBe(true));
  await waitFor(() => expect(viewport3d.calls).toContain('goHome'));
  // The same controls, by name but for the one that says the view is in 3D now: the same button, a box.
  const solid = controls();
  expect(solid.names).toEqual(flat.names.map(name => (name === 'View: 2D' ? 'View: 3D' : name)));
  for (const key of ['strip', 'panel', 'column', 'pill'] as const) expect(solid[key], key).toBe(flat[key]);
  expect(dimensionButton(pane)).toBe(dimension);
  expect(shown(dimension)).toEqual(['View: 3D', 'lucide-box', 'ghost']);
  // The corner is the one it was: the pill (the 3D camera's zoom now), and no cube, Projection or Home of a 3D view's.
  expect(viewport3d.props.viewCube).toBe(false);
  expect(within(pane).queryByRole('button', { name: /^Projection/ })).toBeNull();
  expect(pane.querySelector('[data-view-home]')).toBeNull();
  // The pick and the measurement are where they were; a camera is the 3D view's to pose.
  expect(selected(controller)).toEqual(['#R1.2']);
  fireEvent.click(within(strip(pane)).getByRole('button', { name: 'Measure' }));
  expect(within(pane).getByRole('button', { name: 'Measurement 1: 1.65 mm' })).toBeTruthy();
  await controller.setCamera({ position: [0, 0, 100], target: [0, 0, 0], up: [0, 1, 0] });
  expect(viewport3d.calls.at(-1)).toBe('setPerspective [0,0,100]');
  // Display's presets, in 3D as in 2D, and under them the camera's projection, the one on screen ticked.
  const menu = await presetMenu(user, pane);
  expect([...menu.querySelectorAll('[data-display-projection]')].map(item => [item.textContent, item.getAttribute('aria-checked')]))
    .toEqual([['Orthographic', 'true'], ['Perspective', 'false']]);
  await user.click(within(menu).getByRole('menuitemradio', { name: 'Perspective' }));
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board3d?.value?.projection).toBe('perspective'));
  await user.click(within(await presetMenu(user, pane)).getByRole('menuitemradio', { name: 'Copper' }));
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board?.value?.mode).toBe('copper'));
  // The file keeps it: 3D, opened again in 3D.
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board3d?.value).toMatchObject({ mode: '3d', projection: 'perspective' }));
  // 3, as KiCad's Alt+3: back to 2D, the same pill, the flat canvas shown.
  fireEvent.keyDown(pane.querySelector('[data-board-3d] canvas')!, { key: '3' });
  await waitFor(() => expect(pane.querySelector('[data-board-3d]')).toBeNull());
  expect(pane.querySelector('[data-zoom-pill]')).toBe(flat.pill);
  expect(pane.querySelector('[data-board-surface] canvas[role=img]')!.classList.contains('invisible')).toBe(false);
  expect(selected(controller)).toEqual(['#R1.2']);
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board3d?.value?.mode).toBe('2d'));
  fireEvent.keyDown(pane.querySelector('[data-board-surface] canvas')!, { key: '3' });
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board3d?.value?.mode).toBe('3d'));
  const stored = view.state;
  dispose();
  cleanup();
  const again = await open('blinky.kicad_pcb', { state: stored });
  await waitFor(() => expect(again.pane.querySelector('[data-board-3d]')).not.toBeNull());
  expect(shown(dimensionButton(again.pane))).toEqual(['View: 3D', 'lucide-box', 'ghost']);
  again.dispose();
});

it("2D/3D and Flip each show the state on screen, name it and say what a press does, with its key; Flip is lit from the bottom; ⇧F flips as F still fits", async () => {
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  // A deliberate hover: the hint, and the pointer gone again.
  const hint = async (button: HTMLElement) => {
    fireEvent.pointerMove(button, { pointerType: 'mouse' });
    const text = (await screen.findByRole('tooltip')).textContent;
    fireEvent.pointerLeave(button, { pointerType: 'mouse' });
    await waitFor(() => expect(screen.queryByRole('tooltip')).toBeNull());
    return text;
  };
  // Plain buttons, their names the state: no aria-pressed (the APG button pattern), each its key.
  for (const button of [dimensionButton(pane), flipButton(pane)]) expect(button.hasAttribute('aria-pressed')).toBe(false);
  expect([dimensionButton(pane).getAttribute('aria-keyshortcuts'), flipButton(pane).getAttribute('aria-keyshortcuts')]).toEqual(['3', 'Shift+F']);
  expect([shown(dimensionButton(pane)), await hint(dimensionButton(pane))]).toEqual([['View: 2D', 'lucide-square', 'ghost'], 'Switch to 3D3']);
  expect([shown(flipButton(pane)), await hint(flipButton(pane))]).toEqual([['Side: Top', 'lucide-arrow-down-to-line', 'ghost'], 'View from bottom⇧F']);
  // Moved off the fit (a middle-button pan), so F's fit would show.
  const canvas = pane.querySelector<HTMLCanvasElement>('[data-board-surface] canvas')!;
  const fitted = { ...frames.at(-1)! };
  const at = ([x, y]: [number, number]) => { const [clientX, clientY] = pageToScreen(frames.at(-1)!, x, y); return { clientX, clientY }; };
  const middle = { pointerId: 2, pointerType: 'mouse', button: 1 };
  fireEvent.pointerDown(canvas, { ...middle, ...at([20, 15]) });
  fireEvent.pointerMove(canvas, { ...middle, ...at([25, 15]) });
  fireEvent.pointerUp(canvas, { ...middle, ...at([25, 15]) });
  await waitFor(() => expect(frames.at(-1)!.offsetX).not.toBe(fitted.offsetX));
  const moved = { ...frames.at(-1)! };
  // ⇧F turns the board over, the window kept: drawn from the bottom, and Flip shows it, lit, its hint the way back.
  fireEvent.keyDown(canvas, { key: 'F', code: 'KeyF', shiftKey: true });
  await waitFor(() => expect(drawn.at(-1)).toMatchObject({ side: 'bottom' }));
  expect(frames.at(-1)).toEqual(moved);
  expect([shown(flipButton(pane)), await hint(flipButton(pane))]).toEqual([['Side: Bottom', 'lucide-arrow-up-to-line', 'secondary'], 'View from top⇧F']);
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board?.value?.side).toBe('bottom'));
  // F is the fit, still, not a flip; ⇧F again, and the top is back, unlit.
  fireEvent.keyDown(canvas, { key: 'f', code: 'KeyF' });
  await waitFor(() => expect(frames.at(-1)).toEqual(fitted));
  expect(drawn.at(-1)).toMatchObject({ side: 'bottom' });
  fireEvent.keyDown(canvas, { key: 'F', code: 'KeyF', shiftKey: true });
  await waitFor(() => expect(drawn.at(-1)).toMatchObject({ side: 'top' }));
  expect(shown(flipButton(pane))).toEqual(['Side: Top', 'lucide-arrow-down-to-line', 'ghost']);
  dispose();
});

it("in 3D Flip turns the camera over, and its icon is the side the camera is on: turned by Flip, by ⇧F or by hand, and after a reload on a camera below the board", async () => {
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  fireEvent.click(dimensionButton(pane));
  await waitFor(() => expect(viewport3d.calls).toContain('goHome'));
  // The camera as the 3D view reports it: above the board, or turned over it, below.
  const camera = (below: boolean) => ({ position: [10, below ? 40 : -40, below ? -30 : 30], target: [10, 0, 0], up: [0, 0, 1] });
  const report = (below: boolean) => act(() => { viewport3d.props.onPerspectiveChange(camera(below)); });
  // From above (the stand-in's camera), Flip turns the camera over the board's left-to-right axis, eased; the
  // icon is the camera's side, so it stays the top until the camera passes the board's plane.
  viewport3d.calls.length = 0;
  fireEvent.click(flipButton(pane));
  expect(viewport3d.calls).toEqual(['setPerspective [10,40,-30]']);
  expect(shown(flipButton(pane))).toEqual(['Side: Top', 'lucide-arrow-down-to-line', 'ghost']);
  report(true);
  expect(shown(flipButton(pane))).toEqual(['Side: Bottom', 'lucide-arrow-up-to-line', 'secondary']);
  // Turned back over by hand (an orbit past the board's plane): the icon follows.
  report(false);
  expect(shown(flipButton(pane))).toEqual(['Side: Top', 'lucide-arrow-down-to-line', 'ghost']);
  // ⇧F is Flip's key in 3D too.
  viewport3d.calls.length = 0;
  fireEvent.keyDown(pane.querySelector('[data-board-3d] canvas')!, { key: 'F', code: 'KeyF', shiftKey: true });
  expect(viewport3d.calls).toEqual(['setPerspective [10,40,-30]']);
  report(true);
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board3d?.value?.camera?.position).toEqual([10, 40, -30]));
  // A reload opens on that camera, below the board: Flip says so from the first frame, whatever side the
  // file's Display was left at.
  const stored = structuredClone(view.state);
  stored.renderers[KEY].renderer.board.value.side = 'top';
  dispose();
  cleanup();
  const again = await open('blinky.kicad_pcb', { state: stored });
  await waitFor(() => expect(again.pane.querySelector('[data-board-3d]')).not.toBeNull());
  expect(shown(flipButton(again.pane))).toEqual(['Side: Bottom', 'lucide-arrow-up-to-line', 'secondary']);
  again.dispose();
});

it("a part's card says its 3D model, or why it has none, and the Parts end with the parts that have none; the Layers' 3D models eye is kept with the file", async () => {
  // The models table as the server answers it: R1's STEP found by its document id, D1's named and not found (J1 names none).
  const view = await open('blinky.kicad_pcb', { models: {
    '${KICAD9_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_0603_1608Metric.wrl': { file: 'R_0603_1608Metric.step', document: 'r0603', api: '/api/v1/documents/step/r0603', stamp: '1-2' },
    '${KIPRJMOD}/models/led.step': { file: 'led.step', missing: 'not-found' } } });
  const { pane, dispose } = view;
  await opened(pane);
  showTab(pane, 'Parts');
  const parts = await waitFor(() => { const found = tabBody(pane, 'parts').querySelector<HTMLElement>('[data-board-row="block:no-3d-model"]'); expect(found).not.toBeNull(); return tabBody(pane, 'parts'); });
  expect(parts.querySelector('[data-board-row="block:no-3d-model"]')!.textContent).toContain('No 3D model');
  const fact = async (ref: string) => {
    fireEvent.click(within(parts).getAllByRole('button', { name: `Select ${ref}` })[0]);
    return waitFor(() => {
      const rows = [...pane.querySelectorAll('[data-flat-panel-detail] [data-flat-panel-facts] [data-info-row]')].map(row => row.textContent);
      const found = rows.find(row => row!.startsWith('3D model'));
      expect(found).toBeTruthy();
      return found;
    });
  };
  expect(await fact('R1')).toBe('3D modelR_0603_1608Metric.step');
  expect(await fact('D1')).toBe('3D modelNot found · led.step');
  expect(await fact('J1')).toBe('3D modelNone named');
  // The block's rows are D1 and J1, each saying why, once the block is opened.
  fireEvent.click(within(parts).getByRole('button', { name: 'Expand No 3D model' }));
  await waitFor(() => expect([...parts.querySelectorAll('[data-board-row^="nomodel:"]')].map(row => row.textContent))
    .toEqual([expect.stringContaining('Not found'), expect.stringContaining('None named')]));
  // The Layers' 3D models row: how many parts stand on a model, and an eye, in 2D too; kept with the file's view.
  showTab(pane, 'Layers');
  const row = await waitFor(() => { const found = pane.querySelector<HTMLElement>('[data-layer-row="models-3d"]'); expect(found).not.toBeNull(); return found!; });
  expect(row.textContent).toBe('3D models1');
  fireEvent.click(within(row).getByRole('button', { name: 'Hide 3D models' }));
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board3d?.value?.models).toBe(false));
  dispose();
});

it("in 3D each part's model is opened once by its document id, and a revision of the board keeps it rather than asking again", async () => {
  const id = 'b4ac0e70-0000-4000-8000-000000000002';
  const view = await open('blinky.kicad_pcb', { models: {
    '${KICAD9_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_0603_1608Metric.wrl': { file: 'R_0603_1608Metric.step', document: id, api: `/api/v1/documents/step/${id}`, stamp: '1-2' } } });
  const { pane, dispose, fetch } = view;
  await opened(pane);
  fireEvent.click(dimensionButton(pane));
  const reads = (end: string) => fetch.mock.calls.filter(([input]) => new URL(String(input)).pathname.endsWith(end)).length;
  await waitFor(() => expect(reads(`/step/${id}/structure`)).toBe(1));
  const plots = reads('/kicad_pcb/board/plot');
  await view.saved();
  await waitFor(() => expect(reads('/kicad_pcb/board/plot')).toBeGreaterThan(plots));
  await waitFor(() => expect(reads('/kicad_pcb/board/models')).toBeGreaterThan(1));
  await waitFor(() => expect(pane.querySelector('[data-board-surface] [aria-busy="false"]')).not.toBeNull());
  // The revision's board in 3D holds the model, placed, and asked for nothing more.
  await waitFor(() => expect(pane.querySelector('[data-board-3d][data-board-models="1"][data-board-models-waiting="0"]')).not.toBeNull());
  expect(reads(`/step/${id}/structure`)).toBe(1);
  dispose();
});
