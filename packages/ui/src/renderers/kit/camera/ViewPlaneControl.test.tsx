import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import ViewPlaneControl from '../../../../dist/renderers/kit/camera/ViewPlaneControl.js';
import { VIEW_PLANE_FACES } from './viewportCameraKit.js';

beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });
const ISO = { x: [0.8, -0.3, 0.52], y: [0.6, 0.4, -0.69], z: [0, 0.87, 0.5] };
function cube(extra = {}) {
  const activate = vi.fn(), reset = vi.fn(), parentPointer = vi.fn();
  const props = { showViewPlane: true, meshData: {}, viewPlaneFaces: VIEW_PLANE_FACES, viewPlaneOrientation: ISO,
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
it('hides the cube in fullscreen and preserves an explicit header slot', () => {
  cube({ previewMode: true, viewPlaneHeader: <div>Camera header</div> });
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
  expect(orbit).toHaveBeenLastCalledWith(20, 4);
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
  for (const dot of container.querySelectorAll('circle')) expect(dot.getAttribute('fill')).toBe('transparent');
});
