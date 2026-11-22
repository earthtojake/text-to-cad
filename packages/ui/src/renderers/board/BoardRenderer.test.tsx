import { StrictMode, useMemo, useState } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import { createCadClient } from '@cad/core/client';
import { APP_THEME_COLORS } from '@cad/core/lib/appTheme.js';
import { pageToScreen, screenToPage } from '@cad/core/lib/plot2d/plot.js';
import { FileViewer } from '../../../dist/file-viewer/index.js';
import { createBoardRenderer } from '../../../dist/renderers/board/index.js';
import { createCadPreferences } from '../../../dist/renderers/workspace/index.js';
import { FLOATING_CHROME_SURFACE_CLASS } from '../../../dist/lib/floatingSurface.js';
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
// `homes`: what each Home was asked to frame from (its direction and up). `camera`, `controls` and `hands`: a
// camera for the runtime to hold, its orbit's target and the hands on it (none unless a test sets them).
const viewport3d = vi.hoisted(() => ({ props: null as any, calls: [] as string[], homes: [] as any[], camera: null as any, controls: null as any, hands: 0 }));
vi.mock('../../../dist/renderers/kit/shell/ShellViewport.js', async () => {
  const React = await import('react');
  return {
    default: React.forwardRef(function StandInViewport(props: any, ref) {
      viewport3d.props = props;
      React.useImperativeHandle(ref, () => ({
        captureScreenshotBlob: async () => new Blob(['pixels'], { type: 'image/png' }),
        getPerspective: () => ({ position: [10, -40, 30], target: [10, 0, 0], up: [0, 0, 1] }),
        setPerspective: (camera: any) => { viewport3d.calls.push(`setPerspective ${JSON.stringify(camera.position)}`); return true; },
        goHome: (from?: any) => { viewport3d.calls.push('goHome'); viewport3d.homes.push(from ?? null); return true; },
        resetZoom: () => { viewport3d.calls.push('resetZoom'); return true; },
        zoomToBounds: () => true, zoomPercent: () => 100, subscribeCamera: () => () => {}, zoomBy: () => true, zoomTo100: () => true
      }));
      const hostRef = React.useRef<HTMLDivElement | null>(null);
      const runtimeRef = React.useRef<any>(null);
      React.useEffect(() => { props.onPresentationChange?.({ key: props.modelKey, preparing: false }); }, [props.modelKey]);
      const context = { hostRef, runtimeRef, mountRef: hostRef, viewerReadyTick: 1, commitScene: () => true };
      return <div ref={hostRef} data-stand-in-viewport="">
        <canvas ref={canvas => { runtimeRef.current = canvas ? { renderer: { domElement: canvas, capabilities: { maxTextureSize: 4096 }, initTexture() {} }, requestRender() {},
          get camera() { return viewport3d.camera; }, get controls() { return viewport3d.controls; }, get cameraHands() { return viewport3d.hands; } } : null; }} />
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
  Object.assign(viewport3d, { camera: null, controls: null, hands: 0 });
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
  // The tab's settings: the viewport's Background among them (Light unless a test picks).
  const preferences = createCadPreferences();
  const renderers = [createBoardRenderer({ client, live, preferences })];
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
    background: (next: 'light' | 'dark') => act(() => preferences.update({ viewportBackground: next })),
    dispose: () => client.dispose(), fetch,
    // The board saved again: a new revision, read as the catalog's next answer says.
    saved: async () => { revision = `${revision}+`; await act(() => client.refresh()); } };
}

const opened = async (pane: HTMLElement) => {
  await waitFor(() => expect(pane.querySelector('[data-board-surface] [aria-busy="false"]')).not.toBeNull());
  await waitFor(() => expect(frames.length).toBeGreaterThan(0));
};
const strip = (pane: HTMLElement) => within(pane).getByRole('group', { name: 'Interaction tools' });
// The board's view settings, the navbar's Display (`kit/shell/DisplaySettings.jsx`, `BoardDisplay.jsx`'s `boardViewGroups`):
// its card Side, Mode (2D/3D), in 3D Projection | Style (its presets), Background, and Reset.
const cornerStack = (pane: HTMLElement) => pane.querySelector<HTMLElement>('[data-navbar-view-controls]');
const viewButtons = (pane: HTMLElement) => [...(cornerStack(pane)?.querySelectorAll('button') ?? [])]
  .map(button => button.getAttribute('aria-label') || button.textContent);
const displayButton = (pane: HTMLElement) => within(cornerStack(pane)!).getByRole('button', { name: 'Display' });
// The state Display says each group is in: the side, 2D or 3D, the preset.
const viewValue = (pane: HTMLElement, id: 'side' | 'dimension' | 'display') => displayButton(pane).getAttribute(`data-view-${id}`);
const displayCard = () => document.querySelector<HTMLElement>('[data-settings-card-slide="in"] [data-display-settings-card]');
// Display's card, opened by its button where it is not; it stays open while the person works.
const openCard = (pane: HTMLElement) => { if (!displayCard()) fireEvent.click(displayButton(pane)); return displayCard()!; };
// The card's rows, section by section: each row's id and the value it shows.
const cardSections = (pane: HTMLElement) => {
  const sections: string[][][] = [[]];
  for (const node of openCard(pane).querySelector('[data-settings-card-body]')!.children) {
    if (node.hasAttribute('data-settings-rule')) { sections.push([]); continue; }
    sections.at(-1)!.push([node.getAttribute('data-settings-row')!, node.querySelector('[data-field-value]')!.textContent!]);
  }
  return sections;
};
// Each option's attribute, its dropdown's row.
const ROW_OF: Record<string, string> = { 'data-board-side-option': 'side', 'data-board-dimension-option': 'dimension', 'data-display-mode-option': 'display',
  'data-display-projection': 'projection', 'data-display-background': 'background' };
// A dropdown of the card, opened as a tap opens it: its list, or null where the card has no such row.
const viewSub = (pane: HTMLElement, id: string) => {
  const trigger = openCard(pane).querySelector<HTMLElement>(`[data-settings-select="${id}"]`);
  if (!trigger) return null;
  if (trigger.getAttribute('aria-expanded') !== 'true') fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false, pointerType: 'mouse' });
  return document.querySelector<HTMLElement>('[role=menu]');
};
// The open list put away, as Escape puts it away.
const closeSub = () => { const list = document.querySelector('[role=menu]'); if (list) fireEvent.keyDown(list, { key: 'Escape' }); };
// A choice of Display's, made as a person makes it: its dropdown opened, the option chosen.
const pickView = (pane: HTMLElement, attribute: string, value: string) =>
  fireEvent.click(viewSub(pane, ROW_OF[attribute])!.querySelector<HTMLElement>(`[${attribute}="${value}"]`)!);
// Flip and 2D/3D: the other side, the other mode.
const flip = (pane: HTMLElement) => pickView(pane, 'data-board-side-option', viewValue(pane, 'side') === 'top' ? 'bottom' : 'top');
const switchDimension = (pane: HTMLElement) => pickView(pane, 'data-board-dimension-option', viewValue(pane, 'dimension') === '2d' ? '3d' : '2d');
// A dropdown's options as its list draws them: each its name, whether it is the one chosen, and whether it has its icon.
const viewRows = (pane: HTMLElement, attribute: string) => {
  const rows = [...(viewSub(pane, ROW_OF[attribute])?.querySelectorAll<HTMLElement>(`[${attribute}]`) ?? [])]
    .map(row => [row.querySelector(':scope > span:last-child')?.textContent ?? row.textContent, String(row.getAttribute('data-state') === 'checked'), Boolean(row.querySelector('svg.lucide:not(.lucide-check), svg[data-board-side-icon], svg[data-text-glyph]'))]);
  closeSub();
  return rows;
};
const box = (pane: HTMLElement) => pane.querySelector<HTMLElement>('[data-quick-edit-box]');
// The view's panel (`kit/shell/FlatPanel.jsx`), a tab of it by name, its search box, and one of its tabs' bodies.
const panel = (pane: HTMLElement) => pane.querySelector<HTMLElement>('[data-flat-panel]')!;
const showTab = (pane: HTMLElement, name: string) => fireEvent.click(within(panel(pane)).getByRole('tab', { name }));
// The search box, the structure tab's first row (a board's every tab is its structure's).
const openSearch = (pane: HTMLElement) => within(panel(pane)).queryByRole('textbox', { name: 'Search the board' }) as HTMLInputElement | null;
// The search's icon at the head row's right end, pressed where the search is shut: its box.
const searchBox = (pane: HTMLElement) => {
  if (!openSearch(pane)) fireEvent.click(within(panel(pane)).getByRole('button', { name: 'Search the board' }));
  return openSearch(pane)!;
};
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
  await user.click(within(await displayMenu(user, pane)).getByRole('button', { name }));
  await user.click(await screen.findByRole('menuitemradio', { name: option }));
};
const choice = async (user: ReturnType<typeof userEvent.setup>, pane: HTMLElement, name: string) =>
  within(await displayMenu(user, pane)).getByRole('button', { name }).textContent;
