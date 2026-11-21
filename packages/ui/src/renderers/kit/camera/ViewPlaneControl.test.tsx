import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import ViewPlaneControl from '../../../../dist/renderers/kit/camera/ViewPlaneControl.js';
import { VIEW_PLANE_FACES, createViewPlaneOrientationStore } from './viewportCameraKit.js';

beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });
const ISO = { x: [0.8, -0.3, 0.52], y: [0.6, 0.4, -0.69], z: [0, 0.87, 0.5] };
const TOP = { x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1] };
function cube(extra = {}) {
  const activate = vi.fn(), reset = vi.fn(), parentPointer = vi.fn();
  const props = { showViewPlane: true, meshData: {}, viewPlaneFaces: VIEW_PLANE_FACES, orientation: createViewPlaneOrientationStore(ISO),
    viewPlaneOffsetRight: 16, activateViewPlaneFace: activate, activateDefaultViewPlane: reset, ...extra };
  const view = render(<div onPointerDown={parentPointer}><ViewPlaneControl {...props} /></div>);
  return { ...view, activate, reset, parentPointer, props };
}
it('shows cube faces and isometric corners with keyboard snapping', () => {
  const { activate, parentPointer } = cube();
  expect(screen.getByLabelText('View cube')).toBeTruthy();
  for (const axis of ['X', 'Y', 'Z']) expect(screen.getByText(axis)).toBeTruthy();
  const top = screen.getByRole('button', { name: 'Jump to top view' });
  fireEvent.pointerDown(top); fireEvent.click(top);
  expect(activate).toHaveBeenLastCalledWith('z');
  expect(parentPointer).not.toHaveBeenCalled();
  fireEvent.keyDown(top, { key: 'Enter' });
  expect(activate).toHaveBeenLastCalledWith('z');
  expect(screen.getByLabelText('View cube').querySelectorAll('polygon').length).toBe(3);
});
it('hides the selector when asked and preserves an explicit header slot', () => {
  cube({ showViewPlane: false, viewPlaneHeader: <div>Camera header</div> });
  expect(screen.getByText('Camera header')).toBeTruthy();
  expect(screen.queryByLabelText('View cube')).toBeNull();
});
it('retains drag orbit without snapping after a drag, then permits the next click', () => {
  const orbit = vi.fn();
  const { activate } = cube({ orbitViewCube: orbit });
  const face = screen.getByRole('button', { name: 'Jump to top view' });
  fireEvent.pointerDown(face, { button: 0, clientX: 10, clientY: 10 });
  fireEvent.pointerMove(window, { clientX: 11, clientY: 10 });
  expect(orbit).not.toHaveBeenCalled();
  fireEvent.pointerMove(window, { clientX: 30, clientY: 14 });
  // The drag's first turn says it starts one (its orbit holds its sideways sense from there), the rest do not.
  expect(orbit).toHaveBeenLastCalledWith(20, 4, true);
  fireEvent.pointerMove(window, { clientX: 35, clientY: 14 });
  expect(orbit).toHaveBeenLastCalledWith(5, 0, false);
  fireEvent.pointerUp(window); fireEvent.click(face);
  expect(activate).not.toHaveBeenCalled();
  fireEvent.pointerDown(face, { button: 0, clientX: 10, clientY: 10 });
  fireEvent.pointerUp(window); fireEvent.click(face);
  expect(activate).toHaveBeenLastCalledWith('z');
});

it('keeps a disabled cube visible without allowing snapping or orbit', () => {
  const orbit = vi.fn();
  const { activate, parentPointer } = cube({ disabled: true, orbitViewCube: orbit });
  expect(screen.getByLabelText('View cube')).toBeTruthy();
  for (const face of screen.getAllByRole('button')) {
    expect(face.getAttribute('aria-disabled')).toBe('true');
    expect(face.getAttribute('tabindex')).toBe('-1');
    fireEvent.pointerDown(face, { button: 0, clientX: 10, clientY: 10 });
    fireEvent.pointerMove(window, { clientX: 30, clientY: 14 });
    fireEvent.pointerUp(window);
    fireEvent.click(face);
    fireEvent.keyDown(face, { key: 'Enter' });
  }
  expect(activate).not.toHaveBeenCalled();
  expect(orbit).not.toHaveBeenCalled();
  expect(parentPointer).not.toHaveBeenCalled();
});


