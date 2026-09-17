import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import ViewPlaneControl from '../../../../../dist/renderers/cad/components/viewer/ViewPlaneControl.js';
import { VIEW_PLANE_FACES } from './viewportCameraKit.js';

afterEach(cleanup);

it('labels positive axes without changing snapping, keyboard controls or pointer hit regions', () => {
  const activate = vi.fn(), reset = vi.fn(), parentPointer = vi.fn();
  const props = { showViewPlane: true, meshData: {}, viewPlaneFaces: VIEW_PLANE_FACES,
    viewPlaneOffsetRight: 16, activateViewPlaneFace: activate, activateDefaultViewPlane: reset };
  const { container, rerender } = render(<div onPointerDown={parentPointer}><ViewPlaneControl {...props} /></div>);
  for (const label of ['X', 'Y', 'Z']) {
    const text = screen.getByText(label);
    expect(text.tagName.toLowerCase()).toBe('text');
    expect(text.getAttribute('pointer-events')).toBe('none');
    const hit = text.closest('[role="button"]')!;
    fireEvent.pointerDown(hit); fireEvent.click(hit);
  }
  expect(activate.mock.calls.flat()).toEqual(['x', 'y', 'z']);
  expect(parentPointer).not.toHaveBeenCalled();
  expect(container.querySelectorAll('svg [role="button"]')).toHaveLength(7);
  fireEvent.keyDown(screen.getByRole('button', { name: 'Jump to left view' }), { key: 'Enter' });
  expect(activate).toHaveBeenLastCalledWith('xNeg');
  fireEvent.keyDown(screen.getByRole('button', { name: 'Reset to default isometric view' }), { key: ' ' });
  expect(reset).toHaveBeenCalledOnce();
  rerender(<ViewPlaneControl {...props} viewerTheme={{ viewPlanePalette: { axis: {
    x: { front: [250, 250, 250], back: [250, 250, 250] },
    y: { front: [10, 10, 10], back: [10, 10, 10] },
  } } }} />);
  expect(screen.getByText('X').getAttribute('fill')).toBe('#000000');
  expect(screen.getByText('Y').getAttribute('fill')).toBe('#ffffff');
});
