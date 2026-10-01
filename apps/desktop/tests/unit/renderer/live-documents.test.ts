import { expect, test } from 'vitest';
import { MAX_DOCUMENT_CHARS } from '@main/integrations/documents/module.mjs';
import { MAX_BRIDGE_DOCUMENT_CHARS, desktopLiveDocuments, performDocumentCommand, performPdfCommand, hasDirtyDocument, releaseDocumentTab, discardDocumentTab } from '@renderer/state/live-documents';
import type { LiveTextSnapshot } from '@text-to-cad/ui/host';

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

test('two sessions opening the same resource retain independent unsaved buffers', () => {
  const a = desktopLiveDocuments('session-a-tab', { projectId: 'shared', root: null });
  const b = desktopLiveDocuments('session-b-tab', { projectId: 'shared', root: null });
  a.documents!.drafts.put('same-root', 'same.txt', { base: { content: 'disk' }, value: 'A unsaved', stale: false });
  expect(b.documents!.drafts.get('same-root', 'same.txt')).toBeUndefined();
  b.documents!.drafts.put('same-root', 'same.txt', { base: { content: 'disk' }, value: 'B unsaved', stale: false });
  expect(a.documents!.drafts.get('same-root', 'same.txt')?.value).toBe('A unsaved');
  discardDocumentTab('session-a-tab');
  expect(b.documents!.drafts.get('same-root', 'same.txt')?.value).toBe('B unsaved');
  discardDocumentTab('session-b-tab');
});

test('a reload or close with an unsaved draft anywhere is refused; main turns that into a question', () => {
  const unload = () => { const event = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(event); return event.defaultPrevented; };
  expect(unload()).toBe(false);
  const bindings = desktopLiveDocuments('unload-tab', { projectId: 'project', root: null });
  let snapshot: LiveTextSnapshot = { content: 'draft', revision: 'live', dirty: true, readOnly: false, stale: false };
  const release = bindings.documents!.bind({ sourceId: 'root', path: 'draft.txt', read: () => snapshot, replace: () => snapshot, save: async () => ({ status: 'unavailable' }) });
  expect(unload()).toBe(true);
  release();
  // Unmounted, the retained snapshot still holds the unsaved text.
  expect(unload()).toBe(true);
  snapshot = { ...snapshot, dirty: false };
  discardDocumentTab('unload-tab');
  expect(unload()).toBe(false);
});

test('read_document cuts a buffer over the edit cap and flags it; edit_document refuses such a buffer', async () => {
  const scope = { projectId: 'project', root: null };
  const host = desktopLiveDocuments('big-tab', scope);
  const big: LiveTextSnapshot = { content: 'x'.repeat(3 * 1024 * 1024), revision: 'live-1', dirty: false, readOnly: false, stale: false };
  let replaced = false;
  const release = host.documents!.bind({ sourceId: 'root', path: 'big.txt', read: () => big, replace: () => { replaced = true; return big; }, save: async () => ({ status: 'unavailable' }) });
  const read = await performDocumentCommand('document-read', { tabId: 'big-tab' }, scope) as unknown as { content: string; truncated?: boolean; note?: string; revision: string };
  expect(read.truncated).toBe(true);
  expect(read.content.length).toBe(2 * 1024 * 1024);
  expect(read.note).toMatch(/too large to edit/);
  expect(read.revision).toBe('live-1');
  await expect(performDocumentCommand('document-edit', { tabId: 'big-tab', expectedRevision: 'live-1', content: 'short' }, scope)).rejects.toThrow(/too large to edit through the bridge/);
  expect(replaced).toBe(false);
  release(); discardDocumentTab('big-tab');
});

test('the renderer\'s document cap is the one main\'s tool schema and body limit use', () => {
  expect(MAX_BRIDGE_DOCUMENT_CHARS).toBe(MAX_DOCUMENT_CHARS);
});

test('a cut read puts truncated and note ahead of content, and never ends on half a surrogate pair', async () => {
  const scope = { projectId: 'project', root: null };
  const host = desktopLiveDocuments('pair-tab', scope);
  // The emoji straddles the cap: its high surrogate is the last unit that fits.
  const content = 'x'.repeat(MAX_BRIDGE_DOCUMENT_CHARS - 1) + '\u{1F600}' + 'y'.repeat(10);
  const snapshot: LiveTextSnapshot = { content, revision: 'live-1', dirty: false, readOnly: false, stale: false };
  const release = host.documents!.bind({ sourceId: 'root', path: 'pair.txt', read: () => snapshot, replace: () => snapshot, save: async () => ({ status: 'unavailable' }) });
  const read = await performDocumentCommand('document-read', { tabId: 'pair-tab' }, scope) as unknown as { content: string };
  const json = JSON.stringify(read);
  expect(json.indexOf('"truncated"')).toBeGreaterThan(-1);
  expect(json.indexOf('"truncated"')).toBeLessThan(json.indexOf('"content"'));
  expect(json.indexOf('"note"')).toBeLessThan(json.indexOf('"content"'));
  const last = read.content.charCodeAt(read.content.length - 1);
  expect(last >= 0xd800 && last <= 0xdbff).toBe(false);
  release(); discardDocumentTab('pair-tab');
});