// Display's Style: its presets (each its name, whether it is chosen and whether it has its icon); a preset picked from it;
// the one chosen (Custom while the eyes have left the preset's set).
const presets = async (pane: HTMLElement) => viewRows(pane, 'data-display-mode-option');
const pickPreset = async (_user: ReturnType<typeof userEvent.setup>, pane: HTMLElement, name: string) =>
  fireEvent.click([...viewSub(pane, 'display')!.querySelectorAll<HTMLElement>('[data-display-mode-option]')].find(option => option.textContent === name)!);
const presetChoice = async (_user: ReturnType<typeof userEvent.setup>, pane: HTMLElement) =>
  (await presets(pane)).find(([, chosen]) => chosen === 'true')?.[0] ?? null;
// Display's other choices after the presets: in 3D the projection's options, then the Background's.
const displayChoices = async (_user: ReturnType<typeof userEvent.setup>, pane: HTMLElement) =>
  [...viewRows(pane, 'data-display-projection'), ...viewRows(pane, 'data-display-background')];
const controllerOf = (view: { controller: any }) => waitFor(() => { expect(view.controller).not.toBeNull(); return view.controller; });
// An open menu, by its accessible name (portalled under the body, as every dropdown is).
const openMenu = (name: string) => waitFor(() => { const found = document.querySelector<HTMLElement>(`[role=menu][aria-label="${name}"]`); expect(found).not.toBeNull(); return found!; });
const menuShown = (name: string) => document.querySelector(`[role=menu][aria-label="${name}"]`);
const selected = (controller: any) => controller.readState().selection.map((reference: any) => reference.target.selectors[0]);
/** Select's filter, the submenu of its chevron menu's one row, opened when a press on the board has put it away. */
const filterSubmenu = () => document.querySelector<HTMLElement>('[data-slot=dropdown-menu-sub-content][aria-label="Filter"]');
const filterRow = () => document.querySelector<HTMLElement>('[data-select-filter-row]');
const filterMenu = async (pane: HTMLElement, user: ReturnType<typeof userEvent.setup>) => {
  const shown = filterSubmenu();
  if (shown) return shown;
  if (!menuShown('Filter')) await user.click(within(strip(pane)).getByRole('button', { name: /^Filter:/ }));
  await user.click(await waitFor(() => { expect(filterRow()).not.toBeNull(); return filterRow()!; }));
  return waitFor(() => { expect(filterSubmenu()).not.toBeNull(); return filterSubmenu()!; });
};
/**
 * Ticks or unticks one of the filter's boxes, the menu opened first. jsdom has no geometry for a submenu's
 * pointer grace area: the keyboard ticks, the same handler.
 */
const tick = async (user: ReturnType<typeof userEvent.setup>, box: HTMLElement) => { box.focus(); await user.keyboard('{Enter}'); };
const toggleBox = async (pane: HTMLElement, user: ReturnType<typeof userEvent.setup>, name: string) => {
  await tick(user, within(await filterMenu(pane, user)).getByRole('menuitemcheckbox', { name }));
};

/** A tap on the board where sheet point `at` is on screen in the last frame painted. */
const tap = (pane: HTMLElement, at: [number, number], init: Record<string, unknown> = {}) => {
  const canvas = pane.querySelector<HTMLCanvasElement>('[data-board-surface] canvas')!;
  const [clientX, clientY] = pageToScreen(frames.at(-1)!, at[0], at[1]);
  const event = { pointerId: 1, pointerType: 'mouse', button: 0, clientX, clientY, ...init };
  fireEvent.pointerDown(canvas, event);
  fireEvent.pointerUp(canvas, event);
};

it("a board's strip is a drawing's — Select (in hand), Draw, Measure; its view settings (Side, Mode | Style, Background) the navbar's Display card; its panel is docked, open, the Parts, the Nets, then the Layers", async () => {
  const { pane, dispose } = await open();
  await opened(pane);
  const tools = strip(pane);
  expect([...tools.querySelectorAll(':scope button[aria-pressed]')].filter(button => !button.closest('[data-view-controls]'))
    .map(button => button.getAttribute('aria-label'))).toEqual(['Select', 'Draw', 'Measure']);
  expect(within(tools).getByRole('button', { name: 'Select' }).getAttribute('aria-pressed')).toBe('true');
  expect(within(tools).getByRole('button', { name: 'Filter: everything' })).toBeTruthy();
  // Its view settings are the navbar's, at its right end — Display, the plain cube, no chevron, a toggle whose card is
  // Side and Mode | Style and Background, with Reset — the navbar's 28px button; the corner holds the zoom alone, and
  // nothing of the view is on the strip, which has no rule.
  expect([viewButtons(pane), displayButton(pane).querySelector('.lucide-chevron-down')]).toEqual([['Display', 'Preview'], null]);
  expect([viewValue(pane, 'side'), viewValue(pane, 'dimension'), viewValue(pane, 'display')]).toEqual(['top', '2d', 'board']);
  for (const button of cornerStack(pane)!.querySelectorAll('button')) expect(button.className.includes('size-control')).toBe(true);
  expect([cornerStack(pane)!.closest('[data-viewer-navbar]') !== null, pane.querySelector('[data-view-corner-stack]')]).toEqual([true, null]);
  // Each dropdown shows its choice with its icon (Mode its words alone); its options each theirs, the one on screen chosen. In 2D there is no
  // Projection; Reset is off while the board is as it opened for the first time.
  expect(cardSections(pane)).toEqual([[['side', 'Top'], ['dimension', '2D']], [['display', 'Board'], ['background', 'Light']]]);
  expect(within(displayCard()!).getByRole('button', { name: 'Reset' }).hasAttribute('disabled')).toBe(true);
  expect([viewRows(pane, 'data-board-side-option'), viewRows(pane, 'data-board-dimension-option')])
    .toEqual([[['Top', 'true', true], ['Bottom', 'false', true]], [['2D', 'true', false], ['3D', 'false', false]]]);
  expect(await presets(pane)).toEqual([['Board', 'true', true], ['Copper', 'false', true], ['Assembly', 'false', true], ['Placement', 'false', true]]);
  expect(await displayChoices(userEvent.setup({ skipHover: true, pointerEventsCheck: 0 }), pane)).toEqual([['Light', 'true', true], ['Dark', 'false', true]]);
  expect(tools.querySelector('[data-strip-rule], [data-view-controls]')).toBeNull();
  // The zoom: one control, "100%" and its chevron, not the strip's chrome; no − or +.
  const surface = FLOATING_CHROME_SURFACE_CLASS.split(' ');
  const pill = pane.querySelector<HTMLElement>('[data-zoom-pill]')!;
  expect([[...pill.querySelectorAll('button')].map(button => button.textContent), surface.some(name => pill.classList.contains(name))]).toEqual([['100%'], false]);
  expect(within(pane).queryByRole('button', { name: 'Home' })).toBeNull();
  for (const name of ['Projection', 'Explode', 'Clip', 'Orbit', 'Joints', 'Animation', 'Settings']) {
    expect(within(pane).queryByRole('button', { name }), name).toBeNull();
  }
  // The panel, docked at the left: one head row, the tabs, then the search's icon at its right end; its toggle is the
  // navbar's, its first control, the same neutral button open or shut (aria-expanded says which).
  const aside = panel(pane);
  expect([aside.getAttribute('data-flat-panel'), aside.hidden]).toEqual(['docked', false]);
  const head = aside.querySelector<HTMLElement>('[data-flat-panel-head]')!;
  expect([head.querySelector('[role=tablist]') !== null, head.querySelector('[data-flat-panel-search-open]')!.getAttribute('aria-label'),
    aside.querySelector('[data-flat-panel-body] [data-flat-panel-search]')]).toEqual([true, 'Search the board', null]);
  expect(head.querySelector('[aria-label="Hide panel"]')).toBeNull();
  const leftToggle = pane.querySelector<HTMLElement>('[data-viewer-navbar] [data-navbar-panel="left"]')!;
  expect([leftToggle.getAttribute('aria-label'), leftToggle.getAttribute('aria-expanded'), leftToggle.getAttribute('aria-pressed'), leftToggle.getAttribute('aria-keyshortcuts')])
    .toEqual(['Hide panel', 'true', null, expect.stringMatching(/\\$/)]);
  // 8px over the tabs and under them; at its sides the panel's inset less what the pills (6px) and the search's button
  // (7px) hang out by, so the tabs' names and the search's icon stand on the inset (`--panel-inset`).
  expect([head.style.paddingTop, head.style.paddingBottom, head.style.paddingLeft, head.style.paddingRight])
    .toEqual(['8px', '8px', 'calc(var(--panel-inset) - 6px)', 'calc(var(--panel-inset) - calc((var(--cad-control) - 14px) / 2))']);
  expect(within(aside).getAllByRole('tab').map(tab => [tab.querySelector('[data-flat-panel-tab-name]')!.textContent, tab.getAttribute('aria-selected')])).toEqual([['Parts', 'true'], ['Nets', 'false'], ['Layers', 'false']]);
  expect(aside.querySelector('[role=tab] svg')).toBeNull();
  // The search's box takes the tabs' row; Escape gives it back.
  expect([searchBox(pane).placeholder, within(aside).queryByRole('tablist')]).toEqual(['Search', null]);
  fireEvent.keyDown(searchBox(pane), { key: 'Escape' });
  expect([openSearch(pane), within(aside).getAllByRole('tab').length]).toEqual([null, 3]);
  expect(tabBody(pane, 'parts').hidden).toBe(false);
  expect(tabBody(pane, 'nets').hidden).toBe(true);
  expect(tabBody(pane, 'layers').hidden).toBe(true);
  // The Layers tab is the layer list alone.
  expect(within(tabBody(pane, 'layers')).queryAllByRole('button').filter(node => node.hasAttribute('data-value-dropdown'))).toEqual([]);
  // Nothing is picked yet: Quick Edit is its one row, with no attachments.
  expect([box(pane) !== null, box(pane)!.querySelector('[data-quick-edit-context]')]).toEqual([true, null]);

  dispose();
});

