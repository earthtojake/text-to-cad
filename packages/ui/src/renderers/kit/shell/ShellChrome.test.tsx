import React, { forwardRef } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

// The shell's chrome — the strip, the tool stack, Display's panel, the view's actions and preview —
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
import { FLOATING_CHROME_SURFACE_CLASS, FLOATING_SURFACE_CLASS } from '../../../../dist/renderers/kit/tools/floatingSurface.js';
import { RenderModeIcon } from '../../../../dist/renderers/kit/view-settings/DisplayModeOptions.js';
import { SettingsPopover } from '../../../../dist/renderers/kit/shell/SettingsPopover.js';

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
// The navbar FileViewer hands a renderer: where the view's controls go.
function navbarSlot() {
  const slot = document.createElement('div');
  slot.setAttribute('data-test-navbar', '');
  document.body.append(slot);
  return slot;
}
afterEach(() => document.querySelectorAll('[data-test-navbar]').forEach(slot => slot.remove()));
function frame({ path = 'panel.harness', preferences = tabSettings(), state = undefined as unknown, mobile = false, onStateChange = (_: unknown) => {}, onPanelOpen = vi.fn(), onFullscreenChange = vi.fn(), openPanel = '', appearance = { colorScheme: 'light' } as object, notice = null as React.ReactNode, features = undefined as object | undefined } = {}) {
  const props = { source: { id: 'one', rootName: 'one' }, file: { path, name: path, kind: 'file' }, document: null, openPanel, panelSlot: null, notice, features,
    navbarSlot: navbarSlot(), onFullscreenChange, onPanelOpen, onReady() {}, onOpenFile() {}, appearance, state, onStateChange, reload() {}, data: { services: { preferences } } };
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
  // The strip and the stack under it, 8px in from the viewer's top and left, stopping 8px above
  // the cube in the bottom-left corner (itself 8px off the bottom).
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
  const part = frame({ path: 'panel-part.harness', preferences });
  expect([shown(), Boolean(mark())]).toEqual([['Harness reference'], true]);
  part.unmount();
  const assembly = frame({ path: 'panel.harness', preferences });
  expect([shown(), Boolean(mark())]).toEqual([['Harness tree', 'Harness reference'], false]);
  expect(preferences.writes).toBe(0);
  // Closed in the assembly: closed in a part, and in the next assembly too.
  fireEvent.click(within(panel('Harness tree')!).getByRole('button', { name: 'Close harness tree' }));
  expect(layout(preferences).closed).toEqual({ tree: true });
  assembly.unmount();
  const closedPart = frame({ path: 'panel-part.harness', preferences });
  expect([shown(), Boolean(mark())]).toEqual([['Harness reference'], true]);
  // Opened in a part: open in the next part, and in an assembly.
  fireEvent.click(tool('Select'));
  expect(layout(preferences).closed).toEqual({ tree: false });
  closedPart.unmount();
  const openedPart = frame({ path: 'panel-part.harness', preferences });
  expect([shown(), Boolean(mark())]).toEqual([['Harness tree', 'Harness reference'], false]);
  openedPart.unmount();
  frame({ path: 'panel.harness', preferences });
  expect([shown(), Boolean(mark())]).toEqual([['Harness tree', 'Harness reference'], false]);
});

const barButtons = () => [...document.querySelector('[data-test-navbar]')!.querySelectorAll('button')].map(button => button.getAttribute('aria-label'));
const strip = () => [...screen.getByRole('group', { name: 'Interaction tools' }).querySelectorAll('button')].map(button => button.getAttribute('aria-label'));

it('while the model loads the viewer shows none of its own chrome, and all of it returns with the model', () => {
  frame();
  const stage = (name: string) => act(() => { fireEvent.click(document.querySelector(`[data-harness-stage="${name}"]`)!); });
  expect(screen.getByRole('group', { name: 'Interaction tools' })).toBeTruthy();
  expect(barButtons()).toEqual(['Preview']);
  stage('finding');
  expect(screen.queryByRole('group', { name: 'Interaction tools' })).toBeNull();
  expect(document.querySelector('[data-cad-tool-stack]')).toBeNull();
  expect(barButtons()).toEqual([]);
  expect(viewportProps.current.isLoading).toBe(true);
  stage('idle');
  expect(screen.getByRole('group', { name: 'Interaction tools' })).toBeTruthy();
  expect(barButtons()).toEqual(['Preview']);
  // With nothing to work on yet, the strip is idle together, Display with the tools, and so is Preview.
  stage('unready');
  expect(strip()).toEqual(['Select', 'Draw', 'Keep', 'Pose', 'Display']);
  const idle = (name: string) => (name === 'Preview' ? screen.getByRole('button', { name }) : tool(name)).hasAttribute('disabled');
  expect(['Select', 'Draw', 'Display', 'Preview'].map(idle)).toEqual([true, true, true, true]);
  stage('idle');
  expect(['Select', 'Draw', 'Display', 'Preview'].map(idle)).toEqual([false, false, false, false]);
});

