import React, { forwardRef, useEffect, useImperativeHandle } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

// The shell's chrome — the strip, the tool stack, the file sidebar, the view's actions, Display's dropdown and preview —
// under the smallest renderer that mounts it (`renderers/shell-harness`), with the WebGL viewport
// replaced by an empty box: nothing asserted here is drawn by it. What the viewport is handed is
// recorded, so a test can read what the shell asked of it, and a view update it is handed is
// acknowledged at once, as the real one does once it holds the frame.
// The editor's viewport and, while it is open, Preview's (`PreviewView.jsx`, a viewport of its own).
const viewportProps: { current: any } = { current: null };
const previewProps: { current: any } = { current: null };
// What the viewport's handle answers, where a test gives it one (Preview's picture, `pictureProgress`).
const viewportHandle: { current: any } = { current: null };
vi.mock('../../../../dist/renderers/kit/shell/ShellViewport.js', () => ({
  default: forwardRef(function MockViewport(props: any, ref) {
    const record = props.preview ? previewProps : viewportProps;
    record.current = props;
    useEffect(() => () => { if (props.preview) previewProps.current = null; }, []);
    useImperativeHandle(ref, () => viewportHandle.current, []);
    const update = props.viewUpdate;
    useEffect(() => { if (update?.revision) update.binding.complete(update.revision); }, [update?.revision, update?.binding]);
    // Its first frame drawn, as the real one reports it.
    useEffect(() => { props.onPresentationChange?.({ file: props.modelKey, key: props.presentationKey, preparing: false }); }, [props.presentationKey]);
    return <div data-mock-viewport=""><canvas />{typeof props.children === 'function'
      ? props.children({ runtimeRef: { current: null }, hostRef: { current: null }, mountRef: { current: null }, viewerReadyTick: 0, commitScene: () => true })
      : null}</div>;
  }),
}));
import HarnessRenderer from '../../../../dist/renderers/shell-harness/HarnessRenderer.js';
import { createHarnessRenderer } from '../../../../dist/renderers/shell-harness/index.js';
import { FileViewer } from '../../../../dist/file-viewer/index.js';
import { viewerLinks } from '../../../../dist/file-viewer/navigation/links.js';
import { ViewerElementContext, ViewerHostContext } from '../../../../dist/host/context.js';
import { testHost } from '../../../../dist/host/testing/host.js';
import { ViewerMobileContext } from '../../../../dist/file-viewer/responsive.js';
import { TOOL_PANEL_WIDTH } from '../../../../dist/renderers/kit/tools/toolStackLayout.js';
import { FILE_SIDEBAR_SURFACE_CLASS, FLOATING_CHROME_SURFACE_CLASS, FLOATING_SURFACE_CLASS } from '../../../../dist/lib/floatingSurface.js';
import { SolidModeIcon } from '../../../../dist/renderers/kit/view-settings/DisplayModeOptions.js';
import { ControlUsageProvider } from '../../../../dist/usage/controls.js';
import { SIDEBAR_SLIDE_CLASS } from '../../../../dist/renderers/kit/tools/FileSidebar.js';
import { createAnimationClock } from '../../../../dist/renderers/kit/tools/playbar/animationClock.js';
import { writeFileView } from '../../../../dist/renderers/kit/shell/fileView.js';

// jsdom lays nothing out, so the few sizes the chrome reads are given: a viewer 1280 × 800 whose
// stack column (under the strip) and the sidebar panel's room (under its tiles) are each 600px
// tall, and each panel and the sidebar's as big as its own style says.
const VIEWER = { width: 1280, height: 800 }, STACK_HEIGHT = 600;
const restores: (() => void)[] = [];
function override(target: object, key: string, descriptor: PropertyDescriptor) {
  const previous = Object.getOwnPropertyDescriptor(target, key);
  Object.defineProperty(target, key, { configurable: true, ...descriptor });
  restores.push(() => previous ? Object.defineProperty(target, key, previous) : delete (target as any)[key]);
}
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
  override(HTMLElement.prototype, 'clientHeight', { get(this: HTMLElement) { return this.hasAttribute('data-cad-tool-stack') || this.matches('[data-file-sidebar-room] > :not([data-file-sidebar-tools])') ? STACK_HEIGHT : 0; } });
  const rect = Element.prototype.getBoundingClientRect;
  override(Element.prototype, 'getBoundingClientRect', { value(this: HTMLElement) {
    if (this.hasAttribute('data-cad-scene-backdrop')) return DOMRect.fromRect({ x: 0, y: 0, ...VIEWER });
    if (this.matches('section[data-tool-panel], aside[data-cad-file-sidebar]')) return DOMRect.fromRect({ x: 8, y: 48, width: parseFloat(this.style.width) || 0, height: parseFloat(this.style.maxHeight) || 100 });
    return rect.call(this);
  } });
  for (const name of ['setPointerCapture', 'releasePointerCapture']) override(Element.prototype, name, { value() {} });
  override(Element.prototype, 'hasPointerCapture', { value: () => true });
  override(Element.prototype, 'scrollIntoView', { value() {} });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); while (restores.length) restores.pop()!(); viewportProps.current = null; previewProps.current = null; viewportHandle.current = null; });
// Preview is up: its own view mounted over the editor's, which draws nothing under it.
const inPreview = () => previewProps.current !== null && viewportProps.current.suspended === true;