it('a native board uses the host language for its controls, tree and accessible canvas', async () => {
  const { pane, dispose } = await open('blinky.kicad_pcb', { locale: 'zh-CN' });
  await opened(pane);
  expect(pane.querySelector('canvas')?.getAttribute('aria-label')).toBe('电路板：blinky.kicad_pcb');
  expect(within(panel(pane)).getByRole('tab', { name: '元件' }).getAttribute('aria-selected')).toBe('true');
  fireEvent.click(within(panel(pane)).getByRole('button', { name: '搜索电路板' }));
  expect(within(panel(pane)).getByRole('textbox', { name: '搜索电路板' })).toBeTruthy();
  expect(within(pane).getByRole('button', { name: '选择', exact: true })).toBeTruthy();
  expect(within(pane).getByText('电阻')).toBeTruthy();
  expect(within(pane).queryByText('Resistors')).toBeNull();

  dispose();
});

it('a board without its index is the picture, its view controls, and its Layers (with the layer display): no tools, no Parts or Nets, no Quick Edit', async () => {
  const { board: _index, ...picture } = BOARD as any;
  readPlot = () => json(picture);
  const { pane, dispose } = await open();
  await opened(pane);
  expect(pane.querySelector('canvas')?.getAttribute('aria-label')).toBe('Board: blinky.kicad_pcb');
  // No tools: no strip at all; its view controls are the corner's, over the zoom.
  expect(within(pane).queryByRole('group', { name: 'Interaction tools' })).toBeNull();
  expect(viewButtons(pane)).toEqual(['Display', 'Preview']);
  expect(pane.querySelector('[data-zoom-pill]')).not.toBeNull();
  // Its one list, under its title: one tab is no pill.
  expect([within(panel(pane)).queryAllByRole('tab').length, panel(pane).querySelector('[data-flat-panel-heading]')!.textContent]).toEqual([0, 'Layers']);
  expect(within(panel(pane)).getByRole('tabpanel', { name: 'Layers' })).toBeTruthy();
  tap(pane, [34.175, 15]);
  expect(box(pane)).toBeNull();

  dispose();
});

it('a board has its panel from the first frame, open as it stays once the board is in, and no tools till then; once it failed to load, none of the chrome: the card, with the server’s own sentence', async () => {
  let answer: ((response: Response) => void) | null = null;
  readPlot = () => new Promise<Response>((resolve) => { answer = resolve; });
  const loading = await open();
  await waitFor(() => expect(answer).not.toBeNull());
  const toggle = () => loading.pane.querySelector('[data-viewer-navbar] [data-navbar-panel]')?.getAttribute('aria-expanded') ?? null;
  const aside = loading.pane.querySelector<HTMLElement>('aside[data-flat-panel]');
  const first = toggle();
  // While it loads, the Parts' placeholder rows in a busy tabpanel; gone as the parts arrive.
  const placeholders = () => aside?.querySelectorAll('[role="tabpanel"][aria-busy="true"] [data-tree-row-placeholder]').length ?? 0;
  expect([first, aside?.querySelector('[data-flat-panel-heading]')?.textContent, within(loading.pane).queryByRole('group', { name: 'Interaction tools' }), placeholders()])
    .toEqual(['true', 'Parts', null, 6]);
  await act(async () => { answer!(json(BOARD)); });
  await opened(loading.pane);
  await waitFor(() => expect(placeholders()).toBe(0));
  expect(toggle()).toBe(first);
  loading.dispose();
  cleanup();

  answer = null;
  const { pane, dispose } = await open('broken.kicad_pcb');
  await waitFor(() => expect(answer).not.toBeNull());
  await act(async () => { answer!(json({ error: UNREADABLE }, 400)); });
  const alert = await within(pane).findByRole('alert');
  expect(alert.textContent).toContain('is not a KiCad board');
  expect(within(pane).queryByRole('group', { name: 'Interaction tools' })).toBeNull();
  expect(pane.querySelector('[data-flat-panel], [data-navbar-panel="left"]')).toBeNull();
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
  const quickEdit = await waitFor(() => { expect(box(pane)!.querySelector('[data-quick-edit-context]')).not.toBeNull(); return box(pane)!; });
  const chips = () => [...box(pane)!.querySelectorAll('[data-quick-edit-ref] button[aria-label]')].map(button => button.getAttribute('aria-label'));
  expect(chips()).toEqual(['R1.1', 'Remove R1.1']);
  // A click on the chip opens its list, the pad's row and its key facts; a press on its name there copies its reference,
  // the file's absolute path and the pick, as a copied reference is.
  fireEvent.click(within(quickEdit).getByRole('button', { name: 'R1.1' }));
  const list = await screen.findByRole('dialog', { name: 'R1.1' });
  fireEvent.click(within(list).getByRole('button', { name: 'R1.1' }));
  await waitFor(() => expect(copied).toEqual([`${FILE}#R1.1`]));
  fireEvent.click(within(quickEdit).getByRole('button', { name: 'R1.1' }));
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'R1.1' })).toBeNull());
  // Shift adds: two references are one chip, "2 refs" (`ReferenceChips.jsx`).
  tap(pane, [35.825, 15], { shiftKey: true });
  expect(selected(controller)).toEqual(['#R1.1', '#R1.2']);
  await waitFor(() => expect(chips()).toEqual(['2 refs', 'Remove 2 refs']));
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

// A finger has no Shift: its tap adds what it lands on and takes out what is picked, and on bare board it clears at
// once. A tap that would take something out waits the double-click window (a finger's, its double tap's), which a
// double-click drops: a double-click never takes the selection away (`docs/viewer-ux.md`, "Selection and gestures").
it("a finger's tap adds, and takes out what is picked once its window has passed; a double-click never takes the selection away", async () => {
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  const controller = await controllerOf(view);
  const finger = { pointerType: 'touch' };
  const track = '#track:7a1c0000-0000-4000-8000-000000000001';
  tap(pane, [34.175, 15], finger);
  tap(pane, [30, 15], finger);
  expect(selected(controller)).toEqual(['#R1.1', track]);
  tap(pane, [34.175, 15], finger);
  expect(selected(controller)).toEqual(['#R1.1', track]);
  await waitFor(() => expect(selected(controller)).toEqual([track]));
  tap(pane, [36, 26], finger);
  expect(selected(controller)).toEqual([]);
  // A mouse keeps its rules, a click replacing. A double-click's second click on the pad its first picked would take
  // it out: it waits, and the double-click drops it, so the pad stays picked and nothing is left waiting (Shift adds).
  tap(pane, [30, 15]);
  tap(pane, [34.175, 15]);
  tap(pane, [34.175, 15]);
  expect(selected(controller)).toEqual(['#R1.1']);
  const [clientX, clientY] = pageToScreen(frames.at(-1)!, 34.175, 15);
  fireEvent.dblClick(pane.querySelector<HTMLCanvasElement>('[data-board-surface] canvas')!, { clientX, clientY });
  tap(pane, [35.825, 15], { shiftKey: true });
  expect(selected(controller)).toEqual(['#R1.1', '#R1.2']);
  dispose();
});

