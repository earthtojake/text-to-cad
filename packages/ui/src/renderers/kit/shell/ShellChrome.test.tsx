import React, { forwardRef } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

// The shell's chrome — the strip, the tool stack, the view's actions, Display's dropdown and preview —
// under the smallest renderer that mounts it (`renderers/shell-harness`), with the WebGL viewport
// replaced by an empty box: nothing asserted here is drawn by it. What the viewport is handed is
// recorded, so a test can read what the shell asked of it.
const viewportProps: { current: any } = { current: null };
vi.mock('../../../../dist/renderers/kit/shell/ShellViewport.js', () => ({
  default: forwardRef(function MockViewport(props: any, _ref) {
    viewportProps.current = props;
    return <div data-mock-viewport=""><canvas />{typeof props.children === 'function'
      ? props.children({ runtimeRef: { current: null }, hostRef: { current: null }, mountRef: { current: null }, viewerReadyTick: 0, commitScene: () => true })
      : null}</div>;
  }),
}));
import HarnessRenderer from '../../../../dist/renderers/shell-harness/HarnessRenderer.js';
import { createHarnessRenderer } from '../../../../dist/renderers/shell-harness/index.js';
import { FileViewer } from '../../../../dist/file-viewer/index.js';
import { viewerLinks } from '../../../../dist/file-viewer/navigation/links.js';
import { ViewerHostContext } from '../../../../dist/host/context.js';
import { testHost } from '../../../../dist/host/testing/host.js';
import { ViewerMobileContext } from '../../../../dist/file-viewer/responsive.js';
import { TOOL_PANEL_REFERENCE_HEIGHT, TOOL_PANEL_WIDTH } from '../../../../dist/renderers/kit/tools/toolStackLayout.js';
import { FLOATING_CHROME_SURFACE_CLASS, FLOATING_SURFACE_CLASS } from '../../../../dist/lib/floatingSurface.js';
import { PerspectiveProjectionIcon } from '../../../../dist/renderers/kit/camera/ProjectionModeIcons.js';

// jsdom lays nothing out, so the few sizes the stack reads are given: a viewer 1280 × 800 whose
// stack column (under the strip) is 600px tall, and each panel as big as its own style says.
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
  override(HTMLElement.prototype, 'clientHeight', { get(this: HTMLElement) { return this.hasAttribute('data-cad-tool-stack') ? STACK_HEIGHT : 0; } });
  const rect = Element.prototype.getBoundingClientRect;
  override(Element.prototype, 'getBoundingClientRect', { value(this: HTMLElement) {
    if (this.hasAttribute('data-cad-scene-backdrop')) return DOMRect.fromRect({ x: 0, y: 0, ...VIEWER });
    if (this.matches('section[data-tool-panel]')) return DOMRect.fromRect({ x: 8, y: 48, width: parseFloat(this.style.width) || 0, height: parseFloat(this.style.maxHeight) || 100 });
    return rect.call(this);
  } });
  for (const name of ['setPointerCapture', 'releasePointerCapture']) override(Element.prototype, name, { value() {} });
  override(Element.prototype, 'hasPointerCapture', { value: () => true });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); while (restores.length) restores.pop()!(); viewportProps.current = null; });

/** The tab's settings as a host hands them over, counting every write. */
function tabSettings(initial: object = {}) {
  let settings: any = { toolStack: { panels: {}, collapsed: {}, closed: {} }, ...initial };
  const listeners = new Set<() => void>();
  const store = { writes: 0, getSnapshot: () => settings, subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    update(patch: object) { store.writes += 1; settings = { ...settings, ...patch }; listeners.forEach(listener => listener()); } };
  return store;
}
type Settings = ReturnType<typeof tabSettings>;
// The navbar FileViewer hands a renderer: the box at its right end the view's controls go in.
function navbarSlot() {
  const slot = document.createElement('div');
  slot.setAttribute('data-test-navbar', '');
  document.body.append(slot);
  return slot;
}
afterEach(() => document.querySelectorAll('[data-test-navbar]').forEach(slot => slot.remove()));
function frame({ name = 'panel.harness', preferences = tabSettings(), state = undefined as unknown, mobile = false, onStateChange = (_: unknown) => {}, onFullscreenChange = vi.fn(), appearance = { colorScheme: 'light' } as object, notice = null as React.ReactNode, features = undefined as object | undefined } = {}) {
  const props = { source: { id: 'one' }, file: { path: `/models/${name}`, name, kind: 'file' }, document: null, notice, features,
    navbarSlot: navbarSlot(), onFullscreenChange, onReady() {}, onOpenFile() {}, appearance, state, onStateChange, reload() {}, data: { services: { preferences } } };
  const element = () => <ViewerHostContext.Provider value={testHost()}><ViewerMobileContext.Provider value={mobile}>
    <HarnessRenderer {...(props as any)} /></ViewerMobileContext.Provider></ViewerHostContext.Provider>;
  const view = render(element());
  return { ...view, preferences, remount: () => { view.unmount(); return render(element()); } };
}
const panel = (label: string) => document.querySelector<HTMLElement>(`section[data-tool-panel][aria-label="${label}"]`);
const shown = () => [...document.querySelectorAll<HTMLElement>('[data-cad-tool-stack] section[data-tool-panel]')].filter(node => !node.hidden).map(node => node.getAttribute('aria-label'));
const handles = (label: string) => [...panel(label)!.querySelectorAll('[role=separator]')].map(handle => handle.getAttribute('aria-label'));
const width = (label: string) => parseFloat(panel(label)!.style.width);
const layout = (preferences: Settings) => preferences.getSnapshot().toolStack;
const tool = (name: string) => within(screen.getByRole('group', { name: 'Interaction tools' })).getByRole('button', { name });
function drag(handle: Element, [dx, dy]: [number, number], { release = true } = {}) {
  fireEvent.pointerDown(handle, { button: 0, pointerId: 1, clientX: 100, clientY: 100 });
  fireEvent.pointerMove(handle, { pointerId: 1, clientX: 100 + dx, clientY: 100 + dy });
  if (release) fireEvent.pointerUp(handle, { pointerId: 1, clientX: 100 + dx, clientY: 100 + dy });
}

