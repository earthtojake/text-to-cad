import { act, cleanup, render } from '@testing-library/react';
import { useRef } from 'react';
import { afterEach, expect, test, vi } from 'vitest';
import type { ViewerCommandTarget, ViewerHost } from './types.js';
import type { DocumentSaveResult, DocumentSession } from '../file-viewer/types.js';
import { useViewerCommands } from './useViewerCommands.js';
afterEach(cleanup);
function fixture(id: string) {
  const targets: ViewerCommandTarget[] = [], unbind = vi.fn();
  const host: ViewerHost = { files: { id, rootName: id, stat: async path => ({ path, name: path, kind: 'file', size: 0, extension: 'txt' }) },
    commands: { bind: target => { targets.push(target); return unbind; } },
    navigation: { openFile: () => {} }, environment: { colorScheme: 'light' },
    clipboard: { readText: async () => '', writeText: async () => {}, writeImage: async () => {} },
    promptContext: { getSnapshot: () => ({ kind: 'unavailable', available: false }), subscribe: () => () => {}, deliver: async () => ({ status: 'cancelled' }) } };
  return { host, targets, unbind };
}
function editable(save: DocumentSession['save']): DocumentSession {
  return { key: 'generation', value: 'draft', dirty: true, readOnly: false, saving: false, stale: false, error: null,
    setValue: () => {}, save, reload: () => {}, keepMine: () => {} };
}
function View({ host, generation, value, reload }: { host: ViewerHost; generation: string; value: DocumentSession | null; reload: () => void }) {
  const element = useRef<HTMLDivElement | null>(null);
  useViewerCommands({ host, generation, document: value, reload, path: `${generation}.txt`, element });
  return <div ref={element} tabIndex={-1} data-testid={host.files.id} />;
}

test('two bindings save, reload and focus only their own viewer', async () => {
  const a = fixture('a'), b = fixture('b'), reloadA = vi.fn(), reloadB = vi.fn();
  const saveA = vi.fn(async (): Promise<DocumentSaveResult> => ({ status: 'conflict', actualRevision: 'external' }));
  const saveB = vi.fn(async (): Promise<DocumentSaveResult> => ({ status: 'saved', document: { content: 'draft' } }));
  const rendered = render(<><View host={a.host} generation="a1" value={editable(saveA)} reload={reloadA} /><View host={b.host} generation="b1" value={editable(saveB)} reload={reloadB} /></>);
  expect(await a.targets[0].save()).toMatchObject({ status: 'conflict' });
  expect(saveB).not.toHaveBeenCalled();
  expect(b.targets[0].focus()).toEqual({ status: 'completed' });
  expect(document.activeElement).toBe(rendered.getByTestId('b'));
  expect(a.targets[0].reload()).toEqual({ status: 'completed' });
  expect(a.targets[0].reload()).toEqual({ status: 'stale' });
  expect(reloadA).toHaveBeenCalledTimes(1); expect(reloadB).not.toHaveBeenCalled();
});

test('captured commands and pending saves cannot target a replacement generation', async () => {
  const a = fixture('a'), reload = vi.fn();
  let complete!: (result: DocumentSaveResult) => void;
  const save = vi.fn(() => new Promise<DocumentSaveResult>(resolve => { complete = resolve; }));
  const rendered = render(<View host={a.host} generation="first" value={editable(save)} reload={reload} />);
  const old = a.targets[0], pending = old.save();
  rendered.rerender(<View host={a.host} generation="second" value={null} reload={reload} />);
  expect(a.targets).toHaveLength(2);
  expect(old.focus()).toEqual({ status: 'stale' });
  expect(old.reload()).toEqual({ status: 'stale' });
  expect(await old.save()).toEqual({ status: 'stale' });
  expect(await a.targets[1].save()).toEqual({ status: 'unavailable' });
  await act(async () => { complete({ status: 'saved', document: { content: 'committed old draft' } }); });
  expect(await pending).toEqual({ status: 'stale', committed: true });
  expect(reload).not.toHaveBeenCalled(); expect(save).toHaveBeenCalledTimes(1);
  rendered.unmount();
  expect(a.targets[1].reload()).toEqual({ status: 'stale' });
  expect(a.unbind).toHaveBeenCalledTimes(2);
});

test('replacement sources invalidate captured commands even with the same public identity', () => {
  const a = fixture('root'), b = fixture('root'), reload = vi.fn();
  const rendered = render(<View host={a.host} generation="same" value={null} reload={reload} />);
  const captured = a.targets[0];
  rendered.rerender(<View host={b.host} generation="same" value={null} reload={reload} />);
  expect(captured.reload()).toEqual({ status: 'stale' });
  expect(a.unbind).toHaveBeenCalledTimes(1);
  expect(b.targets[0].focus()).toEqual({ status: 'completed' });
});
