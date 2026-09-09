import { createCadPreferences } from "@hardcore/ui/renderers/cad";
import type { CadPreferences, CadPreferenceSource } from "@hardcore/ui/renderers/cad";
import type { FileViewerState, JsonValue } from "@hardcore/ui/file-viewer";
import { readFileSheetTabLayoutStore, writeFileSheetTabLayoutStore } from "@hardcore/ui/renderers/cad/state";

const MIGRATION_KEY = "hardcore.cadMigration.v1";
type JsonObject = { [key: string]: JsonValue };
function object(value: unknown): value is JsonObject { return !!value && typeof value === "object" && !Array.isArray(value); }
function read(storage: Storage, key: string): JsonObject {
  try { const value: unknown = JSON.parse(storage.getItem(key) ?? "null"); return object(value) ? value : {}; }
  catch { return {}; }
}
function write(storage: Storage, key: string, value: JsonObject) { try { storage.setItem(key, JSON.stringify(value)); } catch { /* Storage can be unavailable. */ } }

/** Old global appearance/tips have a reliable meaning for every desktop root. */
export function migrateCadPreferences(storage: Storage): CadPreferences {
  const theme = read(storage, "cad-viewer:theme");
  const tips = read(storage, "cad-viewer:tutorial-tips:v1");
  return {
    fileSheetTabs: readFileSheetTabLayoutStore(storage),
    ...(theme.version === 13 && typeof theme.themeId === "string" ? { theme: { themeId: theme.themeId, custom: theme.custom ?? null } } : {}),
    ...(tips.version === 1 && Array.isArray(tips.seen) ? { seenTips: tips.seen.filter((tip): tip is string => typeof tip === "string") } : {}),
  };
}

let sharedPreferences: CadPreferenceSource | undefined;
/** CAD appearance is global to this desktop window, as the existing storage keys are. */
export function desktopCadPreferences(): CadPreferenceSource {
  if (!sharedPreferences) {
    let syncing = false;
    const snapshot = () => ({ theme: undefined, seenTips: [], ...migrateCadPreferences(localStorage) });
    const source = createCadPreferences({ initial: snapshot(), onChange: (preferences) => {
      if (syncing) return;
      if (preferences.theme) write(localStorage, "cad-viewer:theme", { version: 13, ...preferences.theme });
      if (preferences.seenTips) write(localStorage, "cad-viewer:tutorial-tips:v1", { version: 1, seen: preferences.seenTips });
      if (preferences.fileSheetTabs) writeFileSheetTabLayoutStore(localStorage, preferences.fileSheetTabs);
    } });
    // Browser storage events carry updates from another Hardcore window. This
    // host-owned store has the lifetime of the window, independent of its roots.
    window.addEventListener("storage", event => {
      if (!["cad-viewer:theme", "cad-viewer:tutorial-tips:v1", "cad-viewer:file-sheet-tab-layout:v5"].includes(event.key ?? "")) return;
      syncing = true;
      try { source.update(snapshot()); } finally { syncing = false; }
    });
    sharedPreferences = source;
  }
  return sharedPreferences;
}

/** Migrate only exact absolute-root namespaces; leave origin/unscoped records intact. */
export function migrateCadFileStates(sourceId: string, rootPath: string, local: Storage, session: Storage): NonNullable<FileViewerState["renderers"]> {
  const migrated = read(local, MIGRATION_KEY);
  if (migrated[sourceId]) return {};
  const prefix = `cad-viewer:file-session:v1:${encodeURIComponent(rootPath)}:`;
  const result: NonNullable<FileViewerState["renderers"]> = {};
  try {
    for (let index = 0; index < session.length; index += 1) {
      const key = session.key(index);
      if (!key?.startsWith(prefix)) continue;
      const fileSession = read(session, key);
      const path = decodeURIComponent(key.slice(prefix.length));
      if (fileSession.version !== 1 || fileSession.fileKey !== path || path.startsWith("/") || path.split("/").includes("..")) continue;
      result[JSON.stringify([path, "cad"])] = { version: 1, fileSession };
    }
    // The legacy directory-session value has no root identity. Its panel and
    // tree fields never owned desktop chrome, and its theme cannot be assigned
    // to this root safely. Preserve that record without copying it.
    const all = read(local, "hardcore.fileViewer.v1");
    const current = object(all[sourceId]) ? all[sourceId] : {};
    local.setItem("hardcore.fileViewer.v1", JSON.stringify({ ...all, [sourceId]: { ...result, ...current } }));
    write(local, MIGRATION_KEY, { ...migrated, [sourceId]: true });
  } catch { /* Keep defaults if a source storage backend is unavailable. */ }
  return result;
}