it('the chrome is inset from the viewer, every panel opens one width, the tree at half the stack and the Reference shorter, and nothing is stored until a person sizes one', () => {
  const { preferences } = frame();
  // The strip and the stack under it, 8px in from the viewer's top and left, stopping 8px above the
  // cube in the bottom-left corner (itself 8px off the bottom).
  expect(document.querySelector<HTMLElement>('[data-cad-tool-groups]')!.style).toMatchObject({ top: '8px', left: '8px', bottom: 'calc(16px + 6rem)' });
  expect(shown()).toEqual(['Harness tree', 'Harness reference']);
  expect(TOOL_PANEL_WIDTH).toBe(164);
  expect([width('Harness tree'), width('Harness reference')]).toEqual([TOOL_PANEL_WIDTH, TOOL_PANEL_WIDTH]);
  expect(panel('Harness tree')!.style.maxHeight).toBe(`${STACK_HEIGHT / 2}px`);
  expect(TOOL_PANEL_REFERENCE_HEIGHT).toBe(144);
  expect(panel('Harness reference')!.style.maxHeight).toBe(`${TOOL_PANEL_REFERENCE_HEIGHT}px`);
  expect(layout(preferences)).toEqual({ panels: {}, collapsed: {}, closed: {} });
  // Two kinds of panel: the tree and the Reference are each the person's to size, by one grip in
  // their bottom-right corner (Quick Edit's, drawn inside the panel); a kept effect is fixed, at the
  // one width, with none.
  fireEvent.click(tool('Keep'));
  expect(shown()).toEqual(['Harness tree', 'Harness reference', 'Kept controls']);
  expect([handles('Harness tree'), handles('Harness reference'), handles('Kept controls')])
    .toEqual([['Resize harness tree'], ['Resize harness reference'], []]);
  for (const label of ['Harness tree', 'Harness reference']) {
    const grip = panel(label)!.querySelector<HTMLElement>('[role=separator]')!;
    expect([grip.getAttribute('data-resize-grip'), grip.parentElement]).toEqual(['bottom-right', panel(label)]);
    expect(grip.className).toMatch(/\babsolute bottom-0\b.*\bright-0 cursor-nwse-resize\b/);
    expect(grip.querySelector('svg path')!.getAttribute('d')).toBe('M7 2L2 7M7 5L5 7');
  }
  expect(width('Kept controls')).toBe(TOOL_PANEL_WIDTH);
  expect(tool('Keep').getAttribute('aria-pressed')).toBe('true');
  expect(preferences.writes).toBe(0);
});

