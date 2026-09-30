import { expect, test, vi } from 'vitest';
import { createCadFileActions, createCatalogFileSource, findCatalogEntry, pathUnderRoot, referencePath, rootPath } from './catalog.js';

function catalogClient(entries: Record<string, unknown>[]) {
  let snapshot = { hydrated: true, entries };
  const listeners = new Set<() => void>();
  return {
    getSnapshot: () => snapshot as never,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    refresh: vi.fn(async () => ({ entries: [] })),
    resolveEntry: async (path: string) => findCatalogEntry(snapshot.entries as never, path) as never,
    publish(next: Record<string, unknown>[]) { snapshot = { ...snapshot, entries: next }; for (const listener of [...listeners]) listener(); },
    listeners,
  };
}

test('a catalog is browsed by its root-relative paths, and its changes arrive typed', async () => {
  const client = catalogClient([{ file: '/models/parts/probe.step', rootRelativeFile: 'parts/probe.step', bytes: 128 }, { file: 'flat.stl', bytes: 64 }]);
  const source = createCatalogFileSource(client, { id: 'a', rootName: 'This directory' });
  const options = { signal: new AbortController().signal };
  expect(await source.list!('', options)).toEqual([{ path: 'parts', name: 'parts', kind: 'directory' }, { path: 'flat.stl', name: 'flat.stl', kind: 'file' }]);
  expect(await source.paths!(options)).toEqual(['parts/probe.step', 'flat.stl']);
  expect(await source.stat('parts/probe.step', options)).toMatchObject({ path: 'parts/probe.step', name: 'probe.step', size: 128, extension: 'step', mediaType: 'cad' });
  // A root's catalog is read-only: no text, no assets, no edits.
  for (const unsupported of ['readText', 'readAsset', 'writeText', 'rename', 'create', 'duplicate', 'trash'] as const) expect(source[unsupported]).toBeUndefined();
  const seen: unknown[] = [];
  const stop = source.subscribe!(change => seen.push(change));
  client.publish([client.getSnapshot().entries[1] as never]);
  client.publish([{ file: 'flat.stl', bytes: 64, compileProgress: 0.5 }]);
  client.publish([{ file: 'flat.stl', bytes: 64, compileProgress: 0.5, hash: 'new' }]);
  expect(seen).toEqual([
    { sourceId: 'a', changes: [{ kind: 'deleted', path: 'parts/probe.step', entryKind: 'file' }] },
    // Progress is metadata; a new revision is content.
    { sourceId: 'a', changes: [{ kind: 'metadata', path: 'flat.stl' }] },
    { sourceId: 'a', changes: [{ kind: 'content', path: 'flat.stl', revision: expect.any(String) }] },
  ]);
  stop();
  expect(client.listeners.size).toBe(0);
  // A root that is not browsed shows its one file and lists nothing.
  const single = createCatalogFileSource(client, { id: 'a', rootName: 'a', browse: false });
  expect([single.list, single.paths]).toEqual([undefined, undefined]);
  const aborted = new AbortController(); aborted.abort();
  await expect(source.paths!({ signal: aborted.signal })).rejects.toMatchObject({ name: 'AbortError' });
});

test('a catalog entry is found by the path under its root, never by an absolute path', () => {
  const entry = { file: '/tmp/workspace/models/examples/sample.step', rootRelativeFile: 'examples/sample.step' };
  expect(findCatalogEntry([entry], 'examples/sample.step')).toBe(entry);
  expect(findCatalogEntry([entry], '/examples/sample.step/')).toBe(entry);
  expect(findCatalogEntry([entry], 'examples\\sample.step')).toBe(entry);
  expect(findCatalogEntry([entry], '/tmp/workspace/models/examples/sample.step')).toBeNull();
  expect(findCatalogEntry([entry], 'examples/sample')).toBeNull();
});

test('paths under a root: in its own separator on disk, in forward slashes in a prompt', () => {
  expect(rootPath('/models', 'parts/a.step')).toBe('/models/parts/a.step');
  expect(rootPath('/', 'Users/me/a.step')).toBe('/Users/me/a.step');
  expect(rootPath('C:\\models\\', 'parts/a.step')).toBe('C:\\models\\parts\\a.step');
  expect(pathUnderRoot('/models', '/models/parts/a.step')).toBe('parts/a.step');
  expect(pathUnderRoot('C:\\models', 'C:\\models\\parts\\a.step')).toBe('parts/a.step');
  expect(pathUnderRoot('/models', '/elsewhere/a.step')).toBeNull();
  const resource = { kind: 'workspace-file', workspaceId: 'w', path: 'parts/a.step' } as const;
  expect(referencePath(resource, { workspaceId: 'w', root: 'C:\\models' })).toBe('C:/models/parts/a.step');
  expect(referencePath({ kind: 'url', url: 'https://example.com/a.step' }, { workspaceId: 'w', root: '/models' })).toBe('https://example.com/a.step');
  expect(() => referencePath({ ...resource, workspaceId: 'other' }, { workspaceId: 'w', root: '/models' })).toThrow('another folder');
});

test('the file menu copies what a root can name, and reveals only where its host can', async () => {
  const copied: string[] = [];
  const clipboard = { writeText: async (text: string) => { copied.push(text); } };
  const reveal = vi.fn(async () => {});
  const actions = createCadFileActions({ root: '/models', platform: 'darwin', clipboard, reveal });
  await actions.perform!['copy-path']!({ path: 'parts', kind: 'directory' });
  await actions.perform!['copy-relative-path']!({ path: 'parts/a.step', kind: 'file' });
  await actions.perform!.reveal!({ path: 'parts/a.step', kind: 'file' });
  expect(copied).toEqual(['/models/parts', 'parts/a.step']);
  expect(reveal).toHaveBeenCalledWith('parts/a.step');
  expect(actions.platform).toBe('darwin');
  // A whole filesystem has no relative paths worth copying; a remote folder, no absolute ones.
  expect(Object.keys(createCadFileActions({ root: '/', clipboard, relative: false }).perform!)).toEqual(['copy-path']);
  expect(Object.keys(createCadFileActions({ clipboard, platform: 'plan9' }).perform!)).toEqual(['copy-relative-path']);
  expect(createCadFileActions({ clipboard, platform: 'plan9' }).platform).toBe('linux');
});
