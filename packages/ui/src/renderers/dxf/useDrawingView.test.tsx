import { StrictMode } from 'react';
import { act, cleanup, render } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useDrawingView } from '../../../dist/renderers/dxf/useDrawingView.js';

// The app mounts under React's StrictMode, which in development runs every effect's cleanup
// and then the effect again on the SAME refs. The browser test runs the production build,
// where that never happens, so this is the one place the remount is exercised: a painter that
// survives it has to paint, or a DXF opens as an empty pane in every development app.

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

function Surface() {
  const view = useDrawingView({ drawing: null, colorScheme: 'dark', onViewMoved: () => {} });
  return <div ref={view.containerRef}><canvas ref={view.canvasRef} /></div>;
}

it('paints after a StrictMode remount: the pending-frame handle does not outlive its frame', () => {
  const frames: Array<() => void> = [];
  vi.stubGlobal('requestAnimationFrame', (callback: () => void) => frames.push(callback));
  vi.stubGlobal('cancelAnimationFrame', (handle: number) => { frames[handle - 1] = () => {}; });
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ width: 320, height: 200 } as DOMRect);
  const fillRect = vi.fn();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    save() {}, restore() {}, setTransform() {}, clearRect() {}, fillRect, fillStyle: '',
  } as unknown as CanvasRenderingContext2D);

  render(<StrictMode><Surface /></StrictMode>);
  frames.splice(0).forEach(frame => frame());

  expect(fillRect).toHaveBeenCalledWith(0, 0, 320, 200);
});

function DraggableSurface() {
  const view = useDrawingView({ drawing: null, colorScheme: 'dark', onViewMoved: () => {} });
  return <div ref={view.containerRef} data-dragging={String(view.dragging)}><canvas ref={view.canvasRef} /></div>;
}

it('a press whose pointer can no longer be captured still drags, and nothing escapes the handler', () => {
  // A pointer lifted before its pointerdown handler runs (or a synthetic event's id) is no longer
  // active, and the browser answers setPointerCapture -- and releasePointerCapture -- with NotFoundError.
  vi.stubGlobal('requestAnimationFrame', () => 1);
  vi.stubGlobal('cancelAnimationFrame', () => {});
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
  const gone = () => { throw new DOMException('No active pointer with the given id is found.', 'NotFoundError'); };
  const prototype = HTMLCanvasElement.prototype as unknown as Record<string, unknown>;
  Object.assign(prototype, { setPointerCapture: gone, releasePointerCapture: gone, hasPointerCapture: () => true });
  const escaped = vi.fn((event: Event) => event.preventDefault());
  window.addEventListener('error', escaped);

  const { container } = render(<DraggableSurface />);
  const canvas = container.querySelector('canvas')!;
  const dragging = () => container.firstElementChild!.getAttribute('data-dragging');
  const press = (type: string) => {
    const event = new Event(type, { bubbles: true, cancelable: true });
    Object.assign(event, { pointerId: 7, pointerType: 'touch', button: 0, clientX: 4, clientY: 4 });
    act(() => { canvas.dispatchEvent(event); });
  };
  try {
    press('pointerdown');
    expect(dragging()).toBe('true');
    press('pointerup');
    expect(dragging()).toBe('false');
    expect(escaped).not.toHaveBeenCalled();
  } finally {
    window.removeEventListener('error', escaped);
    for (const name of ['setPointerCapture', 'releasePointerCapture', 'hasPointerCapture']) delete prototype[name];
  }
});