it("each resizable panel is sized by its corner alone, apart from every other: width and cap in one write when the pointer lets go, the keyboard by 16px and Home and End to the bounds, and a remount opens at what was left", () => {
  const { preferences, remount } = frame();
  fireEvent.click(tool('Keep'));
  const treeCorner = screen.getByRole('separator', { name: 'Resize harness tree' });
  drag(treeCorner, [100, -100], { release: false });
  // Mid-drag: the tree follows the corner, and nothing else moves; nothing is written yet.
  expect([width('Harness tree'), panel('Harness tree')!.style.maxHeight]).toEqual([TOOL_PANEL_WIDTH + 100, `${STACK_HEIGHT / 2 - 100}px`]);
  expect(treeCorner.hasAttribute('data-dragging')).toBe(true);
  expect([width('Harness reference'), width('Kept controls')]).toEqual([TOOL_PANEL_WIDTH, TOOL_PANEL_WIDTH]);
  expect(preferences.writes).toBe(0);
  fireEvent.pointerUp(treeCorner, { pointerId: 1, clientX: 200, clientY: 0 });
  expect(preferences.writes).toBe(1);
  expect(layout(preferences).panels).toEqual({ tree: { width: TOOL_PANEL_WIDTH + 100, height: STACK_HEIGHT / 2 - 100 } });
  // The Reference, by its own corner: its size, and the tree's as it was.
  drag(screen.getByRole('separator', { name: 'Resize harness reference' }), [40, -60]);
  expect(preferences.writes).toBe(2);
  expect(layout(preferences).panels).toEqual({ tree: { width: TOOL_PANEL_WIDTH + 100, height: STACK_HEIGHT / 2 - 100 },
    reference: { width: TOOL_PANEL_WIDTH + 40, height: TOOL_PANEL_REFERENCE_HEIGHT - 60 } });
  expect([width('Harness tree'), width('Harness reference'), panel('Harness reference')!.style.maxHeight])
    .toEqual([TOOL_PANEL_WIDTH + 100, TOOL_PANEL_WIDTH + 40, `${TOOL_PANEL_REFERENCE_HEIGHT - 60}px`]);
  // From the keyboard, one axis a key: Left/Right the width, Up/Down the cap; Home and End both, to their bounds.
  fireEvent.keyDown(treeCorner, { key: 'ArrowLeft' });
  fireEvent.keyDown(treeCorner, { key: 'ArrowDown' });
  expect(layout(preferences).panels.tree).toEqual({ width: TOOL_PANEL_WIDTH + 84, height: STACK_HEIGHT / 2 - 84 });
  fireEvent.keyDown(treeCorner, { key: 'Home' });
  expect(layout(preferences).panels.tree).toEqual({ width: TOOL_PANEL_WIDTH, height: 64 });
  fireEvent.keyDown(treeCorner, { key: 'End' });
  expect(layout(preferences).panels.tree).toEqual({ width: VIEWER.width / 2, height: STACK_HEIGHT });
  expect(layout(preferences).panels.reference).toEqual({ width: TOOL_PANEL_WIDTH + 40, height: TOOL_PANEL_REFERENCE_HEIGHT - 60 });
  remount();
  expect([width('Harness tree'), panel('Harness tree')!.style.maxHeight]).toEqual([VIEWER.width / 2, `${STACK_HEIGHT}px`]);
  expect([width('Harness reference'), panel('Harness reference')!.style.maxHeight]).toEqual([TOOL_PANEL_WIDTH + 40, `${TOOL_PANEL_REFERENCE_HEIGHT - 60}px`]);

  // Position, by its corner too: its width and height in one write, the others as they were.
  preferences.update({ toolStack: { panels: {}, collapsed: {}, closed: {} } });
  fireEvent.click(tool('Pose'));
  expect(handles('Harness position')).toEqual(['Resize harness position']);
  const writes = preferences.writes;
  drag(screen.getByRole('separator', { name: 'Resize harness position' }), [60, -50]);
  expect(preferences.writes).toBe(writes + 1);
  expect(layout(preferences).panels).toEqual({ position: { width: TOOL_PANEL_WIDTH + 60, height: STACK_HEIGHT / 2 - 50 } });
  expect([width('Harness tree'), panel('Harness tree')!.style.maxHeight]).toEqual([TOOL_PANEL_WIDTH, `${STACK_HEIGHT / 2}px`]);
  // Reset puts every size back.
  act(() => preferences.update({ toolStack: { panels: {}, collapsed: {}, closed: {} } }));
  expect([width('Harness tree'), width('Harness reference'), width('Harness position'), panel('Harness tree')!.style.maxHeight])
    .toEqual([TOOL_PANEL_WIDTH, TOOL_PANEL_WIDTH, TOOL_PANEL_WIDTH, `${STACK_HEIGHT / 2}px`]);
});

it("the tree's X closes it, kept mounted, and marks Select; Select pressed while it is the tool opens it again, and from another tool only takes Select up; closed is kept across a remount", () => {
  const { preferences, remount } = frame();
  const tree = panel('Harness tree')!;
  const mark = () => tool('Select').querySelector('[data-tool-panel-closed]');
  // An X at the filter row's end, and no chevron: the tree does not fold.
  expect(within(tree).queryByRole('button', { name: /^(?:Collapse|Expand) harness tree$/ })).toBeNull();
  expect(tool('Select').getAttribute('aria-pressed')).toBe('true');
  expect(mark()).toBeNull();
  fireEvent.click(within(tree).getByRole('button', { name: 'Close harness tree' }));
  expect(shown()).toEqual(['Harness reference']);
  expect([tree.hidden, tree.hasAttribute('data-closed')]).toEqual([true, true]);
  expect(within(tree).getByText('Row 1')).toBeTruthy();
  expect([preferences.writes, layout(preferences).closed]).toEqual([1, { tree: true }]);
  // Select carries the corner mark, and says what it marks; no other tool does.
  expect(mark()).not.toBeNull();
  expect(tool('Select').getAttribute('aria-description')).toBe('Harness tree closed');
  expect([tool('Draw'), tool('Keep'), tool('Pose')].map(button => button.querySelector('[data-tool-panel-closed]'))).toEqual([null, null, null]);
  // From another tool, Select is only taken up: the tree stays closed, the mark with it.
  fireEvent.click(tool('Draw'));
  expect(tool('Draw').getAttribute('aria-pressed')).toBe('true');
  fireEvent.click(tool('Select'));
  expect([tool('Select').getAttribute('aria-pressed'), tool('Draw').getAttribute('aria-pressed')]).toEqual(['true', 'false']);
  expect(shown()).toEqual(['Harness reference']);
  expect(mark()).not.toBeNull();
  // Closed is the person's, across a remount.
  remount();
  expect(shown()).toEqual(['Harness reference']);
  expect(mark()).not.toBeNull();
  // Pressed while it is the tool, Select opens the tree as it was, and the mark goes: opening is
  // the person's choice too, kept as made.
  fireEvent.click(tool('Select'));
  expect(shown()).toEqual(['Harness tree', 'Harness reference']);
  expect([mark(), tool('Select').getAttribute('aria-description')]).toEqual([null, null]);
  expect(layout(preferences).closed).toEqual({ tree: false });
  expect(tool('Select').getAttribute('aria-pressed')).toBe('true');
  // Pressed again with the tree open, it changes nothing.
  const writes = preferences.writes;
  fireEvent.click(tool('Select'));
  expect([shown(), preferences.writes]).toEqual([['Harness tree', 'Harness reference'], writes]);
});

