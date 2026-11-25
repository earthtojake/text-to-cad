import { cleanup, render } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { DocumentGlyph } from '../../../dist/file-viewer/navigation/DocumentGlyph.js';

afterEach(cleanup);

// The lucide icon a glyph draws, by its class (`lucide-file` for File).
const icon = (props: { path: string }) => {
  const { container } = render(<DocumentGlyph {...props} />);
  return [...container.querySelector('svg')!.classList].find(name => name.startsWith('lucide-'));
};

it('draws every CAD file, whatever its kind, as the one plain file glyph', () => {
  const kinds = ['a.step', 'a.stp', 'a.xbf', 'a.stl', 'a.3mf', 'a.glb', 'a.dxf', 'a.urdf', 'a.srdf'].map(path => icon({ path }));
  expect(new Set(kinds)).toEqual(new Set(['lucide-file']));
});
