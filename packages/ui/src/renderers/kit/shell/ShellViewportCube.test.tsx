import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

// Which of the viewport's own controls are drawn (`ShellViewport.jsx`), with the WebGL runtime hook
// replaced by a no-op: the view cube is the tools view's, on a phone as on desktop, never preview's.
vi.mock('../../../../dist/renderers/kit/viewport/useViewerRuntime.js', () => ({ useViewerRuntime: () => {} }));
import ShellViewport from '../../../../dist/renderers/kit/shell/ShellViewport.js';
import { ViewerMobileContext } from '../../../../dist/file-viewer/responsive.js';

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const scene = { object3D: { isObject3D: true }, bounds: { min: [0, 0, 0], max: [1, 1, 1] }, dispose() {} };
it('the view cube is drawn in the tools view, on a phone as on desktop, and never in preview or while the model loads; nor are orbit buttons or camera controls', () => {
  const viewport = (mobile: boolean, previewMode: boolean, isLoading = false) => <ViewerMobileContext.Provider value={mobile}>
    <ShellViewport modelKey="part" scene={scene} isLoading={isLoading} previewMode={previewMode} /></ViewerMobileContext.Provider>;
  const { rerender } = render(viewport(false, false));
  expect(screen.getAllByLabelText('View cube')).toHaveLength(1);
  const extras = () => [screen.queryAllByRole('button', { name: /^Orbit (?:left|right|up|down)$/ }).length, document.querySelectorAll('[data-cad-camera-controls]').length];
  expect(extras()).toEqual([0, 0]);
  rerender(viewport(false, true));
  expect(screen.queryByLabelText('View cube')).toBeNull();
  rerender(viewport(true, false));
  expect(screen.getAllByLabelText('View cube')).toHaveLength(1);
  expect(extras()).toEqual([0, 0]);
  rerender(viewport(false, false, true));
  expect(screen.queryByLabelText('View cube')).toBeNull();
  rerender(<ShellViewport modelKey="part" scene={scene} viewCube={false} />);
  expect(screen.queryByLabelText('View cube')).toBeNull();
});