it('a heading panel folds to its heading by its chevron, its content kept mounted and its grip gone; which panels are folded is kept across a remount', () => {
  const { preferences, remount } = frame();
  const reference = panel('Harness reference')!;
  const fold = within(reference).getByRole('button', { name: 'Collapse harness reference' });
  expect([fold.getAttribute('aria-expanded'), fold.querySelector('[data-chevron]')!.getAttribute('data-chevron')]).toEqual(['true', 'up']);
  fireEvent.click(fold);
  const unfold = within(reference).getByRole('button', { name: 'Expand harness reference' });
  expect([unfold.getAttribute('aria-expanded'), unfold.querySelector('[data-chevron]')!.getAttribute('data-chevron')]).toEqual(['false', 'down']);
  expect(reference.hasAttribute('data-collapsed')).toBe(true);
  expect(within(reference).getByText('Fact 1')).toBeTruthy();
  expect(reference.querySelector('[data-tool-panel-body]')!.closest('[hidden]')).not.toBeNull();
  expect(layout(preferences).collapsed).toEqual({ reference: true });
  // Folded, there is no height to set: no grip.
  expect(handles('Harness reference')).toEqual([]);
  remount();
  expect(within(panel('Harness reference')!).getByRole('button', { name: 'Expand harness reference' })).toBeTruthy();
  fireEvent.click(within(panel('Harness reference')!).getByRole('button', { name: 'Expand harness reference' }));
  expect(layout(preferences).collapsed).toEqual({});
  expect(handles('Harness reference')).toEqual(['Resize harness reference']);
});

it("on a phone the tree starts closed, with Select marked and nothing stored; opened, its cap is the whole column", () => {
  const { preferences } = frame({ mobile: true });
  expect(shown()).toEqual(['Harness reference']);
  expect(tool('Select').querySelector('[data-tool-panel-closed]')).not.toBeNull();
  expect(layout(preferences)).toEqual({ panels: {}, collapsed: {}, closed: {} });
  fireEvent.click(tool('Select'));
  expect(shown()).toEqual(['Harness tree', 'Harness reference']);
  expect(tool('Select').querySelector('[data-tool-panel-closed]')).toBeNull();
  expect(panel('Harness tree')!.style.maxHeight).toBe(`${STACK_HEIGHT}px`);
  expect(layout(preferences).closed).toEqual({ tree: false });
  fireEvent.click(within(panel('Harness tree')!).getByRole('button', { name: 'Close harness tree' }));
  expect([shown(), layout(preferences).closed]).toEqual([['Harness reference'], { tree: true }]);
});

it("a single part's tree starts closed, Select marked, and an assembly's open; once a person closes or opens it, their choice holds in every file", () => {
  const preferences = tabSettings();
  const mark = () => tool('Select').querySelector('[data-tool-panel-closed]');
  // `panel-part.harness` is a single part's, `panel.harness` an assembly's.
  const part = frame({ name: 'panel-part.harness', preferences });
  expect([shown(), Boolean(mark())]).toEqual([['Harness reference'], true]);
  part.unmount();
  const assembly = frame({ name: 'panel.harness', preferences });
  expect([shown(), Boolean(mark())]).toEqual([['Harness tree', 'Harness reference'], false]);
  expect(preferences.writes).toBe(0);
  // Closed in the assembly: closed in a part, and in the next assembly too.
  fireEvent.click(within(panel('Harness tree')!).getByRole('button', { name: 'Close harness tree' }));
  expect(layout(preferences).closed).toEqual({ tree: true });
  assembly.unmount();
  const closedPart = frame({ name: 'panel-part.harness', preferences });
  expect([shown(), Boolean(mark())]).toEqual([['Harness reference'], true]);
  // Opened in a part: open in the next part, and in an assembly.
  fireEvent.click(tool('Select'));
  expect(layout(preferences).closed).toEqual({ tree: false });
  closedPart.unmount();
  const openedPart = frame({ name: 'panel-part.harness', preferences });
  expect([shown(), Boolean(mark())]).toEqual([['Harness tree', 'Harness reference'], false]);
  openedPart.unmount();
  frame({ name: 'panel.harness', preferences });
  expect([shown(), Boolean(mark())]).toEqual([['Harness tree', 'Harness reference'], false]);
});

const displayPopover = () => document.querySelector<HTMLElement>('[data-display-popover]');
// The view's controls, in the navbar's box for them.
const barButtons = () => [...document.querySelector('[data-test-navbar]')?.querySelectorAll('button') ?? []].map(button => button.getAttribute('aria-label'));
// Preview's own, at the view's top-right.
const cornerButtons = () => [...document.querySelector('[data-preview-corner]')?.querySelectorAll('button') ?? []].map(button => button.getAttribute('aria-label'));
const strip = () => [...screen.getByRole('group', { name: 'Interaction tools' }).querySelectorAll('button')].map(button => button.getAttribute('aria-label'));