it("Select's filter is KiCad's boxes in one row's submenu: they tick what a click takes, All ticks them all, Locked items at the foot, and the submenu stays up", async () => {
  const user = userEvent.setup({ skipHover: true, pointerEventsCheck: 0 });
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  const controller = await controllerOf(view);
  await user.click(within(strip(pane)).getByRole('button', { name: 'Filter: everything' }));
  // The chevron's menu is one row, Filter, summing up what is ticked: every kind, as a board opens.
  const root = await openMenu('Filter');
  expect([...root.querySelectorAll('[role^=menuitem]')].map(item => item.getAttribute('aria-label'))).toEqual(['Filter: All']);
  const menu = await filterMenu(pane, user);
  const boxes = () => within(menu).getAllByRole('menuitemcheckbox').map(item => [item.textContent, item.getAttribute('aria-checked')]);
  // All, a rule, the kinds in KiCad's order in one column, each its name alone, then Locked items at the foot after a
  // rule; every kind ticked and no locked items as a board opens.
  expect(menu.querySelectorAll('[data-select-filter] > svg')).toHaveLength(0);
  expect([...menu.querySelectorAll('[data-select-filter], [role=separator]')].map(item => item.getAttribute('data-select-filter') ?? 'rule'))
    .toEqual(['all', 'rule', 'parts', 'texts', 'tracks', 'vias', 'pads', 'graphics', 'zones', 'ruleAreas', 'dimensions', 'rule', 'locked']);
  expect(boxes()).toEqual([['All', 'true'], ['Footprints', 'true'], ['Text', 'true'], ['Tracks', 'true'], ['Vias', 'true'],
    ['Pads', 'true'], ['Graphics', 'true'], ['Zones', 'true'], ['Rule areas', 'true'], ['Dimensions', 'true'], ['Locked items', 'false']]);
  // All unticks every kind, and the submenu stays up for the next box.
  await tick(user, within(menu).getByRole('menuitemcheckbox', { name: 'All' }));
  expect(boxes().filter(([, checked]) => checked === 'true')).toEqual([]);
  expect(filterRow()!.getAttribute('aria-label')).toBe('Filter: None');
  await tick(user, within(menu).getByRole('menuitemcheckbox', { name: 'Footprints' }));
  expect(filterSubmenu()).not.toBeNull();
  expect(boxes()[0]).toEqual(['All', 'mixed']);
  // Select's button wears the funnel while the filter is not every kind (a board's kinds have no glyph of their own).
  const badge = () => within(strip(pane)).getByRole('button', { name: 'Select' }).querySelector('[data-tool-icon-badge]')?.getAttribute('data-tool-icon-badge') ?? '';
  expect(badge()).toBe('filter');
  // The row names the one kind ticked, and counts several; the chevron names them.
  expect(filterRow()!.getAttribute('aria-label')).toBe('Filter: Footprints');
  expect(within(strip(pane)).getByRole('button', { name: 'Filter: Footprints' })).toBeTruthy();
  await tick(user, within(menu).getByRole('menuitemcheckbox', { name: 'Pads' }));
  expect(filterRow()!.getAttribute('aria-label')).toBe('Filter: 2 of 9');
  expect(within(strip(pane)).getByRole('button', { name: 'Filter: Footprints, Pads' })).toBeTruthy();
  await tick(user, within(menu).getByRole('menuitemcheckbox', { name: 'Pads' }));
  // R1.1, under the VBUS track's end: the part, not the pad or the copper.
  tap(pane, [34.175, 15]);
  expect(selected(controller)).toEqual(['#R1']);
  // A press on the board puts the menu away, as any dropdown's outside press does.
  expect(menuShown('Filter')).toBeNull();
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
  await toggleBox(pane, user, 'All');
  await toggleBox(pane, user, 'Footprints');
  tap(pane, [34.175, 15]);
  expect(selected(controller)).toEqual([]);
  await toggleBox(pane, user, 'Locked items');
  tap(pane, [34.175, 15]);
  expect(selected(controller)).toEqual(['#R1']);
  dispose();
});