/** The tab's settings as a host hands them over, counting every write. */
function tabSettings(initial: object = {}) {
  let settings: any = { toolStack: { panels: {}, collapsed: {} }, ...initial };
  const listeners = new Set<() => void>();
  const store = { writes: 0, getSnapshot: () => settings, subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    update(patch: object) { store.writes += 1; settings = { ...settings, ...patch }; listeners.forEach(listener => listener()); } };
  return store;
}
type Settings = ReturnType<typeof tabSettings>;
function frame({ name = 'panel.harness', preferences = tabSettings(), state = undefined as unknown, mobile = false, onStateChange = (_: unknown) => {}, appearance = { colorScheme: 'light' } as object, notice = null as React.ReactNode, viewer = false, data = {} as object,
  usage = null as ((counts: { control: string; count: number; seconds: number }[]) => void) | null } = {}) {
  const props = { source: { id: 'one' }, file: { path: `/models/${name}`, name, kind: 'file' }, document: null, notice,
    onReady() {}, onOpenFile() {}, appearance, state, onStateChange, reload() {}, data: { services: { preferences }, ...data } };
  // `viewer`: inside a viewer's element, as FileViewer draws it, where the viewer's keys are its own.
  const element = () => {
    const shell = <ViewerHostContext.Provider value={testHost()}><ViewerMobileContext.Provider value={mobile}>
      <HarnessRenderer {...(props as any)} /></ViewerMobileContext.Provider></ViewerHostContext.Provider>;
    // `usage`: the host's count of the controls a person used (`usage/controls.js`).
    const counted = usage ? <ControlUsageProvider report={usage}>{shell}</ControlUsageProvider> : shell;
    if (!viewer) return counted;
    const ref = { current: null as HTMLDivElement | null };
    return <ViewerElementContext.Provider value={ref}><div ref={node => { ref.current = node; }}>{counted}</div></ViewerElementContext.Provider>;
  };
  const view = render(element());
  return { ...view, preferences, remount: () => { view.unmount(); return render(element()); } };
}
const panel = (label: string) => document.querySelector<HTMLElement>(`section[data-tool-panel][aria-label="${label}"]`);
const shown = () => [...document.querySelectorAll<HTMLElement>('[data-cad-tool-stack] section[data-tool-panel]')].filter(node => !node.hidden).map(node => node.getAttribute('aria-label'));
// The file sidebar's sections, mounted, top to bottom; its panel; and its tiles, each a section's.
const sections = () => [...document.querySelectorAll<HTMLElement>('[data-cad-file-sidebar] section[data-tool-panel]')].filter(node => !node.closest('[hidden]')).map(node => node.getAttribute('aria-label'));
const bar = () => document.querySelector<HTMLElement>('aside[data-cad-file-sidebar]')!;
const isOpen = () => bar().hasAttribute('data-open');
const tiles = () => within(screen.getByRole('group', { name: 'File sidebar' })).getAllByRole('button');
const tileNames = () => tiles().map(button => button.getAttribute('aria-label'));
const pressedTiles = () => tiles().filter(button => button.getAttribute('aria-pressed') === 'true').map(button => button.getAttribute('aria-label'));
const tile = (name: string) => within(screen.getByRole('group', { name: 'File sidebar' })).getByRole('button', { name, exact: true });
const handles = (label: string) => [...panel(label)!.querySelectorAll('[role=separator]')].map(handle => handle.getAttribute('aria-label'));
const width = (label: string) => parseFloat(panel(label)!.style.width);
const layout = (preferences: Settings) => preferences.getSnapshot().toolStack;
const tool = (name: string) => within(screen.getByRole('group', { name: 'Interaction tools' })).getByRole('button', { name });
function drag(handle: Element, [dx, dy]: [number, number], { release = true } = {}) {
  fireEvent.pointerDown(handle, { button: 0, pointerId: 1, clientX: 100, clientY: 100 });
  fireEvent.pointerMove(handle, { pointerId: 1, clientX: 100 + dx, clientY: 100 + dy });
  if (release) fireEvent.pointerUp(handle, { pointerId: 1, clientX: 100 + dx, clientY: 100 + dy });
}

it("the strip is at the top centre with the stack under it, the file sidebar's tiles at the top-left: no section open until a tile is pressed, its panel a tool panel's width, capped at the room under the tiles, and nothing is stored until a person sizes it", () => {
  const { preferences } = frame();
  // The strip and the stack under it, 8px down from the viewer's top, centred, stopping 8px above
  // the cube's line (the cube itself 8px off the bottom); the sidebar's room 8px in from the top
  // and left, down the viewer's full height to 8px off its bottom.
  expect(document.querySelector<HTMLElement>('[data-cad-tool-groups]')!.style).toMatchObject({ top: '8px', left: '8px', right: '8px', bottom: 'calc(16px + 6rem)' });
  expect(document.querySelector<HTMLElement>('[data-file-sidebar-room]')!.style).toMatchObject({ top: '8px', left: '8px', bottom: '8px' });
  // A tile per section; none open as the file opens, the panel away and out of reach.
  expect([tileNames(), sections(), shown()]).toEqual([['Harness tree', 'Reference'], ['Harness tree', 'Harness reference'], []]);
  expect([isOpen(), bar().hasAttribute('inert')]).toEqual([false, true]);
  fireEvent.click(tile('Harness tree'));
  expect([isOpen(), bar().hasAttribute('inert'), pressedTiles()]).toEqual([true, false, ['Harness tree']]);
  expect(TOOL_PANEL_WIDTH).toBe(164);
  expect([bar().style.width, bar().style.maxHeight]).toEqual([`${TOOL_PANEL_WIDTH}px`, `${STACK_HEIGHT}px`]);
  // A section is the panel's width and its content's height: no width, cap, scroller or grip of its own.
  for (const label of ['Harness tree', 'Harness reference']) {
    expect([panel(label)!.style.width, panel(label)!.style.maxHeight], label).toEqual(['', '']);
    expect(panel(label)!.querySelector('[data-radix-scroll-area-viewport]'), label).toBeNull();
    expect(handles(label), label).toEqual([]);
  }
  // The panel scrolls, as one, and is the person's to size by one grip in its bottom-right corner
  // (Quick Edit's, drawn inside it).
  expect(bar().querySelector('[data-file-sidebar-scroller]')).not.toBeNull();
  const grip = screen.getByRole('separator', { name: 'Resize file sidebar' });
  expect([grip.getAttribute('data-resize-grip'), grip.parentElement]).toEqual(['bottom-right', bar()]);
  expect(grip.className).toMatch(/\babsolute bottom-0\b.*\bright-0 cursor-nwse-resize\b/);
  // A kept effect is the stack's: fixed, at the one width, with no grip.
  fireEvent.click(tool('Keep'));
  expect(shown()).toEqual(['Kept controls']);
  expect([width('Kept controls'), handles('Kept controls')]).toEqual([TOOL_PANEL_WIDTH, []]);
  expect(tool('Keep').getAttribute('aria-pressed')).toBe('true');
  expect([preferences.writes, layout(preferences)]).toEqual([0, { panels: {}, collapsed: {} }]);
});

