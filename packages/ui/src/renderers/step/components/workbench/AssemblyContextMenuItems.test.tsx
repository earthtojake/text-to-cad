import React from 'react';
import { expect, it, vi } from 'vitest';
import { assemblyPartMenuEntries, modelMenuEntries } from
  '../../../../../dist/renderers/step/components/workbench/AssemblyContextMenuItems.js';

// The part menu and the empty-space menu are one definition, rendered in three places:
// the viewport over a part, the viewport over the backdrop, and every Features tree row.
// Since the Inspector's zoom readout and its menu were removed, the framing group at the
// end of each is the viewer's only zoom control, so it must be in all of them.
const text = (entry: any) => (typeof entry.label === 'string' ? entry.label : entry.label.props.children);
const labels = (entries: any[]) => entries.map(text);
const find = (entries: any[], label: string) => entries.find(entry => text(entry) === label);

const partMenu = {
  nodeId: 'o1', label: 'base', copyText: 'o1', selected: false, hidden: false, focused: false,
  showIsolate: true, showHideOther: true, showVisibility: true, showExpandCollapse: false
};

it('ends the part menu with one framing group, after a separator', () => {
  const entries = assemblyPartMenuEntries({ ...partMenu, zoomSelectionAvailable: true }, { actions: {} });
  expect(labels(entries).slice(-2)).toEqual(['Zoom to fit', 'Zoom to selection']);
  // ONE section: a separator opens it, and nothing splits it.
  expect(find(entries, 'Zoom to fit').separatorBefore).toBe(true);
  expect(find(entries, 'Zoom to selection').separatorBefore).toBe(false);
});

it('offers Zoom to selection only when something is selected', () => {
  const off = assemblyPartMenuEntries(partMenu, { actions: {} });
  expect(find(off, 'Zoom to selection').disabled).toBe(true);
  expect(find(off, 'Zoom to fit').disabled).toBe(false);
  const on = assemblyPartMenuEntries({ ...partMenu, zoomSelectionAvailable: true }, { actions: {} });
  expect(find(on, 'Zoom to selection').disabled).toBe(false);
});

it('calls the framing actions with the descriptor the menu was built for', () => {
  const onZoomFit = vi.fn(), onZoomSelection = vi.fn();
  const menu = { ...partMenu, zoomSelectionAvailable: true };
  const entries = assemblyPartMenuEntries(menu, { actions: { onZoomFit, onZoomSelection } });
  find(entries, 'Zoom to fit').onSelect();
  find(entries, 'Zoom to selection').onSelect();
  expect(onZoomFit).toHaveBeenCalledWith(menu);
  expect(onZoomSelection).toHaveBeenCalledWith(menu);
});

it('gives the empty-space menu the same group, so a press on the backdrop is always useful', () => {
  // Nothing hidden and nothing to expand: the framing group is all there is, and it
  // opens the menu rather than following a separator into nothing.
  const bare = modelMenuEntries({ zoomSelectionAvailable: false }, { actions: {} });
  expect(labels(bare)).toEqual(['Zoom to fit', 'Zoom to selection']);
  expect(bare[0].separatorBefore).toBe(false);
  expect(find(bare, 'Zoom to selection').disabled).toBe(true);

  const full = modelMenuEntries({ showShowAll: true, showExpandCollapse: true, zoomSelectionAvailable: true }, { actions: {} });
  expect(labels(full)).toEqual(['Show all', 'Expand all', 'Collapse all', 'Zoom to fit', 'Zoom to selection']);
  expect(find(full, 'Zoom to fit').separatorBefore).toBe(true);
});

it('a disabled menu disables its framing group too', () => {
  const entries = assemblyPartMenuEntries({ ...partMenu, zoomSelectionAvailable: true }, { disabled: true, actions: {} });
  expect(find(entries, 'Zoom to fit').disabled).toBe(true);
  expect(find(entries, 'Zoom to selection').disabled).toBe(true);
});
