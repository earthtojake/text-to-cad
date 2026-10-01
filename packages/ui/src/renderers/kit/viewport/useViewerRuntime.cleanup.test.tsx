import { cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';

// A renderer that does nothing: the hook only needs its canvas and somewhere to call.
const renderers: any[] = [];
vi.mock('@text-to-cad/core/common/webglRenderer.js', () => ({
  createCadWebGlRenderer: () => {
    const domElement = document.createElement('canvas');
    const target: any = { domElement, shadowMap: {}, dispose: vi.fn(), getPixelRatio: () => 1 };
    const renderer = new Proxy(target, { get: (t, key) => (key in t ? t[key] : (t[key] = vi.fn())) });
    renderers.push(renderer);
    return renderer;
  },
}));
const buffer = { fail: false };
vi.mock('./viewportBuffer.js', () => ({
  createViewportBuffer: () => {
    if (buffer.fail) throw new Error('buffer failed');
    return { request: vi.fn(), dispose: vi.fn() };
  },
}));
vi.mock('./framePresentation.js', () => ({ createFramePresentation: () => ({ dispose: vi.fn() }) }));
// The failure under test: initialisation throws after the window's resize listener is registered.
const init = { fail: true };
vi.mock('../camera/zoomPivotReanchor.js', async (original) => {
  const actual = await original<typeof import('../camera/zoomPivotReanchor.js')>();
  return {
    ...actual,
    createZoomPivotReanchor: (...args: Parameters<typeof actual.createZoomPivotReanchor>) => {
      if (init.fail) throw new Error('init failed midway');
      return actual.createZoomPivotReanchor(...args);
    },
  };
});

import { useViewerRuntime } from './useViewerRuntime.js';

class FakeResizeObserver {
  static live = new Set<FakeResizeObserver>();
  constructor(_callback: () => void) {}
  observe() { FakeResizeObserver.live.add(this); }
  disconnect() { FakeResizeObserver.live.delete(this); }
}

beforeEach(() => {
  renderers.length = 0;
  init.fail = true;
  buffer.fail = false;
  FakeResizeObserver.live.clear();
  vi.stubGlobal('ResizeObserver', FakeResizeObserver);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function options(mount: HTMLElement, extra: Record<string, unknown> = {}) {
  const noop = vi.fn();
  return new Proxy({
    mountRef: { current: mount },
    runtimeRef: { current: null },
    previewModeRef: { current: false },
    setError: vi.fn(),
    setViewerReadyTick: vi.fn(),
    getViewerThemeValue: (_theme: unknown, _key: string, fallback: unknown) => fallback,
    getPixelRatioCap: (value: number) => value,
    DEFAULT_LIGHTING: { toneMappingExposure: 1 },
    IDLE_PIXEL_RATIO_CAP: 2,
    INTERACTION_PIXEL_RATIO_CAP: 1,
    onInitializationError: vi.fn(),
    ...extra,
  } as Record<string, unknown>, { get: (target, key: string) => (key in target ? target[key] : noop) });
}

test('a viewer whose initialisation throws midway releases what it had already registered', async () => {
  const added: Array<[string, unknown]> = [];
  const removed: Array<[string, unknown]> = [];
  const add = window.addEventListener.bind(window);
  const remove = window.removeEventListener.bind(window);
  vi.spyOn(window, 'addEventListener').mockImplementation(((type: string, listener: any, opts?: any) => { added.push([type, listener]); add(type, listener, opts); }) as any);
  vi.spyOn(window, 'removeEventListener').mockImplementation(((type: string, listener: any, opts?: any) => { removed.push([type, listener]); remove(type, listener, opts); }) as any);
  const mount = document.createElement('div');
  document.body.appendChild(mount);
  const onInitializationError = vi.fn();
  const hook = renderHook(() => useViewerRuntime({ ...(options(mount) as object), onInitializationError } as any));
  await waitFor(() => expect(onInitializationError).toHaveBeenCalled());
  const resize = added.filter(([type]) => type === 'resize');
  expect(resize).toHaveLength(1);
  // The failed start let go of its observer at once; unmounting finds nothing left to do.
  expect(FakeResizeObserver.live.size).toBe(0);

  hook.unmount();

  expect(removed).toContainEqual(resize[0]);
  expect(FakeResizeObserver.live.size).toBe(0);
  // And the renderer the failed start created is let go with its canvas.
  expect(renderers).toHaveLength(1);
  expect(renderers[0].dispose).toHaveBeenCalled();
  expect(mount.contains(renderers[0].domElement)).toBe(false);
});

test('a viewer whose runtime ref was cleared under it still releases its listeners, observer and renderer', async () => {
  init.fail = false;
  const added: Array<[string, unknown]> = [];
  const removed: Array<[string, unknown]> = [];
  const add = window.addEventListener.bind(window);
  const remove = window.removeEventListener.bind(window);
  vi.spyOn(window, 'addEventListener').mockImplementation(((type: string, listener: any, opts?: any) => { added.push([type, listener]); add(type, listener, opts); }) as any);
  vi.spyOn(window, 'removeEventListener').mockImplementation(((type: string, listener: any, opts?: any) => { removed.push([type, listener]); remove(type, listener, opts); }) as any);
  const mount = document.createElement('div');
  document.body.appendChild(mount);
  const base = options(mount) as { runtimeRef: { current: any } };
  const hook = renderHook(() => useViewerRuntime(base as any));
  await waitFor(() => expect(base.runtimeRef.current).not.toBeNull());
  const listeners = added.filter(([type]) => type === 'resize' || type === 'keydown');
  expect(listeners.length).toBeGreaterThanOrEqual(2);

  base.runtimeRef.current = null;
  hook.unmount();

  for (const listener of listeners) expect(removed).toContainEqual(listener);
  expect(FakeResizeObserver.live.size).toBe(0);
  expect(renderers[0].dispose).toHaveBeenCalled();
});

// What the real macrotask queue needs to finish the hook's dynamic imports, without sleeping.
async function until(condition: () => boolean) {
  for (let turn = 0; turn < 10_000 && !condition(); turn += 1) await new Promise((resolve) => setImmediate(resolve));
  expect(condition()).toBe(true);
}

test('a renderer whose start throws before it is mounted still lets go of its context and canvas', async () => {
  buffer.fail = true;
  const mount = document.createElement('div');
  document.body.appendChild(mount);
  const onInitializationError = vi.fn();
  const hook = renderHook(() => useViewerRuntime({ ...(options(mount) as object), onInitializationError } as any));
  await waitFor(() => expect(onInitializationError).toHaveBeenCalled());
  hook.unmount();

  expect(renderers).toHaveLength(1);
  expect(renderers[0].dispose).toHaveBeenCalled();
  expect(renderers[0].forceContextLoss).toHaveBeenCalledTimes(1);
  expect(mount.querySelector('canvas')).toBeNull();
});

test('a failed start releases its viewer at once, before anything unmounts', async () => {
  const mount = document.createElement('div');
  document.body.appendChild(mount);
  const onInitializationError = vi.fn();
  const added: Array<[string, unknown]> = [];
  const removed: Array<[string, unknown]> = [];
  const add = window.addEventListener.bind(window);
  const remove = window.removeEventListener.bind(window);
  vi.spyOn(window, 'addEventListener').mockImplementation(((type: string, listener: any, opts?: any) => { added.push([type, listener]); add(type, listener, opts); }) as any);
  vi.spyOn(window, 'removeEventListener').mockImplementation(((type: string, listener: any, opts?: any) => { removed.push([type, listener]); remove(type, listener, opts); }) as any);
  renderHook(() => useViewerRuntime({ ...(options(mount) as object), onInitializationError } as any));
  await waitFor(() => expect(onInitializationError).toHaveBeenCalled());

  const resize = added.filter(([type]) => type === 'resize');
  expect(resize).toHaveLength(1);
  expect(removed).toContainEqual(resize[0]);
  expect(renderers[0].dispose).toHaveBeenCalled();
  expect(mount.querySelector('canvas')).toBeNull();
});

test('interaction timers are cleared when the start is released without its runtime', async () => {
  init.fail = false;
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  const mount = document.createElement('div');
  document.body.appendChild(mount);
  const base = options(mount) as { runtimeRef: { current: any } };
  const hook = renderHook(() => useViewerRuntime(base as any));
  await until(() => base.runtimeRef.current !== null);
  // A wheel tick starts an interaction: the idle-quality restore timer is armed (and the first
  // frame's fallback timer already is).
  renderers[0].domElement.dispatchEvent(new WheelEvent('wheel', { deltaY: 10 }));
  expect(vi.getTimerCount()).toBeGreaterThan(0);

  base.runtimeRef.current = null;
  hook.unmount();

  expect(vi.getTimerCount()).toBe(0);
});

test('the idle follow-up timer scheduled by the restore is cleared when the start is released', async () => {
  init.fail = false;
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  const mount = document.createElement('div');
  document.body.appendChild(mount);
  const base = options(mount) as { runtimeRef: { current: any } };
  const hook = renderHook(() => useViewerRuntime(base as any));
  await until(() => base.runtimeRef.current !== null);
  // A render type that restores its own idle quality: the restore timer then nests a second
  // timer (the pixel-ratio raise) instead of applying it at once.
  const onIdleQualityRestore = vi.fn();
  base.runtimeRef.current.onIdleQualityRestore = onIdleQualityRestore;
  renderers[0].domElement.dispatchEvent(new WheelEvent('wheel', { deltaY: 10 }));
  // Step to the restore timer, no further: the follow-up it schedules has not run yet.
  for (let step = 0; step < 20 && onIdleQualityRestore.mock.calls.length === 0; step += 1) vi.advanceTimersToNextTimer();
  expect(onIdleQualityRestore).toHaveBeenCalledTimes(1);
  expect(vi.getTimerCount()).toBeGreaterThan(0);

  base.runtimeRef.current = null;
  hook.unmount();

  expect(vi.getTimerCount()).toBe(0);
});

test('a rebuilt viewer forces its old, still-live context lost, with the rebuilding listeners already off', async () => {
  init.fail = false;
  const mount = document.createElement('div');
  document.body.appendChild(mount);
  const onContextRestored = vi.fn();
  const base = options(mount, { onContextRestored }) as any;
  const hook = renderHook(() => useViewerRuntime(base));
  await until(() => base.runtimeRef.current !== null);
  const canvas = renderers[0].domElement as HTMLCanvasElement;
  const order: string[] = [];
  const removeListener = canvas.removeEventListener.bind(canvas);
  vi.spyOn(canvas, 'removeEventListener').mockImplementation(((type: string, ...rest: any[]) => {
    order.push(`off:${type}`);
    (removeListener as any)(type, ...rest);
  }) as any);
  // Chromium's `loseContext()`: `webglcontextlost` is dispatched ASYNCHRONOUSLY, after the
  // synchronous release chain; `webglcontextrestored` never fires without `restoreContext()`.
  renderers[0].forceContextLoss.mockImplementation(() => {
    order.push('forceContextLoss');
    queueMicrotask(() => canvas.dispatchEvent(new Event('webglcontextlost')));
  });

  hook.unmount();
  await new Promise((resolve) => setTimeout(resolve, 0));

  expect(renderers[0].forceContextLoss).toHaveBeenCalledTimes(1);
  // The listeners are off before the forced loss (matters if an implementation dispatches
  // synchronously) and, as the event arrives later, there is nobody left to hear it.
  const lostOff = order.indexOf('off:webglcontextlost');
  expect(lostOff).toBeGreaterThanOrEqual(0);
  expect(lostOff).toBeLessThan(order.indexOf('forceContextLoss'));
  expect(onContextRestored).not.toHaveBeenCalled();
  expect(base.setError).not.toHaveBeenCalled();
});
