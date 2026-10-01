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
  const entries = readAll();
  if (!(tabId in entries)) return;
  delete entries[tabId];
  writeAll(entries);
}
