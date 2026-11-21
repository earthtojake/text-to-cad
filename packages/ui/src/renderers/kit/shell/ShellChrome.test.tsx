import React, { forwardRef, useEffect, useImperativeHandle } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

// The shell's chrome — the strip, the tool stack, the view's panel, the view's actions, Display's dropdown and preview —
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
import { SETTINGS_PANEL_SURFACE_CLASS, FLOATING_CHROME_SURFACE_CLASS, FLOATING_SURFACE_CLASS } from '../../../../dist/lib/floatingSurface.js';
import { ControlUsageProvider } from '../../../../dist/usage/controls.js';
import { PanelTogglesContext } from '../../../../dist/file-viewer/panelToggles.js';

// The panel's toggle, as the navbar draws it (`file-viewer/panelToggles.js`): what the frame says, as a button.
function NavbarToggles({ children }: { children: React.ReactNode }) {
  const [toggles, setToggles] = React.useState<any>(null);
  return <PanelTogglesContext.Provider value={setToggles}>
    {toggles?.left ? <button type="button" aria-label={toggles.left.label} aria-expanded={toggles.left.open}
      data-navbar-panel="left" onClick={toggles.left.toggle} /> : null}
    {children}
  </PanelTogglesContext.Provider>;
}
import { SIDEBAR_SLIDE_CLASS } from '../../../../dist/renderers/kit/tools/PreviewChrome.js';
import { createAnimationClock } from '../../../../dist/renderers/kit/tools/playbar/animationClock.js';
import { writeFileView } from '../../../../dist/renderers/kit/shell/fileView.js';

// jsdom lays nothing out, so the few sizes the chrome reads are given: a viewer 1280 × 800 whose
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
    if (this.hasAttribute('data-cad-canvas')) return DOMRect.fromRect({ x: 0, y: 0, ...VIEWER });
    if (this.matches('section[data-tool-panel]')) return DOMRect.fromRect({ x: 8, y: 48, width: parseFloat(this.style.width) || 0, height: parseFloat(this.style.maxHeight) || 100 });
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
    const shell = <ViewerHostContext.Provider value={testHost()}><ViewerMobileContext.Provider value={mobile}><NavbarToggles>
      <HarnessRenderer {...(props as any)} /></NavbarToggles></ViewerMobileContext.Provider></ViewerHostContext.Provider>;
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
// The view's panel (`FlatPanel.jsx`): its tabs, the one shown, a tab by name, and the sections on screen.
const flatPanel = () => document.querySelector<HTMLElement>('aside[data-flat-panel]')!;
const tabNames = () => [...flatPanel().querySelectorAll('[data-flat-panel-tab-name]')].map(name => name.textContent);
const shownTab = () => flatPanel().querySelector('[role=tab][aria-selected="true"] [data-flat-panel-tab-name]')?.textContent;
const tab = (name: string) => within(flatPanel()).getByRole('tab', { name, exact: true });
const sections = () => [...flatPanel().querySelectorAll<HTMLElement>('section[data-tool-panel]')].filter(node => !node.hidden).map(node => node.getAttribute('aria-label'));
const handles = (label: string) => [...panel(label)!.querySelectorAll('[role=separator]')].map(handle => handle.getAttribute('aria-label'));
const width = (label: string) => parseFloat(panel(label)!.style.width);
const layout = (preferences: Settings) => preferences.getSnapshot().toolStack;
const tool = (name: string) => within(screen.getByRole('group', { name: 'Interaction tools' })).getByRole('button', { name });
function drag(handle: Element, [dx, dy]: [number, number], { release = true } = {}) {
  fireEvent.pointerDown(handle, { button: 0, pointerId: 1, clientX: 100, clientY: 100 });
  fireEvent.pointerMove(handle, { pointerId: 1, clientX: 100 + dx, clientY: 100 + dy });
  if (release) fireEvent.pointerUp(handle, { pointerId: 1, clientX: 100 + dx, clientY: 100 + dy });
}

it("the strip is at the top centre with the stack under it; the view's panel is docked at the left, open, a tab per section, the first shown, and nothing is stored until a person changes it", () => {
  const { preferences } = frame();
  // The strip and the stack under it, 8px down from the viewer's top, centred on the whole view,
  // stopping 8px above the cube's line (the cube's box 8px off the bottom).
  // The panels never move it: it stands over them, centred on the window (`ViewFrame.jsx`'s top layer).
  expect(document.querySelector<HTMLElement>('[data-cad-tool-groups]')!.style).toMatchObject({ top: '8px', left: '8px', right: '8px', bottom: 'calc(84px)' });
  expect(document.querySelector('[data-cad-tool-groups]')!.closest('[data-view-top-layer]')).not.toBeNull();
  // The panel (`FlatPanel.jsx`), a board's: the search over its tabs, a tab per section in their order, the first shown.
  expect([flatPanel().getAttribute('data-flat-panel'), flatPanel().hidden]).toEqual(['docked', false]);
  expect([tabNames(), shownTab(), sections()]).toEqual([['Harness tree', 'Reference'], 'Harness tree', ['Harness tree']]);
  expect(screen.getByRole('button', { name: 'Search the model' })).toBeTruthy();
  // A section is its tab's page: no surface, width, cap or grip of its own.
  for (const label of ['Harness tree', 'Harness reference']) {
    expect([panel(label)!.style.width, panel(label)!.style.maxHeight, handles(label)], label).toEqual(['', '', []]);
  }
  // A kept effect is the stack's: fixed, at the one width, with no grip.
  fireEvent.click(tool('Keep'));
  expect(shown()).toEqual(['Kept controls']);
  expect([width('Kept controls'), handles('Kept controls')]).toEqual([TOOL_PANEL_WIDTH, []]);
  expect(tool('Keep').getAttribute('aria-pressed')).toBe('true');
  expect([preferences.writes, layout(preferences)]).toEqual([0, { panels: {}, collapsed: {} }]);
});

