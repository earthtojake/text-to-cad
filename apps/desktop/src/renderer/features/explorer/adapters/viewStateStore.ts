import type { FileViewerState, JsonValue } from "@hardcore/ui/file-viewer";

// The per-tab renderer records (camera, display settings, a renderer's own slice), one
// localStorage entry keyed by `[sourceId, tabId]`. A record lives as long as its tab: a
// closed tab's record is forgotten, or the store would grow with every file ever opened.
const KEY = "hardcore.fileViewer.v1";
export type RendererStates = NonNullable<FileViewerState["renderers"]>;
export const viewStateKey = (sourceId: string, tabId: string) => JSON.stringify([sourceId, tabId]);

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

export function readViewState(stateKey: string): RendererStates {
  const entry = readAll()[stateKey];
  return entry && typeof entry === "object" && !Array.isArray(entry) ? entry as Record<string, JsonValue> : {};
}
export function writeViewState(stateKey: string, renderers: RendererStates) {
  writeAll({ ...readAll(), [stateKey]: renderers });
}
/** A tab closed for good: its records go, whichever root it showed. */
export function forgetViewState(tabId: string) {
  const entries = readAll();
  const kept = Object.fromEntries(Object.entries(entries).filter(([key]) => {
    try { const parsed = JSON.parse(key); return !(Array.isArray(parsed) && parsed[1] === tabId); } catch { return true; }
  }));
  if (Object.keys(kept).length !== Object.keys(entries).length) writeAll(kept);
}