it("Preview is a 3D view's, as its renderer declares: a view that does not declare it has no Preview, not a disabled one, and a request for Preview leaves it as it is", () => {
  const onFullscreenChange = vi.fn();
  // Preview asked for from outside the navbar, as a link or a host request would.
  const ask = () => act(() => { fireEvent.click(document.querySelector('[data-harness-ask-preview]')!); });
  // A 3D view (the harness's, declared `previewable`): the navbar offers Preview, and a request enters it.
  frame({ onFullscreenChange });
  expect(barButtons()).toEqual(['Preview']);
  ask();
  expect([viewportProps.current.previewMode, onFullscreenChange.mock.calls]).toEqual([true, [[true]]]);
  cleanup();
  document.querySelectorAll('[data-test-navbar]').forEach(slot => slot.remove());
  onFullscreenChange.mockClear();
  // A view whose renderer does not declare it (`flat.harness`, a 2D view's stand-in): nothing at the
  // navbar's right end, and the same request leaves the normal view on screen, its tools up.
  frame({ path: 'flat.harness', onFullscreenChange });
  expect(barButtons()).toEqual([]);
  expect(screen.queryByRole('button', { name: 'Preview' })).toBeNull();
  ask();
  expect([viewportProps.current.previewMode, onFullscreenChange.mock.calls]).toEqual([false, []]);
  expect(document.querySelector('[data-preview-chrome]')!.hasAttribute('inert')).toBe(false);
  expect(strip()).toEqual(['Draw', 'Display']);
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
  expect(barButtons()).toEqual(['Preview']);
  expect(viewportProps.current.viewCube).toBe(true);
});

it("a dismissed alert's own icon, leftmost of the navbar's right-hand controls, brings its card back; it goes with the card's return, and when the alert clears", async () => {
  // The harness under the real FileViewer, whose navbar holds the host's Settings and the view's control.
  const host = testHost({ links: viewerLinks({ version: '0.7.5' }), environment: { colorScheme: 'light', platform: 'darwin' },
    files: { id: 'one', rootName: 'one', stat: async (path: string) => ({ path, name: path, kind: 'file', extension: 'harness', size: 1 }) } });
  render(<FileViewer file="one.harness" host={host as any} renderers={[createHarnessRenderer({ preferences: tabSettings() })]}
    state={{ panel: null, panelWidth: 220 }} onStateChange={() => {}} settings={<SettingsPopover links={host.links} />} />);
  await screen.findByRole('button', { name: 'Preview' });
  const right = () => [...document.querySelector('[data-viewer-navbar] [data-navbar-controls]')!.parentElement!.querySelectorAll('a, button')]
    .map(node => node.getAttribute('aria-label'));
  const card = () => screen.queryByRole('alert');
  const stage = (name: string) => act(() => { fireEvent.click(document.querySelector(`[data-harness-stage="${name}"]`)!); });
  expect(right()).toEqual(['Settings', 'Preview']);
  stage('failed');
  expect(card()!.textContent).toContain('Harness update failed');
  expect(right()).toEqual(['Settings', 'Preview'], 'the card is up: no icon');
  // Put away: the card's own icon, in the error's colour, named after the alert, before everything else at the right.
  fireEvent.click(within(card()!).getByRole('button', { name: 'Dismiss' }));
  expect(card()).toBeNull();
  expect(right()).toEqual(['Harness update failed', 'Settings', 'Preview']);
  const icon = screen.getByRole('button', { name: 'Harness update failed' });
  expect(icon.querySelector('svg')!.getAttribute('class')).toMatch(/\blucide-circle-alert\b.*\btext-destructive\b/);
  // Pressed, it brings the card back and goes.
  fireEvent.click(icon);
  expect(card()!.textContent).toContain('Harness update failed');
  expect(right()).toEqual(['Settings', 'Preview']);
  // Put away again, and then the alert clears: no card, and no icon; raised again, the card shows.
  fireEvent.click(within(card()!).getByRole('button', { name: 'Dismiss' }));
  expect(right()[0]).toBe('Harness update failed');
  stage('idle');
  expect([card(), right()]).toEqual([null, ['Settings', 'Preview']]);
  stage('failed');
  expect(card()).not.toBeNull();
  expect(right()).toEqual(['Settings', 'Preview']);
});

