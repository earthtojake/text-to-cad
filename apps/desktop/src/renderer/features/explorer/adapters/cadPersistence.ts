import { createCadPreferences } from "@hardcore/ui/renderers/cad";
import type { CadPreferences, CadPreferenceSource } from "@hardcore/ui/renderers/cad";
import type { FileViewerState, JsonValue } from "@hardcore/ui/file-viewer";
import { readOrbit, writeOrbit, ORBIT_STORAGE_KEY } from "@hardcore/ui/renderers/cad/state";

const MIGRATION_KEY = "hardcore.cadMigration.v1";
type JsonObject = { [key: string]: JsonValue };
function object(value: unknown): value is JsonObject { return !!value && typeof value === "object" && !Array.isArray(value); }
function read(storage: Storage, key: string): JsonObject {
  try { const value: unknown = JSON.parse(storage.getItem(key) ?? "null"); return object(value) ? value : {}; }
  catch { return {}; }
}
function write(storage: Storage, key: string, value: JsonObject) { try { storage.setItem(key, JSON.stringify(value)); } catch { /* Storage can be unavailable. */ } }

/** Global motion preferences apply to every desktop root. */
export function migrateCadPreferences(storage: Storage): CadPreferences {
  return {
    orbit: readOrbit(storage),
  };
}

let sharedPreferences: CadPreferenceSource | undefined;
/** CAD motion preferences are shared by every root in this desktop window. */
export function desktopCadPreferences(): CadPreferenceSource {
  if (!sharedPreferences) {
    let syncing = false;
    const snapshot = () => migrateCadPreferences(localStorage);
    let baseline = snapshot();
    const source = createCadPreferences({ initial: baseline, onChange: (preferences) => {
      if (!syncing) {
        if (preferences.orbit && JSON.stringify(preferences.orbit) !== JSON.stringify(baseline.orbit)) writeOrbit(localStorage, preferences.orbit);
      }
      baseline = preferences;
    } });
    // Browser storage events carry updates from another Hardcore window. This
    // host-owned store has the lifetime of the window, independent of its roots.
    window.addEventListener("storage", event => {
      if (event.key !== null && event.key !== ORBIT_STORAGE_KEY) return;
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
    // tree fields never owned desktop chrome. Preserve that record without
    // copying it; retired CAD theme overrides are never restored.
    const all = read(local, "hardcore.fileViewer.v1");
    const current = object(all[sourceId]) ? all[sourceId] : {};
    local.setItem("hardcore.fileViewer.v1", JSON.stringify({ ...all, [sourceId]: { ...result, ...current } }));
    write(local, MIGRATION_KEY, { ...migrated, [sourceId]: true });
  } catch { /* Keep defaults if a source storage backend is unavailable. */ }
  return result;
}
