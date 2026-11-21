import React from 'react';
import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import AnnotationSelectionBar from '../../../../../dist/renderers/kit/tools/annotate/AnnotationSelectionBar.js';
import { ViewerHostContext } from '../../../../../dist/host/context.js';
import { testHost } from '../../../../../dist/host/testing/host.js';

// The ink as it falls on the screen needs a WebGL scene: here it is given, and a fill is what `fillAreasOf` was asked.
const scene = vi.hoisted(() => ({ screen: [] as any[], fills: [] as any[][] }));
vi.mock('../../../../../dist/renderers/kit/tools/annotate/annotation3d.js', () => ({
  annotationsOnScreen: (_runtime: unknown, items: any[]) => scene.screen.filter(ink => items.some(item => item.id === ink.id)),
  annotationWorldPoints: () => [{ project: () => ({ x: 0, y: 0, z: 0 }) }],
  closedShape: (item: any) => item.kind === 'stroke' && item.closed && !item.widths,
  fillAreasOf: (...args: any[]) => { scene.fills.push(args); return [{ kind: 'area', id: 'placed' }]; },
}));

afterEach(() => { cleanup(); scene.fills = []; });

const loop = (gap: number) => Array.from({ length: 64 }, (_, i) => {
  const turn = (i / 63) * (2 * Math.PI - gap / 50);
  return { x: 150 + 50 * Math.cos(turn), y: 150 + 50 * Math.sin(turn) };
});
const pen = (id: string) => ({ id, kind: 'stroke', closed: false, color: '#ff2d55', width: 3, widths: [1, 1], points: new Float32Array(6) });
const runtime = { camera: { updateMatrixWorld() {}, matrixWorld: { elements: [] }, projectionMatrix: { elements: [] } },
  renderer: { domElement: { clientWidth: 400, clientHeight: 300 } } };

async function mount(gap: number) {
  scene.screen = [{ id: 'loop', kind: 'stroke', closed: false, width: 3, points: loop(gap) }];
  const annotation: any = { items: [pen('loop')], selected: ['loop'], fill: vi.fn(), remove: vi.fn(), restyle: vi.fn() };
  await act(async () => {
    render(<ViewerHostContext.Provider value={testHost()}>
      <AnnotationSelectionBar annotation={annotation} runtimeRef={{ current: runtime }} onDelete={() => {}} /></ViewerHostContext.Provider>);
  });
  return annotation;
}

// A selected pen loop is fillable from the bar as the Fill tool takes it: its ends under 20px apart on the screen now.
it("offers Fill for a selected pen loop whose ends meet on the screen, filling it with the outline closed, and not for an open stroke", async () => {
  const annotation = await mount(10);
  (await screen.findByRole('button', { name: 'Fill' })).click();
  const [[, shape, outline]] = scene.fills;
  expect([shape.id, outline.closed]).toEqual(['loop', true]);
  expect(annotation.fill).toHaveBeenCalledWith('loop', [{ kind: 'area', id: 'placed' }]);
  cleanup();
  await mount(120);
  await screen.findByRole('button', { name: 'Delete' });
  expect(screen.queryByRole('button', { name: 'Fill' })).toBeNull();
});