it("the panel's tabs are there whatever the tool, a tool's own section coming and going with it; a tab shows its section alone, its content kept; the tab, the width and a collapse are the person's, and never the tab's settings", () => {
  // The view's frame as wide as the viewer, so the grip's bound is the model's 640px: 1280 - 640.
  const rect = Element.prototype.getBoundingClientRect;
  override(Element.prototype, 'getBoundingClientRect', { value(this: HTMLElement) {
    return this.hasAttribute('data-sidebar') ? DOMRect.fromRect({ x: 0, y: 0, ...VIEWER }) : rect.call(this);
  } });
  const { preferences } = frame();
  expect(flatPanel().style.width).toBe('256px');
  fireEvent.click(tool('Draw'));
  expect(tabNames()).toEqual(['Harness tree', 'Reference']);
  fireEvent.click(tool('Pose'));
  expect(tabNames()).toEqual(['Harness tree', 'Reference', 'Joints']);
  fireEvent.click(tab('Joints'));
  expect([shownTab(), sections()]).toEqual(['Joints', ['Harness position']]);
  // Its head's actions are a row at the top of its tab; nothing folds.
  expect(panel('Harness position')!.querySelector('[aria-expanded]')).toBeNull();
  fireEvent.click(tab('Reference'));
  expect(sections()).toEqual(['Harness reference']);
  // Its width, from the grip on its right edge: 16px a key, Home and End to its bounds.
  const grip = screen.getByRole('separator', { name: 'Resize panel' });
  fireEvent.keyDown(grip, { key: 'End' });
  expect([flatPanel().style.width, grip.getAttribute('aria-valuemax')]).toEqual(['640px', '640']);
  fireEvent.keyDown(grip, { key: 'Home' });
  expect(flatPanel().style.width).toBe('200px');
  // Collapsed, it goes whole, nothing of it over the model (its toggle the navbar's); shown again, on the tab it showed.
  fireEvent.click(screen.getByRole('button', { name: 'Hide panel' }));
  expect(flatPanel().hidden).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: 'Show panel' }));
  expect([flatPanel().hidden, shownTab()]).toEqual([false, 'Reference']);
  // All of it is the file's (`filePanel.js`, kept in the file's view by the file viewer), none the tab's.
  expect([preferences.writes, layout(preferences)]).toEqual([0, { panels: {}, collapsed: {} }]);
});

it("⌘\\ (Ctrl+\\) shows and hides the panel; \\ alone does nothing, the panel and the strip left as they are", () => {
  frame({ viewer: true });
  const view = document.querySelector<HTMLElement>('[data-slot="cad-file-view"]')!;
  const strip = () => document.querySelector<HTMLElement>('[data-cad-tool-groups]')!;
  fireEvent.keyDown(view, { key: '\\', code: 'Backslash' });
  expect([flatPanel().hidden, strip().closest('[hidden]'), screen.getByRole('button', { name: 'Hide panel' }).getAttribute('aria-expanded')]).toEqual([false, null, 'true']);
  fireEvent.keyDown(view, { key: '\\', code: 'Backslash', ctrlKey: true });
  expect([flatPanel().hidden, screen.getByRole('button', { name: 'Show panel' }).getAttribute('aria-expanded')]).toEqual([true, 'false']);
  fireEvent.keyDown(view, { key: '\\', code: 'Backslash' });
  expect(flatPanel().hidden).toBe(true);
  fireEvent.keyDown(view, { key: '\\', code: 'Backslash', metaKey: true });
  expect([flatPanel().hidden, strip().closest('[hidden]')]).toEqual([false, null]);
});

