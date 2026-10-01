import React, { forwardRef } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

// The shell's chrome — the strip, the tool stack, the top-right bar, Display's popover and preview —
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
import { ViewerHostContext } from '../../../../dist/host/context.js';
import { testHost } from '../../../../dist/host/testing/host.js';
import { ViewerMobileContext } from '../../../../dist/file-viewer/responsive.js';
import { TOOL_PANEL_WIDTH } from '../../../../dist/renderers/kit/tools/toolStackLayout.js';
import { FLOATING_CHROME_SURFACE_CLASS, FLOATING_SURFACE_CLASS } from '../../../../dist/renderers/kit/tools/floatingSurface.js';

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
  let settings: any = { toolStack: { panels: {}, collapsed: {} }, ...initial };
  const listeners = new Set<() => void>();
  const store = { writes: 0, getSnapshot: () => settings, subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    update(patch: object) { store.writes += 1; settings = { ...settings, ...patch }; listeners.forEach(listener => listener()); } };
  return store;
}
type Settings = ReturnType<typeof tabSettings>;
function frame({ path = 'panel.harness', preferences = tabSettings(), state = undefined as unknown, mobile = false, onStateChange = (_: unknown) => {}, onPanelOpen = vi.fn() } = {}) {
  const props = { source: { id: 'one', rootName: 'one' }, file: { path, name: path, kind: 'file' }, document: null, openPanel: '', panelSlot: null,
    onPanelOpen, onReady() {}, onOpenFile() {}, appearance: { colorScheme: 'light' }, state, onStateChange, reload() {}, data: { services: { preferences } } };
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

it('the chrome is inset from the viewer, every panel opens one width, the tree at half the stack and the Reference at its cap, and nothing is stored until a person sizes one', () => {
  const { preferences } = frame();
  // The strip and the stack under it, 8px in from the viewer's top, left and bottom.
  expect(document.querySelector<HTMLElement>('[data-cad-tool-groups]')!.style).toMatchObject({ top: '8px', left: '8px', bottom: '8px' });
  expect(shown()).toEqual(['Harness tree', 'Harness reference']);
  expect(TOOL_PANEL_WIDTH).toBe(164);
  expect([width('Harness tree'), width('Harness reference')]).toEqual([TOOL_PANEL_WIDTH, TOOL_PANEL_WIDTH]);
  expect(panel('Harness tree')!.style.maxHeight).toBe(`${STACK_HEIGHT / 2}px`);
  expect(panel('Harness reference')!.style.maxHeight).toBe('288px');
  expect(layout(preferences)).toEqual({ panels: {}, collapsed: {} });
  // Two kinds of panel: the tree is the person's to size, by its right edge, its bottom edge and
  // the corner between them; the Reference and a kept effect are fixed, at the one width.
  fireEvent.click(tool('Keep'));
  expect(shown()).toEqual(['Harness tree', 'Harness reference', 'Kept controls']);
  expect(handles('Harness tree')).toEqual(['Resize harness tree width', 'Resize harness tree height', 'Resize harness tree']);
  expect([handles('Harness reference'), handles('Kept controls')]).toEqual([[], []]);
  expect(width('Kept controls')).toBe(TOOL_PANEL_WIDTH);
  expect(tool('Keep').getAttribute('aria-pressed')).toBe('true');
  expect(preferences.writes).toBe(0);
});

it("the tree's width is the person's: the Reference follows it mid-drag, it is written once on release, and the keyboard nudges it between the one width and half the viewer", () => {
  const { preferences } = frame();
  fireEvent.click(tool('Keep'));
  const handle = screen.getByRole('separator', { name: 'Resize harness tree width' });
  expect(handle.getAttribute('aria-orientation')).toBe('vertical');
  drag(handle, [100, 0], { release: false });
  expect([width('Harness tree'), width('Harness reference'), width('Kept controls')]).toEqual([TOOL_PANEL_WIDTH + 100, TOOL_PANEL_WIDTH + 100, TOOL_PANEL_WIDTH]);
  expect(preferences.writes).toBe(0);
  fireEvent.pointerUp(handle, { pointerId: 1, clientX: 200, clientY: 100 });
  expect(preferences.writes).toBe(1);
  expect(layout(preferences).panels).toEqual({ tree: { width: TOOL_PANEL_WIDTH + 100 } });
  expect([width('Harness tree'), width('Harness reference'), width('Kept controls')]).toEqual([TOOL_PANEL_WIDTH + 100, TOOL_PANEL_WIDTH + 100, TOOL_PANEL_WIDTH]);
  fireEvent.keyDown(handle, { key: 'ArrowLeft' });
  expect(layout(preferences).panels.tree.width).toBe(TOOL_PANEL_WIDTH + 84);
  fireEvent.keyDown(handle, { key: 'Home' });
  expect(layout(preferences).panels.tree.width).toBe(TOOL_PANEL_WIDTH);
  fireEvent.keyDown(handle, { key: 'End' });
  expect(layout(preferences).panels).toEqual({ tree: { width: VIEWER.width / 2 } });
  expect(width('Harness tree')).toBe(VIEWER.width / 2);
});

it("the tree's height and Position's size are each the person's: one write per gesture, the corner both at once, the other panel untouched, and a remount opens at what was left", () => {
  const { preferences, remount } = frame();
  const heightHandle = screen.getByRole('separator', { name: 'Resize harness tree height' });
  expect(heightHandle.getAttribute('aria-orientation')).toBe('horizontal');
  drag(heightHandle, [0, -100]);
  expect(preferences.writes).toBe(1);
  expect(layout(preferences).panels).toEqual({ tree: { height: STACK_HEIGHT / 2 - 100 } });
  fireEvent.keyDown(heightHandle, { key: 'ArrowDown' });
  expect(layout(preferences).panels.tree.height).toBe(STACK_HEIGHT / 2 - 84);
  fireEvent.keyDown(heightHandle, { key: 'Home' });
  expect(layout(preferences).panels.tree.height).toBe(64);
  preferences.update({ toolStack: { panels: { tree: { height: 200 } }, collapsed: {} } });
  remount();
  expect(panel('Harness tree')!.style.maxHeight).toBe('200px');

  // Position, sized by its corner: its width and height in one write, the tree as it was.
  preferences.update({ toolStack: { panels: {}, collapsed: {} } });
  fireEvent.click(tool('Pose'));
  expect(handles('Harness position')).toEqual(['Resize harness position width', 'Resize harness position height', 'Resize harness position']);
  const writes = preferences.writes;
  drag(screen.getByRole('separator', { name: 'Resize harness position' }), [60, -50]);
  expect(preferences.writes).toBe(writes + 1);
  expect(layout(preferences).panels).toEqual({ position: { width: TOOL_PANEL_WIDTH + 60, height: STACK_HEIGHT / 2 - 50 } });
  expect([width('Harness tree'), panel('Harness tree')!.style.maxHeight]).toEqual([TOOL_PANEL_WIDTH, `${STACK_HEIGHT / 2}px`]);
  // The tree's own corner from the keyboard moves it one axis at a time, and Position stays.
  const corner = screen.getByRole('separator', { name: 'Resize harness tree' });
  fireEvent.keyDown(corner, { key: 'ArrowRight' });
  fireEvent.keyDown(corner, { key: 'ArrowUp' });
  expect(layout(preferences).panels).toEqual({ position: { width: TOOL_PANEL_WIDTH + 60, height: STACK_HEIGHT / 2 - 50 },
    tree: { width: TOOL_PANEL_WIDTH + 16, height: STACK_HEIGHT / 2 - 16 } });
  // Reset puts every size back.
  act(() => preferences.update({ toolStack: { panels: {}, collapsed: {} } }));
  expect([width('Harness tree'), width('Harness position'), panel('Harness tree')!.style.maxHeight]).toEqual([TOOL_PANEL_WIDTH, TOOL_PANEL_WIDTH, `${STACK_HEIGHT / 2}px`]);
});

it('every panel folds to its first row by a chevron, its content kept mounted; a folded tree keeps only its width handle; which panels are folded is kept across a remount', () => {
  const { preferences, remount } = frame();
  const tree = panel('Harness tree')!;
  const fold = within(tree).getByRole('button', { name: 'Collapse harness tree' });
  expect([fold.getAttribute('aria-expanded'), fold.querySelector('[data-chevron]')!.getAttribute('data-chevron')]).toEqual(['true', 'up']);
  fireEvent.click(fold);
  const unfold = within(tree).getByRole('button', { name: 'Expand harness tree' });
  expect([unfold.getAttribute('aria-expanded'), unfold.querySelector('[data-chevron]')!.getAttribute('data-chevron')]).toEqual(['false', 'down']);
  expect(tree.hasAttribute('data-collapsed')).toBe(true);
  expect(within(tree).getByText('Row 1')).toBeTruthy();
  expect((tree.querySelector('[data-tool-panel-body]')!.closest('[hidden]'))).not.toBeNull();
  expect(layout(preferences).collapsed).toEqual({ tree: true });
  expect(handles('Harness tree')).toEqual(['Resize harness tree width']);
  // Widened while folded: one write, and it stays folded.
  drag(screen.getByRole('separator', { name: 'Resize harness tree width' }), [80, 0]);
  expect(layout(preferences)).toEqual({ panels: { tree: { width: TOOL_PANEL_WIDTH + 80 } }, collapsed: { tree: true } });
  expect(panel('Harness tree')!.hasAttribute('data-collapsed')).toBe(true);
  fireEvent.click(within(panel('Harness tree')!).getByRole('button', { name: 'Expand harness tree' }));
  expect(layout(preferences).collapsed).toEqual({});
  // A heading panel folds to its heading; both stay folded across a remount.
  fireEvent.click(within(panel('Harness tree')!).getByRole('button', { name: 'Collapse harness tree' }));
  fireEvent.click(within(panel('Harness reference')!).getByRole('button', { name: 'Collapse harness reference' }));
  expect(panel('Harness reference')!.querySelector('[data-tool-panel-body]')!.closest('[hidden]')).not.toBeNull();
  remount();
  expect(within(panel('Harness tree')!).getByRole('button', { name: 'Expand harness tree' })).toBeTruthy();
  expect(within(panel('Harness reference')!).getByRole('button', { name: 'Expand harness reference' })).toBeTruthy();
  fireEvent.click(within(panel('Harness tree')!).getByRole('button', { name: 'Expand harness tree' }));
  fireEvent.click(within(panel('Harness reference')!).getByRole('button', { name: 'Expand harness reference' }));
  expect(layout(preferences).collapsed).toEqual({});
});

it("on a phone a tree's default cap is the whole column, not half of it", () => {
  frame({ mobile: true });
  expect(panel('Harness tree')!.style.maxHeight).toBe(`${STACK_HEIGHT}px`);
});

const displayPopover = () => document.querySelector<HTMLElement>('[data-display-popover]');
const barButtons = () => [...document.querySelector('[data-viewport-actions]')!.querySelectorAll('button')].map(button => button.getAttribute('aria-label'));

it('Display is a popover beside Preview, never a tool: opened over Draw it leaves Draw in hand with its panel, and the stack as it was', async () => {
  const user = userEvent.setup();
  frame();
  expect(barButtons()).toEqual(['Display settings', 'Preview']);
  expect(within(screen.getByRole('group', { name: 'Interaction tools' })).queryByRole('button', { name: /^Display/ })).toBeNull();
  await user.click(tool('Keep'));
  await user.click(tool('Draw'));
  expect(tool('Draw').getAttribute('aria-pressed')).toBe('true');
  // Draw's panel leads the stack, and has nothing to fold.
  const stack = shown();
  expect(stack).toEqual(['Drawing controls', 'Harness tree', 'Harness reference', 'Kept controls']);
  expect(within(panel('Drawing controls')!).queryByRole('button', { name: /^(?:Collapse|Expand) / })).toBeNull();
  const display = screen.getByRole('button', { name: 'Display settings' });
  await user.click(display);
  expect(displayPopover()!.getAttribute('aria-label')).toBe('Display settings');
  expect(display.getAttribute('aria-pressed')).toBe('true');
  expect(shown()).toEqual(stack);
  expect([tool('Draw').getAttribute('aria-pressed'), tool('Keep').getAttribute('aria-pressed')]).toEqual(['true', 'true']);
  expect(viewportProps.current.drawingEnabled).toBe(true);
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
});

it('two surfaces: the strip and the stack share the light chrome surface, and a popover or a menu over the viewport has the more opaque one', async () => {
  const user = userEvent.setup();
  frame();
  expect(FLOATING_CHROME_SURFACE_CLASS).not.toBe(FLOATING_SURFACE_CLASS);
  const classes = (element: Element) => element.className.split(/\s+/);
  const has = (element: Element, surface: string) => surface.split(' ').every(name => classes(element).includes(name));
  expect(has(screen.getByRole('group', { name: 'Interaction tools' }), FLOATING_CHROME_SURFACE_CLASS)).toBe(true);
  for (const label of ['Harness tree', 'Harness reference']) expect(has(panel(label)!, FLOATING_CHROME_SURFACE_CLASS), label).toBe(true);
  await user.click(screen.getByRole('button', { name: 'Display settings' }));
  expect(has(displayPopover()!, FLOATING_SURFACE_CLASS)).toBe(true);
  await user.keyboard('{Escape}');
  await user.click(screen.getByRole('button', { name: 'Preview' }));
  await user.click(screen.getByRole('button', { name: 'Playback settings' }));
  expect(has(screen.getByRole('menu'), FLOATING_SURFACE_CLASS)).toBe(true);
});

it("Preview puts the strip and the stack away and keeps the bar, never opening the host's column; its X brings back the tool in hand with its panel", async () => {
  const user = userEvent.setup();
  const onPanelOpen = vi.fn();
  frame({ onPanelOpen });
  await user.click(tool('Pose'));
  expect(shown()).toContain('Harness position');
  await user.click(screen.getByRole('button', { name: 'Display settings' }));
  await user.click(screen.getByRole('button', { name: 'Preview' }));
  const chrome = document.querySelector<HTMLElement>('[data-preview-chrome]')!;
  expect([chrome.hidden, chrome.hasAttribute('inert')]).toEqual([true, true]);
  expect(chrome.contains(document.querySelector('[data-cad-tool-stack]'))).toBe(true);
  expect(displayPopover()).toBeNull();
  expect(barButtons()).toEqual(['Display settings', 'Exit preview']);
  expect(viewportProps.current.previewMode).toBe(true);
  await user.click(screen.getByRole('button', { name: 'Exit preview' }));
  expect(chrome.hidden).toBe(false);
  expect(viewportProps.current.previewMode).toBe(false);
  expect(shown()).toContain('Harness position');
  expect(tool('Pose').getAttribute('aria-pressed')).toBe('true');
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
  // A fresh file orbits at 1×.
  expect(screen.getByRole('button', { name: 'Pause orbit' })).toBeTruthy();
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
  expect(screen.getByRole('button', { name: 'Play orbit' })).toBeTruthy();
  // Leaving and re-entering preview keeps both.
  await user.click(screen.getByRole('button', { name: 'Exit preview' }));
  await user.click(screen.getByRole('button', { name: 'Preview' }));
  expect(screen.getByRole('button', { name: 'Play orbit' })).toBeTruthy();
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

it('the Display popover keeps its controls together: a dropdown or a color editor inside it goes first, and without taking the popover; a preset keeps it open', async () => {
  override(Element.prototype, 'scrollIntoView', { value() {} });
  // An open listbox makes the page under it inert to the pointer (`pointer-events: none`); a press
  // there still reaches the listbox's outside-press layer, as it does in a browser.
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  frame();
  await user.click(screen.getByRole('button', { name: 'Display settings' }));
  const popover = displayPopover()!;
  expect(popover.querySelectorAll('[data-settings-sections]').length).toBe(1);
  // It does not fold: nothing about it is a panel of the stack.
  expect(within(popover).queryByRole('button', { name: /^(?:Collapse|Expand) display settings$/ })).toBeNull();
  expect(popover.hasAttribute('data-tool-panel')).toBe(false);
  const mode = within(popover).getByRole('combobox', { name: 'Mode' });
  // (Found before a listbox opens: an open one hides the rest of the page from the accessibility tree.)
  const heading = within(popover).getByRole('heading', { name: 'Display' });
  for (const dismiss of ['Escape', 'trigger', 'heading']) {
    await user.click(mode);
    expect(screen.getByRole('listbox')).toBeTruthy();
    if (dismiss === 'Escape') await user.keyboard('{Escape}');
    else await user.click(dismiss === 'trigger' ? mode : heading);
    expect(screen.queryByRole('listbox'), dismiss).toBeNull();
    expect(displayPopover(), `dismissing the dropdown with ${dismiss} keeps the popover`).toBe(popover);
  }
  await user.click(mode);
  await user.click(screen.getByRole('option', { name: 'Render' }));
  expect(displayPopover()).toBe(popover);
  expect(mode.textContent).toContain('Render');
  await user.click(mode);
  await user.click(screen.getByRole('option', { name: 'Solid' }));
  // Solid draws no grid: its colour is there once Grid / Axes is on; Escape closes the colour editor, then the popover.
  expect(within(popover).queryByRole('button', { name: 'Grid color' })).toBeNull();
  await user.click(within(popover).getByRole('button', { name: 'Enable Grid / Axes' }));
  await user.click(within(popover).getByRole('button', { name: 'Grid color' }));
  expect(screen.getByRole('spinbutton', { name: 'Color opacity' })).toBeTruthy();
  await user.keyboard('{Escape}');
  expect(screen.queryByRole('spinbutton', { name: 'Color opacity' })).toBeNull();
  expect(displayPopover()).toBe(popover);
  await user.keyboard('{Escape}');
  expect(displayPopover()).toBeNull();
  expect(screen.getByRole('button', { name: 'Display settings' }).getAttribute('aria-pressed')).toBe('false');
});

it('a failure that leaves nothing on screen puts the tool stack away under its card; with a model on screen the stack stays', () => {
  frame();
  const stack = () => document.querySelector<HTMLElement>('[data-cad-tool-stack]')!;
  const stage = (name: string) => fireEvent.click(document.querySelector(`[data-harness-stage="${name}"]`)!);
  expect(stack().hidden).toBe(false);
  stage('broken');
  expect(screen.getByRole('alert').textContent).toContain('Harness build failed');
  expect(stack().hidden).toBe(true);
  // Kept mounted: the panels come back as they were.
  expect(panel('Harness tree')).not.toBeNull();
  stage('failed');
  expect(screen.getByRole('alert').textContent).toContain('Harness update failed');
  expect(stack().hidden).toBe(false);
  // An error raised beside a model on screen, saying nothing about blocking, leaves the stack up.
  stage('beside');
  expect(screen.getByRole('alert').textContent).toContain('Couldn’t load the harness extra');
  expect(stack().hidden).toBe(false);
  stage('idle');
  expect(stack().hidden).toBe(false);
});

it("a failure card has no view-update spinner beside it: a theme switch under it waits on a frame that is never drawn", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    const slot = document.createElement('div');
    document.body.append(slot);
    const props = (colorScheme: string) => ({ source: { id: 'one', rootName: 'one' }, file: { path: 'panel.harness', name: 'panel.harness', kind: 'file' }, document: null,
      openPanel: '', panelSlot: null, navigationStatusSlot: slot, onPanelOpen() {}, onReady() {}, onOpenFile() {}, appearance: { colorScheme }, state: undefined,
      onStateChange() {}, reload() {}, data: { services: { preferences: tabSettings() } } });
    const element = (colorScheme: string) => <ViewerHostContext.Provider value={testHost()}><ViewerMobileContext.Provider value={false}>
      <HarnessRenderer {...(props(colorScheme) as any)} /></ViewerMobileContext.Provider></ViewerHostContext.Provider>;
    const view = render(element('light'));
    fireEvent.click(document.querySelector('[data-harness-stage="broken"]')!);
    expect(screen.getByRole('alert').textContent).toContain('Harness build failed');
    view.rerender(element('dark'));
    await act(async () => { vi.advanceTimersByTime(500); });
    expect(slot.querySelector('[data-view-update-status]')).toBeNull();
    slot.remove();
  } finally {
    vi.useRealTimers();
  }
});

it("a failure card hides only the Display change still in progress: one that failed keeps its Retry", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    const slot = document.createElement('div');
    document.body.append(slot);
    const props = (colorScheme: string) => ({ source: { id: 'one', rootName: 'one' }, file: { path: 'panel.harness', name: 'panel.harness', kind: 'file' }, document: null,
      openPanel: '', panelSlot: null, navigationStatusSlot: slot, onPanelOpen() {}, onReady() {}, onOpenFile() {}, appearance: { colorScheme }, state: undefined,
      onStateChange() {}, reload() {}, data: { services: { preferences: tabSettings() } } });
    const element = (colorScheme: string) => <ViewerHostContext.Provider value={testHost()}><ViewerMobileContext.Provider value={false}>
      <HarnessRenderer {...(props(colorScheme) as any)} /></ViewerMobileContext.Provider></ViewerHostContext.Provider>;
    const view = render(element('light'));
    fireEvent.click(document.querySelector('[data-harness-stage="broken"]')!);
    view.rerender(element('dark'));
    await act(async () => { vi.advanceTimersByTime(500); });
    // The viewport reports the Display change failed.
    const { viewUpdate } = viewportProps.current;
    await act(async () => { viewUpdate.binding.complete(viewUpdate.revision, new Error('Render studio unavailable')); });
    expect(slot.querySelector('[data-view-update-status]')?.textContent).toContain('Couldn’t update view');
    expect(within(slot).getByRole('button', { name: 'Retry view update' })).toBeTruthy();
    slot.remove();
  } finally {
    vi.useRealTimers();
  }
});
