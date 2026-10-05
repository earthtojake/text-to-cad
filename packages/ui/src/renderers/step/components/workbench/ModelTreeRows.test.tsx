import React, { useState } from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import ModelingTree from '../../../../../dist/renderers/step/components/workbench/ModelingTree.js';
import { FolderExplorer } from '../../../../../dist/file-viewer/navigation/FolderExplorer.js';

// The file explorer the navbar's file name opens and the viewer's model tree drawn side by side.
// jsdom has no layout, so what is asserted is what PRODUCES the geometry: both build their rows
// from the one shared row primitive (`primitives/tree-row.jsx`) — the model tree in its dense form —
// inside a list whose only horizontal inset is 4px, with rows spanning it. The rest of the model
// tree's behaviour (disclosure vs selection, isolation, the one-shot reveal, search hits in a
// collapsed subassembly) is ModelingTree.test.tsx; the explorer's is FolderExplorer.test.tsx.
const scrollIntoView = Element.prototype.scrollIntoView;
beforeEach(() => {
  Element.prototype.scrollIntoView = () => {}; // jsdom has none; the model tree reveals its active row
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); Element.prototype.scrollIntoView = scrollIntoView; });

const leaves = Array.from({ length: 12 }, (_, i) => ({ id: `o${i}`, nodeType: 'part', displayName: `Part ${i}`, leafPartIds: [`o${i}`], children: [] }));
const group = { id: 'group', nodeType: 'assembly', displayName: 'Subassembly', leafPartIds: ['o0', 'o1'], children: leaves.slice(0, 2) };
const root = { id: '__step_model__', nodeType: 'assembly', displayName: 'Document', leafPartIds: leaves.map(n => n.id), children: [group, ...leaves.slice(2)] };
// Different parts, each its own component: one component placed many times would fold into one row.
const descriptor = { components: Object.fromEntries(leaves.map(n => [`c${n.id}`, {}])), occurrences: leaves.map(n => ({ id: n.id, component: `c${n.id}`, name: n.displayName })) };
const source = { list: async () => [{ path: '/models/part.step', name: 'part.step', kind: 'file' }],
  search: async () => ({ paths: ['/models/part.step'], truncated: false }) };

function Trees() {
  const [selected, setSelected] = useState<string[]>([]);
  return <>
    <section data-testid="files"><FolderExplorer source={source} file="/models/part.step" onOpen={() => {}} /></section>
    <section data-testid="model"><ModelingTree active disabled={false} modeling={{ descriptor, results: {}, error: '', retryFailed() {} }} stepRoot={root}
      selectedPartIds={selected} partControls={{ isAssemblyView: true, expandedTreeNodeIds: [], onToggleTreeNode() {}, hiddenPartIds: [],
        onSelectTreeNode: (id: string) => setSelected([id]), onTogglePartVisibility() {}, onFocusTreeNode() {} }} /></section>
  </>;
}

// Everything that could put horizontal space between a list and a row's box, on one element.
const HORIZONTAL_SPACING = /^-?(p|px|ps|pe|pl|pr|m|mx|ms|me|ml|mr)-/;
function horizontalSpacing(element: HTMLElement) {
  const classes = String(element.className || '').split(/\s+/).filter(token => HORIZONTAL_SPACING.test(token));
  const { paddingLeft, paddingRight, marginLeft, marginRight } = element.style;
  return [...classes, ...[paddingLeft, paddingRight, marginLeft, marginRight].filter(Boolean)];
}
// The list's own inset, and that nothing between it and the row adds any, and the row spans it.
function insetOf(row: HTMLElement, list: HTMLElement) {
  const between: string[] = [];
  for (let node = row.parentElement; node && node !== list; node = node.parentElement) between.push(...horizontalSpacing(node));
  const box = row.className.split(/\s+/).filter(token => /^(w-full|-?m[xslr]?-)/.test(token));
  return { list: horizontalSpacing(list), between, box };
}

