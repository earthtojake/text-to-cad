import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import ViewPlaneControl from '../../../../dist/renderers/kit/camera/ViewPlaneControl.js';
import { VIEW_CUBE_CORNERS, VIEW_PLANE_FACE_BY_ID, VIEW_PLANE_FACES } from './viewportCameraKit.js';

afterEach(cleanup);

// The default camera looks from the right, front and top (DEFAULT_VIEW_DIRECTION): world X
// points right and a little toward the viewer, Y away from it, Z up.
const ISO = { x: [0.8, -0.3, 0.52], y: [0.6, 0.4, -0.69], z: [0, 0.87, 0.5] };

function cube(extra = {}) {
  const activate = vi.fn(), reset = vi.fn(), parentPointer = vi.fn();
  const props = { showViewPlane: true, meshData: {}, viewPlaneFaces: VIEW_PLANE_FACES, viewPlaneOrientation: ISO,
    viewPlaneOffsetRight: 16, activateViewPlaneFace: activate, activateDefaultViewPlane: reset, ...extra };
  const view = render(<div onPointerDown={parentPointer}><ViewPlaneControl {...props} /></div>);
  return { ...view, activate, reset, parentPointer, props };
}

it('draws the three faces turned toward the camera, labelled, and each snaps to its view', () => {
  const { activate, parentPointer } = cube();
  for (const label of ['TOP', 'FRONT', 'RIGHT']) expect(screen.getByText(label).getAttribute('pointer-events')).toBe('none');
  for (const hidden of ['BOTTOM', 'BACK', 'LEFT']) expect(screen.queryByText(hidden)).toBeNull();
  for (const name of ['Jump to top view', 'Jump to front view', 'Jump to right view']) {
    const face = screen.getByRole('button', { name });
    fireEvent.pointerDown(face); fireEvent.click(face);
  }
  expect(activate.mock.calls.flat()).toEqual(['z', 'yNeg', 'x']);
  expect(parentPointer).not.toHaveBeenCalled();
  fireEvent.keyDown(screen.getByRole('button', { name: 'Jump to top view' }), { key: 'Enter' });
  expect(activate).toHaveBeenLastCalledWith('z');
});

it('offers the corners facing the camera as isometric views', () => {
  const { activate } = cube();
  const corner = screen.getByRole('button', { name: 'Jump to front right top isometric view' });
  fireEvent.click(corner);
  expect(activate).toHaveBeenLastCalledWith('iso+-+');
  expect(VIEW_PLANE_FACE_BY_ID['iso+-+'].direction).toEqual([1, -1, 1]);
  expect(screen.queryByRole('button', { name: 'Jump to back left bottom isometric view' })).toBeNull();
  expect(VIEW_CUBE_CORNERS).toHaveLength(8);
});

it('keeps the reset to the default isometric view one click away, and the axis colours', () => {
  const { reset } = cube();
  fireEvent.click(screen.getByRole('button', { name: 'Reset to default isometric view' }));
  expect(reset).toHaveBeenCalledOnce();
  for (const axis of ['X', 'Y', 'Z']) expect(screen.getByText(axis)).toBeTruthy();
});

it('keeps the camera header available when plan or orbit mode hides the cube', () => {
  const props = { meshData: {}, viewPlaneFaces: VIEW_PLANE_FACES, viewPlaneOffsetRight: 16,
    activateViewPlaneFace: vi.fn(), activateDefaultViewPlane: vi.fn(), viewPlaneHeader: <div>Zoom header</div> };
  const { rerender } = render(<ViewPlaneControl {...props} showViewPlane={false} />);
  expect(screen.getByText('Zoom header')).toBeTruthy();
  expect(screen.queryByLabelText('View cube')).toBeNull();
  rerender(<ViewPlaneControl {...props} showViewPlane previewMode />);
  expect(screen.queryByLabelText('View cube')).toBeNull();
});

it('orbits when the cube is dragged, and the click that ends a drag snaps to nothing', async () => {
  const orbit = vi.fn();
  const { activate } = cube({ orbitViewCube: orbit });
  const face = screen.getByRole('button', { name: 'Jump to top view' });
  fireEvent.pointerDown(face, { button: 0, clientX: 10, clientY: 10 });
  fireEvent.pointerMove(window, { clientX: 11, clientY: 10 });
  expect(orbit).not.toHaveBeenCalled();
  fireEvent.pointerMove(window, { clientX: 30, clientY: 14 });
  expect(orbit).toHaveBeenLastCalledWith(20, 4);
  fireEvent.pointerUp(window);
  fireEvent.click(face);
  expect(activate).not.toHaveBeenCalled();
  await new Promise(resolve => setTimeout(resolve, 0));
  fireEvent.pointerDown(face, { button: 0, clientX: 10, clientY: 10 });
  fireEvent.pointerUp(window);
  fireEvent.click(face);
  expect(activate).toHaveBeenLastCalledWith('z');
});