it("each section's panel is sized by its corner, on its own: width and cap in one write when the pointer lets go, the keyboard by 16px and Home and End to the bounds, and a remount opens at what was left", () => {
  const { preferences, remount } = frame();
  fireEvent.click(tile('Harness tree'));
  const corner = screen.getByRole('separator', { name: 'Resize file sidebar' });
  drag(corner, [100, -100], { release: false });
  // Mid-drag: the panel follows the corner; nothing is written yet.
  expect([bar().style.width, bar().style.maxHeight]).toEqual([`${TOOL_PANEL_WIDTH + 100}px`, `${STACK_HEIGHT - 100}px`]);
  expect(corner.hasAttribute('data-dragging')).toBe(true);
  expect(preferences.writes).toBe(0);
  fireEvent.pointerUp(corner, { pointerId: 1, clientX: 200, clientY: 0 });
  expect(preferences.writes).toBe(1);
  expect(layout(preferences).panels).toEqual({ 'sidebar:tree': { width: TOOL_PANEL_WIDTH + 100, height: STACK_HEIGHT - 100 } });
  expect([bar().style.width, bar().style.maxHeight]).toEqual([`${TOOL_PANEL_WIDTH + 100}px`, `${STACK_HEIGHT - 100}px`]);
  // From the keyboard, one axis a key: Left/Right the width, Up/Down the cap; Home and End both, to their bounds.
  fireEvent.keyDown(corner, { key: 'ArrowLeft' });
  fireEvent.keyDown(corner, { key: 'ArrowDown' });
  expect(layout(preferences).panels['sidebar:tree']).toEqual({ width: TOOL_PANEL_WIDTH + 84, height: STACK_HEIGHT - 84 });
  fireEvent.keyDown(corner, { key: 'Home' });
  // Narrower than a tool panel, down to room for a heading's name and its buttons.
  expect(layout(preferences).panels['sidebar:tree']).toEqual({ width: 120, height: 64 });
  fireEvent.keyDown(corner, { key: 'End' });
  expect(layout(preferences).panels['sidebar:tree']).toEqual({ width: VIEWER.width / 2, height: STACK_HEIGHT });
  // Another section's panel has a size of its own: the default, until it is sized.
  fireEvent.click(tile('Reference'));
  expect([bar().style.width, bar().style.maxHeight]).toEqual([`${TOOL_PANEL_WIDTH}px`, `${STACK_HEIGHT}px`]);
  remount();
  fireEvent.click(tile('Harness tree'));
  expect([bar().style.width, bar().style.maxHeight]).toEqual([`${VIEWER.width / 2}px`, `${STACK_HEIGHT}px`]);
  // Reset puts it back.
  act(() => preferences.update({ toolStack: { panels: {}, collapsed: {} } }));
  expect([bar().style.width, bar().style.maxHeight]).toEqual([`${TOOL_PANEL_WIDTH}px`, `${STACK_HEIGHT}px`]);
});

it("the sidebar's tiles are there whatever the tool, a tool's own section coming and going with it; one section is open at a time, another tile taking its place, and its X or a second press of its tile closes it, its content kept", () => {
  const { preferences } = frame();
  expect(tool('Select').getAttribute('aria-pressed')).toBe('true');
  fireEvent.click(tool('Pencil'));
  expect(tileNames()).toEqual(['Harness tree', 'Reference']);
  fireEvent.click(tool('Pose'));
  expect(tileNames()).toEqual(['Harness tree', 'Reference', 'Position']);
  const closed = () => ['Harness tree', 'Harness reference', 'Harness position'].filter(label => panel(label)!.hasAttribute('data-sidebar-closed'));
  fireEvent.click(tile('Reference'));
  expect([pressedTiles(), closed()]).toEqual([['Reference'], ['Harness tree', 'Harness position']]);
  // Its head is its name and its X: nothing folds.
  const head = panel('Harness reference')!.querySelector<HTMLElement>('[data-sidebar-head]')!;
  expect([within(head).getByRole('heading').textContent, within(head).getAllByRole('button').map(button => button.getAttribute('aria-label'))])
    .toEqual(['Reference', ['Close reference']]);
  expect(panel('Harness reference')!.querySelector('[aria-expanded]')).toBeNull();
  fireEvent.click(tile('Position'));
  expect([pressedTiles(), closed()]).toEqual([['Position'], ['Harness tree', 'Harness reference']]);
  // A closed section stays mounted: the tree's search is as it was left.
  fireEvent.click(tile('Harness tree'));
  fireEvent.change(screen.getByRole('textbox', { name: 'Filter tree' }), { target: { value: 'Row 1' } });
  fireEvent.click(tile('Reference'));
  fireEvent.click(tile('Harness tree'));
  expect((screen.getByRole('textbox', { name: 'Filter tree' }) as HTMLInputElement).value).toBe('Row 1');
  // A second press of its tile closes it, and so does its X: the panel slides away.
  fireEvent.click(tile('Harness tree'));
  expect([pressedTiles(), isOpen()]).toEqual([[], false]);
  fireEvent.click(tile('Reference'));
  fireEvent.click(within(panel('Harness reference')!).getByRole('button', { name: 'Close reference' }));
  expect([pressedTiles(), isOpen()]).toEqual([[], false]);
  // Pose put down: its section, and its tile, go with it.
  fireEvent.click(tool('Pose'));
  expect([tileNames(), preferences.writes]).toEqual([['Harness tree', 'Reference'], 0]);
});

it("on a phone the file sidebar is one tile at the top-left, on the strip's line, the strip kept clear of it; it opens the panel on the section last open (the first, at first), headed by a tab per section and one X", () => {
  frame({ mobile: true });
  const strip = screen.getByRole('group', { name: 'Interaction tools' });
  const toggle = screen.getByRole('button', { name: 'Sidebar' });
  // The sidebar's tile reserves its width and an 8px gap; the controls centre within that
  // room, with their viewport-centering offset verified in the real-browser layout test.
  expect([strip.contains(toggle), toggle.hasAttribute('data-file-sidebar-toggle'), document.querySelectorAll('[data-file-sidebar-tools] button').length])
    .toEqual([false, true, 1]);
  const column = document.querySelector<HTMLElement>('[data-cad-tool-groups]')!;
  expect(column.style).toMatchObject({ left: '62px', right: '8px' });
  expect(column.className).toMatch(/\bitems-center\b/);
  // Its room runs from the top-left corner to the view's bottom inset, clear of Quick Edit's peek.
  expect(document.querySelector<HTMLElement>('[data-file-sidebar-room]')!.style).toMatchObject({ top: '8px', left: '8px', bottom: 'calc(var(--cad-quick-edit-peek, 0px) + 8px)' });
  const tabs = () => [...document.querySelectorAll<HTMLElement>('[data-file-sidebar-tab]')].map(tab => [tab.getAttribute('aria-label'), tab.getAttribute('data-state')]);
  const shownSection = () => ['Harness tree', 'Harness reference'].filter(label => !panel(label)!.hasAttribute('data-sidebar-closed'));
  expect(isOpen()).toBe(false);
  fireEvent.click(toggle);
  expect([isOpen(), toggle.getAttribute('aria-pressed'), tabs(), shownSection()]).toEqual([true, 'true', [['Harness tree', 'on'], ['Reference', 'off']], ['Harness tree']]);
  // A phone's panel, its own width and no grip; the one X is the tab row's, none in a section's head.
  expect([bar().style.width, bar().querySelector('[data-file-sidebar-corner]')]).toEqual(['288px', null]);
  expect([...document.querySelectorAll('[data-file-sidebar-close]')].map(button => [button.getAttribute('aria-label'), Boolean(button.closest('[data-file-sidebar-tabs]'))]))
    .toEqual([['Close sidebar', true]]);
  fireEvent.click(document.querySelector('[data-file-sidebar-tab="reference"]')!);
  expect([tabs(), shownSection()]).toEqual([[['Harness tree', 'off'], ['Reference', 'on']], ['Harness reference']]);
  // Closed by its X, it opens again on the section last open; the tile closes it too.
  fireEvent.click(screen.getByRole('button', { name: 'Close sidebar' }));
  expect([isOpen(), toggle.getAttribute('aria-pressed')]).toEqual([false, 'false']);
  fireEvent.click(toggle);
  expect([isOpen(), shownSection()]).toEqual([true, ['Harness reference']]);
  fireEvent.click(toggle);
  expect(isOpen()).toBe(false);
  fireEvent.click(tool('Pencil'));
  expect(tool('Pencil').getAttribute('aria-pressed')).toBe('true');
  // The drawing row is the same row on a phone, its buttons 36px tiles (`data-touch`), wrapping where it must; there is no chevron.
  const row = screen.getByRole('toolbar', { name: 'Annotation controls' });
  expect(row.hasAttribute('data-touch')).toBe(true);
  expect(screen.queryByRole('button', { name: /^(Pencil|Shapes) tools$/ })).toBeNull();
  expect([...row.querySelectorAll('[role=group][aria-label$=" tools"] button')].map(button => button.getAttribute('aria-label'))).toEqual(['Pen', 'Highlighter', 'Eraser']);
});