it("a drag under Select draws the shared box: over bare board it names the area on the working layer, over the board's items it takes what it touches; the other drags pan as the 3D views' do; a jittered click is a click", async () => {
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
  // A drag is the box between its ends, every viewer's (drawn as it goes); over bare board it takes nothing, so it
  // names its area on F.Cu, the copper seen from the top; Shift at its release adds it; it does not pan.
  const before = { ...frames.at(-1)! };
  fireEvent.pointerDown(canvas, { ...press, ...at([25, 1]) });
  fireEvent.pointerMove(canvas, { ...press, ...at([30, 6]) });
  fireEvent.pointerMove(canvas, { ...press, ...at([35, 11]) });
  expect(pane.querySelectorAll('[data-box-select]')).toHaveLength(1);
  fireEvent.pointerUp(canvas, { ...press, ...at([35, 11]), shiftKey: true });
  expect(pane.querySelector('[data-box-select]')).toBeNull();
  expect(selected(controller)).toEqual(['#R1.1', '#F.Cu@x25y1..x35y11']);
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
  expect(selected(controller)).toEqual(['#R1.1', '#F.Cu@x25y1..x35y11']);
  // Over a pad: its reference, Deselect (it is picked), its net, and the framing.
  const overPad = await menuAt([34.175, 15]);
  expect(overPad.slice(0, 2)).toEqual(['Copy Reference', 'Deselect']);
  expect(overPad.at(-2)).toBe('Zoom to fit');
  await closeMenu();
  const quickEdit = await waitFor(() => { expect(box(pane)!.querySelector('[data-quick-edit-context]')).not.toBeNull(); return box(pane)!; });
  // A pad and an area: two references, one chip ("2 refs").
  expect([...quickEdit.querySelectorAll('[data-quick-edit-ref] button[aria-label]')].map(button => button.getAttribute('aria-label')))
    .toEqual(['2 refs', 'Remove 2 refs']);
  // The note's packet names them, for a snapshot to light them where the person put them.
  const note = within(quickEdit).getByRole('textbox', { name: 'Describe your changes' });
  note.textContent = 'Keep this clear.';
  fireEvent.input(note);
  fireEvent.click(within(quickEdit).getByRole('button', { name: 'Copy Prompt' }));
  await waitFor(() => expect(promptFiles.create).toHaveBeenCalledTimes(1));
  expect((promptFiles.create.mock.calls[0] as any)[0].references).toEqual(['#R1.1', '#F.Cu@x25y1..x35y11']);
  await waitFor(() => expect(copied.at(-1)).toContain(`${FILE}#F.Cu@x25y1..x35y11`));
  // A box that starts on R1 is a box all the same. It takes what it touches, even in part, as the filter
  // does (the part, its pads, the track into it), in place of the rest, whichever way it is drawn.
  const drag = (from: [number, number], to: [number, number]) => {
    fireEvent.pointerDown(canvas, { ...press, ...at(from) });
    fireEvent.pointerMove(canvas, { ...press, ...at([(from[0] + to[0]) / 2, (from[1] + to[1]) / 2]) });
    fireEvent.pointerUp(canvas, { ...press, ...at(to) });
  };
  drag([35.5, 15.2], [33.8, 15.6]);
  expect(selected(controller)).toEqual(expect.arrayContaining(['#R1', '#R1.1', '#R1.2']));
  expect(selected(controller).some((id: string) => id.includes('@x25'))).toBe(false);
  expect(selected(controller).some((id: string) => id.startsWith('#track:'))).toBe(true);
  tap(pane, [36, 26]);
  expect(selected(controller)).toEqual([]);
  drag([33.8, 15.2], [35.5, 15.6]);
  expect(selected(controller)).toEqual(expect.arrayContaining(['#R1', '#R1.1', '#R1.2']));
  expect(selected(controller).some((id: string) => id.startsWith('#track:'))).toBe(true);
  // A box that touches nothing names the area, either way.
  drag([35, 11], [25, 1]);
  expect(selected(controller)).toEqual(['#F.Cu@x25y1..x35y11']);
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
  // The panel is its lists alone: nothing of a pick is drawn under them, picked or not (a chip's card reads it).
  const detail = () => panel(pane).querySelector<HTMLElement>('[data-flat-panel-detail], [data-detail-card]');
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
  expect(parts.querySelector('[data-board-row="sheet:led"]')!.className).toContain('bg-brand-subtle');
  expect(detail()).toBeNull();
  expect(frames.at(-1)).toEqual(fitted);
  menu = await blockMenu();
  fireEvent.click(within(menu).getByRole('menuitem', { name: 'Zoom to led' }));
  await waitFor(() => expect(frames.at(-1)!.scale).toBeGreaterThan(fitted.scale));

  // A part selects as a click on the board does, and a net from the Nets; still nothing under the lists.
  fireEvent.click(within(parts).getByRole('button', { name: 'Select J1' }));
  expect(selected(controller)).toEqual(['#J1']);
  expect(detail()).toBeNull();
  fireEvent.click(within(panel(pane)).getByRole('tab', { name: 'Nets' }));
  fireEvent.click(within(nets).getByRole('button', { name: 'Select LED' }));
  expect(selected(controller)).toEqual(['#net:LED']);

  // The panel's search reads the parts with their pads and the nets: a pasted pad reference finds the pad,
  // and its press selects it.
  fireEvent.change(searchBox(pane), { target: { value: '#J1.2' } });
  await waitFor(() => expect(parts.querySelector('[data-search-row="pad:J1.2"]')).not.toBeNull());
  fireEvent.click(within(parts.querySelector<HTMLElement>('[data-search-row="pad:J1.2"]')!).getByRole('button'));
  expect(selected(controller)).toEqual(['#J1.2']);
  // A net by its name, in the Nets' hits, no Layers (none matches).
  fireEvent.change(searchBox(pane), { target: { value: 'VBUS' } });
  await waitFor(() => expect(nets.querySelector('[data-search-row="net:VBUS"]')).not.toBeNull());
  expect(tabBody(pane, 'layers').querySelector('[data-flat-panel-hit]')).toBeNull();
  fireEvent.click(within(nets.querySelector<HTMLElement>('[data-search-row="net:VBUS"]')!).getByRole('button', { name: 'Select VBUS' }));
  expect(selected(controller)).toEqual(['#net:VBUS']);
  // A search that names a layer finds it in the Layers too; Escape in the box clears it.
  fireEvent.change(searchBox(pane), { target: { value: 'B.Cu' } });
  await waitFor(() => expect([...tabBody(pane, 'layers').querySelectorAll('[data-flat-panel-hit] [data-layer-row]')].map(row => row.getAttribute('data-layer-row'))).toEqual(['B.Cu']));
  // The match lit in its name, as the Parts' and Nets' are.
  expect([...tabBody(pane, 'layers').querySelectorAll('[data-layer-row="B.Cu"] [data-tree-filter-hit]')].map(hit => hit.textContent).join('')).toBe('B.Cu');
  fireEvent.keyDown(searchBox(pane), { key: 'Escape' });
  // Closed: the tabs again, on the tab that was open (the Nets), no hits anywhere.
  expect([openSearch(pane), tabBody(pane, 'layers').querySelector('[data-flat-panel-hit]'), within(panel(pane)).getByRole('tab', { selected: true }).querySelector('[data-flat-panel-tab-name]')!.textContent])
    .toEqual([null, null, 'Nets']);
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
  fireEvent.click(within(pane).getByRole('button', { name: 'Hide panel' }));
  tap(pane, [20, 23.175]);
  expect(selected(controller)).toEqual(['#D1.2']);
  expect(scrolled.at(-1)).toBe('net:GND');
  fireEvent.click(within(pane).getByRole('button', { name: 'Show panel' }));
  await waitFor(() => expect(scrolled.at(-1)).toBe('net:LED'));
  dispose();
});

