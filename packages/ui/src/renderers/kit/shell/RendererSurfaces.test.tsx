import React, { forwardRef, useImperativeHandle, useRef } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

// The shell's surfaces a RENDERER fills — the viewport menu, Quick Edit, the camera-settled
// report — driven end to end through the real RendererShell and useRendererShell under the shell
// harness (a renderer that uses all three), with only the WebGL viewport replaced. The stand-in
// hands the overlay the same viewport context the real one does (a host the pointer events arrive
// on, a runtime whose renderer's canvas is the scene's), and records the props the shell wired, so
// the camera reports reach the renderer through exactly the callbacks the real viewport calls.
// The viewport's own half of those reports (a resize, a preview camera) is ShellViewport.test.tsx.
const viewport = vi.hoisted(() => ({ props: null as any, resetView: vi.fn(() => true) }));
vi.mock('../../../../dist/renderers/kit/shell/ShellViewport.js', () => ({
  default: forwardRef(function StandInViewport(props: any, ref) {
    viewport.props = props;
    useImperativeHandle(ref, () => ({ captureScreenshotBlob: async () => new Blob(['pixels'], { type: 'image/png' }), resetView: viewport.resetView }));
    const hostRef = useRef<HTMLDivElement | null>(null);
    const runtimeRef = useRef<any>(null);
    const context = { hostRef, runtimeRef, mountRef: hostRef, viewerReadyTick: 1, commitScene: () => true };
    return <div ref={hostRef} data-stand-in-viewport="">
      <canvas ref={canvas => { runtimeRef.current = canvas ? { renderer: { domElement: canvas } } : null; }} />
      {typeof props.children === 'function' ? props.children(context) : props.children}
    </div>;
  })
}));
import HarnessRenderer from '../../../../dist/renderers/shell-harness/HarnessRenderer.js';
import { ViewerHostContext } from '../../../../dist/host/context.js';
import { testHost } from '../../../../dist/host/testing/host.js';

beforeEach(() => {
  viewport.resetView.mockClear();
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); viewport.props = null; });

// The navbar FileViewer hands a renderer: where the view's controls go.
function navbarSlot() {
  const slot = document.createElement('div');
  slot.setAttribute('data-test-navbar', '');
  document.body.append(slot);
  return slot;
}
afterEach(() => document.querySelectorAll('[data-test-navbar]').forEach(slot => slot.remove()));
function mount(host = testHost(), state?: unknown) {
  const save = vi.fn();
  const navigation = vi.fn();
  let settings: any = { toolStack: { panels: {}, collapsed: {} } };
  const listeners = new Set<() => void>();
  const preferences = { getSnapshot: () => settings, subscribe: (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener); },
    update: (patch: any) => { settings = { ...settings, ...patch }; listeners.forEach(listener => listener()); } };
  const props = { source: { id: 'one', rootName: 'one' }, file: { path: 'one.harness', name: 'one.harness', kind: 'file' }, document: null,
    openPanel: '', panelSlot: null, navbarSlot: navbarSlot(), onPanelOpen() {}, onReady() {}, onOpenFile() {}, appearance: { colorScheme: 'light' },
    state, onStateChange: save, onNavigationActionsChange: navigation, reload() {}, data: { services: { preferences } } };
  const view = render(<ViewerHostContext.Provider value={host}><HarnessRenderer {...(props as any)} /></ViewerHostContext.Provider>);
  const canvas = view.container.querySelector('[data-stand-in-viewport] > canvas') as HTMLCanvasElement;
  const overlay = (name: string) => view.container.querySelector(`[data-harness-${name}]`)!.textContent;
  return { ...view, canvas, overlay, save, navigation };
}

// A secondary press as the browser delivers one: down, (moves), up, all on the canvas.
function pointer(target: Element, type: string, init: Record<string, unknown>) {
  const event = new Event(type, { bubbles: true, cancelable: true });
  Object.assign(event, { pointerId: 1, pointerType: 'mouse', buttons: 0, shiftKey: false, ...init });
  act(() => { target.dispatchEvent(event); });
}
function secondaryTap(target: Element, x: number, y: number, init: Record<string, unknown> = {}) {
  pointer(target, 'pointerdown', { button: 2, buttons: 2, clientX: x, clientY: y, ...init });
  pointer(target, 'pointerup', { button: 2, clientX: x, clientY: y, ...init });
}
const menuAnchor = () => document.querySelector('button[aria-hidden="true"][style*="position: fixed"]') as HTMLElement | null;
// The harness's selection: a press it notes through its menu, which Quick Edit carries as a reference.
function pick(canvas: Element) {
  secondaryTap(canvas, 300, 200);
  act(() => { fireEvent.click(screen.getByRole('menuitem', { name: 'Note the press' })); });
}

