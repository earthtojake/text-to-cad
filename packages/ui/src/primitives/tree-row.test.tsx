import { render } from '@testing-library/react';
import { TreeRowGlyph, TreeRowLabel, TreeRowSurface } from './tree-row.jsx';

it('a row a level down keeps its glyph slot when it has no glyph, is padded a level in from the panel\'s line, and hangs from one guide', () => {
  const { container } = render(<TreeRowSurface dense depth={1}><TreeRowGlyph /><TreeRowLabel>leaf</TreeRowLabel></TreeRowSurface>);
  const row = container.querySelector<HTMLElement>('[data-tree-row]')!;
  const slot = row.firstElementChild!;
  expect([slot.hasAttribute('data-tree-row-glyph'), slot.childElementCount, row.style.paddingLeft, row.querySelectorAll('[data-tree-guide]').length])
    .toEqual([true, 0, 'calc(var(--tree-row-pad, 5px) + 10px)', 1]);
});