it("the Layers tab holds KiCad's layer display options — the others, the pours, the zones' and tracks' opacity — and a Layers row's press makes it the active layer", async () => {
  const user = userEvent.setup({ skipHover: true, pointerEventsCheck: 0 });
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  const menu = await displayMenu(user, pane);
  // The preset is the strip's Display, not the tab's: the tab has the layers and their display.
  expect([...menu.querySelectorAll('[data-settings-section]')].map(section => section.getAttribute('data-settings-section'))).toEqual(['board-layer-display']);
  expect(within(menu).getAllByRole('button').filter(node => node.hasAttribute('data-value-dropdown')).map(select => [select.getAttribute('aria-label'), select.textContent]))
    .toEqual([['Other layers', 'Shown']]);
  expect(within(menu).getByRole('slider', { name: 'Zone opacity' }).getAttribute('aria-valuenow')).toBe('0.6');
  expect((within(menu).getByRole('textbox', { name: 'Track opacity value' }) as HTMLInputElement).value).toBe('100');
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
  expect((zones as HTMLInputElement).value).toBe('25');
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
  // Each group headed by the panel's shared heading, over its rows.
  expect([...layers.querySelectorAll('[data-layer-group] > [data-tree-heading]')].map(heading => [heading.tagName, heading.textContent]))
    .toEqual([['LI', 'Front'], ['LI', 'Back'], ['LI', 'Other']]);
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

it("the board is drawn in the viewport's theme, Light by default whatever the app's: Dark draws it again in the dark canvas and palette, from the payload it holds", async () => {
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
  // The app dark, the viewport's Background Light (the default): the board stays as it is drawn, light.
  await view.scheme('dark');
  await waitFor(() => expect(pane.querySelector('[data-viewport-scheme]')!.getAttribute('data-viewport-scheme')).toBe('light'));
  expect([themes.includes('dark'), canvases.at(-1), swatch('F.SilkS')]).toEqual([false, APP_THEME_COLORS.light.canvas, 'rgb(156, 150, 77)']);
  await view.scheme('light');
  // Dark, in the light app: drawn again here, KiCad's own colours on the neutral dark canvas, nothing asked of the server.
  await view.background('dark');
  await waitFor(() => expect(themes).toContain('dark'));
  await waitFor(() => expect(canvases.at(-1)).toBe(APP_THEME_COLORS.dark.canvas));
  expect(swatch('F.SilkS')).toBe('rgb(242, 237, 161)');
  expect(reads).toBe(plots);
  expect(pane.querySelector('[data-cad-canvas-box]')!.classList.contains('dark')).toBe(true);
  dispose();
});

it("a board's card picture is drawn once, in the light theme, on nothing but the board", async () => {
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  const controller = await controllerOf(view);
  themes.length = 0;
  const picture = await controller.thumbnail({ width: 480, height: 360 });
  expect(picture).toBeInstanceOf(Blob);
  expect('dark' in picture).toBe(false);
  expect(themes).toEqual(['light']);
  dispose();
});

it('a preset chooses the layers; the side (Flip) and the pours are kept through a change of preset', async () => {
  const user = userEvent.setup({ skipHover: true, pointerEventsCheck: 0 });
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  // The side, the corner's Side: the top shown, and a press turns the board over.
  expect(viewValue(pane, 'side')).toBe('top');
  flip(pane);
  expect(viewValue(pane, 'side')).toBe('bottom');
  await user.click(within(await displayMenu(user, pane)).getByRole('switch', { name: 'Copper pours' }));
  // A switch is not a layer set: the preset is still the one on screen, the corner's Display ticks it.
  expect(await presetChoice(user, pane)).toBe('Board');
  expect((await presets(pane)).map(([name]) => name)).toEqual(['Board', 'Copper', 'Assembly', 'Placement']);
  // Then the viewport's Background, the person's, every view's: Light and Dark.
  expect((await displayChoices(user, pane)).map(([name]) => name)).toEqual(['Light', 'Dark']);
  await pickPreset(user, pane, 'Copper');
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
  expect(box(pane)!.querySelector('[data-quick-edit-context]')).toBeNull();
  // Select takes a measurement first, so the note's pick is D1.1, off the measurement's ends.
  fireEvent.click(within(strip(pane)).getByRole('button', { name: 'Select' }));
  tap(pane, [20, 24.825]);
  const quickEdit = await waitFor(() => { expect(box(pane)!.querySelector('[data-quick-edit-context]')).not.toBeNull(); return box(pane)!; });
  const note = within(quickEdit).getByRole('textbox', { name: 'Describe your changes' });
  note.textContent = 'Move this pad.';
  fireEvent.input(note);
  fireEvent.click(within(quickEdit).getByRole('button', { name: 'Copy Prompt' }));
  await waitFor(() => expect(promptFiles.create).toHaveBeenCalledTimes(1));
  const request = promptFiles.create.mock.calls[0][0] as any;
  expect(request).not.toHaveProperty('measurements');
  expect(request.views).toEqual([expect.objectContaining({ label: 'current view', display: { mode: 'board', side: 'top', poured: true, others: 'shown', zones: 0.6, tracks: 1 } })]);
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

it("the panel collapses whole, leaving nothing over the board, its toggle the navbar's; ⌘\\ shows and hides it, / opens it on its search, and the tab is kept", async () => {
  const { pane, dispose } = await open();
  await opened(pane);
  showTab(pane, 'Layers');
  const toggle = () => pane.querySelector<HTMLElement>('[data-viewer-navbar] [data-navbar-panel="left"]')!;
  fireEvent.click(toggle());
  expect(panel(pane).hidden).toBe(true);
  // Nothing floats over the board: the navbar's toggle, unpressed, is the way back.
  expect(pane.querySelector('[data-flat-panel-pill]')).toBeNull();
  // The same neutral button open or shut: its name and aria-expanded say which.
  expect([toggle().getAttribute('aria-label'), toggle().getAttribute('aria-expanded'), toggle().getAttribute('data-variant')]).toEqual(['Show panel', 'false', 'ghost']);
  fireEvent.click(toggle());
  expect(panel(pane).hidden).toBe(false);
  expect([toggle().getAttribute('aria-label'), toggle().getAttribute('aria-expanded'), toggle().getAttribute('data-variant')]).toEqual(['Hide panel', 'true', 'ghost']);
  expect(within(panel(pane)).getByRole('tab', { name: 'Layers' }).getAttribute('aria-selected')).toBe('true');
  // The keys, while the board has the keyboard.
  const canvas = pane.querySelector<HTMLCanvasElement>('canvas[data-board-tool]')!;
  fireEvent.keyDown(canvas, { key: '\\', metaKey: true });
  await waitFor(() => expect(panel(pane).hidden).toBe(true));
  fireEvent.keyDown(canvas, { key: '\\', ctrlKey: true });
  await waitFor(() => expect(panel(pane).hidden).toBe(false));
  fireEvent.click(toggle());
  fireEvent.keyDown(canvas, { key: '/' });
  // / opens the search box, the keyboard in it.
  await waitFor(() => expect(document.activeElement).toBe(openSearch(pane)));
  expect(panel(pane).hidden).toBe(false);
  dispose();
});

it("at 900px the panel pushes the board aside, and below 700px it starts collapsed, its navbar toggle opening it beside the board; a phone has no panel", async () => {
  const sized = (width: number) => vi.mocked(HTMLElement.prototype.getBoundingClientRect).mockReturnValue(
    { x: 0, y: 0, left: 0, top: 0, right: width, bottom: 700, width, height: 700, toJSON: noop } as DOMRect);
  sized(900);
  const view = await open();
  await opened(view.pane);
  // At 900px the panel pushes; there is one, at the left.
  expect([panel(view.pane).getAttribute('data-flat-panel'), panel(view.pane).hidden, view.pane.querySelectorAll('aside').length]).toEqual(['docked', false, 1]);
  view.dispose();
  cleanup();
  // Below 700px it starts collapsed (`sidebars.js`), unwritten; its navbar toggle opens it, pushing too: no panel ever
  // overlays the board.
  sized(650);
  const narrow = await open();
  await opened(narrow.pane);
  await waitFor(() => expect(panel(narrow.pane).hidden).toBe(true));
  fireEvent.click(within(narrow.pane.querySelector<HTMLElement>('[data-viewer-navbar]')!).getByRole('button', { name: 'Show panel' }));
  expect([panel(narrow.pane).getAttribute('data-flat-panel'), panel(narrow.pane).hidden]).toEqual(['docked', false]);
  expect(narrow.pane.querySelector('[data-flat-panel-scrim]')).toBeNull();
  narrow.dispose();
  cleanup();
  // A phone: no docked panel and no pill; the navbar's toggle opens the panel as a sheet from the left, and Display opens
  // its card, the desktop's — Side, Mode | Style, Background — a phone having no corner; no bottom sheet. Bottom, chosen
  // in Side's dropdown, turns the board over, the card staying open.
  sized(400);
  const phone = await open();
  await opened(phone.pane);
  expect([phone.pane.querySelector('[data-flat-panel]'), phone.pane.querySelector('[data-zoom-pill]')]).toEqual([null, null]);
  expect(phone.pane.querySelector('[data-cad-toolbar] [data-view-controls]')).toBeNull();
  expect(within(phone.pane).queryByRole('button', { name: 'More tools' })).toBeNull();
  fireEvent.click(within(phone.pane.querySelector<HTMLElement>('[data-viewer-navbar]')!).getByRole('button', { name: 'Show panel' }));
  await waitFor(() => expect(document.querySelector('[data-panel-sheet] [data-flat-panel="page"]')).not.toBeNull());
  fireEvent.keyDown(document.querySelector('[data-panel-sheet]')!, { key: 'Escape' });
  await waitFor(() => expect(document.querySelector('[data-panel-sheet]')).toBeNull());
  expect(viewButtons(phone.pane)).toEqual(['Display', 'Preview']);
  expect([cardSections(phone.pane).map(rows => rows.map(([id]) => id)), document.querySelector('[data-vaul-drawer], [data-view-sheet]')])
    .toEqual([[['side', 'dimension'], ['display', 'background']], null]);
  pickView(phone.pane, 'data-board-side-option', 'bottom');
  await waitFor(() => expect(drawn.at(-1)).toMatchObject({ side: 'bottom' }));
  expect([viewValue(phone.pane, 'side'), displayCard() !== null]).toEqual(['bottom', true]);
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

it("2D/3D is one view: the strip, its view controls, the panel and the corner stay the same mounted controls, Projection is Display's in 3D, and what is picked and measured stays; 3 switches; the file keeps it", async () => {
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
  // What the strip (its view controls among it), the panel and the corner (its pill) are, by their names and by the elements themselves.
  const controls = () => ({
    strip: strip(pane), panel: panel(pane), views: cornerStack(pane), pill: pane.querySelector<HTMLElement>('[data-zoom-pill]'),
    names: [...pane.querySelectorAll<HTMLElement>('[data-cad-tool-groups] button, [data-flat-panel] [role=tab], [data-zoom-pill] button, [data-navbar-view-controls] button')]
      .map(button => (button.getAttribute('aria-label') || button.textContent)!.replace(/^(Display mode): .*/, '$1'))
  });
  const flat = controls();
  expect(flat.pill).not.toBeNull();
  // In 2D Display has no Projection: a flat board has none.
  expect(await displayChoices(user, pane)).toEqual([['Light', 'true', true], ['Dark', 'false', true]]);
  const dimension = displayButton(pane);
  expect(viewValue(pane, 'dimension')).toBe('2d');
  switchDimension(pane);
  await waitFor(() => expect(pane.querySelector('[data-board-3d]')).not.toBeNull());
  // Its first frame up, the flat canvas is put away (and lets its rasters go); the camera eases to Home.
  await waitFor(() => expect(pane.querySelector('[data-board-surface] canvas[role=img]')!.classList.contains('invisible')).toBe(true));
  await waitFor(() => expect(viewport3d.calls).toContain('goHome'));
  // The same controls, by name and by element: the same Display button, reading 3D.
  const solid = controls();
  expect(solid.names).toEqual(flat.names);
  for (const key of ['strip', 'panel', 'views', 'pill'] as const) expect(solid[key], key).toBe(flat[key]);
  expect(displayButton(pane)).toBe(dimension);
  expect(viewValue(pane, 'dimension')).toBe('3d');
  // The corner is the one it was: the zoom (the 3D camera's now), and no cube, Home or Projection of a 3D view's.
  expect(viewport3d.props.viewCube).toBe(false);
  expect([within(pane).queryAllByRole('button', { name: /^Projection/ }).filter(button => !button.hasAttribute('data-value-dropdown')), pane.querySelector('[data-view-home]')]).toEqual([[], null]);
  // The pick and the measurement are where they were; a camera is the 3D view's to pose.
  expect(selected(controller)).toEqual(['#R1.2']);
  fireEvent.click(within(strip(pane)).getByRole('button', { name: 'Measure' }));
  expect(within(pane).getByRole('button', { name: 'Measurement 1: 1.65 mm' })).toBeTruthy();
  await controller.setCamera({ position: [0, 0, 100], target: [0, 0, 0], up: [0, 1, 0] });
  expect(viewport3d.calls.at(-1)).toBe('setPerspective [0,0,100]');
  // Display's card in 3D: the camera's Projection after Side and Mode, the one on screen chosen; the presets as in 2D.
  expect(viewButtons(pane)).toEqual(['Display', 'Preview']);
  expect(cardSections(pane)).toEqual([[['side', 'Top'], ['dimension', '3D'], ['projection', 'Orthographic']], [['display', 'Board'], ['background', 'Light']]]);
  expect((await displayChoices(user, pane)).map(([name, checked]) => [name, checked])).toEqual([['Orthographic', 'true'], ['Perspective', 'false'], ['Light', 'true'], ['Dark', 'false']]);
  pickView(pane, 'data-display-projection', 'perspective');
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board3d?.value?.projection).toBe('perspective'));
  await pickPreset(user, pane, 'Copper');
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board?.value?.mode).toBe('copper'));
  // The file keeps it: 3D, opened again in 3D.
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board3d?.value).toMatchObject({ mode: '3d', projection: 'perspective' }));
  // Reset: the board as it opens for the first time — the top, 2D, Board and Orthographic — the same pill, the flat canvas
  // shown, the pick kept; the Background, the person's, left.
  fireEvent.click(within(displayCard()!).getByRole('button', { name: 'Reset' }));
  await waitFor(() => expect(pane.querySelector('[data-board-3d]')).toBeNull());
  expect(cardSections(pane)).toEqual([[['side', 'Top'], ['dimension', '2D']], [['display', 'Board'], ['background', 'Light']]]);
  expect(within(displayCard()!).getByRole('button', { name: 'Reset' }).hasAttribute('disabled')).toBe(true);
  expect(pane.querySelector('[data-zoom-pill]')).toBe(flat.pill);
  expect(pane.querySelector('[data-board-surface] canvas[role=img]')!.classList.contains('invisible')).toBe(false);
  expect(selected(controller)).toEqual(['#R1.2']);
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board3d?.value).toMatchObject({ mode: '2d', projection: 'orthographic' }));
  // 3, as KiCad's Alt+3: 3D again.
  fireEvent.keyDown(pane.querySelector('[data-board-surface] canvas')!, { key: '3' });
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board3d?.value?.mode).toBe('3d'));
  const stored = view.state;
  dispose();
  cleanup();
  const again = await open('blinky.kicad_pcb', { state: stored });
  await waitFor(() => expect(again.pane.querySelector('[data-board-3d]')).not.toBeNull());
  expect(viewValue(again.pane, 'dimension')).toBe('3d');
  again.dispose();
});

