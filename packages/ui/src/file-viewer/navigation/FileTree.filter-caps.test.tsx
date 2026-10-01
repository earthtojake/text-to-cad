import React, { useState } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { FileTree } from './FileTree.jsx';

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.scrollIntoView = () => {};
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function Tree({ paths }: { paths: () => Promise<any> }) {
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const source = { rootName: 'project', expanded, setExpanded, listings: { '': [] }, load() {}, revision: 0, paths, platform: 'darwin', onAction() {} };
  return <FileTree source={source as any} activePath={null} onOpen={() => {}} />;
}
const filter = () => screen.getByRole('combobox', { name: 'Filter files' });

it('says how many matches the 200-row list left out and where the index stopped', async () => {
  const all = Array.from({ length: 250 }, (_, index) => `file${index}.txt`);
  render(<Tree paths={async () => ({ paths: all, truncated: true })} />);
  fireEvent.change(filter(), { target: { value: 'file' } });
  await waitFor(() => expect(screen.getByText('Showing the first 200 of 250 matches; the index stopped at 250 files')).toBeTruthy());
  expect(document.querySelectorAll('[data-path]')).toHaveLength(200);
});

it('says the index stopped short even when every match fits', async () => {
  render(<Tree paths={async () => ({ paths: ['a.txt'], truncated: true })} />);
  fireEvent.change(filter(), { target: { value: 'a' } });
  await waitFor(() => expect(screen.getByText('The index stopped at 1 files; some matches may be missing')).toBeTruthy());
});

it('shows the sentence a failed index read came with, not "No file matches"', async () => {
  render(<Tree paths={async () => { throw new Error('that folder is gone'); }} />);
  fireEvent.change(filter(), { target: { value: 'a' } });
  await waitFor(() => expect(screen.getByText('Could not search the files: that folder is gone')).toBeTruthy());
  expect(screen.queryByText(/No file matches/)).toBeNull();
});
