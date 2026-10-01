import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { TooltipProvider } from '../../../dist/primitives/tooltip.js';
import { FileNavRow } from '../../../dist/file-viewer/navigation/FileNavRow.js';

afterEach(cleanup);
const source = { list: async () => [] };
const row = (props: Record<string, unknown>) => render(<TooltipProvider><FileNavRow crumbs={[]} source={source} activePath={null} onOpen={() => {}}
  trailing={<button type="button" aria-label="Hide files">t</button>} {...props} /></TooltipProvider>);

it('an empty tab names its row "Files" instead of leaving it blank, and keeps the tree toggle', () => {
  row({ empty: true });
  expect(screen.getByRole('navigation', { name: 'Breadcrumb' }).textContent).toContain('Files');
  expect(screen.getByRole('button', { name: 'Hide files' })).toBeTruthy();
});

it('a host leading slot wins over the empty label, and an open file has none', () => {
  row({ empty: true, leading: <span>feature-branch</span> });
  const nav = screen.getByRole('navigation', { name: 'Breadcrumb' });
  expect(nav.textContent).toContain('feature-branch');
  expect(nav.querySelector('[data-file-nav-empty]')).toBeNull();
  cleanup();
  row({ empty: false });
  expect(screen.getByRole('navigation', { name: 'Breadcrumb' }).querySelector('[data-file-nav-empty]')).toBeNull();
});