it("Display's Side and Mode choose the state on screen; ⇧F flips as F still fits", async () => {
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  // Display's Side and Mode: the state on screen chosen.
  const user = userEvent.setup({ skipHover: true, pointerEventsCheck: 0 });
  const rows = async () => [viewRows(pane, 'data-board-side-option'), viewRows(pane, 'data-board-dimension-option')]
    .map(list => list.map(([name, chosen]) => [name, chosen]));
  expect(await rows()).toEqual([[['Top', 'true'], ['Bottom', 'false']], [['2D', 'true'], ['3D', 'false']]]);
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
  // The sides' glyphs, Side's Top and Bottom options': the board's two layers, the solid one at 85%, set as the side it shows.
  const list = viewSub(pane, 'side')!;
  const glyph = (side: string) => { const svg = list.querySelector(`[data-board-side-option="${side}"] svg[data-board-side-icon]`)!;
    return { place: svg.querySelector('g')!.getAttribute('transform'), paths: [...svg.querySelectorAll('path')].map(path => [path.getAttribute('d'), path.getAttribute('fill-opacity')]) }; };
  const top = glyph('top'), bottom = glyph('bottom');
  expect(top.paths.map(([, fill]) => fill)).toEqual(['0.85', null]);
  // The same drawing mirrored top to bottom, so the two sides weigh the same: the top's set 0.75 down, the bottom's 0.75 up.
  expect([top.place, bottom.place, bottom.paths]).toEqual(['translate(0 0.75)', 'matrix(1 0 0 -1 0 23.25)', top.paths]);
  closeSub();
  // ⇧F turns the board over, the window kept: drawn from the bottom, and Display's Side says so.
  fireEvent.keyDown(canvas, { key: 'F', code: 'KeyF', shiftKey: true });
  await waitFor(() => expect(drawn.at(-1)).toMatchObject({ side: 'bottom' }));
  expect(frames.at(-1)).toEqual(moved);
  expect((await rows())[0]).toEqual([['Top', 'false'], ['Bottom', 'true']]);
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board?.value?.side).toBe('bottom'));
  // F is the fit, still, not a flip; ⇧F again, and the top is back.
  fireEvent.keyDown(canvas, { key: 'f', code: 'KeyF' });
  await waitFor(() => expect(frames.at(-1)).toEqual(fitted));
  expect(drawn.at(-1)).toMatchObject({ side: 'bottom' });
  fireEvent.keyDown(canvas, { key: 'F', code: 'KeyF', shiftKey: true });
  await waitFor(() => expect(drawn.at(-1)).toMatchObject({ side: 'top' }));
  expect(viewValue(pane, 'side')).toBe('top');
  dispose();
});

it("in 3D Flip turns the camera over, and its icon is the side the camera is on: turned by Flip, by ⇧F or by hand, and after a reload on a camera below the board", async () => {
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  switchDimension(pane);
  await waitFor(() => expect(viewport3d.calls).toContain('goHome'));
  // The camera as the 3D view reports it: above the board, or turned over it, below.
  const camera = (below: boolean) => ({ position: [10, below ? 40 : -40, below ? -30 : 30], target: [10, 0, 0], up: [0, 0, 1] });
  const report = (below: boolean) => act(() => { viewport3d.props.onPerspectiveChange(camera(below)); });
  // From above (the stand-in's camera), Flip turns the camera over the board's left-to-right axis, eased; the
  // icon is the camera's side, so it stays the top until the camera passes the board's plane.
  viewport3d.calls.length = 0;
  flip(pane);
  expect(viewport3d.calls).toEqual(['setPerspective [10,40,-30]']);
  expect(viewValue(pane, 'side')).toBe('top');
  report(true);
  expect(viewValue(pane, 'side')).toBe('bottom');
  // Turned back over by hand (an orbit past the board's plane): the icon follows.
  report(false);
  expect(viewValue(pane, 'side')).toBe('top');
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
  expect(viewValue(again.pane, 'side')).toBe('bottom');
  again.dispose();
});

it("entering 3D eases to a camera on the side 2D showed, so Flip keeps it: Home's tilt from below for the bottom, the camera left in 3D turned over to the top", async () => {
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  const side = () => viewValue(pane, 'side');
  // Seen from the bottom in 2D, then in 3D: Home framed from the 3D views' Home direction turned over the board.
  flip(pane);
  await waitFor(() => expect(drawn.at(-1)).toMatchObject({ side: 'bottom' }));
  viewport3d.homes.length = 0;
  switchDimension(pane);
  await waitFor(() => expect(viewport3d.homes).toHaveLength(1));
  expect([viewport3d.homes[0], side()]).toEqual([{ direction: [2.1, 1.65, -1.08], up: [0, 0, 1] }, 'bottom']);
  // The camera at rest under the board, kept with the file; back in 2D, still the bottom, which Flip turns to the top.
  act(() => { viewport3d.props.onPerspectiveChange({ position: [10, 40, -30], target: [10, 0, 0], up: [0, 0, 1] }); });
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board3d?.value?.camera?.position).toEqual([10, 40, -30]));
  switchDimension(pane);
  await waitFor(() => expect(pane.querySelector('[data-board-3d]')).toBeNull());
  expect(side()).toBe('bottom');
  flip(pane);
  await waitFor(() => expect(drawn.at(-1)).toMatchObject({ side: 'top' }));
  // In 3D again, from the top: the camera it was left at, turned over the board to the top about its target, and no Home.
  viewport3d.calls.length = 0;
  switchDimension(pane);
  await waitFor(() => expect(viewport3d.calls).toContain('setPerspective [10,-40,30]'));
  expect([viewport3d.homes.length, side()]).toEqual([1, 'top']);
  dispose();
});

