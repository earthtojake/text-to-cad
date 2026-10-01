import { createTabStore, type TabRecord, type TabRecordStorage, type TabStore } from "@text-to-cad/ui/tab-store";

// The desktop's tab: each file tab's record (`@text-to-cad/ui/tab-store`: the tab's viewer settings
// and its file views), one localStorage entry keyed by tab id. A record lives as long as its tab:
// it survives a window reload and a restart, and a closed tab's record is forgotten, or the
// store would grow with every file ever opened. The explorer's own chrome — the panel column's
// width, each root's open folders, the open panel, the theme — is the window's and the
// session's, kept where the explorer keeps it, not here.
const KEY = "text-to-cad.tabs.v1";

function readAll(): Record<string, unknown> {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(KEY) ?? "null");
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {};
  } catch { return {}; }
}
function writeAll(entries: Record<string, unknown>) {
  try { localStorage.setItem(KEY, JSON.stringify(entries)); }
  catch { /* A blocked storage backend does not prevent opening or editing files. */ }
}

/** One tab's record in the shared entry: read whole, written whole. */
export function desktopTabRecord(tabId: string): TabRecordStorage {
  return {
    read: () => readAll()[tabId],
    write(record: TabRecord) { writeAll({ ...readAll(), [tabId]: record }); },
  };
}

const stores = new Map<string, TabStore>();
/** The tab's store, one per tab for the window's lifetime; the renderers and the file tab share it. */
export function desktopTabStore(tabId: string): TabStore {
  let store = stores.get(tabId);
  if (!store) { store = createTabStore(desktopTabRecord(tabId)); stores.set(tabId, store); }
  return store;
}
/** A tab closed for good: its record goes, whichever roots it showed. */
export function forgetTabStore(tabId: string) {
  stores.delete(tabId);
  forgetWhere((candidate) => candidate === tabId);
}

// Which session each stored tab belongs to. A session deleted in a run that never loaded its
// strip has no tabs in memory to forget one by one, and without this its records stayed forever.
const OWNERS = "text-to-cad.tabs.owners.v1";
function readOwners(): Record<string, string> {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(OWNERS) ?? "null");
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, string> : {};
  } catch { return {}; }
}
function writeOwners(owners: Record<string, string>) {
  try { localStorage.setItem(OWNERS, JSON.stringify(owners)); }
  catch { /* As writeAll: the index is housekeeping, not something a tab needs. */ }
}
function forgetWhere(doomed: (tabId: string, owner: string | undefined) => boolean) {
  const owners = readOwners(), entries = readAll();
  let changed = false;
  for (const tabId of new Set([...Object.keys(owners), ...Object.keys(entries)])) {
    if (!doomed(tabId, owners[tabId])) continue;
    stores.delete(tabId);
    delete owners[tabId]; delete entries[tabId];
    changed = true;
  }
  if (changed) { writeAll(entries); writeOwners(owners); }
}

/** The session a strip's file tabs belong to, noted whenever the strip is loaded or saved. */
export function rememberTabOwners(sessionId: string, tabIds: readonly string[]) {
  const owners = readOwners();
  const missing = tabIds.filter((tabId) => owners[tabId] !== sessionId);
  if (missing.length === 0) return;
  for (const tabId of missing) owners[tabId] = sessionId;
  writeOwners(owners);
}
/** A session gone for good: every record its tabs left, loaded this run or not. */
export function forgetSessionTabStores(sessionId: string) {
  forgetWhere((_tabId, owner) => owner === sessionId);
}
/** Records of sessions that no longer exist (`sessions` is every session, archived ones too). */
export function pruneTabStores(sessions: ReadonlySet<string>) {
  forgetWhere((_tabId, owner) => owner !== undefined && !sessions.has(owner));
}
