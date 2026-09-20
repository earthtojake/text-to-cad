import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import ViewPlaneControl from '../../../../../dist/renderers/cad/components/viewer/ViewPlaneControl.js';
import { VIEW_PLANE_FACES } from './viewportCameraKit.js';

afterEach(cleanup);

it('keeps X/Y/Z outside the endpoint bubbles while preserving snapping, keyboard controls and hit regions', () => {
  const activate = vi.fn(), reset = vi.fn(), parentPointer = vi.fn();
  const props = { showViewPlane: true, meshData: {}, viewPlaneFaces: VIEW_PLANE_FACES,
    viewPlaneOffsetRight: 16, activateViewPlaneFace: activate, activateDefaultViewPlane: reset };
  const { container, rerender } = render(<div onPointerDown={parentPointer}><ViewPlaneControl {...props} /></div>);
  for (const label of ['X', 'Y', 'Z']) {
    const text = screen.getByText(label);
    expect(text.tagName.toLowerCase()).toBe('text');
    expect(text.getAttribute('pointer-events')).toBe('none');
    expect(text.closest('[role="button"]')).toBeNull();
    expect(text.getAttribute('font-weight')).toBe('400');
  }
  for (const name of ['Jump to right view', 'Jump to back view', 'Jump to top view']) {
    const hit=screen.getByRole('button',{name});
    fireEvent.pointerDown(hit); fireEvent.click(hit);
  }
  expect(activate.mock.calls.flat()).toEqual(['x', 'y', 'z']);
  expect(parentPointer).not.toHaveBeenCalled();
  expect(container.querySelectorAll('svg [role="button"]')).toHaveLength(7);
  fireEvent.keyDown(screen.getByRole('button', { name: 'Jump to left view' }), { key: 'Enter' });
  expect(activate).toHaveBeenLastCalledWith('xNeg');
  fireEvent.keyDown(screen.getByRole('button', { name: 'Reset to default isometric view' }), { key: ' ' });
  expect(reset).toHaveBeenCalledOnce();
  const center = screen.getByRole('button', { name: 'Reset to default isometric view' });
  for (const stem of container.querySelectorAll('svg > line')) {
    expect(stem.compareDocumentPosition(center) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  }
  expect(center.querySelector('circle:last-child')?.getAttribute('fill')).toMatch(/, 1\)$/);

  rerender(<ViewPlaneControl {...props} viewerTheme={{ viewPlanePalette: { axis: {
    x: { front: [250, 250, 250], back: [250, 250, 250] },
    y: { front: [10, 10, 10], back: [10, 10, 10] },
  } } }} viewPlaneOrientation={{x:[0,0,1],y:[1,0,0],z:[0,1,0]}} />);
  const finalButton=container.querySelector('svg [role="button"]:last-of-type')!;
  for (const label of ['X', 'Y', 'Z']) {
    const axisLabel=screen.getByText(label);
    expect(axisLabel).toBeTruthy();
    expect(finalButton.compareDocumentPosition(axisLabel) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  }
  expect(screen.getByText('X').getAttribute('fill')).toContain('rgba(');
});

it('keeps the camera header available when plan or orbit mode hides the axis selector', () => {
  const props = { meshData: {}, viewPlaneFaces: VIEW_PLANE_FACES, viewPlaneOffsetRight: 16,
    activateViewPlaneFace: vi.fn(), activateDefaultViewPlane: vi.fn(), viewPlaneHeader: <div>Zoom header</div> };
  const {rerender}=render(<ViewPlaneControl {...props} showViewPlane={false}/>);
  expect(screen.getByText('Zoom header')).toBeTruthy();
  expect(screen.queryByLabelText('Perspective selector')).toBeNull();
  rerender(<ViewPlaneControl {...props} showViewPlane previewMode/>);
  expect(screen.getByText('Zoom header')).toBeTruthy();
  expect(screen.queryByLabelText('Perspective selector')).toBeNull();
});