it("leaving 3D gives the 2D view its own window back, whatever the camera did there: an orbit's zoom and centre never reach the plan, after a reload in 3D too", async () => {
  const view = await open();
  const { pane, dispose } = view;
  await opened(pane);
  // The 2D view panned off its fit (a middle-button drag): its own window.
  const canvas = pane.querySelector<HTMLCanvasElement>('[data-board-surface] canvas')!;
  const at = ([x, y]: [number, number]) => { const [clientX, clientY] = pageToScreen(frames.at(-1)!, x, y); return { clientX, clientY }; };
  const middle = { pointerId: 2, pointerType: 'mouse', button: 1 };
  const fitted = { ...frames.at(-1)! };
  fireEvent.pointerDown(canvas, { ...middle, ...at([20, 15]) });
  fireEvent.pointerMove(canvas, { ...middle, ...at([28, 18]) });
  fireEvent.pointerUp(canvas, { ...middle, ...at([28, 18]) });
  await waitFor(() => expect(frames.at(-1)!.offsetX).not.toBe(fitted.offsetX));
  const own = { ...frames.at(-1)! };
  // In 3D, a hand orbits and zooms the camera: tilted, zoomed in threefold, centred far off the 2D window.
  const orbit = (where: HTMLElement) => {
    const camera = new THREE.OrthographicCamera(-600, 600, 350, -350, 0.1, 1000);
    camera.position.set(60, -80, 40);
    camera.up.set(0, 0, 1);
    camera.zoom = 3;
    camera.lookAt(60, -20, 0);
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld();
    Object.assign(viewport3d, { camera, controls: { target: new THREE.Vector3(60, -20, 0) }, hands: viewport3d.hands + 1 });
    const solid = where.querySelector<HTMLCanvasElement>('[data-board-3d] canvas')!;
    Object.defineProperties(solid, { clientWidth: { configurable: true, value: 1200 }, clientHeight: { configurable: true, value: 700 } });
    act(() => { viewport3d.props.onPerspectiveChange({ position: [60, -80, 40], target: [60, -20, 0], up: [0, 0, 1] }); });
  };
  switchDimension(pane);
  await waitFor(() => expect(viewport3d.calls).toContain('goHome'));
  orbit(pane);
  switchDimension(pane);
  await waitFor(() => expect(pane.querySelector('[data-board-3d]')).toBeNull());
  // Back in 2D: the window it was left at, exactly, from the side Flip showed.
  expect(frames.at(-1)).toEqual(own);
  expect(drawn.at(-1)).toMatchObject({ side: 'top' });
  // Into 3D again and left there; reopened in 3D, the camera orbited, then back to 2D: the 2D window the file
  // was left at, never the camera's.
  switchDimension(pane);
  await waitFor(() => expect(view.state.renderers?.[KEY]?.renderer?.board3d?.value?.mode).toBe('3d'));
  const stored = view.state;
  dispose();
  cleanup();
  frames.length = 0;
  const again = await open('blinky.kicad_pcb', { state: stored });
  await waitFor(() => expect(again.pane.querySelector('[data-board-3d]')).not.toBeNull());
  orbit(again.pane);
  switchDimension(again.pane);
  await waitFor(() => expect(again.pane.querySelector('[data-board-3d]')).toBeNull());
  await waitFor(() => expect(frames.length).toBeGreaterThan(0));
  for (const key of ['scale', 'offsetX', 'offsetY'] as const) expect(frames.at(-1)![key], key).toBeCloseTo(own[key], 6);
  again.dispose();
});

it("a part's Details say its 3D model, or why it has none, and the Parts end with the parts that have none; the Layers' 3D models eye is kept with the file", async () => {
  // The models table as the server answers it: R1's STEP found by its document id, D1's named and not found (J1 names none).
  const view = await open('blinky.kicad_pcb', { models: {
    '${KICAD9_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_0603_1608Metric.wrl': { file: 'R_0603_1608Metric.step', document: 'r0603', api: '/api/v1/documents/step/r0603', stamp: '1-2' },
    '${KIPRJMOD}/models/led.step': { file: 'led.step', missing: 'not-found' } } });
  const { pane, dispose } = view;
  await opened(pane);
  showTab(pane, 'Parts');
  const parts = await waitFor(() => { const found = tabBody(pane, 'parts').querySelector<HTMLElement>('[data-board-row="block:no-3d-model"]'); expect(found).not.toBeNull(); return tabBody(pane, 'parts'); });
  expect(parts.querySelector('[data-board-row="block:no-3d-model"]')!.textContent).toContain('No 3D model');
  // Read in its Quick Edit chip's list: a press on the chip opens it, the part's row with its key facts under it.
  const fact = async (ref: string) => {
    fireEvent.click(within(parts).getAllByRole('button', { name: `Select ${ref}` })[0]);
    const chip = await waitFor(() => { const found = box(pane)?.querySelector<HTMLElement>(`[data-quick-edit-ref] button[aria-label^="${ref}"]`); expect(found).toBeTruthy(); return found!; });
    if (chip.getAttribute('aria-expanded') !== 'true') fireEvent.click(chip);
    return waitFor(() => {
      const rows = [...document.querySelectorAll(`[data-quick-edit-group-member] [data-quick-edit-ref-facts] > div`)].map(row => row.textContent);
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
  // Its one glyph, a box, in the row's slot as every tree's kind icon is.
  expect([row.querySelectorAll('[data-tree-row-glyph]').length, row.firstElementChild!.hasAttribute('data-tree-row-glyph'), row.firstElementChild!.querySelector('svg')]).toEqual([1, true, expect.anything()]);
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
  switchDimension(pane);
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

it("a board has Preview as a 3D file has: its button right of Display, the page Preview's while it is up (its bar, no navbar, no tools, no Part colours), Escape back to the view as it was, its settings kept with the file", async () => {
  const view = await open();
  const { pane } = view;
  await opened(pane);
  tap(pane, [35.825, 15]);
  await waitFor(() => expect(selected(view.controller)).toEqual(['#R1.2']));
  expect(viewButtons(pane)).toEqual(['Display', 'Preview']);
  fireEvent.click(within(cornerStack(pane)!).getByRole('button', { name: 'Preview' }));
  // Preview's own bar names the file, in the navbar's place; the strip, the panel and Quick Edit are put away, and
  // Preview's own view (a viewport of its own, in Preview) is mounted over the board's.
  const bar = await waitFor(() => { const found = pane.querySelector<HTMLElement>('[data-preview-bar]'); expect(found).not.toBeNull(); return found!; });
  expect(bar.querySelector('[data-preview-name]')!.textContent).toBe('blinky.kicad_pcb');
  await waitFor(() => expect(pane.querySelector('[data-viewer-navbar]')).toBeNull());
  expect(pane.querySelector('[data-view-top-layer]')!.hasAttribute('hidden')).toBe(true);
  await waitFor(() => expect(pane.querySelector('[data-preview-view] [data-stand-in-viewport]')).not.toBeNull());
  expect([viewport3d.props.preview, viewport3d.props.renderMode, pane.querySelector('[data-board-3d]')]).toEqual([true, true, null]);
  // Its settings: Orbit, then Render's lighting, background and floor; no Part colours. An edit is the file's.
  fireEvent.click(within(bar).getByRole('button', { name: 'Display' }));
  const settings = pane.querySelector<HTMLElement>('[data-preview-settings-panel]')!;
  expect([...settings.querySelectorAll('[data-settings-heading]')].map(heading => heading.textContent)).toEqual(['Orbit', 'Lighting', 'Background', 'Floor']);
  fireEvent.click(within(settings).getByRole('switch', { name: 'Floor' }));
  await waitFor(() => expect(view.state.renderers?.[KEY]?.preview).toEqual({ floor: { enabled: false } }));
  // A tool's key takes up nothing in Preview; Escape leaves it, and the view is as it was: the navbar, the tool in hand, the pick.
  fireEvent.keyDown(settings, { key: 'm' });
  fireEvent.keyDown(settings, { key: 'Escape' });
  await waitFor(() => expect(pane.querySelector('[data-preview-bar]')).toBeNull());
  await waitFor(() => expect(pane.querySelector('[data-viewer-navbar]')).not.toBeNull());
  expect([viewButtons(pane), within(strip(pane)).getByRole('button', { name: 'Select' }).getAttribute('aria-pressed'), selected(view.controller),
    pane.querySelector('[data-board-surface] canvas[role=img]')!.classList.contains('invisible')]).toEqual([['Display', 'Preview'], 'true', ['#R1.2'], false]);
  view.dispose();
});
