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

it('opens a phone-sized tab with no file on the host\'s home, not under the sheet of its tree', async () => {
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue({ width: 400, height: 600 } as DOMRect);
  const browsing = { ...host, files: { ...host.files, list: async () => [] } };
  const empty = (presentation: object) =>
    render(<FileViewer file={null} host={browsing as any} renderers={[renderer]} state={{ panel: null }} onStateChange={() => {}} presentation={presentation} />);
  empty({ home: <p>home</p> });
  expect(await screen.findByText('home')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Show files' })).toBeTruthy();
  cleanup();
  // With nothing of its own there, the tree is all there is to reach for.
  empty({ empty: <p>nothing open</p> });
  expect(await screen.findByRole('button', { name: 'Hide files' })).toBeTruthy();
});