it('while the model loads the viewer shows none of its own chrome, and all of it returns with the model', () => {
  frame();
  const stage = (name: string) => act(() => { fireEvent.click(document.querySelector(`[data-harness-stage="${name}"]`)!); });
  expect(screen.getByRole('group', { name: 'Interaction tools' })).toBeTruthy();
  expect(barButtons()).toEqual(['Display', 'Preview']);
  stage('finding');
  expect(screen.queryByRole('group', { name: 'Interaction tools' })).toBeNull();
  expect(document.querySelector('[data-cad-tool-stack]')).toBeNull();
  expect(barButtons()).toEqual([]);
  expect(viewportProps.current.isLoading).toBe(true);
  stage('idle');
  expect(screen.getByRole('group', { name: 'Interaction tools' })).toBeTruthy();
  expect(barButtons()).toEqual(['Display', 'Preview']);
  // With nothing to work on yet, the strip is idle together, and so are Display and Preview.
  stage('unready');
  expect(strip()).toEqual(['Select', 'Draw', 'Keep', 'Pose']);
  const idle = (name: string) => (['Display', 'Preview'].includes(name) ? screen.getByRole('button', { name }) : tool(name)).hasAttribute('disabled');
  expect(['Select', 'Draw', 'Display', 'Preview'].map(idle)).toEqual([true, true, true, true]);
  stage('idle');
  expect(['Select', 'Draw', 'Display', 'Preview'].map(idle)).toEqual([false, false, false, false]);
});

it("Display and Preview are a 3D view's, as its renderer declares: a view that does not declare it has neither, not disabled ones, and a request for Preview leaves it as it is", () => {
  const onFullscreenChange = vi.fn();
  // Preview asked for from outside the navbar, as a link or a host request would.
  const ask = () => act(() => { fireEvent.click(document.querySelector('[data-harness-ask-preview]')!); });
  // A 3D view (the harness's, declared `previewable`): Display and Preview in the navbar, and a request enters Preview.
  frame({ onFullscreenChange });
  expect(barButtons()).toEqual(['Display', 'Preview']);
  ask();
  expect([viewportProps.current.previewMode, onFullscreenChange.mock.calls]).toEqual([true, [[true]]]);
  cleanup();
  onFullscreenChange.mockClear();
  // A view whose renderer does not declare it (`flat.harness`, a 2D view's stand-in): nothing in the
  // navbar, and the same request leaves the normal view on screen, its tools up.
  frame({ name: 'flat.harness', onFullscreenChange });
  expect(barButtons()).toEqual([]);
  for (const name of ['Display', 'Preview']) expect(screen.queryByRole('button', { name })).toBeNull();
  ask();
  expect([viewportProps.current.previewMode, onFullscreenChange.mock.calls]).toEqual([false, []]);
  expect(document.querySelector('[data-preview-chrome]')!.hasAttribute('inert')).toBe(false);
  expect(strip()).toEqual(['Draw']);
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
  expect(barButtons()).toEqual(['Display', 'Preview']);
  expect(viewportProps.current.viewCube).toBe(true);
});

it("a dismissed alert's own icon, at the navbar's right, brings its card back; it goes with the card's return, and when the alert clears", async () => {
  // The harness under the real FileViewer, whose navbar's right holds nothing of its own: only the
  // view's controls, last, in the box the navbar keeps for them.
  const host = testHost({ links: viewerLinks({ version: '0.7.5' }), environment: { colorScheme: 'light', platform: 'darwin' },
    files: { id: 'one', stat: async (path: string) => ({ path, name: path.split('/').pop()!, kind: 'file', extension: 'harness', size: 1 }) } });
  render(<FileViewer file="/models/one.harness" host={host as any} renderers={[createHarnessRenderer({ preferences: tabSettings() })]}
    state={{}} onStateChange={() => {}} />);
  await screen.findByRole('button', { name: 'Preview' });
  const right = () => [...document.querySelector('[data-viewer-navbar] > div')!.querySelectorAll('a, button')].map(node => node.getAttribute('aria-label'));
  const card = () => screen.queryByRole('alert');
  const stage = (name: string) => act(() => { fireEvent.click(document.querySelector(`[data-harness-stage="${name}"]`)!); });
  const view = ['Display', 'Preview'];
  expect(right()).toEqual(view);
  expect([...document.querySelector('[data-viewer-navbar] [data-view-controls]')!.querySelectorAll('button')].map(node => node.getAttribute('aria-label'))).toEqual(view);
  stage('failed');
  expect(card()!.textContent).toContain('Harness update failed');
  expect(right()).toEqual(view, 'the card is up: no icon');
  // Put away: the card's own icon, in the error's colour, named after the alert, at the right, before the view's controls.
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
  const corner = () => [...document.querySelector('[data-viewport-top-right]')?.children ?? []]
    .map(child => child.hasAttribute('data-viewport-notice') ? 'notice' : child.hasAttribute('data-quick-edit') ? 'Quick Edit' : child.tagName);
  const stage = (name: string) => act(() => { fireEvent.click(document.querySelector(`[data-harness-stage="${name}"]`)!); });
  // On a narrow view the column starts below the tool strip's row, so the strip stays in reach.
  const clearsStrip = () => document.querySelector('[data-viewport-top-right]')!.className.includes('@max-md/cad-viewport:top-');
  frame({ notice });
  stage('finding');
  expect(screen.queryByRole('dialog', { name: 'A notice' })).toBeNull();
  stage('broken');  // a load the model did not survive: only its card
  expect(screen.queryByRole('dialog', { name: 'A notice' })).toBeNull();
  stage('idle');
  expect(corner()).toEqual(['notice', 'Quick Edit']);
  expect(clearsStrip()).toBe(true);
  cleanup();
  // Shown small, the view has no Quick Edit and no strip, and the notice still asks.
  frame({ notice, appearance: { colorScheme: 'light', compact: true } });
  expect(corner()).toEqual(['notice']);
  expect(clearsStrip()).toBe(false);
});