it('a secondary tap on the canvas opens the renderer\'s own items at the press, in the renderer\'s state, and an item acts on that press', () => {
  const { canvas, overlay } = mount();
  secondaryTap(canvas, 300, 200);
  const menu = screen.getByRole('menu');
  expect(within(menu).getAllByRole('menuitem').map(item => item.textContent)).toEqual(['Note the press', 'Clear the note']);
  // It opens AT the press: the anchor is the press point, not a corner.
  expect([menuAnchor()?.style.left, menuAnchor()?.style.top]).toEqual(['300px', '200px']);
  // The second item is disabled until the first has been taken: the renderer's state reaching the menu.
  expect(screen.getByRole('menuitem', { name: 'Clear the note' }).hasAttribute('data-disabled')).toBe(true);
  fireEvent.keyDown(menu, { key: 'Escape' });
  expect(screen.queryByRole('menu')).toBeNull();
  // A second press elsewhere opens it there instead.
  secondaryTap(canvas, 520, 60);
  expect([menuAnchor()?.style.left, menuAnchor()?.style.top]).toEqual(['520px', '60px']);
  act(() => { fireEvent.click(screen.getByRole('menuitem', { name: 'Note the press' })); });
  expect(screen.queryByRole('menu')).toBeNull();
  expect(overlay('menu-note')).toBe('520,60');
  secondaryTap(canvas, 520, 60);
  expect(screen.getByRole('menuitem', { name: 'Clear the note' }).hasAttribute('data-disabled')).toBe(false);
});

it('a press the renderer has nothing to say about, a secondary drag, or a press off the canvas opens no menu', () => {
  const { canvas, container } = mount();
  // Shift: the harness answers null, which is "nothing to offer here".
  secondaryTap(canvas, 300, 200, { shiftKey: true });
  expect(screen.queryByRole('menu')).toBeNull();
  // A secondary DRAG is the camera's (a pan), past the tap slop.
  pointer(canvas, 'pointerdown', { button: 2, buttons: 2, clientX: 300, clientY: 200 });
  pointer(canvas, 'pointermove', { buttons: 2, clientX: 390, clientY: 240 });
  pointer(canvas, 'pointerup', { button: 2, clientX: 390, clientY: 240 });
  expect(screen.queryByRole('menu')).toBeNull();
  // A control drawn over the canvas keeps its own presses.
  secondaryTap(container.querySelector('[data-harness-overlay]')!, 300, 200);
  expect(screen.queryByRole('menu')).toBeNull();
  // And a plain tap still opens it: the gesture above was the only difference.
  secondaryTap(canvas, 300, 200);
  expect(screen.getByRole('menu')).toBeTruthy();
});

it('Quick Edit is there once something is picked, with what the host can do, is put away in Preview, and nothing sits at the bottom', () => {
  const destination = { kind: 'composer', available: true } as const;
  const send = vi.fn(async () => ({ status: 'sent' as const, partIds: [] }));
  const { container, canvas } = mount(testHost({ promptContext: { getSnapshot: () => destination, subscribe: () => () => {}, deliver: async () => ({ status: 'added', partIds: [] }), send } }));
  expect(container.querySelector('[data-viewport-bottom-actions]')).toBeNull();
  // Nothing picked, nothing drawn: no Quick Edit at all, not even a button.
  expect(container.querySelector('[data-quick-edit-box]')).toBeNull();
  expect(screen.queryByRole('button', { name: 'Quick Edit' })).toBeNull();
  pick(canvas);
  const box = screen.getByRole('region', { name: 'Quick Edit' });
  expect(box.querySelector('[data-quick-edit-chip="references"]')!.textContent).toBe('1 ref');
  expect(within(box).getAllByRole('button').map(button => button.getAttribute('aria-label') || button.textContent)).toEqual(['Close Quick Edit', 'Copy Prompt', 'Queue', 'Send']);
  // Its X clears the pick, as a press on the background would, and goes with it.
  fireEvent.click(within(box).getByRole('button', { name: 'Close Quick Edit' }));
  expect(screen.queryByRole('region', { name: 'Quick Edit' })).toBeNull();
  pick(canvas);
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Preview' })); });
  expect(container.querySelector('[data-preview-chrome]')!.contains(container.querySelector('[data-quick-edit]'))).toBe(true);
  expect(container.querySelector('[data-preview-chrome]')!.hasAttribute('inert')).toBe(true);
});