it('the file explorer, open over the top-left corner, puts the tools out of sight, kept as they are', () => {
  frame({ openPanel: 'tree' });
  const groups = document.querySelector<HTMLElement>('[data-cad-tool-groups]')!;
  expect(groups.classList.contains('invisible')).toBe(true);
  expect(shown()).toEqual(['Harness tree', 'Harness reference']);
  cleanup();
  frame();
  expect(document.querySelector<HTMLElement>('[data-cad-tool-groups]')!.classList.contains('invisible')).toBe(false);
});

it("the host's notice waits for the model, then takes the top-right with Quick Edit stacked under it", () => {
  const notice = <div role="dialog" aria-label="Allow Analytics" />;
  const corner = () => [...document.querySelector('[data-viewport-top-right]')?.children ?? []]
    .map(child => child.hasAttribute('data-viewport-notice') ? 'notice' : child.hasAttribute('data-quick-edit') ? 'Quick Edit' : child.tagName);
  const stage = (name: string) => act(() => { fireEvent.click(document.querySelector(`[data-harness-stage="${name}"]`)!); });
  // On a narrow view the column starts below the tool strip's row, so the strip stays in reach.
  const clearsStrip = () => document.querySelector('[data-viewport-top-right]')!.className.includes('@max-md/cad-viewport:top-');
  frame({ notice });
  stage('finding');
  expect(screen.queryByRole('dialog', { name: 'Allow Analytics' })).toBeNull();
  stage('broken');  // a load the model did not survive: only its card
  expect(screen.queryByRole('dialog', { name: 'Allow Analytics' })).toBeNull();
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
  const notice = <div role="dialog" aria-label="Allow Analytics" />;
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
  expect(strip()).toEqual(['Select', 'Draw', 'Keep', 'Pose', 'Display']);
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

it("Display is the strip's last button, the Render mode's sphere: it opens its panel at the foot of the stack and closes it again, and never takes the tool in hand", async () => {
  const user = userEvent.setup();
  const { remount } = frame();
  // After the file's own tools, on every strip; not among the navbar's controls.
  expect(strip()).toEqual(['Select', 'Draw', 'Keep', 'Pose', 'Display']);
  expect(barButtons()).toEqual(['Preview']);
  // Its icon is the Render mode's, the same drawing the Mode menu shows for Render.
  const sphere = render(<RenderModeIcon />).container.querySelector('svg')!;
  expect(tool('Display').querySelector('svg')!.innerHTML).toBe(sphere.innerHTML);
  await user.click(tool('Keep'));
  await user.click(tool('Draw'));
  expect(tool('Draw').getAttribute('aria-pressed')).toBe('true');
  // Draw's panel leads the stack, and has nothing to fold.
  const stack = shown();
  expect(stack).toEqual(['Drawing controls', 'Harness tree', 'Harness reference', 'Kept controls']);
  expect(within(panel('Drawing controls')!).queryByRole('button', { name: /^(?:Collapse|Expand) / })).toBeNull();
  await user.click(tool('Display'));
  // Its panel joins the stack at its foot; the tool in hand, its panel and the kept effect stay.
  expect(shown()).toEqual([...stack, 'Display settings']);
  expect(['Display', 'Draw', 'Keep'].map(name => tool(name).getAttribute('aria-pressed'))).toEqual(['true', 'true', 'true']);
  expect(viewportProps.current.drawingEnabled).toBe(true);
  // As wide as its settings are laid out for (the popover's 256px), giving way like a details panel,
  // and it does not fold: its first row is the Display section's heading, Reset then the X.
  const display = panel('Display settings')!;
  expect([display.getAttribute('data-tool-panel'), width('Display settings')]).toEqual(['details', 256]);
  expect(within(display).queryByRole('button', { name: /^(?:Collapse|Expand) display/ })).toBeNull();
  const heading = display.querySelector('[data-settings-section="display"] [data-settings-section-heading]')!;
  expect([...heading.querySelectorAll('button[aria-label]')].map(button => button.getAttribute('aria-label'))).toEqual(['Reset', 'Close display settings']);
  // The file's view alone: none of the host's settings.
  expect([...display.querySelectorAll('[data-settings-section]')].map(section => section.getAttribute('data-settings-section')))
    .toEqual(['display', 'surfaces', 'grid-axes', 'lighting', 'background', 'floor']);
  // A press on the model and Escape leave it up: the stack's panels are never Escape's.
  await user.pointer({ keys: '[MouseLeft]', target: document.querySelector('[data-mock-viewport] canvas')! });
  act(() => document.querySelector<HTMLElement>('[data-slot="cad-file-view"]')!.focus());
  await user.keyboard('{Escape}');
  expect(shown()).toEqual([...stack, 'Display settings']);
  // Its X closes it, and so does a second press; Draw is still the tool throughout.
  await user.click(within(display).getByRole('button', { name: 'Close display settings' }));
  expect(shown()).toEqual(stack);
  expect(tool('Display').getAttribute('aria-pressed')).toBe('false');
  await user.click(tool('Display'));
  await user.click(tool('Display'));
  expect(shown()).toEqual(stack);
  expect(tool('Draw').getAttribute('aria-pressed')).toBe('true');
  // From the keyboard, as any button of the strip: Enter opens it, Space closes it.
  act(() => tool('Display').focus());
  await user.keyboard('{Enter}');
  expect(shown()).toContain('Display settings');
  await user.keyboard(' ');
  expect(shown()).not.toContain('Display settings');
  // Another opening of the file starts with it closed.
  await user.click(tool('Display'));
  remount();
  expect(shown()).not.toContain('Display settings');
  expect(tool('Display').getAttribute('aria-pressed')).toBe('false');
});

it("two surfaces: the strip and the stack's panels share the light chrome surface, and Display's settings and a menu over the viewport the more opaque one", async () => {
  const user = userEvent.setup();
  frame();
  expect(FLOATING_CHROME_SURFACE_CLASS).not.toBe(FLOATING_SURFACE_CLASS);
  const classes = (element: Element) => element.className.split(/\s+/);
  const has = (element: Element, surface: string) => surface.split(' ').every(name => classes(element).includes(name));
  expect(has(screen.getByRole('group', { name: 'Interaction tools' }), FLOATING_CHROME_SURFACE_CLASS)).toBe(true);
  await user.click(tool('Display'));
  for (const label of ['Harness tree', 'Harness reference']) expect(has(panel(label)!, FLOATING_CHROME_SURFACE_CLASS), label).toBe(true);
  // Display's settings are read while they are up: their text must not compete with the model.
  expect([has(panel('Display settings')!, FLOATING_SURFACE_CLASS), has(panel('Display settings')!, FLOATING_CHROME_SURFACE_CLASS)]).toEqual([true, false]);
  await user.click(screen.getByRole('button', { name: 'Preview' }));
  await user.click(screen.getByRole('button', { name: 'Playback settings' }));
  expect(has(screen.getByRole('menu'), FLOATING_SURFACE_CLASS)).toBe(true);
});

it("Preview is fullscreen: the strip, the stack and the navbar's controls step aside, never opening the host's column; its corner's way out brings back the tool in hand with its panel", async () => {
  const user = userEvent.setup();
  const onPanelOpen = vi.fn();
  const onFullscreenChange = vi.fn();
  frame({ onPanelOpen, onFullscreenChange });
  await user.click(tool('Pose'));
  expect(shown()).toContain('Harness position');
  await user.click(tool('Display'));
  await user.click(screen.getByRole('button', { name: 'Preview' }));
  const chrome = document.querySelector<HTMLElement>('[data-preview-chrome]')!;
  expect([chrome.hidden, chrome.hasAttribute('inert')]).toEqual([true, true]);
  expect(chrome.contains(document.querySelector('[data-cad-tool-stack]'))).toBe(true);
  expect(chrome.contains(panel('Display settings'))).toBe(true);
  // The page steps aside (the host hides its navbar), and the way out is the view's own corner.
  expect(onFullscreenChange.mock.calls).toEqual([[true]]);
  expect(barButtons()).toEqual([]);
  const corner = document.querySelector<HTMLElement>('[data-preview-corner]')!;
  expect(viewportProps.current.previewMode).toBe(true);
  await user.click(within(corner).getByRole('button', { name: 'Exit preview' }));
  expect(onFullscreenChange.mock.calls).toEqual([[true], [false]]);
  expect(chrome.hidden).toBe(false);
  expect(viewportProps.current.previewMode).toBe(false);
  expect(barButtons()).toEqual(['Preview']);
  // The stack comes back as it was: the tool in hand with its panel, and Display's panel.
  expect(shown()).toEqual(expect.arrayContaining(['Harness position', 'Display settings']));
  expect(tool('Pose').getAttribute('aria-pressed')).toBe('true');
  expect(tool('Display').getAttribute('aria-pressed')).toBe('true');
  // Escape is the viewer's: whatever it closes, it is never the host's column (only its toggle does that).
  act(() => document.querySelector<HTMLElement>('[data-slot="cad-file-view"]')!.focus());
  await user.keyboard('{Escape}');
  await user.keyboard('{Escape}');
  expect(onPanelOpen).not.toHaveBeenCalled();
});

it("preview's Playback settings are the file's: kept between previews, written to the file's view, restored when it is reopened, and another file starts at the defaults", async () => {
  const user = userEvent.setup();
  const states: any[] = [];
  const settings = () => screen.getByRole('menu', { name: 'Playback settings' });
  const choices = async () => {
    await user.click(screen.getByRole('button', { name: 'Playback settings' }));
    const orbit = within(settings()).getByRole('menuitemcheckbox', { name: 'Orbit' }).getAttribute('aria-checked');
    const speed = within(settings()).getByRole('menuitem', { name: /^Orbit speed/ }).getAttribute('aria-label');
    await user.keyboard('{Escape}');
    return [orbit, speed];
  };
  const first = frame({ onStateChange: state => states.push(state) });
  await user.click(screen.getByRole('button', { name: 'Preview' }));
  // A static file has nothing under the model: Playback settings sit in the corner, before the way out.
  expect(screen.queryByRole('toolbar', { name: 'Orbit playback' })).toBeNull();
  expect([...document.querySelector('[data-preview-corner]')!.querySelectorAll('button')].map(button => button.getAttribute('aria-label')))
    .toEqual(['Playback settings', 'Exit preview']);
  // A fresh file orbits at 1×.
  expect(await choices()).toEqual(['true', 'Orbit speed: 1×']);
  // Orbit off, and its speed 2×.
  await user.click(screen.getByRole('button', { name: 'Playback settings' }));
  await user.click(within(settings()).getByRole('menuitemcheckbox', { name: 'Orbit' }));
  expect(screen.getByRole('menu', { name: 'Playback settings' })).toBeTruthy();
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
  frame({ path: 'other.harness' });
  await user.click(screen.getByRole('button', { name: 'Preview' }));
  expect(await choices()).toEqual(['true', 'Orbit speed: 1×']);
});

it('the Display panel keeps its controls together: a dropdown or a color editor inside it closes first and alone, a preset keeps the panel, and Escape never closes it', async () => {
  override(Element.prototype, 'scrollIntoView', { value() {} });
  // An open listbox makes the page under it inert to the pointer (`pointer-events: none`); a press
  // there still reaches the listbox's outside-press layer, as it does in a browser.
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  frame();
  await user.click(tool('Display'));
  const display = panel('Display settings')!;
  expect(display.querySelectorAll('[data-settings-sections]').length).toBe(1);
  const mode = within(display).getByRole('combobox', { name: 'Mode' });
  // (Found before a listbox opens: an open one hides the rest of the page from the accessibility tree.)
  const heading = within(display).getByRole('heading', { name: 'Display' });
  for (const dismiss of ['Escape', 'trigger', 'heading']) {
    await user.click(mode);
    expect(screen.getByRole('listbox')).toBeTruthy();
    if (dismiss === 'Escape') await user.keyboard('{Escape}');
    else await user.click(dismiss === 'trigger' ? mode : heading);
    expect(screen.queryByRole('listbox'), dismiss).toBeNull();
    expect(panel('Display settings'), `dismissing the dropdown with ${dismiss} keeps the panel`).toBe(display);
  }
  await user.click(mode);
  await user.click(screen.getByRole('option', { name: 'Render' }));
  expect(panel('Display settings')).toBe(display);
  expect(mode.textContent).toContain('Render');
  await user.click(mode);
  await user.click(screen.getByRole('option', { name: 'Solid' }));
  // Solid draws no grid: its colour is there once Grid / Axes is on; Escape closes the colour editor, and the panel stays.
  expect(within(display).queryByRole('button', { name: 'Grid color' })).toBeNull();
  await user.click(within(display).getByRole('button', { name: 'Enable Grid / Axes' }));
  await user.click(within(display).getByRole('button', { name: 'Grid color' }));
  expect(screen.getByRole('spinbutton', { name: 'Color opacity' })).toBeTruthy();
  await user.keyboard('{Escape}');
  expect(screen.queryByRole('spinbutton', { name: 'Color opacity' })).toBeNull();
  expect(panel('Display settings')).toBe(display);
  await user.keyboard('{Escape}');
  expect(panel('Display settings')).toBe(display);
  expect(tool('Display').getAttribute('aria-pressed')).toBe('true');
});