it("Quick edit turned off in Settings takes Quick Edit away: nothing a pick or a sketch could open, and the host's notice alone at the top-right", () => {
  const notice = <div role="dialog" aria-label="A notice" />;
  const corner = () => [...document.querySelector('[data-viewport-top-right]')?.children ?? []]
    .map(child => child.hasAttribute('data-viewport-notice') ? 'notice' : child.hasAttribute('data-quick-edit') ? 'Quick Edit' : child.tagName);
  // On, as it starts and as a host that says nothing leaves it: Quick Edit waits under the notice.
  frame({ notice, features: { quickEdit: true } });
  expect(corner()).toEqual(['notice', 'Quick Edit']);
  cleanup();
  // Off: no Quick Edit at all, whatever is picked or drawn; the tools are as they were.
  frame({ notice, features: { quickEdit: false } });
  expect(corner()).toEqual(['notice']);
  expect(document.querySelector('[data-quick-edit]')).toBeNull();
  expect(strip()).toEqual(['Select', 'Draw', 'Keep', 'Pose']);
  cleanup();
  frame({ features: { quickEdit: false } });
  expect(document.querySelector('[data-viewport-top-right]')).toBeNull();
});

it('a host showing the view small gets the model alone: no tools, no view actions, no Quick Edit, no cube', () => {
  frame({ appearance: { colorScheme: 'light', compact: true } });
  expect(screen.queryByRole('group', { name: 'Interaction tools' })).toBeNull();
  expect(document.querySelector('[data-cad-tool-stack]')).toBeNull();
  expect(barButtons()).toEqual([]);
  expect(document.querySelector('[data-quick-edit]')).toBeNull();
  expect(viewportProps.current.viewCube).toBe(false);
});

it("Display is the dropdown at the navbar's right end, before Preview, the perspective box: opened over Draw it leaves Draw in hand with its panel, and the stack as it was", async () => {
  const user = userEvent.setup();
  const { remount } = frame();
  // The view's controls in the navbar, Display then Preview; nothing of Display on the strip.
  expect(barButtons()).toEqual(['Display', 'Preview']);
  expect(strip()).toEqual(['Select', 'Draw', 'Keep', 'Pose']);
  const display = screen.getByRole('button', { name: 'Display' });
  // Its icon is the perspective box, the drawing the Projection menu shows for Perspective.
  const box = render(<PerspectiveProjectionIcon />).container.querySelector('svg')!;
  expect(display.querySelector('svg')!.innerHTML).toBe(box.innerHTML);
  await user.click(tool('Keep'));
  await user.click(tool('Draw'));
  expect(tool('Draw').getAttribute('aria-pressed')).toBe('true');
  // Draw's panel leads the stack, and has nothing to fold.
  const stack = shown();
  expect(stack).toEqual(['Drawing controls', 'Harness tree', 'Harness reference', 'Kept controls']);
  expect(within(panel('Drawing controls')!).queryByRole('button', { name: /^(?:Collapse|Expand) / })).toBeNull();
  await user.click(display);
  expect(displayPopover()!.getAttribute('aria-label')).toBe('Display settings');
  expect(display.getAttribute('aria-pressed')).toBe('true');
  // Nothing joins the stack, and the tool in hand, its panel and the kept effect stay.
  expect(shown()).toEqual(stack);
  expect([tool('Draw').getAttribute('aria-pressed'), tool('Keep').getAttribute('aria-pressed')]).toEqual(['true', 'true']);
  expect(viewportProps.current.drawingEnabled).toBe(true);
  // Nothing about it is a panel of the stack: its first row is the Display section's heading,
  // Reset then the X, and it holds the file's view alone, none of the host's settings.
  expect(displayPopover()!.closest('[data-tool-panel]')).toBeNull();
  const heading = displayPopover()!.querySelector('[data-settings-section="display"] [data-settings-section-heading]')!;
  expect([...heading.querySelectorAll('button[aria-label]')].map(button => button.getAttribute('aria-label'))).toEqual(['Reset', 'Close display settings']);
  expect([...displayPopover()!.querySelectorAll('[data-settings-section]')].map(section => section.getAttribute('data-settings-section')))
    .toEqual(['display', 'surfaces', 'grid-axes', 'lighting', 'background', 'floor']);
  // Its X puts it away, and so does its button; Draw is still the tool.
  await user.click(within(displayPopover()!).getByRole('button', { name: 'Close display settings' }));
  expect(displayPopover()).toBeNull();
  expect(display.getAttribute('aria-pressed')).toBe('false');
  await user.click(display);
  await user.click(display);
  expect(displayPopover()).toBeNull();
  // Escape puts it away and leaves the stack's panels and the tool alone.
  await user.click(display);
  await user.keyboard('{Escape}');
  expect(displayPopover()).toBeNull();
  expect(shown()).toEqual(stack);
  expect(tool('Draw').getAttribute('aria-pressed')).toBe('true');
  // A press outside it — on the model — puts it away too, and the kept effect stays.
  await user.click(display);
  await user.pointer({ keys: '[MouseLeft]', target: document.querySelector('[data-mock-viewport] canvas')! });
  expect(displayPopover()).toBeNull();
  expect(tool('Keep').getAttribute('aria-pressed')).toBe('true');
  // Another opening of the file starts with it shut.
  await user.click(display);
  expect(displayPopover()).not.toBeNull();
  remount();
  expect(displayPopover()).toBeNull();
  expect(screen.getByRole('button', { name: 'Display' }).getAttribute('aria-pressed')).toBe('false');
});