// Display: the current mode's tile and its menu, the modes and the Grid switch.
const displayButton = (root: HTMLElement = document.body) => within(root).getByRole('button', { name: /^Display mode: / });
const displayLit = (root?: HTMLElement) => displayButton(root).getAttribute('aria-expanded') === 'true';
const displayMenu = () => document.querySelector<HTMLElement>('[role=menu][aria-label="Display"]');
// Projection: its own tile, before Display's, and its menu of the two projections.
const projectionButton = () => screen.getByRole('button', { name: /^Projection: / });
const projectionMenu = () => document.querySelector<HTMLElement>('[role=dialog][aria-label="Projection"]');
async function openDisplay(user: ReturnType<typeof userEvent.setup>, root?: HTMLElement) {
  await user.click(displayButton(root));
  await waitFor(() => expect(displayMenu()).not.toBeNull());
}
// A control by its name, whatever it says it is set to ("Projection: Orthographic" is Projection).
const named = (button: Element) => button.getAttribute('aria-label')!.split(':')[0];
// The view's controls: the strip's last, after its tools and a rule.
const barButtons = () => [...document.querySelector('[role=group][aria-label="Interaction tools"] [data-view-controls]')?.querySelectorAll('button') ?? []].map(named);
// Preview's own bar, over the view's top edge: its name, and its controls at its right.
const previewBar = () => document.querySelector<HTMLElement>('[data-preview-bar]');
const cornerButtons = () => [...previewBar()?.querySelectorAll('button') ?? []].map(named);
// The strip's tools, before the view's controls.
const strip = () => [...screen.getByRole('group', { name: 'Interaction tools' }).querySelectorAll('button')].filter(button => !button.closest('[data-view-controls]')).map(button => button.getAttribute('aria-label'));

it('while the model loads the viewer shows none of its own chrome, and all of it returns with the model', () => {
  frame();
  const stage = (name: string) => act(() => { fireEvent.click(document.querySelector(`[data-harness-stage="${name}"]`)!); });
  expect(screen.getByRole('group', { name: 'Interaction tools' })).toBeTruthy();
  expect(barButtons()).toEqual(['Projection', 'Display mode', 'Preview']);
  stage('finding');
  expect(screen.queryByRole('group', { name: 'Interaction tools' })).toBeNull();
  expect(document.querySelector('[data-cad-tool-stack]')).toBeNull();
  expect(barButtons()).toEqual([]);
  expect(viewportProps.current.isLoading).toBe(true);
  stage('idle');
  expect(screen.getByRole('group', { name: 'Interaction tools' })).toBeTruthy();
  expect(barButtons()).toEqual(['Projection', 'Display mode', 'Preview']);
  // With nothing to work on yet, the strip is idle together, and so are Projection, Display and Preview.
  stage('unready');
  expect(strip()).toEqual(['Select', 'Pencil', 'Shapes', 'Keep', 'Pose']);
  const idle = (name: string) => (name === 'Display' ? displayButton() : name === 'Projection' ? projectionButton()
    : name === 'Preview' ? screen.getByRole('button', { name }) : tool(name)).hasAttribute('disabled');
  expect(['Select', 'Pencil', 'Shapes', 'Projection', 'Display', 'Preview'].map(idle)).toEqual([true, true, true, true, true, true]);
  stage('idle');
  expect(['Select', 'Pencil', 'Shapes', 'Projection', 'Display', 'Preview'].map(idle)).toEqual([false, false, false, false, false, false]);
});

it("Display and Preview are a 3D view's, as its renderer declares: a view that does not declare it has neither, not disabled ones, and a request for Preview leaves it as it is", () => {
  // Preview asked for from outside the strip, as a link or a host request would.
  const ask = () => act(() => { fireEvent.click(document.querySelector('[data-harness-ask-preview]')!); });
  // A 3D view (the harness's, declared `previewable`): Projection, Display and Preview end the strip, and a request enters it.
  frame();
  expect(barButtons()).toEqual(['Projection', 'Display mode', 'Preview']);
  ask();
  expect(inPreview()).toBe(true);
  cleanup();
  // A view whose renderer does not declare it (`flat.harness`, a 2D view's stand-in): neither on the
  // strip, no rule, and the same request leaves the normal view on screen, its tools up.
  frame({ name: 'flat.harness' });
  expect(barButtons()).toEqual([]);
  for (const name of [/^Projection: /, /^Display mode: /, 'Preview']) expect(screen.queryByRole('button', { name })).toBeNull();
  expect(document.querySelector('[data-strip-rule]')).toBeNull();
  ask();
  expect(inPreview()).toBe(false);
  expect(document.querySelector('[data-preview-chrome]')!.hasAttribute('inert')).toBe(false);
  expect(strip()).toEqual(['Pencil', 'Shapes']);
});

it('a load the model did not survive leaves only the card saying so, and a failed update it survives keeps the chrome', () => {
  frame();
  const stage = (name: string) => act(() => { fireEvent.click(document.querySelector(`[data-harness-stage="${name}"]`)!); });
  stage('broken');
  expect(screen.getByText('Couldn’t load the harness model')).toBeTruthy();
  expect(screen.queryByRole('group', { name: 'Interaction tools' })).toBeNull();
  expect(document.querySelector('[data-cad-tool-stack]')).toBeNull();
  expect(barButtons()).toEqual([]);
  expect(document.querySelector('[data-viewport-status]')).toBeNull();
  expect(viewportProps.current.viewCube).toBe(false);
  stage('failed');
  expect(screen.getByRole('group', { name: 'Interaction tools' })).toBeTruthy();
  expect(barButtons()).toEqual(['Projection', 'Display mode', 'Preview']);
  expect(viewportProps.current.viewCube).toBe(true);
});

