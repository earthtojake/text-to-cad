import { imageResult } from './image-result';
import { movedFilePath } from '@text-to-cad/ui/file-viewer';
import type { DocumentDrafts, LiveTextDocument, LivePdfDocument, ViewerHost, TextDraft, LiveTextSnapshot, LivePdfSnapshot } from '@text-to-cad/ui/host';

export interface LiveDocumentScope { projectId: string; root: string | null; path?: string | null }
type Binding<T> = LiveDocumentScope & { sourceId: string; path: string; target: T };
const text = new Map<string, Binding<LiveTextDocument>>();
const pdf = new Map<string, Binding<LivePdfDocument>>();
const inactiveText = new Map<string, Binding<LiveTextSnapshot>>();
const inactivePdf = new Map<string, Binding<LivePdfSnapshot>>();
// Drafts have app-window lifetime. Project/tab switches do not evict unsaved work.
const retained = new Map<string, TextDraft>();
const draftOwners = new Map<string, Set<string>>();
function bind<T extends { sourceId: string; path: string }>(map: Map<string, Binding<T>>, tabId: string, scope: LiveDocumentScope, target: T) {
  const value = { ...scope, sourceId: target.sourceId, path: target.path, target }; map.set(tabId, value);
  return () => { if (map.get(tabId) === value) map.delete(tabId); };
}
export function desktopLiveDocuments(tabId: string, scope: LiveDocumentScope): Pick<ViewerHost, 'documents' | 'pdf'> {
  const ownedDrafts: DocumentDrafts = { get: (sourceId, path) => retained.get(JSON.stringify([tabId, sourceId, path])), put(sourceId, path, value) {
    const key = JSON.stringify([tabId, sourceId, path]);
    if (value) { const owned = draftOwners.get(tabId) ?? new Set<string>(); owned.add(key); draftOwners.set(tabId, owned); }
    if (value) retained.set(key, value); else retained.delete(key);
  } };
  return { documents: { drafts: ownedDrafts, bind: target => {
    inactiveText.delete(tabId);
    const release = bind(text, tabId, scope, target);
    return () => { if (text.get(tabId)?.target === target) inactiveText.set(tabId, { ...scope, sourceId: target.sourceId, path: target.path, target: target.read() }); release(); };
  } }, pdf: { assetBaseUrl: new URL("./pdfjs/", document.baseURI).href, bind: target => {
    inactivePdf.delete(tabId);
    const release = bind(pdf, tabId, scope, target);
    return () => { if (pdf.get(tabId)?.target === target) inactivePdf.set(tabId, { ...scope, sourceId: target.sourceId, path: target.path, target: target.state() }); release(); };
  } } };
}
/** The FileSource id a desktop file tab's drafts and bindings are keyed by. */
export function desktopSourceId(projectId: string, root: string | null): string {
  return JSON.stringify(['desktop', projectId, root]);
}
/**
 * A file or folder moved: every tab's draft and inactive snapshot follows it.
 * A mounted view carries its own draft across (useFileDocument), but a tab
 * that is not mounted — another tab of this session, any tab of another —
 * only has its path rewritten by the store; a draft left under the old name
 * is edits the tab no longer shows and a close that is refused forever.
 */
export function moveDocuments(sourceId: string, from: string, to: string): void {
  for (const [key, draft] of [...retained]) {
    const [tabId, source, path] = JSON.parse(key) as [string, string, string];
    const moved = source === sourceId ? movedFilePath(path, from, to) : path;
    if (moved === path) continue;
    const next = JSON.stringify([tabId, source, moved]);
    retained.delete(key); retained.set(next, draft);
    const owned = draftOwners.get(tabId);
    if (owned?.delete(key)) owned.add(next);
  }
  for (const map of [inactiveText, inactivePdf] as Map<string, { sourceId: string; path: string }>[]) {
    for (const [tabId, binding] of map) {
      const moved = binding.sourceId === sourceId ? movedFilePath(binding.path, from, to) : binding.path;
      if (moved !== binding.path) map.set(tabId, { ...binding, path: moved });
    }
  }
}
/** Close is a host workflow: never silently drop an unsaved live or retained draft. */
export function hasDirtyDocument(tabId: string): boolean {
  return Boolean(text.get(tabId)?.target.read().dirty || inactiveText.get(tabId)?.target.dirty
    || [...(draftOwners.get(tabId) ?? [])].some(key => retained.has(key)));
}
/** Any tab, mounted or not, holding text that is not on disk. */
export function hasAnyDirtyDocument(): boolean {
  return [...new Set([...text.keys(), ...inactiveText.keys(), ...draftOwners.keys()])].some(hasDirtyDocument);
}
/**
 * Drafts live only in this document, so a reload or close would drop them.
 * Refusing the unload hands the choice to main (`will-prevent-unload` in
 * src/main/menu.ts), which asks — or, when the app is quitting, proceeds.
 */