it("two surfaces: the strip and the stack share the light chrome surface, and Display's dropdown and a menu over the viewport the more opaque one", async () => {
  const user = userEvent.setup();
  frame();
  expect(FLOATING_CHROME_SURFACE_CLASS).not.toBe(FLOATING_SURFACE_CLASS);
  const classes = (element: Element) => element.className.split(/\s+/);
  const has = (element: Element, surface: string) => surface.split(' ').every(name => classes(element).includes(name));
  expect(has(screen.getByRole('group', { name: 'Interaction tools' }), FLOATING_CHROME_SURFACE_CLASS)).toBe(true);
  for (const label of ['Harness tree', 'Harness reference']) expect(has(panel(label)!, FLOATING_CHROME_SURFACE_CLASS), label).toBe(true);
  // Display's settings are read while they are up: their text must not compete with the model.
  await user.click(screen.getByRole('button', { name: 'Display' }));
  expect(has(displayPopover()!, FLOATING_SURFACE_CLASS)).toBe(true);
  await user.keyboard('{Escape}');
  await user.click(screen.getByRole('button', { name: 'Preview' }));
  await user.click(screen.getByRole('button', { name: 'Orbit' }));
  expect(has(screen.getByRole('menu'), FLOATING_SURFACE_CLASS)).toBe(true);
});

it("Preview is fullscreen: the strip, the stack and the navbar's controls step aside; its corner holds Orbit, Display — the file's own settings — and the way out, which brings back the tool in hand with its panel", async () => {
  const user = userEvent.setup();
  const onFullscreenChange = vi.fn();
  frame({ onFullscreenChange });
  await user.click(tool('Pose'));
  expect(shown()).toContain('Harness position');
  await user.click(screen.getByRole('button', { name: 'Display' }));
  await user.click(screen.getByRole('button', { name: 'Preview' }));
  const chrome = document.querySelector<HTMLElement>('[data-preview-chrome]')!;
  expect([chrome.hidden, chrome.hasAttribute('inert')]).toEqual([true, true]);
  expect(chrome.contains(document.querySelector('[data-cad-tool-stack]'))).toBe(true);
  expect(displayPopover()).toBeNull();
  // The page steps aside (the host hides its navbar), and the view's controls are its own corner's:
  // Orbit, then Display, as it sat in the navbar, then the way out where Preview sat.
  expect(onFullscreenChange.mock.calls).toEqual([[true]]);
  expect(barButtons()).toEqual([]);
  expect(cornerButtons()).toEqual(['Orbit', 'Display', 'Exit preview']);
  const corner = document.querySelector<HTMLElement>('[data-preview-corner]')!;
  expect(viewportProps.current.previewMode).toBe(true);
  // Display is preview's as well: the same dropdown over the file's own settings, preview's tools
  // still put away under it.
  await user.click(within(corner).getByRole('button', { name: 'Display' }));
  expect(displayPopover()!.getAttribute('aria-label')).toBe('Display settings');
  expect(within(corner).getByRole('button', { name: 'Display' }).getAttribute('aria-pressed')).toBe('true');
  await user.click(within(displayPopover()!).getByRole('button', { name: 'Enable Grid / Axes' }));
  expect([viewportProps.current.previewMode, chrome.hidden]).toEqual([true, true]);
  await user.click(within(corner).getByRole('button', { name: 'Exit preview' }));
  expect(onFullscreenChange.mock.calls).toEqual([[true], [false]]);
  expect(chrome.hidden).toBe(false);
  expect(viewportProps.current.previewMode).toBe(false);
  expect(barButtons()).toEqual(['Display', 'Preview']);
  // The stack comes back as it was, the tool in hand with its panel; Display, put away, stays shut,
  // even where Preview was asked for without a press outside it.
  expect(shown()).toContain('Harness position');
  expect(tool('Pose').getAttribute('aria-pressed')).toBe('true');
  expect([displayPopover(), screen.getByRole('button', { name: 'Display' }).getAttribute('aria-pressed')]).toEqual([null, 'false']);
  await user.click(screen.getByRole('button', { name: 'Display' }));
  // What was set in preview is the file's view: the tools view's Display holds it.
  expect(within(displayPopover()!).getByRole('button', { name: 'Disable Grid / Axes' })).toBeTruthy();
  act(() => { fireEvent.click(document.querySelector('[data-harness-ask-preview]')!); });
  expect([viewportProps.current.previewMode, displayPopover()]).toEqual([true, null]);
  await user.click(within(document.querySelector<HTMLElement>('[data-preview-corner]')!).getByRole('button', { name: 'Exit preview' }));
  expect([displayPopover(), screen.getByRole('button', { name: 'Display' }).getAttribute('aria-pressed')]).toEqual([null, 'false']);
});

