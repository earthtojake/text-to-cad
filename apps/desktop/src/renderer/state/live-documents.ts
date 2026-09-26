import type { DocumentDrafts, LiveTextDocument, LivePdfDocument, ViewerHost, TextDraft, LiveTextSnapshot, LivePdfSnapshot } from '@hardcore/ui/host';

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
/** Close is a host workflow: never silently drop an unsaved live or retained draft. */
export function hasDirtyDocument(tabId: string): boolean {
  return Boolean(text.get(tabId)?.target.read().dirty || inactiveText.get(tabId)?.target.dirty
    || [...(draftOwners.get(tabId) ?? [])].some(key => retained.has(key)));
}
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
export async function performDocumentCommand(kind: string, params: Record<string, unknown>, scope: LiveDocumentScope) {
  if (kind === 'document-read' && !text.has(String(params.tabId))) {
    const snapshot = target(inactiveText, params, scope);
    const binding = inactiveText.get(String(params.tabId))!;
    return { ...snapshot, tabId: String(params.tabId), sourceId: binding.sourceId, path: binding.path, active: false };
  }
  const document = target(text, params, scope);
  if (kind === 'document-read') return { ...document.read(), tabId: String(params.tabId), sourceId: document.sourceId, path: document.path, active: true };
  const expected = requiredString(params, 'expectedRevision');
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
    const bytes = new Uint8Array(await blob.arrayBuffer());
    let binary = ''; for (const byte of bytes) binary += String.fromCharCode(byte);
    return { base64: btoa(binary), mimeType: 'image/png', ...frozen, page: capturedPage, visiblePage: frozen.page };
  }
  throw new Error(`Unknown PDF command: ${kind}`);
}
