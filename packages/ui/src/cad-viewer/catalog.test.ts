import { expect, test, vi } from 'vitest';
import { baseName, createCadFileActions, createCadFileSource, joinPath, normalizePath } from './catalog.js';

// A CAD client as the source reads it: a file's catalog entry, a folder at a time, a search.
function cadClient(entries: Record<string, unknown>[]) {
  const missing = Object.assign(new Error('File does not exist: /models/gone.step'), { code: 'cad-file-missing' });
  return {
    missing,
    resolveEntry: vi.fn(async (path: string) => {
      const entry = entries.find(item => item.file === path);
      if (!entry) throw missing;
      return entry as never;
    }),
    folder: vi.fn(async (path: string) => ({ path, entries: [{ name: 'parts', kind: 'directory' as const }, { name: 'a.step', kind: 'file' as const }], truncated: false })),
    search: vi.fn(async (path: string) => ({ path, results: ['C:\\models\\parts\\a.step'], truncated: true })),
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
  expect([Object.keys(plain.perform!), plain.platform, plain.apps, plain.openApp]).toEqual([['copy-path'], 'linux', undefined, undefined]);
});

test('Open in asks the client for a document\'s apps by its id: a model\'s by its own, a file\'s by its row\'s', async () => {
  const id = '6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab';
  const files = { targets: [] };
  const client = { openInApps: vi.fn(async () => files), openIn: vi.fn(async () => {}),
    entryOf: vi.fn((path: string) => (path === '/models/a.step' ? { id: 'file-a', file: path } : null)) };
  const actions = createCadFileActions({ clipboard: { writeText: async () => {} }, openIn: client as never });
  const signal = new AbortController().signal;
  expect(await actions.apps!({ path: id, kind: 'file' }, { signal })).toBe(files);
  expect(await actions.apps!({ path: '/models/a.step', kind: 'file' })).toBe(files);
  // A file the client holds no row of has no id to ask by: no apps, and nothing asked.
  expect(await actions.apps!({ path: '/models/unknown.step', kind: 'file' })).toBeNull();
  expect(client.openInApps.mock.calls).toEqual([[id, { signal }], ['file-a', {}]]);
  await actions.openApp!({ path: '/models/a.step', kind: 'file' }, 'source', 'freecad');
  expect(client.openIn).toHaveBeenCalledWith('file-a', 'source', 'freecad');
});

test('a document the engine holds by its id alone keeps its id, is named by its model and has no file to browse', async () => {
  const id = '6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab';
  const client = cadClient([{ id, file: id, name: 'bracket', sourcePath: null, kind: 'xbf', bytes: 0 }]);
  const source = createCadFileSource(client as never);
  const options = { signal: new AbortController().signal };
  const stat = await source.stat(id, options);
  expect(stat).toMatchObject({ path: id, name: 'bracket', navigationPath: null, extension: 'xbf', mediaType: 'cad-document' });
  expect('folder' in stat).toBe(false);
  // No script named, no file to act on; one named is its file menu's (`sourceFile`), never a place to
  // browse from, and one the envelope says is gone is `sourceMissing`.
  expect(['sourceFile' in stat, 'sourceMissing' in stat]).toEqual([false, false]);
  const scripted = (sourcePresent: boolean) => createCadFileSource(cadClient([{ id, file: id, name: 'bracket', sourcePath: null,
    script: 'C:\\m\\parts.py', sourcePresent, kind: 'xbf', bytes: 0 }]) as never).stat(id, options);
  const present = await scripted(true);
  expect([present.sourceFile, 'sourceMissing' in present]).toEqual(['C:/m/parts.py', false]);
  expect(await scripted(false)).toMatchObject({ path: id, navigationPath: null, sourceFile: 'C:/m/parts.py', sourceMissing: true });
  // No live-document collection: the home is Recents.
  expect('collections' in source).toBe(false);
});