it("a dismissed alert's own icon, at the navbar's right, brings its card back; it goes with the card's return, and when the alert clears", async () => {
  // The harness under the real FileViewer, whose navbar's right holds nothing of its own but a
  // dismissed alert's icon: the view's controls (Projection, Display and Preview) end the strip.
  const host = testHost({ links: viewerLinks({ version: '0.7.5' }), environment: { colorScheme: 'light', platform: 'darwin' },
    files: { id: 'one', stat: async (path: string) => ({ path, name: path.split('/').pop()!, kind: 'file', extension: 'harness', size: 1 }) } });
  render(<FileViewer file="/models/one.harness" host={host as any} renderers={[createHarnessRenderer({ preferences: tabSettings() })]}
    state={{}} onStateChange={() => {}} />);
  await screen.findByRole('button', { name: 'Preview' });
  const right = () => [...document.querySelector('[data-viewer-navbar] > div')!.querySelectorAll('a, button')].map(node => node.getAttribute('aria-label'));
  const card = () => screen.queryByRole('alert');
  const stage = (name: string) => act(() => { fireEvent.click(document.querySelector(`[data-harness-stage="${name}"]`)!); });
  const view: string[] = [];
  expect([right(), barButtons()]).toEqual([view, ['Projection', 'Display mode', 'Preview']]);
  expect(document.querySelectorAll('[data-viewer-navbar] [data-view-controls] button')).toHaveLength(0);
  stage('failed');
  expect(card()!.textContent).toContain('Harness update failed');
  expect(right()).toEqual(view, 'the card is up: no icon');
  // Put away: the card's own icon, in the error's colour, named after the alert, at the navbar's right.
  fireEvent.click(within(card()!).getByRole('button', { name: 'Dismiss' }));
  expect(card()).toBeNull();
  expect(right()).toEqual(['Harness update failed', ...view]);
  const icon = screen.getByRole('button', { name: 'Harness update failed' });
  expect(icon.querySelector('svg')!.getAttribute('class')).toMatch(/\blucide-circle-alert\b.*\btext-destructive\b/);
  // Pressed, it brings the card back and goes.
  fireEvent.click(icon);
  expect(card()!.textContent).toContain('Harness update failed');
  expect(right()).toEqual(view);
  // Put away again, and then the alert clears: no card, and no icon; raised again, the card shows.
  fireEvent.click(within(card()!).getByRole('button', { name: 'Dismiss' }));
  expect(right()[0]).toBe('Harness update failed');
  stage('idle');
  expect([card(), right()]).toEqual([null, view]);
  stage('failed');
  expect(card()).not.toBeNull();
  expect(right()).toEqual(view);
});

it("the host's notice waits for the model, then takes the top-right with Quick Edit stacked under it", () => {
  const notice = <div role="dialog" aria-label="A notice" />;
  const corner = () => [...document.querySelector('[data-viewport-top-right-content]')?.children ?? []]
    .map(child => child.hasAttribute('data-viewport-notice') ? 'notice' : child.hasAttribute('data-quick-edit') ? 'Quick Edit' : child.tagName);
  const stage = (name: string) => act(() => { fireEvent.click(document.querySelector(`[data-harness-stage="${name}"]`)!); });
  frame({ notice });
  stage('finding');
  expect(screen.queryByRole('dialog', { name: 'A notice' })).toBeNull();
  stage('broken');  // a load the model did not survive: only its card
  expect(screen.queryByRole('dialog', { name: 'A notice' })).toBeNull();
  stage('idle');
  expect(corner()).toEqual(['notice', 'Quick Edit']);
  cleanup();
  // Shown small, the view has no Quick Edit and no strip, and the notice still asks.
  frame({ notice, appearance: { colorScheme: 'light', compact: true } });
  expect(corner()).toEqual(['notice']);
});

it('a host showing the view small gets the model alone: no tools, no view actions, no Quick Edit, no cube', () => {
  frame({ appearance: { colorScheme: 'light', compact: true } });
  expect(screen.queryByRole('group', { name: 'Interaction tools' })).toBeNull();
  expect(document.querySelector('[data-cad-tool-stack]')).toBeNull();
  expect(document.querySelector('[data-cad-tools-toggle]')).toBeNull();
  expect(barButtons()).toEqual([]);
  expect(document.querySelector('[data-quick-edit]')).toBeNull();
  expect(viewportProps.current.viewCube).toBe(false);
});

it("Projection, Display and Preview end the strip; Render is no mode of Display's, Projection a menu of its own, and Display's Grid leaves the drawing tools and kept tools in place", async () => {
  const user = userEvent.setup({ skipHover: true });
  const { remount } = frame();
  expect([strip(), barButtons()]).toEqual([['Select', 'Pencil', 'Shapes', 'Keep', 'Pose'], ['Projection', 'Display mode', 'Preview']]);
  // After the strip's rule.
  expect(document.querySelector('[data-cad-toolbar] [data-strip-rule] + [data-view-controls]')).not.toBeNull();
  const solid = render(<SolidModeIcon />).container.querySelector('svg')!;
  expect(displayButton().querySelector('svg')!.innerHTML).toEqual(solid.innerHTML);
  await openDisplay(user);
  // The modes the view offers (an edgeless one: Solid), then Grid: Render is Preview's, and the projection is Projection's.
  expect(within(displayMenu()!).getAllByRole('menuitemradio').map(item => [item.textContent, item.getAttribute('aria-checked')]))
    .toEqual([['Solid', 'true']]);
  expect(within(displayMenu()!).getAllByRole('menuitemcheckbox').map(item => [item.textContent, item.getAttribute('aria-checked')]))
    .toEqual([['Grid', 'false']]);
  expect(within(displayMenu()!).queryByRole('menuitemradio', { name: 'Perspective' })).toBeNull();
  await user.keyboard('{Escape}');
  await waitFor(() => expect(displayMenu()).toBeNull());
  expect(projectionButton().getAttribute('aria-label')).toBe('Projection: Orthographic');
  await user.click(projectionButton());
  expect(within(projectionMenu()!).getAllByRole('radio').map(item => [item.textContent, item.getAttribute('aria-checked')]))
    .toEqual([['Orthographic', 'true'], ['Perspective', 'false']]);
  // A choice closes it, and its tile says it.
  await user.click(within(projectionMenu()!).getByRole('radio', { name: 'Perspective', exact: true }));
  await waitFor(() => expect(projectionMenu()).toBeNull());
  expect(projectionButton().getAttribute('aria-label')).toBe('Projection: Perspective');
  await user.click(tool('Keep'));
  await user.click(tool('Pencil'));
  const stack = shown();
  const controls = screen.getByRole('toolbar', { name: 'Annotation controls' });
  await openDisplay(user);
  expect([shown(), screen.getByRole('toolbar', { name: 'Annotation controls' })]).toEqual([stack, controls]);
  // Grid toggles and leaves the menu open.
  await user.click(within(displayMenu()!).getByRole('menuitemcheckbox', { name: 'Grid' }));
  expect(within(displayMenu()!).getByRole('menuitemcheckbox', { name: 'Grid' }).getAttribute('aria-checked')).toBe('true');
  expect(displayButton().getAttribute('aria-label')).toBe('Display mode: Solid');
  await user.keyboard('{Escape}');
  await waitFor(() => expect(displayMenu()).toBeNull());
  expect(tool('Pencil').getAttribute('aria-pressed')).toBe('true');
  await openDisplay(user);
  await user.pointer({ keys: '[MouseLeft]', target: document.querySelector('[data-mock-viewport] canvas')! });
  await waitFor(() => expect(displayMenu()).toBeNull());
  expect(tool('Keep').getAttribute('aria-pressed')).toBe('true');
  await openDisplay(user);
  remount();
  expect([displayMenu(), displayLit()]).toEqual([null, false]);
});

