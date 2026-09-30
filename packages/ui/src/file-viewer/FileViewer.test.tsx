import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { unavailablePromptContext } from '@text-to-cad/core/prompt';
import { FileViewer, defineFileRenderer } from '../../dist/file-viewer/index.js';

beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const renderer = defineFileRenderer({
  id: 'plain', priority: 1, matches: () => true,
  load: async () => ({ default: () => <p>shown</p> }),
  prepare: async () => ({ data: null }),
});
// A host that shows one file and browses nothing: a source with no listing, as an agent host's file view has.
const host = {
  files: { id: 'one', rootName: 'one', stat: async (path: string) => ({ path, name: path, kind: 'file' as const, extension: 'step', size: 1 }) },
  clipboard: { writeText: async () => {}, readText: async () => '', writeImage: async () => {} },
  promptContext: unavailablePromptContext, environment: { colorScheme: 'light' as const }, navigation: { openFile() {} },
};
const open = (props: { navigationPath?: string | null; leading?: JSX.Element }) =>
  render(<FileViewer file="parts/a.step" host={host as any} renderers={[renderer]} state={{ panel: null }} onStateChange={() => {}} {...props} />);

it('draws the nav row only when it has something to hold', async () => {
  open({ navigationPath: null });
  await screen.findByText('shown');
  expect(screen.queryByRole('navigation', { name: 'Breadcrumb' })).toBeNull();
  cleanup();
  open({ navigationPath: null, leading: <button type="button">Back</button> });
  await screen.findByText('shown');
  expect(screen.getByRole('navigation', { name: 'Breadcrumb' })).toBeTruthy();
  cleanup();
  open({});
  await screen.findByText('shown');
  expect(screen.getByRole('button', { name: 'Browse a.step' })).toBeTruthy();
});