it("preview's Orbit is the file's: kept between previews, written to the file's view, restored when it is reopened, and another file starts at the defaults", async () => {
  const user = userEvent.setup();
  const states: any[] = [];
  const settings = () => screen.getByRole('menu', { name: 'Orbit' });
  const choices = async () => {
    await user.click(screen.getByRole('button', { name: 'Orbit' }));
    const orbit = within(settings()).getByRole('menuitemcheckbox', { name: 'Orbit' }).getAttribute('aria-checked');
    const speed = within(settings()).getByRole('menuitem', { name: /^Orbit speed/ }).getAttribute('aria-label');
    await user.keyboard('{Escape}');
    return [orbit, speed];
  };
  const first = frame({ onStateChange: state => states.push(state) });
  await user.click(screen.getByRole('button', { name: 'Preview' }));
  // A static file has nothing under the model: no playbar, and Orbit leads the corner.
  expect(screen.queryByRole('toolbar', { name: 'Animation playback' })).toBeNull();
  expect(cornerButtons()).toEqual(['Orbit', 'Display', 'Exit preview']);
  // A fresh file orbits at 1×.
  expect(await choices()).toEqual(['true', 'Orbit speed: 1×']);
  // Orbit off, and its speed 2×.
  await user.click(screen.getByRole('button', { name: 'Orbit' }));
  await user.click(within(settings()).getByRole('menuitemcheckbox', { name: 'Orbit' }));
  expect(screen.getByRole('menu', { name: 'Orbit' })).toBeTruthy();
  const speedItem = within(settings()).getByRole('menuitem', { name: /^Orbit speed/ });
  await user.click(speedItem);
  // jsdom has no geometry for the submenu's pointer grace area; the keyboard path is the same handler.
  (await screen.findByRole('menuitemradio', { name: '2×' })).focus();
  await user.keyboard('{Enter}');
  // Leaving and re-entering preview keeps both.
  await user.click(screen.getByRole('button', { name: 'Exit preview' }));
  await user.click(screen.getByRole('button', { name: 'Preview' }));
  expect(await choices()).toEqual(['false', 'Orbit speed: 2×']);
  // The file's view holds them.
  first.unmount();
  const saved = states.at(-1);
  expect(saved.playback).toEqual({ orbit: false, orbitSpeed: 2, autoplay: false });
  // Reopened from that view: the same choices. Another file: the defaults.
  const reopened = frame({ state: saved });
  await user.click(screen.getByRole('button', { name: 'Preview' }));
  expect(await choices()).toEqual(['false', 'Orbit speed: 2×']);
  reopened.unmount();
  frame({ name: 'other.harness' });
  await user.click(screen.getByRole('button', { name: 'Preview' }));
  expect(await choices()).toEqual(['true', 'Orbit speed: 1×']);
});

it('the Display dropdown keeps its controls together: a dropdown or a color editor inside it goes first, and without taking the dropdown; a preset keeps it open', async () => {
  override(Element.prototype, 'scrollIntoView', { value() {} });
  // An open listbox makes the page under it inert to the pointer (`pointer-events: none`); a press
  // there still reaches the listbox's outside-press layer, as it does in a browser.
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  frame();
  await user.click(screen.getByRole('button', { name: 'Display' }));
  const popover = displayPopover()!;
  expect(popover.querySelectorAll('[data-settings-sections]').length).toBe(1);
  const mode = within(popover).getByRole('combobox', { name: 'Mode' });
  // (Found before a listbox opens: an open one hides the rest of the page from the accessibility tree.)
  const heading = within(popover).getByRole('heading', { name: 'Display' });
  for (const dismiss of ['Escape', 'trigger', 'heading']) {
    await user.click(mode);
    expect(screen.getByRole('listbox')).toBeTruthy();
    if (dismiss === 'Escape') await user.keyboard('{Escape}');
    else await user.click(dismiss === 'trigger' ? mode : heading);
    expect(screen.queryByRole('listbox'), dismiss).toBeNull();
    expect(displayPopover(), `dismissing the dropdown with ${dismiss} keeps Display open`).toBe(popover);
  }
  await user.click(mode);
  await user.click(screen.getByRole('option', { name: 'Render' }));
  expect(displayPopover()).toBe(popover);
  expect(mode.textContent).toContain('Render');
  await user.click(mode);
  await user.click(screen.getByRole('option', { name: 'Solid' }));
  // Solid draws no grid: its colour is there once Grid / Axes is on; Escape closes the colour editor, then Display.
  expect(within(popover).queryByRole('button', { name: 'Grid color' })).toBeNull();
  await user.click(within(popover).getByRole('button', { name: 'Enable Grid / Axes' }));
  await user.click(within(popover).getByRole('button', { name: 'Grid color' }));
  expect(screen.getByRole('spinbutton', { name: 'Color opacity' })).toBeTruthy();
  await user.keyboard('{Escape}');
  expect(screen.queryByRole('spinbutton', { name: 'Color opacity' })).toBeNull();
  expect(displayPopover()).toBe(popover);
  await user.keyboard('{Escape}');
  expect(displayPopover()).toBeNull();
  expect(screen.getByRole('button', { name: 'Display' }).getAttribute('aria-pressed')).toBe('false');
});