it('the file explorer and the model tree share one row primitive and one horizontal inset, the model tree in denser rows', async () => {
  render(<Trees />);
  const files = screen.getByTestId('files'), model = screen.getByTestId('model');
  const fileRow = (await within(files).findByText('part.step')).closest('[data-explorer-row]') as HTMLElement;
  const modelRow = within(model).getByRole('button', { name: 'Select Part 2' }).parentElement as HTMLElement;
  // The explorer keeps the regular 28px row in `text-xs`; the model tree the dense 24px row in the
  // panels' 11px `text-tiny`; both the primitive's type weight.
  expect([fileRow.style.height, modelRow.style.height]).toEqual(['28px', '24px']);
  expect(fileRow.className).toMatch(/(^|\s)text-xs(\s|$)/);
  expect(modelRow.className).toMatch(/(^|\s)text-tiny(\s|$)/);
  for (const row of [fileRow, modelRow]) expect(row.className).toMatch(/(^|\s)font-normal(\s|$)/);
  // The disclosure column: 16px wide, a row tall.
  expect(within(model).getByRole('button', { name: 'Expand Subassembly' }).className.split(/\s+/)).toEqual(expect.arrayContaining(['w-4', 'h-6']));
  // One inset: 4px on the list (the explorer's `p-1`, the tree's `px-1`), nothing between the list
  // and a row, and the row spans the list.
  expect(insetOf(fileRow, fileRow.closest('[data-slot="scroll-area-viewport"]') as HTMLElement)).toEqual({ list: ['p-1'], between: [], box: ['w-full'] });
  expect(insetOf(modelRow, within(model).getByRole('list', { name: 'Model' }).parentElement as HTMLElement)).toEqual({ list: ['px-1'], between: [], box: ['w-full'] });
  // Both scroll in the chrome's one scroll region, never a native scroller.
  expect(fileRow.closest('[data-slot="scroll-area"]')).not.toBeNull();
  expect(modelRow.closest('[data-slot="scroll-area"]')).not.toBeNull();
});

it('model search hits keep the tree\'s row and its inset', async () => {
  render(<Trees />);
  const model = screen.getByTestId('model');
  const shared = { list: ['px-1'], between: [], box: ['w-full'] };
  // "part 1" ranks the nested Part 1 — inside the still-collapsed Subassembly — above Part 10 and 11.
  fireEvent.change(within(model).getByRole('textbox', { name: 'Filter model' }), { target: { value: 'part 1' } });
  const results = await within(model).findByRole('list', { name: 'Model search results' });
  const first = within(results).getAllByRole('button', { name: /^Select / })[0];
  expect(first.getAttribute('aria-label')).toBe('Select Part 1');
  const hitRow = first.parentElement as HTMLElement;
  expect(hitRow.style.height).toBe('24px');
  expect(insetOf(hitRow, results.parentElement as HTMLElement)).toEqual(shared);
});

it('a row\'s actions float over its right end, the name running under them and fading out, and a selected row keeps its weight', () => {
  render(<Trees />);
  const model = screen.getByTestId('model');
  const name = within(model).getByRole('button', { name: 'Select Part 2' });
  const row = name.parentElement as HTMLElement;
  const actions = row.querySelector('[data-row-actions]') as HTMLElement;
  // Positioned over the row (which is their containing block), at its right end and full height,
  // with nothing drawn behind them.
  expect(row.className).toMatch(/(^|\s)relative(\s|$)/);
  for (const token of ['absolute', 'right-0', 'inset-y-0']) expect(actions.className.split(/\s+/)).toContain(token);
  expect(actions.className).not.toMatch(/backdrop-|(^|\s)bg-/);
  // The name keeps the row's full width (flex-1) and is masked out under the room the actions take.
  expect(name.className.split(/\s+/)).toContain('flex-1');
  expect(name.className).toMatch(/mask-image:linear-gradient\(to_right,.*var\(--row-actions\)/);
  expect(row.style.getPropertyValue('--row-actions')).not.toBe('');
  // Selected, the row is lit, not bold.
  fireEvent.click(name);
  expect(name.getAttribute('aria-pressed')).toBe('true');
  expect(`${row.className} ${name.className}`).not.toMatch(/font-(medium|semibold|bold)/);
  expect(row.className).toMatch(/(^|\s)font-normal(\s|$)/);
});