it('offers edge snapping between faces while keeping the corner targets above it', () => {
  const { activate } = cube();
  const edges = screen.getAllByRole('button', { name: /edge view$/ });
  expect(edges.length).toBeGreaterThan(0);
  fireEvent.click(edges[0]);
  expect(activate.mock.calls[0][0]).toMatch(/^edge/);
  expect(screen.queryByRole('button', { name: /Reset to default/ })).toBeNull();
});

it('uses the enlarged cube itself for navigation without surrounding arrow buttons', () => {
  const { container } = cube({ orbitViewCube: vi.fn() });
  expect(screen.queryByRole('button', { name: /^Orbit / })).toBeNull();
  expect(screen.getByLabelText('View cube').parentElement?.style.width).toBe('7rem');
  // Each corner's hit area is invisible; the dot drawn on it is what shows.
  const corners = [...container.querySelectorAll('g[role="button"]')].filter(g => /isometric view$/.test(g.getAttribute('aria-label') ?? ''));
  expect(corners.length).toBeGreaterThan(0);
  for (const corner of corners) {
    const [hit, dot] = corner.querySelectorAll('circle');
    expect(hit.getAttribute('fill')).toBe('transparent');
    expect(dot.getAttribute('fill')).not.toBe('transparent');
  }
  // The right-front-top corner, the usual isometric view, has the largest dot.
  const home = screen.getByRole('button', { name: 'Jump to front right top isometric view' }).querySelectorAll('circle')[1];
  expect(Number(home.getAttribute('r'))).toBeGreaterThan(2);
});
it('follows its orientation store alone: an equal orientation is no change, a new one redraws only the cube', () => {
  const orientation = createViewPlaneOrientationStore(ISO);
  let renders = 0;
  function Parent() { renders += 1; return <ViewPlaneControl showViewPlane meshData={{}} viewPlaneFaces={VIEW_PLANE_FACES} orientation={orientation} viewPlaneOffsetRight={16} activateViewPlaneFace={() => {}} />; }
  render(<Parent />);
  const drawn = () => [...screen.getByLabelText('View cube').querySelectorAll('polygon')].map(face => face.getAttribute('points')).join('|');
  const iso = drawn();
  const notified = vi.fn();
  orientation.subscribe(notified);
  act(() => orientation.set({ x: [...ISO.x], y: [...ISO.y], z: [...ISO.z] }));
  expect(notified).not.toHaveBeenCalled();
  act(() => orientation.set(TOP));
  expect(notified).toHaveBeenCalledTimes(1);
  expect(drawn()).not.toBe(iso);
  expect(screen.getByLabelText('View cube').querySelectorAll('polygon').length).toBe(1);
  expect(renders).toBe(1);
});
it('draws its axes on its own edges, every line and label inside its square box, however the cube is turned', () => {
  // Seen from below at 45°, the Z axis points straight down.
  const DOWN = { x: [0.707, 0.5, 0.5], y: [-0.707, 0.5, 0.5], z: [0, -0.707, 0.707] };
  for (const orientation of [ISO, DOWN]) {
    cleanup();
    cube({ orientation: createViewPlaneOrientationStore(orientation), viewPlaneSize: '68px' });
    // The box is square (one uniform scale), cropped to the cube: 12 to 88 in the drawing's units.
    const svg = screen.getByLabelText('View cube');
    const [x0, y0, w, h] = svg.getAttribute('viewBox')!.split(' ').map(Number);
    expect([x0, y0, w, h]).toEqual([12, 12, 76, 76]);
    const box = svg.parentElement!;
    expect([box.style.width, box.style.height]).toEqual(['68px', '68px']);
    for (const axis of ['X', 'Y', 'Z']) {
      const label = screen.getByText(axis);
      for (const value of [Number(label.getAttribute('x')), Number(label.getAttribute('y'))]) expect(value >= x0 + 4 && value <= x0 + w - 4, `${axis}: ${value}`).toBe(true);
    }
    // Each axis line runs along one of the cube's edges: from a corner to a corner, 2 half-sizes (42 units) long at most.
    for (const line of svg.querySelectorAll('g[aria-hidden="true"] line')) {
      const length = Math.hypot(Number(line.getAttribute('x2')) - Number(line.getAttribute('x1')), Number(line.getAttribute('y2')) - Number(line.getAttribute('y1')));
      expect(length).toBeLessThanOrEqual(42.01);
      for (const value of ['x1', 'y1', 'x2', 'y2'].map(name => Number(line.getAttribute(name)))) expect(value >= x0 && value <= x0 + w).toBe(true);
    }
  }
});
