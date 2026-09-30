import React, { forwardRef, useImperativeHandle, useRef } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

// The shell's surfaces a RENDERER fills — the viewport menu, the bottom action, the camera-settled
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

function mount(host = testHost(), state?: unknown) {
  const save = vi.fn();
  const navigation = vi.fn();
  let settings: any = { toolStack: { panels: {}, collapsed: {} } };
  const listeners = new Set<() => void>();
  const preferences = { getSnapshot: () => settings, subscribe: (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener); },
    update: (patch: any) => { settings = { ...settings, ...patch }; listeners.forEach(listener => listener()); } };
  const props = { source: { id: 'one', rootName: 'one' }, file: { path: 'one.harness', name: 'one.harness', kind: 'file' }, document: null,
    openPanel: '', panelSlot: null, onPanelOpen() {}, onReady() {}, onOpenFile() {}, appearance: { colorScheme: 'light' },
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

it('the renderer\'s bottom action shows its count when the reference does not fit, the whole reference when it does, and no native tooltip', () => {
  // jsdom has no layout: the button's width is 280px and a label is 7px a character, so the
  // decision is the measured one (`ViewportBottomAction.jsx`'s ruler), not a string length rule.
  const scrollWidth = vi.spyOn(HTMLElement.prototype, 'scrollWidth', 'get').mockImplementation(function (this: HTMLElement) { return (this.textContent || '').length * 7; });
  const clientWidth = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(() => 280);
  try {
    const { container } = mount();
    const action = () => container.querySelector('[data-harness-bottom-action]') as HTMLElement;
    // The renderer's `render` drew the control; what it says is the count, not a cut-off reference.
    expect(action().getAttribute('title')).toBeNull();
    expect(action().querySelector('span')!.textContent).toBe('Copy 1 reference');
    act(() => { fireEvent.click(action()); });
    // The short reference fits (36 characters): shown whole, still with no tooltip.
    expect(action().querySelector('span')!.textContent).toBe('#harness_document/triangle_face_0001');
    expect(action().getAttribute('title')).toBeNull();
  } finally { scrollWidth.mockRestore(); clientWidth.mockRestore(); }
});

it('one shared Add To Prompt action is the only bottom control, independent of the active tool and absent in Preview', () => {
  const destination = { kind: 'composer', available: true } as const;
  const { container } = mount(testHost({ promptContext: { getSnapshot: () => destination, subscribe: () => () => {}, deliver: async () => ({ status: 'added', partIds: [] }) } }));
  const action = () => container.querySelector('[data-viewport-bottom-actions]') as HTMLElement | null;
  expect(action()).not.toBeNull();
  expect(within(action()!).getAllByRole('button')).toHaveLength(1);
  expect(within(action()!).getByRole('button', { name: 'Add To Prompt' }).className).toContain('bg-white');
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Draw' })); });
  expect(within(action()!).getAllByRole('button')).toHaveLength(1);
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Preview' })); });
  expect(action()).toBeNull();
  expect(container.querySelector('[data-file-navigation-overlay]')).toBeNull();
});

it('Add To Prompt sends a screenshot and tool context through the composer port', async () => {
  const deliver = vi.fn(async (_context: unknown) => ({ status: 'added' as const }));
  const writeImage = vi.fn(async () => {});
  const destination = { kind: 'composer', available: true } as const;
  const host = testHost({
    promptContext: { getSnapshot: () => destination, subscribe: () => () => {}, deliver } as any,
    clipboard: { writeText: async () => {}, readText: async () => '', writeImage },
  });
  const { container } = mount(host);
  const button = within(container.querySelector('[data-viewport-bottom-actions]') as HTMLElement).getByRole('button', { name: 'Add To Prompt' });
  expect((button as HTMLButtonElement).disabled).toBe(false);
  fireEvent.click(button);
  await waitFor(() => expect(deliver).toHaveBeenCalledTimes(1));
  const context = deliver.mock.calls[0][0] as any;
  expect(context.parts.map((part: any) => part.kind)).toEqual(['reference', 'text', 'attachment']);
  expect((await context.parts[2].content).type).toBe('image/png');
  expect(writeImage).not.toHaveBeenCalled();
});

it('clipboard destinations retain the snapshot action and Copy Drawing with ink, without Add To Prompt', async () => {
  const destination = { kind: 'clipboard', available: true } as const;
  const writeImage = vi.fn(async () => {}), deliver = vi.fn();
  const { container, navigation } = mount(testHost({
    promptContext: { getSnapshot: () => destination, subscribe: () => () => {}, deliver } as any,
    clipboard: { writeText: async () => {}, readText: async () => '', writeImage },
  }));
  expect(screen.queryByRole('button', { name: 'Add To Prompt' })).toBeNull();
  // The bottom row is the renderer's own action (the harness's reference), not a prompt one.
  expect(container.querySelector('[data-viewport-bottom-actions] [data-harness-bottom-action]')).not.toBeNull();
  const snapshot = navigation.mock.calls.at(-1)![0];
  expect(snapshot.map((action: any) => action.label)).toEqual(['Take snapshot']);
  act(() => snapshot[0].onInvoke());
  await waitFor(() => expect(writeImage).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole('button', { name: 'Draw' }));
  expect(container.querySelector('[data-viewport-bottom-actions]')).toBeNull();
  act(() => viewport.props.drawing.onContentChange(true));
  const copy = screen.getByRole('button', { name: /Copy Drawing/ });
  expect(copy.className).toContain('bg-primary/85');
  expect(copy.className).not.toContain('bg-white');
  fireEvent.click(copy);
  await waitFor(() => expect(writeImage).toHaveBeenCalledTimes(2));
  expect(deliver).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
  expect(container.querySelector('[data-viewport-bottom-actions]')).toBeNull();
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
it('Reset view clears inspection edits, preserves appearance and exits Preview before resetting the camera', () => {
  const appearance = { mode: 'xray', edges: { enabled: true, visibility: 'all' } };
  const { canvas, overlay, unmount, save } = mount(testHost(), { version: 2, display: {
    ...appearance, clip: { enabled: true, axis: 'x', offset: 0.3 }, exploded: { enabled: true, amount: 0.4 }
  } });
  secondaryTap(canvas, 300, 200);
  fireEvent.click(screen.getByRole('menuitem', { name: 'Note the press' }));
  expect(overlay('menu-note')).toBe('300,200');
  fireEvent.click(screen.getByRole('button', { name: 'Draw' }));
  expect(viewport.props.drawingEnabled).toBe(true);
  const clearInk = vi.fn();
  act(() => viewport.props.drawing.onReady({ clear: clearInk }));
  viewport.resetView.mockImplementationOnce(() => {
    expect(viewport.props.drawingEnabled).toBe(false);
    expect(overlay('menu-note')).toBe('');
    return true;
  });
  fireEvent.click(screen.getByRole('button', { name: 'Reset view' }));
  expect(clearInk).toHaveBeenCalledTimes(1);
  expect(viewport.resetView).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
  expect(viewport.props.previewMode).toBe(true);
  viewport.resetView.mockImplementationOnce(() => {
    expect(viewport.props.previewMode).toBe(false);
    return true;
  });
  fireEvent.click(screen.getByRole('button', { name: 'Reset view' }));
  expect(viewport.resetView).toHaveBeenCalledTimes(2);
  expect(screen.getByRole('button', { name: 'Preview' })).toBeTruthy();
  unmount();
  const display = save.mock.calls.at(-1)![0].display;
  expect(display).toMatchObject(appearance);
  expect(display.clip?.enabled ?? false).toBe(false);
  expect(display.exploded?.enabled ?? false).toBe(false);
  expect(display.clip?.offset ?? 0).toBe(0);
  expect(display.exploded?.amount ?? 0).toBe(0);
});
