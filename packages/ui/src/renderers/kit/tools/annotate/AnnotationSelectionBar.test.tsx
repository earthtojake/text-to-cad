import React from 'react';
import { act, cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import AnnotationSelectionBar from '../../../../../dist/renderers/kit/tools/annotate/AnnotationSelectionBar.js';
import { ViewerHostContext } from '../../../../../dist/host/context.js';
import { testHost } from '../../../../../dist/host/testing/host.js';

// Where the picked ink falls on the screen needs a WebGL scene: here every point falls on the view's middle.
vi.mock('../../../../../dist/renderers/kit/tools/annotate/annotation3d.js', () => ({
  annotationWorldPoints: () => [{ project: () => ({ x: 0, y: 0, z: 0 }) }],
}));

afterEach(cleanup);

const runtime = { camera: { updateMatrixWorld() {}, matrixWorld: { elements: [] }, projectionMatrix: { elements: [] } },
  renderer: { domElement: { clientWidth: 400, clientHeight: 300 } } };

// A rectangle picked: its bar is its Colour and Stroke width, a rule, and Delete, each a step of its own.
it("offers a picked shape's Colour and Stroke width, a rule, then Delete", async () => {
  const rectangle = { id: 'rect', kind: 'stroke', closed: true, color: '#ff2d55', width: 2, points: new Float32Array(12) };
  const annotation: any = { items: [rectangle], selected: ['rect'], remove: vi.fn(), restyle: vi.fn() };
  const onDelete = vi.fn();
  await act(async () => {
    render(<ViewerHostContext.Provider value={testHost()}>
      <AnnotationSelectionBar annotation={annotation} runtimeRef={{ current: runtime }} onDelete={onDelete} /></ViewerHostContext.Provider>);
  });
  const bar = await screen.findByRole('toolbar', { name: 'Selected annotation' });
  const controls = [...bar.querySelectorAll('button, [role=separator]')]
    .map(element => (element.getAttribute('role') === 'separator' ? '|' : element.getAttribute('aria-label')));
  expect(controls).toEqual(['Colour', 'Stroke width', '|', 'Delete']);
  within(bar).getByRole('button', { name: 'Delete' }).click();
  expect(onDelete).toHaveBeenCalledTimes(1);
});