function guardUnload(event: BeforeUnloadEvent) {
  if (!hasAnyDirtyDocument()) return;
  event.preventDefault();
  event.returnValue = '';
}
if (typeof window !== 'undefined') window.addEventListener('beforeunload', guardUnload);
export function releaseDocumentTab(tabId: string): void {
  if (hasDirtyDocument(tabId)) throw new Error('Save or explicitly discard the document before closing its tab.');
  discardDocumentTab(tabId);
}
/** Explicit user discard; deleting bindings first prevents unmount from recreating snapshots. */
export function discardDocumentTab(tabId: string): void {
  text.delete(tabId); pdf.delete(tabId); inactiveText.delete(tabId); inactivePdf.delete(tabId);
  const owned = draftOwners.get(tabId); draftOwners.delete(tabId);
  for (const key of owned ?? []) {
    // A different tab holding the same file retains ownership of its draft.
    if (![...draftOwners.values()].some(keys => keys.has(key))) retained.delete(key);
  }
}
function target<T>(map: Map<string, Binding<T>>, params: Record<string, unknown>, scope: LiveDocumentScope): T {
  const binding = map.get(String(params.tabId));
  if (!binding || binding.projectId !== scope.projectId || binding.root !== scope.root || (scope.path !== undefined && binding.path !== scope.path)) throw new Error('No live document for this tab in the session workspace. Open and activate the file first.');
  return binding.target;
}
function requiredString(params: Record<string, unknown>, key: string) {
  const value = params[key]; if (typeof value !== 'string') throw new Error(`${key} must be a string.`); return value;
}
// The longest buffer the bridge reads or replaces, in UTF-16 units. The same
// number as MAX_DOCUMENT_CHARS in main's documents/module.mjs (the renderer
// cannot import it: change both; live-documents.test.ts holds them equal).
export const MAX_BRIDGE_DOCUMENT_CHARS = 2 * 1024 * 1024;
const TOO_LARGE_TO_EDIT = 'The buffer is too large to edit through the bridge; edit it in the editor.';
/**
 * A read result cut at the cap, flagged and noted in the text the agent sees;
 * the revision still names the whole buffer. `truncated` and `note` come
 * before `content` in the object: a client that clips the JSON it is handed
 * clips the tail, and the flag must not be in it.
 */
function boundedRead(snapshot: LiveTextSnapshot) {
  if (snapshot.content.length <= MAX_BRIDGE_DOCUMENT_CHARS) return snapshot;
  // A cut between the halves of a surrogate pair would end the text on a lone high surrogate.
  let end = MAX_BRIDGE_DOCUMENT_CHARS;
  const last = snapshot.content.charCodeAt(end - 1);
  if (last >= 0xd800 && last <= 0xdbff) end -= 1;
  return { truncated: true, note: `Only the first ${end} of ${snapshot.content.length} characters are shown; this buffer is too large to edit through the bridge.`,
    ...snapshot, content: snapshot.content.slice(0, end) };
}
export async function performDocumentCommand(kind: string, params: Record<string, unknown>, scope: LiveDocumentScope) {
  if (kind === 'document-read' && !text.has(String(params.tabId))) {
    const snapshot = target(inactiveText, params, scope);
    const binding = inactiveText.get(String(params.tabId))!;
    return { ...boundedRead(snapshot), tabId: String(params.tabId), sourceId: binding.sourceId, path: binding.path, active: false };
  }
  const document = target(text, params, scope);
  if (kind === 'document-read') return { ...boundedRead(document.read()), tabId: String(params.tabId), sourceId: document.sourceId, path: document.path, active: true };
  const expected = requiredString(params, 'expectedRevision');
  // A replacement is the whole buffer: over the cap the agent has only seen a cut read, and its content would drop the rest.
  if (kind === 'document-edit' && document.read().content.length > MAX_BRIDGE_DOCUMENT_CHARS) throw new Error(TOO_LARGE_TO_EDIT);
  if (kind === 'document-edit') return document.replace(requiredString(params, 'content'), expected);
  if (kind === 'document-save') return document.save(expected);
  throw new Error(`Unknown document command: ${kind}`);
}
export async function performPdfCommand(kind: string, params: Record<string, unknown>, scope: LiveDocumentScope) {
  if (kind === 'pdf-state' && !pdf.has(String(params.tabId))) return { ...target(inactivePdf, params, scope), active: false };
  const document = target(pdf, params, scope);
  if (kind === 'pdf-state') return { ...document.state(), active: true };
  if (kind === 'pdf-read') return { ...document.state(), pages: await document.read(params.startPage as number | undefined, params.endPage as number | undefined) };
  if (kind === 'pdf-page') return document.setPage(params.page as number);
  if (kind === 'pdf-capture') {
    const frozen = document.state();
    const capturedPage = params.page as number | undefined ?? frozen.page;
    const blob = await document.capture(capturedPage);
    // Through the same cap as the viewer and drawing captures: a page rendered at up to 4096 px can be over the model's image limit.
    return imageResult(blob, { ...frozen, page: capturedPage, visiblePage: frozen.page });
  }
  throw new Error(`Unknown PDF command: ${kind}`);
}
