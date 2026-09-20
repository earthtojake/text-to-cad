import React, { useState } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import FileSheetTabbedSurface from '../../../../../dist/renderers/cad/components/workbench/FileSheetTabbedSurface.js';

Object.assign(globalThis, { React });
afterEach(cleanup);

function Tree({ active }: { active: boolean }) {
  const [expanded, setExpanded] = useState(false);
  return <button aria-expanded={expanded} onClick={() => setExpanded(value => !value)}>{active ? 'Expand model' : 'Inactive model'}</button>;
}

function Inspector() {
  const [open, setOpen] = useState(['tree']);
  return <FileSheetTabbedSurface openSectionIds={open} onOpenSectionIdsChange={setOpen} sections={[
    { id: 'tree', title: 'Features', keepMounted: true, scrollsContent: true, content: (active: boolean) => <Tree active={active} /> },
    { id: 'details', title: 'Details', keepMounted: true, scrollsContent: true, content: <p>Model details</p> },
  ]} />;
}

it('keeps tree state and scroll when switching tabs, with inactive content hidden', () => {
  render(<Inspector />);
  fireEvent.click(screen.getByRole('button', { name: 'Expand model' }));
  const panel = document.querySelector('[data-file-sheet-tab-panel="tree"]')!;
  panel.scrollTop = 120;
  fireEvent.mouseDown(screen.getByRole('tab', { name: 'Details' }), { button: 0, ctrlKey: false });
  expect(screen.queryByRole('button', { name: /model/ })).toBeNull();
  expect(panel.getAttribute('hidden')).toBe('');
  fireEvent.mouseDown(screen.getByRole('tab', { name: 'Features' }), { button: 0, ctrlKey: false });
  expect(screen.getByRole('button', { name: 'Expand model' }).getAttribute('aria-expanded')).toBe('true');
  expect(document.querySelector('[data-file-sheet-tab-panel="tree"]')).toBe(panel);
  expect(panel.scrollTop).toBe(120);
});


it('shows the model directly when it is the only section', () => {
  render(<FileSheetTabbedSurface sections={[
    { id: 'tree', title: 'Features', content: <p>Assembly tree</p> },
  ]} />);
  expect(screen.queryByRole('tablist')).toBeNull();
  expect(screen.getByRole('region', { name: 'Features' }).textContent).toBe('Assembly tree');
});

it('keeps header actions outside the tablist, including single-section inspectors', () => {
  const { rerender } = render(<FileSheetTabbedSurface sections={[
    { id: 'tree', title: 'Features', content: <p>Assembly tree</p> },
    { id: 'view', title: 'View', content: <p>View controls</p> },
  ]} headerActions={<button>100%</button>} />);
  const zoom = screen.getByRole('button', { name: '100%' });
  expect(zoom.closest('[role="tablist"]')).toBeNull();
  expect(zoom.closest('[data-file-sheet-header]')).toBeTruthy();
  rerender(<FileSheetTabbedSurface sections={[
    { id: 'tree', title: 'Features', content: <p>Assembly tree</p> },
  ]} headerActions={<button>100%</button>} />);
  expect(screen.queryByRole('tablist')).toBeNull();
  expect(screen.getByRole('button', { name: '100%' })).toBeTruthy();
});

it('uses native tab keyboard navigation', async () => {
  render(<Inspector />);
  const model = screen.getByRole('tab', { name: 'Features' });
  model.focus();
  fireEvent.keyDown(model, { key: 'ArrowRight' });
  await waitFor(() => expect(screen.getByRole('tab', { name: 'Details' }).getAttribute('aria-selected')).toBe('true'));
  expect(screen.getByText('Model details')).toBeTruthy();
});

it('uses one fixed strip and restores the most recent available per-file tab', () => {
  const sections = [
    { id: 'tree', title: 'Features', content: <p>Assembly tree</p> },
    { id: 'motion', title: 'Motion', content: <p>Movement controls</p> },
    { id: 'view', title: 'View', content: <p>View controls</p> },
  ];
  const changes: string[][] = [];
  const { rerender } = render(<FileSheetTabbedSurface sections={sections}
    openSectionIds={['tree', 'pose', 'display', 'animation']} onOpenSectionIdsChange={(ids: string[]) => changes.push(ids)} />);
  expect(screen.getAllByRole('tablist')).toHaveLength(1);
  expect(screen.getAllByRole('tab').map(tab => tab.textContent)).toEqual(['Features', 'Motion', 'View']);
  expect(screen.getAllByRole('tab').every(tab => !tab.draggable)).toBe(true);
  expect(screen.queryByRole('separator')).toBeNull();
  expect(screen.getByRole('tab', { name: 'Motion' }).getAttribute('aria-selected')).toBe('true');
  expect(screen.queryByText('Assembly tree')).toBeNull();
  fireEvent.mouseDown(screen.getByRole('tab', { name: 'View' }), { button: 0, ctrlKey: false });
  expect(changes).toEqual([['view']]);

  // The next file supplies its own active selection; the host still controls it.
  rerender(<FileSheetTabbedSurface sections={sections} openSectionIds={['view']} />);
  expect(screen.getByRole('tab', { name: 'View' }).getAttribute('aria-selected')).toBe('true');
  rerender(<FileSheetTabbedSurface sections={sections} openSectionIds={['tree']} />);
  expect(screen.getByRole('tab', { name: 'Features' }).getAttribute('aria-selected')).toBe('true');
  expect(screen.getAllByRole('tab').map(tab => tab.textContent)).toEqual(['Features', 'Motion', 'View']);
});

it('falls back to the first supported tab without reordering optional sections', () => {
  const { rerender } = render(<FileSheetTabbedSurface openSectionIds={['motion']} sections={[
    { id: 'tree', title: 'Features', content: <p>Assembly tree</p> },
    { id: 'view', title: 'View', content: <p>View controls</p> },
  ]} />);
  expect(screen.getByRole('tab', { name: 'Features' }).getAttribute('aria-selected')).toBe('true');
  rerender(<FileSheetTabbedSurface openSectionIds={['motion']} sections={[
    { id: 'tree', title: 'Features', content: <p>Assembly tree</p> },
    { id: 'motion', title: 'Motion', content: <p>Movement controls</p> },
    { id: 'view', title: 'View', content: <p>View controls</p> },
  ]} />);
  expect(screen.getAllByRole('tab').map(tab => tab.textContent)).toEqual(['Features', 'Motion', 'View']);
  expect(screen.getByRole('tab', { name: 'Motion' }).getAttribute('aria-selected')).toBe('true');
});

it('shows a single section\'s title in place of a tab strip', () => {
  const view = render(<FileSheetTabbedSurface openSectionIds={[]} sections={[{ id: 'view', title: 'View', content: <p>Display settings</p> }]} />);
  expect(screen.queryByRole('tablist')).toBeNull();
  expect(screen.getByRole('heading', { name: 'View' })).toBeTruthy();
  expect(screen.getByRole('region', { name: 'View' }).textContent).toContain('Display settings');
  // With a choice to make, the strip is the title.
  view.rerender(<FileSheetTabbedSurface openSectionIds={['view']} sections={[
    { id: 'motion', title: 'Motion', content: <p>Joints</p> }, { id: 'view', title: 'View', content: <p>Display settings</p> }]} />);
  expect(screen.getByRole('tablist')).toBeTruthy();
  expect(screen.queryByRole('heading', { name: 'View' })).toBeNull();
});
