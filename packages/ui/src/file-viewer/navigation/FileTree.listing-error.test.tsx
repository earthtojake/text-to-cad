import React, { useState } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { FileTree } from './FileTree.jsx';

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  Element.prototype.scrollIntoView = () => {};
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function Tree({ listings, failures, load, open = [] as string[] }: { listings: Record<string, any[]>; failures: Record<string, string>; load: (d: string) => void; open?: string[] }) {
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set(open));
  const source = { rootName: 'project', expanded, setExpanded, listings, failures, load, revision: 0,
    paths: async () => [], platform: 'darwin', onAction() {} };
  return <FileTree source={source as any} activePath={null} onOpen={() => {}} />;
}

it('a root that could not be listed says why, with a Retry that lists it again', () => {
  const load = vi.fn();
  render(<Tree listings={{}} failures={{ '': 'that folder is gone' }} load={load} />);
  expect(screen.getByRole('alert').textContent).toBe('that folder is goneRetry');
  expect(screen.queryByText('Reading…')).toBeNull();
  expect(screen.getByRole('tree').getAttribute('aria-busy')).toBeNull();
  load.mockClear();
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
  expect(load).toHaveBeenCalledWith('');
});

it('a folder that could not be listed shows the sentence and a Retry under its chevron', () => {
  const load = vi.fn();
  render(<Tree listings={{ '': [{ path: 'STEP', name: 'STEP', kind: 'directory' }] }} failures={{ STEP: 'permission denied' }} load={load} open={['STEP']} />);
  const row = document.querySelector('[data-path="STEP"]')!;
  expect(row.nextElementSibling?.textContent).toBe('permission deniedRetry');
  load.mockClear();
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
  expect(load).toHaveBeenCalledWith('STEP');
});
