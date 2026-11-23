import { render } from '@testing-library/react';
import { TreeRowDetail, TreeRowGlyph, TreeRowHeading, TreeRowLabel, TreeRowName, TreeRowSurface, TreeRowToggle } from './tree-row.jsx';
import { TreeFilterMatch, TreeSearchStatus, matchIndices } from './tree-filter.jsx';

it('a row a level down keeps its glyph slot when it has no glyph, is padded a level in from the panel\'s line, and hangs from one guide', () => {
  const { container } = render(<TreeRowSurface dense depth={1}><TreeRowGlyph /><TreeRowLabel>leaf</TreeRowLabel></TreeRowSurface>);
  const row = container.querySelector<HTMLElement>('[data-tree-row]')!;
  const slot = row.firstElementChild!;
  expect([slot.hasAttribute('data-tree-row-glyph'), slot.childElementCount, row.style.paddingLeft, row.querySelectorAll('[data-tree-guide]').length, row.style.height])
    .toEqual([true, 0, 'calc(var(--tree-row-pad, 5px) + 10px)', 1, 'var(--cad-row)']);
});

it('a branch\'s chevron and a leaf\'s icon take the same one slot, so the names of a level start on one column', () => {
  const { container } = render(<>
    <TreeRowSurface dense depth={0}><TreeRowToggle open label='Collapse a' onToggle={() => {}} /><TreeRowLabel>a</TreeRowLabel></TreeRowSurface>
    <TreeRowSurface dense depth={0}><TreeRowGlyph /><TreeRowLabel>b</TreeRowLabel></TreeRowSurface>
  </>);
  const [branch, leaf] = [...container.querySelectorAll<HTMLElement>('[data-tree-row]')];
  expect([...branch.children].map(child => child.hasAttribute('data-tree-row-glyph'))).toEqual([true, false]);
  expect([...leaf.children].map(child => child.hasAttribute('data-tree-row-glyph'))).toEqual([true, false]);
  expect(branch.style.paddingLeft).toBe(leaf.style.paddingLeft);
});

it('a name and its detail are every tree\'s: the name whole, the detail muted in the row\'s own text and first to give way', () => {
  const { container } = render(<TreeRowSurface dense depth={0}><TreeRowGlyph /><span><TreeRowName>F.Cu</TreeRowName><TreeRowDetail>134</TreeRowDetail></span></TreeRowSurface>);
  const [name, detail] = [...container.querySelectorAll<HTMLElement>('[data-tree-row] span span')];
  expect(name.className.split(' ')).toEqual(expect.arrayContaining(['max-w-full', 'shrink-0', 'truncate']));
  expect(detail.className.split(' ')).toEqual(expect.arrayContaining(['flex-1', 'text-muted-foreground', 'truncate']));
  // No size of its own: a count reads in the row's text, the panel's 12px.
  expect(`${name.className} ${detail.className}`).not.toMatch(/text-(tiny|micro|xs)/);
});

it('a heading over rows is the panel\'s 28px muted line, in the element asked for', () => {
  const { container } = render(<ul><TreeRowHeading as='li' aria-hidden='true'>Front</TreeRowHeading></ul>);
  const heading = container.querySelector<HTMLElement>('[data-tree-heading]')!;
  expect([heading.tagName, heading.textContent, heading.getAttribute('aria-hidden')]).toEqual(['LI', 'Front', 'true']);
  expect(heading.className.split(' ')).toEqual(expect.arrayContaining(['h-control', 'text-ui', 'text-muted-foreground']));
  // It pads nothing: the panel's body puts its words on the panel's inset (`--panel-inset`), as every line of text.
  expect(heading.className).not.toMatch(/(^|\s)p[xlr]?-/);
});

it('a plain search lights where the query falls in a name, ignoring case, and nothing where it does not', () => {
  expect(matchIndices('B.SilkS', 'silk')).toEqual([2, 3, 4, 5]);
  expect([matchIndices('B.SilkS', 'cu'), matchIndices('B.SilkS', '')]).toEqual([[], []]);
  const { container } = render(<span><TreeFilterMatch text='Edge.Cuts' query='cut' /></span>);
  expect([...container.querySelectorAll('[data-tree-filter-hit]')].map(hit => hit.textContent).join('')).toBe('Cut');
  expect(container.textContent).toBe('Edge.Cuts');
  // Lit in the brand's text colour, a weight up: never the name's own colour, in either theme.
  for (const hit of container.querySelectorAll('[data-tree-filter-hit]')) expect([...hit.classList]).toEqual(expect.arrayContaining(['text-brand-text', 'font-medium']));
});

it('a search\'s status counts its hits, or says only the first are listed', () => {
  const { container, rerender } = render(<TreeSearchStatus shown={3} total={3} hit />);
  const status = () => container.querySelector<HTMLElement>('[data-tree-status]')!;
  expect([status().getAttribute('role'), status().hasAttribute('data-flat-panel-hit'), status().textContent]).toEqual(['status', true, '3 matches']);
  rerender(<TreeSearchStatus shown={200} total={1234} />);
  expect([status().hasAttribute('data-flat-panel-hit'), status().textContent]).toEqual([false, 'First 200 of 1,234 matches']);
});

it('no panel view of a tree sets a text size of its own: rows, details, counts and headings are the panel\'s 12px', async () => {
  const { readFileSync } = await import('node:fs');
  const views = ['board/LayersSection.jsx', 'dxf/LayersSection.jsx', 'schematic/SheetsSection.jsx', 'robot/LinksSection.jsx', 'kit/inspector/CircuitTree.jsx',
    'kit/inspector/SceneTreeSection.jsx', 'kit/inspector/layerRows.jsx', 'xbf/XbfModelTree.jsx', 'xbf/XbfParametersSection.jsx'];
  const sized = views.filter(view => /\btext-(tiny|micro|xs)\b/.test(readFileSync(`${process.cwd()}/src/renderers/${view}`, 'utf8')));
  expect(sized).toEqual([]);
});
