import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { usePlaneDrawing } from '../../../../dist/renderers/kit/plane/usePlaneDrawing.js';
import { planeViewForViewport } from '../../../../dist/renderers/kit/tools/draw/planeViewLock.js';

// A sketch is the picture with its ink. The pane's size changes while one is up (a window resized):
// the drawing editor keeps its scroll and zoom against the pane's corner, so the picture must come
// back under the ink — the same lock, the editor's viewport as it is — whatever the plane view did
// to it. And a copy of it is the picture as sharp as it will be, not a patch scaled mid-zoom.
let resized: (() => void) | null = null;
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { constructor(callback: () => void) { resized = callback; } observe() {} disconnect() { resized = null; } });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); resized = null; });

it('a pane resized under a sketch puts the picture back under its ink, in the same frame', () => {
  const fitted = { scale: 8, offsetX: 100, offsetY: 400 };
  const transformRef = { current: fitted };
  const setView = vi.fn((next: typeof fitted) => { transformRef.current = next; });
  const paintNow = vi.fn();
  const canvasRef = { current: document.createElement('canvas') };
  const view = renderHook(() => usePlaneDrawing({ active: true, plane: { transformRef, setView, paintNow, canvasRef } }));
  // The editor reports where it is, then the person pans and zooms it: the picture follows.
  act(() => view.result.current.overlay.onViewportChange({ scrollX: 0, scrollY: 0, zoom: 1 }));
  act(() => view.result.current.overlay.onViewportChange({ scrollX: 12, scrollY: -4, zoom: 1.5 }));
  const followed = planeViewForViewport({ transform: fitted, viewport: { scrollX: 0, scrollY: 0, zoom: 1 } }, { scrollX: 12, scrollY: -4, zoom: 1.5 });
  expect(setView).toHaveBeenLastCalledWith(followed);
  // The plane view refits the picture to the new pane; the sketch did not move, so neither may the picture.
  transformRef.current = { scale: 6, offsetX: 40, offsetY: 300 };
  setView.mockClear();
  act(() => resized?.());
  expect(setView).toHaveBeenLastCalledWith(followed);
  expect(paintNow).toHaveBeenCalled();
});

it('a copy of the sketch draws the picture final first, as sharp as it will be once the view rests', async () => {
  const order: string[] = [];
  const plot = document.createElement('canvas');
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => ({ drawImage: (source: unknown) => { if (source === plot) order.push('copied'); } }) as unknown as RenderingContext);
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation((callback) => callback(new Blob(['png'], { type: 'image/png' })));
  const view = renderHook(() => usePlaneDrawing({ active: true, plane: { transformRef: { current: null }, setView: () => {}, settle: () => order.push('settled'), canvasRef: { current: plot } } }));
  await view.result.current.capture();
  expect(order).toEqual(['settled', 'copied']);
});