// Preview, entered as its tile enters it: the view covered first, then Preview under the cover.
async function enterPreview(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Preview' }));
  await screen.findByRole('button', { name: 'Exit preview' });
}
const previewSettings = () => screen.queryByRole('region', { name: 'Preview settings' });

it("three surfaces: the strip, the sidebar's tiles and the stack share the light chrome surface; the sidebar's panel and Preview's settings, read while they are up, are between; Display's dropdown is the most opaque", async () => {
  const user = userEvent.setup({ skipHover: true });
  frame();
  expect(new Set([FLOATING_CHROME_SURFACE_CLASS, FILE_SIDEBAR_SURFACE_CLASS, FLOATING_SURFACE_CLASS]).size).toBe(3);
  const classes = (element: Element) => element.className.split(/\s+/);
  const has = (element: Element, surface: string) => surface.split(' ').every(name => classes(element).includes(name));
  expect(has(screen.getByRole('group', { name: 'Interaction tools' }), FLOATING_CHROME_SURFACE_CLASS)).toBe(true);
  expect(has(screen.getByRole('group', { name: 'File sidebar' }), FLOATING_CHROME_SURFACE_CLASS)).toBe(true);
  fireEvent.click(tool('Keep'));
  expect(has(panel('Kept controls')!, FLOATING_CHROME_SURFACE_CLASS)).toBe(true);
  // The sidebar's panel is read for as long as a section is open, and its sections have no surface of their own.
  expect(has(bar(), FILE_SIDEBAR_SURFACE_CLASS)).toBe(true);
  expect(has(panel('Harness tree')!, FLOATING_CHROME_SURFACE_CLASS)).toBe(false);
  // Display's menu is read while it is up: its text must not compete with the model.
  await openDisplay(user);
  expect(has(displayMenu()!, FLOATING_SURFACE_CLASS)).toBe(true);
  await user.keyboard('{Escape}');
  await enterPreview(user);
  await user.click(screen.getByRole('button', { name: 'Preview settings' }));
  expect(has(previewSettings()!, FILE_SIDEBAR_SURFACE_CLASS)).toBe(true);
});

it("Preview is in Render: the strip, the view's controls, the stack and the file sidebar step aside; its bar holds the file's name, its settings (Orbit and Render's) and the way out, which brings back the tool in hand and the file's own mode", async () => {
  const user = userEvent.setup({ skipHover: true });
  frame();
  await user.click(tool('Pose'));
  expect(tileNames()).toEqual(['Harness tree', 'Reference', 'Position']);
  await openDisplay(user);
  const editor = viewportProps.current;
  await enterPreview(user);
  const chrome = document.querySelector<HTMLElement>('[data-preview-chrome]')!;
  expect([chrome.hidden, chrome.hasAttribute('inert')]).toEqual([true, true]);
  expect(chrome.contains(document.querySelector('[data-cad-tool-stack]'))).toBe(true);
  expect(displayMenu()).toBeNull();
  // The strip goes with the tools view.
  expect([barButtons(), screen.queryByRole('group', { name: 'Interaction tools' })]).toEqual([[], null]);
  // The file sidebar is the tools view's alone: hidden, its sections kept mounted. (The harness has
  // no routine, so no playbar either.)
  expect([document.querySelector<HTMLElement>('[data-file-sidebar-room]')!.hidden, screen.queryByRole('group', { name: 'File sidebar' })]).toEqual([true, null]);
  expect(sections()).toEqual([]);
  expect(panel('Harness position')).not.toBeNull();
  expect(screen.queryByRole('toolbar', { name: 'Animation playback' })).toBeNull();
  // Its bar, along the view's top edge: the file's name, then its settings and the way out, an X.
  expect([previewBar()!.querySelector('[data-preview-name]')!.textContent, cornerButtons()]).toEqual(['panel.harness', ['Preview settings', 'Exit preview']]);
  expect(previewBar()!.className).toMatch(/\bh-9\b/);
  const corner = previewBar()!;
  expect(within(corner).getByRole('button', { name: 'Exit preview' }).querySelector('svg.lucide-x')).not.toBeNull();
  // Preview draws Render in a view of its own; the editor's viewport is asked for nothing new.
  expect([inPreview(), previewProps.current.renderMode, previewProps.current.projection, viewportProps.current.renderMode]).toEqual([true, true, 'perspective', false]);
  const unchanged = () => ['renderMode', 'renderConfiguration', 'displaySettings', 'quality', 'projection', 'themeSettings', 'appearance']
    .filter(key => viewportProps.current[key] !== editor[key]);
  expect(unchanged()).toEqual([]);
  // Its settings are closed as it opens; they are Orbit, then Preview's own look, the file's.
  expect(previewSettings()).toBeNull();
  await user.click(within(corner).getByRole('button', { name: 'Preview settings' }));
  expect(within(previewSettings()!).getAllByRole('heading').map(heading => heading.textContent)).toEqual(expect.arrayContaining(['Settings', 'Orbit']));
  const floor = () => within(previewSettings()!).getByRole('checkbox', { name: 'Floor', exact: true });
  expect(floor().getAttribute('aria-checked')).toBe('true');
  fireEvent.click(floor());
  expect([inPreview(), chrome.hidden]).toEqual([true, true]);
  await user.click(within(corner).getByRole('button', { name: 'Exit preview' }));
  expect(chrome.hidden).toBe(false);
  // Preview's view is gone, and the editor's is as it was: nothing Preview did reached it.
  expect([inPreview(), previewProps.current, viewportProps.current.suspended, unchanged()]).toEqual([false, null, false, []]);
  expect(barButtons()).toEqual(['Projection', 'Display mode', 'Preview']);
  // The tools view is in the file's own mode, as it always was.
  expect(displayButton().getAttribute('aria-label')).toBe('Display mode: Solid');
  // The tool in hand is as it was, its section's tile with it; Display, put away, stays shut.
  expect(tileNames()).toEqual(['Harness tree', 'Reference', 'Position']);
  expect(tool('Pose').getAttribute('aria-pressed')).toBe('true');
  expect([displayMenu(), displayLit()]).toEqual([null, false]);
  // What was set in Preview is the file's Render settings: the next visit has it.
  act(() => { fireEvent.click(document.querySelector('[data-harness-ask-preview]')!); });
  expect(inPreview()).toBe(true);
  await user.click(within(previewBar()!).getByRole('button', { name: 'Preview settings' }));
  expect(floor().getAttribute('aria-checked')).toBe('false');
  await user.click(within(previewBar()!).getByRole('button', { name: 'Exit preview' }));
  expect([displayMenu(), displayLit()]).toEqual([null, false]);
});

