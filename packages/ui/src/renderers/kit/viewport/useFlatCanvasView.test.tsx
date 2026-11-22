import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { fitTransform } from '@cad/core/lib/drawing2d/transform.js';
import { useFlatCanvasView } from './useFlatCanvasView.js';
import { flatViewRecord } from './flatView.js';
import { DEFAULT_PANEL_WIDTH } from '../shell/sidebars.js';

// Every flat view's canvas (a board, a schematic's sheet, a drawing): the view the file was left at,
// placed on the pane the picture is laid out in. A reload with the view's panel open lays the picture
// out in the whole view first (the panel docks beside the canvas once the file has loaded), then in
// what the panel leaves: the view must come back as it was left, not carried by half a panel's width.

const BOUNDS = [0, 0, 160, 100] as const;
const VIEW = { width: 1440, height: 800 };
const PANEL = DEFAULT_PANEL_WIDTH;
let pane = { ...VIEW };
const observers = new Set<() => void>();
const resize = (next: { width: number; height: number }) => act(() => { pane = next; observers.forEach(callback => callback()); });
const painted: Array<{ scale: number; offsetX: number; offsetY: number }> = [];

beforeEach(() => {
  pane = { ...VIEW };
  painted.length = 0;
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => setTimeout(() => callback(performance.now()), 0));
  vi.stubGlobal('cancelAnimationFrame', (handle: number) => clearTimeout(handle));
  vi.stubGlobal('ResizeObserver', class {
    callback: () => void;
    constructor(callback: () => void) { this.callback = callback; }
    observe() { observers.add(this.callback); } unobserve() {} disconnect() { observers.delete(this.callback); }
  });
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(() =>
    ({ x: 0, y: 0, left: 0, top: 0, right: pane.width, bottom: pane.height, width: pane.width, height: pane.height, toJSON() {} }) as DOMRect);
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({} as CanvasRenderingContext2D);
});
afterEach(() => { cleanup(); observers.clear(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

type Tap = (point: { x: number; y: number }, event: PointerEvent) => unknown;
function Canvas({ content, restored, onViewMoved, onTap = null, takesAway = null }: { content: unknown; restored: object | null;
  onViewMoved: (view: unknown) => void; onTap?: Tap | null; takesAway?: Tap | null }) {
  const view = useFlatCanvasView({ content, bounds: content ? BOUNDS : null, restored, onViewMoved, onTap, takesAway,
    paint: (_ctx: unknown, frame: { transform: { scale: number; offsetX: number; offsetY: number } | null }) => { if (frame.transform) painted.push({ ...frame.transform }); } });
  return <div ref={view.containerRef}><canvas ref={view.canvasRef} /></div>;
}
const settle = () => act(() => new Promise(resolve => setTimeout(resolve, 5)));
const narrow = { width: VIEW.width - PANEL, height: VIEW.height };

it('a reload with the panel open restores the view exactly, though the picture was first laid out in the whole view', async () => {
  // The view the person left, framed on the canvas beside the open panel: zoomed in and panned.
  const fit = fitTransform(BOUNDS, narrow.width, narrow.height);
  const left = { scale: fit.scale * 2.5, offsetX: fit.offsetX - 133.25, offsetY: fit.offsetY + 41.5 };
  const moved = vi.fn();
  // The page loads: the canvas is the whole view until the file has loaded and the panel docks.
  const view = render(<Canvas content={null} restored={flatViewRecord(left, narrow)} onViewMoved={moved} />);
  view.rerender(<Canvas content={{ revision: 1 }} restored={flatViewRecord(left, narrow)} onViewMoved={moved} />);
  await settle();
  resize(narrow);
  await settle();
  expect(painted.at(-1)).toEqual(left);
  // Nothing was written back: the view on screen is the one the record already holds.
  expect(moved).not.toHaveBeenCalled();
  // The window resized before anybody touched it: the view is placed from its record by what it shows,
  // and back on its own pane it is the record's again, exactly.
  resize({ width: 1000, height: 600 });
  await settle();
  expect(painted.at(-1)).not.toEqual(left);
  resize(narrow);
  await settle();
  expect(painted.at(-1)).toEqual(left);
  expect(moved).not.toHaveBeenCalled();
});

it('a view the person moved is kept with its pane, and a resize carries it by what it shows', async () => {
  const moved = vi.fn();
  render(<Canvas content={{ revision: 1 }} restored={null} onViewMoved={moved} />);
  await settle();
  expect(moved).toHaveBeenLastCalledWith(null);
  const canvas = document.querySelector('canvas')!;
  // A mouse wheel's notch, a zoom about the pointer: the person's view, written with the pane it is framed in.
  act(() => { canvas.dispatchEvent(new WheelEvent('wheel', { cancelable: true, deltaX: 0, deltaY: -100, deltaMode: 0, clientX: 400, clientY: 300 })); });
  await settle();
  const after = painted.at(-1)!;
  expect(moved).toHaveBeenLastCalledWith({ ...after, ...VIEW });
  // The panel docks: the point at the centre stays at the centre of what is left, at the same zoom against the fit.
  const centre = [(VIEW.width / 2 - after.offsetX) / after.scale, (after.offsetY - VIEW.height / 2) / after.scale];
  resize(narrow);
  await settle();
  const carried = painted.at(-1)!;
  expect((narrow.width / 2 - carried.offsetX) / carried.scale).toBeCloseTo(centre[0], 9);
  expect((carried.offsetY - narrow.height / 2) / carried.scale).toBeCloseTo(centre[1], 9);
  expect(moved).toHaveBeenLastCalledWith({ ...carried, ...narrow });
});

it('a record an earlier build kept, the transform alone, is taken as it is', async () => {
  const left = { scale: 7.5, offsetX: 120, offsetY: 610 };
  const moved = vi.fn();
  render(<Canvas content={{ revision: 1 }} restored={left} onViewMoved={moved} />);
  await settle();
  expect(painted.at(-1)).toEqual(left);
  expect(moved).not.toHaveBeenCalled();
});

// A tap that would take something out of the selection waits the double-click window, and the double-click drops it
// before it fits: a double-click on a picked item never shows it going and coming back (`docs/viewer-ux.md`, "Selection
// and gestures", as a 3D view's pick holds it). A lone one acts once the window has passed (a finger's window is its
// double tap's); a tap on something else lets it act first; one the renderer no longer takes (a tool put down, the view
// moved off it) is dropped, and so is one still waiting as the canvas goes.
it('holds a tap that takes the selection away for the double-click window, and a double-click drops it', async () => {
  const onTap = vi.fn();
  // What is under the left half of the pane is picked: a tap there would take it away.
  let picked = true;
  const takesAway = vi.fn((point: { x: number }) => (picked && point.x < 100 ? 'left' : null));
  const view = render(<Canvas content={{ revision: 1 }} restored={null} onViewMoved={() => {}} onTap={onTap} takesAway={takesAway} />);
  await settle();
  const canvas = document.querySelector('canvas')!;
  const tap = (clientX: number, pointerType = 'mouse') => act(() => {
    for (const type of ['pointerdown', 'pointerup']) {
      canvas.dispatchEvent(new PointerEvent(type, { bubbles: true, cancelable: true, pointerId: 1, button: 0, pointerType, clientX, clientY: 50 }));
    }
  });
  const taps = () => onTap.mock.calls.map(([point]) => point.x);
  vi.useFakeTimers();
  try {
    // A double-click on it: both clicks wait, and the double-click drops them.
    tap(50);
    tap(50);
    act(() => { canvas.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true, clientX: 50, clientY: 50 })); });
    vi.advanceTimersByTime(1000);
    expect(taps()).toEqual([]);
    // A lone click acts once the window has passed: 220ms for a mouse, a finger's 300ms.
    tap(50);
    vi.advanceTimersByTime(219);
    expect(taps()).toEqual([]);
    vi.advanceTimersByTime(1);
    expect(taps()).toEqual([50]);
    tap(50, 'touch');
    vi.advanceTimersByTime(299);
    expect(taps()).toEqual([50]);
    vi.advanceTimersByTime(1);
    expect(taps()).toEqual([50, 50]);
    // A tap on something else in the window: the waiting one acts first, then this one, at once.
    tap(50);
    tap(150);
    expect(taps()).toEqual([50, 50, 50, 150]);
    // Taken no more when its window has passed: dropped.
    tap(50);
    picked = false;
    vi.advanceTimersByTime(220);
    picked = true;
    // Still waiting as the canvas goes: dropped.
    tap(50);
    view.unmount();
    vi.advanceTimersByTime(300);
    expect(taps()).toEqual([50, 50, 50, 150]);
  } finally {
    vi.useRealTimers();
  }
});
