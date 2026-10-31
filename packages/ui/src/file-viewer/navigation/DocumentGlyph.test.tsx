import { cleanup, render } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { DocumentGlyph } from '../../../dist/file-viewer/navigation/DocumentGlyph.js';

afterEach(cleanup);

// The lucide icon a glyph draws, by its class (`lucide-file` for File).
const icon = (props: { model?: boolean; path: string }) => {
  const { container } = render(<DocumentGlyph {...props} />);
  return [...container.querySelector('svg')!.classList].find(name => name.startsWith('lucide-'));
};

it('draws a model as the cube and every CAD file, whatever its kind, as the one plain file glyph', () => {
  expect(icon({ model: true, path: '6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab' })).toBe('lucide-box');
  const kinds = ['a.step', 'a.stp', 'a.xbf', 'a.stl', 'a.3mf', 'a.glb', 'a.dxf', 'a.urdf', 'a.srdf', 'a.sdf'].map(path => icon({ path }));
  expect(new Set(kinds)).toEqual(new Set(['lucide-file']));
});