it("Preview is covered from the press until its picture has converged, then shows the finished picture", async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'requestAnimationFrame', 'cancelAnimationFrame'] });
  try {
    // The studio frame's progress, as the viewport reports it: samples drawn of those it accumulates.
    const picture = { sample: 0, samples: 16 };
    viewportHandle.current = { pictureProgress: () => ({ ...picture }) };
    frame();
    const cover = () => document.querySelector('[data-preview-cover]');
    const wait = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
    // The press is answered at once, before Preview itself is entered under it.
    expect(cover()?.textContent).toBe('Preparing preview…');
    await wait(100);
    expect([inPreview(), cover() !== null]).toEqual([true, true]);
    // In Render, and still converging well past the shortest cover: it holds.
    picture.sample = 9;
    await wait(2000);
    expect([previewProps.current.renderMode, cover() !== null]).toEqual([true, true]);
    // Every sample drawn: it lifts.
    picture.sample = 16;
    await wait(100);
    expect(cover()).toBeNull();
  } finally {
    vi.useRealTimers();
  }
});

it("Preview's bar is its name and its two controls alone; it and the playbar go together after two seconds without the pointer moving, come back as it moves or a tap lands, and stay while its settings are open", async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'requestAnimationFrame', 'cancelAnimationFrame'] });
  try {
    const played: string[] = [];
    const routine = { clips: [{ id: 'spin' }], clock: createAnimationClock(), onRelease() {}, onPlayToggle: () => played.push('toggle') };
    frame({ notice: <p>Host notice</p>, data: { previewAnimation: routine } });
    const wait = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });
    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
    await wait(100);
    expect(inPreview()).toBe(true);
    // The bar and the playbar, hidden or shown: always together.
    const playbar = () => document.querySelector<HTMLElement>('[data-preview-playbar]')!;
    const hidden = () => {
      const both = [previewBar()!.getAttribute('data-state') === 'hidden', playbar().getAttribute('data-state') === 'hidden'];
      expect(both[0]).toBe(both[1]);
      return both[0];
    };
    // The name as words, and the two controls: nothing else in it, and the host's notice is the tools view's.
    expect([previewBar()!.querySelector('[data-preview-name]')!.textContent, cornerButtons(), previewBar()!.querySelectorAll('a, input, [role=menu]').length])
      .toEqual(['panel.harness', ['Preview settings', 'Exit preview'], 0]);
    expect(screen.getByText('Host notice').closest('[data-preview-chrome]')!.hasAttribute('hidden')).toBe(true);
    expect(hidden()).toBe(false);
    // Two seconds counted from the frame that shows it (16 ms frames here), so a long frame is never idle time.
    await wait(1900);
    expect(hidden()).toBe(false);
    await wait(200);
    expect(hidden()).toBe(true);
    expect([previewBar()!.className, playbar().className]).toEqual([expect.stringMatching(/\bopacity-0\b/), expect.stringMatching(/\bopacity-0\b/)]);
    // Hidden, the playbar's routine is as it was: nothing played or stopped it.
    expect(played).toEqual([]);
    // The pointer moving anywhere over the view brings it back, and the count starts again.
    const view = document.querySelector('[data-slot="cad-file-view"]')!;
    fireEvent.pointerMove(view);
    expect(hidden()).toBe(false);
    await wait(2100);
    expect(hidden()).toBe(true);
    // A tap on the view, on a touch screen, brings it back too.
    fireEvent.pointerDown(view, { pointerType: 'touch' });
    expect(hidden()).toBe(false);
    // Its settings open, it stays for as long as they are.
    fireEvent.click(within(previewBar()!).getByRole('button', { name: 'Preview settings' }));
    expect(previewSettings()).not.toBeNull();
    await wait(5000);
    expect(hidden()).toBe(false);
    fireEvent.click(within(previewBar()!).getByRole('button', { name: 'Preview settings' }));
    await wait(2100);
    expect(hidden()).toBe(true);
    // The focus a press leaves on one of its controls does not hold it (jsdom's focus is no keyboard's) ...
    act(() => { within(previewBar()!).getByRole('button', { name: 'Exit preview' }).focus(); });
    await wait(2100);
    expect(hidden()).toBe(true);
    act(() => { within(previewBar()!).getByRole('button', { name: 'Exit preview' }).blur(); });
    // ... the keyboard's does: it brings it back, the playbar's as well as the bar's.
    const matches = Element.prototype.matches;
    override(Element.prototype, 'matches', { value(this: Element, selector: string) { return selector === ':focus-visible' ? this === document.activeElement : matches.call(this, selector); } });
    act(() => { within(previewBar()!).getByRole('button', { name: 'Exit preview' }).focus(); });
    expect(hidden()).toBe(false);
    await wait(5000);
    expect(hidden()).toBe(false);
    act(() => { within(previewBar()!).getByRole('button', { name: 'Exit preview' }).blur(); });
    await wait(2100);
    expect(hidden()).toBe(true);
    act(() => { within(playbar()).getByRole('button', { name: /^Play / }).focus(); });
    expect(hidden()).toBe(false);
    // The pointer resting on the playbar holds both.
    fireEvent.pointerOver(playbar());
    await wait(5000);
    expect(hidden()).toBe(false);
    fireEvent.click(within(previewBar()!).getByRole('button', { name: 'Exit preview' }));
    expect([inPreview(), previewBar()]).toEqual([false, null]);
  } finally {
    vi.useRealTimers();
  }
});

it("Preview settings is pressed while its panel is open and a second press closes it; the panel slides in and out from the view's right edge as the file sidebar's does", async () => {
  const user = userEvent.setup({ skipHover: true });
  frame();
  await enterPreview(user);
  const button = () => within(previewBar()!).getByRole('button', { name: 'Preview settings' });
  const panel = () => document.querySelector<HTMLElement>('[data-preview-panel]')!;
  // Closed: off the edge, out of reach and out of the accessibility tree; the button not pressed.
  expect([button().getAttribute('aria-pressed'), previewSettings(), panel().hasAttribute('inert'), panel().className]).toEqual(
    ['false', null, true, expect.stringContaining('translate-x-[calc(100%+1rem)]')]);
  // The file sidebar's own slide, on both.
  expect([panel().className, bar().className]).toEqual([expect.stringContaining(SIDEBAR_SLIDE_CLASS), expect.stringContaining(SIDEBAR_SLIDE_CLASS)]);
  await user.click(button());
  expect([button().getAttribute('aria-pressed'), previewSettings() !== null, panel().hasAttribute('data-open')]).toEqual(['true', true, true]);
  expect(panel().className).not.toContain('translate-x-[calc(100%+1rem)]');
  await user.click(button());
  expect([button().getAttribute('aria-pressed'), previewSettings(), panel().hasAttribute('data-open')]).toEqual(['false', null, false]);
  // Its own X closes it too, and the button is no longer pressed.
  await user.click(button());
  await user.click(within(previewSettings()!).getByRole('button', { name: 'Close preview settings' }));
  expect([button().getAttribute('aria-pressed'), previewSettings()]).toEqual(['false', null]);
  // Left open, Preview's exit takes it away; back in Preview it is closed.
  await user.click(button());
  await user.click(within(previewBar()!).getByRole('button', { name: 'Exit preview' }));
  await enterPreview(user);
  expect([button().getAttribute('aria-pressed'), previewSettings()]).toEqual(['false', null]);
});

