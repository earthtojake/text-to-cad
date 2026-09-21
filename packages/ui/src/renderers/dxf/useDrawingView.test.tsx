import { StrictMode } from 'react';
import { cleanup, render } from '@testing-library/react';
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
