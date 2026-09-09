import React, { useState } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
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
  return <FileSheetTabbedSurface kind="step" openSectionIds={open} onOpenSectionIdsChange={setOpen} sections={[
    { id: 'tree', title: 'Geometry', keepMounted: true, scrollsContent: true, content: (active: boolean) => <Tree active={active} /> },
    { id: 'features', title: 'Source features', keepMounted: true, scrollsContent: true, content: <p>Source operations</p> },
  ]} />;
}

it('keeps tree state and scroll when switching tabs, with inactive content hidden', () => {
  render(<Inspector />);
  fireEvent.click(screen.getByRole('button', { name: 'Expand model' }));
  const panel = document.querySelector('[data-file-sheet-tab-panel="tree"]')!;
  panel.scrollTop = 120;
  fireEvent.click(screen.getByRole('tab', { name: 'Source features' }));
  expect(screen.queryByRole('button', { name: /model/ })).toBeNull();
  expect(panel.getAttribute('hidden')).toBe('');
  fireEvent.click(screen.getByRole('tab', { name: 'Geometry' }));
  expect(screen.getByRole('button', { name: 'Expand model' }).getAttribute('aria-expanded')).toBe('true');
  expect(document.querySelector('[data-file-sheet-tab-panel="tree"]')).toBe(panel);
  expect(panel.scrollTop).toBe(120);
});
