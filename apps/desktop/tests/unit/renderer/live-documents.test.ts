import { expect, test } from 'vitest';
import { desktopLiveDocuments, performDocumentCommand, performPdfCommand, hasDirtyDocument, releaseDocumentTab } from '@renderer/state/live-documents';
import type { LiveTextSnapshot } from '@hardcore/ui/host';

test('inactive documents preserve unsaved reads, isolate worktrees, and cannot silently close', async () => {
  const scope = { projectId: 'project', root: '/worktree' };
  const bindings = desktopLiveDocuments('retained-tab', scope);
  let snapshot: LiveTextSnapshot = { content: 'unsaved human draft', revision: 'live-2', diskRevision: 'disk-1', dirty: true, readOnly: false, stale: false };
  const release = bindings.documents!.bind({ sourceId: 'root', path: 'draft.txt', read: () => snapshot,
    replace: () => snapshot, save: async () => ({ status: 'unavailable' }) });
  expect(await performDocumentCommand('document-read', { tabId: 'retained-tab' }, scope)).toMatchObject({ active: true, content: 'unsaved human draft' });
  release();
  expect(await performDocumentCommand('document-read', { tabId: 'retained-tab' }, scope)).toMatchObject({ active: false, content: 'unsaved human draft' });
  expect(hasDirtyDocument('retained-tab')).toBe(true);
  expect(() => releaseDocumentTab('retained-tab')).toThrow(/Save or explicitly discard/);
  await expect(performDocumentCommand('document-read', { tabId: 'retained-tab' }, { ...scope, root: null })).rejects.toThrow(/workspace/);
  await expect(performDocumentCommand('document-edit', { tabId: 'retained-tab', expectedRevision: 'live-2', content: 'replacement' }, scope)).rejects.toThrow(/activate/);
  snapshot = { ...snapshot, dirty: false };
  const unbind = bindings.documents!.bind({ sourceId: 'root', path: 'draft.txt', read: () => snapshot, replace: () => snapshot, save: async () => ({ status: 'unavailable' }) });
  unbind(); releaseDocumentTab('retained-tab');
  await expect(performDocumentCommand('document-read', { tabId: 'retained-tab' }, scope)).rejects.toThrow(/workspace/);
});

test('inactive PDFs report their last visible page while captures require a live viewer', async () => {
  const scope = { projectId: 'project', root: null };
  const host = desktopLiveDocuments('pdf-tab', scope);
  const release = host.pdf!.bind({ sourceId: 'root', path: 'a.pdf', state: () => ({ sourceId: 'root', path: 'a.pdf', page: 3, pageCount: 5, selection: 'selected' }),
    read: async () => [], setPage: () => { throw new Error('unused'); }, capture: async () => new Blob() });
  release();
  expect(await performPdfCommand('pdf-state', { tabId: 'pdf-tab' }, scope)).toMatchObject({ active: false, page: 3, selection: 'selected' });
  await expect(performPdfCommand('pdf-capture', { tabId: 'pdf-tab' }, scope)).rejects.toThrow(/activate/);
  releaseDocumentTab('pdf-tab');
});

test('retained snapshots cannot impersonate a different file in a reused tab', async () => {
  const scope = { projectId: 'project', root: null };
  const host = desktopLiveDocuments('reused', scope);
  const snapshot: LiveTextSnapshot = { content: 'private old file', revision: 'live', dirty: false, readOnly: false, stale: false };
  const release = host.documents!.bind({ sourceId: 'source', path: 'old.txt', read: () => snapshot, replace: () => snapshot, save: async () => ({ status: 'unavailable' }) });
  release();
  await expect(performDocumentCommand('document-read', { tabId: 'reused' }, { ...scope, path: 'new.pdf' })).rejects.toThrow(/workspace/);
  expect(await performDocumentCommand('document-read', { tabId: 'reused' }, { ...scope, path: 'old.txt' })).toMatchObject({ content: 'private old file' });
  releaseDocumentTab('reused');
});

test('explicit discard removes owned drafts, including earlier files, and unmount cannot resurrect them', async () => {
  const { discardDocumentTab } = await import('@renderer/state/live-documents');
  const scope = { projectId: 'project', root: null };
  const host = desktopLiveDocuments('discard', scope);
  host.documents!.drafts.put('root', 'prior.txt', { base: { content: 'base' }, value: 'unsaved earlier file', stale: false });
  const snapshot: LiveTextSnapshot = { content: 'unsaved', revision: 'live', dirty: true, readOnly: false, stale: false };
  const release = host.documents!.bind({ sourceId: 'root', path: 'current.txt', read: () => snapshot, replace: () => snapshot, save: async () => ({ status: 'unavailable' }) });
  host.documents!.drafts.put('root', 'current.txt', { base: { content: 'base' }, value: 'unsaved', stale: false });
  discardDocumentTab('discard'); release();
  expect(hasDirtyDocument('discard')).toBe(false);
  expect(host.documents!.drafts.get('root', 'prior.txt')).toBeUndefined();
  expect(host.documents!.drafts.get('root', 'current.txt')).toBeUndefined();
  await expect(performDocumentCommand('document-read', { tabId: 'discard' }, scope)).rejects.toThrow(/workspace/);
});
