import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, test } from 'vitest';
import { useLiveDocument } from './useLiveDocument.js';
import { useFileDocument } from '../file-viewer/hooks/useFileDocument.js';
import type { LiveTextDocument, TextDraft } from './documents.js';
import type { ViewerHost } from './types.js';
import type { FileSource, RendererRegistration } from '../file-viewer/types.js';

afterEach(cleanup);
test('dirty drafts survive unmount and a fresh disk revision marks them stale; reload discards', async () => {
  const drafts = new Map<string, TextDraft>();
  let disk = { content: 'disk', revision: 'r1' };
  const source: FileSource = { id: 'root', rootName: 'root', stat: async path => ({ path, name: path, kind: 'file', size: 4, extension: 'txt' }), writeText: async () => ({ status: 'conflict' }) };
  const renderers: RendererRegistration[] = [{ id: 'text', matches: () => true, priority: 1, prepare: async () => ({ Component: () => null, text: disk }) }];
  const store = { get: (source: string, path: string) => drafts.get(source + path), put: (source: string, path: string, value: TextDraft | null) => { if (value) drafts.set(source + path, value); else drafts.delete(source + path); } };
  const first = renderHook(() => useFileDocument('a.txt', source, renderers, store));
  await waitFor(() => expect(first.result.current.document).not.toBeNull());
  act(() => first.result.current.document!.setValue('unsaved'));
  first.unmount(); disk = { content: 'external', revision: 'r2' };
  const reopenedSource = { ...source };
  const second = renderHook(() => useFileDocument('a.txt', reopenedSource, renderers, store));
  await waitFor(() => expect(second.result.current.document?.value).toBe('unsaved'));
  expect(second.result.current.document?.stale).toBe(true);
  act(() => second.result.current.document!.reload());
  await waitFor(() => expect(second.result.current.document?.value).toBe('external'));
  expect(drafts.size).toBe(0);
});
test('live revisions reject two edits with one token and detached commands fail', async () => {
  let target: LiveTextDocument | undefined;
  const source: FileSource = { id: 'root', rootName: 'root', stat: async path => ({ path, name: path, kind: 'file', size: 4, extension: 'txt' }), writeText: async (_path, options) => ({ status: 'saved', document: { content: options.content, revision: 'r2' } }) };
  const renderers: RendererRegistration[] = [{ id: 'text', matches: () => true, priority: 1, prepare: async () => ({ Component: () => null, text: { content: 'disk', revision: 'r1' } }) }];
  const documents: ViewerHost['documents'] = { drafts: { get: () => undefined, put: () => {} }, bind(value) { target = value; return () => {}; } };
  const host = { files: source, documents } as ViewerHost;
  const hook = renderHook(() => { const value = useFileDocument('a.txt', source, renderers); useLiveDocument(host, 'a.txt', value.document); return value; });
  await waitFor(() => expect(target).toBeDefined());
  const captured = target!; const token = captured.read().revision;
  act(() => {
    expect(captured.replace('agent edit', token).content).toBe('agent edit');
    expect(() => captured.replace('clobber', token)).toThrow(/revision conflict/);
  });
  expect(hook.result.current.document?.value).toBe('agent edit');
  const saved = await act(() => captured.save(captured.read().revision));
  expect(saved.status).toBe('saved');
  hook.unmount(); expect(() => captured.read()).toThrow(/no longer mounted/);
});