it("under a FileViewer the navbar steps aside for Preview's bar, and is back as Preview closes", async () => {
  const user = userEvent.setup({ skipHover: true });
  const host = testHost({ links: viewerLinks({ version: '0.7.5' }), environment: { colorScheme: 'light', platform: 'darwin' },
    files: { id: 'one', stat: async (path: string) => ({ path, name: path.split('/').pop()!, kind: 'file', extension: 'harness', size: 1 }) } });
  render(<FileViewer file="/models/one.harness" host={host as any} renderers={[createHarnessRenderer({ preferences: tabSettings() })]}
    state={{}} onStateChange={() => {}} />);
  await screen.findByRole('button', { name: 'Preview' });
  const navbar = () => document.querySelector('[data-viewer-navbar]');
  expect([navbar() !== null, previewBar()]).toEqual([true, null]);
  await enterPreview(user);
  expect([navbar(), previewBar()!.querySelector('[data-preview-name]')!.textContent]).toEqual([null, 'one.harness']);
  await user.click(within(previewBar()!).getByRole('button', { name: 'Exit preview' }));
  expect([navbar() !== null, previewBar()]).toEqual([true, null]);
});

// Preview's Orbit, in its settings: off at every entry, its speed a row of Orbit's there while it is on.
function previewOrbit(user: ReturnType<typeof userEvent.setup>) {
  const orbit = () => within(previewSettings()!).getByRole('checkbox', { name: 'Orbit' });
  const speed = () => within(previewSettings()!).getByRole('combobox', { name: 'Orbit speed' }).textContent;
  return {
    orbit,
    enter: async () => { await enterPreview(user); await user.click(screen.getByRole('button', { name: 'Preview settings' })); },
    speedOnceOn: async () => { if (orbit().getAttribute('aria-checked') !== 'true') await user.click(orbit()); return speed(); },
    async choose(value: string) {
      await user.click(within(previewSettings()!).getByRole('combobox', { name: 'Orbit speed' }));
      await user.click(screen.getByRole('option', { name: value }));
    }
  };
}

it("Preview opens still: Orbit, in its settings, turns the camera, and a speed chosen is the file's view's, never Orbit on or off, kept between visits", async () => {
  const user = userEvent.setup({ skipHover: true });
  const { orbit, enter, speedOnceOn, choose } = previewOrbit(user);
  const states: any[] = [];
  const view = frame({ onStateChange: state => states.push(state) });
  await enter();
  expect([orbit().getAttribute('aria-checked'), previewProps.current.orbit, within(previewSettings()!).queryByRole('combobox', { name: 'Orbit speed' })]).toEqual(['false', false, null]);
  await user.click(orbit());
  expect([orbit().getAttribute('aria-checked'), previewProps.current.orbit]).toEqual(['true', true]);
  // A fresh file orbits at 1×; 2× chosen.
  expect(await speedOnceOn()).toBe('1×');
  await choose('2×');
  expect(previewProps.current.orbitSpeed).toBe(2);
  // Leaving and coming back: still again, at 2×.
  await user.click(screen.getByRole('button', { name: 'Exit preview' }));
  await enterPreview(user);
  expect([previewProps.current.orbit, previewProps.current.orbitSpeed]).toEqual([false, 2]);
  // The file's view holds the speed, and no Orbit on or off.
  view.unmount();
  expect(states.at(-1).playback).toEqual({ orbitSpeed: 2, autoplay: false });
});

it("Orbit's speed comes back with the file's view", async () => {
  const user = userEvent.setup({ skipHover: true });
  frame({ state: writeFileView({ playback: { orbitSpeed: 2 } }) });
  await enterPreview(user);
  expect([previewProps.current.orbit, previewProps.current.orbitSpeed]).toEqual([false, 2]);
});

it('Escape puts the tool in hand down and takes Select up, what it set kept', async () => {
  const user = userEvent.setup({ skipHover: true });
  frame({ viewer: true });
  await user.click(tool('Pencil'));
  expect(tool('Pencil').getAttribute('aria-pressed')).toBe('true');
  act(() => { document.querySelector<HTMLElement>('[data-slot="cad-file-view"]')!.focus(); });
  await user.keyboard('{Escape}');
  expect([tool('Pencil').getAttribute('aria-pressed'), tool('Select').getAttribute('aria-pressed')]).toEqual(['false', 'true']);
});

it('Escape closes the Display menu and gives its tile the focus back, the tool in hand kept', async () => {
  const user = userEvent.setup({ skipHover: true });
  frame();
  await openDisplay(user);
  await user.keyboard('{Escape}');
  await waitFor(() => expect([displayMenu(), displayLit()]).toEqual([null, false]));
  await waitFor(() => expect(document.activeElement).toBe(displayButton()));
  expect(tool('Select').getAttribute('aria-pressed')).toBe('true');
});

it("what a person uses is counted for the host by name: a tool taken up and how long it was up, Display's Grid, Preview and its seconds, never the tool the file opened in or its return from Preview", async () => {
  let now = 5_000_000;
  vi.spyOn(Date, 'now').mockImplementation(() => now);
  const reports: { control: string; count: number; seconds: number }[][] = [];
  const user = userEvent.setup({ skipHover: true });
  const view = frame({ usage: counts => reports.push(counts) });
  fireEvent.click(tool('Pencil'));
  now += 5_000;
  fireEvent.click(tool('Select'));
  await openDisplay(user);
  await user.click(within(displayMenu()!).getByRole('menuitemcheckbox', { name: 'Grid' }));
  await enterPreview(user);
  // Preview's bar: its settings opened (a use, no seconds), then its way out.
  await user.click(within(previewBar()!).getByRole('button', { name: 'Preview settings', exact: true }));
  now += 3_000;
  await user.click(screen.getByRole('button', { name: 'Exit preview' }));
  expect(reports).toEqual([]); // said at most every minute, or as the view goes
  view.unmount();
  const said = Object.fromEntries(reports.flat().map(({ control, ...counts }) => [control, counts]));
  expect(said).toEqual({ pencil: { count: 1, seconds: 5 }, display_grid: { count: 1, seconds: 0 }, preview: { count: 1, seconds: 3 },
    preview_settings: { count: 1, seconds: 0 },
    // Select is counted once: the person took it up again; the file opened in it, and Preview gave it back.
    select: { count: 1, seconds: 0 } });
  vi.restoreAllMocks();
});
