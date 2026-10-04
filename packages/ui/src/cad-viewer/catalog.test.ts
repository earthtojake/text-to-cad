import { expect, test, vi } from 'vitest';
import { baseName, createCadFileActions, createCadFileSource, joinPath, normalizePath } from './catalog.js';

// A CAD client as the source reads it: a catalog of the files on screen, a folder at a time, a search.
function cadClient(entries: Record<string, unknown>[]) {
  let snapshot = { entries };
  const listeners = new Set<() => void>();
  const missing = Object.assign(new Error('File does not exist: /models/gone.step'), { code: 'cad-file-missing' });
  return {
    missing,
    getSnapshot: () => snapshot as never,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    resolveEntry: vi.fn(async (path: string) => {
      const entry = snapshot.entries.find(item => item.file === path);
      if (!entry) throw missing;
      return entry as never;
    }),
    folder: vi.fn(async (path: string) => ({ path, entries: [{ name: 'parts', kind: 'directory' as const }, { name: 'a.step', kind: 'file' as const }], truncated: false })),
    search: vi.fn(async (path: string) => ({ path, results: ['C:\\models\\parts\\a.step'], truncated: true })),
    publish(next: Record<string, unknown>[]) { snapshot = { entries: next }; for (const listener of [...listeners]) listener(); },
    listeners,
  };
}

test('a path has one spelling in every app: forward slashes, and no trailing one but the top of a filesystem\'s', () => {
  expect(['C:\\models\\a.step', '/models/parts/', '/', 'C:\\', ''].map(normalizePath)).toEqual(['C:/models/a.step', '/models/parts', '/', 'C:/', '']);
  expect([baseName('/models/parts/a.step'), baseName('C:\\models\\a.step'), baseName('/')]).toEqual(['a.step', 'a.step', '/']);
  expect([joinPath('/', 'models'), joinPath('C:/', 'models'), joinPath('/models/', 'a.step')]).toEqual(['/models', 'C:/models', '/models/a.step']);
});

test('the source reads a file from its catalog entry, a folder a time and a search through the client, all by absolute path', async () => {
  const client = cadClient([{ file: '/models/parts/Probe.STEP', bytes: 128, hash: 'one' }]);
  const source = createCadFileSource(client as never, { id: 'a' });
  const options = { signal: new AbortController().signal };
  expect(await source.stat('/models/parts/Probe.STEP', options)).toEqual({ path: '/models/parts/Probe.STEP', name: 'Probe.STEP', kind: 'file', size: 128,
    extension: 'step', mediaType: 'cad', revision: expect.any(String) });
  // A file the client does not have fails as the client says, so the viewer can say it does not exist.
  await expect(source.stat('/models/gone.step', options)).rejects.toBe(client.missing);
  expect(await source.list!('/', options)).toEqual([{ path: '/parts', name: 'parts', kind: 'directory' }, { path: '/a.step', name: 'a.step', kind: 'file' }]);
  expect(await source.list!('C:/models', options)).toEqual([{ path: 'C:/models/parts', name: 'parts', kind: 'directory' }, { path: 'C:/models/a.step', name: 'a.step', kind: 'file' }]);
  expect(await source.search!('C:/models', 'a', options)).toEqual({ paths: ['C:/models/parts/a.step'], truncated: true });
  expect(client.search).toHaveBeenCalledWith('C:/models', 'a', options);
});

test('the source reports only what changed in a file that stayed: progress is metadata, a new revision is content', () => {
  const probe = { file: '/models/probe.step', bytes: 128 };
  const flat = { file: '/models/flat.stl', bytes: 64 };
  const client = cadClient([probe, flat]);
  const source = createCadFileSource(client as never, { id: 'a' });
  const seen: unknown[] = [];
  const stop = source.subscribe!(change => seen.push(change));
  // The catalog is the files on screen: one going, or another coming, is a view moving, not the disk changing.
  client.publish([flat]);
  client.publish([flat, { file: '/models/other.step', bytes: 1 }]);
  client.publish([{ ...flat, compileProgress: 0.5 }]);
  client.publish([{ ...flat, compileProgress: 0.5, hash: 'new' }]);
  expect(seen).toEqual([
    { sourceId: 'a', changes: [{ kind: 'metadata', path: '/models/flat.stl' }] },
    { sourceId: 'a', changes: [{ kind: 'content', path: '/models/flat.stl', revision: expect.any(String) }] },
  ]);
  stop();
  expect(client.listeners.size).toBe(0);
});

test('the file menu copies a file\'s absolute path, and reveals it only where its host can', async () => {
  const copied: string[] = [];
  const clipboard = { writeText: async (text: string | Promise<string>) => { copied.push(await text); } };
  const reveal = vi.fn(async () => {});
  const actions = createCadFileActions({ platform: 'darwin', clipboard, reveal });
  await actions.perform!['copy-path']!({ path: 'C:\\models\\a.step', kind: 'file' });
  await actions.perform!.reveal!({ path: '/models/a.step', kind: 'file' });
  expect([copied, reveal.mock.calls, actions.platform]).toEqual([['C:/models/a.step'], [['/models/a.step']], 'darwin']);
  // A host that cannot reveal copies, and that is all; a platform it does not know is named the Linux way.
  const plain = createCadFileActions({ clipboard, platform: 'plan9' });
  expect([Object.keys(plain.perform!), plain.platform]).toEqual([['copy-path'], 'linux']);
});