it('a sketch opens Quick Edit, which sends the file, the note and the view with its ink through the port', async () => {
  const destination = { kind: 'composer', available: true } as const;
  const send = vi.fn(async (_context: unknown) => ({ status: 'sent' as const, partIds: [] }));
  const host = testHost({ promptContext: { getSnapshot: () => destination, subscribe: () => () => {}, deliver: async () => ({ status: 'added', partIds: [] }), send } as any });
  mount(host);
  fireEvent.click(screen.getByRole('button', { name: 'Draw' }));
  // The surface clears its ink as the viewport's does, saying so once it is gone.
  const clearInk = vi.fn(() => viewport.props.drawing.onContentChange(false, 0));
  act(() => viewport.props.drawing.onReady({ clear: clearInk }));
  act(() => viewport.props.drawing.onContentChange(true, 1));
  const box = screen.getByRole('region', { name: 'Quick Edit' });
  expect(box.querySelector('[data-quick-edit-chip="sketch"]')).not.toBeNull();
  const note = within(box).getByRole('textbox', { name: 'Describe your changes' });
  expect(document.activeElement).toBe(note);
  fireEvent.change(note, { target: { value: 'Add a boss here.' } });
  fireEvent.keyDown(note, { key: 'Enter' });
  await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
  const context = send.mock.calls[0][0] as any;
  expect(context.parts.map((part: any) => part.kind)).toEqual(['text', 'reference', 'attachment']);
  expect((await context.parts[2].content).type).toBe('image/png');
  // Sent, the note goes with its sketch.
  await waitFor(() => expect(screen.queryByRole('region', { name: 'Quick Edit' })).toBeNull());
  expect(clearInk).toHaveBeenCalledTimes(1);
});

it('clipboard destinations keep the snapshot action, and Draw copies its ink from the foot of its controls', async () => {
  const destination = { kind: 'clipboard', available: true } as const;
  const writeImage = vi.fn(async () => {}), deliver = vi.fn();
  const { navigation } = mount(testHost({
    promptContext: { getSnapshot: () => destination, subscribe: () => () => {}, deliver } as any,
    clipboard: { writeText: async () => {}, readText: async () => '', writeImage },
  }));
  const snapshot = navigation.mock.calls.at(-1)![0];
  expect(snapshot.map((action: any) => action.label)).toEqual(['Take snapshot']);
  act(() => snapshot[0].onInvoke());
  await waitFor(() => expect(writeImage).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole('button', { name: 'Draw' }));
  const controls = () => screen.getByRole('region', { name: 'Drawing controls' });
  expect(within(controls()).queryByRole('button', { name: /^Copy/ })).toBeNull();
  act(() => viewport.props.drawing.onContentChange(true, 1));
  fireEvent.click(within(controls()).getByRole('button', { name: 'Copy Drawing' }));
  await waitFor(() => expect(writeImage).toHaveBeenCalledTimes(2));
  // A clipboard destination's Quick Edit copies its prompt, and nothing else.
  expect(within(screen.getByRole('region', { name: 'Quick Edit' })).queryByRole('button', { name: 'Queue' })).toBeNull();
  expect(deliver).not.toHaveBeenCalled();
});

it('a host with no prompt workflow gets no snapshot, and Quick Edit copies a prompt: left out, not disabled', () => {
  // The test host composes `unavailablePromptContext`.
  const { navigation, canvas } = mount();
  expect(navigation.mock.calls.flatMap(([actions]) => actions)).toEqual([]);
  pick(canvas);
  expect(within(screen.getByRole('region', { name: 'Quick Edit' })).getAllByRole('button').map(button => button.getAttribute('aria-label') || button.textContent))
    .toEqual(['Close Quick Edit', 'Copy Prompt']);
});

it('the renderer is told the camera settled, through what the viewport reports: a recorded move and its own settle', () => {
  const { overlay } = mount();
  expect(overlay('camera-settles')).toBe('0');
  // A camera that moved and was recorded (`onPerspectiveChange`) is a settle.
  act(() => { viewport.props.onPerspectiveChange({ position: [1, 2, 3], target: [0, 0, 0], up: [0, 0, 1], zoom: 1, projection: 'orthographic' }); });
  expect(overlay('camera-settles')).toBe('1');
  // So is the viewport's own settle (a preview camera, a resize), which records nothing.
  act(() => { viewport.props.onCameraSettled(); });
  expect(overlay('camera-settles')).toBe('2');
  // Preview: the camera that moves records no perspective, and the renderer still hears of it.
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Preview' })); });
  expect(viewport.props.previewMode).toBe(true);
  act(() => { viewport.props.onPerspectiveChange({ position: [4, 5, 6], target: [0, 0, 0], up: [0, 0, 1], zoom: 2, projection: 'orthographic' }); });
  act(() => { viewport.props.onCameraSettled(); });
  expect(overlay('camera-settles')).toBe('4');
});

// The full reset crosses the renderer callback and the shell's tool/preview
// lifecycle; it must reach the camera only after those changes commit.
