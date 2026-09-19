import React, { useState } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import FileSheetTabbedSurface from '../../../../../dist/renderers/cad/components/workbench/FileSheetTabbedSurface.js';
import { FileSheetTabPreferencesContext } from '../../../../../dist/renderers/cad/workbench/fileSheetTabPreferences.js';

Object.assign(globalThis, { React });
afterEach(cleanup);

function Tree({ active }: { active: boolean }) {
  const [expanded, setExpanded] = useState(false);
  return <button aria-expanded={expanded} onClick={() => setExpanded(value => !value)}>{active ? 'Expand model' : 'Inactive model'}</button>;
}

function Inspector() {
  const [open, setOpen] = useState(['tree']);
  return <FileSheetTabbedSurface kind="mesh" openSectionIds={open} onOpenSectionIdsChange={setOpen} sections={[
    { id: 'tree', title: 'Model', keepMounted: true, scrollsContent: true, content: (active: boolean) => <Tree active={active} /> },
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
  fireEvent.mouseDown(screen.getByRole('tab', { name: 'Model' }), { button: 0, ctrlKey: false });
  expect(screen.getByRole('button', { name: 'Expand model' }).getAttribute('aria-expanded')).toBe('true');
  expect(document.querySelector('[data-file-sheet-tab-panel="tree"]')).toBe(panel);
  expect(panel.scrollTop).toBe(120);
});


it('shows the model directly when it is the only section', () => {
  render(<FileSheetTabbedSurface kind="step" sections={[
    { id: 'tree', title: 'Model', content: <p>Assembly tree</p> },
  ]} />);
  expect(screen.queryByRole('tablist')).toBeNull();
  expect(screen.getByRole('region', { name: 'Model' }).textContent).toBe('Assembly tree');
});

it('uses native tab keyboard navigation', async () => {
  render(<Inspector />);
  const model = screen.getByRole('tab', { name: 'Model' });
  model.focus();
  fireEvent.keyDown(model, { key: 'ArrowRight' });
  await waitFor(() => expect(screen.getByRole('tab', { name: 'Details' }).getAttribute('aria-selected')).toBe('true'));
  expect(screen.getByText('Model details')).toBeTruthy();
});

it('migrates legacy tab selections and keeps the same custom layout across display changes', async () => {
  const preferences = { store: { step: { split: true, top: ['tree'], bottom: ['pose', 'animation', 'display', 'render'], ratio: 0.65 } }, update() {} };
  const sections = [
    { id: 'tree', title: 'Model', content: <p>Assembly tree</p> },
    { id: 'motion', title: 'Motion', content: <p>Movement controls</p> },
    { id: 'view', title: 'View', content: <p>View controls</p> },
  ];
  const props = { kind: 'step', sections, openSectionIds: ['tree', 'pose', 'display', 'animation'] };
  const content = (mode: string) => <FileSheetTabPreferencesContext.Provider value={preferences}>
    <FileSheetTabbedSurface {...props} {...{ layoutMode: mode, layoutScope: 'part.step' }} />
  </FileSheetTabPreferencesContext.Provider>;
  const { rerender } = render(content('cad'));
  await waitFor(() => expect(document.querySelectorAll('[data-file-sheet-tab-pane]')).toHaveLength(2));
  expect(screen.getAllByRole('tab', { name: 'Motion' })).toHaveLength(1);
  expect(screen.getAllByRole('tab', { name: 'View' })).toHaveLength(1);
  expect(screen.getByRole('tab', { name: 'Motion' }).getAttribute('aria-selected')).toBe('true');
  rerender(content('render'));
  expect(document.querySelectorAll('[data-file-sheet-tab-pane]')).toHaveLength(2);
  expect(screen.getByRole('tab', { name: 'Motion' }).getAttribute('aria-selected')).toBe('true');
  expect(screen.getByText('Movement controls')).toBeTruthy();
  expect(screen.getByText('Assembly tree')).toBeTruthy();
});
