import React from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { textGlyphIcon } from '../../../../dist/renderers/kit/shell/TextGlyph.js';

afterEach(cleanup);

// A word as an icon (a board's 2D and 3D): drawn as a Lucide icon is, on its 24-unit grid in its colour, hidden from
// the name, its figures tabular.
it('a word is an icon: drawn as a Lucide icon is, in its colour, hidden from the name, its figures tabular', () => {
  const Glyph = textGlyphIcon('2D');
  const { container } = render(<span><Glyph /></span>);
  const glyph = container.querySelector('svg')!;
  expect([glyph.getAttribute('viewBox'), glyph.getAttribute('aria-hidden'), glyph.getAttribute('fill'), glyph.dataset.textGlyph])
    .toEqual(['0 0 24 24', 'true', 'currentColor', '2D']);
  const text = glyph.querySelector('text')!;
  expect([text.textContent, text.getAttribute('font-weight'), text.style.fontVariantNumeric]).toEqual(['2D', '600', 'tabular-nums']);
});