it("on a phone the panel is a sheet from the left behind the navbar's toggle, closed at the start, and the strip is centred in the view", async () => {
  frame({ mobile: true, viewer: true });
  const column = document.querySelector<HTMLElement>('[data-cad-tool-groups]')!;
  expect(column.style).toMatchObject({ left: '8px', right: '8px' });
  expect(column.className).toMatch(/\bitems-center\b/);
  // No docked panel and nothing over the model until the toggle opens the sheet: the same panel, its tabs and search, a
  // phone page's sizes; Escape (or a tap outside, a swipe back, its Back) puts it away. ⌘\ is its key too; / is none.
  expect(document.querySelector('[data-flat-panel]')).toBeNull();
  fireEvent.keyDown(document.querySelector('[data-slot="cad-file-view"]')!, { key: '/' });
  expect(document.querySelector('[data-flat-panel]')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Show panel' }));
  const sheet = await waitFor(() => { const found = document.querySelector<HTMLElement>('[data-panel-sheet]'); expect(found).not.toBeNull(); return found!; });
  expect([sheet.getAttribute('role'), sheet.querySelector('[data-flat-panel]')!.getAttribute('data-flat-panel'), sheet.querySelectorAll('[role=tab]').length > 0,
    sheet.querySelector('[data-flat-panel-search-open]') !== null, document.querySelector('[data-navbar-panel="left"]')!.getAttribute('aria-label')]).toEqual(['dialog', 'page', true, true, 'Hide panel']);
  fireEvent.keyDown(sheet, { key: 'Escape' });
  await waitFor(() => expect(document.querySelector('[data-panel-sheet]')).toBeNull());
  // A swipe back towards its edge closes it too.
  fireEvent.keyDown(document.querySelector('[data-slot="cad-file-view"]')!, { key: '\\', ctrlKey: true });
  const again = await waitFor(() => { const found = document.querySelector<HTMLElement>('[data-panel-sheet]'); expect(found).not.toBeNull(); return found!; });
  fireEvent.pointerDown(again, { pointerId: 3, pointerType: 'touch', clientX: 200, clientY: 300 });
  fireEvent.pointerUp(again, { pointerId: 3, pointerType: 'touch', clientX: 100, clientY: 310 });
  await waitFor(() => expect(document.querySelector('[data-panel-sheet]')).toBeNull());
  fireEvent.click(tool('Draw'));
  expect(tool('Draw').getAttribute('aria-pressed')).toBe('true');
  // The drawing row is the same row on a phone, its buttons 36px tiles (`data-touch`), wrapping where it must: the
  // drawing tools, then what is drawn next; Draw has no chevron.
  const row = screen.getByRole('toolbar', { name: 'Annotation controls' });
  expect(row.hasAttribute('data-touch')).toBe(true);
  expect([...row.querySelectorAll('[role=group][aria-label="Drawing tools"] button')].map(button => button.getAttribute('aria-label')))
    .toEqual(['Pen', 'Highlighter', 'Line', 'Arrow', 'Rectangle', 'Ellipse', 'Text']);
  expect([...row.querySelectorAll('[role=group][aria-label="Editing tools"] button')].map(button => button.getAttribute('aria-label')))
    .toEqual(['Fill', 'Eraser']);
  expect(screen.queryByRole('button', { name: 'Drawing tools' })).toBeNull();
});

// The corner's stack over the cube (`ViewCornerStack.jsx`): Display, its menu the modes, Grid and the Background; Projection; Home.
// The view's settings: View, a tile of the cube's row (`ViewCornerStack.jsx`'s `CubeRow`), one menu of submenus.
const viewButton = () => screen.getByRole('button', { name: 'View' });
const viewMenu = () => document.querySelector<HTMLElement>('[role=menu][aria-label="View"]');
const openView = async () => {
  fireEvent.pointerDown(viewButton(), { button: 0, ctrlKey: false, pointerType: 'mouse' });
  await waitFor(() => expect(viewMenu()).not.toBeNull());
  return viewMenu()!;
};
async function closeView(user: ReturnType<typeof userEvent.setup>) {
  await user.keyboard('{Escape}');
  await waitFor(() => expect(viewMenu()).toBeNull());
}
const gridItem = () => within(viewMenu()!).getByRole('menuitemcheckbox', { name: 'Grid' });
// A submenu of View, opened by a press on its row.
const viewSub = (id: string) => {
  fireEvent.click(viewMenu()!.querySelector<HTMLElement>(`[data-view-sub="${id}"]`)!);
  return document.querySelector<HTMLElement>(`[data-view-sub-content="${id}"]`)!;
};
const backgroundItem = (value: string) => viewSub('background').querySelector<HTMLElement>(`[data-display-background="${value}"]`);
// A control by its name, whatever it says it is set to.
const named = (button: Element) => button.getAttribute('aria-label')!.split(':')[0];
// The view's controls: the corner's (the row under the cube: Home, View), the navbar's (Preview, under a file viewer's
// navbar), then Preview, the strip's last outside one.
const barButtons = () => [...document.querySelectorAll('[data-view-corner-stack] button'), ...document.querySelectorAll('[data-navbar-view-controls] button'),
  ...document.querySelectorAll('[role=group][aria-label="Interaction tools"] [data-view-controls] button')].map(named);
// Preview's own bar, over the view's top edge: its name, and its controls at its right.
const previewBar = () => document.querySelector<HTMLElement>('[data-preview-bar]');
const cornerButtons = () => [...previewBar()?.querySelectorAll('button') ?? []].map(named);
// The strip's tools, before the view's controls.
const strip = () => [...screen.getByRole('group', { name: 'Interaction tools' }).querySelectorAll('button')].filter(button => !button.closest('[data-view-controls]')).map(button => button.getAttribute('aria-label'));

it('while the model loads the viewer shows none of its own chrome, and all of it returns with the model', () => {
  frame();
  const stage = (name: string) => act(() => { fireEvent.click(document.querySelector(`[data-harness-stage="${name}"]`)!); });
  expect(screen.getByRole('group', { name: 'Interaction tools' })).toBeTruthy();
  expect(barButtons()).toEqual(['Home', 'View', 'Preview']);
  stage('finding');
  expect(screen.queryByRole('group', { name: 'Interaction tools' })).toBeNull();
  expect(document.querySelector('[data-cad-tool-stack]')).toBeNull();
  expect(barButtons()).toEqual([]);
  expect(viewportProps.current.isLoading).toBe(true);
  stage('idle');
  expect(screen.getByRole('group', { name: 'Interaction tools' })).toBeTruthy();
  expect(barButtons()).toEqual(['Home', 'View', 'Preview']);
  // With nothing to work on yet, the strip is idle together, and so are the corner's Home and View, and Preview.
  stage('unready');
  expect(strip()).toEqual(['Select', 'Draw', 'Keep', 'Pose']);
  const idle = (name: string) => (['Preview', 'Home', 'View'].includes(name) ? screen.getByRole('button', { name }) : tool(name)).hasAttribute('disabled');
  expect(['Select', 'Draw', 'Home', 'View', 'Preview'].map(idle)).toEqual([true, true, true, true, true]);
  stage('idle');
  expect(['Select', 'Draw', 'Home', 'View', 'Preview'].map(idle)).toEqual([false, false, false, false, false]);
});

it("Display and Preview are a 3D view's, as its renderer declares: a view that does not declare it has neither, not disabled ones, and a request for Preview leaves it as it is", () => {
  // Preview asked for from outside the strip, as a link or a host request would.
  const ask = () => act(() => { fireEvent.click(document.querySelector('[data-harness-ask-preview]')!); });
  // A 3D view (the harness's, declared `previewable`): Home and View under the cube, Preview ending the strip, and a
  // request enters it.
  frame();
  expect(barButtons()).toEqual(['Home', 'View', 'Preview']);
  ask();
  expect(inPreview()).toBe(true);
  cleanup();
  // A view whose renderer does not declare it (`flat.harness`, a 2D view's stand-in): neither on the
  // strip, no rule, and the same request leaves the normal view on screen, its tools up.
  frame({ name: 'flat.harness' });
  expect(barButtons()).toEqual([]);
  expect(screen.queryByRole('button', { name: 'Preview' })).toBeNull();
  expect([screen.queryByRole('button', { name: 'View' }), document.querySelector('[data-view-corner-stack]')]).toEqual([null, null]);
  expect(document.querySelector('[data-strip-rule]')).toBeNull();
  ask();
  expect(inPreview()).toBe(false);
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
  expect(barButtons()).toEqual(['Home', 'View', 'Preview']);
  expect(viewportProps.current.viewCube).toBe(true);
});

// A 3D view's settings under a file's navbar (`ViewSettingsMenu.jsx`): View, ONE menu on a desktop and a phone alike —
// the cube's row's tile on a desktop, the corner's tile alone on a phone (no cube) — a choice a submenu (Display ▸,
// Projection ▸, Background ▸), each row its name and the choice's name muted, no icon; Grid a check row of the menu
// itself; on a phone Reset view last, and no bottom sheet. The navbar's right end is Preview alone.
it("a 3D view's View: one menu of submenus, the cube's row's on a desktop and the corner's on a phone; the navbar's right end Preview alone", async () => {
  const host = testHost({ links: viewerLinks({ version: '0.7.5' }), environment: { colorScheme: 'light', platform: 'darwin' },
    files: { id: 'one', stat: async (path: string) => ({ path, name: path.split('/').pop()!, kind: 'file', extension: 'harness', size: 1 }) } });
  const viewer = (layout?: 'mobile') => <FileViewer file="/models/one.harness" host={host as any} renderers={[createHarnessRenderer({ preferences: tabSettings() })]}
    state={{}} onStateChange={() => {}} layout={layout as any} />;
  const right = () => [...document.querySelectorAll('[data-navbar-view] [data-navbar-view-controls] > *')].map(node => node.getAttribute('aria-label'));
  const openView = async () => {
    fireEvent.pointerDown(screen.getByRole('button', { name: 'View' }), { button: 0, ctrlKey: false, pointerType: 'mouse' });
    return waitFor(() => { const found = document.querySelector<HTMLElement>('[role=menu][aria-label="View"]'); expect(found).not.toBeNull(); return found!; });
  };
  // The menu's top level: each submenu's row (its id, its value, whether it shows the value's icon), the check rows, Reset view.
  const top = (menu: HTMLElement) => ({
    subs: [...menu.querySelectorAll<HTMLElement>('[data-view-sub]')].map(row => [row.getAttribute('data-view-sub'), row.querySelector('[data-view-sub-value]')!.textContent,
      Boolean(row.querySelector('svg:not(.lucide-chevron-right)'))]),
    toggles: [...menu.querySelectorAll<HTMLElement>('[data-view-toggle]')].map(row => [row.textContent, row.getAttribute('aria-checked'), Boolean(row.querySelector('svg'))]),
    reset: menu.querySelector('[data-view-reset]')?.textContent ?? null, labels: menu.querySelectorAll('[data-slot=dropdown-menu-label]').length
  });
  // A submenu opened by a press on its row: its options, each its name, whether it is ticked and whether it has its icon.
  const sub = (menu: HTMLElement, id: string) => {
    fireEvent.click(menu.querySelector<HTMLElement>(`[data-view-sub="${id}"]`)!);
    const content = document.querySelector<HTMLElement>(`[data-view-sub-content="${id}"]`)!;
    return { content, rows: [...content.querySelectorAll<HTMLElement>('[role=menuitemradio]')].map(item => [item.textContent, item.getAttribute('aria-checked'),
      Boolean(item.querySelector('svg:not(.lucide-check)'))]) };
  };
  const view = render(viewer());
  await screen.findByRole('button', { name: 'Preview' });
  expect([right(), Boolean(screen.getByRole('button', { name: 'View' }).closest('[data-view-cube-row]'))]).toEqual([['Preview'], true]);
  let menu = await openView();
  expect(top(menu)).toEqual({ subs: [['projection', 'Orthographic', false], ['display', 'Solid', false], ['background', 'Light', false]],
    toggles: [['Grid', 'false', false]], reset: null, labels: 0 });
  expect(sub(menu, 'projection').rows).toEqual([['Perspective', 'false', true], ['Orthographic', 'true', true]]);
  expect(sub(menu, 'background').rows).toEqual([['Light', 'true', true], ['Dark', 'false', true]]);
  // Grid leaves the menu open; a projection chosen closes it and switches the view.
  fireEvent.click(within(menu).getByRole('menuitemcheckbox', { name: 'Grid' }));
  expect(within(menu).getByRole('menuitemcheckbox', { name: 'Grid' }).getAttribute('aria-checked')).toBe('true');
  fireEvent.click(sub(menu, 'projection').content.querySelector<HTMLElement>('[data-display-projection="perspective"]')!);
  await waitFor(() => expect(document.querySelector('[role=menu][aria-label="View"]')).toBeNull());
  expect(screen.getByRole('button', { name: 'View' }).getAttribute('data-view-projection')).toBe('perspective');
  view.unmount();
  cleanup();
  // A phone: Preview in the navbar, no cube; View the corner's 36px tile; the same menu, its submenus the desktop's,
  // Reset view last; no Drawer.
  render(viewer('mobile'));
  await screen.findByRole('button', { name: 'Preview' });
  const tile = screen.getByRole('button', { name: 'View' });
  expect([right(), viewportProps.current.viewCube, document.querySelector('[data-zoom-pill]'), Boolean(tile.closest('[data-view-corner-tile]')), tile.className.includes('size-9')])
    .toEqual([['Preview'], false, null, true, true]);
  menu = await openView();
  expect(top(menu)).toEqual({ subs: [['projection', 'Orthographic', false], ['display', 'Solid', false], ['background', 'Light', false]],
    toggles: [['Grid', 'false', false]], reset: 'Reset view', labels: 0 });
  expect(document.querySelector('[data-vaul-drawer], [data-slot=drawer-content], [data-view-sheet]')).toBeNull();
  const modes = sub(menu, 'display');
  expect(modes.rows).toEqual([['Solid', 'true', true]]);
  fireEvent.click(sub(menu, 'projection').content.querySelector<HTMLElement>('[data-display-projection="perspective"]')!);
  await waitFor(() => expect(screen.getByRole('button', { name: 'View' }).getAttribute('data-view-projection')).toBe('perspective'));
  await waitFor(() => expect(document.querySelector('[role=menu][aria-label="View"]')).toBeNull());
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
  // Preview at the row's right (its panel's toggle is the row's first control, at its left); the view's settings stand
  // with the camera's, Home and View under the cube; the strip holds no Preview.
  const view = ['Preview'];
  expect([right(), barButtons(), document.querySelector('[role=group][aria-label="Interaction tools"] [data-view-controls]')])
    .toEqual([view, ['Home', 'View', 'Preview'], null]);
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

it("the host's notice waits for the model, then takes the top-right; Quick Edit is the bar at the view's bottom, on the strip's line", () => {
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
  expect(corner()).toEqual(['notice']);
  // Quick Edit's row: at the bottom, where the frame's measure stands it (from the stage's left, 400px at most).
  const row = document.querySelector<HTMLElement>('[data-quick-edit-row]')!;
  expect([row.querySelector('[data-quick-edit]') !== null, row.closest('[data-viewport-top-right]'), row.style.bottom, row.style.left, row.style.width])
    .toEqual([true, null, '16px', 'var(--cad-quick-edit-left, 8px)', 'var(--cad-quick-edit-width, calc(100% - 2 * 8px))']);
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

it("the row under the cube is Home and View, Preview ends the strip; View wears the projection's icon and its menu holds Projection, Display, Background and Grid, its rows no icons and its options theirs, and Grid leaves the drawing tools and kept tools in place", async () => {
  const user = userEvent.setup({ skipHover: true });
  const goHome = vi.fn(() => true);
  viewportHandle.current = { goHome };
  const { remount } = frame();
  expect([strip(), barButtons()]).toEqual([['Select', 'Draw', 'Keep', 'Pose'], ['Home', 'View', 'Preview']]);
  // No rule on the strip.
  expect(document.querySelector('[data-strip-rule]')).toBeNull();
  // The corner is the cube's and its row's: the frame stands nothing else beside it. Home brings back the view the file opened with.
  expect([...document.querySelectorAll('[data-preview-chrome] button')].filter(button => !button.closest('[data-cad-tool-groups], [data-viewport-top-right], [data-flat-panel], [data-view-top-layer]'))
    .map(named)).toEqual(['Home', 'View']);
  // The cube's 68px box 12px off the top, and under it, 4px under the box, the row centred on the drawn cube (8px in
  // from the box's right edge); its buttons 24px bare icons with a halo, on no tile; View the projection's icon, no chevron.
  expect(viewportProps.current.viewCube).toBe(true);
  const row = document.querySelector<HTMLElement>('[data-view-cube-row]')!;
  expect([row.style.right, row.style.top, row.style.bottom]).toEqual(['calc(var(--cad-viewport-corner-right, 2px) + 18px)',
    'calc(16px + 68px + var(--cad-viewport-corner-top, 0px))', '']);
  for (const button of row.querySelectorAll('button')) {
    expect([button.className.includes('size-6'), button.className.includes('text-foreground/62'), button.className.includes('drop-shadow')], named(button)).toEqual([true, true, true]);
  }
  expect(viewButton().querySelector('.lucide-chevron-down')).toBeNull();
  // The tile wears the projection on screen's icon, the one its option in Projection's submenu has.
  const glyph = (node: Element) => node.querySelector('svg:not(.lucide-check)')!.innerHTML;
  const projectionGlyph = (value: string) => glyph(viewSub('projection').querySelector(`[data-display-projection="${value}"]`)!);
  await user.click(screen.getByRole('button', { name: 'Home' }));
  expect(goHome).toHaveBeenCalledTimes(1);
  // View's menu, under the row, its end on the cube box's: each choice a submenu whose row is its name and, at its
  // right, its value (no icon), Grid a check row (no icon); the options each with its icon, the one on screen ticked.
  const menu = await openView();
  expect([menu.getAttribute('data-side'), menu.getAttribute('data-align')]).toEqual(['bottom', 'end']);
  expect(glyph(viewButton())).toBe(projectionGlyph('orthographic'));
  expect([...menu.querySelectorAll<HTMLElement>('[data-view-sub]')].map(item => [item.getAttribute('data-view-sub'), item.querySelector('[data-view-sub-value]')!.textContent,
    Boolean(item.querySelector('svg:not(.lucide-chevron-right)'))])).toEqual([['projection', 'Orthographic', false], ['display', 'Solid', false], ['background', 'Light', false]]);
  expect([gridItem().getAttribute('aria-checked'), Boolean(gridItem().querySelector('svg'))]).toEqual(['false', false]);
  const options = (id: string) => [...viewSub(id).querySelectorAll<HTMLElement>('[role=menuitemradio]')].map(item => [item.textContent, item.getAttribute('aria-checked'),
    Boolean(item.querySelector('svg:not(.lucide-check)'))]);
  expect([options('display'), options('background')]).toEqual([[['Solid', 'true', true]], [['Light', 'true', true], ['Dark', 'false', true]]]);
  // A projection chosen closes the menu and switches the view.
  fireEvent.click(viewSub('projection').querySelector<HTMLElement>('[data-display-projection="perspective"]')!);
  await waitFor(() => expect(viewMenu()).toBeNull());
  expect(viewButton().getAttribute('data-view-projection')).toBe('perspective');
  await openView();
  expect(glyph(viewButton())).toBe(projectionGlyph('perspective'));
  await closeView(user);
  await user.click(tool('Keep'));
  await user.click(tool('Draw'));
  const stack = shown();
  const controls = screen.getByRole('toolbar', { name: 'Annotation controls' });
  // Grid toggles and leaves the menu open, and the drawing tools and the kept controls stay as they were.
  await openView();
  await user.click(gridItem());
  expect(gridItem().getAttribute('aria-checked')).toBe('true');
  await closeView(user);
  expect([shown(), screen.getByRole('toolbar', { name: 'Annotation controls' })]).toEqual([stack, controls]);
  expect([tool('Draw').getAttribute('aria-pressed'), tool('Keep').getAttribute('aria-pressed')]).toEqual(['true', 'true']);
  remount();
  expect(barButtons()).toEqual(['Home', 'View', 'Preview']);
});

// Preview, entered as its tile enters it: the view covered first, then Preview under the cover.
async function enterPreview(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Preview' }));
  await screen.findByRole('button', { name: 'Exit preview' });
}
const previewSettings = () => screen.queryByRole('region', { name: 'Preview settings' });

it("three surfaces: the strip and the stack share the chrome surface, Preview's settings are more opaque, a dropdown the most; the docked panel is the chrome's colour, the navbar's, its tabs no surface of their own", async () => {
  const user = userEvent.setup({ skipHover: true });
  frame();
  expect(new Set([FLOATING_CHROME_SURFACE_CLASS, SETTINGS_PANEL_SURFACE_CLASS, FLOATING_SURFACE_CLASS]).size).toBe(3);
  const classes = (element: Element) => element.className.split(/\s+/);
  const has = (element: Element, surface: string) => surface.split(' ').every(name => classes(element).includes(name));
  expect(has(screen.getByRole('group', { name: 'Interaction tools' }), FLOATING_CHROME_SURFACE_CLASS)).toBe(true);
  fireEvent.click(tool('Keep'));
  expect(has(panel('Kept controls')!, FLOATING_CHROME_SURFACE_CLASS)).toBe(true);
  // The docked panel is chrome, not something floating: the chrome's colour, a step off the canvas, and its tabs no surface of their own.
  expect(classes(flatPanel()).includes('bg-sidebar')).toBe(true);
  expect(has(panel('Harness tree')!, FLOATING_CHROME_SURFACE_CLASS)).toBe(false);
  // There is one panel: nothing docked at the right.
  expect(document.querySelectorAll('aside').length).toBe(1);
  // View's menu, a dropdown, the most opaque.
  expect(has(await openView(), FLOATING_SURFACE_CLASS)).toBe(true);
  await closeView(user);
  await enterPreview(user);
  await user.click(screen.getByRole('button', { name: 'Preview settings' }));
  expect(has(previewSettings()!, SETTINGS_PANEL_SURFACE_CLASS)).toBe(true);
});

it("Preview is in Render: the strip, the view's controls, the stack and the panel step aside; its bar holds the file's name, its settings (Orbit and Render's) and the way out, which brings back the tool in hand and the file's own mode", async () => {
  const user = userEvent.setup({ skipHover: true });
  frame();
  await user.click(tool('Pose'));
  expect(tabNames()).toEqual(['Harness tree', 'Reference', 'Joints']);
  // The editor's viewport as the view has settled: its pending view update applied (the stand-in acknowledges it at once).
  await act(async () => { await Promise.resolve(); });
  const editor = viewportProps.current;
  await enterPreview(user);
  const chrome = document.querySelector<HTMLElement>('[data-preview-chrome]')!;
  expect([chrome.hidden, chrome.hasAttribute('inert')]).toEqual([true, true]);
  // The strip's column and Quick Edit stand in the layer over the panels, which goes with it.
  const top = document.querySelector<HTMLElement>('[data-view-top-layer]')!;
  expect([top.hidden, top.hasAttribute('inert'), top.contains(document.querySelector('[data-cad-tool-stack]'))]).toEqual([true, true, true]);
  // The strip goes with the tools view.
  expect([barButtons(), screen.queryByRole('group', { name: 'Interaction tools' })]).toEqual([[], null]);
  // The panel is the tools view's alone: hidden, its sections kept mounted, no pill. (The harness has
  // no routine, so no playbar either.)
  expect([flatPanel().hidden, screen.queryByRole('button', { name: 'Show panel' })]).toEqual([true, null]);
  expect(panel('Harness position')).not.toBeNull();
  expect(screen.queryByRole('toolbar', { name: 'Animation playback' })).toBeNull();
  // Its bar, along the view's top edge: the file's name, then its settings and the way out, an X.
  expect([previewBar()!.querySelector('[data-preview-name]')!.textContent, cornerButtons()]).toEqual(['panel.harness', ['Preview settings', 'Exit preview']]);
  expect(previewBar()!.className).toMatch(/\bh-10\b/);
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
  expect(barButtons()).toEqual(['Home', 'View', 'Preview']);
  // The tools view is as it was: the panel back, the tool in hand, its section's tab with it.
  expect(flatPanel().hidden).toBe(false);
  expect(tabNames()).toEqual(['Harness tree', 'Reference', 'Joints']);
  expect(tool('Pose').getAttribute('aria-pressed')).toBe('true');
  // What was set in Preview is the file's Render settings: the next visit has it.
  act(() => { fireEvent.click(document.querySelector('[data-harness-ask-preview]')!); });
  expect(inPreview()).toBe(true);
  await user.click(within(previewBar()!).getByRole('button', { name: 'Preview settings' }));
  expect(floor().getAttribute('aria-checked')).toBe('false');
  await user.click(within(previewBar()!).getByRole('button', { name: 'Exit preview' }));
  expect(flatPanel().hidden).toBe(false);
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

it("Preview settings is pressed while its panel is open and a second press closes it; the panel slides in and out from the view's right edge", async () => {
  const user = userEvent.setup({ skipHover: true });
  frame();
  await enterPreview(user);
  const button = () => within(previewBar()!).getByRole('button', { name: 'Preview settings' });
  const panel = () => document.querySelector<HTMLElement>('[data-preview-panel]')!;
  // Closed: off the edge, out of reach and out of the accessibility tree; the button not pressed.
  expect([button().getAttribute('aria-pressed'), previewSettings(), panel().hasAttribute('inert'), panel().className]).toEqual(
    ['false', null, true, expect.stringContaining('translate-x-[calc(100%+1rem)]')]);
  expect(panel().className).toContain(SIDEBAR_SLIDE_CLASS);
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
  await user.click(tool('Draw'));
  expect(tool('Draw').getAttribute('aria-pressed')).toBe('true');
  act(() => { document.querySelector<HTMLElement>('[data-slot="cad-file-view"]')!.focus(); });
  await user.keyboard('{Escape}');
  expect([tool('Draw').getAttribute('aria-pressed'), tool('Select').getAttribute('aria-pressed')]).toEqual(['false', 'true']);
});

it("what a person uses is counted for the host by name: a tool taken up and how long it was up, Display's Grid, Preview and its seconds, never the tool the file opened in or its return from Preview", async () => {
  let now = 5_000_000;
  vi.spyOn(Date, 'now').mockImplementation(() => now);
  const reports: { control: string; count: number; seconds: number }[][] = [];
  const user = userEvent.setup({ skipHover: true });
  const view = frame({ usage: counts => reports.push(counts) });
  fireEvent.click(tool('Draw'));
  now += 5_000;
  fireEvent.click(tool('Select'));
  await openView();
  await user.click(gridItem());
  await closeView(user);
  await enterPreview(user);
  // Preview's bar: its settings opened (a use, no seconds), then its way out.
  await user.click(within(previewBar()!).getByRole('button', { name: 'Preview settings', exact: true }));
  now += 3_000;
  await user.click(screen.getByRole('button', { name: 'Exit preview' }));
  expect(reports).toEqual([]); // said at most every minute, or as the view goes
  view.unmount();
  const said = Object.fromEntries(reports.flat().map(({ control, ...counts }) => [control, counts]));
  expect(said).toEqual({ draw: { count: 1, seconds: 5 }, display_grid: { count: 1, seconds: 0 }, preview: { count: 1, seconds: 3 },
    preview_settings: { count: 1, seconds: 0 },
    // Select is counted once: the person took it up again; the file opened in it, and Preview gave it back.
    select: { count: 1, seconds: 0 } });
  vi.restoreAllMocks();
});

it("the model area follows the viewport's Background, not the app's theme: Light in a dark app draws the scene, the cube and what stands on the picture light, the chrome dark; Dark from View's Background, and Light again", async () => {
  const user = userEvent.setup({ skipHover: true });
  const { preferences } = frame({ appearance: { colorScheme: 'dark' } });
  const box = () => document.querySelector<HTMLElement>('[data-cad-canvas-box]')!;
  const corner = () => document.querySelector<HTMLElement>('[data-view-corner]')!;
  // Light, the default: the scene's look, the cube's axes and the canvas box's tokens light; the strip (chrome) not scoped.
  // Unset in the tab's settings (a host that hands over less): Light.
  expect(preferences.getSnapshot().viewportBackground).toBeUndefined();
  expect([viewportProps.current.appearance, box().classList.contains('light'), corner().classList.contains('light'),
    document.querySelector('[data-viewport-scheme]')!.getAttribute('data-viewport-scheme')]).toEqual(['light', true, true, 'light']);
  expect(screen.getByRole('group', { name: 'Interaction tools' }).closest('.light')).toBeNull();
  // The light viewport's scene stands on its gradient, top to bottom, whatever the app's theme.
  expect([viewportProps.current.themeSettings.background.type, viewportProps.current.themeSettings.background.solidColor]).toEqual(['linear', '#dfe2e5']);
  // View's Background: Dark, then Light again, each the person's, kept in the tab's settings.
  await openView();
  fireEvent.click(backgroundItem('dark')!);
  await waitFor(() => expect(viewportProps.current.appearance).toBe('dark'));
  expect([preferences.getSnapshot().viewportBackground, box().classList.contains('dark'), viewportProps.current.themeSettings.background]).toEqual(['dark', true,
    expect.objectContaining({ type: 'solid', solidColor: '#1e1e1e' })]);
  await openView();
  expect(backgroundItem('theme')).toBeNull();
  fireEvent.click(backgroundItem('light')!);
  await waitFor(() => expect(preferences.getSnapshot().viewportBackground).toBe('light'));
  await waitFor(() => expect(viewportProps.current.appearance).toBe('light'));
});
